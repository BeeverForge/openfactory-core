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

from tests.a_pull_request_awaiting_review_on_each_row import ROWS


@pytest.mark.parametrize("row", list(ROWS))
def test_the_pull_request_lands_in_the_review_column(row, tmp_path, monkeypatch):
    where = ROWS[row](True, tmp_path, monkeypatch)

    assert where.landed == where.review, (
        f"{row}: the deployment mapped a review column ({where.review!r}) and a pull request "
        f"waiting on a person's review landed in {where.landed or 'nothing'!r}"
        + (" — the column every park uses" if where.landed == where.needs_action else ""))
