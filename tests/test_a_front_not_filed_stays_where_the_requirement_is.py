"""A front a breakdown did not file stays where the requirement is shown, beside the retry (#564).

WHAT WAS MEASURED. On v0.5.0-rc.1, accepting requirement 66 from the panel broke it into three
fronts: the vet refused the storage front, and the other two were filed. #580 made every door say
which front was not filed and why — but on the panel that sentence is a toast, gone in seconds,
and the requirement's row went on looking like everything had been filed.

THE RULE THIS FILE HOLDS:
  1. the fronts a breakdown leaves out are kept (`ledger.UNFILED`), over what the requirement's
     last breakdown left out — and nothing is kept for one that filed everything, found it all
     existing, or was told the requirement describes what is already built (#182);
  2. the breakdown on the worker keeps them, and a ledger that cannot take them costs no card;
  3. the requirements read carries them, and a ledger that cannot be read costs that column only;
  4. the page shows them on the requirement's row, with the retry, and reloads after a breakdown;
  5. nobody is chased about them: no reader of the product role's loops sees them.
"""

from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace

import pytest

from openfactory.memory import store as loop_store
from openfactory.memory.ledger import KINDS, UNFILED, fold, waiting
from openfactory.product import unfiled
from openfactory.product.authoring import WriteResult
from tests.test_a_refusal_is_not_an_answer import run

T0, T1 = "2026-10-11T10:00:00+00:00", "2026-10-11T11:00:00+00:00"
ACME = SimpleNamespace(name="acme", language="pt-BR")
REFUSED = "a frente «Armazenamento» não foi registrada: a revisão recusou o card (sem critério)."
OUT_OF_TIME = "a frente «Exportação» não foi registrada: o tempo da quebra acabou."


@pytest.fixture
def ledger(monkeypatch) -> SimpleNamespace:
    """The loop ledger as a list — append-only, like the store."""
    book = SimpleNamespace(rows=[])
    monkeypatch.setattr(loop_store, "read", lambda project, **_k: list(book.rows))
    monkeypatch.setattr(loop_store, "write",
                        lambda project, loops, **_k: book.rows.extend(loops) or len(loops))
    return book


def _results(*refused: str, landed: int = 2):
    return ([WriteResult(ok=True, ref=f"#{40 + i}") for i in range(landed)]
            + [WriteResult(ok=False, detail=why) for why in refused])


# ── 1. what is kept ─────────────────────────────────────────────────────────────────────────────

def test_TODAYS_RUN_the_front_the_vet_refused_is_kept_for_the_requirement(ledger):
    kept = unfiled.record(ACME, 66, _results(REFUSED), now=T0)

    assert kept == [REFUSED]
    assert unfiled.open_fronts(ACME) == {66: [REFUSED]}


def test_the_next_breakdown_is_the_truth_now(ledger):
    """Whatever it filed: its own fronts left out replace the last one's, and none clears them."""
    unfiled.record(ACME, 66, _results(REFUSED), now=T0)
    unfiled.record(ACME, 66, _results(OUT_OF_TIME, landed=0), now=T1)
    assert unfiled.open_fronts(ACME) == {66: [OUT_OF_TIME]}

    unfiled.record(ACME, 66, _results(landed=1), now=T1)
    assert unfiled.open_fronts(ACME) == {}
    assert [x.state for x in fold(ledger.rows)] == ["closed", "closed"]


def test_only_a_front_not_filed_is_kept(ledger):
    """A card that landed, one that already existed, and the module's verdict that the requirement
    describes what is already built are not fronts left out."""
    built = SimpleNamespace(ok=False, detail="já está construído", nothing_to_build=True)
    existed = WriteResult(ok=True, ref="#9", existed=True)
    # filed, with the board's own sentence about its placement: a card, not a front left out
    unplaced = WriteResult(ok=True, ref="#10", detail="o quadro recusou a colocação do card")

    assert unfiled.record(ACME, 66, [existed, built, unplaced, *_results()], now=T0) == []
    assert ledger.rows == [], "a breakdown that left nothing out wrote a loop"


def test_each_requirement_keeps_its_own(ledger):
    unfiled.record(ACME, 66, _results(REFUSED), now=T0)
    unfiled.record(ACME, 7, _results(OUT_OF_TIME), now=T0)
    unfiled.record(ACME, 66, _results(), now=T1)

    assert unfiled.open_fronts(ACME) == {7: [OUT_OF_TIME]}


def test_an_unreadable_loop_is_skipped_and_said(ledger, caplog):
    from openfactory.memory.ledger import open_loop

    ledger.rows = [open_loop(UNFILED, "66", owner=unfiled.OWNER, ts=T0,
                             context={"fronts": "{not json"})]
    with caplog.at_level(logging.WARNING):
        assert unfiled.open_fronts(ACME) == {}
    assert "unreadable unfiled-fronts loop" in caplog.text


# ── 2. kept by the breakdown on the worker ──────────────────────────────────────────────────────

@pytest.fixture
def worker(monkeypatch):
    from openfactory.runtime.temporal import activities

    seen = SimpleNamespace(kept=[], raises=None)

    def _record(project, number, results):
        if seen.raises:
            raise seen.raises
        seen.kept.append((number, [getattr(r, "detail", "") for r in results if not r.ok]))
        return []

    monkeypatch.setattr(activities, "ProjectRegistry",
                        lambda: SimpleNamespace(get=lambda _n: ACME))
    monkeypatch.setattr(activities, "_product_break_down",
                        lambda *a, **k: _results(REFUSED))
    monkeypatch.setattr(unfiled, "record", _record)
    return seen


def _inp():
    from openfactory.runtime.temporal.io import ProductBreakdownInput

    return ProductBreakdownInput(project="acme", number=66, actor="ana", asked_for=False)


def test_the_breakdown_keeps_what_it_left_out(worker):
    from openfactory.runtime.temporal.activities import product_role_break_down

    rows = asyncio.run(product_role_break_down(_inp()))

    assert worker.kept == [(66, [REFUSED])]
    assert [r["ref"] for r in rows if r["ok"]] == ["#40", "#41"]


def test_a_ledger_that_cannot_take_it_costs_no_card(worker, caplog):
    from openfactory.runtime.temporal.activities import product_role_break_down

    worker.raises = ConnectionError("the sink is down")
    with caplog.at_level(logging.ERROR):
        rows = asyncio.run(product_role_break_down(_inp()))

    assert [r["ref"] for r in rows if r["ok"]] == ["#40", "#41"]
    assert "OPENFACTORY_PRODUCT_UNFILED_NOT_KEPT" in caplog.text


# ── 3. carried by the requirements read ─────────────────────────────────────────────────────────

def _corpus_module():
    reqs = [SimpleNamespace(number=n, title=f"req {n}", status="accepted", slug=f"r{n}",
                            asked_by="", date="", path=f"{n}.md", has_decisions=False, affects=(),
                            came_from_the_code=False, evidence="", observed_at="")
            for n in (7, 66)]
    corpus = SimpleNamespace(requirements=reqs, summary=lambda: "2 requirements",
                             promises=lambda: reqs, observed=lambda: [], findings=[])
    return SimpleNamespace(context=lambda: SimpleNamespace(available=True, corpus=corpus))


def _read(monkeypatch):
    from openfactory.actions import catalog
    from openfactory.actions.base import PRODUCT, Actor

    monkeypatch.setattr(catalog, "_product_module",
                        lambda _n, **_k: (_corpus_module(), ACME, None))
    out = asyncio.run(catalog._product_requirements(
        project="acme", by=Actor(id="ana", display="Ana", via="panel", admin=True,
                                 scopes=frozenset({PRODUCT}))))
    return {r["number"]: r["unfiled"] for r in out.data["requirements"]}


def test_the_requirements_read_carries_what_each_breakdown_left_out(ledger, monkeypatch):
    unfiled.record(ACME, 66, _results(REFUSED), now=T0)

    assert _read(monkeypatch) == {7: [], 66: [REFUSED]}


def test_a_ledger_that_cannot_be_read_costs_that_column_only(monkeypatch, caplog):
    def _down(_project):
        raise ConnectionError("the sink is down")

    monkeypatch.setattr(unfiled, "open_fronts", _down)
    with caplog.at_level(logging.WARNING):
        assert _read(monkeypatch) == {7: [], 66: []}
    assert "could not be read" in caplog.text


# ── 4. shown on the row ─────────────────────────────────────────────────────────────────────────

def _painted(reqs) -> str:
    return run("nodes['#prodReqs']=node();nodes['#prodCount']=node();paintRequirements();"
               "return nodes['#prodReqs'].innerHTML", "paintRequirements",
               stubs=f"let _prod={{reqs:{json.dumps(reqs)},reqFindings:[]}};")


def _row(n=66, status="accepted", left=()):
    return {"number": n, "title": f"req {n}", "status": status, "unfiled": list(left)}


def test_the_row_says_what_was_not_filed_beside_the_retry():
    html = _painted([_row(left=[REFUSED, OUT_OF_TIME])])

    assert "2 fronts were not filed by the last breakdown" in html, html
    assert "Armazenamento" in html and "Exportação" in html and "Break down…" in html, html


def test_a_row_with_nothing_left_out_says_nothing_of_it():
    html = _painted([_row(left=[])])

    assert "not filed" not in html, html


def test_a_breakdown_from_the_page_reloads_the_rows():
    got = run("await breakDownRequirement(66);return {asked,reloaded}", "breakDownRequirement",
              stubs="let _prod={project:'acme'};let asked=[],reloaded=0;"
                    "function confirm(){return true}"
                    "async function act(n,a){asked.push([n,a.number]);return {ok:true,message:'x'}}"
                    "function loadRequirements(){reloaded++}")

    assert got == {"asked": [["product_break_down", "66"]], "reloaded": 1}, got


# ── 5. nobody is chased about them ──────────────────────────────────────────────────────────────

def test_no_reader_of_the_product_roles_loops_sees_them(ledger):
    """The agenda, the facts the role reads and the sweeps read the role's own loops
    (`owner=followup.OWNER`): a front left out is shown on the row, never chased."""
    from openfactory.product import followup

    unfiled.record(ACME, 66, _results(REFUSED), now=T0)

    assert UNFILED in KINDS
    assert waiting(ledger.rows, owner=followup.OWNER) == []
    assert unfiled.OWNER != followup.OWNER
