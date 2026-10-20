"""A product write the role refuses on purpose answers as a refusal, never as a 500 (#908).

WHAT WAS WRONG: `_write_outcome` (`actions/catalog.py`) rendered every `WriteResult` with
`ok=False` as `refused(FAILED, …)`, and `/api/act/{name}` maps FAILED to 500. So a sentence the
product module composed on purpose — "only the person who asked for #1, or someone with permission
to approve, can close or remove it", "#1 is already closed" — reached a person as an internal
error. Measured on 620bb577 (2026-10-20): `product_withdraw_card` by a named product-scoped
stranger answered HTTP 500, `code='failed'`, with the module's own sentence as the message.

WHAT IS PROVEN HERE, through the real panel (`TestClient(app)`), the real `ProductModule` and the
local tracker, with each person on their own named product credential (`OPENFACTORY_PRODUCT_TOKENS`):

  · a person who neither asked for the card nor administers the product is refused 403 `denied`,
    with the module's sentence unchanged, for a close and for a removal, and nothing is written;
  · a card that is already closed answers 409 `conflict`, with the module's sentence;
  · the rows that render a LIST of results by hand — `product_promote`, `product_reorder`,
    `product_break_down` — answer the refusal every result names, not 500: measured on 620bb577
    (2026-10-20), a stranger's promote and reorder, and a breakdown whose every front the role
    declined, each answered 500 / `failed`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.test_a_card_nobody_started_can_be_closed_and_removed import (  # noqa: F401 — fixtures
    ADMIN,
    ASKER,
    STRANGER,
    _audit,
    _opened_by_product,
    board,
    deployment,
    told,
    tracker,
)

#: One fictitious credential per person, as `OPENFACTORY_PRODUCT_TOKENS` names them
#: (`token:id:display`): each resolves to that person, scoped to the product area.
CREDENTIAL = {STRANGER: "fictitious-stranger-credential-5120",
              ADMIN: "fictitious-admin-credential-7731",
              ASKER: "fictitious-asker-credential-3307"}


@pytest.fixture
def client(deployment, monkeypatch):  # noqa: F811 — the imported fixture
    """The panel, with every person here on their own named product credential."""
    from openfactory.identity.local import CLOSING_ENVS, PRODUCT_PEOPLE_ENV

    monkeypatch.delenv("OPENFACTORY_IDENTITY", raising=False)
    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(PRODUCT_PEOPLE_ENV, ",".join(
        f"{secret}:{who}:{who}" for who, secret in CREDENTIAL.items()))
    from openfactory.api.app import app

    return TestClient(app)


def _post(client, row: str, *, who: str, **params):
    return client.post(f"/api/act/{row}", headers={"authorization": f"Bearer {CREDENTIAL[who]}"},
                       json={"params": {"project": "acme", **params}})


def test_a_person_who_neither_asked_for_the_card_nor_administers_it_is_refused_403_with_the_modules_sentence(  # noqa: E501
        client, deployment, tracker, board, told):  # noqa: F811 — the imported fixtures
    """Criterion 1: a `WriteResult` the module refuses on purpose ("not yours") maps to a refusal
    code, never to FAILED. On 620bb577 this answered 500 / `failed` with the same sentence."""
    from openfactory.contracts.refs import canonical_ref
    from openfactory.product import voice

    ref = _opened_by_product(tracker, board)
    sentence = voice.card_withdrawn_result(ref=canonical_ref(ref), how="not_yours",
                                           language="en", approvers=[ADMIN])

    for remove in (False, True):
        r = _post(client, "product_withdraw_card", who=STRANGER, number=ref,
                  reason="not mine but still", remove=remove)
        said = r.json()
        assert (r.status_code, said["code"]) == (403, "denied"), (remove, r.status_code, said)
        assert said["message"] == said["detail"] == sentence, (remove, said)

    assert tracker.get_ticket(ref).state == "open", "the card was closed"
    assert _audit(ref) is None, "the card was removed"
    assert told == [], "the conversation was told something happened"


def test_a_card_already_closed_answers_409_with_the_modules_sentence(
        client, deployment, tracker, board, told):  # noqa: F811 — the imported fixtures
    """Criterion 1: "already closed" is the module's answer, a conflict with the card's state, not
    a breakage. Driven through the card's own control: its board gate (`_opened_by`,
    `_withdraw_refusal`) lets a closed card through to the module — measured on 620bb577, the second
    `product_withdraw_card` reached `_close_one` and answered 500 / `failed` with this sentence."""
    from openfactory.contracts.refs import canonical_ref
    from openfactory.product import voice

    ref = _opened_by_product(tracker, board)
    first = _post(client, "product_withdraw_card", who=ADMIN, number=ref, reason="filed twice")
    assert first.status_code == 200 and first.json()["ok"], first.text
    assert tracker.get_ticket(ref).state == "closed"

    r = _post(client, "product_withdraw_card", who=ADMIN, number=ref, reason="filed twice")

    said = r.json()
    sentence = voice.card_said("already_closed", number=canonical_ref(ref), language="en")
    assert (r.status_code, said["code"]) == (409, "conflict"), (r.status_code, said)
    assert said["message"] == said["detail"] == sentence, said


def test_a_promotion_the_person_may_not_make_answers_403_not_500(
        client, deployment, tracker, board):  # noqa: F811 — the imported fixtures
    """Criterion 1, second instance: `product_promote` leaves `may_act` to `ProductModule.promote`,
    whose "not yours" came back as a one-result list the row rendered as FAILED — measured on
    620bb577, a product-scoped stranger's promote answered HTTP 500 / `failed`."""
    from openfactory.product.module import unauthorized_message

    ref = _opened_by_product(tracker, board)
    r = _post(client, "product_promote", who=STRANGER, numbers=ref, yes=True)

    said = r.json()
    assert (r.status_code, said["code"]) == (403, "denied"), (r.status_code, said)
    assert said["message"] == unauthorized_message(deployment), said
    assert said["data"]["refusal"] == "not_yours", said


def test_a_promotion_of_a_card_outside_the_projects_slice_answers_409_with_the_modules_sentence(
        client, deployment, tracker, board, monkeypatch):  # noqa: F811 — the imported fixtures
    """Criterion 1, the instance #752 added after this branch was cut: `ProductModule.promote`
    refuses by name a card its board says is another project's (`holds` → False) — a conflict
    with where the card is, not a breakage. Measured on 3a996b0a merged with bb929e49
    (2026-10-20): the site named no `refusal=`, and the row answered 500 / `failed`, with a
    reference and an `OPENFACTORY_PRODUCT_WRITE_FAILED` line, for "… is not in acme's slice"."""
    from openfactory.contracts.refs import canonical_ref
    from openfactory.product.voice import board_move_said

    ref = _opened_by_product(tracker, board)
    # A shared board's slice, as Jira's `scope_jql` reads it: the batch read does not return the
    # card, and the board, asked by key, says it is not this project's
    monkeypatch.setattr(type(board), "columns", lambda self: {}, raising=True)
    monkeypatch.setattr(type(board), "holds", lambda self, number: False, raising=False)

    r = _post(client, "product_promote", who=ADMIN, numbers=ref, yes=True)

    said = r.json()
    assert (r.status_code, said["code"]) == (409, "conflict"), (r.status_code, said)
    assert said["data"]["refusal"] == "not_waiting", said
    assert said["message"] == board_move_said("outside_the_slice", ref=canonical_ref(ref),
                                              project="acme", language="en"), said


def test_a_reorder_of_a_card_outside_the_projects_slice_answers_409_with_the_modules_sentence(
        client, deployment, tracker, board, monkeypatch):  # noqa: F811 — the imported fixtures
    """The same instance in `ProductModule.reorder` (#752 asks `holds` per card there): another
    project's card is refused by name, 409 with the module's sentence — on 3a996b0a merged with
    bb929e49 (2026-10-20) the site named no `refusal=` and the row answered 500 / `failed`."""
    from openfactory.contracts.refs import canonical_ref
    from openfactory.product.voice import board_move_said

    first, second = _opened_by_product(tracker, board), _opened_by_product(tracker, board)
    monkeypatch.setattr(type(board), "holds", lambda self, number: False, raising=False)

    r = _post(client, "product_reorder", who=ADMIN, numbers=f"{second},{first}", yes=True)

    said = r.json()
    assert (r.status_code, said["code"]) == (409, "conflict"), (r.status_code, said)
    assert said["data"]["refusal"] == "not_waiting", said
    assert said["message"] == board_move_said("outside_the_slice", ref=canonical_ref(second),
                                              project="acme", language="en"), said


def test_a_reorder_the_person_may_not_make_answers_403_not_500(
        client, deployment, tracker, board):  # noqa: F811 — the imported fixtures
    """Criterion 1, second instance: `product_reorder` rendered `ProductModule.reorder`'s "not
    yours" as FAILED — measured on 620bb577, HTTP 500 / `failed` for a product-scoped stranger."""
    from openfactory.product.module import unauthorized_message

    first, second = _opened_by_product(tracker, board), _opened_by_product(tracker, board)
    r = _post(client, "product_reorder", who=STRANGER, numbers=f"{second},{first}", yes=True)

    said = r.json()
    assert (r.status_code, said["code"]) == (403, "denied"), (r.status_code, said)
    assert said["message"] == unauthorized_message(deployment), said
    assert said["data"]["refusal"] == "not_yours", said


def test_a_breakdown_whose_every_front_was_refused_answers_that_refusal(
        client, deployment, monkeypatch):  # noqa: F811 — the imported fixture
    """Criterion 1, second instance: `product_break_down` answered FAILED whenever nothing was
    filed, even when the worker's every front named the same deliberate refusal ("requirement 7 no
    longer stands") — measured on 620bb577, HTTP 500 / `failed`. The worker is a stand-in that
    hands back the rows `product_role_break_down` builds, `refusal` included (task 8's boundary)."""
    from types import SimpleNamespace

    from openfactory.actions import catalog
    from openfactory.product import voice

    class _Module:
        """Past the row's own gates: the corpus is readable and 7 names a promise."""

        def context(self):
            promise = SimpleNamespace(is_promise=True)
            return SimpleNamespace(available=True, reason="",
                                   corpus=SimpleNamespace(by_number=lambda n: promise))

    detail = voice.breakdown_said("retired", number=7, language="en")
    front = {"ok": False, "ref": "", "url": "", "existed": False, "detail": detail,
             "refusal": "not_waiting"}

    class _Engine:
        async def execute_workflow(self, name, inp, **_kw):
            return [dict(front), dict(front)]

    async def _connected():
        return _Engine(), None

    monkeypatch.setattr(catalog, "_product_module", lambda name, by=None: (
        _Module(), deployment, None))
    monkeypatch.setattr(catalog, "_connected", _connected)
    monkeypatch.setattr(catalog, "_where_it_was_written", lambda project, number: ("", ""))

    r = _post(client, "product_break_down", who=ADMIN, number="7", yes=True)

    said = r.json()
    assert (r.status_code, said["code"]) == (409, "conflict"), (r.status_code, said)
    assert detail.rstrip(".") in said["message"], said
    assert said["data"]["refusal"] == "not_waiting", said


def test_a_refusal_in_a_portuguese_project_answers_403_with_the_modules_portuguese_sentence_unchanged(  # noqa: E501
        client, deployment, tracker, board, told):  # noqa: F811 — the imported fixtures
    """Criterion 1, in the project's own language: the code is chosen from the module's word, never
    from its sentence, so a pt-BR project's refusal is the same 403 `denied`, and its sentence
    ("só quem pediu o #1 … pode fechá-lo ou removê-lo") travels byte for byte. On 620bb577 this
    answered 500 / `failed` with that sentence, as the English one did."""
    from openfactory.contracts.refs import canonical_ref
    from openfactory.product import voice
    from openfactory.registry import ProjectRegistry

    ProjectRegistry().set_language("acme", "pt-BR")
    ref = _opened_by_product(tracker, board)
    sentence = voice.card_withdrawn_result(ref=canonical_ref(ref), how="not_yours",
                                           language="pt-BR", approvers=[ADMIN])
    assert sentence != voice.card_withdrawn_result(ref=canonical_ref(ref), how="not_yours",
                                                   language="en", approvers=[ADMIN])

    r = _post(client, "product_withdraw_card", who=STRANGER, number=ref, reason="não é meu")

    said = r.json()
    assert (r.status_code, said["code"]) == (403, "denied"), (r.status_code, said)
    assert said["message"] == said["detail"] == sentence, said
    assert said["data"]["refusal"] == "not_yours", said
    assert tracker.get_ticket(ref).state == "open", "the card was closed"


#: A worker newer than this panel, mid-upgrade: one front landed, the other names a refusal word
#: this panel's `authoring.REFUSALS` does not hold.
_A_WORD_FROM_A_NEWER_WORKER = "not_yet_a_word_this_panel_knows"
_FILED_AND_ONE_NEWER = [
    {"ok": True, "ref": "acme#41", "url": "", "existed": False, "detail": "", "refusal": ""},
    {"ok": False, "ref": "", "url": "", "existed": False, "detail": "the role held this one back.",
     "refusal": _A_WORD_FROM_A_NEWER_WORKER},
]


def _a_newer_worker(monkeypatch, deployment):  # noqa: F811 — the imported fixture
    """The breakdown's engine hands back `_FILED_AND_ONE_NEWER`; the row's own gates pass."""
    from types import SimpleNamespace

    from openfactory.actions import catalog

    class _Module:
        def context(self):
            promise = SimpleNamespace(is_promise=True)
            return SimpleNamespace(available=True, reason="",
                                   corpus=SimpleNamespace(by_number=lambda n: promise))

    class _Engine:
        async def execute_workflow(self, name, inp, **_kw):
            return [dict(row) for row in _FILED_AND_ONE_NEWER]

    async def _connected():
        return _Engine(), None

    monkeypatch.setattr(catalog, "_product_module", lambda name, by=None: (
        _Module(), deployment, None))
    monkeypatch.setattr(catalog, "_connected", _connected)
    monkeypatch.setattr(catalog, "_where_it_was_written", lambda project, number: ("", ""))


def test_a_breakdown_from_a_newer_worker_whose_front_names_an_unknown_refusal_still_answers_what_landed(  # noqa: E501
        client, deployment, monkeypatch, caplog):  # noqa: F811 — the imported fixture
    """Criterion 1, the rolling upgrade the other way round (human decision 2026-10-20, option A):
    a worker NEWER than the panel hands back a front whose `refusal` this panel does not know.
    `confirm.breakdown_outcome` rebuilt a `WriteResult` from that dict, and `WriteResult`'s check
    raised `ValueError` — measured on this branch at 37d4ebf3: HTTP 500, `reason="raised"`, for a
    breakdown whose other front HAD landed. An unknown word is read as nobody's decision (as
    `_not_done` reads it), logged as `OPENFACTORY_PRODUCT_REFUSAL_UNKNOWN`, and the landed front
    is said."""
    import logging

    _a_newer_worker(monkeypatch, deployment)

    with caplog.at_level(logging.ERROR):
        r = _post(client, "product_break_down", who=ADMIN, number="7", yes=True)

    said = r.json()
    assert (r.status_code, said["ok"]) == (200, True), (r.status_code, said)
    assert "acme#41" in said["message"], said
    unknown = [rec.getMessage() for rec in caplog.records
               if "OPENFACTORY_PRODUCT_REFUSAL_UNKNOWN" in rec.getMessage()]
    assert unknown and _A_WORD_FROM_A_NEWER_WORKER in unknown[0], caplog.text


def test_an_acceptance_whose_breakdown_came_from_a_newer_worker_still_says_what_landed(
        deployment, monkeypatch):  # noqa: F811 — the imported fixture
    """The acceptance's door (`_with_the_work_filed`) renders the same rows through the same
    `_breakdown_said`: before option A it raised inside the acceptance's courtesy — after the
    promise was written — measured on this branch at 37d4ebf3 as a `ValueError` out of
    `WriteResult.__post_init__`."""
    import asyncio

    from openfactory.actions import catalog
    from openfactory.actions.base import done
    from tests.test_the_confirmation_executor import _actor

    _a_newer_worker(monkeypatch, deployment)
    accepted = done("accepted requirement 7.", project="acme", number=7)

    out = asyncio.run(catalog._with_the_work_filed(accepted, project="acme", number=7,
                                                   by=_actor(), proj=deployment))

    assert out.ok and out.message.startswith("accepted requirement 7."), out.message
    assert "acme#41" in out.message, out.message
