"""A board that maps a review column gets its pull requests there (#753, AC2).

A pull request waiting only for a person's review went to Needs Action on every row — the column
every park uses — so whoever triaged the board could not tell a reviewer's wait from a stuck card
(reported 2026-10-14 from a deployment of ~19 Jira projects). The resolver now answers
`needs_review` for it; this holds the other half, on each of the seven rows that turn a key into a
column: a deployment that MAPPED the key — a `Needs Review` row in `board.db`, an option on its
Projects board, `status_map` on Jira, `state_map` on the Azure tracker, `columns` on the Azure
board — gets the card in that column, and not in Needs Action.

Red on `main` (1be1835a) on every row: the card lands in Needs Action, its option or its status.
The rows, and how each reads where the card landed, are in
`tests/a_pull_request_awaiting_review_on_each_row.py`.
"""

from __future__ import annotations

import pytest

from tests.a_pull_request_awaiting_review_on_each_row import ROWS, github_person_gated_move


@pytest.mark.parametrize("row", list(ROWS))
def test_the_pull_request_lands_in_the_review_column(row, tmp_path, monkeypatch):
    where = ROWS[row](True, tmp_path, monkeypatch)

    assert where.landed == where.review, (
        f"{row}: the deployment mapped a review column ({where.review!r}) and a pull request "
        f"waiting on a person's review landed in {where.landed or 'nothing'!r}"
        + (" — the column every park uses" if where.landed == where.needs_action else ""))


def test_a_github_board_the_platform_made_gets_the_pull_request_in_its_needs_review(monkeypatch):
    """A Projects board the platform created carries "Needs Review" under its default name, and
    the deployment maps nothing: a pull request waiting on a person's review goes there. The
    parametrized row above maps the key to a name of its own, so it cannot see the default.

    GREEN ON 374ef5cd, as it must be: it holds `columns.yields_its_name` to its narrow case. With
    the name made to yield even when no other key carries it, `set_status` skips the default
    and sends the card to Needs Action (plan 753, row 45)."""
    options = [{"name": "Backlog", "id": "OPT_BACKLOG"}, {"name": "TO-DO", "id": "OPT_TODO"},
               {"name": "In progress", "id": "OPT_PROG"}, {"name": "In review", "id": "OPT_REVIEW"},
               {"name": "Needs Review", "id": "OPT_NEEDS_REVIEW"},
               {"name": "Needs Action", "id": "OPT_ACTION"}, {"name": "Done", "id": "OPT_DONE"}]

    moved, sent, board = github_person_gated_move(monkeypatch, options)

    assert moved and sent == ["OPT_NEEDS_REVIEW"], (moved, sent)
    assert board.stage_key("Needs Review") == "needs_review"


def test_a_github_deployment_that_maps_needs_review_onto_its_review_column_gets_what_it_mapped(
        monkeypatch):
    """`columns: {needs_review: "In review"}` is the deployment's explicit choice, as on Jira: the
    pull request goes there and reads back as `in_review` (two keys, one status — the documented
    behaviour). `columns.yields_its_name` yields only `needs_review`'s DEFAULT name, never one the
    deployment wrote.

    GREEN ON 64a666dd, as it must be: it holds the default-name check in `yields_its_name`. With that
    check dropped, the mapped "In review" yields to `in_review`'s default, and the card goes to
    Needs Action (the branch review of 64a666dd, cut c1, measured 2026-10-22; plan 753, row 47)."""
    options = [{"name": n, "id": "OPT_" + n} for n in
               ("Backlog", "TO-DO", "In progress", "In review", "Needs Action", "Done")]

    moved, sent, board = github_person_gated_move(monkeypatch, options,
                                                  columns={"needs_review": "In review"})

    assert moved and sent == ["OPT_In review"], (moved, sent)
    assert board.stage_key("In review") == "in_review"
