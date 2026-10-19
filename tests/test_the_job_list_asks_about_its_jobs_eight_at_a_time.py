"""The job list asks the engine about its jobs eight at a time, so a busy floor's list answers
inside the read deadline (#754, criteria 1 and 2).

`list_jobs` walked `client.list_workflows(...)` and awaited each row's enrichment before it read the
next workflow. For a row that looks RUNNING that is one `describe()` and then up to three queries a
WORKER answers by replaying history (`awaiting_action`, `awaiting_merge`, `awaiting_approval`). The
measurement in `view.py`'s deadline comment gave 317 ms for 50 jobs, mostly closed, and noted that
the cost "grows with the number of RUNNING jobs". A downstream deployment (one host, ~19 projects)
reported the consequence: with a few dozen running jobs the read overran
`OPENFACTORY_ENGINE_DEADLINE` (3 s), `_within` remembered the engine as silent, and every reader in
the process (floor, inbox, card, stream, tech-lead) was refused for
`OPENFACTORY_ENGINE_UNREACHABLE_FOR`, although the engine had answered every question it was asked.

The jobs are now asked about `OPENFACTORY_LIST_CONCURRENCY` at a time, 8 when unset.

THE PEAK IS REACHED, NOT MERELY ALLOWED. Every stand-in `describe()` waits on a barrier of `k`
under a bound: fewer than `k` at once and the barrier never fills, the describe fails, the row reads
as `gone` and the list comes back short; more than `k` at once and the peak counted on entry is
above `k`. The only test that reads a wall clock is the deadline one, and its margin is about 4x
either way: 48 running jobs x 4 RPCs x 10 ms is ~1.9 s one after another, ~0.25 s eight at a time,
against a 1.0 s deadline.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from temporalio.client import WorkflowExecutionStatus

from openfactory.runtime.temporal import view as tv
from openfactory.runtime.temporal.vocabulary import EngineUnreachable

ROOT = Path(__file__).resolve().parents[1]
VARIABLE = "OPENFACTORY_LIST_CONCURRENCY"


@pytest.fixture(autouse=True)
def _a_fresh_engine_memory():
    """The breaker a red run opens must not close the next test's engine (`reset_clients` clears
    both the pool and the remembered silence)."""
    tv.reset_clients()
    yield
    tv.reset_clients()


class _Wf:
    """A RUNNING `JobWorkflow` as `list_workflows` yields it (`_FakeWf`'s shape)."""

    def __init__(self, i: int) -> None:
        self.id = f"openfactory-books-{i}"
        self.run_id = f"run-{i}"
        self.status = WorkflowExecutionStatus.RUNNING
        # Distinct, so the newest-first sort has one answer; recent, so nothing reads as wedged.
        self.start_time = datetime.now(UTC) - timedelta(minutes=i)
        self.close_time = None

    async def memo(self):
        return {}


class _Handle:
    """A live handle whose every engine call is counted in and out of `flight`, and costs `rpc()`."""

    def __init__(self, client: _Busy, wf: _Wf) -> None:
        self._client = client
        self._wf = wf

    async def _call(self, wait):
        flight = self._client.flight
        flight["now"] += 1
        flight["peak"] = max(flight["peak"], flight["now"])
        try:
            await wait()
        finally:
            flight["now"] -= 1

    async def describe(self):
        await self._call(self._client.on_describe)
        return type("D", (), {"status": WorkflowExecutionStatus.RUNNING,
                              "run_id": self._wf.run_id})()

    async def query(self, *_a, **_kw):
        await self._call(self._client.on_query)
        return None  # not parked, not at a gate: the row is "running"


class _Page:
    """What the SDK's `list_workflows` returns: `WorkflowExecutionAsyncIterator` (temporalio 1.34.0)
    is a plain class with `__aiter__`/`__anext__`, NOT an async generator. An abandoned async
    generator is closed by a task the loop schedules (`async_generator_athrow`), which the
    no-task-left assertion below would count as a question still running; the real iterator
    leaves nothing to close."""

    def __init__(self, wfs: list[_Wf]) -> None:
        self._left = iter(wfs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._left)
        except StopIteration:
            raise StopAsyncIteration from None


class _Busy:
    """An engine with `n` running jobs; `on_describe`/`on_query` are what each call waits for."""

    def __init__(self, n: int, *, on_describe, on_query) -> None:
        self._wfs = [_Wf(i) for i in range(n)]
        self.on_describe = on_describe
        self.on_query = on_query
        self.flight = {"now": 0, "peak": 0}

    def list_workflows(self, query):
        return _Page(self._wfs)

    def get_workflow_handle(self, wf_id, run_id=None):
        return _Handle(self, next(w for w in self._wfs if w.id == wf_id))


def _sleeping(seconds: float):
    async def wait():
        await asyncio.sleep(seconds)
    return wait


def _barrier(k: int):
    """A describe that returns only once `k` describes are in flight together (0.5 s bound)."""
    gate = asyncio.Barrier(k)

    async def wait():
        await asyncio.wait_for(gate.wait(), 0.5)
    return wait


async def _nothing():
    return None


async def test_a_busy_floors_job_list_answers_inside_the_read_deadline(monkeypatch):
    """Criterion 1. Before: 48 running jobs at 10 ms an RPC were asked about one after another,
    ~1.9 s, so a 1.0 s deadline refused the list and opened the breaker for every reader."""
    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "1.0")
    monkeypatch.delenv(VARIABLE, raising=False)
    client = _Busy(48, on_describe=_sleeping(0.01), on_query=_sleeping(0.01))

    started = time.monotonic()
    try:
        rows = await tv.list_jobs(client, "default")
    except EngineUnreachable as exc:
        pytest.fail(f"{exc} — after {time.monotonic() - started:.2f}s, peak in flight "
                    f"{client.flight['peak']}, every reader now refused for "
                    f"{tv.unreachable_for():.1f}s")
    elapsed = time.monotonic() - started

    assert len(rows) == 48
    assert tv.unreachable_for() == 0
    assert elapsed < 1.0


async def test_eight_jobs_are_asked_about_at_once_when_the_operator_says_nothing(monkeypatch):
    """Criterion 2, the default. Before: one describe in flight, so the barrier of 8 never filled,
    every describe failed, and every row read as `gone`."""
    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "10")
    monkeypatch.delenv(VARIABLE, raising=False)
    client = _Busy(16, on_describe=_barrier(8), on_query=_nothing)

    rows = await tv.list_jobs(client, "default")

    assert (client.flight["peak"], len(rows)) == (8, 16)


async def test_the_operator_sets_how_many_jobs_are_asked_about_at_once(monkeypatch):
    """Criterion 2, the variable. Exactly 3: neither the default nor one at a time."""
    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "10")
    monkeypatch.setenv(VARIABLE, "3")
    client = _Busy(12, on_describe=_barrier(3), on_query=_nothing)

    rows = await tv.list_jobs(client, "default")

    assert (client.flight["peak"], len(rows)) == (3, 12)


@pytest.mark.parametrize(("value", "said"), [("0", 1), ("-2", 1), ("zero", 1), (" ", 0)])
def test_a_concurrency_nobody_can_read_is_eight_said_once(monkeypatch, caplog, value, said):
    """A bound nobody can read must not become no bound, nor one job at a time, and must not be
    silent: said once however often it is read, as `OPENFACTORY_SOURCES_PARALLEL` is (#369). A
    blank value is unset, and says nothing."""
    monkeypatch.setattr(tv, "_LIST_CONCURRENCY_SAID", set(), raising=False)
    monkeypatch.setenv(VARIABLE, value)
    caplog.set_level(logging.WARNING, logger=tv.log.name)

    read = [tv.list_concurrency() for _ in range(3)]

    assert read == [tv.DEFAULT_LIST_CONCURRENCY] * 3
    lines = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    named = [line for line in lines if VARIABLE in line]
    assert len(named) == said, lines
    assert all(repr(value) in line and str(tv.DEFAULT_LIST_CONCURRENCY) in line
               for line in named), named


def _table_row(page: Path, first_cell: str) -> list[str]:
    """The cells of the one markdown table row whose first cell is `first_cell`."""
    rows = [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in page.read_text(encoding="utf-8").splitlines()
            if line.lstrip().startswith("|")]
    matches = [r for r in rows if r and r[0] == first_cell]
    assert len(matches) == 1, f"{page.name} has {len(matches)} rows starting {first_cell!r}"
    return matches[0]


def test_the_reference_documents_the_concurrency_the_code_has():
    cells = _table_row(ROOT / "docs" / "reference" / "configuration.md", f"`{VARIABLE}`")

    numbers = {int(n) for n in re.findall(r"\b\d+\b", " ".join(cells[1:]))}

    assert numbers == {tv.DEFAULT_LIST_CONCURRENCY}, (
        f"the reference names {sorted(numbers)} and the code defaults to "
        f"{tv.DEFAULT_LIST_CONCURRENCY}")


async def test_a_job_list_that_ran_out_of_time_leaves_no_question_running(monkeypatch):
    """Criterion 2's bound. A list that ran past the deadline must not leave its questions running
    behind it: a query to a silent worker otherwise runs until the SDK gives up (30 s, measured in
    `review_verdicts`' docstring), on the tech-lead's standing loop (#147) for as long as it lives.
    Passes on the sequential list (`wait_for` cancelled the one coroutine); it holds that the
    concurrent one cancels every enrichment it started."""
    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "0.3")
    monkeypatch.delenv(VARIABLE, raising=False)
    client = _Busy(16, on_describe=_nothing, on_query=_sleeping(30))

    with pytest.raises(EngineUnreachable, match="OPENFACTORY_ENGINE_DEADLINE"):
        await tv.list_jobs(client, "default")
    await asyncio.sleep(0)

    assert client.flight["now"] == 0
    left = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
    assert left == []
