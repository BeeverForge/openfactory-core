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
  walking `view.py`, not listed here, so a write added later is held without anybody remembering;
  the panel's Stop and Scan, which write through `actions.catalog` instead, are held by name.

- ANOTHER QUESTION, A COPY OF ITS OWN, AND THE BREAKER FIRST: the key is the question too, an
  asker inside the window may edit its rows without editing the next asker's, and an engine
  remembered as silent refuses the list even while one is remembered (the PO's Q5).

The first test is red on `main` (two scans where one is required). The others pass there — there
is no shared answer to serve wrongly — and are what the mutation plan's "the key forgets the loop /
the client / the question", "the window never ends", "the remembered rows themselves", "a failure
is stored", "a scan that lost the slot is stored", "the breaker is not asked" and "a write forgets
nothing" cuts turn red (`tools/mutations/754_the_job_list_is_asked_side_by_side_and_shared.py`).

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
from openfactory.runtime.temporal.vocabulary import EngineUnreachable
from tests.job_list_scans import PROJECT, RECENT, WRITTEN, CountedEngine, forget, scans_of

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


async def test_every_asker_right_after_is_handed_a_list_of_its_own(clock):
    """Criterion 5 with #165's copy: the callers annotate rows before rendering, so a remembered
    list handed out by reference is one the first asker inside the window rewrites for every asker
    after it. Two askers inside the window; the first edits a row and drops one; the second reads
    the list as the engine gave it. Passes on HEAD; red under the cut that hands out the
    remembered rows themselves (the shared scan's own copy does not reach this path)."""
    engine = CountedEngine()

    await tv.list_jobs(engine, "default")
    clock.now += 0.5
    mine = await tv.list_jobs(engine, "default")
    as_given = mine[0]["state"]
    mine[0]["state"] = "edited by one caller"
    mine.pop()
    clock.now += 0.5
    theirs = await tv.list_jobs(engine, "default")

    assert engine.scans == 1
    assert theirs[0]["state"] == as_given == "running"
    assert len(theirs) == 8


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


async def test_an_asker_with_another_question_right_after_is_scanned_for_it(clock, monkeypatch):
    """Criterion 5's key is the question as well (engineering-lessons §11: what a cache is keyed on
    has to be what the work it skips would have read). Inside the window, a smaller `limit`, a
    start-time `query` and another namespace each get a scan of their own and the answer to their
    own question. Passes on HEAD; red under the cut that drops the question from the remembered
    list's key: every asker after the first is handed the first's eight rows, one scan in all. A
    UI address, so each row's link names the namespace it was read in."""
    monkeypatch.setattr(tv, "ui_base", lambda: "http://engine-ui.example")
    engine = CountedEngine()

    await tv.list_jobs(engine, "default")
    five = await tv.list_jobs(engine, "default", limit=5)
    recent = await tv.list_jobs(engine, "default", query=RECENT)
    elsewhere = await tv.list_jobs(engine, "elsewhere")

    assert engine.scans == 4, f"four questions in one window were answered by {engine.scans} scans"
    assert (len(five), len(recent)) == (5, 2)
    assert all("/namespaces/elsewhere/" in r["temporal_url"] for r in elsewhere)


async def test_a_scan_in_flight_across_a_write_is_not_handed_to_the_next_asker(clock):
    """Criterion 5 with the PO's Q2 default, the race the parametrized write test cannot see. A
    list is under way when a write goes through this process; that list's own asker keeps its
    answer, and the next asker inside the window is scanned afresh, because the rows were read
    before the write. Passes on HEAD; red under the cuts that store a scan whose slot a forget took
    (`holds` not asked) and that leave the scan in flight in the slot when the list is forgotten:
    either way the pre-write list fills the window, one scan in all."""
    engine = CountedEngine()

    before = asyncio.create_task(tv.list_jobs(engine, "default"))
    while engine.scans == 0:
        await asyncio.sleep(0)
    await tv.act_job(engine, PROJECT, WRITTEN, action="resume")
    assert engine.writes, "the write was not made, so this case proves nothing"
    assert scans_of(await before) == {"1"}
    after = await tv.list_jobs(engine, "default")

    assert engine.scans == 2, "the list read before the write was handed out after it"
    assert scans_of(after) == {"2"}


async def test_an_engine_remembered_as_silent_refuses_a_list_remembered_before_it(clock):
    """The breaker is asked before the remembered list, as `@_bounded_read` asked it before the
    read (the PO's Q5, default): an engine that just ran out of time refuses every reader for
    `OPENFACTORY_ENGINE_UNREACHABLE_FOR`, in `_within`'s own sentence, and a list read before the
    silence is not handed out as if the engine had answered. Passes on HEAD; red under the cut that
    drops the breaker check from `list_jobs` (the list inside the window is returned)."""
    engine = CountedEngine()

    await tv.list_jobs(engine, "default")
    tv._did_not_answer()

    with pytest.raises(EngineUnreachable, match="did not answer the job list a moment ago"):
        await tv.list_jobs(engine, "default")
    assert engine.scans == 1


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


async def test_a_write_that_raised_after_the_engine_took_it_still_drops_the_list():
    """Criterion 5, `_a_write`'s "on every exit, not only a return": a Resume whose signal the
    engine took but whose reply the transport lost raises, and the list after it is still a fresh
    scan, since the job did change. Every case above succeeds, so a `_a_write` that forgot only
    after a return (`answer = await fn(...); forget_jobs(); return answer`) kept them green: the
    review of 9e282ff measured 70 passed under that cut, and this test red (`assert 1 == 2`)."""
    engine = CountedEngine()
    real = engine.get_workflow_handle

    def handle(wf_id, run_id=None):
        h = real(wf_id, run_id)
        signal = h.signal

        async def lost(*a, **k):
            await signal(*a, **k)
            raise RuntimeError("the transport gave up on the reply")

        h.signal = lost
        return h

    await tv.list_jobs(engine, "default")
    engine.get_workflow_handle = handle
    with pytest.raises(RuntimeError, match="gave up on the reply"):
        await tv.act_job(engine, PROJECT, WRITTEN, action="resume")
    assert engine.writes, "the resume raised before it wrote, so this case proves nothing"
    engine.get_workflow_handle = real
    after = await tv.list_jobs(engine, "default")

    assert engine.scans == 2, "the list after a write that raised was the one from before it"
    assert scans_of(after) == {"2"}


# ── the panel's own writes, outside `view.py` ──────────────────────────────────────────────────
#
# The walk above reads `view.py` alone. Two buttons write `JobWorkflow`s from the panel's process
# through the action catalogue instead: Stop (`catalog._stop`, a handle's `terminate`) and Scan
# TO-DO now (`catalog._scan`, `client.start_workflow`), which the panel follows with a re-read of
# `/api/temporal/jobs` 600 ms later (`panel.html`). Measured at review on 9e282ff: the list after
# Stop was the one from before it (`assert 1 == 2` scans). They are held here by name.

class _Tracker:
    """The ticket `_stop` settles, at a state the door accepts; every write a no-op."""

    def get_ticket(self, ref):
        return SimpleNamespace(state="open", title="t", raw="")

    def set_state(self, ref, state, reason=None, **_kw):
        pass

    def comment(self, ref, body):
        pass


class _Board:
    """One card in TO-DO, so `_scan` has exactly one job to start."""

    def pickup_column(self) -> str:
        return "TO-DO"

    def items_in_status(self, status: str) -> list[str]:
        return [WRITTEN]


def _a_panel_admin():
    from openfactory.actions.base import Actor

    return Actor(id="rob", display="Rob", via="panel", admin=True)


def _engine_through_the_catalogue(monkeypatch, engine: CountedEngine) -> None:
    from openfactory.actions import catalog

    async def connected():
        return engine, None

    monkeypatch.setattr(catalog, "_connected", connected)


async def test_the_panels_stop_is_seen_by_the_next_list(monkeypatch):
    """Criterion 5 with the PO's Q2 default, for the panel's Stop. A list, a Stop the engine
    takes, and a list inside the window: the second list is a fresh scan. Red on 9e282ff (the
    list after the Stop was the one from before it, 1 scan where 2 are required)."""
    from openfactory.actions import catalog

    engine, terminated = CountedEngine(), []
    real = engine.get_workflow_handle

    def handle(wf_id, run_id=None):
        h = real(wf_id, run_id)

        async def terminate(reason=""):
            terminated.append(wf_id)

        h.terminate = terminate
        return h

    engine.get_workflow_handle = handle
    _engine_through_the_catalogue(monkeypatch, engine)
    monkeypatch.setattr(catalog, "_board_pair",
                        lambda name: (SimpleNamespace(name=PROJECT), _Tracker(), None, None))

    await tv.list_jobs(engine, "default")
    out = await catalog._stop(by=_a_panel_admin(), project=PROJECT, issue="3")
    assert terminated, f"the Stop never reached the engine, so this proves nothing: {out.message}"
    after = await tv.list_jobs(engine, "default")

    assert engine.scans == 2, "the list after the panel's Stop was the one from before it"
    assert scans_of(after) == {"2"}


async def test_the_panels_scan_is_seen_by_the_next_list(monkeypatch):
    """Criterion 5 with the PO's Q2 default, for the panel's Scan TO-DO now. A list, a scan that
    starts the one TO-DO card, and a list inside the window: the second list is a fresh scan. The
    button's own floor count is a listing too (scan 2), so the list after it must be scan 3. Red
    on 9e282ff (the list after the Scan was scan 1's)."""
    from openfactory.actions import catalog
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.registry import ProjectRegistry

    project = Project(name=PROJECT, repo_path="/tmp/books",
                      tracker=ProviderRef(kind="github", repo="o/books",
                                          options={"board_owner": "o", "board_number": "1"}))
    monkeypatch.setattr(ProjectRegistry, "get", lambda self, name: project)
    monkeypatch.setattr("openfactory.credentials.tracker_token", lambda: "tok")
    monkeypatch.setattr("openfactory.factory.resolve_box_image", lambda *_a, **_kw: "an-image")
    monkeypatch.setattr("openfactory.adapters.board.build_board", lambda *_a, **_kw: _Board())
    monkeypatch.setattr("openfactory.runtime.temporal.max_concurrent_jobs", lambda: 100)
    engine = CountedEngine()
    _engine_through_the_catalogue(monkeypatch, engine)

    await tv.list_jobs(engine, "default")
    out = await catalog._scan(by=_a_panel_admin(), project=PROJECT)
    assert engine.writes == [("start", tv.job_id(PROJECT, WRITTEN))], (
        f"the Scan started nothing, so this proves nothing: {out.message}")
    after = await tv.list_jobs(engine, "default")

    assert engine.scans == 3, "the list after the panel's Scan was the one from before it"
    assert scans_of(after) == {"3"}
