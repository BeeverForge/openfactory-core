"""A card written in Jira's editor passes the gate it passes on GitHub (#751).

ONE CARD, AS EACH VENDOR'S EDITOR STORES IT: an Objective section, an Acceptance criteria heading
with two bullets (one carrying a `code` run). On GitHub that is the
markdown a person types. On Azure Boards it is the `<h2>`/`<ul><li>` HTML the browser editor saves
(`multilineFieldsFormat: html`). On Jira it is an ADF document of `heading` and `bulletList` nodes,
in the shape Jira Cloud's browser editor stored KAN-4 on 2026-10-19 (`KAN_4_DESCRIPTION` in
`tests/test_a_jira_description_keeps_its_headings_and_bullets.py`): a heading directly followed by
its list, and an EMPTY paragraph between blocks.

Each card goes through that vendor's own `get_ticket`, the door the sizing gate reads, and the test
asserts what the gate is handed: the objective, the criteria, and `spec_verdict(ticket) == ""`.
Measured on 1be1835 (2026-10-19), Jira's `_text` walked the ADF tree joining every text node with a
newline, so the Jira card reached the parser as `Acceptance criteria\\nthe \\nopenfactory.yaml\\n
file is created…`: no `## `, no `- `, criteria `[]`, and the gate refused a complete card with "no
sections at all".

THE GITHUB AND AZURE PARAMS PASS ON MAIN ON PURPOSE. They are the control: the same card, read by
the two vendors this change does not touch, is what "passes the gate" means. Only the Jira params
(English and pt-BR) are red before the fix.

The one difference between the vendors' criteria is the code run. GitHub stores the backticks as
text, so its criterion is "the `openfactory.yaml` file is created"; Azure's editor stores
`<code>`, and Jira's a `code` mark, and both converters keep the words without the backticks
(`_HtmlToMarkdown` today; `JiraTracker._text` as pinned in the sibling module). Each param therefore
names the criteria its own vendor gives, and the words are the same.

THE CARD ENDS AT ITS LIST, ON EVERY VENDOR. A paragraph after the list is glued into the last
criterion by Azure's converter today (measured on 1be1835: `...refused with its reason\nAgreed with
the product owner.`, read as one criterion), which is the plan's Azure follow-up and not this
change. The control has to be a card both untouched vendors read right; the paragraph-after-a-list
property is held for Jira by `test_a_paragraph_after_a_list_is_not_read_into_its_last_criterion`.
"""

from __future__ import annotations

import pytest

from openfactory.adapters.tracker.parse import criteria
from openfactory.orchestrator.machine import spec_verdict
from tests.test_the_tracker_has_a_read_side import (
    _ALICE,
    JIRA_PAGE_2,
    _ado_tracker,
    _Gh,
    _Jira,
)

# ── the card, in each vendor's stored shape ─────────────────────────────────────────────────────

OBJECTIVE = "Create a project from the command line."
CRITERIA = ["the openfactory.yaml file is created",
            "a name already taken is refused with its reason"]
#: GitHub's markdown keeps the backticks a person typed: they are the text the issue stores.
CRITERIA_AS_GITHUB_STORES_THEM = ["the `openfactory.yaml` file is created",
                                  "a name already taken is refused with its reason"]

GITHUB_BODY = ("## Objective\n"
               f"{OBJECTIVE}\n"
               "\n"
               "## Acceptance criteria\n"
               "- the `openfactory.yaml` file is created\n"
               "- a name already taken is refused with its reason\n")

#: What Azure Boards' browser editor saves when the toolbar's Heading 2 and bullet list are used.
AZURE_HTML = ("<h2>Objective</h2>"
              f"<div>{OBJECTIVE}</div>"
              "<div><br></div>"
              "<h2>Acceptance criteria</h2>"
              "<ul><li>the <code>openfactory.yaml</code> file is created</li>"
              "<li>a name already taken is refused with its reason</li></ul>")


def _t(text: str, *marks: str) -> dict:
    node: dict = {"type": "text", "text": text}
    if marks:
        node["marks"] = [{"type": m} for m in marks]
    return node


def _p(*inline: dict) -> dict:
    return {"type": "paragraph", "content": list(inline)}


#: The editor's empty paragraph, exactly as KAN-4 recorded it: no `content` key at all.
_EMPTY = {"type": "paragraph"}


def _h2(text: str) -> dict:
    return {"type": "heading", "attrs": {"level": 2}, "content": [_t(text)]}


def _bullets(*items: list[dict]) -> dict:
    return {"type": "bulletList",
            "content": [{"type": "listItem", "content": [_p(*inline)]} for inline in items]}


def _jira_card(objective_heading: str, objective: str, criteria_heading: str,
               items: list[list[dict]]) -> dict:
    """An ADF description in the order and shape KAN-4's editor stored its blocks."""
    return {"type": "doc", "version": 1, "content": [
        _h2(objective_heading),
        _p(_t(objective)),
        _EMPTY,
        _h2(criteria_heading),
        _bullets(*items),
    ]}


JIRA_ADF = _jira_card(
    "Objective", OBJECTIVE, "Acceptance criteria",
    [[_t("the "), _t("openfactory.yaml", "code"), _t(" file is created")],
     [_t("a name already taken is refused with its reason")]])

OBJETIVO = "Criar um projeto pela linha de comando."
CRITERIOS = ["o arquivo openfactory.yaml é criado",
             "um nome já usado é recusado com o motivo"]

#: The same card written in Portuguese on a site whose people write in Portuguese: the headings a
#: person types there are `Objetivo` and `Critérios de aceite`.
JIRA_ADF_PT_BR = _jira_card(
    "Objetivo", OBJETIVO, "Critérios de aceite",
    [[_t("o arquivo "), _t("openfactory.yaml", "code"), _t(" é criado")],
     [_t("um nome já usado é recusado com o motivo")]])


# ── each vendor's own door ──────────────────────────────────────────────────────────────────────

def _jira_fields(description: dict) -> dict:
    return {"summary": "criar um projeto", "labels": [], "assignee": None,
            "status": {"name": "To Do", "statusCategory": {"key": "new"}},
            "description": description}


def _github(body: str):
    issue = {"number": 7, "title": "create a project", "body": body, "labels": [],
             "author": {"login": "alicecsp"}, "state": "OPEN"}
    return _Gh({"issue": issue}).get_ticket("#7")


def _azure(html: str):
    item = {"id": 12, "fields": {"System.Id": 12, "System.WorkItemType": "Issue",
                                 "System.State": "To Do", "System.Title": "create a project",
                                 "System.CreatedBy": _ALICE, "System.Description": html},
            "multilineFieldsFormat": {"System.Description": "html"}}
    return _ado_tracker({("GET", "wit/workitems/12"): item}).get_ticket("12")


def _jira(description: dict):
    issue = {"id": "10071", "key": "DAR-7", "fields": _jira_fields(description)}
    return _Jira({("GET", "issue/DAR-7"): issue}).get_ticket("DAR-7")


_CARDS = {
    "github": (lambda: _github(GITHUB_BODY), OBJECTIVE, CRITERIA_AS_GITHUB_STORES_THEM),
    "azure_devops": (lambda: _azure(AZURE_HTML), OBJECTIVE, CRITERIA),
    "jira": (lambda: _jira(JIRA_ADF), OBJECTIVE, CRITERIA),
    "jira_pt_br": (lambda: _jira(JIRA_ADF_PT_BR), OBJETIVO, CRITERIOS),
}


@pytest.mark.parametrize("vendor", list(_CARDS))
def test_the_same_card_gives_the_gate_the_same_criteria_on_every_vendor(vendor):
    """C3: a card with a level-2 heading and a bullet list, through each vendor's `get_ticket`,
    gives the gate its objective and its two criteria, and the gate takes it.

    Before (1be1835, 2026-10-19), on both Jira params: `acceptance_criteria == []` and
    `spec_verdict` refused the card for having "no sections at all". GitHub and Azure passed: they
    are the control."""
    read, objective, expected = _CARDS[vendor]

    ticket = read()

    assert [c.text for c in ticket.acceptance_criteria] == expected
    assert ticket.objective == objective
    assert spec_verdict(ticket) == ""


def test_a_jira_card_in_the_board_read_carries_the_same_criteria():
    """C3b: the board read (`list_tickets` → `_summary`), which the queue, triage and refine read
    with `parse.criteria`, sees the criteria `get_ticket` sees. A card the gate takes must not be
    called "no criteria" by the queue, the disagreement #150 removed.

    Before (1be1835, 2026-10-19): `criteria(summary.body) == []`."""
    page = dict(JIRA_PAGE_2)
    (row,) = page["issues"]
    page["issues"] = [row | {"fields": row["fields"] | {"description": JIRA_ADF}}]
    tracker = _Jira({("POST", "search/jql"): [page]})

    (summary,) = tracker.list_tickets()

    assert criteria(summary.body) == CRITERIA
