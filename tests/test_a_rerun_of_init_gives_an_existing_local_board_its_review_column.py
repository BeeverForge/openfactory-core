"""A re-run of `project init` gives an existing local board its review column (#753, Q1 answer B).

A local board made before #753 has main's six rows in `board.db` — Backlog, TO-DO, In progress,
In review, Needs Action, Done — and no "Needs Review", so a pull request waiting for a person's
review keeps landing in Needs Action there (AC3). The human chose (2026-10-21) that such a
deployment opts in by re-running `openfactory project init`, and that the row lands where a new
board has it: between In review and Needs Action.

RED BEFORE THIS CHANGE, MEASURED 2026-10-21 on a real six-row board written by main 1be1835a's
`project init`: the branch's re-run printed `· board already attached (6 columns (Backlog, TO-DO,
In progress, In review, Needs Action, Done))` and wrote nothing — `cli.py` skipped the setup's
`create` whenever `attached` answered. And `LocalBoardSetup.create` called directly gave the new
row position 4, which Needs Action already held, so the board read `… Needs Action, Needs Review,
Done`: the two columns in the wrong order.

The six rows are written LITERALLY, as `tests/a_pull_request_awaiting_review_on_each_row.py`
writes them for AC3, with TO-DO renamed the way a deployment may rename it (C-14), so a re-run
that restored the platform's word would show.

EVERY RE-RUN COMES THROUGH BOTH DOORS: the command a person types, and the `project_init` row it
maps onto, which the panel and `act` run too. The completion lives in the row's board step since
#741 moved `project init` onto the row; the command is one door onto it, and the opt-in the upgrade
note gives must hold whichever a deployment uses.
"""

from __future__ import annotations

import sqlite3
import sys

import pytest

sys.path.insert(0, "tests")
import one_machine as om  # noqa: E402

from tests.a_pull_request_awaiting_review_on_each_row import MAINS_SIX  # noqa: E402

#: The deployment's own name for `todo`, as a person who renamed it left it.
RENAMED_TODO = "A Fazer"


def _columns(root) -> list[tuple[str, str, int]]:
    with sqlite3.connect(root / "board.db") as db:
        return db.execute("SELECT key, name, position FROM columns WHERE project = 'myapp' "
                          "ORDER BY position ASC").fetchall()


def _cards(root) -> list[tuple]:
    with sqlite3.connect(root / "board.db") as db:
        return db.execute("SELECT * FROM cards WHERE project = 'myapp' ORDER BY ref").fetchall()


#: The doors a re-run comes through: what a person types, and the row every front end maps onto.
DOORS = {
    "project init": lambda repo: ("project", "init", "myapp", str(repo)),
    "the row": lambda repo: ("act", "project_init", "-p", "myapp"),
}


@pytest.fixture(params=sorted(DOORS))
def rerun(request):
    """Run `project_init` again on `myapp`, through one door: `(exit code, what it said)`."""
    return lambda repo: om.cli(*DOORS[request.param](repo))


@pytest.fixture
def six_row_board(tmp_path, monkeypatch):
    """A registered local project whose board is main's six rows, with one card on it."""
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = om.a_repository(tmp_path)
    om.a_deployment(tmp_path, monkeypatch=monkeypatch)
    code, out = om.cli("project", "init", "myapp", str(repo))
    assert code == 0, out
    code, out = om.cli("act", "card_create", "-p", "myapp", "-P", "title=Add the feature",
                       "-P", "body=a card that was on the board before the re-run")
    assert code == 0, out
    with sqlite3.connect(tmp_path / "board.db") as db:
        db.execute("DELETE FROM columns WHERE project = 'myapp'")
        for position, (key, name) in enumerate(MAINS_SIX):
            db.execute("INSERT INTO columns(project, key, name, position) VALUES (?,?,?,?)",
                       ("myapp", key, RENAMED_TODO if key == "todo" else name, position))
        db.execute("UPDATE cards SET column_key = 'needs_action' WHERE project = 'myapp'")
    return tmp_path, repo


def test_the_rerun_adds_needs_review_between_in_review_and_needs_action(six_row_board, rerun):
    root, repo = six_row_board

    code, out = rerun(repo)

    assert code == 0, out
    assert [name for _, name, _ in _columns(root)] == [
        "Backlog", RENAMED_TODO, "In progress", "In review", "Needs Review", "Needs Action",
        "Done"], f"the re-run left the six-row board as {_columns(root)}; it said:\n{out}"


def test_the_rerun_gives_every_column_a_position_of_its_own(six_row_board, rerun):
    """A tie sorts by insertion order, which is how the measured board read Needs Review AFTER
    Needs Action: the order the panel shows must not depend on when a row was written."""
    root, repo = six_row_board

    rerun(repo)

    positions = [position for _, _, position in _columns(root)]
    assert len(set(positions)) == len(positions) == 7, f"positions after the re-run: {_columns(root)}"


def test_the_rerun_renames_no_column_the_deployment_had(six_row_board, rerun):
    root, repo = six_row_board

    rerun(repo)

    names = {key: name for key, name, _ in _columns(root)}
    assert {key: names.get(key) for key, _ in MAINS_SIX} == {
        key: (RENAMED_TODO if key == "todo" else name) for key, name in MAINS_SIX}, (
        "a re-run of init renamed a column the deployment had")


def test_the_rerun_leaves_the_cards_where_they_were(six_row_board, rerun):
    """The new column is opted into, not back-filled: a card in Needs Action before the re-run is
    there after it, and the next move of a pull request is what puts one in Needs Review."""
    root, repo = six_row_board
    before = _cards(root)

    rerun(repo)

    assert _cards(root) == before, "a re-run of init touched the cards"


def test_the_rerun_says_what_it_added(six_row_board, rerun):
    """`init` is read at a terminal: a re-run that changed the board says so, and names it."""
    _, repo = six_row_board

    _, out = rerun(repo)

    assert "Needs Review" in out and "added" in out, out


def test_a_second_rerun_on_the_seven_row_board_changes_nothing(six_row_board, rerun):
    root, repo = six_row_board
    rerun(repo)
    seven = _columns(root)

    code, out = rerun(repo)

    assert code == 0, out
    assert _columns(root) == seven
    assert "added" not in out, f"a re-run that changed nothing said it added something:\n{out}"


@pytest.fixture
def a_hand_ordered_seven_row_board(six_row_board):
    """The seven-row board a re-run made, after a person moved Needs Action to the end by hand
    (position 99, as @robertocsp measured it on PR #1040, 2026-10-22)."""
    root, repo = six_row_board
    code, out = om.cli("project", "init", "myapp", str(repo))
    assert code == 0, out
    with sqlite3.connect(root / "board.db") as db:
        db.execute("UPDATE columns SET position = 99 WHERE project = 'myapp' "
                   "AND key = 'needs_action'")
    return root, repo


def test_a_rerun_keeps_the_order_a_person_gave_the_board(a_hand_ordered_seven_row_board, rerun):
    """A re-run that adds nothing moves nothing: the board a person ordered by hand keeps its order.

    RED ON 3cfca18d AND ON fa0171c1 (@robertocsp, PR #1040's review, Not-blocking 3, 2026-10-22):
    `LocalBoardSetup.create` wrote every row's position on every call, so the board read
    `…, Needs Review, Done, Needs Action` before the re-run and `…, Needs Review, Needs Action,
    Done` after it, a person's order undone by a command that added nothing."""
    root, repo = a_hand_ordered_seven_row_board
    before = _columns(root)

    code, out = rerun(repo)

    assert code == 0, out
    assert _columns(root) == before, f"a re-run that added nothing re-ordered the board:\n{out}"


def test_a_rerun_that_adds_nothing_does_not_say_it_added_columns(a_hand_ordered_seven_row_board,
                                                                  rerun):
    """`init` says "added the columns it lacked" only when the board has a key it lacked before.

    RED ON 3cfca18d AND ON fa0171c1 (the same review point): the sentence was decided by comparing
    `attached()`'s position-ordered names, so the re-order above made `init` print "✓ board: added
    the columns it lacked" on a board it had added nothing to."""
    _, repo = a_hand_ordered_seven_row_board

    _, out = rerun(repo)

    assert "added the columns it lacked" not in out, out


def test_init_decides_added_by_the_keys_not_by_the_sentence(a_hand_ordered_seven_row_board, rerun,
                                                             monkeypatch):
    """A row whose `create` re-orders a board and adds no key has added nothing, whatever its
    `attached()` sentence now reads: `init` compares the keys before and after.

    The local row no longer re-orders a board it adds nothing to, so the CLI's own rule is held
    here against a row that still does: `create` wrapped to write board order on every call, as
    `LocalBoardSetup.create` did on 3cfca18d. RED ON fa0171c1: `cli.py` compared the sentences."""
    from openfactory.adapters.board.columns import BOARD_ORDER
    from openfactory.adapters.board_setup.local import LocalBoardSetup

    root, repo = a_hand_ordered_seven_row_board
    create = LocalBoardSetup.create

    def create_and_reorder(self, *, project, owner, title, token):
        answer = create(self, project=project, owner=owner, title=title, token=token)
        with sqlite3.connect(root / "board.db") as db:
            for position, key in enumerate(BOARD_ORDER):
                db.execute("UPDATE columns SET position = ? WHERE project = 'myapp' AND key = ?",
                           (position, key))
        return answer

    monkeypatch.setattr(LocalBoardSetup, "create", create_and_reorder)

    _, out = rerun(repo)

    assert [key for key, _, _ in _columns(root)][-2:] == ["needs_action", "done"], (
        f"the stand-in row did not re-order the board: {_columns(root)}")
    assert "added the columns it lacked" not in out, out
