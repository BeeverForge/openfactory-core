"""The conversation starts a requirement's breakdown on the worker, as every other door does, and is
told what it filed when it ends (#563, ADR-0051 D18, slice 18b).

WHAT WAS MEASURED. On a live run (v0.5.0-rc.1) one requirement got its cards through more than one
door at once. The panel, the CLI and the API start `ProductBreakdownWorkflow` under one id per
requirement, and the engine runs one execution of it at a time. The conversation's two doors — "quebra
o requisito 7" and the acceptance's second act — called `module.break_down` in their own process, so
nothing shared told them apart from the panel's: accepting from the panel while the conversation
said yes broke the requirement down twice.

THE RULE THIS FILE HOLDS:
  1. the engine — the conversation's start and the panel's start of one requirement's breakdown,
     on Temporal's own test server with the real workflow: it runs once, whichever door came first;
  2. the telling — the breakdown on the worker tells the conversation that started it what it
     filed (or that it failed) when it ends, and tells nobody when no conversation started it;
  3. the doors — each conversation door starts it and says so, says one already running as news,
     and says an engine that did not answer; no door runs the breakdown in its own process (D17);
  4. the sentence the conversation is told, for each thing a breakdown can answer.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

import openfactory.product.channel as pc
from openfactory.product import breaking
from openfactory.product.authoring import WriteResult
from openfactory.runtime.temporal import TASK_QUEUE
from openfactory.runtime.temporal.io import ProductBreakdownInput, breakdown_workflow_id
from openfactory.runtime.temporal.workflow import ProductBreakdownWorkflow
from tests.test_the_confirmation_executor import _actor, _returns
from tests.the_chat_turn import chat_turn

ROOT = Path(__file__).resolve().parents[1]
FILED = [{"ok": True, "ref": "acme#41", "url": "", "detail": "", "existed": False,
          "nothing_to_build": False}]


# ── 1. the engine ───────────────────────────────────────────────────────────────────────────────

PERFORMED: list[ProductBreakdownInput] = []
HELD: dict[str, asyncio.Event] = {}


@activity.defn(name="product_role_break_down")
async def _the_breakdown(inp: ProductBreakdownInput) -> list[dict]:
    """The act behind the real workflow, held open: still drafting when the other door asks."""
    PERFORMED.append(inp)
    await HELD["go"].wait()
    return FILED


@pytest.fixture
async def env():
    PERFORMED.clear()
    HELD["go"] = asyncio.Event()
    e = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    try:
        yield e
    finally:
        HELD["go"].set()
        await e.shutdown()


async def _until(what, why: str, *, within: float = 20.0) -> None:
    deadline = time.monotonic() + within
    while not what():
        if time.monotonic() > deadline:
            raise AssertionError(f"waited {within}s: {why}")
        await asyncio.sleep(0.02)


ACME = SimpleNamespace(name="acme", language="pt-BR")


@pytest.mark.owns_its_engine
async def test_TODAYS_RUN_the_panel_accepts_while_the_conversation_asks_and_it_runs_once(
        env, monkeypatch):
    """THE MEASURED DEFECT. The panel's acceptance is breaking the requirement down; the
    conversation asks for the same breakdown. It ran ONCE, and the conversation was told it was
    running rather than starting a second one."""
    from openfactory.actions import catalog

    monkeypatch.setattr(catalog, "_connected", _returns(env.client))
    async with Worker(env.client, task_queue=TASK_QUEUE, workflows=[ProductBreakdownWorkflow],
                      activities=[_the_breakdown]):
        panel = asyncio.create_task(catalog._broken_down_on_the_worker(
            project="acme", number=7, by=_actor(), asked_for=False))
        await _until(lambda: PERFORMED, "the panel's breakdown never reached the worker")
        how = await breaking.start(ACME, 7, actor="bia", asked_for=True, conversation="C1",
                                   room="R1", requester="bia", client=env.client)
        HELD["go"].set()
        filed = await asyncio.wait_for(panel, timeout=60)

    assert how == breaking.RUNNING, how
    assert len(PERFORMED) == 1, f"the requirement was broken down {len(PERFORMED)} times"
    assert filed == FILED, filed


@pytest.mark.owns_its_engine
async def test_the_conversation_first_and_the_panel_reads_what_it_filed(env, monkeypatch):
    """The other order: the conversation started it, with where it was asked, and the panel's
    acceptance files nothing and reads the same execution (18a)."""
    from openfactory.actions import catalog

    monkeypatch.setattr(catalog, "_connected", _returns(env.client))
    async with Worker(env.client, task_queue=TASK_QUEUE, workflows=[ProductBreakdownWorkflow],
                      activities=[_the_breakdown]):
        how = await breaking.start(ACME, 7, actor="bia", asked_for=True, conversation="C1",
                                   room="R1", requester="bia", client=env.client)
        await _until(lambda: PERFORMED, "the conversation's breakdown never reached the worker")
        panel = asyncio.create_task(catalog._broken_down_on_the_worker(
            project="acme", number=7, by=_actor(), asked_for=False))
        await asyncio.sleep(0.3)
        HELD["go"].set()
        refused = await asyncio.wait_for(asyncio.gather(panel, return_exceptions=True),
                                         timeout=60)

    assert how == breaking.STARTED, how
    assert len(PERFORMED) == 1, f"the requirement was broken down {len(PERFORMED)} times"
    ((inp),) = PERFORMED
    assert (inp.conversation, inp.room, inp.requester, inp.asked_for) == ("C1", "R1", "bia", True)
    assert isinstance(refused[0], catalog._AlreadyBreakingDown), refused
    assert refused[0].filed == FILED, refused[0].filed


#: Every telling the workflow asked for, when the breakdown did not finish.
UNFINISHED: list[ProductBreakdownInput] = []


@activity.defn(name="product_breakdown_did_not_finish")
async def _told_unfinished(inp: ProductBreakdownInput) -> bool:
    UNFINISHED.append(inp)
    return True


@activity.defn(name="product_role_break_down")
async def _the_breakdown_that_raises(inp: ProductBreakdownInput) -> list[dict]:
    from temporalio.exceptions import ApplicationError

    raise ApplicationError("the harness died", non_retryable=True)


async def _ended(env, breakdown, inp: ProductBreakdownInput):
    UNFINISHED.clear()
    async with Worker(env.client, task_queue=TASK_QUEUE, workflows=[ProductBreakdownWorkflow],
                      activities=[breakdown, _told_unfinished]):
        handle = await env.client.start_workflow(
            "ProductBreakdownWorkflow", inp, id=breakdown_workflow_id(inp.project, inp.number),
            task_queue=TASK_QUEUE)
        try:
            await asyncio.wait_for(handle.result(), timeout=60)
        except Exception as exc:  # noqa: BLE001 — the case asserts on it
            return exc
    return None


@pytest.mark.owns_its_engine
async def test_a_breakdown_that_did_not_finish_is_told_by_the_workflow(env):
    """REVIEW OF #616. The activity told its own failure, but a worker that died or a heartbeat
    that stopped never reached that line, and the conversation heard "started" and then nothing.
    The workflow tells it now, and the breakdown still fails."""
    failed = await _ended(env, _the_breakdown_that_raises, ProductBreakdownInput(
        project="acme", number=7, actor="bia", asked_for=True, conversation="C1", room="R1"))

    assert failed is not None, "a breakdown that did not finish was reported as done"
    assert [(i.conversation, i.room) for i in UNFINISHED] == [("C1", "R1")], UNFINISHED


def test_whatever_ends_the_breakdown_reaches_the_telling():
    """A worker that died and a heartbeat that stopped reach the workflow as an `ActivityError`
    whose cause is a timeout, as an error the activity raised does: the workflow catches that
    class, never one narrower, so each of them is told."""
    source = inspect.getsource(ProductBreakdownWorkflow.run)

    assert "except ActivityError:" in source and "product_breakdown_did_not_finish" in source


@pytest.mark.owns_its_engine
async def test_a_breakdown_no_conversation_started_is_told_to_nobody_when_it_fails(env):
    failed = await _ended(env, _the_breakdown_that_raises, ProductBreakdownInput(
        project="acme", number=7, actor="bia", asked_for=False))

    assert failed is not None and UNFINISHED == []


@pytest.mark.owns_its_engine
async def test_after_it_ends_the_conversation_may_start_it_again(env):
    """Once means one at a time (D18 item 1): a breakdown that ended does not refuse the next."""
    async with Worker(env.client, task_queue=TASK_QUEUE, workflows=[ProductBreakdownWorkflow],
                      activities=[_the_breakdown]):
        HELD["go"].set()
        first = await breaking.start(ACME, 7, actor="bia", asked_for=True, client=env.client)
        await env.client.get_workflow_handle(breakdown_workflow_id("acme", 7)).result()
        second = await breaking.start(ACME, 7, actor="bia", asked_for=True, client=env.client)

    assert (first, second) == (breaking.STARTED, breaking.STARTED)


# ── 2. the telling ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def worker_side(monkeypatch):
    """The breakdown activity with its project, its module's act and the door's telling recorded:
    `told` is every announcement, `broke` every call into the module."""
    from openfactory.product import door
    from openfactory.runtime.temporal import activities

    told, broke = [], []
    seen = SimpleNamespace(told=told, broke=broke, results=[WriteResult(ok=True, ref="#41")],
                           raises=None)

    class _Registry:
        def get(self, _name):
            return SimpleNamespace(name="acme", language="pt-BR", product=None)

    def _break(project, number, actor, asked_for, **where):
        broke.append((number, actor, asked_for, where))
        if seen.raises:
            raise seen.raises
        return seen.results

    async def _announce(project, *, id, conversation, text, room="", client=None):
        told.append({"id": id, "conversation": conversation, "text": text, "room": room})
        return SimpleNamespace(accepted=True)

    monkeypatch.setattr(activities, "ProjectRegistry", _Registry)
    monkeypatch.setattr(activities, "_product_break_down", _break)
    monkeypatch.setattr(door, "announce", _announce)
    monkeypatch.setattr("openfactory.product.confirm.breakdown_told",
                        lambda project, number, results, *, asked_for, module=None, language=None:
                        f"told REQ-{number}: {[getattr(r, 'ref', '') for r in results or []]}"
                        f" asked={asked_for} in={language}" if results is not None
                        else f"told REQ-{number}: failed")
    return seen


def _inp(**kw) -> ProductBreakdownInput:
    return ProductBreakdownInput(**{"project": "acme", "number": 7, "actor": "bia",
                                    "asked_for": True, **kw})


async def test_the_conversation_that_started_it_is_told_what_it_filed(worker_side):
    from openfactory.runtime.temporal.activities import product_role_break_down

    rows = await product_role_break_down(_inp(conversation="C1", room="R1", requester="bia",
                                              language="en"))

    assert [r["ref"] for r in rows] == ["#41"]
    assert worker_side.told == [{"id": "breakdown-acme-7", "conversation": "C1",
                                 "text": "told REQ-7: ['#41'] asked=True in=en", "room": "R1"}]
    # …and the delivery loop is announced in the same conversation (#267 slice 3)
    assert worker_side.broke == [(7, "bia", True, {"conversation": "C1", "requester": "bia"})]


async def test_a_breakdown_no_conversation_started_is_told_to_nobody(worker_side):
    from openfactory.runtime.temporal.activities import product_role_break_down

    await product_role_break_down(_inp())

    assert worker_side.told == [], "the panel's breakdown was told to a conversation"


async def test_a_breakdown_that_failed_still_fails_and_leaves_the_telling_to_the_workflow(
        worker_side):
    """The workflow tells a breakdown that did not finish, whatever ended it (review of #616): the
    activity's own except could not see a worker that died, so it tells nothing itself."""
    from openfactory.runtime.temporal.activities import product_role_break_down

    worker_side.raises = RuntimeError("the harness died")
    with pytest.raises(RuntimeError, match="the harness died"):
        await product_role_break_down(_inp(conversation="C1"))

    assert worker_side.told == []


async def test_the_breakdown_that_did_not_finish_is_told(worker_side):
    from openfactory.runtime.temporal.activities import product_breakdown_did_not_finish

    assert await product_breakdown_did_not_finish(_inp(conversation="C1", room="R1")) is True
    assert worker_side.told == [{"id": "breakdown-acme-7", "conversation": "C1",
                                 "text": "told REQ-7: failed", "room": "R1"}]


async def test_a_telling_that_failed_never_costs_the_cards(worker_side, monkeypatch, caplog):
    from openfactory.product import door
    from openfactory.runtime.temporal.activities import product_role_break_down

    async def _down(*_a, **_k):
        raise ConnectionError("the door is down")

    monkeypatch.setattr(door, "announce", _down)
    with caplog.at_level(logging.ERROR):
        rows = await product_role_break_down(_inp(conversation="C1"))

    assert [r["ref"] for r in rows] == ["#41"]
    assert "OPENFACTORY_PRODUCT_BREAKDOWN_UNTOLD" in caplog.text, caplog.text


async def test_what_the_module_refused_as_built_is_carried_to_the_waiting_door(worker_side):
    """A reading of the code accepted files nothing (#182): the row says so, so a door reading the
    rows does not count it as a card."""
    from openfactory.runtime.temporal.activities import product_role_break_down

    worker_side.results = [SimpleNamespace(ok=True, ref="", detail="já está construído",
                                           url="", existed=False, nothing_to_build=True)]
    rows = await product_role_break_down(_inp(asked_for=False))

    assert rows[0]["nothing_to_build"] is True, rows


# ── 3. the doors ────────────────────────────────────────────────────────────────────────────────

class _Product:
    admins = ["UADM"]
    agent_name, docs_repo, channel_id, enabled, docs_branch = "Nina", "a/docs", "C1", True, "main"


class _Project:
    name, language = "books", "pt-BR"
    product = _Product()


class _Module:
    def __init__(self, accepted=None):
        self.broke = []
        self._accepted = accepted or WriteResult(ok=True)

    def accept(self, number, *, actor):
        return self._accepted

    def break_down(self, *a, **k):  # pragma: no cover — reaching it is the defect
        self.broke.append((a, k))
        raise AssertionError("the conversation ran the breakdown in its own process")

    def confirmed(self, *_a, **_k):
        return "neither"

    def settle_acceptance(self, *_a, **_k):
        return None

    def close_decisions_answered(self, **_):
        return 0

    def record_decisions(self, *_a, **_k):
        return None


@pytest.fixture
def started(monkeypatch):
    """`breaking.start_now`, recorded: what each door asked for, and what the engine answers."""
    from openfactory.memory import transcript
    from openfactory.product import staging

    monkeypatch.setattr(staging, "_PENDING", {})
    monkeypatch.setattr(staging, "_EXPIRED_TOMBSTONES", {})
    monkeypatch.setattr(transcript, "record", lambda *a, **k: "")
    monkeypatch.setattr(transcript, "recent", lambda *a, **k: [])
    seen = SimpleNamespace(calls=[], answer=breaking.STARTED)

    def _start(project, number, **kw):
        seen.calls.append((number, kw))
        if isinstance(seen.answer, Exception):
            raise seen.answer
        return seen.answer

    monkeypatch.setattr(breaking, "start_now", _start)
    return seen


def _asked(module, text="quebra o requisito 7 em tarefas"):
    return chat_turn(_Project(), text=text, user="UADM", thread="C1", channel="R1", module=module)


def test_asking_for_the_breakdown_starts_it_and_says_so(started):
    module = _Module()

    said = _asked(module)

    assert started.calls == [(7, {"actor": "UADM", "asked_for": True, "conversation": "C1",
                                  "room": "R1", "requester": "UADM", "language": "pt-BR"})]
    assert said.startswith("Nina: Comecei a quebrar o requisito 7 em tarefas."), said
    assert "digo aqui o que virou card" in said, said
    assert module.broke == []


def test_a_breakdown_already_running_is_news_not_a_failure(started):
    started.answer = breaking.RUNNING

    said = _asked(_Module())

    assert "já está sendo quebrado" in said and "não comecei outra" in said, said
    assert "nada foi registrado" not in said, said


def test_an_engine_that_does_not_answer_is_said(started, caplog):
    started.answer = ConnectionError("no engine")

    with caplog.at_level(logging.ERROR):
        said = _asked(_Module())

    assert "Não consegui começar a quebrar o requisito 7" in said, said
    assert "OPENFACTORY_PRODUCT_BREAKDOWN_NOT_STARTED" in caplog.text, caplog.text


def _accept(module, **entry):
    pc.remember("C1", {"kind": "accept", "number": 6, "channel": "R1", "asked_by": "<@UADM>",
                       **entry}, person="UADM")
    return chat_turn(_Project(), text="sim", user="UADM", thread="C1", channel="R1",
                     module=module)


def test_the_acceptance_starts_its_breakdown_with_where_it_was_asked(started):
    module = _Module()

    said = _accept(module)

    ((number, kw),) = started.calls
    assert number == 6 and kw["asked_for"] is False and kw["actor"] == "UADM", kw
    assert (kw["conversation"], kw["room"]) == ("C1", "R1"), kw
    assert "Acordado" in said and "Comecei a quebrar o requisito 6" in said, said
    assert module.broke == []


def test_an_acceptance_whose_breakdown_could_not_start_still_says_the_agreement_holds(
        started, caplog):
    started.answer = ConnectionError("no engine")

    with caplog.at_level(logging.ERROR):
        said = _accept(_Module())

    assert "Acordado" in said and "O acordo está registrado do mesmo jeito" in said, said
    assert "OPENFACTORY_PRODUCT_AUTOBREAK_FAILED" in caplog.text, caplog.text


def test_no_conversation_door_runs_the_breakdown_in_its_own_process():
    """D17: the pull request that brings the slice removes the path it replaces."""
    from openfactory.product import confirm, engine

    for module in (engine, confirm):
        assert ".break_down(" not in inspect.getsource(module), module.__name__


# ── 4. what the conversation is told ────────────────────────────────────────────────────────────

class _Words:
    def board_words(self):
        return {"backlog": "Pendências"}


def _told(results, *, asked_for):
    from openfactory.product.confirm import breakdown_told

    return breakdown_told(SimpleNamespace(name="acme", language="pt-BR"), 7, results,
                          asked_for=asked_for, module=_Words())


@pytest.mark.parametrize("asked_for", [True, False])
def test_what_landed_is_told_with_the_boards_own_column(asked_for):
    said = _told([WriteResult(ok=True, ref="#41"), WriteResult(ok=True, ref="#42")],
                 asked_for=asked_for)

    assert "#41, #42" in said and "Pendências" in said, said


def test_a_reading_of_the_code_is_told_as_nothing_to_build():
    said = _told([SimpleNamespace(ok=True, ref="", detail="", nothing_to_build=True)],
                 asked_for=False)

    assert "requisito 7" in said and "#" not in said, said


def test_an_unagreed_requirement_asked_for_is_told_the_modules_refusal():
    said = _told([WriteResult(ok=False, detail="o requisito 7 ainda não foi acordado")],
                 asked_for=True)

    assert "ainda não foi acordado" in said, said


@pytest.mark.parametrize("results", [[], [WriteResult(ok=False, detail="sem quadro")]])
def test_an_acceptance_whose_breakdown_filed_nothing_says_the_agreement_holds(results):
    said = _told(results, asked_for=False)

    assert said.startswith("Ainda não consegui transformar isso em frentes de trabalho"), said
    assert "O acordo está registrado do mesmo jeito" in said, said


def test_the_conversation_is_told_in_its_own_language():
    """A conversation is answered in the language it speaks (#432), which need not be the
    project's: the start carries it to the worker, and the sentence is written in it."""
    from openfactory.product.confirm import breakdown_told

    said = breakdown_told(SimpleNamespace(name="acme", language="pt-BR"), 7,
                          [WriteResult(ok=True, ref="#41")], asked_for=True, module=_Words(),
                          language="en")

    assert "starting work on it" in said and "Pendências" in said, said


@pytest.mark.parametrize(("asked_for", "agreed"), [(True, False), (False, True)])
def test_a_breakdown_that_did_not_finish_never_says_nothing_was_filed(asked_for, agreed):
    """REVIEW OF #619. It raised, its worker died or its heartbeat stopped, perhaps after filing
    some cards: the sentence says some may be on the board and that asking again does not file
    them twice — and, after an acceptance, that the agreement stands."""
    said = _told(None, asked_for=asked_for)

    assert said.startswith("A quebra do requisito 7 em tarefas não terminou."), said
    assert "podem já estar no quadro" in said and "não é registrado duas vezes" in said, said
    assert ("O acordo continua registrado." in said) is agreed, said
    assert "Ainda não consegui" not in said, said
