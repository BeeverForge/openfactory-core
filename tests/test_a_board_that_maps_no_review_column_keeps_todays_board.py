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

from tests.a_pull_request_awaiting_review_on_each_row import ROWS, github_person_gated_move


@pytest.mark.parametrize("row", list(ROWS))
def test_the_pull_request_still_lands_in_needs_action(row, tmp_path, monkeypatch):
    where = ROWS[row](False, tmp_path, monkeypatch)

    assert where.landed == where.needs_action, (
        f"{row}: the deployment maps no review column, and a pull request waiting on a person's "
        f"review landed in {where.landed or 'nothing — it stayed where it was'!r} instead of "
        f"Needs Action ({where.needs_action!r})")



def test_the_local_board_says_which_column_it_fell_back_from(tmp_path, monkeypatch, caplog):
    """The local board's fallback is not silent: a person reading the log learns that this board
    has no Needs Review row and that the card went to Needs Action instead, which is what a
    deployment opting in looks for. The warning names both keys. On this branch at 70cfff7c,
    cutting `if key != keys[0]` to `if False` in `LocalBoard.set_status` survived every test and
    plan 753 (#753's review, cuts table); this holds it. It also names the remedy, the re-run of
    `project init` that adds the missing row (PR #1040's review)."""
    import logging

    from tests.a_pull_request_awaiting_review_on_each_row import local_board

    with caplog.at_level(logging.WARNING, logger="openfactory"):
        where = local_board(False, tmp_path, monkeypatch)

    fell_back = [r.getMessage() for r in caplog.records
                 if r.levelno == logging.WARNING and "'needs_review'" in r.getMessage()]
    assert where.landed == where.needs_action
    assert len(fell_back) == 1 and "'needs_action'" in fell_back[0], [
        r.getMessage() for r in caplog.records]
    assert "openfactory project init acme" in fell_back[0], fell_back


def test_a_github_board_with_neither_column_still_sends_the_pull_request_to_backlog(monkeypatch):
    """A board made before its owner added Needs Action by hand has neither option. On `main` the
    person-gated pull request fell back to Backlog (`set_column`'s fallback for Needs Action); the
    last of `column_keys` must still be the name `set_column` is handed, or it moves nowhere.

    GREEN ON `main` (1be1835a) AND ON THE BRANCH, as an invariant is: it holds the last resort
    against a cut. With `names[-1]` cut to `names[0]` in `GitHubProjectBoard.set_status`, the name
    handed on is "Needs Review", which `set_column` does not map, and the card moves nowhere
    (`AssertionError: (False, [])`). That cut survived the 36 GitHub test modules (#753's review,
    point 2)."""
    options = [{"name": "Backlog", "id": "OPT_BACKLOG"}, {"name": "TO-DO", "id": "OPT_TODO"},
               {"name": "In progress", "id": "OPT_PROG"}, {"name": "In review", "id": "OPT_REVIEW"},
               {"name": "Done", "id": "OPT_DONE"}]

    moved, sent, _board = github_person_gated_move(monkeypatch, options)

    assert moved and sent == ["OPT_BACKLOG"], (moved, sent)


def test_a_github_board_whose_review_column_is_called_needs_review_parks_the_pull_request(
        monkeypatch):
    """A GitHub deployment that renamed its review column to "Needs Review" (`columns:
    {in_review: "Needs Review"}`) and never mapped `needs_review` keeps sending a person-gated
    pull request to Needs Action, where `main` sent it, and reads the card back as a park.

    RED ON 374ef5cd (PR #1040's review, @hermesfelipe, 2026-10-21): `_columns` merges the
    defaults, so `needs_review`'s default "Needs Review" matched that board's `in_review` option,
    `set_status` moved the card there, and `key_for` read it back as `in_review` — RUNNING, the
    #166 defect again for that deployment. `needs_review`'s default name yields to a key the
    deployment gave it (`columns.YIELDS_ITS_DEFAULT_NAME`), on the write as on the read."""
    options = [{"name": "Backlog", "id": "OPT_BACKLOG"}, {"name": "TO-DO", "id": "OPT_TODO"},
               {"name": "In progress", "id": "OPT_PROG"},
               {"name": "Needs Review", "id": "OPT_THEIR_REVIEW"},
               {"name": "Needs Action", "id": "OPT_ACTION"}, {"name": "Done", "id": "OPT_DONE"}]

    moved, sent, board = github_person_gated_move(monkeypatch, options,
                                                   columns={"in_review": "Needs Review"})

    named = {o["id"]: o["name"] for o in options}
    assert moved and sent == ["OPT_ACTION"], (moved, [named.get(o) for o in sent])
    assert board.stage_key(named[sent[0]]) == "needs_action"



def test_the_local_board_says_it_once_and_not_on_every_move(tmp_path, monkeypatch, caplog):
    """A board made before 0.7 has no Needs Review row until `project init` is re-run, and every
    pull request waiting on a person falls back on it: the warning that says so is said once per
    board in a process, not on every move. The second pull request still lands in Needs Action.

    RED ON 374ef5cd (PR #1040's review, @hermesfelipe, 2026-10-21: "warns on every move for any
    pre-0.7 board until init is re-run"): two moves on one board logged the warning twice."""
    import logging

    from openfactory.adapters.board.local import LocalBoard
    from openfactory.adapters.tracker.local import LocalTracker
    from openfactory.contracts import JobState
    from tests.a_pull_request_awaiting_review_on_each_row import local_board

    with caplog.at_level(logging.WARNING, logger="openfactory"):
        local_board(False, tmp_path, monkeypatch)
        tracker = LocalTracker("acme", db_path=tmp_path / "board.db")
        second = tracker.create_ticket(title="Import", body="")
        LocalBoard(tracker).set_status(issue=second, issue_url="", state=JobState.PR_OPEN,
                                       needs_person=True)

    fell_back = [r.getMessage() for r in caplog.records
                 if r.levelno == logging.WARNING and "'needs_review'" in r.getMessage()]
    landed = LocalBoard(LocalTracker("acme", db_path=tmp_path / "board.db")).columns() or {}
    assert landed.get(str(second).lstrip("#")) == "Needs Action", landed
    assert len(fell_back) == 1, fell_back


@pytest.mark.parametrize(("carrier", "called"), [
    ("in_review", "Needs Review"), ("needs_action", "Needs Review"),
    # the panel lets a person type the name in any case, and `yields_its_name` compares casefolded
    ("in_review", "Needs review")])
def test_a_rerun_of_init_adds_no_second_needs_review_where_another_column_carries_it(
        carrier, called, tmp_path, monkeypatch):
    """A local board of main's six rows whose `in_review` or `needs_action` row a person renamed
    "Needs Review" keeps ONE column of that name across a re-run of `project init`, under its own
    key, and a pull request waiting on a person still lands where `main` put it: Needs Action, or
    the park itself when the park is the column called "Needs Review". `init` says why it added no
    column and how to opt in. The name is compared in any case, as `columns.yields_its_name` compares.

    RED ON 3cfca18d (PR #1040, @hermesfelipe's blocker and @robertocsp's Blocking 1, 2026-10-22):
    `LocalBoardSetup.create` inserted `needs_review` under its default name beside the row that
    already carried it — `[('in_review', 'Needs Review', 3), ('needs_review', 'Needs Review', 4),
    …]` — and the person-gated pull request went to the new row, whose name reads back as
    `in_review` (`columns.yields_its_name`), the factory's own review. The release note sends every
    local deployment through this re-run to opt in."""
    import sqlite3
    import sys

    sys.path.insert(0, "tests")
    import one_machine as om

    from openfactory.adapters.tracker.local import LocalTracker
    from openfactory.contracts import JobState
    from tests.a_pull_request_awaiting_review_on_each_row import MAINS_SIX

    monkeypatch.setenv("HOME", str(tmp_path))
    repo = om.a_repository(tmp_path)
    om.a_deployment(tmp_path, monkeypatch=monkeypatch)
    code, out = om.cli("project", "init", "myapp", str(repo))
    assert code == 0, out
    db = tmp_path / "board.db"
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM columns WHERE project = 'myapp'")
        for position, (key, name) in enumerate(MAINS_SIX):
            conn.execute("INSERT INTO columns(project, key, name, position) VALUES (?,?,?,?)",
                         ("myapp", key, called if key == carrier else name, position))

    code, out = om.cli("project", "init", "myapp", str(repo))

    assert code == 0, out
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT key, name, position FROM columns WHERE project = 'myapp' "
                            "ORDER BY position").fetchall()
    carriers = [key for key, name, _ in rows if name.strip().casefold() == "needs review"]
    assert carriers == [carrier], f"the re-run left {rows}; it said:\n{out}"
    assert f"'{carrier}'" in out and "map needs_review" in out and "`columns` option" in out, (
        f"init did not say which column already carries \"Needs Review\" and how to opt in:\n{out}")

    tracker = LocalTracker("myapp", db_path=db)
    ref = tracker.create_ticket(title="Export", body="")
    tracker.set_state(ref, JobState.PR_OPEN, needs_person=True)
    with sqlite3.connect(db) as conn:
        (landed,) = conn.execute("SELECT column_key FROM cards WHERE project = 'myapp' AND ref = ?",
                                 (str(ref).lstrip("#"),)).fetchone()
    assert landed == "needs_action", f"the pull request waiting on a person landed in {landed!r}"


@pytest.mark.parametrize("carrier", ["in_review", "needs_action"])
def test_a_new_local_board_whose_map_calls_another_column_needs_review_has_one(carrier, tmp_path):
    """The same rule on a board's FIRST `init`: a deployment whose `columns:` already calls
    `in_review` or `needs_action` "Needs Review" gets six columns, one of them of that name, and the
    setup says why it added no seventh.

    RED ON 3cfca18d (@robertocsp's Blocking 1, measured on a fresh `board.db` with the real
    `LocalBoardSetup.create`): `columns: '{"in_review": "Needs Review"}'` gave `['Backlog', 'TO-DO',
    'In progress', 'Needs Review', 'Needs Review', 'Needs Action', 'Done']`."""
    import json
    import sqlite3
    from types import SimpleNamespace

    from openfactory.adapters.board_setup.local import LocalBoardSetup

    db = tmp_path / "board.db"
    project = SimpleNamespace(name="acme", tracker=SimpleNamespace(kind="local", options={
        "board_db": str(db), "columns": json.dumps({carrier: "Needs Review"})}))
    setup = LocalBoardSetup()

    setup.create(project=project, owner="", title="acme", token=None)

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT key, name FROM columns WHERE project = 'acme' "
                            "ORDER BY position").fetchall()
    assert [key for key, name in rows if name == "Needs Review"] == [carrier], rows
    assert f"'{carrier}'" in setup.left_out(project), setup.left_out(project)
