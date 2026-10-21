"""A merge gate's answer is a refusal or a failure as it is, read off one table (#908).

`_the_gate_said` (`product/module.py`) decides, for `send_back` and `accept_change`, which word a
merge gate answers is the person's to wait out (`NOT_WAITING`, 409), which is theirs to refuse
(`NOT_YOURS`, 403), and which is a write that was tried and did not happen (`NOT_REFUSED`, 500 with
a reference). Measured in the review of 3a996b0a (2026-10-20): moving `accept.UNRECORDED` or
`adjust.UNREACHABLE` into the waiting set — an acceptance that could not be written answering 409 —
survived 1229 tests. Each word is pinned here, and every word a gate can answer must be in the
table, so a new member of `adjust.WHY` is classified before it ships rather than raising.
"""

import pytest

from openfactory.product import accept, adjust
from openfactory.product.authoring import NOT_REFUSED, NOT_WAITING, NOT_YOURS
from openfactory.product.module import _the_gate_said

EXPECTED = {"not_yours": NOT_YOURS,
            adjust.NOT_WAITING: NOT_WAITING, adjust.WORKING: NOT_WAITING,
            adjust.DEAF: NOT_WAITING, adjust.SPENT: NOT_WAITING,
            accept.UNTRIED: NOT_WAITING, accept.MOVED: NOT_WAITING,
            adjust.UNREACHABLE: NOT_REFUSED, accept.UNRECORDED: NOT_REFUSED}


def test_every_word_a_gate_can_answer_is_classified_here():
    assert set(adjust.WHY) | {accept.UNTRIED, accept.MOVED, accept.UNRECORDED} <= set(EXPECTED)


@pytest.mark.parametrize("why", sorted(EXPECTED))
def test_a_gate_word_is_a_refusal_or_a_failure_as_it_is(why):
    assert _the_gate_said(why, ref="#7", detail="said").refusal == EXPECTED[why]
