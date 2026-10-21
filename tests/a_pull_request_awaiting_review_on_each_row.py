"""A pull request a person must review, moved by each of the seven rows that resolve a column (#753).

`column_key(PR_OPEN, needs_person=True)` is resolved to a column in SEVEN places, each with its own
rule for "this deployment mapped the key": a `columns` row in `board.db` (the local tracker and
the local board), a Status option on a Projects v2 board, `status_map` on Jira (the tracker and the
board, which reads the tracker's map), `state_map` plus the process's categories and parking names
on the Azure Boards tracker, and `columns` on the Azure Boards board. Two test files ask the same
question of all seven — AC2, a deployment that mapped `needs_review`, and AC3, one that did not —
so the rows are built here, once, and each answers WHERE THE CARD LANDED, read off the thing the
row wrote:

* local: the card's column as a second reader of `board.db` sees it (`LocalBoard.columns()`);
* GitHub: the `option` id sent in the `updateProjectV2ItemFieldValue` mutation's argv;
* Jira: the status the POSTed transition goes to;
* Azure Boards: the `System.State` value in the PATCH body.

`""` means the row moved nothing. The only doubles are the vendors' transports, in the shapes the
rows' own test files already record (`test_tracker_board_writes.py`, `test_a_jira_project_is_a_board.py`,
`test_the_ado_tracker.py`, `test_the_ado_board.py`); every adapter is the real class.

THE LOCAL BOARDS ARE WRITTEN LITERALLY, NOT BY `LocalBoardSetup`. A board a deployment already has
was made by 0.6's setup, which wrote six rows; the setup under test writes whatever the vocabulary
now holds. So the six rows are spelled out below as `main` (1be1835a) wrote them, and the mapped
board is those six plus `needs_review` — a test that built its board from the module it checks
would bless whatever that module says.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from openfactory.contracts import JobState

#: The six columns `LocalBoardSetup` wrote on `main` (1be1835a), in its `BOARD_ORDER`.
MAINS_SIX = (("backlog", "Backlog"), ("todo", "TO-DO"), ("in_progress", "In progress"),
             ("in_review", "In review"), ("needs_action", "Needs Action"), ("done", "Done"))

#: The name a deployment that maps the key gives its review column. Not the platform's own
#: "Needs Review" on the hosted rows, so a row that resolved the key by the vocabulary's default
#: instead of by the deployment's map would miss it.
AWAITING_REVIEW = "Awaiting Review"


@dataclass(frozen=True)
class Landing:
    """Where the card went, and the two places it could have been meant to go."""

    landed: str
    review: str
    needs_action: str


def _local_board(db, *, maps_review: bool) -> None:
    from openfactory.adapters.board_db import connect

    rows = [*MAINS_SIX, *((("needs_review", "Needs Review"),) if maps_review else ())]
    with connect(db, write=True) as conn:
        for position, (key, name) in enumerate(rows):
            conn.execute("INSERT INTO columns(project, key, name, position) VALUES (?,?,?,?)",
                         ("acme", key, name, position))


def local_tracker(maps_review: bool, tmp_path, monkeypatch) -> Landing:
    from openfactory.adapters.board.local import LocalBoard
    from openfactory.adapters.tracker.local import LocalTracker

    db = tmp_path / "board.db"
    _local_board(db, maps_review=maps_review)
    tracker = LocalTracker("acme", db_path=db)
    ref = tracker.create_ticket(title="Export", body="")

    tracker.set_state(ref, JobState.PR_OPEN, needs_person=True)

    landed = (LocalBoard(LocalTracker("acme", db_path=db)).columns() or {}).get("1", "")
    return Landing(landed, "Needs Review", "Needs Action")


def local_board(maps_review: bool, tmp_path, monkeypatch) -> Landing:
    from openfactory.adapters.board.local import LocalBoard
    from openfactory.adapters.tracker.local import LocalTracker

    db = tmp_path / "board.db"
    _local_board(db, maps_review=maps_review)
    tracker = LocalTracker("acme", db_path=db)
    ref = tracker.create_ticket(title="Export", body="")

    LocalBoard(tracker).set_status(issue=ref, issue_url="", state=JobState.PR_OPEN,
                                   needs_person=True)

    landed = (LocalBoard(LocalTracker("acme", db_path=db)).columns() or {}).get("1", "")
    return Landing(landed, "Needs Review", "Needs Action")


# ── GitHub Projects v2: `gh` answered from a script, as `test_tracker_board_writes.py` does ─────

def github_projects(maps_review: bool, tmp_path, monkeypatch) -> Landing:
    """A Projects v2 board whose Status field has the platform's six options, plus the deployment's
    review column when it maps one. The card lands on whichever option id the move mutation sends."""
    from openfactory.adapters.tracker.github_project import GitHubProjectBoard

    options = [{"name": "Backlog", "id": "OPT_BACKLOG"}, {"name": "TO-DO", "id": "OPT_TODO"},
               {"name": "In progress", "id": "OPT_PROG"}, {"name": "In review", "id": "OPT_REVIEW"},
               {"name": "Needs Action", "id": "OPT_NEEDS_ACTION"}, {"name": "Done", "id": "OPT_DONE"}]
    if maps_review:
        options.append({"name": AWAITING_REVIEW, "id": "OPT_AWAITING_REVIEW"})
    script = [
        ("field-list", json.dumps({"fields": [{"name": "Status", "id": "FID",
                                               "options": options}]})),
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
    calls: list[list[str]] = []

    def gh(argv, **kw):
        calls.append(list(argv))
        joined = " ".join(argv)
        stdout = next((out for marker, out in script if marker in joined), "")
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", gh)
    columns = {"needs_review": AWAITING_REVIEW} if maps_review else None
    board = GitHubProjectBoard("org", "6", token="t", columns=columns)

    board.set_status(issue="7", issue_url="https://github.com/o/r/issues/7",
                     state=JobState.PR_OPEN, needs_person=True)

    moves = [argv for argv in calls if "updateProjectV2ItemFieldValue" in " ".join(argv)]
    sent = [a.split("=", 1)[1] for argv in moves for a in argv if a.startswith("option=")]
    return Landing(sent[-1] if sent else "", "OPT_AWAITING_REVIEW", "OPT_NEEDS_ACTION")


# ── Jira: the REST call replaced on the real tracker, as `test_a_jira_project_is_a_board.py` ────

#: A site's whole map, as a deployment writes it; `needs_review` joins it only when mapped.
JIRA_STATUS_MAP = {"backlog": "Backlog", "todo": "TO-DO", "in_progress": "Em andamento",
                   "in_review": "Em análise", "needs_action": "Needs Action", "done": "Donee"}

#: The transitions the workflow offers from where the issue stands, by the status each goes to.
_JIRA_TRANSITIONS = {"transitions": [
    {"id": str(n), "name": f"to {to}", "to": {"name": to}}
    for n, to in enumerate(("Backlog", "TO-DO", "Em andamento", "Em análise", "Needs Action",
                            "Donee", AWAITING_REVIEW), start=11)]}


def _jira(maps_review: bool):
    from openfactory.adapters.tracker.jira import JiraTracker

    status_map = dict(JIRA_STATUS_MAP, **({"needs_review": AWAITING_REVIEW} if maps_review else {}))
    tracker = JiraTracker(site="https://x", project_key="DAR", email="a@b.c", token="t",
                          status_map=status_map)
    posted: list[str] = []

    def call(method, path, payload=None, **kw):
        if method == "POST" and path.endswith("/transitions"):
            posted.append(str(((payload or {}).get("transition") or {}).get("id") or ""))
            return {}
        if path.endswith("/transitions"):
            return _JIRA_TRANSITIONS
        if path.startswith("issue/"):
            return {"fields": {"status": {"name": "Em análise"}}}
        return {}

    tracker._call = call

    def landed() -> str:
        to = {t["id"]: t["to"]["name"] for t in _JIRA_TRANSITIONS["transitions"]}
        return to.get(posted[-1], "") if posted else ""

    return tracker, landed


def jira_tracker(maps_review: bool, tmp_path, monkeypatch) -> Landing:
    tracker, landed = _jira(maps_review)

    tracker.set_state("DAR-1", JobState.PR_OPEN, needs_person=True)

    return Landing(landed(), AWAITING_REVIEW, "Needs Action")


def jira_board(maps_review: bool, tmp_path, monkeypatch) -> Landing:
    from openfactory.adapters.board.jira import JiraProjectBoard

    tracker, landed = _jira(maps_review)

    JiraProjectBoard(tracker).set_status(issue="DAR-1", issue_url="", state=JobState.PR_OPEN,
                                         needs_person=True)

    return Landing(landed(), AWAITING_REVIEW, "Needs Action")


# ── Azure Boards: the real client with only `call` replaced, as `test_the_ado_tracker.py` ───────

#: A Basic-shaped process, as `test_the_ado_tracker.py` recorded it live: Needs Action has no
#: category of its own (InProgress), and In review is the Resolved one — the category a review
#: column must NEVER be derived from, because it is `in_review`'s.
_ADO_STATES = [{"name": "To Do", "category": "Proposed"},
               {"name": "Doing", "category": "InProgress"},
               {"name": "Needs Action", "category": "InProgress"},
               {"name": "In review", "category": "Resolved"},
               {"name": "Done", "category": "Completed"}]

#: The board's columns, each mapping the work item type to the state of the same name.
_ADO_COLUMNS = ["To Do", "Doing", "Needs Action", "In review", "Done"]


def _ado_client(*, states: list[dict], columns: list[str]):
    from openfactory.adapters.azure_devops import AzureDevOpsClient

    class Recorded(AzureDevOpsClient):
        def __init__(self, **kw):
            super().__init__(organization="acme-ai", project="factory", token="pat")
            self.patched: list[str] = []

        def call(self, method, path, *, body=None, params=None, project_scoped=True,
                 content_type="application/json", api_version=None):
            method = method.upper()
            if method == "PATCH" and path.startswith("wit/workitems/"):
                self.patched.append(str(body[0]["value"]))
                return {"id": 3}
            if path == "wit/workitemtypes/Issue/states":
                return {"value": states}
            if path.endswith("/columns"):
                return {"value": [{"name": c, "stateMappings": {"Issue": c}} for c in columns]}
            if path.startswith("wit/workitems/"):
                return {"id": 3, "fields": {"System.WorkItemType": "Issue",
                                            "System.State": "In review"}}
            raise AssertionError(f"the adapter called {method} {path}, a route this row never "
                                 "recorded")

    return Recorded()


def azure_tracker(maps_review: bool, tmp_path, monkeypatch) -> Landing:
    """Mapped is `state_map`; unmapped is a process with no state for it, where `needs_action`
    is found the way it always was — by its parking name, since it has no category."""
    from openfactory.adapters.tracker.azure_devops import AzureBoardsTracker

    states = [*_ADO_STATES, *([{"name": AWAITING_REVIEW, "category": "Resolved"}]
                              if maps_review else [])]
    client = _ado_client(states=states, columns=[])
    state_map = {"needs_review": AWAITING_REVIEW} if maps_review else None
    tracker = AzureBoardsTracker(organization="acme-ai", project="factory", client=client,
                                 state_map=state_map)

    tracker.set_state("3", JobState.PR_OPEN, needs_person=True)

    return Landing(client.patched[-1] if client.patched else "", AWAITING_REVIEW, "Needs Action")


def azure_board(maps_review: bool, tmp_path, monkeypatch) -> Landing:
    """Mapped is `columns` naming a column the board has; the row's own defaults name none."""
    from openfactory.adapters.board.azure_devops import AzureBoardsBoard

    client = _ado_client(states=[], columns=[*_ADO_COLUMNS,
                                             *([AWAITING_REVIEW] if maps_review else [])])
    monkeypatch.setattr("openfactory.adapters.board.azure_devops.AzureDevOpsClient",
                        lambda **kw: client)
    columns = {"needs_review": AWAITING_REVIEW} if maps_review else None
    board = AzureBoardsBoard(organization="acme-ai", project="factory", team="factory Team",
                             board="Issues", columns=columns)

    board.set_status(issue="3", issue_url="", state=JobState.PR_OPEN, needs_person=True)

    return Landing(client.patched[-1] if client.patched else "", AWAITING_REVIEW, "Needs Action")


#: Every row that resolves a lifecycle key to a column, by the name a failing case is reported as.
ROWS: dict[str, Callable[..., Landing]] = {
    "local tracker": local_tracker,
    "local board": local_board,
    "GitHub Projects": github_projects,
    "Jira tracker": jira_tracker,
    "Jira board": jira_board,
    "Azure Boards tracker": azure_tracker,
    "Azure Boards board": azure_board,
}
