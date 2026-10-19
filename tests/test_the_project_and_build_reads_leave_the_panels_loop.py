"""The floor's project and build reads do not run on the loop that serves the panel (#748).

Reported 2026-10-14 by a deployment running a worktree box with about nineteen projects: the panel stopped
answering for seconds at a time, and the engine reads that now time out after 3 s reported that
the engine did not answer. `floor/reading.py::gather` (lines 97-100 at `82500f9`) called
`got.projects = _projects()` and `got.build = _build()` without leaving the loop, and `gather` is
awaited on the panel's only event loop by `/api/v1/floor` and its aliases (`api/app.py:1335`), on
the standing loop by the product read model (`product/model.py:813`), and inside `asyncio.run` by
`openfactory floor` (`cli.py:2269`).

The read blocks once per registered project. `_projects` (`reading.py:516`) calls
`box_prove.health(p)` for each, and that call goes on:

    health → gate_reason (box_prove.py:1629) → load_manifest (loader.py:34)
           → factory.resolve_repo_path → repo_cache sync: git ls-remote --symref, fetch,
             reset --hard (repo_cache.py:175/383/386), under a flock
    then   _current_digest: `docker image inspect`, up to 2 processes, 60 s each (box_prove.py:1462)
    or     _machine_version: `<harness> --version`, 30 s (box_prove.py:1582), on an image-less box

`_build` (`namespace.py:245`) reads the build stamps off the state volume: cheap, but blocking.

Measured on `82500f9` with this file (2026-10-18): nineteen projects whose box read blocks 30 ms
each held the loop for 588 ms in one piece (616 ms on a second run; 19 x 30 ms = 570 ms) — every
other request, both SSE streams and the socket waited that long, and a real forge round trip per
project makes it seconds.

WHAT IS DOUBLED: `reading._projects` and `reading._build` for the thread tests, by a blocking call
that says which thread it ran on; and, for the loop-keeps-serving test, only
`openfactory.box_prove.health` — by a 30 ms blocking call answering a proven box, the way
`test_a_read_that_failed_is_not_an_empty_floor.py` doubles it. Everything else is the real thing:
the real `gather`, the real `_projects` over a real registry file of nineteen projects, and for
the CLI's path the real `asyncio.run`.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import threading
import time
from datetime import UTC, datetime

import pytest
import yaml

from openfactory.floor import reading

#: What one project's box read blocks for in the doubles: a forge round trip is longer, so this
#: is the kind case. And what "the loop kept serving" allows on eight shared cores (#241's number).
_READ_S = 0.03
_A_TICK_IS_LATE_BY = 0.15
_HANGS_AFTER = 6.0

#: The reporter's deployment.
_PROJECTS = 19

T0 = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)

PROJECTS = [{"name": "acme", "enabled": True,
             "box": {"state": "proven", "gate": "", "detail": ""}}]
BUILD = {"agree": True, "stamps": {"panel": "0.7.0", "worker": "0.7.0"}}


class _Read:
    """`reading._projects` or `reading._build`, doubled: it blocks a real thread for `_READ_S`,
    records which one, and answers a copy of `answer`. It never waits on an event, so no worker
    thread is left blocked behind a test."""

    def __init__(self, answer):
        self.answer = answer
        self.threads: list[int] = []

    def __call__(self):
        self.threads.append(threading.get_ident())
        time.sleep(_READ_S)
        return reading.copy.deepcopy(self.answer)


async def _watched(coro):
    """Run `coro` with a 10 ms heartbeat already ticking on this loop; answer the longest gap it
    suffered, which is what everything else the panel serves would have waited."""
    gaps: list[float] = []
    stop = asyncio.Event()

    async def beat():
        last = time.monotonic()
        while not stop.is_set():
            await asyncio.sleep(0.01)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    beating = asyncio.ensure_future(beat())
    await asyncio.sleep(0.05)
    try:
        got = await asyncio.wait_for(coro, _HANGS_AFTER)
    finally:
        stop.set()
        await beating
    return got, max(gaps)


# ── 1. off the loop's own thread ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_project_read_does_not_run_on_the_loops_own_thread(monkeypatch):
    made = _Read(PROJECTS)
    monkeypatch.setattr(reading, "_projects", made)

    await reading.gather(want=("projects",), now=T0)

    assert made.threads and made.threads[0] != threading.get_ident(), (
        "the box read — git, `docker image inspect` and `<harness> --version` once per registered "
        "project — ran on the thread that serves the panel")


@pytest.mark.asyncio
async def test_the_build_read_does_not_run_on_the_loops_own_thread(monkeypatch):
    made = _Read(BUILD)
    monkeypatch.setattr(reading, "_build", made)

    await reading.gather(want=("build",), now=T0)

    assert made.threads and made.threads[0] != threading.get_ident(), (
        "the build stamps were read off the state volume on the thread that serves the panel")


def test_the_CLIs_floor_path_reads_the_projects_off_its_loop_too(monkeypatch):
    """`openfactory floor` has no loop of its own: it runs `asyncio.run(floor.gather(...))`, which
    is a loop, and the product read model runs `gather` on the standing loop the same way. The
    read must leave whichever loop awaits it."""
    projects, build = _Read(PROJECTS), _Read(BUILD)
    monkeypatch.setattr(reading, "_projects", projects)
    monkeypatch.setattr(reading, "_build", build)

    asyncio.run(reading.gather(want=("projects", "build"), now=T0))

    here = threading.get_ident()
    assert projects.threads and projects.threads[0] != here, (
        "under `asyncio.run` the box read ran on the loop's thread")
    assert build.threads and build.threads[0] != here, (
        "under `asyncio.run` the build stamps were read on the loop's thread")


def _sync_readers_called_bare_in_gather() -> list[str]:
    """Every call, inside `gather`, to a synchronous top-level function of `reading`, made on the
    loop rather than handed to `asyncio.to_thread`. Parsed from the module's source, so a comment
    that names `_projects()` cannot satisfy or trip it."""
    tree = ast.parse(inspect.getsource(reading))
    sync = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    gather = next(n for n in tree.body
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "gather")

    def is_to_thread(call: ast.Call) -> bool:
        f = call.func
        return (isinstance(f, ast.Attribute) and f.attr == "to_thread"
                and isinstance(f.value, ast.Name) and f.value.id == "asyncio")

    # A lambda handed to `to_thread` runs in the worker thread, so a call inside it is not on the
    # loop. `asyncio.to_thread(_projects())` is: the call is evaluated before `to_thread` is.
    off_the_loop: set[int] = set()
    for node in ast.walk(gather):
        if isinstance(node, ast.Call) and is_to_thread(node):
            for arg in node.args[:1]:
                if isinstance(arg, ast.Lambda):
                    off_the_loop.update(id(n) for n in ast.walk(arg.body))

    found = []
    for node in ast.walk(gather):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in sync and id(node) not in off_the_loop):
            found.append(f"reading.py:{node.lineno}: {ast.unparse(node)}")
    return found


def test_gather_calls_no_synchronous_reader_of_this_module_bare():
    """For a field added later. This is the second time a blocking reader was called on the loop
    from `gather` (the budget was the first, #240/#241): every synchronous function of this module
    that `gather` reaches goes through `asyncio.to_thread`."""
    bare = _sync_readers_called_bare_in_gather()

    assert not bare, (
        "`gather` runs on the panel's loop, and calls these synchronous readers on it rather than "
        "through `asyncio.to_thread`: " + "; ".join(bare))


# ── 2. the loop keeps serving ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_and_the_loop_keeps_SERVING_while_every_projects_box_is_read(monkeypatch, tmp_path):
    reg = tmp_path / "registry.yaml"
    reg.write_text(yaml.safe_dump({"projects": {
        f"p{i:02d}": {"name": f"p{i:02d}", "repo_path": f"/work/p{i:02d}", "enabled": True,
                      "tracker": {"kind": "local", "repo": f"p{i:02d}"},
                      "forge": {"kind": "local", "repo": f"p{i:02d}"},
                      "ci": {"kind": "none", "repo": f"p{i:02d}"}}
        for i in range(_PROJECTS)}}))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(reg))

    def health(_p):
        time.sleep(_READ_S)        # one project's git, `docker image inspect`, `--version`
        return {"state": "proven", "gate": "", "detail": ""}

    monkeypatch.setattr("openfactory.box_prove.health", health)

    got, worst = await _watched(reading.gather(want=("projects",), now=T0))

    assert got.projects is not None and len(got.projects) == _PROJECTS, got.projects
    assert worst < _A_TICK_IS_LATE_BY, (
        f"a task on the panel's loop waited {worst * 1000:.0f} ms while {_PROJECTS} projects' "
        f"boxes were read at {_READ_S * 1000:.0f} ms each — every other request, both SSE streams "
        f"and the socket waited with it")


# ── 3. the answer is unchanged ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_floor_read_still_ANSWERS_with_projects_and_build_on_it(monkeypatch):
    """The whole `gather`, as `/api/floor` asks for the slow tier: the reads moving off the loop
    must not drop what they read."""
    monkeypatch.setattr(reading, "_projects", _Read(PROJECTS))
    monkeypatch.setattr(reading, "_build", _Read(BUILD))

    got = await reading.gather(want=("projects", "build"), now=T0)

    assert got.projects == PROJECTS, "the box read left the loop and its answer was dropped"
    assert got.build == BUILD, "the build read left the loop and its answer was dropped"


@pytest.mark.asyncio
async def test_an_UNREADABLE_registry_is_still_None_when_read_off_the_loop(monkeypatch):
    """`[]` tells the floor there are no projects — a claim — on exactly the failure where the
    honest answer is that we could not look (engineering-lessons §2). Driven through `gather`, so
    it holds wherever the read runs."""

    class _Boom:
        def list(self):
            raise RuntimeError("registry unreadable")

    monkeypatch.setattr("openfactory.registry.ProjectRegistry", _Boom)

    got = await reading.gather(want=("projects",), now=T0)

    assert got.projects is None, (
        f"an unreadable registry reported {got.projects!r} — a deployment with no projects")
