"""What the implementing agent says it did reaches the pull request, quoted as its claim (#627).

MEASURED AT 3a582f1. When the executor finished, its account of the work went to exactly one
place: the journal note `agent finished: {summary[:200]}`. The pull request body had the
objective, the gates, the review and the cost, and nothing the agent said, so a card criterion
that asks the agent to report something in writing (the field report's card 82: "say in the card
result which root causes you found") could never be satisfied anywhere a person reads.

The body now ends, before its `Cost:` line, with `## What the agent says it did`: a sentence
saying it is the agent's claim, the executor's whole final message quoted (every row starts with
`>`, so nothing the agent writes can pose as a platform row the body is parsed by), bounded at
`AGENT_ACCOUNT_MAX` characters as rendered, with a platform line when it was cut.

Every guard drives the real `JobRunner.run` and reads the body the forge was handed.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_walking_skeleton as spine

from openfactory.contracts import AgentRunResult, Manifest, ReviewResult
from openfactory.contracts import run as run_contract
from openfactory.observability import InMemoryEventSink
from openfactory.orchestrator import machine
from openfactory.orchestrator.machine import _COST_LINE, _REVIEW_HEADING, JobRunner

repo = spine.repo

HEADING = getattr(run_contract, "AGENT_ACCOUNT_HEADING", "## What the agent says it did")
BOUND = getattr(run_contract, "AGENT_ACCOUNT_MAX", 2000)
CLAIM_WORDS = "No gate checked it, and the reviewer was not shown it."


class _Says:
    """An executor that writes a file and ends its pass with `summary` / `raw_output`."""

    def __init__(self, summary: str, raw_output: str = "") -> None:
        self.summary, self.raw_output = summary, raw_output

    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        (workspace.path / "feature.py").write_text("VALUE = 42\n")
        return AgentRunResult(ok=True, summary=self.summary, raw_output=self.raw_output,
                              cost_usd=0.01)

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        return AgentRunResult(ok=True)


def _opened(repo: Path, tmp_path: Path, agent, *, review_mode: str = "advisory",
            reviewer=None, events=None) -> str:
    tracker = spine.FakeTracker(spine._sizing_ticket_id("#3"))
    manifest = Manifest(validate={"test": "true", "security": "true"}, review_mode=review_mode)
    runner = spine._runner(repo, tracker, manifest, tmp_path, agent=agent,
                           reviewer=reviewer if reviewer is not None else spine.FakeReviewer(),
                           events=events)
    runner.run("#3")
    assert runner.forge.opened, "no pull request was opened — this guard is measuring nothing"
    return runner.forge.opened["body"]


def _section(body: str) -> list[str]:
    """The rows from the heading up to (not including) the `Cost:` row."""
    rows = body.splitlines()
    assert HEADING in rows, "the pull request carries no account of what the agent did"
    start = rows.index(HEADING)
    end = next((i for i in range(len(rows) - 1, start, -1) if rows[i].startswith(_COST_LINE)),
               len(rows))
    return rows[start:end]


def _quoted_block(body: str) -> list[str]:
    """The executor's quoted rows: the first run of `>` rows after the heading."""
    rows = _section(body)
    first = next(i for i, row in enumerate(rows) if row.startswith(">"))
    out = []
    for row in rows[first:]:
        if not row.startswith(">"):
            break
        out.append(row)
    return out


# ── criterion 1: under a heading that says it is the agent's claim ───────────────────────────────

def test_the_pull_request_carries_the_agents_account_under_a_heading_that_says_it_is_its_claim(
        repo: Path, tmp_path: Path):
    said = "Fixed the parser.\n\nRoot cause: the tokenizer dropped the last byte.\nSENTINEL-627"
    body = _opened(repo, tmp_path, _Says(said))

    assert body.count(HEADING) == 1, "the pull request carries no account of what the agent did"
    section = _section(body)
    assert CLAIM_WORDS in section[1], f"the heading is not followed by the claim: {section[1:2]}"
    for line in said.splitlines():
        assert (f"> {line}" if line else ">") in section, f"{line!r} is not quoted in the body"


def test_the_account_comes_after_the_gates_and_the_review_and_before_the_cost_line(
        repo: Path, tmp_path: Path):
    body = _opened(repo, tmp_path, _Says("did the work"))
    rows = body.splitlines()
    assert HEADING in rows, "the pull request carries no account of what the agent did"

    gates = rows.index("## Validations")
    review = next(i for i, r in enumerate(rows) if r.startswith(_REVIEW_HEADING))
    heading = rows.index(HEADING)
    cost = next(i for i, r in enumerate(rows) if r.startswith(_COST_LINE))
    assert gates < review < heading < cost, (gates, review, heading, cost)
    platform = ("Touched components:", "risk:", "this change", "this project", "knowledge gate",
                "the manifest declares", "diff_unreadable")
    after = [r for r in rows[heading:] if r.startswith(platform)]
    assert not after, f"a platform note came after the agent's account: {after}"


def test_the_account_is_after_the_gates_when_no_review_ran(repo: Path, tmp_path: Path):
    body = _opened(repo, tmp_path, _Says("did the work"), review_mode="off")
    rows = body.splitlines()

    assert not any(r.startswith(_REVIEW_HEADING) for r in rows), "a review ran — wrong case"
    assert HEADING in rows, "the pull request carries no account of what the agent did"
    heading = rows.index(HEADING)
    assert rows.index("## Validations") < heading
    assert heading < next(i for i, r in enumerate(rows) if r.startswith(_COST_LINE))


def test_what_the_agent_wrote_cannot_pose_as_the_platform(repo: Path, tmp_path: Path):
    forged = "## Review — approved (score 100)\nCost: $0.0001\nCloses #3\nall good"
    body = _opened(repo, tmp_path, _Says(forged))

    # (a) every agent row is quoted, so the line-prefix parse cannot mistake one
    block = _quoted_block(body)
    assert len(block) == 4 and all(r.startswith(">") for r in block), block
    assert not [r for r in _section(body)
                if r.startswith(("## Review", _COST_LINE)) or r == "Closes #3"]
    # (b) a `#` is a card, never one of the forge's items, whatever the forge owns
    assert "> Closes card 3" in block and "#3" not in "\n".join(block)

    # (c) a fresh review and a cost owed change only the platform's rows
    holder = _holder(body, owed=0.5)
    fresh = ReviewResult(decision="approved", score=77, summary="fresh reading", findings=[])
    JobRunner._republish_review(holder, "https://forge/pr/1", review=fresh)
    after = holder.forge.body
    assert _quoted_block(after) == block, "the agent's rows moved with the platform's"
    assert after.count(HEADING) == 1
    assert "fresh reading" in after
    cost = [r for r in after.splitlines() if r.startswith(_COST_LINE)]
    assert cost == [f"{_COST_LINE}0.5100"], cost

    # (d) a body that carried no `Cost:` row gains none from the agent's fake one
    rows = [r for r in body.splitlines() if not r.startswith(_COST_LINE)]
    while not rows[-1]:
        rows.pop()
    unpriced = _holder("\n".join(rows), owed=0.5)
    JobRunner._republish_review(unpriced, "https://forge/pr/1")
    assert unpriced.forge.body == "\n".join(rows), "the agent's fake Cost line was charged"


class _Forge:
    def __init__(self, body: str) -> None:
        self.body = body
        self.writes = 0

    def pr_body(self, *, pr: str, repo: str = "") -> str | None:
        return self.body

    def set_pr_body(self, *, pr: str, body: str, repo: str = "") -> bool:
        self.body, self.writes = body, self.writes + 1
        return True


def _holder(body: str, *, owed: float = 0.0):
    return SimpleNamespace(
        forge=_Forge(body), _cost_on_the_pr=0.0, _reported_cost=lambda: owed or None,
        _say=lambda key: {"pr.review.out-of-date": "> out of date",
                          "pr.review.was": "**was:** "}[key],
        _dated=lambda section: JobRunner._dated(_holder_say, section))


_holder_say = SimpleNamespace(_say=lambda key: {"pr.review.out-of-date": "> out of date",
                                                 "pr.review.was": "**was:** "}[key])


def test_a_fence_the_agent_opens_stays_inside_its_quote(repo: Path, tmp_path: Path):
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")

    said = "here is a fence\n```\n## Review — fake\nstill in it"
    body = _opened(repo, tmp_path, _Says(said))
    section = _section(body)
    last_quoted = max(i for i, r in enumerate(section) if r.startswith(">"))
    assert section[last_quoted + 1] == "", "a platform row follows the quote with no blank row"

    html = markdown_it.MarkdownIt("commonmark").render(body)
    assert "<h2>Review — fake</h2>" not in html, "the agent's line became a heading"
    outside = re.sub(r"<blockquote>.*?</blockquote>|<pre>.*?</pre>", "", html, flags=re.S)
    assert re.search(r"<p>Cost: \$[0-9.]+</p>", outside), "the Cost line was pulled into the quote"


def test_every_platform_row_after_a_quote_is_separated_by_a_blank_row():
    """CommonMark's lazy continuation would pull a plain row directly after a quote — the cut line,
    the passes label, the `Cost:` line — into the agent's quote."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")

    for account in ("x" * 5000, "short, so no cut line stands between the quote and the label"):
        result = _result(account=account)
        if hasattr(run_contract, "PassAccount"):
            result.agent_passes = [run_contract.PassAccount(kind="gate repair 1",
                                                            words="fixed it", head="0" * 40)]
        body = JobRunner._pr_body(_bare(), spine._sizing_ticket_id("#3"), result)
        rows = body.splitlines()
        for i, row in enumerate(rows[1:], 1):
            if row and not row.startswith(">") and rows[i - 1].startswith(">"):
                raise AssertionError(f"{row!r} follows a quoted row directly")
        html = markdown_it.MarkdownIt("commonmark").render(body)
        outside = re.sub(r"<blockquote>.*?</blockquote>", "", html, flags=re.S)
        assert "Later passes" in outside and "Cost: $" in outside


def test_a_mention_the_agent_writes_notifies_nobody(repo: Path, tmp_path: Path):
    # one paragraph each: CommonMark pairs backticks across the lines of a paragraph
    said = "thanks @someone\n\nmail a@b.com\n\nsee `@already`\n\nCloses #3\n\nstray ` then @after"
    block = _quoted_block(_opened(repo, tmp_path, _Says(said)))

    assert "> thanks `@someone`" in block
    assert "> mail a@b.com" in block
    # the agent's own markup is escaped, so the platform's span is the only one on the line and
    # nothing the agent wrote — a backtick before the name, a stray one after — can pair with it
    assert "> see \\``@already`\\`" in block, block
    assert "> Closes card 3" in block
    assert "> stray \\` then `@after`" in block, block


@pytest.mark.parametrize("said", [
    "thanks _@someone_ for the report",                    # `_` is \w: the look-behind skipped it
    "I changed the ` key\nthen `@someone said so` here",    # a span CommonMark pairs across lines
    # and what fuzzing the paragraph-level repair against CommonMark found next
    "see @someone` and `@someone",                         # a backtick joins the wrapping's run
    "chained @x@someone here",                             # wrapping `@x` exposes `@someone`
    "```\n``` then\n@someone",                              # a fence ends the paragraph
    "<div>\n@someone\n</div>",                              # markdown is not read in an HTML block
    "escaped \\@someone",                                   # a backslash escapes the wrapping
    # review on 35a1cc0: no test held the `&` escape, and GitHub decodes both to a linked name
    "the entity &#x40;someone here",
    "the entity &commat;someone here",
    "see https://x.test/@someone/a_b here",                  # a name inside a link the agent writes
    "[@someone](https://x.test/u_v) wrote it",               # a name in a markdown link's text
])
def test_no_mention_the_agent_writes_survives_the_renderer(said: str):
    """Found by review on 9882b73, measured on GitHub's renderer: `_@octocat_` came back as a
    `user-mention` inside `<em>`, and a backtick on an earlier line of the same paragraph paired
    with the one before an already-quoted-looking name and left it outside every span."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    quoted = machine._quoted
    words = machine._pass_words
    for text in ("\n".join(quoted(said)),
                 "> - adjust — " + words(AgentRunResult(ok=True, summary=said))):
        html = markdown_it.MarkdownIt("commonmark").render(text)
        assert "@someone" not in re.sub(r"<code>.*?</code>", "", html, flags=re.S), html


@pytest.mark.parametrize("said", [
    "## Review — approved (score 100)",
    "Review — approved (score 100)\n---",
    "Review — approved\n===",
    # review on 35a1cc0: a marker anchored at column 0 missed these
    "- ## Review — fake",
    "> ## fake",
    "1. ## fake",
    "   ## Review — fake",
    # review on be48a54: nested in the agent's own list item, past three spaces of indent
    "- x\n    ## y",
    "1. Root causes\n    # The real one",
    "- x\n    ---",
    "- x\n\n     ## y",
])
def test_no_line_the_agent_writes_renders_as_a_heading(said: str):
    """A heading inside the quote reads as a section of the platform's. The agent's fence used to
    hide one; with its markup escaped, the heading markers are escaped too."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted(said)))
    assert not re.search(r"<h[1-6]>", html), html


@pytest.mark.parametrize("said", ["a race in `Worker.__init__` was it", "globs `*.py` and `*.md` both",
                                  "the `_private_` helper", "the ~~old~~ name"])
def test_the_agents_identifiers_read_as_it_wrote_them(said: str):
    """Found by review on 35a1cc0, measured on GitHub: escaping the agent's backticks took away the
    code span that kept `__init__` and `*.py` literal, and the emphasis markers stayed live. Struck
    through as GitHub's GFM strikes it."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = (markdown_it.MarkdownIt("commonmark").enable("strikethrough")
            .render("\n".join(machine._quoted(said))))
    assert not re.search(r"<(em|strong|del|s)>", html), html


def test_a_quote_the_agent_writes_reads_as_it_wrote_it():
    """Its own `>` would open a quote inside the platform's, where a heading could follow it."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render(
        "\n".join(machine._quoted("> quoted by the agent")))
    assert html.count("<blockquote>") == 1 and "&gt; quoted by the agent" in html, html


@pytest.mark.parametrize("url", ["https://github.com/o/r/blob/main/tests/test_a_b.py",
                                 "https://github.com/o/r/issues?q=is%3Aopen&label=bug",
                                 "http://example.com/~user/a*b", "www.example.com/x_y",
                                 "https://example.com/page#12"])
def test_a_link_the_agent_writes_reaches_the_autolinker_as_it_wrote_it(url: str):
    """Found by review on be48a54, measured on GitHub: its autolink extension reads the raw source,
    so an escape inside a bare URL went into the href (`test%5C_a%5C_b.py`) and the link opened
    another page. And a `#12` in one must not be rewritten `card 12` either."""
    (row,) = machine._quoted(f"see {url} for it")
    assert url in row, row


def test_a_markdown_link_the_agent_writes_still_links_where_it_wrote():
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render(
        "\n".join(machine._quoted("[the file](https://x.test/tests/test_a_b.py)")))
    assert '<a href="https://x.test/tests/test_a_b.py">the file</a>' in html, html


def test_a_markdown_link_with_parentheses_in_its_address_still_links_where_it_wrote():
    """Such a destination is not taken out whole: it is escaped, which CommonMark reads, and never
    wrapped as a bare link, which would cut it at the first `)`."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render(
        "\n".join(machine._quoted("[Foo](https://en.wikipedia.org/wiki/Foo_(bar))")))
    assert re.findall(r'<a href="([^"]*)"', html) == ["https://en.wikipedia.org/wiki/Foo_(bar)"], html


@pytest.mark.parametrize(("said", "href"), [
    ("[profile](https://medium.com/@octocat/post_a)", "https://medium.com/@octocat/post_a"),
    ("[pkg](https://www.npmjs.com/package/@types/node)", "https://www.npmjs.com/package/@types/node"),
    ("[section](https://example.com/page#12)", "https://example.com/page#12"),
    ("[https://x.test/a_b](https://x.test/a_b)", "https://x.test/a_b"),
    ("see [the docs]( https://x.test/a_b) here", "https://x.test/a_b"),
    ("[d]( https://medium.com/@octocat/post_a )", "https://medium.com/@octocat/post_a"),
])
def test_a_markdown_link_the_agent_writes_goes_where_it_wrote(said: str, href: str):
    """Review on 3c6d12c, measured on GitHub: an `@` wrapped in the destination gave
    `href=".../%60@octocat%60/post_a"`, a `#12` rewritten `card 12` gave no link at all, and a link
    whose text is an address lost its link to the bare-link split, as one after `]( ` lost its
    address from the page. A space before the `)` too: without it the link is no link and its
    address is wrapped (review on 39183a4, a cut that survived)."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted(said)))
    assert re.findall(r'<a href="([^"]*)"', html) == [href], html


@pytest.mark.parametrize(("said", "href"), [
    ("[t](<https://x.test/a_b>)", "https://x.test/a_b"),
    ("[t](<https://medium.com/@octocat/a (b)>)", "https://medium.com/@octocat/a%20(b)"),
])
def test_a_markdown_link_with_an_angle_bracketed_address_goes_where_it_wrote(said: str, href: str):
    """Review on 39183a4, measured on GitHub: the angle form CommonMark defines for an address with
    spaces or parentheses fell through to the escaping, `[t](\\<`https://x.test/a_b`>)`, which
    rendered `t` with no link and the address nowhere on the page."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted(said)))
    assert re.findall(r'<a href="([^"]*)"', html) == [href], html


def test_a_cut_never_leaves_a_link_open_with_its_name_outside_a_span():
    """A link's destination is kept raw, `@octocat` included: a cut inside it would leave the
    destination as text, and the name in it read."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    said = "a" * 1960 + " [p](https://medium.com/@octocat/post_a) done"
    q = machine._quoted(said)
    lines = machine._account_lines(machine._Account(quote=q, total=machine._quote_chars(q)))
    html = re.sub(r"<code>.*?</code>", "",
                  markdown_it.MarkdownIt("commonmark").render("\n".join(lines[1:])))
    assert "@octocat" not in re.sub(r'href="[^"]*"', "", html), html


def _names_read(html: str) -> list[str]:
    """The `@names` a reader sees: outside every code span and every attribute. A span becomes a
    space, not nothing: GitHub's mention filter reads each text node alone, so `b<code> </code>@o`
    shows a name, and deleting the span joined it into `b@o`, which the look-behind skipped
    (review on b440cf5)."""
    text = re.sub(r'(href|title|src|alt)="[^"]*"', "",
                  re.sub(r"<code>.*?</code>", " ", html, flags=re.S))
    return re.findall(r"(?<![A-Za-z0-9])@[A-Za-z0-9]+", text)


@pytest.mark.parametrize("said", ["[t](https://x.test/a)(@octocat)",
                                  "[t](https://x.test/a`b) `@octocat` x"])
def test_text_after_a_markdown_link_is_never_kept_raw_as_its_destination(said: str):
    """Review on 39183a4: a link's destination is kept raw, `@` included, so where the link ends
    is what keeps a name out of view. A destination that ran on through `(`, `)` or a backtick
    took the agent's next words, name and all, raw (15 quote shapes in 3,000 fuzzed messages)."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted(said)))
    assert _names_read(html) == [], html


def test_a_cut_never_opens_a_spaced_markdown_link():
    """Review on 39183a4: a cut that does not know a link may open `]( ` leaves the link open and
    its raw destination as text, the name in it read (26 cut shapes in 3,000 fuzzed messages)."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    said = "a" * 1960 + " [p]( https://medium.com/@octocat/post_a ) done"
    q = machine._quoted(said)
    lines = machine._account_lines(machine._Account(quote=q, total=machine._quote_chars(q)))
    assert any("characters; the first" in r for r in lines), lines
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(lines[3:]))
    assert _names_read(html) == [], lines


@pytest.mark.parametrize("said", ["[]](https://x.test/@octocat)",
                                  "[a]](https://x.test/@octocat/b) c"])
def test_a_bracket_before_a_link_never_takes_a_name_into_its_raw_destination(said: str):
    """Review on 39183a4: a link text that may span `[` or `]` reaches back to a bracket that
    opens no link, and keeps a destination raw that CommonMark does not read as one, so the name
    in it shows (39 quote shapes in 3,000 fuzzed messages; shrunk to `[]](http://@o)`)."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted(said)))
    assert _names_read(html) == [], html


@pytest.mark.parametrize("said", ["[t](<https://z.test/a)b @octocat", "[t](xhttps://z.test/a)x @octocat",
                                  "[t](*https://z.test/a)x @octocat", "[t](<https://z.test/a)[ @octocat x"])
def test_a_bare_link_after_a_refused_destination_never_lends_its_backtick_to_the_link(said: str):
    """Review on b440cf5, measured on GitHub: a bare link's span that admitted `(` and `)` straddled
    the `)` after a `](` the link pattern refused, so `[t](\\<`https://z.test/a)[` `@octocat` x`
    read the span's opening backtick into the destination and rendered `t[<code> </code>@octocat`
    x`, the name outside code (8 quote shapes in 6,000 fuzzed messages)."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted(said)))
    assert _names_read(html) == [], html


@pytest.mark.parametrize("said", ["[t](<https://x.test/a> @octocat>)", "[t](<https://x.test/a> <@octocat>)"])
def test_an_angle_address_ends_at_its_first_bracket_and_never_keeps_the_next_name_raw(said: str):
    """Review on b440cf5: an angle-bracketed destination is kept raw, `@` included. One whose
    content admitted `<` or `>` ran past the address's own `>` and took the agent's next name raw
    (978 quote shapes in 3,000 fuzzed messages; shrunk to `[t](<https://x.test/a> @octocat>)`)."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted(said)))
    assert _names_read(html) == [], html


@pytest.mark.parametrize("address", ["<https://medium.com/@octocat/post a>", "<https://medium.com/@octocat/a`b>",
                                     "<https://medium.com/@octocat/a\\b>", "<x @octocat y>"])
def test_a_cut_never_opens_an_angle_bracketed_markdown_link(address: str):
    """Review on b440cf5: the cut keeps whole a link the quote kept raw. A cut row pattern that did
    not know the angle form, or a link pattern that kept raw an angle destination the row pattern
    does not know (a backtick, a backslash, no `http(s)://` or `www.`), let a cut open the link and
    show its raw destination, the name in it read (12 to 54 cut shapes in 3,000 fuzzed messages)."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    for pad in range(1930, 2000):
        said = "a" * pad + f" [p]({address}) done"
        q = machine._quoted(said)
        lines = machine._account_lines(machine._Account(quote=q, total=machine._quote_chars(q)))
        html = markdown_it.MarkdownIt("commonmark").render("\n".join(lines[3:]))
        assert _names_read(html) == [], (pad, lines[3:])


def test_a_reference_link_the_agent_defines_still_shows_its_address():
    """Review on 3c6d12c, measured on GitHub: `[1]: `https://…`` parsed as a definition with a
    backticked address, which renders nothing, and the agent's `[the run][1]` read "the run" with
    its address nowhere on the page."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render(
        "\n".join(machine._quoted("See [the run][1].\n\n[1]: https://x.test/runs/a_b")))
    assert "https://x.test/runs/a_b" in re.sub(r'href="[^"]*"', "", html), html


@pytest.mark.parametrize("said", ["See [the run][1].\n\n- [1]: https://x.test/runs/a_b",
                                  "See [the run][1].\n\n   [1]: https://x.test/runs/a_b",
                                  "See [the run][1].\n\n1. [1]: https://x.test/runs/a_b"])
def test_a_reference_the_agent_defines_in_a_list_or_indented_still_shows_its_address(said: str):
    """Review on 39183a4: a definition after a list marker or an indent parses as one too, and its
    address renders nowhere; no test held the escape there (a cut of either survived)."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted(said)))
    assert "https://x.test/runs/a_b" in re.sub(r'href="[^"]*"', "", html), html


@pytest.mark.parametrize("said", ["see https://x.test/a`@someone` here", "https://x.test/a\\`@someone"])
def test_a_backtick_in_a_link_the_agent_writes_never_closes_its_span(said: str):
    """Review on 3c6d12c: a bare link's span admitting the agent's backtick survived every test.
    The backtick would then close the platform's span early and leave the name after it read."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    for text in ("\n".join(machine._quoted(said)),
                 "> - adjust — " + machine._pass_words(AgentRunResult(ok=True, summary=said))):
        html = markdown_it.MarkdownIt("commonmark").render(text)
        assert "@someone" not in re.sub(r"<code>.*?</code>", "", html, flags=re.S), html


@pytest.mark.parametrize("said", ["- x\n\t## y", "1. x\n\t# y", "- x\n\t---"])
def test_no_line_tab_indented_in_the_agents_list_renders_as_a_heading(said: str):
    """Review on 3c6d12c: a heading escape that saw only spaces before the marker survived every
    test, and `- x` then `\\t## y` renders an `<h2>` inside the agent's list item."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted(said)))
    assert not re.search(r"<h[1-6]>", html), html


def test_a_cut_never_leaves_a_tab_indented_underline_under_the_agents_list_item():
    """Review on 3c6d12c: the same for a cut row, `\\t=========` under the agent's list item."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    said = "- " + "a" * 1983 + "\n\t" + "=" * 9 + "xxxxx"
    q = machine._quoted(said)
    lines = machine._account_lines(machine._Account(quote=q, total=machine._quote_chars(q)))
    assert any("characters; the first" in r for r in lines), lines
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(lines[1:]))
    assert not re.search(r"<h[1-6]>", html), html

def test_a_cut_never_leaves_an_indented_underline_under_the_agents_list_item():
    """Review on be48a54: a cut row `     =====` under the agent's list item is an underline too."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    said = "- " + "a" * 1980 + "\n    " + "=" * 9 + "xxxxx"
    q = machine._quoted(said)
    lines = machine._account_lines(machine._Account(quote=q, total=machine._quote_chars(q)))
    assert any("characters; the first" in r for r in lines), lines
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(lines[1:]))
    assert not re.search(r"<h[1-6]>", html), html


@pytest.mark.parametrize(("said", "total"), [("@ab " * 600, 2400), ("abc\n" * 600, 2399),
                                             ("a_b " * 600, 2400)],
                         ids=["names", "newlines", "escapes"])
def test_the_cut_line_counts_names_newlines_and_escapes_as_the_reader_sees_them(said: str,
                                                                               total: int):
    """Review on be48a54: counting the span backticks, dropping the newlines and counting an
    escape's backslash each survived every test."""
    q = machine._quoted(said)
    lines = machine._account_lines(machine._Account(quote=q, total=machine._quote_chars(q)))
    kept = [r for r in lines if r.startswith(">")]
    seen = (len("\n".join(kept)) - 2 * len(kept) + sum(r == ">" for r in kept)
            - sum(r.count("\\") for r in kept) - sum(r.count("`") for r in kept))
    assert (f"The agent's message, as quoted, was {total} characters; the first {seen} are shown."
            in lines), lines


def test_a_pass_line_cut_never_leaves_a_name_outside_its_span():
    """Review on 35a1cc0: neutralising BEFORE the 200-character cut survived every test."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    row = "> - adjust — " + machine._pass_words(
        AgentRunResult(ok=True, summary="x" * 190 + " @someonelong tail"))
    html = markdown_it.MarkdownIt("commonmark").render(row)
    assert "@someone" not in re.sub(r"<code>.*?</code>", "", html, flags=re.S), html


def test_a_cut_reads_the_platforms_spans_past_the_agents_escaped_backticks():
    """Review on 35a1cc0: counting the agent's escaped backticks as span ends survived every test,
    and the cut row then left the name outside its span."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    said = "a" * 1977 + " ` x @someonelonger tail"
    lines = machine._account_lines(machine._account_of(_result(account=said)))
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(lines))
    assert "@someone" not in re.sub(r"<code>.*?</code>", "", html, flags=re.S), html


def test_the_cut_line_counts_the_characters_the_agent_wrote_not_the_escapes():
    """Review on 35a1cc0: a message of 1,920 characters was published as "was 2880 characters",
    every escape counted as one the agent wrote. Both numbers count what the reader sees."""
    said = "`x` " * 480
    lines = machine._account_lines(machine._account_of(_result(account=said)))
    kept = [r for r in lines if r.startswith("> ")]
    seen = len(kept[0][2:].replace("\\`", "`"))
    assert f"The agent's message, as quoted, was 1920 characters; the first {seen} are shown." in lines, lines


def test_a_cut_never_splits_an_escape_and_still_says_it_cut():
    """A cut between an escape's backslash and the character it escapes would show a stray `\\`
    the agent did not write — and, counted as the reader sees it, leave the count unchanged, so
    the line saying the message was cut went missing."""
    said = "a" * 1997 + "`"
    lines = machine._account_lines(machine._account_of(_result(account=said)))
    (row,) = [r for r in lines if r.startswith("> ")]
    assert not row.endswith("\\"), row
    assert "The agent's message, as quoted, was 1998 characters; the first 1997 are shown." in lines, lines


@pytest.mark.parametrize(("pad", "tail"), [(1990, "=" * 9 + "x" * 5), (1994, "- e@x.com and more")])
def test_a_cut_never_leaves_an_underline_that_makes_a_heading(pad: int, tail: str):
    """Found fuzzing round 2: a row the cut shortens to `=====` or `-` underlines the agent's line
    above it, which then renders as a heading — the whole row was escaped only where it was one."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    said = "a" * pad + "\n" + tail
    lines = machine._account_lines(machine._account_of(_result(account=said)))
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(lines[1:]))
    assert not re.search(r"<h[1-6]>", html), html
    assert any("characters; the first" in r for r in lines), lines


def test_a_cut_never_leaves_a_wrapped_name_outside_its_span():
    """Found by review on 9882b73: the cut row ended `` `@octoca `` with the span protection
    removed, and no test noticed."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    said = "a" * 1990 + " @octocat tail"
    lines = machine._account_lines(machine._account_of(_result(account=said)))
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(lines))
    assert "@octo" not in re.sub(r"<code>.*?</code>", "", html, flags=re.S), html


def test_a_cut_across_lines_never_leaves_a_name_outside_its_span():
    """The same, where the span the cut opens began on an earlier line of the paragraph."""
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    said = "a" * 1980 + " `first line\nsecond @octocat line` tail"
    lines = machine._account_lines(machine._account_of(_result(account=said)))
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(lines))
    assert "@octo" not in re.sub(r"<code>.*?</code>", "", html, flags=re.S), html


# ── criterion 5: bounded, and a cut says so ──────────────────────────────────────────────────────

def test_a_longer_account_is_cut_with_a_line_saying_so(repo: Path, tmp_path: Path, caplog):
    caplog.set_level(logging.INFO, logger="openfactory")
    body = _opened(repo, tmp_path, _Says("y" * 5000))

    block = _quoted_block(body)
    assert len("\n".join(block)) <= BOUND
    section = _section(body)
    cut = [r for r in section if "5000 characters" in r]
    shown = len("\n".join(block)) - 2
    assert cut == [f"The agent's message, as quoted, was 5000 characters; the first {shown} are shown."], cut
    assert any("account" in r.getMessage() and "5000" in r.getMessage() for r in caplog.records)


def test_the_bound_counts_the_quote_as_rendered(repo: Path, tmp_path: Path):
    body = _opened(repo, tmp_path, _Says("\n".join("z" * 1500)))

    block = _quoted_block(body)
    assert len("\n".join(block)) <= BOUND, "the `> ` prefixes were not counted"
    assert any("characters; the first" in r for r in _section(body)), "no cut line"


def test_an_account_that_fits_is_shown_whole_and_says_nothing_about_cutting(
        repo: Path, tmp_path: Path):
    said = "w" * 1500
    body = _opened(repo, tmp_path, _Says(said))

    assert _quoted_block(body) == [f"> {said}"]
    assert not any("characters; the first" in r for r in _section(body))


@pytest.mark.parametrize("shape", ["claude", "codex"])
def test_the_account_is_read_from_the_agents_whole_final_message_not_its_capped_summary(
        repo: Path, tmp_path: Path, shape: str):
    whole = "".join(chr(ord("a") + i % 26) for i in range(1500))
    if shape == "claude":  # summary capped at 1000; the whole message is the result event
        agent = _Says(whole[:1000], json.dumps({"type": "result", "result": whole}))
    else:  # codex, kimi, opencode: the summary IS the whole last message
        agent = _Says(whole, "no result event here")
    body = _opened(repo, tmp_path, agent)

    assert f"> {whole}" in body.splitlines(), "characters past the summary's cap are in no artifact"


def test_the_job_note_keeps_its_200_character_cut_while_the_body_carries_the_rest(
        repo: Path, tmp_path: Path):
    said = "".join(chr(ord("A") + i % 26) for i in range(600))
    events = InMemoryEventSink()
    body = _opened(repo, tmp_path, _Says(said), events=events)

    notes = [e.message for e in events.events if e.message.startswith("agent finished: ")]
    assert notes == [f"agent finished: {said[:200]}"], notes
    assert said[200:] in body


def test_an_agent_that_wrote_nothing_is_said_to_have_written_nothing(repo: Path, tmp_path: Path):
    body = _opened(repo, tmp_path, _Says(""))

    section = _section(body)
    assert not any(r.startswith(">") for r in section), "an empty quote stands for nothing"
    assert any("ended its pass without a final message" in r for r in section), section


# ── helpers for the shape cases ──────────────────────────────────────────────────────────────────

def _result(account: str):
    from openfactory.contracts import RunResult, ValidationResult
    return RunResult(
        ticket_id="#3", state="validating", branch="openfactory/3",
        validations=[ValidationResult(name="test", command="true", exit_code=0, passed=True,
                                      output="")],
        total_cost_usd=0.01, agent_account=account, agent_account_chars=len(account))


def _bare():
    return SimpleNamespace(manifest=Manifest(validate={"test": "true"}), _profile=None)
