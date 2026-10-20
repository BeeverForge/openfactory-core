"""Every refusal the product module can name answers its own code over `/api/act`, and none is 500 (#908).

WHAT WAS WRONG: `_write_outcome` (`actions/catalog.py`) rendered every `WriteResult` with `ok=False`
as `refused(FAILED, …)`, which `/api/act/{name}` answers as HTTP 500. Measured on 620bb577
(2026-10-20): `product_withdraw_card` by a product-scoped stranger answered 500 / `failed` with the
module's own sentence "only the person who asked for #1 … can close or remove it".

THE FAMILY IS READ, NOT LISTED. The reasons are the module's vocabulary
(`openfactory.product.authoring.REFUSALS`); the rows are every catalogue row whose runner reaches
`_write_outcome` or `_none_done` inside `catalog.py`, derived from its call graph with the action
layer's own walk (`tests/test_the_action_layer.py`). What this file states by hand is only what a
reader cannot derive: how to get each row past its own checks to the module (`ROWS`), and the code
each reason answers (`DECIDED`, the decision of #908's Q1) — and both are held to the derived sets,
so a row or a reason added tomorrow fails here until it is driven and decided.

EACH CASE drives the real panel (`TestClient(app)`) on a named operator credential, with the
module replaced by one whose called method refuses with that reason and a sentence (two of them
for the rows that render a list; the worker's dict, or two, for the three rows the worker runs),
and asserts the status, the code, the sentence unchanged, and the module's word in
`data.refusal`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from openfactory.actions import catalog
from openfactory.product.authoring import REFUSALS, WriteResult
from tests.test_a_card_nobody_started_can_be_closed_and_removed import (  # noqa: F401 — fixtures
    _opened_by_product,
    board,
    deployment,
    tracker,
)
from tests.test_the_action_layer import _catalog_functions, _reachable_from

#: The code each reason of the module answers — #908's Q1, as the plan's default decided it. The
#: catalogue's own table must say the same (`test_the_catalogue_maps_each_reason_as_decided`).
DECIDED = {"not_yours": "denied", "not_found": "not_found", "not_waiting": "conflict",
           "already_closed": "conflict", "already_there": "conflict", "not_valid": "invalid"}

#: A card the product role opened, on the local board, in Backlog: what a row that reads the board
#: before it asks the module (the card's controls, the floor's close and removal) needs.
CARD = "<a product card>"
#: The worker runs these two rows' module call; the panel reads back the activity's dict.
WORKER = "<the worker>"
#: The breakdown runs on the worker too, and hands back one dict per front: the panel reads the
#: module only for its own gates (`context`), then renders the list through `_none_done`.
BREAKDOWN = "<the worker's breakdown>"
#: The module methods that answer a LIST of results, of which the row renders none made.
LISTS = {"promote", "reorder"}

#: Per row: the parameters that get it past its own checks, and the module method it then calls.
ROWS: dict[str, tuple[dict[str, object], str]] = {
    "product_propose": ({"answer": {"draft": {"title": "A monthly report"}}, "yes": True},
                        "propose"),
    "product_accept": ({"number": "7", "yes": True}, "accept"),
    "product_drop": ({"number": "7", "reason": "not needed", "yes": True}, "drop"),
    "product_close_card": ({"number": "7", "yes": True}, "close_card"),
    "product_correct_card": ({"number": "7", "text": "Lock it", "yes": True}, "correct_card"),
    "product_adjust": ({"number": "7", "instruction": "make it monthly"}, "send_back"),
    "product_accept_change": ({"number": "7"}, "accept_change"),
    "product_record_decision": ({"number": "7", "decision": "monthly", "yes": True},
                                "record_decision"),
    "product_confirm_capability": ({"capability": "billing", "yes": True},
                                   "confirm_capability"),
    "product_note_fact": ({"term": "closing", "body": "it is monthly", "yes": True},
                          "note_fact"),
    "product_file_defect": ({"restated": "the report is weekly", "yes": True}, "file_defect"),
    "product_file_ticket": ({"title": "A monthly report", "yes": True}, "file_ticket"),
    "product_refine_card": ({"number": "7", "yes": True}, WORKER),
    "product_align_card": ({"number": "7", "requirement": "3", "yes": True}, WORKER),
    "product_withdraw_card": ({"number": CARD, "reason": "filed twice"}, "withdraw_card"),
    "card_close": ({"issue": CARD, "reason": "filed twice"}, "withdraw_card"),
    "card_remove": ({"issue": CARD, "reason": "filed twice"}, "withdraw_card"),
    "product_promote": ({"numbers": "7", "yes": True}, "promote"),
    "product_reorder": ({"numbers": "7,8", "yes": True}, "reorder"),
    "product_break_down": ({"number": "7", "yes": True}, BREAKDOWN),
}

#: One fictitious operator — named, unscoped — so every row above, floor or product, is reachable.
OPERATOR = "fictitious-operator-credential-6604"


#: The two renderings of a module's not-ok result: one `WriteResult` (`_write_outcome`), and a list
#: of them of which none was made (`_none_done`: promote, reorder, the breakdown). A row reaching
#: either is in the family — the second joined after the review of PR #970 found a future list row
#: would not be driven.
_RENDERINGS = {"_write_outcome", "_none_done"}


def _rendering_a_write() -> set[str]:
    """Every catalogue row whose runner reaches `_write_outcome` or `_none_done`, by the action
    layer's own walk."""
    functions = _catalog_functions()
    return {name for name, spec in catalog.CATALOG.items()
            if _RENDERINGS & _reachable_from(spec.run.__name__, functions)}


@pytest.fixture
def client(deployment, monkeypatch):  # noqa: F811 — the imported fixture
    from openfactory.identity.local import CLOSING_ENVS, PEOPLE_ENV

    monkeypatch.delenv("OPENFACTORY_IDENTITY", raising=False)
    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(PEOPLE_ENV, f"{OPERATOR}:op-1:Operator")
    from openfactory.api.app import app

    return TestClient(app)


class _Refusing:
    """A product module whose every write refuses with one reason and one sentence, and which
    records the method the row called — so the refusal is known to come from where `ROWS` says."""

    def __init__(self, result):
        self.result, self.called = result, []

    def __getattr__(self, method: str):
        if method.startswith("__"):
            raise AttributeError(method)

        def write(*_args, **_kwargs):
            self.called.append(method)
            return [self.result, self.result] if method in LISTS else self.result
        return write


class _PastTheGates:
    """The breakdown row's module: its own gates pass — the corpus is readable and 7 names a
    promise — and nothing else is asked of it here; the fronts come from the worker."""

    def context(self):
        from types import SimpleNamespace

        promise = SimpleNamespace(is_promise=True)
        return SimpleNamespace(available=True, reason="",
                               corpus=SimpleNamespace(by_number=lambda n: promise))


class _Worker:
    """The durable engine's client, handing back the activity's dict as the worker would."""

    def __init__(self, answer: dict):
        self.answer, self.called = answer, []

    async def execute_workflow(self, workflow, *_args, **_kwargs):
        if workflow == "ProductBreakdownWorkflow":
            self.called.append(BREAKDOWN)
            return [dict(self.answer), dict(self.answer)]
        self.called.append(WORKER if workflow == "ProductCardWorkflow" else workflow)
        return dict(self.answer)


def test_every_row_that_renders_a_write_is_in_the_table_this_family_drives():
    """A row added tomorrow that renders a module's `WriteResult` fails here until it is driven."""
    derived = _rendering_a_write()
    assert derived, "the walk found no row reaching `_write_outcome` — the family is empty"
    assert set(ROWS) == derived, (
        f"driven but not rendering a write: {sorted(set(ROWS) - derived)}; "
        f"rendering a write and not driven: {sorted(derived - set(ROWS))}")


def test_every_refusal_reason_names_a_code_and_none_names_failed():
    """The catalogue's reason → code table covers exactly the module's vocabulary, and no reason is
    answered as a failure or an outage: a refusal is somebody's decision, never a breakage."""
    from openfactory import actions

    table = catalog._REFUSAL_CODE
    assert set(table) == set(REFUSALS), (sorted(table), sorted(REFUSALS))
    assert not {code for code in table.values() if code in (actions.FAILED, actions.UNAVAILABLE)}
    assert set(DECIDED) == set(REFUSALS), (
        f"a reason with no decided code: {sorted(set(REFUSALS) - set(DECIDED))}")


def test_the_catalogue_maps_each_reason_as_decided():
    assert dict(catalog._REFUSAL_CODE) == DECIDED


@pytest.mark.parametrize("reason", sorted(REFUSALS))
@pytest.mark.parametrize("row", sorted(ROWS))
def test_each_refusal_reason_answers_its_code_and_the_modules_sentence_on_every_row_that_renders_a_write(  # noqa: E501
        client, deployment, tracker, board, monkeypatch, row, reason):  # noqa: F811 — fixtures
    from openfactory.api.app import _STATUS

    params, method = ROWS[row]
    sentence = f"the module declined {row}: {reason.replace('_', ' ')}."
    if CARD in params.values():
        ref = _opened_by_product(tracker, board)
        params = {k: (ref if v == CARD else v) for k, v in params.items()}

    said_as = sentence
    if method in (WORKER, BREAKDOWN):
        called = _Worker({"ok": False, "detail": sentence, "ref": "", "url": "",
                          "existed": False, "refusal": reason})

        async def connected():
            return called, None
        monkeypatch.setattr(catalog, "_connected", connected)
        if method == BREAKDOWN:
            monkeypatch.setattr(catalog, "_product_module", lambda name, by=None: (
                _PastTheGates(), deployment, None))
            monkeypatch.setattr(catalog, "_where_it_was_written", lambda project, number: ("", ""))
            # the row asks `may_act` itself, before the worker: the operator administers the floor,
            # not acme's product — what is driven here is the rendering, not that gate
            from openfactory.product import module as product_module
            monkeypatch.setattr(product_module, "may_act", lambda *_a, **_k: True)
            # the row heads the fronts' sentence with what was not filed (`_product_break_down`)
            said_as = f"nothing was filed for requirement 7: {sentence.rstrip('.')}."
    else:
        called = _Refusing(WriteResult(ok=False, refusal=reason, detail=sentence))
        the_real = catalog._product_module

        def module_of(name, *, by=None):
            _module, project, bad = the_real(name, by=by)
            return (None if bad else called), project, bad
        monkeypatch.setattr(catalog, "_product_module", module_of)

    r = client.post(f"/api/act/{row}", headers={"authorization": f"Bearer {OPERATOR}"},
                    json={"params": {"project": "acme", **params}})

    said = r.json()
    assert called.called == [method], (row, called.called, r.status_code, said)
    assert r.status_code != 500, (row, reason, said)
    expected = DECIDED[reason]
    assert (r.status_code, said["code"]) == (_STATUS[expected], expected), (row, reason, said)
    assert said["message"] == said["detail"] == said_as, said
    assert said["data"]["refusal"] == reason, said["data"]
