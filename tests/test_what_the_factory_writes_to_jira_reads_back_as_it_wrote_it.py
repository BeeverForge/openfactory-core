"""What the factory writes to Jira reads back as it wrote it (#751, the second instance).

THE FACTORY'S OWN WRITES LOST THEIR BLANK LINES. `JiraTracker._adf` sends a body as one paragraph
per line, an empty paragraph for a blank line. `JiraTracker._text` walked the tree for text nodes
and joined them with a newline, so an empty paragraph, which has none, vanished. Measured on
1be1835 (2026-10-19): `_text(_adf(_child_body(...)))` returned `**Focus:** t\\n## Objective…`, and
a split child's `## Out of scope` bullet ran straight into the line under it, so on Jira its
`out_of_scope` was `['Everything covered by the sibling sub-tickets of CONT-1 (this is part 1/2;
run in order). _Auto-split from CONT-1 by the pre-flight sizer (ADR-0013)._']` (#163's lazy
continuation joins the next line into the item when no blank line ends it). On GitHub, which keeps
the markdown as written, it is the first sentence alone.

It is the same defect as the editor-written card: the walk discarded the shape of the blocks. Here
the blocks are the ones the factory itself wrote.

THE BODIES COME FROM THE WRITERS (engineering lesson 5): `activities._child_body` builds them, with
nothing carried and with a parent's sections carried (taken from a parent body by
`parse.carried_sections`, as the split does), and `_adf` writes them. The expected `out_of_scope`
is what `parse_ticket_body` reads from the raw markdown, computed here, never typed.
"""

from __future__ import annotations

import pytest

from openfactory.adapters.tracker.jira import JiraTracker
from openfactory.adapters.tracker.parse import carried_sections, parse_ticket_body
from openfactory.runtime.temporal import activities as acts
from tests.test_the_tracker_has_a_read_side import _Jira

#: A child as the pre-flight sizer returns it.
CHILD = {"title": "t", "objective": "Write the config file.",
         "criteria": ["the file is written", "a second run leaves it unchanged"]}

#: A parent a person wrote, with a section the sizer does not rewrite: the split carries it.
PARENT_BODY = ("Asked by the operations team.\n"
               "\n"
               "## Objective\n"
               "Write the config file and keep it stable.\n"
               "\n"
               "## Acceptance criteria\n"
               "- the file is written\n"
               "\n"
               "## Context\n"
               "The file is read at boot.\n"
               "\n"
               "It is never edited by hand.\n")

_BODIES = {
    "a split child, nothing carried": lambda: acts._child_body(CHILD, "CONT-1", 1, 2),
    "a split child carrying its parent's sections": lambda: acts._child_body(
        CHILD, "CONT-1", 1, 2, carried=carried_sections(PARENT_BODY)),
    "a body with a run of blank lines": lambda: "a\n\n\nb",
}


@pytest.mark.parametrize("name", list(_BODIES))
def test_a_body_the_factory_wrote_reads_back_byte_identical(name):
    """C6 (second instance): what `_adf` writes, `_text` reads back as it was, blank lines
    included, so the parser sees the sections and lists the writer drew.

    Before (1be1835, 2026-10-19): every empty paragraph was dropped, so the split child read back
    as `**Focus:** t\\n## Objective…` and `a\\n\\n\\nb` as `a\\nb`."""
    body = _BODIES[name]()
    assert "\n\n" in body  # the property is about blank lines: a body without one holds nothing

    assert JiraTracker._text(JiraTracker._adf(body)) == body.strip()


def test_a_split_childs_out_of_scope_does_not_swallow_the_auto_split_line_on_jira():
    """C6 (second instance), through the door the gate reads: a split child the factory wrote to
    Jira, read back by `get_ticket`, has the out-of-scope item the same markdown gives
    `parse_ticket_body` directly, and not the auto-split line glued onto it.

    Before (1be1835, 2026-10-19): `out_of_scope == ['Everything covered by the sibling sub-tickets
    of CONT-1 (this is part 1/2; run in order). _Auto-split from CONT-1 by the pre-flight sizer
    (ADR-0013)._']`."""
    body = acts._child_body(CHILD, "CONT-1", 1, 2)
    as_written = parse_ticket_body(id="CONT-2", title="t", body=body, repo="CONT").out_of_scope
    assert len(as_written) == 1 and "Auto-split" not in as_written[0]  # the reference is sound
    issue = {"id": "10072", "key": "CONT-2",
             "fields": {"summary": "t", "labels": [], "assignee": None,
                        "status": {"name": "To Do", "statusCategory": {"key": "new"}},
                        "description": JiraTracker._adf(body)}}

    ticket = _Jira({("GET", "issue/CONT-2"): issue}, project_key="CONT").get_ticket("CONT-2")

    assert ticket.out_of_scope == as_written
