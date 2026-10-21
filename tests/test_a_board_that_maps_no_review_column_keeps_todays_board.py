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
