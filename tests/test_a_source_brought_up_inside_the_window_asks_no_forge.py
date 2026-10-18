"""A source brought up inside the freshness window is served as it was, and asks its forge nothing
(#369, criterion 3).

An unmoved source already cost one question (#372): the `ls-remote` that names the branch also says
where it is, and a master standing there is not fetched or checked out. One question per source is
still N round trips per message, before the role says a word — at a few hundred sources, a few
hundred. A source the product role brought up less than `fresh_for` seconds ago is now served
without starting any git process; the first sync after the window asks the forge again.

What is pinned, against real git over `file://` and a clock the test holds (no sleep):

  1. inside the window no git process starts, and what the cone left out is still said;
  2. a commit pushed inside the window is served on the first sync after it;
  3. a window is never left behind by a sync that did not finish, or that failed;
  4. a stamp from the future (a clock that went back, a skewed volume) opens no window;
  5. a window of zero asks every time, and the window is kept per branch asked for;
  6. a served tree that is gone is brought up again, window or not, and a root where no stamp
     can be written serves the source and only loses the window;
  7. the window is the operator's, `OPENFACTORY_SOURCES_FRESH_SECONDS`.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from openfactory.product import sources
from openfactory.runtime import repo_cache
from openfactory.runtime.repo_cache import SparseRepoCache

KEY = "acme--source--lib"
T0 = 1_800_000_000.0


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}).stdout


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


@pytest.fixture()
def origin(tmp_path) -> Path:
    """A repository serving partial clones: code on `main`, a picture its cone leaves out, and a
    `develop` that says something else."""
    repo = tmp_path / "origin"
    (repo / "lib").mkdir(parents=True)
    (repo / "lib" / "core.py").write_text("ANSWER = 1\n")
    (repo / "assets").mkdir()
    (repo / "assets" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
    _git(repo, "init", "-q", "-b", "main")
    for key, value in (("user.name", "fixture"), ("user.email", "fixture@example.invalid"),
                       ("commit.gpgsign", "false"), ("uploadpack.allowFilter", "true"),
                       ("uploadpack.allowAnySHA1InWant", "true")):
        _git(repo, "config", key, value)
    _commit(repo, "main")
    _git(repo, "checkout", "-q", "-b", "develop")
    (repo / "lib" / "core.py").write_text("ANSWER = 2  # develop\n")
    _commit(repo, "develop")
    _git(repo, "checkout", "-q", "main")
    return repo


class _Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def clock() -> _Clock:
    return _Clock()


@pytest.fixture()
def git_calls(monkeypatch) -> dict[str, int]:
    """Every git subcommand `repo_cache` starts from here on, counted."""
    counts: dict[str, int] = {}
    real = repo_cache.subprocess.run

    def counting(args, *a, **kw):
        if isinstance(args, (list, tuple)) and args and args[0] == "git":
            sub = next(x for x in args[1:] if not str(x).startswith("-"))
            counts[sub] = counts.get(sub, 0) + 1
        return real(args, *a, **kw)

    monkeypatch.setattr(repo_cache.subprocess, "run", counting)
    return counts


def _cache(tmp_path: Path, clock: _Clock, fresh_for: float = 60) -> SparseRepoCache:
    return SparseRepoCache(tmp_path / "cache", fresh_for=fresh_for, clock=clock)


def _sync(tmp_path, clock, at: float, url: str, branch: str = "", fresh_for: float = 60):
    clock.now = at
    cache = _cache(tmp_path, clock, fresh_for)
    return cache, cache.sync(KEY, url, branch)


def test_a_second_sync_inside_the_window_starts_no_git_process_and_one_after_it_asks_the_forge(
        tmp_path, origin, clock, git_calls):
    url = f"file://{origin}"
    first, served = _sync(tmp_path, clock, T0, url)
    assert served is not None and first.left_out == ["assets"] and first.partial
    git_calls.clear()

    inside, again = _sync(tmp_path, clock, T0 + 59, url)

    assert again == served and (again / "lib" / "core.py").is_file()
    assert git_calls == {}, git_calls
    assert (inside.left_out, inside.partial) == (first.left_out, first.partial)

    after, _ = _sync(tmp_path, clock, T0 + 60, url)

    assert git_calls.get("ls-remote") == 1, git_calls
    assert (after.left_out, after.partial) == (first.left_out, first.partial)


def test_a_commit_pushed_inside_the_window_is_served_on_the_first_turn_after_it(
        tmp_path, origin, clock):
    url = f"file://{origin}"
    _sync(tmp_path, clock, T0, url)
    (origin / "lib" / "core.py").write_text("ANSWER = 3\n")
    _commit(origin, "moved inside the window")

    _, inside = _sync(tmp_path, clock, T0 + 30, url)
    assert (inside / "lib" / "core.py").read_text() == "ANSWER = 1\n"

    _, after = _sync(tmp_path, clock, T0 + 61, url)
    assert (after / "lib" / "core.py").read_text() == "ANSWER = 3\n"


def test_a_sync_that_did_not_finish_leaves_no_window_behind(tmp_path, origin, clock, git_calls,
                                                            monkeypatch):
    """A sync that changed the master and died before serving it must not leave the last good
    sync's window open over a master that now stands somewhere else."""
    url = f"file://{origin}"
    _sync(tmp_path, clock, T0, url)

    def dies(*_a, **_kw):
        raise OSError("killed while publishing")

    with monkeypatch.context() as patch:
        patch.setattr(SparseRepoCache, "_publish", dies)
        _, broken = _sync(tmp_path, clock, T0 + 1, url, "develop")
    assert broken is None
    git_calls.clear()

    _sync(tmp_path, clock, T0 + 2, url)

    assert git_calls.get("ls-remote", 0) >= 1, git_calls


def test_a_failed_sync_opens_no_window(tmp_path, origin, clock, git_calls):
    """"Could not reach the forge" is asked again on the next turn — a failure is never cached."""
    url = f"file://{origin}"
    _sync(tmp_path, clock, T0, url)
    away = origin.rename(tmp_path / "away")     # the forge is gone for one turn
    _, failed = _sync(tmp_path, clock, T0 + 61, url)
    away.rename(origin)
    assert failed is None
    git_calls.clear()

    _, served = _sync(tmp_path, clock, T0 + 62, url)

    assert served is not None
    assert git_calls.get("ls-remote") == 1, git_calls


def test_a_stamp_from_the_future_opens_no_window(tmp_path, origin, clock, git_calls):
    """The clock went back, or another machine on a shared volume runs ahead: a stamp later than
    now says nothing about how fresh the source is."""
    url = f"file://{origin}"
    _sync(tmp_path, clock, T0, url)
    git_calls.clear()

    _sync(tmp_path, clock, T0 - 10, url)

    assert git_calls.get("ls-remote") == 1, git_calls


def test_a_window_of_zero_asks_the_forge_every_time(tmp_path, origin, clock, git_calls):
    url = f"file://{origin}"
    _sync(tmp_path, clock, T0, url, fresh_for=0)
    git_calls.clear()

    _sync(tmp_path, clock, T0 + 1, url, fresh_for=0)
    _sync(tmp_path, clock, T0 + 2, url, fresh_for=0)

    assert git_calls.get("ls-remote") == 2, git_calls


def test_the_window_is_kept_per_ask_so_another_branch_is_never_served_from_it(
        tmp_path, origin, clock, git_calls):
    url = f"file://{origin}"
    _sync(tmp_path, clock, T0, url)
    git_calls.clear()

    _, served = _sync(tmp_path, clock, T0 + 1, url, "develop")

    assert git_calls.get("ls-remote") == 1, git_calls
    assert (served / "lib" / "core.py").read_text() == "ANSWER = 2  # develop\n"


def test_a_served_tree_that_is_gone_is_brought_up_again_inside_the_window(tmp_path, origin,
                                                                         clock):
    url = f"file://{origin}"
    _, served = _sync(tmp_path, clock, T0, url)
    shutil.rmtree(served)

    _, again = _sync(tmp_path, clock, T0 + 1, url)

    assert again is not None and (again / "lib" / "core.py").read_text() == "ANSWER = 1\n"


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root writes through a read-only directory, so nothing is refused")
def test_a_root_where_no_window_can_be_written_still_serves_and_asks_the_forge_next_time(
        tmp_path, origin, clock, git_calls):
    """A full or read-only volume costs the window, never the source: the sync serves, and the
    next turn asks the forge as it did before there was a window."""
    url = f"file://{origin}"
    fresh = tmp_path / "cache" / repo_cache._FRESH_DIRNAME
    fresh.mkdir(parents=True)
    fresh.chmod(0o500)
    try:
        _, served = _sync(tmp_path, clock, T0, url)
        assert served is not None and (served / "lib" / "core.py").is_file()
        git_calls.clear()

        _, again = _sync(tmp_path, clock, T0 + 1, url)
    finally:
        fresh.chmod(0o700)

    assert again == served
    assert git_calls.get("ls-remote") == 1, git_calls
    assert list(fresh.iterdir()) == [], "a half-written stamp was left behind"


# ── the window is the operator's ───────────────────────────────────────────────────────────────

def test_the_window_is_the_operators_and_unset_is_the_default(monkeypatch):
    monkeypatch.delenv("OPENFACTORY_SOURCES_FRESH_SECONDS", raising=False)
    assert sources.fresh_for() == sources.DEFAULT_FRESH_SECONDS

    monkeypatch.setenv("OPENFACTORY_SOURCES_FRESH_SECONDS", "5")
    assert sources.fresh_for() == 5

    monkeypatch.setenv("OPENFACTORY_SOURCES_FRESH_SECONDS", "0")
    assert sources.fresh_for() == 0


@pytest.mark.parametrize("value", ["soon", "-1"])
def test_a_window_nobody_can_read_is_the_default_and_is_said_once(monkeypatch, caplog, value):
    monkeypatch.setattr(sources, "_FRESH_SAID", set(), raising=False)
    monkeypatch.setenv("OPENFACTORY_SOURCES_FRESH_SECONDS", value)
    caplog.set_level(logging.WARNING, logger="openfactory.product")

    got = [sources.fresh_for(), sources.fresh_for()]

    assert got == [sources.DEFAULT_FRESH_SECONDS] * 2
    named = [r.getMessage() for r in caplog.records
             if "OPENFACTORY_SOURCES_FRESH_SECONDS" in r.getMessage()]
    assert len(named) == 1, named
    assert repr(value) in named[0] and str(sources.DEFAULT_FRESH_SECONDS) in named[0]
