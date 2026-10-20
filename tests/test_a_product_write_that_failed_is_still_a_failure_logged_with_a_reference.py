"""A product write that was tried and did not happen is still a failure, logged with a reference (#908).

WHAT THIS HOLDS, BESIDE THE FIX: #908 makes a write the product module declined ON PURPOSE answer
as a refusal (403, 404, 409, 400). The other half of the criterion is that nothing ELSE moves: a
write nobody decided against — the board could not be read, the module raised, a worker too old to
say why — is still `FAILED` (500), and now carries a reference that names its log line, so the
person who reports "it said it could not" hands an operator the line to read.

Measured on this branch before the change (2026-10-20): the board-unreadable close answered 500 /
`failed` with the module's sentence and NO `reference` (`data` had none, and the only log line was
the module's own `OPENFACTORY_PRODUCT_WRITE_FAILED act=close #1` — with nothing a person could
quote); the module raising answered 500 / `raised` with `could not product_withdraw_card: forge
down` and logged `action product_withdraw_card raised for …` with no reference either.

WHAT IS PROVEN HERE, through the real panel (`TestClient(app)`) and the real `ProductModule` on the
local tracker, as the product admin on a named product credential:

  · a board that cannot be read answers 500 `failed`, with the module's sentence (no traceback), and
    a `data.reference` that the row's `OPENFACTORY_PRODUCT_WRITE_FAILED reference=…` line carries;
  · a module that raises answers 500 `raised`, with the message it gives today, and a
    `data.reference` that the `action … raised` line carries;
  · a result from a worker older than `refusal` (its dict names none) is a failure with a
    reference — the rolling-deploy case. It passes before the change on the code and the status;
    it is red only on the reference.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from tests.test_a_card_nobody_started_can_be_closed_and_removed import (  # noqa: F401 — fixtures
    ADMIN,
    _opened_by_product,
    board,
    deployment,
    told,
    tracker,
)
from tests.test_a_product_refusal_answers_as_a_refusal_and_never_500 import (  # noqa: F401
    _post,
    client,
)


def _lines(caplog, *, carrying: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if carrying in r.getMessage()]


def test_a_board_that_cannot_be_read_answers_500_and_its_reference_is_in_the_log_and_the_answer(
        client, deployment, tracker, board, told, monkeypatch, caplog):  # noqa: F811 — fixtures
    """Criterion 2: the forge unreachable is still FAILED, logged with a reference. Before: 500,
    no `data.reference`, no line naming one."""
    from openfactory.product import voice

    ref = _opened_by_product(tracker, board)

    def unreadable(*_a, **_k):
        raise ConnectionError("the tracker did not answer")
    monkeypatch.setattr(type(tracker), "list_tickets", unreadable)

    with caplog.at_level(logging.INFO):
        r = _post(client, "product_withdraw_card", who=ADMIN, number=ref, reason="filed twice")

    said = r.json()
    assert (r.status_code, said["code"]) == (500, "failed"), (r.status_code, said)
    assert said["message"] == voice.card_said("board_unreadable", language="en"), said
    assert "Traceback" not in said["message"] and "did not answer" not in said["message"], said
    reference = said["data"].get("reference")
    assert reference, f"the failure carries no reference to its log line: {said['data']}"
    assert _lines(caplog, carrying=f"OPENFACTORY_PRODUCT_WRITE_FAILED reference={reference}"), (
        f"no log line names reference {reference}: "
        f"{_lines(caplog, carrying='OPENFACTORY_PRODUCT_WRITE_FAILED')}")
    assert tracker.get_ticket(ref).state == "open"


@pytest.fixture
def the_door_cannot_read_the_card(monkeypatch):
    """The card's door (`Ports.seen`) asks a tracker that answers 503 — the forge down for the one
    read the door makes, after every gate before it read the card. Only the door's read fails, so
    what is measured is what the door's "could not see" becomes, not a gate's."""
    from openfactory.lifecycle.ports import Ports

    class Down:
        def get_ticket(self, *_a, **_k):
            raise RuntimeError("HTTP 503 from the forge")

    seen = Ports.seen

    def through_a_tracker_that_is_down(self, card):
        self._tracker = Down()
        return seen(self, card)
    monkeypatch.setattr(Ports, "seen", through_a_tracker_that_is_down)


@pytest.mark.parametrize("row, params", [
    ("product_promote", {"yes": True}),
    ("product_withdraw_card", {"reason": "filed twice"}),
])
def test_a_card_its_door_could_not_read_is_a_failure_with_a_reference_not_a_conflict(
        row, params, client, deployment, tracker, board, told,  # noqa: F811 — the fixtures
        the_door_cannot_read_the_card, caplog):
    """Criterion 2, the door's own read (review of 3a996b0a, point 2): a tracker that cannot be
    read when the card's door looks is the forge unreachable — FAILED, logged with a reference —
    never "the state does not admit it now". Measured on 3a996b0a (2026-10-20), as the product
    admin: both rows answered 409 `conflict`, `refusal=not_waiting`, `reference=None`, where
    620bb577 answered 500 `failed`."""
    ref = _opened_by_product(tracker, board)
    number = {"numbers": ref} if row == "product_promote" else {"number": ref}

    with caplog.at_level(logging.INFO):
        r = _post(client, row, who=ADMIN, **number, **params)

    said = r.json()
    assert (r.status_code, said["code"]) == (500, "failed"), (r.status_code, said)
    assert said["data"].get("refusal") is None, said
    reference = said["data"].get("reference")
    assert reference, f"the failure carries no reference to its log line: {said['data']}"
    assert _lines(caplog, carrying=f"OPENFACTORY_PRODUCT_WRITE_FAILED reference={reference}"), (
        f"no log line names reference {reference}")
    assert tracker.get_ticket(ref).state == "open"


def test_a_board_its_door_could_not_read_is_a_failure_with_a_reference_not_a_conflict(
        client, deployment, tracker, board, monkeypatch, caplog):  # noqa: F811 — the fixtures
    """Criterion 2, the door's other read: a board that answers no columns (`None`, unread) when
    the door places a promoted card is a failure with a reference, not 409 — the second unread
    `Seen` (`lifecycle/ports.py`, "the board could not be read"), which on 3a996b0a answered 409
    `conflict` through the same `moved.refused` → `NOT_WAITING`."""
    ref = _opened_by_product(tracker, board)
    monkeypatch.setattr(type(board), "columns", lambda self: None)

    with caplog.at_level(logging.INFO):
        r = _post(client, "product_promote", who=ADMIN, numbers=ref, yes=True)

    said = r.json()
    assert (r.status_code, said["code"]) == (500, "failed"), (r.status_code, said)
    assert said["message"].startswith("acme's board could not be read"), said
    reference = said["data"].get("reference")
    assert reference, f"the failure carries no reference to its log line: {said['data']}"
    assert _lines(caplog, carrying=f"OPENFACTORY_PRODUCT_WRITE_FAILED reference={reference}")


def test_a_module_that_raises_answers_500_and_its_reference_is_in_the_log_and_the_answer(
        client, deployment, tracker, board, told, monkeypatch, caplog):  # noqa: F811 — fixtures
    """Criterion 2: the module raising is still FAILED (`raised`), logged with a reference. The
    message is pinned as `perform` words it today (`_why`): this change adds the reference, it does
    not re-decide what a raised exception says. Before: no `data.reference`."""
    from openfactory.product.module import ProductModule

    ref = _opened_by_product(tracker, board)

    def raises(self, *_a, **_k):
        raise RuntimeError("forge down")
    monkeypatch.setattr(ProductModule, "withdraw_card", raises)

    with caplog.at_level(logging.INFO):
        r = _post(client, "product_withdraw_card", who=ADMIN, number=ref, reason="filed twice")

    said = r.json()
    assert (r.status_code, said["code"], said["data"]["reason"]) == (500, "failed", "raised"), said
    assert said["message"] == "could not product_withdraw_card: forge down", said
    reference = said["data"].get("reference")
    assert reference, f"the failure carries no reference to its log line: {said['data']}"
    raised = _lines(caplog, carrying="action product_withdraw_card raised")
    assert raised and all(reference in line for line in raised), (reference, raised)


def test_a_result_from_an_older_worker_that_names_no_refusal_is_a_failure(
        deployment, monkeypatch, caplog):  # noqa: F811 — the imported fixture
    """The rolling deploy: a worker older than `WriteResult.refusal` hands back a dict without it.
    That is "nobody decided", so it answers FAILED — never a refusal nobody made — with a reference.
    On this branch before the change: FAILED already (this pins the fallback), no reference."""
    from openfactory import actions
    from openfactory.actions import catalog
    from openfactory.policy.authz import PRODUCT

    class Older:
        async def execute_workflow(self, *_a, **_k):
            return {"ok": False, "detail": "I could not rewrite #7 just now.", "ref": "#7",
                    "url": "", "existed": False}

    async def connected():
        return Older(), None
    monkeypatch.setattr(catalog, "_connected", connected)
    by = actions.Actor(id=ADMIN, display=ADMIN, via="panel", admin=True,
                       scopes=frozenset({PRODUCT}))

    with caplog.at_level(logging.INFO):
        out = asyncio.run(catalog._product_card("refine", project="acme", number="7", by=by,
                                                yes=True))

    assert (out.ok, out.code) == (False, actions.FAILED), out
    assert out.message == "I could not rewrite #7 just now."
    assert "refusal" not in out.data or not out.data["refusal"], out.data
    reference = out.data.get("reference")
    assert reference, f"the failure carries no reference to its log line: {out.data}"
    assert _lines(caplog, carrying=f"OPENFACTORY_PRODUCT_WRITE_FAILED reference={reference}")


@pytest.mark.parametrize("word", ["", "not_yours"])
def test_a_reference_is_minted_only_for_a_failure(word):
    """A refusal is somebody's decision and has a sentence that says it; it carries no reference.
    (`""` — nobody decided — is the failure, and does.)"""
    from types import SimpleNamespace

    from openfactory.actions import catalog

    out = catalog._write_outcome(SimpleNamespace(ok=False, detail="no.", refusal=word),
                                 did="closed #1", project="acme")

    assert bool(out.data.get("reference")) is (word == ""), out.data


def test_a_list_whose_refusals_disagree_is_a_failure_with_a_reference():
    """A list row (`product_promote`, `product_reorder`, `product_break_down`) whose results name
    different refusals is nobody's single decision: a failure, with a reference. The cut where the
    first word answers (`why = next(iter(words), "")`) survived 1578 tests in the review of
    3a996b0a (2026-10-20)."""
    from openfactory.actions import catalog
    from openfactory.product.authoring import NOT_FOUND, NOT_YOURS, WriteResult

    mixed = [WriteResult(ok=False, refusal=NOT_YOURS, detail="a"),
             WriteResult(ok=False, refusal=NOT_FOUND, detail="b")]
    said = catalog._none_done(mixed, "s", did="reorder the backlog", project="p")
    assert (said.code, said.data.get("refusal")) == ("failed", None), said
    assert said.data["reference"]


def test_a_word_this_panel_does_not_know_is_a_failure_and_is_logged(caplog):
    """A refusal word from a worker newer than this panel is answered as a failure and SAID in the
    log, so the drift is seen. Removing `_not_done`'s `OPENFACTORY_PRODUCT_REFUSAL_UNKNOWN` line
    survived 956 tests in the review of 3a996b0a (2026-10-20); only `confirm.py`'s copy was held."""
    from openfactory.actions import catalog

    with caplog.at_level(logging.ERROR):
        said = catalog._none_done([{"ok": False, "refusal": "from_the_future"}], "s",
                                  did="break the requirement down", project="p")
    assert said.code == "failed", said
    assert "OPENFACTORY_PRODUCT_REFUSAL_UNKNOWN" in caplog.text and "from_the_future" in caplog.text


def test_a_promotion_the_cards_door_refuses_by_its_column_answers_409_not_500(
        client, deployment, tracker, board, monkeypatch):  # noqa: F811 — the fixtures
    """The door's other side (#908): a card in a column nobody maps is refused by its state —
    `card_unmapped`, not `unread` — so 409 `not_waiting`, never the 500 of a door that could not
    read. Measured in the review of 1fd403d3 (2026-10-20): `_the_door_said`'s NOT_WAITING branch
    → NOT_REFUSED, and `unread=True` on `card_unmapped`, each survived 3814 tests."""
    from openfactory.contracts.refs import canonical_ref

    ref = _opened_by_product(tracker, board)
    monkeypatch.setattr(type(board), "columns",
                        lambda self: {canonical_ref(ref): "Somewhere nobody maps",
                                      str(ref): "Somewhere nobody maps"})

    r = _post(client, "product_promote", who=ADMIN, numbers=ref, yes=True)

    said = r.json()
    assert (r.status_code, said["code"]) == (409, "conflict"), (r.status_code, said)
    assert said["data"]["refusal"] == "not_waiting", said
    assert "Somewhere nobody maps" in said["message"], said


@pytest.mark.parametrize("row", ["product_promote", "product_reorder"])
def test_a_card_whose_slice_could_not_be_asked_is_a_failure_with_a_reference(
        row, client, deployment, tracker, board, monkeypatch):  # noqa: F811 — the fixtures
    """#752's `holds` answering None — the board could not say whose card it is — is a failure,
    500 with a reference, never 409. Measured in the review of 1fd403d3 (2026-10-20): the
    `unreachable` arm → NOT_WAITING survived 3814 tests in promote and in reorder."""
    first, second = _opened_by_product(tracker, board), _opened_by_product(tracker, board)
    monkeypatch.setattr(type(board), "columns", lambda self: {}, raising=True)
    monkeypatch.setattr(type(board), "holds", lambda self, number: None, raising=False)

    numbers = first if row == "product_promote" else f"{second},{first}"
    r = _post(client, row, who=ADMIN, numbers=numbers, yes=True)

    said = r.json()
    assert (r.status_code, said["code"]) == (500, "failed"), (r.status_code, said)
    assert said["data"].get("reference"), said
