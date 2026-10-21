"""A card in the review column is one the platform maps: named, read back, and judged (#753).

THE KEY THAT WENT OUT AND NEVER CAME BACK. #753 gives a pull request waiting only on a person's
review its own key, `needs_review`, apart from the parks in `needs_action`. The first attempt at it
(#258) taught the resolver to answer the key and declared it nowhere else, and its review measured
what a board then did with a card standing there:

    name_for("needs_review") -> ''      key_for("Needs Review") -> ''
    card_edit / card_close   -> "… is in 'Needs Review', which is not a column this platform
                                 maps, so it cannot tell where the card is in its life."

Every test #258 carried asserted the key going OUT to a row; none read it back. So these drive the
other direction, on the real parts: the platform's vocabulary and each board row's `stage_key` /
`stage_column` (AC4), the real `card_edit` and `card_close` on a real `board.db` whose board has
the seventh column (AC5), and the real `card_move` back to the queue (AC6). The only double is the
engine's answer to "is a job on this card" (`catalog._job_on_the_card`), which is the one part that
leaves the machine.

THE SEVENTH COLUMN IS WRITTEN HERE, NOT BY `project init`, and with `INSERT OR IGNORE`: the board
these tests need is one that HAS a Needs Review column, whichever code created it — a board made by
0.6's six-column setup and given the column by hand is the upgrade a deployment takes, and once the
setup writes it itself the insert is a no-op.
"""

from __future__ import annotations

import asyncio

import pytest

#: The review column as the platform names it on a board it created.
NEEDS_REVIEW = "Needs Review"

_A_CARD = ("## Objective\n\nExport the monthly report\n\n## Acceptance criteria\n\n"
           "- the export is a CSV\n")

#: What #258's review measured the door answering for a card in the review column.
_UNMAPPED = "not a column this platform maps"


# ── the parts ─────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def deployment(tmp_path, monkeypatch):
    """A registered local project with the board `project init` makes, plus the review column."""
    monkeypatch.setenv("OPENFACTORY_BOARD_DB", str(tmp_path / "board.db"))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(tmp_path / "metrics.db"))
    from openfactory.adapters.board_db import connect
    from openfactory.adapters.board_setup.local import LocalBoardSetup
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.product.board import forget_board
    from openfactory.registry import ProjectRegistry

    registry = ProjectRegistry()
    registry.add(Project(name="acme", repo_path=str(tmp_path), language="en",
                         tracker=ProviderRef(kind="local", repo="acme", options={})))
    project = registry.get("acme")
    LocalBoardSetup().create(project=project, owner="", title="acme", token=None)
    with connect(None, write=True) as conn:
        conn.execute("INSERT OR IGNORE INTO columns(project, key, name, position) "
                     "VALUES (?,?,?,?)", ("acme", "needs_review", NEEDS_REVIEW, 6))
    forget_board()
    yield project
    forget_board()


def _board(project):
    from openfactory.adapters.board import build_board

    return build_board(project)


def _column(project, ref: str) -> str:
    """The card's column as a second reader sees it: the board's own name, off a fresh row."""
    from openfactory.contracts.refs import canonical_ref

    return (_board(project).columns() or {}).get(canonical_ref(ref), "")


def _act(name: str, **params):
    from openfactory import actions

    by = actions.Actor(id="rob", display="Rob", via="panel", admin=True)
    return asyncio.run(actions.perform(name, by=by, **params))


def _awaiting_review(project) -> str:
    """A card the operator opened, now in the review column — where a pull request a person must
    review is placed (`column_key(PR_OPEN, needs_person=True)`)."""
    ref = _act("card_create", project="acme", title="Export", body=_A_CARD).data["issue"]
    assert _board(project).set_column(issue=ref, issue_url="", name=NEEDS_REVIEW)
    assert _column(project, ref) == NEEDS_REVIEW
    return ref


def _the_engine_says(monkeypatch, answer) -> list[tuple[str, str]]:
    """Stand the engine's answer in for `_job_on_the_card`, and record every time it is asked."""
    from openfactory.actions import catalog

    asked: list[tuple[str, str]] = []

    async def job_on_the_card(project, issue):
        from openfactory.contracts.refs import canonical_ref

        asked.append((project, canonical_ref(issue)))
        return answer

    monkeypatch.setattr(catalog, "_job_on_the_card", job_on_the_card)
    return asked


def _asked_about(ref: str) -> list[tuple[str, str]]:
    from openfactory.contracts.refs import canonical_ref

    return [("acme", canonical_ref(ref))]


def _a_job_waits_on_a_review():
    from openfactory.actions import catalog

    return catalog._JobOnTheCard(running=True, waiting_on="a person to review its pull request",
                                 answer_it="merge")


# ── AC4: the platform names the column and reads it back, on every row ──────────────────────

def _the_platform(_request):
    return None, NEEDS_REVIEW


def _the_local_board(request):
    return _board(request.getfixturevalue("deployment")), NEEDS_REVIEW


def _github_projects(_request):
    from openfactory.adapters.tracker.github_project import GitHubProjectBoard

    return GitHubProjectBoard("acme", "1", token="t"), NEEDS_REVIEW


def _a_jira_project(_request):
    from openfactory.adapters.board.jira import JiraProjectBoard
    from openfactory.adapters.tracker.jira import JiraTracker

    named = "Em revisão pelo cliente"
    tracker = JiraTracker(site="https://acme-team.atlassian.net", project_key="DAR",
                          email="alice@acme.ai", token="t", status_map={"needs_review": named})
    return JiraProjectBoard(tracker), named


def _an_azure_board(_request):
    from openfactory.adapters.board.azure_devops import AzureBoardsBoard

    named = "Aguardando revisão"
    return (AzureBoardsBoard(organization="acme", project="shop", token="t",
                             columns={"needs_review": named}), named)


_ROWS = {
    # board=None is the platform's own vocabulary: `stage_key` falls to `key_for` and
    # `stage_column` to `name_for`, the two #258's review measured answering ''.
    "the platform's own vocabulary": _the_platform,
    "the local board": _the_local_board,
    "GitHub Projects": _github_projects,
    "a Jira project, renamed in status_map": _a_jira_project,
    "an Azure Boards board, renamed in columns": _an_azure_board,
}


@pytest.mark.parametrize("row", list(_ROWS))
def test_the_platform_names_it_and_reads_it_back(row, request):
    """AC4: the review column is a stage the board names and the platform reads back.

    Before: `stage_key` answered `''` for it on every row — the local board's own rows dropped a
    key outside `CANONICAL_COLUMNS`, the generic seam refused a row's answer outside it, and the
    vocabulary itself did not hold it (#258's review: `key_for("Needs Review") -> ''`)."""
    from openfactory.adapters.board.base import stage_column, stage_key

    board, named = _ROWS[row](request)

    assert stage_key(board, named) == "needs_review", (
        f"{row}: {named!r} read back as {stage_key(board, named)!r}")
    assert stage_column(board, "needs_review") == named


def test_a_job_may_be_running_on_it_and_it_is_not_delivered():
    """AC4: a card in the review column has been taken up, may still have its job on it, and is
    not delivered work — asked of the key the column's own name reads back as.

    `_watch_to_merge` holds the floor through review for up to `merge_deadline_days`, so a close
    must ask the engine (`may_be_running`); a close there is never recorded as a delivery
    (`has_finished`). Before: `key_for("Needs Review")` answered `''`, which every one of the three
    reads as "I cannot tell"."""
    from openfactory.adapters.board.columns import (
        has_finished,
        has_started,
        key_for,
        may_be_running,
    )

    key = key_for(NEEDS_REVIEW)

    assert (key, has_started(key), may_be_running(key), has_finished(key)) == (
        "needs_review", True, True, False)


# ── AC5: the door reads a card there as waiting on a person ───────────────────────────────────

def test_the_door_reads_a_card_there_as_waiting_on_a_person(deployment, monkeypatch):
    """AC5: a card in the review column is judged by the door, not refused as unmapped.

    An edit is refused with the taken-up sentence (the text is what the job read at pickup), and a
    close asks the engine whether a job is still on the card: one a job waits on is refused naming
    the answer that job is waiting for, and one no job holds goes through the card's door and is
    closed as not delivered — the door reading the column as `waiting_on_a_person`
    (`lifecycle/table.py::BY_COLUMN`). Before: all three answered `card_unmapped` — "… is not a
    column this platform maps" — and the engine was never asked, so a pull request waiting on a
    review could not be closed at all (#258's review, measured on `card_edit` and `card_close`)."""
    ref = _awaiting_review(deployment)

    edit = _act("card_edit", project="acme", issue=ref, title="Export, as CSV")
    assert not edit.ok and edit.code == "conflict", edit.message
    assert _UNMAPPED not in edit.message, edit.message
    assert "has taken it up" in edit.message, edit.message

    asked = _the_engine_says(monkeypatch, _a_job_waits_on_a_review())
    close = _act("card_close", project="acme", issue=ref, reason="not wanted any more")
    assert not close.ok and _UNMAPPED not in close.message, close.message
    assert asked == _asked_about(ref), "the close never asked the engine whether a job is on it"
    assert "`merge`" in close.message, close.message
    assert _column(deployment, ref) == NEEDS_REVIEW

    from openfactory.actions import catalog

    _the_engine_says(monkeypatch, catalog._JobOnTheCard())
    closed = _act("card_close", project="acme", issue=ref, reason="not wanted any more")
    assert closed.ok, closed.message
    assert closed.data.get("delivered") is False, closed.data


# ── AC6: back to the queue only when no job waits on it ───────────────────────────────────────

def test_queueing_a_card_from_the_review_column_asks_whether_its_job_still_waits(deployment,
                                                                                 monkeypatch):
    """AC6: a card in the review column goes back to the queue by hand only when no job waits on
    it, as one in Needs Action does (`card_move`'s promoted-from-a-park check).

    Before: the move was refused as "not a column this platform maps". With the column mapped but
    the check still reading `needs_action` alone, the card would be queued under the job still
    watching its pull request, and the next pickup would start a second job on it."""
    ref = _awaiting_review(deployment)

    asked = _the_engine_says(monkeypatch, _a_job_waits_on_a_review())
    held = _act("card_move", project="acme", issue=ref, column="TO-DO")
    assert not held.ok and _UNMAPPED not in held.message, held.message
    assert asked == _asked_about(ref), "the move never asked the engine whether a job waits on it"
    assert "`merge`" in held.message, held.message
    assert _column(deployment, ref) == NEEDS_REVIEW

    from openfactory.actions import catalog

    _the_engine_says(monkeypatch, catalog._JobOnTheCard())
    queued = _act("card_move", project="acme", issue=ref, column="TO-DO")
    assert queued.ok, queued.message
    assert _column(deployment, ref) == "TO-DO"
