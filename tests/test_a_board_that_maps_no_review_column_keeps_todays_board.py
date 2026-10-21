"""A board that maps no review column keeps today's board (#753, AC3 — the invariant).

`needs_review` is a key no deployment made before 0.7 maps: a `board.db` written by 0.6's six-row
setup, a Projects board without the option, a Jira `status_map` or an Azure `state_map`/`columns`
that never named it. On such a board a pull request waiting for a person's review must still land
where it always did — Needs Action — and never stay where it was, or fall to a label: "an existing
deployment keeps today's behaviour". The fallback is `FALLS_BACK_TO` in the contract
(`adapters/tracker/base.py`), and every row must take it.

GREEN ON `main` BY CONSTRUCTION for the six rows that read the resolver there: before the key
existed, every row answered Needs Action. That is the point of an invariant, so it is proven by
mutation instead — cutting each row's fallback must turn its case red
(`tools/mutations/753_a_pull_request_waiting_for_a_reviewer_has_its_own_column.py`). The Jira
board is the exception and is red on `main`: it read `STATE_KEYS.get(state)` and dropped
`needs_person`, so it sent this card to In review (the second instance of the defect, #753).

The rows, and how each reads where the card landed, are in
`tests/a_pull_request_awaiting_review_on_each_row.py`; the local boards there are main's six rows,
written literally.
"""

from __future__ import annotations

import pytest

from tests.a_pull_request_awaiting_review_on_each_row import ROWS


@pytest.mark.parametrize("row", list(ROWS))
def test_the_pull_request_still_lands_in_needs_action(row, tmp_path, monkeypatch):
    where = ROWS[row](False, tmp_path, monkeypatch)

    assert where.landed == where.needs_action, (
        f"{row}: the deployment maps no review column, and a pull request waiting on a person's "
        f"review landed in {where.landed or 'nothing — it stayed where it was'!r} instead of "
        f"Needs Action ({where.needs_action!r})")


def test_a_github_board_with_neither_column_still_sends_the_pull_request_to_backlog(monkeypatch):
    """A board made before its owner added Needs Action by hand has neither option. On `main` the
    person-gated pull request fell back to Backlog (`set_column`'s fallback for Needs Action); the
    last of `column_keys` must still be the name `set_column` is handed, or it moves nowhere.

    GREEN ON `main` (1be1835a) AND ON THE BRANCH, as an invariant is: it holds the last resort
    against a cut. With `names[-1]` cut to `names[0]` in `GitHubProjectBoard.set_status`, the name
    handed on is "Needs Review", which `set_column` does not map, and the card moves nowhere
    (`AssertionError: (False, [])`). That cut survived the 36 GitHub test modules (#753's review,
    point 2)."""
    import json
    import subprocess

    from openfactory.adapters.tracker.github_project import GitHubProjectBoard
    from openfactory.contracts import JobState

    options = [{"name": "Backlog", "id": "OPT_BACKLOG"}, {"name": "TO-DO", "id": "OPT_TODO"},
               {"name": "In progress", "id": "OPT_PROG"}, {"name": "In review", "id": "OPT_REVIEW"},
               {"name": "Done", "id": "OPT_DONE"}]
    script = [
        ("field-list", json.dumps({"fields": [{"name": "Status", "id": "FID", "options": options}]})),
        ("project view", json.dumps({"id": "PID"})),
        ("repository(owner:", json.dumps({"data": {"repository": {"issue": {"id": "NODE7"}}}})),
        ("addProjectV2ItemById",
         json.dumps({"data": {"addProjectV2ItemById": {"item": {"id": "ITEM7"}}}})),
        ("updateProjectV2ItemFieldValue",
         json.dumps({"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "ITEM7"}}}})),
        ("api graphql", json.dumps({"data": {"organization": {"projectV2": {"items": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{"id": "ITEM7", "content": {"number": 7},
                       "fieldValueByName": {"name": "In review"}}]}}}}})),
    ]
    calls = []

    def gh(argv, **kw):
        calls.append(list(argv))
        joined = " ".join(argv)
        out = next((o for marker, o in script if marker in joined), "")
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")

    monkeypatch.setattr(subprocess, "run", gh)
    board = GitHubProjectBoard("org", "6", token="t")

    moved = board.set_status(issue="7", issue_url="https://github.com/o/r/issues/7",
                             state=JobState.PR_OPEN, needs_person=True)

    sent = [a.split("=", 1)[1] for argv in calls if "updateProjectV2ItemFieldValue" in " ".join(argv)
            for a in argv if a.startswith("option=")]
    assert moved and sent == ["OPT_BACKLOG"], (moved, sent)
