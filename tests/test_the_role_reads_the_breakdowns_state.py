"""The role reads each agreed requirement's breakdown, and a breakdown the panel started is told
where the requirement was written (#563, ADR-0051 D18, slice 18e).

WHAT WAS MEASURED. On v0.5.0-rc.1 one requirement got three cards through three doors. One of
them was a card the role itself drafted for an accepted requirement: nothing it read said that a
breakdown of that requirement was running, or which cards already carried its work, so it reached
for the one filing marker it had. And the acceptance from the panel broke the requirement down
with nobody in the conversation the requirement came from told what was filed.

THE RULE THIS FILE HOLDS:
  1. the role's requirements index carries a `breakdown` column for each agreed requirement:
     running now (the engine's listing), the open cards that execute it (their `## Source`),
     none filed — and, when the engine cannot be asked, that it is unknown, never "not running";
     its instruction keeps a card for an agreed requirement's work out of `[[TICKET`, and has a
     card about a requirement name it as `REQ-NNNN`;
  2. the module asks the engine once per role, and an engine that cannot be asked is unknown;
  3. a breakdown the panel, the command line or the API starts is told to the conversation its
     requirement was asked in, as the requirement's delivery loop names it — and to nobody new
     when nothing names one.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from openfactory.memory import store as loop_store
from openfactory.memory.ledger import DELIVERY, open_loop
from openfactory.product import breaking
from openfactory.product.corpus import Corpus, Requirement
from openfactory.product.role import Breakdowns, ProductRole, requirement_index

ROOT = Path(__file__).resolve().parents[1]


def _req(n, status="accepted"):
    return Requirement(number=n, slug="x", path=f"{n:04d}-x.md", title=f"req {n}", status=status)


def _card(ref, *, executes=None, state="open"):
    body = f"## Objective\n\nx\n\n## Source\n\nExecutes REQ-{executes:04d}\n" if executes else ""
    return SimpleNamespace(number=ref, title=f"card {ref}", body=body, state=state,
                           column="Backlog", labels=[], state_reason="")


#: Two agreed requirements and one proposed.
REQS = (_req(66), _req(7), _req(9, "proposed"))


def _index(*, running=frozenset(), cards=(), reqs=REQS):
    role = ProductRole(SimpleNamespace(name="h"), corpus=Corpus(requirements=list(reqs)),
                       cards=list(cards), breakdowns=Breakdowns(running=running))
    return role._breakdown_column(), role._prompt("the task", "the body", audience="client")


def _row(prompt: str, n: int) -> str:
    return next(line for line in prompt.splitlines() if line.startswith(f"| REQ-{n:04d} |"))


# ── 1. what the role reads ──────────────────────────────────────────────────────────────────────

def test_TODAYS_RUN_the_role_reads_that_the_breakdown_is_running():
    column, prompt = _index(running=frozenset({66}))

    assert column[66] == "running now", column
    assert _row(prompt, 66).endswith("| running now |"), _row(prompt, 66)
    assert "never offer a free-standing card for it" in prompt


def test_the_cards_that_carry_its_work_are_read_off_the_board():
    column, _prompt = _index(cards=[_card("41", executes=66), _card("42", executes=66),
                                    _card("43", executes=7, state="closed"), _card("44")])

    assert column[66] == "cards #41, #42", column
    assert column[7] == "none filed", "a closed card was read as carrying the work"


def test_running_and_carded_are_both_said():
    column, _prompt = _index(running=frozenset({66}), cards=[_card("41", executes=66)])

    assert column[66] == "running now; cards #41", column


def test_an_engine_that_cannot_be_asked_is_unknown_never_not_running():
    column, prompt = _index(running=None, cards=[_card("41", executes=7)])

    assert column[66] == "no open cards; whether one is running is unknown", column
    assert column[7] == "cards #41; whether one is running is unknown", column
    assert "none filed" not in _row(prompt, 66)


def test_a_requirement_that_is_not_a_promise_has_no_breakdown():
    column, prompt = _index()

    assert 9 not in column and _row(prompt, 9).endswith("| — |"), _row(prompt, 9)


def test_without_the_state_the_index_is_as_it_was():
    plain = requirement_index(Corpus(requirements=[_req(66)]))
    role = ProductRole(SimpleNamespace(name="h"), corpus=Corpus(requirements=[_req(66)]))

    assert "breakdown" not in plain and role._breakdown_column() is None
    assert "breakdown |" not in role._prompt("t", "b", audience="client")


def test_the_card_marker_is_kept_off_an_agreed_requirements_work():
    """D18 item 5: the role proposes the breakdown, never a free-standing card, for an agreed
    requirement, and names the requirement in a card it drafts about one — which 18c's door then
    reads."""
    source = (ROOT / "openfactory/product/role.py").read_text(encoding="utf-8")

    assert "NOR FOR THE WORK OF " in source and "AN AGREED REQUIREMENT" in source
    assert "it as REQ-NNNN in its title or description" in source


# ── 2. the module asks the engine once per role ─────────────────────────────────────────────────

def test_the_module_reads_the_running_breakdowns_and_says_unknown_when_it_cannot(monkeypatch,
                                                                                 caplog):
    from openfactory.product.module import ProductModule

    module = ProductModule.__new__(ProductModule)
    module.project = SimpleNamespace(name="acme")

    monkeypatch.setattr(breaking, "running_numbers_now", lambda project: {66})
    assert module._breakdowns() == Breakdowns(running=frozenset({66}))

    def _down(project):
        raise RuntimeError("the durable engine is not answering")

    monkeypatch.setattr(breaking, "running_numbers_now", _down)
    with caplog.at_level(logging.INFO, logger="openfactory.product"):
        assert module._breakdowns() == Breakdowns(running=None)
    assert "could not be listed" in caplog.text


def test_every_role_the_module_builds_is_handed_the_breakdowns():
    """Reachability, read off the builder: a reader nothing hands to the role is the defect this
    repository keeps shipping — built, tested, and reached by nothing."""
    from openfactory.product.module import ProductModule

    assert "breakdowns=self._breakdowns()," in inspect.getsource(ProductModule._role)


def test_the_running_breakdowns_are_one_listing_of_this_project_alone():
    class _Engine:
        def __init__(self):
            self.queries = []

        async def list_workflows(self, query):
            self.queries.append(query)
            for wf_id in ("openfactory-product-breakdown-acme-66",
                          "openfactory-product-breakdown-acme-7",
                          "openfactory-product-breakdown-acme-2-5",   # project `acme-2`
                          "openfactory-product-breakdown-other-9"):
                yield SimpleNamespace(id=wf_id)

    engine = _Engine()
    got = asyncio.run(breaking.running_numbers(SimpleNamespace(name="acme"), client=engine))

    assert got == {66, 7}
    assert engine.queries == [breaking._RUNNING], engine.queries


# ── 3. told where the requirement was written ───────────────────────────────────────────────────

@pytest.fixture
def ledger(monkeypatch) -> SimpleNamespace:
    book = SimpleNamespace(rows=[])
    monkeypatch.setattr(loop_store, "read", lambda project, **_k: list(book.rows))
    return book


def _promise(subject, *, conversation="", ts="2026-10-10T10:00:00+00:00"):
    context = {"issues": "#41", **({"conversation": conversation} if conversation else {})}
    return open_loop(DELIVERY, subject, owner="product", ts=ts, context=context)


def test_the_conversation_the_requirement_was_asked_in_is_its_delivery_loops(ledger):
    ledger.rows = [_promise("66", conversation="person:ana", ts="2026-10-09T10:00:00+00:00"),
                   _promise("66", conversation="person:bia", ts="2026-10-10T10:00:00+00:00"),
                   _promise("7", conversation="person:caio"), _promise("8")]
    acme = SimpleNamespace(name="acme")

    assert breaking.written_from(acme, 66) == "person:bia", "the latest conversation wins"
    assert breaking.written_from(acme, 8) == "" and breaking.written_from(acme, 99) == ""


@pytest.fixture
def door(monkeypatch):
    """The panel's door to the breakdown, over an engine that records what it was started with."""
    from openfactory.actions import catalog
    from tests.test_the_confirmation_executor import _actor, _returns

    started = []

    class _Engine:
        async def execute_workflow(self, name, inp, **kw):
            started.append(inp)
            return []

    monkeypatch.setattr(catalog, "_connected", _returns(_Engine()))
    monkeypatch.setattr("openfactory.registry.ProjectRegistry",
                        lambda: SimpleNamespace(get=lambda n: SimpleNamespace(name=n)))
    monkeypatch.setattr("openfactory.product.events.room_of", lambda project: "room:acme")
    return SimpleNamespace(catalog=catalog, started=started, actor=_actor)


def test_TODAYS_RUN_the_panels_acceptance_is_told_where_the_requirement_was_written(door, ledger):
    ledger.rows = [_promise("66", conversation="person:ana")]

    asyncio.run(door.catalog._broken_down_on_the_worker(project="acme", number=66,
                                                        by=door.actor(), asked_for=False))

    ((inp,),) = [door.started]
    assert (inp.conversation, inp.room, inp.asked_for) == ("person:ana", "", False), inp


def test_a_requirement_asked_in_the_room_is_told_in_the_room(door, ledger):
    ledger.rows = [_promise("66", conversation="room:acme")]

    asyncio.run(door.catalog._broken_down_on_the_worker(project="acme", number=66,
                                                        by=door.actor(), asked_for=True))

    assert (door.started[0].conversation, door.started[0].room) == ("room:acme", "room:acme")


def test_a_requirement_whose_record_names_no_conversation_is_told_to_nobody_new(door, ledger):
    asyncio.run(door.catalog._broken_down_on_the_worker(project="acme", number=66,
                                                        by=door.actor(), asked_for=True))

    assert (door.started[0].conversation, door.started[0].room) == ("", "")


def test_a_ledger_that_cannot_be_read_costs_the_telling_never_the_breakdown(door, monkeypatch,
                                                                            caplog):
    def _down(project, **_k):
        raise ConnectionError("the sink is down")

    monkeypatch.setattr(loop_store, "read", _down)
    with caplog.at_level(logging.WARNING):
        asyncio.run(door.catalog._broken_down_on_the_worker(project="acme", number=66,
                                                            by=door.actor(), asked_for=True))

    assert len(door.started) == 1 and door.started[0].conversation == ""
    assert "could not be read" in caplog.text


def test_the_conversations_own_doors_are_unchanged():
    """The conversation passes where it was asked itself (18b); only the doors with none look it up."""
    from openfactory.product import confirm, engine

    for module in (confirm, engine):
        assert "written_from" not in inspect.getsource(module), module.__name__
