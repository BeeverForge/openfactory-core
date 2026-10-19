"""A crashed job's marker stops holding the cache's served tree after a day (#747).

A job that dies without `cleanup` — a killed worker, a host that rebooted — leaves its worktree
directory and its marker on disk, and git never prunes a tree whose directory is still there. If
the marker held for ever, that key's served tree, and the manifest and preflight code read from it,
would never advance. So a marker older than `JOB_MARKER_MAX_AGE` (a day) no longer holds, and the
sync says it passed one over ("bounds are logged when hit", engineering lessons). The day is longer
than the longest job the default timeouts allow, so a live job is never stripped of its hold.

The age is the marker file's mtime, set here with `os.utime`: no sleeping, and no patched clock the
cache does not read.
"""

from __future__ import annotations

import logging
import os
import time

import pytest

from openfactory.runtime.repo_cache import RepoCache
from tests.test_a_cache_sync_never_pulls_the_git_directory_out_from_under_a_running_job import (
    Origin,
    _answers,
    _head,
    _job,
    _marker,
)

DAY = 24 * 60 * 60


@pytest.fixture
def origin(tmp_path) -> Origin:
    return Origin(tmp_path)


def _aged(marker, seconds: float) -> None:
    then = time.time() - seconds
    os.utime(marker, (then, then))


def test_a_marker_older_than_a_day_no_longer_holds_the_served_tree_and_says_so(
        tmp_path, origin, caplog):
    """C5, over the bound: the sync publishes the moved base, and a line names the worktree whose
    stale marker it passed over. Before the fix the publish happened too (nothing held anything),
    but nothing was said: the log assertion is what fails there."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    _, ws = _job(tmp_path, served, origin)
    marker = _marker(ws.path)
    if marker.exists():
        # the marker's existence is held by the box's own tests; here only its age matters
        _aged(marker, DAY + 60)

    tip = origin.advance()
    with caplog.at_level(logging.INFO, logger="openfactory.repo_cache"):
        cache.sync("p", origin.url, "main")

    assert _head(served) == tip, "a marker a day old still held the served tree"
    passed = [r.getMessage() for r in caplog.records
              if "OPENFACTORY_CACHE_HOLD_EXPIRED" in r.getMessage()]
    assert len(passed) == 1 and str(ws.path.resolve()) in passed[0], (
        f"the stale marker was passed over without a word: {passed}")


def test_a_marker_just_under_a_day_still_holds_the_served_tree(tmp_path, origin):
    """C5, under the bound: a minute short of a day still holds. Before the fix the tree was
    swapped and the job's worktree answered 128."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    before = _head(served)
    _, ws = _job(tmp_path, served, origin)
    marker = _marker(ws.path)
    if marker.exists():
        _aged(marker, DAY - 60)

    origin.advance()
    cache.sync("p", origin.url, "main")

    assert _head(served) == before, "a marker younger than a day did not hold the served tree"
    rc, said = _answers(ws.path)
    assert rc == 0, said


def test_the_markers_day_outlasts_the_longest_job_the_default_timeouts_allow():
    """C5: the bound is longer than `ACTIVITY_CEILING` — the agent's wall plus the box's and the
    orchestration's overheads, 4 h 30 min by default — so no job the default timeouts let run is
    still running when its marker stops holding. Before the fix the bound did not exist
    (`ImportError`), which is accepted: the property is about the new constant. An operator who
    raises `OPENFACTORY_AGENT_TIMEOUT` past the day is outside what this holds."""
    from openfactory.adapters.gitworktrees import JOB_MARKER_MAX_AGE
    from openfactory.adapters.sandbox.timeouts import ACTIVITY_CEILING

    assert JOB_MARKER_MAX_AGE == DAY
    assert JOB_MARKER_MAX_AGE > ACTIVITY_CEILING, (JOB_MARKER_MAX_AGE, ACTIVITY_CEILING)
