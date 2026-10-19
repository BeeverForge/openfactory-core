"""A job list read a moment ago is shared, and never across loops (#754, criterion 5: "askers right
after it share its answer for a few seconds (keyed by loop and client, so a dead loop's answer is
never served)").

`api/app.py::temporal_stream` asks for the job list on every 2 s tick of every connected browser,
and `panel.html` re-reads `/api/temporal/jobs` 600-800 ms after most clicks. On `main` each of
those is a whole scan of the engine (`list_workflows`, then a describe and up to three worker
queries per running row), so the reads a person causes by watching the panel are the reads that
pushed the reporter's list past `OPENFACTORY_ENGINE_DEADLINE`.

A reader within `tv.LIST_TTL_S` of a scan is now handed that scan's answer. What that must never
cost, each a claim below:

- ANOTHER LOOP IS NEVER HANDED THIS LOOP'S ANSWER. The tech-lead and the CLI open an `asyncio.run`
  per question (#134: a client belongs to the loop that made it), so the answer is keyed by the
  running loop, held by identity.
- ANOTHER CLIENT IS NEVER HANDED THIS CLIENT'S ANSWER: two engines are two floors.
- THE ANSWER EXPIRES, and A SCAN THAT FAILED IS NOT AN ANSWER: a failure is shared with the askers
  waiting on it and never stored (engineering-lessons §11), or a recovered engine would read as
  down for the rest of the window.
- A WRITE THROUGH THIS PROCESS IS SEEN BY THE NEXT LIST (the PO's Q2, default): Approve, Merge or
  Resume followed by the panel's re-read would otherwise show the job as it was before the click
  for the rest of the window, a button that looks as if it did nothing. The writes are found by
  walking `view.py`, not listed here, so a write added later is held without anybody remembering.

The first test is red on `main` (two scans where one is required). The others pass there — there
is no shared answer to serve wrongly — and are what the mutation plan's "the key forgets the loop /
the client", "the window never ends", "a failure is stored" and "a write forgets nothing" cuts
turn red (`tools/mutations/754_the_job_list_is_asked_side_by_side_and_shared.py`).

THE CLOCK IS STATED, NOT WAITED FOR: `view.py`'s `time.monotonic` (a loop clock, as the breaker's
`_SILENT_UNTIL` is, never the wall clock) is replaced by one the test moves.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from openfactory.runtime.temporal import view as tv
from tests.job_list_scans import PROJECT, WRITTEN, CountedEngine, forget, scans_of

#: Q1's default, used only where `main` has no window to read: the expiry test must pass there.
_Q1_WINDOW = 2.0


class _Clock:
    """`view.py`'s `time`, with a `monotonic` the test moves; everything else is the real module."""

    def __init__(self) -> None:
        self.now = time.monotonic()

    def monotonic(self) -> float:
        return self.now

    def __getattr__(self, name):
        return getattr(time, name)


@pytest.fixture(autouse=True)
def clock(monkeypatch) -> _Clock:
    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "10")
    monkeypatch.setattr(tv, "_registered_projects", lambda: [PROJECT])
    stated = _Clock()
    monkeypatch.setattr(tv, "time", stated)
    tv.reset_clients()
    forget()
    yield stated
    forget()
    tv.reset_clients()


async def test_an_asker_right_after_a_scan_is_handed_its_answer(clock):
    """Criterion 5. A second asker one second after a scan is handed that scan's answer: one scan,
    the same rows, built by scan 1. On `main`: two scans. The window is "a few seconds" (the
    issue), longer than the second waited here and no longer than a few of the stream's 2 s
    ticks."""
    engine = CountedEngine()

    first = await tv.list_jobs(engine, "default")
    clock.now += 1.0
    second = await tv.list_jobs(engine, "default")

    assert engine.scans == 1, f"an asker one second after a scan cost {engine.scans} scans"
    assert second == first
    assert scans_of(second) == {"1"}
    assert 1.0 < tv.LIST_TTL_S <= 6.0, f"a window of {tv.LIST_TTL_S}s is not a few seconds"


async def test_the_shared_answer_expires_after_its_window(clock):
    """Criterion 5. Past the window the next asker is read a fresh list, built by scan 2. Passes
    on `main`; red under the cut that never lets the answer expire."""
    engine = CountedEngine()

    await tv.list_jobs(engine, "default")
    clock.now += getattr(tv, "LIST_TTL_S", _Q1_WINDOW) + 0.01
    later = await tv.list_jobs(engine, "default")

    assert engine.scans == 2, f"an asker after the window cost {engine.scans} scans, not a fresh one"
    assert scans_of(later) == {"2"}


def test_another_loops_asker_is_never_handed_this_loops_answer():
    """Criterion 5, "keyed by loop". The same client asked from two event loops inside the window,
    as the tech-lead and the CLI do with an `asyncio.run` per question: two scans, and the second
    loop's rows are its own scan's. Passes on `main`; red under the cut that drops the loop from
    the key. Synchronous on purpose: the test owns both loops."""
    engine = CountedEngine()

    first = asyncio.run(tv.list_jobs(engine, "default"))
    second = asyncio.run(tv.list_jobs(engine, "default"))

    assert engine.scans == 2, f"two loops were answered by {engine.scans} scan(s)"
    assert scans_of(first) == {"1"}
    assert scans_of(second) == {"2"}


async def test_another_clients_asker_is_never_handed_this_clients_answer():
    """Criterion 5, "keyed by client". Two engines on one loop inside the window: each is scanned,
    and each asker reads its own engine's rows. Passes on `main`; red under the cut that drops the
    client from the key."""
    one, other = CountedEngine(), CountedEngine(issues=3)

    from_one = await tv.list_jobs(one, "default")
    from_other = await tv.list_jobs(other, "default")

    assert (one.scans, other.scans) == (1, 1)
    assert (len(from_one), len(from_other)) == (8, 3)


async def test_a_scan_that_failed_is_not_handed_to_the_next_asker():
    """Criterion 5, "a failure shared, never stored" (engineering-lessons §11). The first scan is
    refused; the next asker, inside the window, is scanned again and gets the rows. Passes on
    `main`; red under the cut that stores a failed scan."""
    engine = CountedEngine(failing=1)

    with pytest.raises(RuntimeError, match="the engine refused the listing"):
        await tv.list_jobs(engine, "default")
    rows = await tv.list_jobs(engine, "default")

    assert engine.scans == 2
    assert len(rows) == 8


#: The engine calls that change what a job list would read. A handle's `cancel` and `terminate`
#: are writes; an `asyncio.Task`'s `cancel` is not, which is why the receiver is checked too.
_WRITE_CALLS = {"signal", "start_workflow", "execute_workflow", "terminate", "cancel",
                "execute_update", "start_update", "start_update_with_start_workflow",
                "execute_update_with_start_workflow"}


def _writes_in_view() -> list[str]:
    """Every `async def` in `view.py` that makes a write call on the client or on a handle the
    client gave it (`client.get_workflow_handle(...)`, named or chained), read from the module's
    syntax tree."""
    tree = ast.parse(Path(inspect.getsourcefile(tv)).read_text(encoding="utf-8"))

    def a_handle(node) -> bool:
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get_workflow_handle")

    found = []
    for fn in tree.body:
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        engines = {"client"} | {
            target.id for node in ast.walk(fn) if isinstance(node, ast.Assign)
            and a_handle(node.value) for target in node.targets if isinstance(target, ast.Name)}
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _WRITE_CALLS
                    and (a_handle(node.func.value)
                         or isinstance(node.func.value, ast.Name)
                         and node.func.value.id in engines)):
                found.append(fn.name)
                break
    return found


_WRITES = _writes_in_view()

#: What each write is called with, by PARAMETER NAME, so the list of writes is the tree's alone:
#: an answer every gate in `CountedEngine` accepts.
_ARGUMENTS = {
    "project": PROJECT, "issue": WRITTEN, "unit": "web", "signal": "stop", "by": "a person",
    "version": "1.4.0", "approver": "a person", "comment": "", "answer": "merge",
    "instruction": "", "action": "resume", "choice": "",
    "params": SimpleNamespace(project=PROJECT, issue=WRITTEN, unit="web"),
}


def test_the_walk_finds_the_writes_view_makes():
    """The parametrization below is only as good as the walk: it must see a write on the client
    (a start) and a write on a handle (a signal), and not the reads that cancel their own tasks
    (`review_verdicts`) or list (`list_jobs`)."""
    assert "start_job" in _WRITES and "approve_job" in _WRITES, _WRITES
    assert "list_jobs" not in _WRITES and "review_verdicts" not in _WRITES, _WRITES


@pytest.mark.parametrize("write", _WRITES)
async def test_a_write_through_this_process_is_seen_by_the_next_list(write, monkeypatch):
    """Criterion 5 with the PO's Q2 default. A list, a write the engine accepts, and a list inside
    the window: the second list is a fresh scan. Passes on `main` (nothing is remembered); red
    under the cut that drops the forget from a write."""
    monkeypatch.setenv("OPENFACTORY_GATE_SECRET", "a gate key for this test only")
    engine = CountedEngine()
    fn = getattr(tv, write)
    kwargs = {}
    for name, parameter in list(inspect.signature(fn).parameters.items())[1:]:
        if name in _ARGUMENTS:
            kwargs[name] = _ARGUMENTS[name]
        elif parameter.default is inspect.Parameter.empty:
            pytest.fail(f"`{write}` takes `{name}`, which this test does not know how to answer: "
                        f"add it to _ARGUMENTS")

    await tv.list_jobs(engine, "default")
    await fn(engine, **kwargs)
    assert engine.writes, f"`{write}` returned without writing, so this case proves nothing"
    after = await tv.list_jobs(engine, "default")

    assert engine.scans == 2, f"the list after `{write}` was the one from before it"
    assert scans_of(after) == {"2"}
