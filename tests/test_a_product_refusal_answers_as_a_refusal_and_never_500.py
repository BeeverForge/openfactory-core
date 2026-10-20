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
  · a card that is already closed answers 409 `conflict`, with the module's sentence.
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
