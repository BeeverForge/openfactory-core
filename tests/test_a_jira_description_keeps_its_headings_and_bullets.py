"""A Jira description keeps its headings and bullets, so the parser reads the sections and the
criteria a person wrote in Jira's own editor (#751).

The parser reads markdown shapes: a section is a line starting with `## `, a criterion is a `- `
bullet. Jira's editor turns the `## ` and `- ` a person types into `heading` and `bulletList` nodes
of Atlassian Document Format, and `JiraTracker._text` walked that tree joining every text node with
a newline, keeping the words and dropping the shapes. Measured on 1be1835 (2026-10-19): a level-2
heading plus a one-item bullet whose text carries a `code` mark read as

    'Acceptance criteria\\nthe \\nx\\n is created'      →   criteria() == []

so the sizing gate refused a complete ticket as having "no sections at all".

Every assertion is on one of two values: the exact string `JiraTracker._text` returns for a given
document, and what `parse` reads from that string (`criteria`, `section_names`). The rendering
is pinned only where the parser reads it.

The fixtures are the shapes Jira's browser editor stores. `KAN_4_DESCRIPTION` below is a recorded
document; the shapes it does not carry (a `code` mark, an `expand`, a heading with no level) are
built from the ADF schema with the helpers under it.
"""

from __future__ import annotations

import pytest

from openfactory.adapters.tracker.jira import JiraTracker
from openfactory.adapters.tracker.parse import criteria, section_names

# ── recorded shape: Jira Cloud ──────────────────────────────────────────────────────────────────

#: KAN-4's `description`, RECORDED FROM A LIVE CALL on 2026-10-19:
#: `GET /rest/api/3/issue/KAN-4?fields=description` on a Jira Cloud site, the issue written by a
#: person in the Jira Cloud browser editor, team-managed project KAN. Redacted: every `localId`
#: (on nearly every node) is removed; the document carried no account id, no other id and no site
#: URL. No key and no text here is invented. What it shows that the schema alone does not: the
#: editor stores an EMPTY paragraph between blocks, the `bold` of a heading is a separate `text`
#: node, a nested list sits inside the `listItem` after its paragraph, and a table's first row is
#: `tableHeader` cells.
KAN_4_DESCRIPTION = {"type": "doc", "version": 1, "content": [
    {"type": "heading", "attrs": {"level": 2}, "content": [
        {"type": "text", "text": "Acceptance "},
        {"type": "text", "text": "criteria", "marks": [{"type": "strong"}]}]},
    {"type": "bulletList", "content": [
        {"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "the card 4 is created"}]}]},
        {"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "test"}]},
            {"type": "bulletList", "content": [
                {"type": "listItem", "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "sub list"}]}]}]}]}]},
    {"type": "paragraph"},
    {"type": "orderedList", "attrs": {"order": 1}, "content": [
        {"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "test 1"}]}]},
        {"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "test 2"}]}]},
        {"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "test 3"}]}]}]},
    {"type": "paragraph"},
    {"type": "paragraph", "content": [{"type": "text", "text": (
        "Test paragraph → The reviewer ran the interrupted-add test file on git 2.34.1, 2.43.0, "
        "2.47.3 (the worker image's git) and 2.55.0 (CI's), and it passed on all four. The 746 "
        "mutation checks caught all 29 on both 2.43.0 and 2.55.0.")}]},
    {"type": "paragraph"},
    {"type": "table", "attrs": {"isNumberColumnEnabled": False, "layout": "align-start"},
     "content": [
        {"type": "tableRow", "content": [
            {"type": "tableHeader", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "col1", "marks": [{"type": "strong"}]}]}]},
            {"type": "tableHeader", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "col2", "marks": [{"type": "strong"}]}]}]},
            {"type": "tableHeader", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "col3", "marks": [{"type": "strong"}]}]}]}]},
        {"type": "tableRow", "content": [
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "aaa"}]}]},
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "bbb"}]}]},
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "ccc"}]}]}]},
        {"type": "tableRow", "content": [
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "aaa"}]}]},
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "bbb"}]}]},
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "ccc"}]}]}]}]},
    {"type": "paragraph"},
    {"type": "paragraph", "content": [
        {"type": "text", "text": "Line with hard break"},
        {"type": "hardBreak"},
        {"type": "text", "text": "after hard break"}]},
]}

#: The recorded nodes the tests below reuse, by what they are.
_KAN_4_HEADING = KAN_4_DESCRIPTION["content"][0]
_KAN_4_NESTED_BULLETS = KAN_4_DESCRIPTION["content"][1]
_KAN_4_NUMBERED = KAN_4_DESCRIPTION["content"][3]
_KAN_4_TABLE = KAN_4_DESCRIPTION["content"][7]


# ── the ADF schema's shapes, for what the recorded document does not carry ──────────────────────

def _doc(*blocks: dict) -> dict:
    return {"type": "doc", "version": 1, "content": list(blocks)}


def _t(text: str, *marks: str) -> dict:
    node: dict = {"type": "text", "text": text}
    if marks:
        node["marks"] = [{"type": m} for m in marks]
    return node


_BR = {"type": "hardBreak"}


def _p(*inline: dict | str) -> dict:
    return {"type": "paragraph",
            "content": [_t(i) if isinstance(i, str) else i for i in inline]}


def _h(level: int | None, *inline: dict | str) -> dict:
    node = _p(*inline) | {"type": "heading"}
    if level is not None:
        node["attrs"] = {"level": level}
    return node


def _li(*blocks: dict | str) -> dict:
    return {"type": "listItem", "content": [_p(b) if isinstance(b, str) else b for b in blocks]}


def _ul(*items: dict | str) -> dict:
    return {"type": "bulletList", "content": [_li(i) if isinstance(i, str) else i for i in items]}


def _ol(*items: dict | str) -> dict:
    return _ul(*items) | {"type": "orderedList", "attrs": {"order": 1}}


_AC = _h(2, "Acceptance criteria")


def _read(*blocks: dict) -> str:
    return JiraTracker._text(_doc(*blocks))  # noqa: SLF001 — the reader every Jira body goes through


# ── C1: a heading is `#` × its level plus all of its inline text ────────────────────────────────

@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_a_heading_reads_as_its_level_in_hashes_and_its_text(level):
    """C1: "render a `heading` node as `#`×`attrs.level` plus its text". On 1be1835 every level read
    as the bare `Title`, so a card's `## Objective` and `## Acceptance criteria` were no sections at
    all. Only `## ` opens a section in the parser (on every vendor), so the parser-level assertion
    is made on level 2."""
    body = _read(_h(level, "Title"))

    assert body == "#" * level + " Title"
    if level == 2:
        assert section_names(body) == ["Title"]


@pytest.mark.parametrize("heading, expected", [
    pytest.param(_KAN_4_HEADING, "## Acceptance criteria", id="kan-4-bold"),
    pytest.param(_h(2, "Acceptance ", _t("criteria", "strong"), " for ", _t("make", "code")),
                 "## Acceptance criteria for make", id="schema-bold-and-code"),
])
def test_a_heading_written_with_bold_and_code_is_one_line(heading, expected):
    """C1, with all of its inline content on one line. The editor stores a bold or code run as a
    `text` node of its own (KAN-4's heading is two), and on 1be1835 each text node became a line:
    `Acceptance \\ncriteria`. Drawing `## ` before the first node alone would still leave
    `criteria` on a line of its own, outside the heading the parser looks for."""
    body = JiraTracker._text(_doc(heading))  # noqa: SLF001

    assert body == expected
    # The whole heading is the section the parser reads, not its first run. `section_names`, not
    # `criteria_heading`: "Acceptance criteria for make" is not an alias of the criteria section.
    assert section_names(body) == [expected.removeprefix("## ")]


@pytest.mark.parametrize("attrs", [
    pytest.param(None, id="no-attrs"),
    pytest.param({"level": 9}, id="level-9"),
    pytest.param({"level": 0}, id="level-0"),
])
def test_a_heading_with_no_level_is_read_as_a_plain_line(attrs):
    """C1's bound: a heading whose level is missing or outside 1..6 is drawn as a plain line, never
    as an invented heading. GREEN ON 1be1835 ON PURPOSE: the old walk drew every heading as a plain
    line, so this is a guard on the new renderer (mutation M11 turns it red), not a reproduction."""
    heading = {"type": "heading", "content": [_t("Title")]}
    if attrs is not None:
        heading["attrs"] = attrs

    # Not first in the document: the final strip() would hide a heading drawn as `"#" * 0 + " "`.
    body = _read(_p("Before."), heading)

    assert body == "Before.\nTitle"
    assert section_names(body) == []


# ── C2: each list item, bulleted or numbered, nested or not, is one `- ` line ──────────────────

def test_a_bullet_list_reads_as_one_dash_line_per_item():
    """C2: "a `listItem` as `- ` plus its text". On 1be1835 the items came back as bare lines, so
    the parser found no bullet under the criteria heading and read no criterion."""
    assert _read(_ul("a", "b")) == "- a\n- b"
    assert criteria(_read(_AC, _ul("a", "b"))) == ["a", "b"]


@pytest.mark.parametrize("numbered, items", [
    pytest.param(_ol("a", "b"), ["a", "b"], id="schema"),
    pytest.param(_KAN_4_NUMBERED, ["test 1", "test 2", "test 3"], id="kan-4"),
])
def test_a_numbered_list_reads_as_bullets_the_gate_counts(numbered, items):
    """C2, for `orderedList`: its items are `- ` lines, as Azure's converter draws `<ol><li>`. The
    parser does not read `1.` as a criterion, so drawing the numbers would leave a numbered list of
    criteria unread. On 1be1835 they were bare lines and `criteria` was `[]`."""
    assert _read(numbered) == "\n".join(f"- {i}" for i in items)
    assert criteria(_read(_AC, numbered)) == items


@pytest.mark.parametrize("bullets, items", [
    pytest.param(_ul(_li("parent", _ul("child"))), ["parent", "child"], id="schema"),
    pytest.param(_KAN_4_NESTED_BULLETS, ["the card 4 is created", "test", "sub list"], id="kan-4"),
])
def test_a_nested_list_item_is_a_criterion_of_its_own(bullets, items):
    """C2, nested items: each nested item is a `- ` line of its own, flat, as Azure's converter
    draws it (human answer Q2, 2026-10-19). "Stop descending" read literally would glue the child's
    text onto its parent's line. On 1be1835 every item was a bare line and `criteria` was `[]`."""
    assert _read(bullets) == "\n".join(f"- {i}" for i in items)
    assert criteria(_read(_AC, bullets)) == items


def test_an_inline_mark_inside_a_bullet_does_not_split_the_criterion():
    """C2, inline marks on one line: the issue's own measurement. On 1be1835 this item read as
    `the \\nx\\n is created`, three lines and no criterion."""
    item = _ul(_li(_p("the ", _t("x", "code"), " is created")))

    assert _read(item) == "- the x is created"
    assert criteria(_read(_AC, item)) == ["the x is created"]


def test_a_list_item_of_two_paragraphs_is_one_criterion():
    """C2: the item's first paragraph follows `- `, the next one sits on the line directly below,
    and the parser's lazy continuation (#163) joins them into one criterion, as it does for the same
    item written on GitHub. On 1be1835 both were bare lines and `criteria` was `[]`."""
    item = _ul(_li("first", "second"))

    assert _read(item) == "- first\nsecond"
    assert criteria(_read(_AC, item)) == ["first second"]


#: A `mediaSingle` (an image) as the ADF schema allows it in a `listItem`. It carries no text.
_IMAGE = {"type": "mediaSingle", "attrs": {"layout": "center"}, "content": [
    {"type": "media", "attrs": {"type": "file", "id": "image", "collection": "attachments"}}]}


@pytest.mark.parametrize("opening, expected", [
    pytest.param({"type": "codeBlock", "attrs": {"language": "bash"},
                  "content": [_t("make test passes")]}, ["make test passes"], id="code-block"),
    pytest.param(_IMAGE, ["the logo is shown"], id="image-then-paragraph"),
    pytest.param(_ul("child"), ["child"], id="nested-list"),
])
def test_a_list_item_that_opens_with_another_block_is_still_a_criterion_of_its_own(
        opening, expected):
    """C2, whatever block the item opens with. `@atlaskit/adf-schema` 57.7.18 (2026-10-19) lets a
    `listItem` open with a `codeBlock`, a `mediaSingle`, a `taskList` or a nested list, not only a
    paragraph. The renderer drew `- ` only before a FIRST-CHILD PARAGRAPH, so an item opening with a
    code block read as a bare line under the item above, and lazy continuation (#163) glued the two:
    `["a make test passes", "c"]`; an item opening with an image lost its `- ` the same way. The
    nested-list param is green on that renderer ON PURPOSE: its items already draw their own `- `,
    and the guard is that the fix does not draw a second one (`- - child`)."""
    rest = [_p("the logo is shown")] if opening is _IMAGE else []
    bullets = _ul("a", {"type": "listItem", "content": [opening, *rest]}, "c")

    assert _read(bullets) == "\n".join(f"- {i}" for i in ["a", *expected, "c"])
    assert criteria(_read(_AC, bullets)) == ["a", *expected, "c"]


# ── C4: a list ends on a blank line ────────────────────────────────────────────────────────────

def test_a_paragraph_after_a_list_is_not_read_into_its_last_criterion():
    """C4: once items read as `- ` lines, a paragraph the editor stores right after the list would
    sit on the very next line, and the parser's lazy continuation (#163) would read it into the last
    criterion: `["a", "b Note that this was agreed"]`. A list therefore ends on a blank line. On
    1be1835 `criteria` was `[]`, for the issue's reason."""
    body = _read(_AC, _ul("a", "b"), _p("Note that this was agreed"))

    assert body == "## Acceptance criteria\n- a\n- b\n\nNote that this was agreed"
    assert criteria(body) == ["a", "b"]


def test_the_editors_empty_paragraph_between_two_lists_does_not_end_the_criteria():
    """C2 with C4, on the whole recorded document: Jira's editor stores an EMPTY paragraph between
    KAN-4's bullet list and its numbered list (measured live on 2026-10-19, and still so on the
    re-fetch of task 10), and C4 ends every list on a blank line. Both lists sit under the one
    criteria heading, so the blank line between them must not end the section: the six items are
    the ticket's six criteria. On 1be1835 the document read as bare lines, `section_names` was `[]`,
    `criteria` was `[]`, and the gate said "no sections at all"."""
    body = JiraTracker._text(KAN_4_DESCRIPTION)  # noqa: SLF001

    assert section_names(body) == ["Acceptance criteria"]
    assert criteria(body) == [
        "the card 4 is created", "test", "sub list", "test 1", "test 2", "test 3"]


# ── C5: ADR-0022's property — no text is lost to the nodes that hold it ────────────────────────

def test_a_table_cell_and_an_expand_still_give_up_their_text():
    """C5: a description is never read as empty because of the nodes it uses (ADR-0022 §4). KAN-4's
    table (a `tableHeader` row, then `tableCell` rows) and an `expand` are walked for their text.
    GREEN ON 1be1835 ON PURPOSE: the old walk read every text node, so this is a regression guard on
    the new renderer's generic recursion (mutation M10), not a reproduction."""
    expand = {"type": "expand", "attrs": {"title": "Details"},
              "content": [_p("hidden detail")]}

    body = JiraTracker._text(_doc(_KAN_4_TABLE, expand))  # noqa: SLF001

    assert [line for line in body.splitlines() if line] == [
        "col1", "col2", "col3", "aaa", "bbb", "ccc", "aaa", "bbb", "ccc", "hidden detail"]


def test_a_hard_break_is_a_line_break_not_a_glued_word():
    """C5: a `hardBreak` (Shift+Enter in the editor; KAN-4 carries one) is a line break. Joining a
    node's inline content with nothing, which C1 and C2 need, would otherwise glue the two halves
    into `line oneline two`. Inside a bullet the second half sits directly under the item, so the
    criterion keeps both halves. On 1be1835 the item read as `line one\\nline two` with no `- `, and
    `criteria` was `[]`."""
    item = _ul(_li(_p("line one", _BR, "line two")))

    assert _read(item) == "- line one\nline two"
    assert criteria(_read(_AC, item)) == ["line one line two"]


def test_an_action_item_and_a_decision_still_give_up_their_text():
    """C5: `taskItem` and `decisionItem` hold inline content directly (ADF schema 57.7.18), so
    their text nodes reach the block walk bare. A description of action items alone must not
    read empty (ADR-0022 §4). GREEN ON 1be1835 ON PURPOSE: a regression guard (M15)."""
    task = {"type": "taskList", "attrs": {"localId": "t"}, "content": [
        {"type": "taskItem", "attrs": {"localId": "i", "state": "TODO"},
         "content": [_t("ship the release")]}]}
    decision = {"type": "decisionList", "attrs": {"localId": "d"}, "content": [
        {"type": "decisionItem", "attrs": {"localId": "e", "state": "DECIDED"},
         "content": [_t("we use Postgres")]}]}

    assert _read(task, decision) == "ship the release\nwe use Postgres"
