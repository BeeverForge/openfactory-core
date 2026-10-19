"""A job lets go of the cache's served tree when git removes its worktree (#747).

THE MARKER LIVES WHERE GIT CLEANS UP. The worktree box writes `openfactory-job` into the admin
directory of the worktree it added (`<served>/.git/worktrees/<name>`), and while that marker stands
over a worktree that is still on disk the cache does not swap the served tree. Nothing has to
remember to delete it: git deletes the whole admin directory, foreign files included, on `git
worktree remove` (what the box's `cleanup` runs) and on `git worktree prune` once the worktree's
directory is gone — measured on git 2.43.0 and 2.34.1 before this was written.

THE RULE THIS FILE HOLDS:
  1. the box's `cleanup` takes the marker with the admin directory;
  2. `git worktree prune` takes the marker of a tree whose directory is gone;
  3. while the job stands, a sync leaves the served tree at the old commit; once the box cleaned
     up, the next sync publishes the moved base.

Before the fix the first assertion of each fails: `prepare` wrote no marker, and the first sync
already swapped the tree.
"""

from __future__ import annotations

import shutil

import pytest

from openfactory.runtime.repo_cache import RepoCache
from tests.test_a_cache_sync_never_pulls_the_git_directory_out_from_under_a_running_job import (
    Origin,
    _answers,
    _git,
    _head,
    _job,
    _marker,
)


@pytest.fixture
def origin(tmp_path) -> Origin:
    return Origin(tmp_path)


def test_git_worktree_remove_takes_the_job_marker_with_the_admin_directory(tmp_path, origin):
    """C4, `worktree remove`: the box's own `cleanup`."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    box, ws = _job(tmp_path, served, origin)
    marker = _marker(ws.path)
    assert marker.is_file(), f"prepare wrote no job marker at {marker}"

    box.cleanup(workspace=ws)

    assert not marker.parent.exists(), f"the admin directory outlived the job: {marker.parent}"


def test_git_worktree_prune_takes_the_marker_of_a_tree_whose_directory_is_gone(tmp_path, origin):
    """C4, `worktree prune`: a job's directory deleted by hand, then pruned — here in the test's
    own repository, never in a person's."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    _, ws = _job(tmp_path, served, origin)
    marker = _marker(ws.path)
    assert marker.is_file(), f"prepare wrote no job marker at {marker}"

    shutil.rmtree(ws.path)
    _git("worktree", "prune", cwd=served)

    assert not marker.parent.exists(), f"prune left the admin directory: {marker.parent}"


def test_once_the_box_cleaned_up_the_next_sync_publishes_the_moved_base(tmp_path, origin):
    """C4, the hold ends: held while the job stands, published once it is gone. Before the fix the
    middle assertion failed: the first sync had already swapped the tree under the job."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    before = _head(served)
    box, ws = _job(tmp_path, served, origin)

    tip = origin.advance()
    cache.sync("p", origin.url, "main")
    assert _head(served) == before, "the sync swapped the served tree while the job stood on it"
    assert _answers(ws.path)[0] == 0

    box.cleanup(workspace=ws)
    cache.sync("p", origin.url, "main")
    assert _head(served) == tip, "the hold outlived the job: the moved base was never published"
