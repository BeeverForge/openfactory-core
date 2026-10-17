"""A card the sizer splits keeps what its author wrote (#624).

THE CHILDREN WERE BUILT FROM THE SIZER'S OUTPUT ALONE. `_child_body` wrote a Focus line, the
sizer's `## Objective` and `## Acceptance criteria`, an `## Out of scope` line naming the siblings
and the "Auto-split from" line — and `_do_split` read the parent only for its title. Every other
section a person wrote (`## Scope`, `## Context`, `## Housekeeping`, the factory's own template's
`## What was asked`) was gone, and the parent is closed as not planned, so the child is all the
job, the reviewer and the person read. Measured on a field run (card 79 → 98): the parent's Scope
said where each ingredient grows, and no child said it.

WHAT IS DRIVEN HERE IS THE REAL `_do_split` OVER THE REAL `LocalTracker` on a board file of its
own, with the children read back through `get_ticket` — the real `parse_ticket_body` — and handed
to the real brief and the two real reviewer prompts. Every sentence is a distinct literal, so a
count of it means what it says.
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace

import pytest

from openfactory.adapters.agent.base import AgentContext, ticket_brief
from openfactory.adapters.reviewer.base import ReviewInput
from openfactory.adapters.reviewer.claude_code import ClaudeCodeReviewer
from openfactory.adapters.reviewer.harness import build_review_prompt
from openfactory.adapters.tracker.local import LocalTracker
from openfactory.adapters.tracker.parse import section_names
from openfactory.contracts import Ticket
from openfactory.runtime.temporal import activities as acts
from openfactory.runtime.temporal.io import SplitInput

PREAMBLE = "Filed after the spring walk through the kitchen garden."
PARENT_OBJECTIVE = "Plant a herb garden that feeds the kitchen all year."
SCOPE_PROSE = "Lavender grows only on the north terrace, where the wall keeps the frost off."
SCOPE_BULLET = "the basil bed sits beside the kitchen door"
HOUSEKEEPING = "Close the compost bins after every rain."
PARENT_OUT = "the orchard beyond the stone wall"
PARENT_CRITERIA = ("the parent's mint promise is kept", "the parent's thyme promise is kept")

PARENT_BODY = (
    f"{PREAMBLE}\n\n"
    f"## Objective\n{PARENT_OBJECTIVE}\n\n"
    f"## Scope\n{SCOPE_PROSE}\n- {SCOPE_BULLET}\n\n"
    f"## Housekeeping\n{HOUSEKEEPING}\n\n"
    f"## Out of scope\n- {PARENT_OUT}\n\n"
    "## Acceptance criteria\n" + "\n".join(f"- {c}" for c in PARENT_CRITERIA)
)

CHILDREN = [
    {"title": "the north beds", "objective": "the sizer's objective for the north beds",
     "criteria": ["the sizer's first north criterion", "the sizer's second north criterion"]},
    {"title": "the kitchen door beds", "objective": "the sizer's objective for the door beds",
     "criteria": ["the sizer's door criterion"]},
]


@pytest.fixture
def board(tmp_path, monkeypatch):
    """One project on the local row, with the split's three outside reads pointed at it — the
    pattern of `test_a_card_that_was_split_is_not_delivered_until_its_children_are.py`."""
    def _open(tracker_class=LocalTracker):
        tracker = tracker_class("acme", db_path=tmp_path / "board.db")
        monkeypatch.setattr(acts, "_tracker_for", lambda project: tracker)
        monkeypatch.setattr(acts.ProjectRegistry, "get",
                            lambda self, name: SimpleNamespace(name="acme", language="en"))
        import openfactory.loader
        monkeypatch.setattr(openfactory.loader, "load_manifest",
                            lambda project: SimpleNamespace(split_to_todo=False))
        return tracker
    return _open


def _split(tracker, body: str = PARENT_BODY, children=CHILDREN) -> tuple[str, list[Ticket]]:
    """Split a parent carrying `body`; return its ref and its children as `get_ticket` reads
    them back."""
    parent = tracker.create_ticket(title="Plan 79 — The herb garden", body=body)
    acts._do_split(SplitInput(project="acme", issue=parent.lstrip("#"),
                              reasons="two gardens in one card", children=children))
    kids = [r for r in tracker.children_of(parent)]
    assert len(kids) == len(children), kids
    return parent, [tracker.get_ticket(r) for r in kids]


def _heading(parent: str) -> str:
    return f"From the parent card ({parent})"


def _under(body: str, heading: str) -> str:
    """The part of `body` below the line `## <heading>`."""
    return body.split(f"\n## {heading}\n", 1)[1]


def _fences(text: str) -> list[tuple[int, int]]:
    """Every `(start, end)` span between a brief's own data markers — copied from
    `test_provenance_in_the_brief.py`, read out of the document a harness really receives."""
    spans = []
    for match in re.finditer(r"^<<<data ([0-9a-f]+)>>>$", text, re.M):
        close = text.find(f"<<<end data {match.group(1)}>>>", match.end())
        assert close != -1, "a block opens and never ends"
        spans.append((match.end(), close))
    return spans


def _inside_a_fence(text: str, needle: str) -> bool:
    where = text.index(needle)
    return any(start <= where < end for start, end in _fences(text))


# ── criterion 1: the parent's other sections are carried, under a heading that names it ────────

def test_each_child_carries_the_parents_scope_and_its_other_sections_under_a_heading_that_names_the_parent(board):  # noqa: E501
    tracker = board()
    parent, kids = _split(tracker)

    for kid in kids:
        body = kid.raw
        assert body.splitlines().count(f"## {_heading(parent)}") == 1, body
        carried = _under(body, _heading(parent))
        assert "### Scope" in carried.splitlines()
        assert "### Housekeeping" in carried.splitlines()
        for sentence in (PREAMBLE, SCOPE_PROSE, f"- {SCOPE_BULLET}", HOUSEKEEPING):
            assert sentence in carried, (sentence, body)


def test_no_child_carries_the_parents_objective_or_criteria_beside_the_sizers_rewrite(board):
    """The objective and the criteria are the two sections the sizer rewrote per child; the
    parent's would sit beside them, and a reader could not tell which one this card promises."""
    tracker = board()
    parent, kids = _split(tracker)

    for kid, child in zip(kids, CHILDREN, strict=True):
        body = kid.raw
        assert SCOPE_PROSE in body, "the carried half: the Scope is in the child"
        assert body.count(PARENT_OBJECTIVE) == 0, body
        for criterion in PARENT_CRITERIA:
            assert body.count(criterion) == 0, (criterion, body)
        assert body.count(child["objective"]) == 1, body
        for criterion in child["criteria"]:
            assert body.count(criterion) == 1, (criterion, body)
        # THE CHILD'S OWN SECTIONS ARE STILL ITS OWN: the carried ones sit one level down, so the
        # parser never reads the parent's Scope as this card's, nor its Out of scope as a second
        assert section_names(body) == ["Objective", "Acceptance criteria", "Out of scope",
                                       _heading(parent)], section_names(body)
        assert kid.in_scope == [] and kid.context is None, (kid.in_scope, kid.context)
        assert kid.objective == child["objective"]
        assert [c.text for c in kid.acceptance_criteria] == child["criteria"]


def test_a_parent_written_in_portuguese_is_carried_by_what_its_headings_mean(board):
    """`## Critérios de aceite` is the criteria and `## Escopo` is the scope — matched by meaning,
    as the parser matches them (#46), never by the English spelling."""
    tracker = board()
    body = ("## Objetivo\nUma horta que alimenta a cozinha o ano inteiro.\n\n"
            "## Escopo\nA alfazema cresce só no terraço norte.\n\n"
            "## Critérios de aceite\n- a promessa da hortelã do pai é cumprida")
    parent, kids = _split(tracker, body)

    for kid in kids:
        carried = _under(kid.raw, _heading(parent))
        assert "### Escopo" in carried.splitlines(), kid.raw
        assert "A alfazema cresce só no terraço norte." in carried
        assert "Uma horta que alimenta" not in kid.raw
        assert "a promessa da hortelã" not in kid.raw


def test_a_parent_with_nothing_beside_its_objective_and_criteria_carries_no_empty_heading(board):
    """Passes before the change too — nothing was ever carried. It guards the fix against writing
    the heading over an empty block."""
    tracker = board()
    parent, kids = _split(tracker, "## Objective\nonly this\n\n## Acceptance criteria\n- c")

    for kid in kids:
        assert section_names(kid.raw) == ["Objective", "Acceptance criteria", "Out of scope"]
        assert "From the parent card" not in kid.raw
        assert getattr(kid, "from_parent", None) is None


# ── criterion 4: the carried sections reach the job and the reviewer ────────────────────────────

def test_the_carried_sections_reach_the_jobs_brief_and_the_reviewers_prompt(board):
    tracker = board()
    _parent, kids = _split(tracker)
    kid = kids[0]

    assert SCOPE_PROSE in (kid.from_parent or "") and HOUSEKEEPING in (kid.from_parent or "")
    review = ReviewInput(ticket=kid, diff="")
    assert SCOPE_PROSE in review.ticket.from_parent, "the reviewer's ticket input"

    brief = ticket_brief(AgentContext(ticket=kid))
    harness_prompt = build_review_prompt(review)
    claude_prompt = ClaudeCodeReviewer()._prompt(review)
    for sentence in (SCOPE_PROSE, HOUSEKEEPING):
        assert sentence in brief and _inside_a_fence(brief, sentence), brief
        assert sentence in harness_prompt, harness_prompt
        assert sentence in claude_prompt, claude_prompt


# ── criterion 5: within the tracker's body limit, cut with a line that says so ──────────────────

class _SmallTracker(LocalTracker):
    body_limit = 1200


def _long_scope() -> str:
    """~5,000 characters of Scope that opens a code fence early and closes it late, so a cut in
    the middle leaves it open unless the writer closes it."""
    lines = ["The beds are laid out as follows:", "```"]
    lines += [f"bed {i:03d}: rosemary, sage and oregano in a row of clay pots" for i in range(80)]
    lines += ["```", "That is every bed."]
    return "\n".join(lines)


def _too_long_body() -> str:
    return (f"## Objective\n{PARENT_OBJECTIVE}\n\n## Scope\n{_long_scope()}\n\n"
            f"## Housekeeping\n{HOUSEKEEPING}\n\n## Acceptance criteria\n- c")


def test_a_parent_too_long_to_carry_is_cut_with_a_line_that_says_so_and_links_to_it(board):
    tracker = board(_SmallTracker)
    parent, kids = _split(tracker, _too_long_body())
    url = tracker.ticket_url(parent)
    assert url

    for kid, child in zip(kids, CHILDREN, strict=True):
        body = kid.raw
        assert len(body) <= 1200, len(body)
        lines = body.splitlines()
        cut = next(i for i, line in enumerate(lines) if "are cut here" in line)
        assert url in lines[cut] and parent in lines[cut], lines[cut]
        fences = [ln for ln in lines[:cut] if ln.strip().startswith(("```", "~~~"))]
        assert len(fences) % 2 == 0, "the cut line sits inside a code fence nobody closed"
        assert body.count(child["objective"]) == 1
        for criterion in child["criteria"]:
            assert body.count(criterion) == 1
        assert lines[-1].startswith("_Auto-split from "), lines[-1]


def test_the_limit_is_asked_of_the_tracker_and_every_shipped_row_declares_one(board):
    """Each hosted row declares its vendor's limit; the local row, which stores any length,
    declares none and gets `CARD_BODY_LIMIT` — the smallest a shipped row declares, the most
    cautious bound for a row nobody measured."""
    from openfactory.adapters.tracker.azure_devops import AzureBoardsTracker
    from openfactory.adapters.tracker.github import GitHubIssuesTracker
    from openfactory.adapters.tracker.jira import JiraTracker

    declared = {row: row.body_limit for row in (GitHubIssuesTracker, JiraTracker,
                                                AzureBoardsTracker)}
    assert declared == {GitHubIssuesTracker: 65_536, JiraTracker: 32_767,
                        AzureBoardsTracker: 1_000_000}, declared
    assert acts.CARD_BODY_LIMIT == min(declared.values())
    assert not hasattr(LocalTracker, "body_limit")

    # …and the row that declares none IS cut at that bound, not left unbounded
    tracker = board()
    body = (f"## Objective\n{PARENT_OBJECTIVE}\n\n## Scope\n"
            + "\n".join(f"- bed {i:05d} holds chives, dill and parsley" for i in range(1500))
            + "\n\n## Acceptance criteria\n- c")
    assert len(body) > acts.CARD_BODY_LIMIT
    _parent, kids = _split(tracker, body)
    for kid in kids:
        assert len(kid.raw) <= acts.CARD_BODY_LIMIT, len(kid.raw)
        assert "are cut here" in kid.raw


def test_a_cut_is_logged_with_how_much_was_kept(board, caplog):
    tracker = board(_SmallTracker)
    with caplog.at_level(logging.WARNING):
        _parent, kids = _split(tracker, _too_long_body())

    said = [r.getMessage() for r in caplog.records
            if "OPENFACTORY_SPLIT_CARRIED_CUT" in r.getMessage()]
    assert len(said) == len(kids), said
    for kid in kids:
        line = next(s for s in said if kid.title in s)
        found = re.search(r"kept (\d+) of (\d+) characters", line)
        assert found, line
        kept, total = int(found.group(1)), int(found.group(2))
        assert 0 <= kept < total and total > len(_long_scope()), line


# ── an old payload still reads ──────────────────────────────────────────────────────────────────

def test_a_card_read_before_this_change_still_validates():
    """A Temporal payload serialised before the field existed carries no `from_parent`; it must
    still validate. Passes on main by construction (the field is absent there too)."""
    old = {"id": "#1", "title": "t", "objective": "o", "repo": "acme"}
    assert Ticket.model_validate(old).id == "#1"
    assert getattr(Ticket.model_validate(old), "from_parent", None) is None


# ── review of 83256a1: the edges of the bound ───────────────────────────────────────────────────

def test_a_child_whose_own_part_nearly_fills_the_limit_is_not_pushed_over_it():
    """The carried header and the cut line cost ~360 characters. When the sizer's own part fits the
    limit but leaves less than that, the child was written over the limit — 579 characters at a
    limit of 222, a child main would have created (review of 83256a1). With no room to carry
    anything, the child is what it was before #624."""
    child = {"title": "f", "objective": "o", "criteria": ["c"]}
    bare = acts._child_body(child, "#1", 1, 2)
    carried = ("", [("Scope", "word " * 200)])
    for limit in (len(bare), len(bare) + 100, len(bare) + 300):
        body = acts._child_body(child, "#1", 1, 2, carried=carried, limit=limit, parent_url="u")
        assert len(body) <= limit, (limit, len(body))


@pytest.mark.parametrize(("text", "closer"), [
    ("```\n~~~\n" + "x\n" * 50, "```"),            # a tilde line inside a backtick fence
    ("````\n```\n" + "x\n" * 50, "````"),          # three backticks inside a four-backtick fence
    ("~~~~~\n```\n~~~\n" + "x\n" * 50, "~~~~~"),   # shorter closers inside a long tilde fence
], ids=["tilde-inside-backticks", "three-inside-four", "short-closers-inside-long-tildes"])
def test_a_fence_the_cut_leaves_open_is_closed_by_its_own_marker(text, closer):
    """Counting fence lines by parity left the cut line inside code when the fence held a line of
    the other kind, and closed a four-backtick fence with three (review of 83256a1). A closer is the
    opener's character, at least as many times."""
    kept = acts._markdown_within(text, 20)
    assert len(kept) <= 20, kept
    assert kept.splitlines()[-1] == closer, kept


def test_a_closer_that_would_cross_the_budget_gives_a_line_back():
    kept = acts._markdown_within("```\n" + "a" * 10 + "\n" + "b" * 10, 16)
    assert len(kept) <= 16 and kept.endswith("```"), kept


def test_one_line_longer_than_the_budget_is_cut_at_a_word():
    assert acts._markdown_within("word " * 100, 23) == "word word word word"


def test_the_parents_front_matter_is_not_carried_as_prose(board):
    tracker = board()
    _parent, kids = _split(tracker, "---\nbase_branch: dev\n---\nprose above the headings\n\n"
                                    "## Objective\no\n\n## Acceptance criteria\n- c")
    for kid in kids:
        assert "base_branch" not in kid.raw, kid.raw
        assert "prose above the headings" in (kid.from_parent or "")


def test_an_empty_parent_section_is_not_carried_as_an_empty_heading(board):
    tracker = board()
    _parent, kids = _split(tracker, "## Objective\no\n\n## Scope\n\n## Housekeeping\nh\n\n"
                                    "## Acceptance criteria\n- c")
    for kid in kids:
        assert "### Housekeeping" in kid.raw.splitlines()
        assert "### Scope" not in kid.raw.splitlines(), kid.raw


# ── re-review of a3558546: what the no-room branch and the fence rules promise ──────────────────

def test_a_child_with_no_room_to_carry_is_the_child_main_wrote_and_says_so(caplog):
    """Not only within the limit: EXACTLY main's body — the "Auto-split from" line included — and
    the cut logged, as the branch's comment says."""
    child = {"title": "f", "objective": "o", "criteria": ["c"]}
    bare = acts._child_body(child, "#1", 1, 2)
    with caplog.at_level(logging.WARNING):
        body = acts._child_body(child, "#1", 1, 2, carried=("", [("Scope", "word " * 200)]),
                                limit=len(bare) + 100, parent_url="u", title="T")
    assert body == bare, body
    assert any("OPENFACTORY_SPLIT_CARRIED_CUT T — kept 0 of" in r.getMessage()
               for r in caplog.records)


@pytest.mark.parametrize(("text", "closer"), [
    ("```\n``` not a closer\n" + "x\n" * 50, "```"),   # a fence line with text after it is content
    ("  ```\n" + "x\n" * 50, "```"),                    # up to three spaces of indent still opens
], ids=["closer-with-trailing-text", "indented-opener"])
def test_what_commonmark_reads_as_a_fence_is_what_the_cut_closes(text, closer):
    kept = acts._markdown_within(text, 20)
    assert len(kept) <= 20 and kept.splitlines()[-1] == closer, kept


def test_four_spaces_of_indent_is_not_a_fence_and_is_not_closed():
    """Four spaces make an indented code block, not a fence: closing it would add a stray fence
    that opens one below the cut."""
    kept = acts._markdown_within("    ```\n" + "x\n" * 50, 20)
    assert not kept.endswith("```"), kept
