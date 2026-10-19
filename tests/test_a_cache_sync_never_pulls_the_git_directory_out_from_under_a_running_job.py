"""A repository cache sync never pulls the git directory out from under a running job (#747).

WHAT WAS MEASURED (82500f9, git 2.43.0). On the worktree box a project registered by clone URL is
served by the worker's cache, and `WorktreeSandbox.prepare` runs `git worktree add -b <branch>
<wt> <base>` IN THE SERVED CHECKOUT: the job's admin directory (`<root>/<key>/.git/worktrees/
<name>`), its branch and every object it writes live in the served `.git`. The next sync of the
same key — another card's preflight, the next job's `resolve_repo_path`, a knowledge refresh —
found the master moved, or the served tree dirty, and swapped the served tree into
`.trash/<key>~<hex>`, replacing it with a fresh hardlink snapshot of the master, which has no
`worktrees/`. The job's `<wt>/.git` still pointed at the old admin directory: `git -C <wt> status`
exited 128 with `fatal: not a git repository: <root>/p/.git/worktrees/wt`, and `publish_branch`
failed with the same words, so the finished work was never pushed.

THE RULE THIS FILE HOLDS, for every cache class (`RepoCache` and each subclass, found rather than
listed):
  1. a job's worktree, added by the real box to the served checkout, still answers git after the
     base moved (or the served tree was scribbled in) and the cache synced, and its work is pushed;
  2. a held sync says so, once, naming the served tree, the worktree holding it and the marker's
     age, with no card id in the line;
  3. a marked worktree whose directory is gone holds nothing (reverse guard);
  4. a `.git/worktrees` that cannot be read holds the tree, and says so — "could not see" is never
     "there is nothing" (engineering lessons §2);
  5. an unmoved sync reads no marker and starts no git process more than it did (reverse guard).

THE WRITER IS THE PRODUCTION ONE (engineering lessons §1): the real `RepoCache`/`SparseRepoCache`
over a local origin, and the real `WorktreeSandbox.prepare` — never a fake box, never a worktree
added by hand. The marker path is the issue's contract spelt out, `$(git -C <wt> rev-parse
--absolute-git-dir)/openfactory-job`, so these tests are red on the code before the fix for the
defect and not for an import.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

from openfactory.adapters import gitworktrees
from openfactory.adapters.sandbox.worktree import WorktreeSandbox
from openfactory.runtime import repo_cache
from openfactory.runtime.repo_cache import RepoCache

#: Every cache class, asked of the code: a cache added tomorrow falls under the rule without an edit
CACHES = [RepoCache, *RepoCache.__subclasses__()]
#: The marker's name, as the issue states the contract — not imported, so the code before the fix
#: fails these tests for the defect rather than for an `ImportError`
MARKER = "openfactory-job"
#: A card id as `tests/test_no_card_id_reaches_a_stranger.py` reads one
CARD_ID = re.compile(r"#\d{2,3}\b|C-\d{2}\b")
BRANCH = "openfactory/747"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def _answers(wt: Path) -> tuple[int, str]:
    """What `git status` in the job's worktree says: its exit code and its words."""
    done = subprocess.run(["git", "-C", str(wt), "status", "--porcelain"], capture_output=True,
                          text=True, env={**os.environ, "LC_ALL": "C"})
    return done.returncode, done.stdout + done.stderr


class Origin:
    """A bare repository the cache clones and the job pushes to, and a clone that moves it."""

    def __init__(self, tmp: Path) -> None:
        self.work = tmp / "origin-work"
        self.work.mkdir()
        _git("init", "-q", "-b", "main", cwd=self.work)
        (self.work / "app.py").write_text("x = 1\n")
        _git("add", "-A", cwd=self.work)
        _git("commit", "-qm", "first", cwd=self.work)
        self.bare = tmp / "origin.git"
        _git("clone", "-q", "--bare", str(self.work), str(self.bare), cwd=tmp)
        # the sparse cache clones `--filter=blob:none` and fetches blobs on demand
        _git("config", "uploadpack.allowFilter", "true", cwd=self.bare)
        _git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=self.bare)
        _git("remote", "add", "origin", str(self.bare), cwd=self.work)
        self.url = str(self.bare)

    def advance(self, text: str = "x = 2\n") -> str:
        """Move `main` on the origin by one commit, and answer the new tip."""
        (self.work / "app.py").write_text(text)
        _git("commit", "-qam", "advance", cwd=self.work)
        _git("push", "-q", "origin", "main", cwd=self.work)
        return self.tip()

    def tip(self) -> str:
        return _git("rev-parse", "main", cwd=self.bare).strip()


@pytest.fixture
def origin(tmp_path) -> Origin:
    return Origin(tmp_path)


def _job(tmp_path: Path, served: Path, origin: Origin):
    """The worktree box's own `prepare` over the served checkout, as `build_runner` drives it for a
    project registered by clone URL: the job's remote is the forge, here the bare origin."""
    box = WorktreeSandbox(root=tmp_path / "jobs")
    ws = box.prepare(repo_path=served, base_branch="main", branch=BRANCH,
                     remote_url=origin.url)
    return box, ws


def _marker(wt: Path) -> Path:
    """Where the issue says the box writes the marker: the worktree's own admin directory."""
    admin = _git("rev-parse", "--absolute-git-dir", cwd=wt).strip()
    return Path(admin) / MARKER


def _head(path: Path) -> str:
    return _git("rev-parse", "HEAD", cwd=path).strip()


def test_a_jobs_worktree_still_answers_git_after_the_base_moved_and_the_cache_synced(
        tmp_path, origin):
    """C1, "What happens". Before the fix the second sync swapped the served tree into the trash
    and `git status` in the job's worktree exited 128, `fatal: not a git repository:
    <root>/p/.git/worktrees/<name>` (82500f9, git 2.43.0)."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    assert served is not None
    _, ws = _job(tmp_path, served, origin)

    origin.advance()
    assert cache.sync("p", origin.url, "main") == served

    rc, said = _answers(ws.path)
    assert rc == 0, f"the job's worktree lost its git directory to the sync: {said.strip()}"


def test_a_jobs_finished_work_is_pushed_after_the_cache_synced_under_it(tmp_path, origin):
    """C1: the job commits, a sync of the same key runs while it works, and the box pushes. Before
    the fix the push failed with `push failed: fatal: not a git repository`, and the branch never
    reached the forge."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    box, ws = _job(tmp_path, served, origin)
    (ws.path / "feature.py").write_text("done = True\n")
    _git("add", "-A", cwd=ws.path)
    _git("commit", "-qm", "the job's work", cwd=ws.path)
    work = _head(ws.path)

    origin.advance()
    cache.sync("p", origin.url, "main")

    try:
        box.publish_branch(workspace=ws, remote_url=origin.url)
    except RuntimeError as exc:
        pytest.fail(f"the job's finished work was not pushed: {exc}")
    assert _git("rev-parse", BRANCH, cwd=origin.bare).strip() == work


def test_a_scribble_in_the_served_tree_does_not_swap_it_out_from_under_a_job(tmp_path, origin):
    """C1, the "dirty" half of "stale or dirty": the base did not move, but a stray file in the
    served tree made it dirty. Before the fix that alone swapped the tree, with the same exit 128
    in the job's worktree."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    _, ws = _job(tmp_path, served, origin)

    (served / "scribble.txt").write_text("somebody was here\n")
    cache.sync("p", origin.url, "main")

    rc, said = _answers(ws.path)
    assert rc == 0, f"a scribble swapped the tree out from under the job: {said.strip()}"


@pytest.mark.parametrize("cls", CACHES, ids=lambda c: c.__name__)
def test_no_cache_class_swaps_a_tree_a_marked_worktree_still_stands_on(tmp_path, origin, cls):
    """C1, every cache class: `RepoCache._sync` and `SparseRepoCache._sync_sparse` both decide
    through `_needs_publish`. The sparse served tree is a partial clone, and the real `prepare`
    takes it: the worktree's checkout fetches the blobs it needs from the origin, which serves
    filters. Before the fix both classes swapped the tree, and the worktree answered 128."""
    cache = cls(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    assert served is not None, getattr(cache, "failure", "")
    _, ws = _job(tmp_path, served, origin)

    origin.advance()
    assert cache.sync("p", origin.url, "main") == served

    rc, said = _answers(ws.path)
    assert rc == 0, f"{cls.__name__} swapped the tree under a job's worktree: {said.strip()}"


def test_a_held_sync_says_which_worktree_holds_the_tree_and_why(tmp_path, origin, caplog):
    """C3: the hold is said, once, with a stable token, naming the served tree, the worktree that
    holds it and how old its marker is — and no card id, because an operator's terminal is a
    surface. Before the fix nothing was said: the tree was swapped."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    _, ws = _job(tmp_path, served, origin)
    marker = _marker(ws.path)
    if marker.exists():
        # ninety minutes old, so the line's age is a number this test chose; the marker's
        # existence itself is held by the box's own tests
        then = time.time() - 90 * 60
        os.utime(marker, (then, then))

    origin.advance()
    with caplog.at_level(logging.INFO, logger="openfactory.repo_cache"):
        cache.sync("p", origin.url, "main")

    held = [r.getMessage() for r in caplog.records if "OPENFACTORY_CACHE_HELD" in r.getMessage()]
    assert len(held) == 1, f"a held sync must say so exactly once: {held}"
    line = held[0]
    assert str(served) in line, line
    assert str(ws.path.resolve()) in line, line
    assert "90 min" in line, line
    assert not CARD_ID.search(line), line


def test_a_marked_worktree_whose_directory_is_gone_does_not_hold_the_tree(tmp_path, origin):
    """C3, "still on disk". A job's directory deleted without `git worktree prune` leaves its admin
    directory and its marker behind; nothing stands on the served tree any more, so the sync
    publishes the moved base. REVERSE GUARD: green before the fix (it published anyway); held red
    by the mutation that drops the "still on disk" test."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    _, ws = _job(tmp_path, served, origin)
    shutil.rmtree(ws.path)

    tip = origin.advance()
    cache.sync("p", origin.url, "main")

    assert _head(served) == tip, "a worktree whose directory is gone still held the cache"


def test_a_worktrees_directory_that_cannot_be_read_holds_the_tree_and_says_so(
        tmp_path, origin, caplog, monkeypatch):
    """C3, engineering lessons §2: a `.git/worktrees` the cache cannot list is "could not see",
    never "there is nothing", so the tree is held and the line says the worktrees could not be
    read. Before the fix the swap happened and nothing was said.

    AS ROOT, `chmod 000` REFUSES NOTHING, so there the listing itself is made to refuse, the way
    the kernel refuses it to the user CI runs as."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    before = _head(served)
    _, ws = _job(tmp_path, served, origin)
    worktrees = served / ".git" / "worktrees"

    origin.advance()
    worktrees.chmod(0)
    try:
        with monkeypatch.context() as patch:
            if os.access(worktrees, os.R_OK):
                real = os.scandir

                def refused(path=".", *a, **kw):
                    if Path(path) == worktrees:
                        raise PermissionError(13, "Permission denied", str(path))
                    return real(path, *a, **kw)

                patch.setattr(os, "scandir", refused)
            with caplog.at_level(logging.INFO, logger="openfactory.repo_cache"):
                cache.sync("p", origin.url, "main")
    finally:
        for left in [worktrees, *(tmp_path / "cache" / ".trash").glob("p~*/.git/worktrees")]:
            if left.exists():
                left.chmod(stat.S_IRWXU)

    assert _head(served) == before, "an unreadable worktrees directory was read as no job at all"
    held = [r.getMessage() for r in caplog.records if "OPENFACTORY_CACHE_HELD" in r.getMessage()]
    assert len(held) == 1 and str(served) in held[0] and "could not be read" in held[0], held
    rc, said = _answers(ws.path)
    assert rc == 0, said


def test_an_unmoved_sync_reads_no_marker_and_starts_no_extra_git_process(
        tmp_path, origin, monkeypatch):
    """C3, no new cost on the routine sync: with a job's marker on disk and the origin unmoved, a
    sync starts exactly as many git processes as a sync of a key no job stands on, and reads no
    marker — the marks are read only when a publish would otherwise happen. REVERSE GUARD: green
    before the fix; held red by the mutation that reads the marks before the head and dirty
    comparison."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    assert cache.sync("q", origin.url, "main") is not None
    _job(tmp_path, served, origin)

    calls: list[str] = []
    real_run = subprocess.run

    def counting(args, *a, **kw):
        if isinstance(args, (list, tuple)) and args and args[0] == "git":
            calls.append(str(kw.get("cwd") or ""))
        return real_run(args, *a, **kw)

    reads: list[Path] = []
    real_marks = getattr(gitworktrees, "live_job_marks", None)

    def reading(repo, *a, **kw):
        reads.append(Path(repo))
        return real_marks(repo, *a, **kw)

    monkeypatch.setattr(gitworktrees, "live_job_marks", reading, raising=False)
    monkeypatch.setattr(repo_cache.subprocess, "run", counting)

    cache.sync("q", origin.url, "main")
    without = len(calls)
    calls.clear()
    cache.sync("p", origin.url, "main")
    with_job = len(calls)

    assert with_job == without, f"{with_job} git processes with a job's marker, {without} without"
    assert reads == [], f"an unmoved sync read the job marks of {reads}"


def test_a_held_sparse_sync_opens_no_freshness_window(tmp_path, origin):
    """A held sync serves the OLD commit, and the sparse cache's freshness window (`fresh_for`)
    would stamp that commit as fresh: after the job let go, the next sync inside the window was
    served the held tree again without asking the forge, for up to `fresh_for` seconds. A held
    sync opens no window, so the first sync after the release publishes the moved base."""
    from openfactory.runtime.repo_cache import SparseRepoCache

    now = [1_000_000.0]
    cache = SparseRepoCache(root=tmp_path / "cache", fresh_for=60, clock=lambda: now[0])
    served = cache.sync("p", origin.url, "main")
    assert served is not None, cache.failure
    before = _head(served)
    box, ws = _job(tmp_path, served, origin)

    tip = origin.advance()
    now[0] += 120                       # past the first sync's window: this one asks the forge
    cache.sync("p", origin.url, "main")
    assert _head(served) == before, "the sync swapped the served tree while the job stood on it"

    box.cleanup(workspace=ws)
    now[0] += 10                        # inside the window a held sync would have opened
    cache.sync("p", origin.url, "main")
    assert _head(served) == tip, "the held tree was served again from its freshness window"
