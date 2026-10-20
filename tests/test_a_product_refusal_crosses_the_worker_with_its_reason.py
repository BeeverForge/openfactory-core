"""A product refusal crosses the worker with its reason, or the panel cannot tell it from a failure.

WHAT WAS WRONG (#908): `refine` and `align` run on the worker (`product_role_card`), and so does a
breakdown (`product_role_break_down`). Each activity hands back the module's `WriteResult` as a
HAND-PICKED dict — `ok`, `detail`, `ref`, `url`, `existed` (and `nothing_to_build`) — and the panel
rebuilds it from that dict (`_product_card`'s `SimpleNamespace`, `actions/catalog.py`). A field not
in the dict never reaches `_write_outcome`: on this branch before this file's change, the module's
`refusal=NOT_YOURS` on a refined card arrived at the panel as no refusal at all — a failure, 500.

WHAT IS PROVEN HERE, by calling each activity function directly (outside an activity context, as
`product_role_break_down` allows through `activity.in_activity()`), with the module patched:

  · the card activity hands back the module's refusal word, for both verbs;
  · the breakdown activity hands back each front's own refusal word, and `""` for a front nobody
    refused (a failure stays a failure);
  · an unknown verb, which the activity refuses itself, names `not_valid`;
  · the conversation's rebuild of a breakdown's dicts (`confirm.breakdown_outcome`) keeps the word.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from openfactory.product.authoring import (
    NOT_REFUSED,
    NOT_VALID,
    NOT_WAITING,
    NOT_YOURS,
    WriteResult,
)

ACME = SimpleNamespace(name="acme", language="en")
NOT_YOURS_SENTENCE = "only the person who asked for #7, or someone who may approve, can refine it."


@pytest.fixture
def worker(monkeypatch):
    """The activities, on a registry that knows `acme`, with nothing kept and nobody told."""
    from openfactory.product import unfiled
    from openfactory.runtime.temporal import activities

    monkeypatch.setattr(activities, "ProjectRegistry",
                        lambda: SimpleNamespace(get=lambda _n: ACME))
    monkeypatch.setattr(unfiled, "record", lambda *_a, **_k: [])
    return activities


@pytest.mark.parametrize("verb", ["refine", "align"])
def test_the_card_activity_hands_back_the_modules_refusal(worker, monkeypatch, verb):
    """Criterion "the boundary": the refusal the module set on the card is in the activity's dict.
    Before: the dict had no `refusal` key — `KeyError: 'refusal'`."""
    from openfactory.runtime.temporal.io import ProductCardInput

    monkeypatch.setattr(worker, "_product_card_write", lambda _p, _inp: WriteResult(
        ok=False, refusal=NOT_YOURS, detail=NOT_YOURS_SENTENCE))

    out = asyncio.run(worker.product_role_card(
        ProductCardInput(project="acme", number="7", verb=verb, requirement=3, actor="stranger")))

    assert out["refusal"] == "not_yours", out
    assert (out["ok"], out["detail"]) == (False, NOT_YOURS_SENTENCE)


def test_the_card_activity_names_an_unknown_verb_not_valid(worker):
    """The activity's own refusal of a verb it does not run is a refusal, not a failure."""
    from openfactory.runtime.temporal.io import ProductCardInput

    out = asyncio.run(worker.product_role_card(
        ProductCardInput(project="acme", number="7", verb="rewrite")))

    assert (out["ok"], out["refusal"]) == (False, NOT_VALID), out
    assert "unknown card verb 'rewrite'" in out["detail"]


def test_the_breakdown_activity_hands_back_each_fronts_refusal(worker, monkeypatch):
    """Each front's word, in order; a front nobody refused carries `""` — still a failure."""
    from openfactory.runtime.temporal.io import ProductBreakdownInput

    monkeypatch.setattr(worker, "_product_break_down", lambda *_a, **_k: [
        WriteResult(ok=True, ref="#40"),
        WriteResult(ok=False, refusal=NOT_WAITING, detail="the requirement is retired."),
        WriteResult(ok=False, detail="I could not push the card."),
        SimpleNamespace(ok=False, detail="an older module's result, with no field at all"),
    ])

    rows = asyncio.run(worker.product_role_break_down(
        ProductBreakdownInput(project="acme", number=3, actor="ana")))

    assert [r["refusal"] for r in rows] == ["", "not_waiting", NOT_REFUSED, NOT_REFUSED], rows


def test_the_conversations_rebuild_of_a_breakdowns_rows_keeps_the_refusal(monkeypatch):
    """`breakdown_outcome` rebuilds a `WriteResult` from each dict, keeping only the fields the
    dataclass knows; the refusal is one of them, so it reaches the reply's renderer."""
    from openfactory.product import confirm

    seen = []
    monkeypatch.setattr(confirm, "_breakdown_reply",
                        lambda results, *_a, **_k: seen.extend(results) or "said")

    confirm.breakdown_outcome([{"ok": False, "detail": "retired", "ref": "", "url": "",
                                "existed": False, "nothing_to_build": False,
                                "refusal": NOT_WAITING}], number=3, project=ACME)

    assert [r.refusal for r in seen] == [NOT_WAITING]
