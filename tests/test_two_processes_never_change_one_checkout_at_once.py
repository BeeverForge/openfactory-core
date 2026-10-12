"""Two processes that share a repository cache never change one checkout at the same time (#656).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640). On one machine the panel and the worker are
two processes, and both fall back to the same cache directory. The cache's lock was a
`threading.Lock`: it queued the threads of ONE process and nothing else. The panel answering a turn
and the worker breaking a requirement down synced one key at once, one `rmtree`-ed and re-cloned
the master the other was resetting, and git said "already exists and is not an empty directory".
Every fresh project got an impediment card, and two of four acceptances filed nothing.
`test_the_box_can_obtain_the_repository.py` had already met the same race between xdist workers,
and moved its tests to a root of their own rather than fix it.

THE RULE THIS FILE HOLDS, for every cache class (`RepoCache` and each subclass, found rather than
listed):
  1. while one process runs git on a key of a cache root, no other process runs git on that key;
  2. two different keys are not queued behind each other;
  3. a process killed in the middle of a sync leaves nothing for the next one to wait on;
  4. a sync that cannot have its key within its wait degrades, says so, and never hangs.

HOW IT IS SEEN WITHOUT LUCK. Each process is a real one (`spawn`), and the cache's two git runners
are wrapped in it. Every git command it runs writes a numbered `start` and `end` line, numbered by
one counter both processes share, so the order is the order it happened in, not a guess from
clocks. The first process stops at its first git command and waits to be released. The second is
started only then. On a lock that holds, the second cannot reach git while the first waits; on one
that does not, it reaches git within milliseconds, and the numbers show the overlap.
"""

from __future__ import annotations

import multiprocessing
import os
import subprocess
from pathlib import Path

import pytest

from openfactory.runtime import repo_cache
from openfactory.runtime.repo_cache import RepoCache

#: Every cache class, asked of the code: a cache added tomorrow falls under the rule without an edit
CACHES = [RepoCache, *RepoCache.__subclasses__()]
SPAWN = multiprocessing.get_context("spawn")
#: How long the parent lets the second process try while the first waits. On a lock that does not
#: hold it is in git within milliseconds; on one that does, no wait of any length lets it in.
TRY_SECONDS = 3
#: An upper bound on anything that should happen at once — a process starting, a sync finishing.
#: Reached only when something is broken.
BOUND = 120


@pytest.fixture
def origin(tmp_path):
    """A real bare repository with one commit, so a sync has something to clone."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "README.md").write_text("one\n")
    for args in (["init", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"], ["add", "-A"], ["commit", "-m", "one"]):
        subprocess.run(["git", *args], cwd=work, check=True, capture_output=True)
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "--bare", str(work), str(bare)], check=True,
                   capture_output=True)
    return str(bare)


def _syncing(kind: str, root: str, key: str, url: str, events: str, counter,
             entered, release, wait: float | None) -> None:
    """One process syncing `key`: every git command it runs is written down, numbered; when
    `release` is given, it stops at its first git command until released."""
    me = os.getpid()
    held = [release is None]

    def _say(what: str) -> None:
        with counter.get_lock():
            counter.value += 1
            with open(events, "a", encoding="utf-8") as fh:
                fh.write(f"{counter.value} {me} {what}\n")

    def _watched(real):
        def _run(*args, **kwargs):
            _say("start")
            entered.set()
            if not held[0]:
                held[0] = True
                release.wait(BOUND)
            try:
                return real(*args, **kwargs)
            finally:
                _say("end")
        return _run

    repo_cache._git = _watched(repo_cache._git)
    repo_cache._git_out = _watched(repo_cache._git_out)
    if wait is not None:
        repo_cache._LOCK_WAIT_SECONDS = wait
    got = getattr(repo_cache, kind)(Path(root)).sync(key, url)
    _say("synced" if got else "failed")


class _Run:
    """The events of one run, read back in the order the shared counter gave them."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def lines(self) -> list[tuple[int, int, str]]:
        if not self.path.exists():
            return []
        rows = [line.split() for line in self.path.read_text(encoding="utf-8").splitlines()]
        return sorted((int(n), int(pid), what) for n, pid, what in rows)

    def span(self, pid: int) -> tuple[int, int]:
        """From the first git command `pid` started to the last one it ended."""
        mine = [n for n, who, what in self.lines() if who == pid and what in ("start", "end")]
        return min(mine), max(mine)

    def inside(self, pid: int, other: int) -> list[tuple[int, int, str]]:
        """`other`'s git commands numbered inside `pid`'s span."""
        first, last = self.span(pid)
        return [row for row in self.lines()
                if row[1] == other and row[2] in ("start", "end") and first < row[0] < last]

    def said(self, pid: int) -> str:
        ends = [what for _n, who, what in self.lines() if who == pid and what in ("synced",
                                                                                  "failed")]
        return ends[-1] if ends else "nothing"


def _two(tmp_path, kind: str, first_key: str, second_key: str, origin: str, *,
         kill_first: bool = False, second_wait: float | None = None):
    """The first process stops at its first git command; the second is started then, given
    `TRY_SECONDS` to reach git, and the first is then released (or killed)."""
    run = _Run(tmp_path / "events")
    counter = SPAWN.Value("i", 0)
    first_in, first_go, second_in = SPAWN.Event(), SPAWN.Event(), SPAWN.Event()
    root = str(tmp_path / "cache")
    first = SPAWN.Process(target=_syncing, args=(kind, root, first_key, origin, str(run.path),
                                                 counter, first_in, first_go, None))
    first.start()
    assert first_in.wait(BOUND), "the first process never reached git"
    second = SPAWN.Process(target=_syncing, args=(kind, root, second_key, origin, str(run.path),
                                                  counter, second_in, None, second_wait))
    second.start()
    reached = None
    if second_wait is not None:
        second.join(BOUND)      # it gives up while the first still holds the key
    else:
        reached = second_in.wait(TRY_SECONDS)
    if kill_first:
        first.kill()
    else:
        first_go.set()
    second.join(BOUND)
    first.join(BOUND)
    assert second.exitcode == 0, f"the second process ended with {second.exitcode}"
    return run, first.pid, second.pid, reached


# ── 1. one key, one process at a time ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("cache", CACHES, ids=lambda c: c.__name__)
def test_TODAYS_RUN_a_second_process_waits_for_the_key_the_first_is_changing(tmp_path, origin,
                                                                             cache):
    """The panel and the worker, one key: the second runs no git until the first has finished."""
    run, first, second, _ = _two(tmp_path, cache.__name__, "jornada", "jornada", origin)

    overlap = run.inside(first, second)
    assert not overlap, (
        f"the second process ran git on the key while the first was changing it: {overlap} "
        f"inside {run.span(first)}; all events: {run.lines()}")
    assert run.said(first) == "synced" and run.said(second) == "synced", run.lines()


# ── 2. two keys are not queued behind each other ───────────────────────────────────────────────

def test_two_keys_are_changed_at_once(tmp_path, origin):
    """A product's sources are synced by several processes at once; the lock is per key, and a
    lock per root would queue every source behind the slowest."""
    run, first, second, reached = _two(tmp_path, "RepoCache", "web", "api", origin)

    assert reached, "a process syncing another key waited for the first: the lock is not per key"
    assert run.inside(first, second), run.lines()
    assert run.said(first) == "synced" and run.said(second) == "synced", run.lines()


# ── 3. a holder that dies leaves nothing to wait on ────────────────────────────────────────────

def test_a_process_killed_in_the_middle_leaves_nothing_to_wait_on(tmp_path, origin):
    """The worker is restarted in the middle of a sync: the next process has the key at once,
    because the kernel lets go of what a dead process held, and nothing on disk says otherwise."""
    run, first, second, _ = _two(tmp_path, "RepoCache", "jornada", "jornada", origin,
                                 kill_first=True)

    assert run.said(first) == "nothing", run.lines()
    assert run.said(second) == "synced", f"the next sync did not have the key: {run.lines()}"


# ── 4. a wait that runs out degrades, and never hangs ──────────────────────────────────────────

@pytest.mark.parametrize("cache", CACHES, ids=lambda c: c.__name__)
def test_a_sync_that_cannot_have_the_key_in_time_degrades(tmp_path, origin, cache):
    """A sync whose key is held past its wait returns nothing, as any failed sync does, and its
    caller degrades; it does not wait for ever behind a holder that hung."""
    run, first, second, _ = _two(tmp_path, cache.__name__, "jornada", "jornada", origin,
                                 second_wait=0.5)

    assert run.said(second) == "failed", run.lines()
    assert not [row for row in run.lines() if row[1] == second and row[2] == "start"], (
        f"the process that could not have the key ran git on it anyway: {run.lines()}")
    assert run.said(first) == "synced", run.lines()
