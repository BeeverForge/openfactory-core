"""A breakdown asked for while one of the same requirement runs is said as running, and reads what
the running one filed (#563, ADR-0051 D18, slice 18a).

WHAT WAS MEASURED. On a live run (v0.5.0-rc.1) a requirement's breakdowns were started by more
than one door. The panel, the CLI and the API start `ProductBreakdownWorkflow` under one id per
requirement, "so the engine refuses the second start rather than filing every card twice". It
does refuse it — with `WorkflowAlreadyStartedError` — and nothing caught that: the acceptance's
catch-all answered "I could not turn it into units of work", the explicit door's "nothing was
filed … Asking again is safe", while the first breakdown was filing the cards.

THE RULE THIS FILE HOLDS: a door that meets a running breakdown files nothing, waits on THE SAME
execution as a second answer to a proposal does (#456), and says the breakdown was running and
what it filed; when that cannot be read, it says its cards will be on the board.

  1. the engine — two starts of one requirement's breakdown on Temporal's own test server, the
     real workflow, the act held open: it runs once, and the second reads its result;
  2. the doubles — each door's sentence, for each thing the running breakdown can answer.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from openfactory.runtime.temporal import TASK_QUEUE
from openfactory.runtime.temporal.io import ProductBreakdownInput, breakdown_workflow_id
from openfactory.runtime.temporal.workflow import ProductBreakdownWorkflow
from tests.test_the_confirmation_executor import _actor, _returns

ROOT = Path(__file__).resolve().parents[1]
FILED = [{"ok": True, "ref": "acme#41", "url": "", "detail": "", "existed": False},
         {"ok": True, "ref": "acme#42", "url": "", "detail": "", "existed": False}]


# ── 1. the engine ───────────────────────────────────────────────────────────────────────────────

#: What the breakdown on the worker was asked to do, one row per run.
PERFORMED: list[tuple[str, ProductBreakdownInput]] = []
#: Released by the test once the second door has reached the running execution.
HELD: dict[str, asyncio.Event] = {}


@activity.defn(name="product_role_break_down")
async def _the_breakdown(inp: ProductBreakdownInput) -> list[dict]:
    """The act behind the real workflow, held open: still drafting when the second door asks."""
    PERFORMED.append((activity.info().workflow_id, inp))
    await HELD["go"].wait()
    return FILED


class _Watched:
    """The test engine's own client, with a note of which execution a caller waited on."""

    def __init__(self, client) -> None:
        self.client, self.attached = client, []

    async def execute_workflow(self, *args, **kwargs):
        return await self.client.execute_workflow(*args, **kwargs)

    def get_workflow_handle(self, workflow_id, **kwargs):
        self.attached.append(workflow_id)
        return self.client.get_workflow_handle(workflow_id, **kwargs)


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


@pytest.mark.owns_its_engine
async def test_a_second_start_while_one_runs_files_nothing_and_reads_what_the_first_filed(
        env, monkeypatch):
    """THE MEASURED DEFECT. The acceptance's breakdown is drafting; a person asks for the same
    breakdown from another door. The breakdown ran ONCE, and the second door read its cards."""
    from openfactory.actions import catalog

    client = _Watched(env.client)
    monkeypatch.setattr(catalog, "_connected", _returns(client))

    async with Worker(env.client, task_queue=TASK_QUEUE, workflows=[ProductBreakdownWorkflow],
                      activities=[_the_breakdown]):
        first = asyncio.create_task(catalog._broken_down_on_the_worker(
            project="acme", number=7, by=_actor(), asked_for=False))
        await _until(lambda: PERFORMED, "the first breakdown never reached the worker")
        second = asyncio.create_task(catalog._broken_down_on_the_worker(
            project="acme", number=7, by=_actor(id="bia"), asked_for=True))
        await _until(lambda: client.attached or second.done(),
                     "the second door neither returned nor waited on the running breakdown")
        assert not second.done(), "the second door returned while the first was still running"
        HELD["go"].set()
        a, b = await asyncio.wait_for(asyncio.gather(first, second, return_exceptions=True),
                                      timeout=60)

    assert len(PERFORMED) == 1, f"the requirement was broken down {len(PERFORMED)} times"
    ((started, _),) = PERFORMED
    assert started == breakdown_workflow_id("acme", 7)
    assert client.attached == [started], client.attached
    assert a == FILED, a
    assert isinstance(b, catalog._AlreadyBreakingDown) and b.filed == FILED, b


# ── 2. the doubles ──────────────────────────────────────────────────────────────────────────────

class _Running:
    """An engine on which this requirement's breakdown is already running: a second start is
    refused, and the running execution answers `outcome` — or raises it."""

    def __init__(self, outcome) -> None:
        self.outcome, self.started, self.attached = outcome, [], []

    async def execute_workflow(self, name, _inp, **kw):
        self.started.append(kw["id"])
        raise WorkflowAlreadyStartedError(kw["id"], name)

    def get_workflow_handle(self, workflow_id, **_kw):
        self.attached.append(workflow_id)
        outcome = self.outcome

        class _Handle:
            async def result(self):
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome

        return _Handle()


def _accepted():
    from openfactory.actions.base import done

    return done("accepted requirement 7.", project="acme", number=7)


@pytest.mark.asyncio
async def test_the_acceptance_says_the_running_breakdown_and_its_cards(monkeypatch):
    from openfactory.actions import catalog

    engine = _Running(FILED)
    monkeypatch.setattr(catalog, "_connected", _returns(engine))

    out = await catalog._with_the_work_filed(_accepted(), project="acme", number=7, by=_actor())

    assert out.ok and out.message.startswith("accepted requirement 7."), out.message
    assert "already running" in out.message and "acme#41, acme#42" in out.message, out.message
    assert "could not turn it into units of work" not in out.message
    assert engine.attached == engine.started == [breakdown_workflow_id("acme", 7)]
    assert out.data["running"] is True and out.data["filed"] == FILED


@pytest.mark.asyncio
async def test_a_running_breakdown_that_cannot_be_read_is_said_on_the_board_not_as_a_failure(
        monkeypatch):
    from openfactory.actions import catalog

    monkeypatch.setattr(catalog, "_connected", _returns(_Running(RuntimeError("deadline"))))

    out = await catalog._with_the_work_filed(_accepted(), project="acme", number=7, by=_actor())

    assert out.ok, out.message
    assert "already running" in out.message and "on the board when it ends" in out.message
    assert "could not turn it into units of work" not in out.message


@pytest.fixture
def _promised(monkeypatch):
    """A product whose requirement 7 is a promise, and a person who may act on it — so the
    explicit door reaches its engine."""
    from openfactory.actions import catalog

    requirement = SimpleNamespace(is_promise=True)
    module = SimpleNamespace(context=lambda: SimpleNamespace(
        available=True, reason="", corpus=SimpleNamespace(by_number=lambda _n: requirement)))
    project = SimpleNamespace(name="acme", language="en")
    monkeypatch.setattr(catalog, "_product_module", lambda _n, **_kw: (module, project, None))
    monkeypatch.setattr("openfactory.product.module.may_act", lambda *_a, **_k: True)


@pytest.mark.asyncio
async def test_the_explicit_door_says_the_running_breakdown_never_that_nothing_was_filed(
        monkeypatch, _promised):
    from openfactory.actions import catalog

    monkeypatch.setattr(catalog, "_connected", _returns(_Running(FILED)))

    out = await catalog._product_break_down(project="acme", number="7", by=_actor(), yes=True)

    assert out.ok, out.message
    assert "already running" in out.message and "acme#41, acme#42" in out.message, out.message
    assert "nothing was filed" not in out.message and "Asking again" not in out.message


@pytest.mark.asyncio
async def test_a_running_breakdown_that_filed_nothing_is_said_with_its_reason(monkeypatch,
                                                                           _promised):
    """What the running one answered, said as a refusal like the door's own: nothing was filed,
    and why — but as the running breakdown's outcome, not as this door's failure to reach it."""
    from openfactory.actions import catalog

    refused = [{"ok": False, "ref": "", "url": "", "existed": False,
                "detail": "the board refused the card."}]
    monkeypatch.setattr(catalog, "_connected", _returns(_Running(refused)))

    out = await catalog._product_break_down(project="acme", number="7", by=_actor(), yes=True)

    assert not out.ok and out.code == catalog.FAILED, (out.code, out.message)
    assert "already running" in out.message, out.message
    assert out.message.endswith("it filed nothing: the board refused the card."), out.message


def test_the_breakdown_s_id_is_spelled_in_one_place():
    """Every door asks the engine for the SAME execution only while they spell it alike."""
    spelled = [str(path.relative_to(ROOT)) for path in sorted((ROOT / "openfactory").rglob("*.py"))
               if "openfactory-product-breakdown-" in path.read_text(encoding="utf-8")]
    assert spelled == ["openfactory/runtime/temporal/io.py"], spelled
