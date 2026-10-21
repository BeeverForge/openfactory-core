"""A pull request waiting for a reviewer is not a blocked card (#753, criterion AC1).

Reported 2026-10-14 from a downstream deployment (one host, ~19 projects on one Jira site): on a
board with both an "In Review" and a "Blocked" column, a card whose pull request is open and only
needs a person's review was moved to the same column as a card that is genuinely stuck — a failing
gate, missing criteria. Whoever triages the board could not tell the two apart.

The cause is one line. `column_key(JobState.PR_OPEN, needs_person=True)` answered `"needs_action"`
(`openfactory/adapters/tracker/base.py:167-168` on 1be1835a, the same lines the issue cites at
v0.6.0-rc.2:168) — the key every park uses. #166 was right that a person is the blocker there; it
was wrong to give that person's wait the stuck cards' key.

So the resolver answers a key of its own, `needs_review`, for that one case, and the contract
declares in ONE table where an unmapped `needs_review` falls back to: `needs_action`'s column, so a
deployment that maps nothing keeps today's board. Every other answer is unchanged — the rest of the
review bucket with a person still answers `needs_action` (no caller passes `True` with those states
today; `machine.py` passes it only with `PR_OPEN`), and a park stays a park whatever a caller says.
"""

from __future__ import annotations

from openfactory.adapters.tracker.base import STATE_KEYS, column_key
from openfactory.contracts import JobState

# The states of the review bucket other than `pr_open`, spelled here rather than read from the
# module's private tuple, so a change to that tuple is a change this file sees.
_THE_REST_OF_THE_REVIEW_BUCKET = (JobState.REVIEWING, JobState.MERGED,
                                  JobState.STAGING_VERIFYING, JobState.PROD_VERIFYING)

# The parks: a person is the blocker by the state's own nature, and a card here IS stuck.
_THE_PARKS = (JobState.NEEDS_REFINEMENT, JobState.ON_HOLD, JobState.BLOCKED, JobState.FAILED,
              JobState.AWAITING_PROD_APPROVAL)


def test_a_pull_request_a_person_must_review_answers_its_own_key():
    """AC1. On 1be1835a this answered `"needs_action"`, the key of every park (#753)."""
    assert column_key(JobState.PR_OPEN, needs_person=True) == "needs_review"


def test_a_triager_can_tell_a_reviewers_wait_from_a_stuck_card():
    """AC1, the issue's own sentence: the two must not share a key. On 1be1835a every park and the
    person-gated pull request all answered `"needs_action"`."""
    waiting = column_key(JobState.PR_OPEN, needs_person=True)
    shared = {s.value for s in _THE_PARKS
              if column_key(s) == waiting or column_key(s, needs_person=True) == waiting}
    assert not shared, f"a pull request waiting for review shares {waiting!r} with {sorted(shared)}"


def test_every_other_answer_of_the_resolver_is_unchanged():
    """AC1, "every other answer is unchanged": for every `JobState` and every value of
    `needs_person`, the answer is the one 1be1835a gave — `STATE_KEYS` when the state decides or
    the caller says no person; `needs_action` for the rest of the review bucket with a person; a
    park stays `needs_action` and `done` stays `done` whatever is passed. Only the one pair above
    moves; widening the new key to the whole review bucket turns this red."""
    wrong = []
    for state in JobState:
        for needs_person in (None, False, True):
            if state is JobState.PR_OPEN and needs_person:
                continue  # the one answer this change moves, held by the test above
            if needs_person and state in _THE_REST_OF_THE_REVIEW_BUCKET:
                expected = "needs_action"
            else:
                expected = STATE_KEYS.get(state)
            got = column_key(state, needs_person=needs_person)
            if got != expected:
                wrong.append((state.value, needs_person, got, expected))
    assert not wrong, f"(state, needs_person, answered, expected): {wrong}"
    # The parks and `done`, named, so the table above cannot drift away from them unnoticed.
    assert {column_key(s, needs_person=p) for s in _THE_PARKS for p in (None, False, True)} \
        == {"needs_action"}
    assert column_key(JobState.DONE, needs_person=True) == "done"


def test_the_fallback_is_declared_once_in_the_contract():
    """AC3's table, in the contract beside `STATE_KEYS`: an unmapped `needs_review` resolves to
    `needs_action`'s column, so a deployment that maps nothing keeps today's board. ONE table, not
    six adapters each spelling the fallback. On 1be1835a it does not exist (ImportError)."""
    from openfactory.adapters.tracker.base import FALLS_BACK_TO

    assert FALLS_BACK_TO == {"needs_review": "needs_action"}
