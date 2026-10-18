"""A re-run on the worktree box starts again over its own earlier tree that git has forgotten.

THE FIELD REPORT (#746, against v0.6.0-rc.2). A card that runs again on the worktree box dies in
`prepare` with `worktree add failed: … fatal: '<root>/openfactory-28' already exists`, and the
classifier reads that as `unknown` and escalates. Since #623 the box clears only a tree that
`git worktree list --porcelain` lists at its own path, `root / <branch>`; a directory git has
forgotten is not listed, so it stays on disk and git refuses the add over it.

THE COMMON CAUSE IN PRODUCTION IS THE REPOSITORY CACHE'S REPUBLISH. The served checkout the box is
handed (`RepoCache.sync`, then `resolve_repo_path`) is a hardlink snapshot of a hidden master, and
`RepoCache._publish` replaces it with a fresh snapshot whenever the base moves. The new snapshot
has no `.git/worktrees/`, so git has forgotten every tree the box made from the old one, while
their directories stay under the shared `<cache>/.openfactory-worktrees`. Every card of that
project that runs again after its base moved dies. Reproduced on c0a50f3 with the real `RepoCache`
and a `file://` forge (2026-10-18, git 2.43.0): the second `prepare` of `openfactory/28` raised
`worktree add failed: … '<cache>/.openfactory-worktrees/openfactory-28' already exists`.

WHAT GIT LEAVES, measured on git 2.34.1 (ubuntu:22.04) and 2.43.0 (the host), same on both, with an
empty `HOME` and `GIT_CONFIG_NOSYSTEM=1`. A forgotten tree (pruned while its directory was away, or
its admin directory lost) keeps `<wt>/.git` as a FILE, `gitdir: <repo>/.git/worktrees/<name>`,
absolute; the admin directory is gone. `git worktree remove --force <wt>` answers rc 128 `'<wt>'
is not a working tree`; `git worktree add` over it answers rc 128 `'<wt>' already exists`, and
`--force` does not get past it. `git worktree repair <wt>` answers rc 1. Git 2.48 added
`worktree.useRelativePaths`; measured on git 2.49.1 (alpine:3.22, 2026-10-18) with it set, the
`.git` file reads `gitdir: ../../repo/.git/worktrees/x`, relative to the tree's own directory, and
the add over the forgotten tree fails the same way (rc 128, `already exists`).

THE ISSUE'S OWN FIX, `rmtree` WHATEVER IS THERE, IS NOT TAKEN: the root is shared by every project
in the cache, so the directory at `wt` can be another repository's working tree (#623's rule, and
the reason PR #792 left #746 open). Only a tree PROVABLY THIS REPOSITORY'S is removed: its `.git`
file names this repository's `<common>/worktrees/<x>`, and the porcelain, read, does not list
`wt`. When the porcelain cannot be read, nothing is removed (engineering lessons §2).

Every state here is built the way git builds it, with real repositories and real linked
worktrees; no `.git` file is written where git would write a real one, except the relative form,
which this machine's git (2.43.0) cannot write and which is rewritten to the bytes 2.49.1 wrote.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from openfactory.adapters.sandbox import worktree as worktree_box
from openfactory.adapters.sandbox.worktree import WorktreeSandbox
from openfactory.runtime.repo_cache import RepoCache

BRANCH = "openfactory/28"
LEFT = "left-by-the-last-run.txt"


def _git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"git {' '.join(args)}: {p.stderr}"
    return p.stdout.strip()


def _commit(repo: Path, name: str, text: str, message: str) -> None:
    (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgSign=false",
         "commit", "-q", "-m", message)


def _repository(where: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(where)], capture_output=True, check=True)
    _commit(where, "README.md", "# app\n", "base")
    return where


def _common(repo: Path) -> Path:
    """The repository's common git directory, as git names it, resolved."""
    return (repo / _git(repo, "rev-parse", "--git-common-dir")).resolve()


def _registered(repo: Path) -> list[str]:
    return [line.split(" ", 1)[1] for line in _git(repo, "worktree", "list", "--porcelain")
            .splitlines() if line.startswith("worktree ")]


def _a_working_tree_of(path: Path, repo: Path) -> bool:
    p = subprocess.run(["git", "-C", str(path), "rev-parse", "--git-common-dir"],
                       capture_output=True, text=True, timeout=60)
    return p.returncode == 0 and (path / p.stdout.strip()).resolve() == _common(repo)


@pytest.fixture(params=["boxes", "my boxes", "symlinked"])
def box_root(tmp_path, request):
    """Where the box keeps its worktrees: plain, with a space, and through a symlink, which git
    lists by its real path (copied from the #623 file, not imported across test modules)."""
    if request.param != "symlinked":
        return tmp_path / request.param
    real = tmp_path / "real-boxes"
    real.mkdir()
    link = tmp_path / "linked-boxes"
    os.symlink(real, link)
    return link


def _fresh(box: WorktreeSandbox, repo: Path, **kw):
    return box.prepare(repo_path=repo, base_branch="main", branch=BRANCH, **kw)


def _pruned_while_away(tmp_path: Path, repo: Path, box: WorktreeSandbox) -> Path:
    """The box's earlier tree, with a file its run left, forgotten the way a person's prune does
    it: the directory was away (an unmounted disk, a move) when `git worktree prune` ran."""
    wt = _fresh(box, repo).path
    (wt / LEFT).write_text("from the earlier pass\n")
    away = tmp_path / "away"
    shutil.move(str(wt), str(away))
    _git(repo, "worktree", "prune")
    shutil.move(str(away), str(wt))
    assert str(wt.resolve()) not in _registered(repo), "git still lists the tree: not forgotten"
    assert (wt / ".git").is_file()
    return wt


def _assert_started_clean(ws, wt: Path, repo: Path) -> None:
    assert ws.path == wt
    assert _a_working_tree_of(ws.path, repo), f"{ws.path} is not a working tree of {repo}"
    assert _git(ws.path, "symbolic-ref", "--short", "HEAD") == BRANCH
    assert not (ws.path / LEFT).exists(), "the earlier pass's file is still in the new tree"


def test_a_tree_of_this_repository_git_pruned_while_its_directory_was_away_is_cleared_and_the_job_starts(  # noqa: E501
        tmp_path, box_root):
    """C1. On c0a50f3 the second `prepare` raised `RuntimeError: worktree add failed: … '<wt>'
    already exists`: the box clears only what the porcelain lists, and git no longer lists it."""
    repo = _repository(tmp_path / "myapp")
    box = WorktreeSandbox(root=box_root)
    wt = _pruned_while_away(tmp_path, repo, box)
    _assert_started_clean(_fresh(box, repo), wt, repo)


def test_a_tree_whose_registration_went_with_the_repository_s_admin_directory_is_cleared_and_the_job_starts(  # noqa: E501
        tmp_path):
    """C1. The admin directory `<repo>/.git/worktrees/<name>` is gone (lost with a restored or
    re-cloned `.git`), and the tree's `.git` file still names it. On c0a50f3: `worktree add
    failed: … already exists`."""
    repo = _repository(tmp_path / "myapp")
    box = WorktreeSandbox(root=tmp_path / "boxes")
    wt = _fresh(box, repo).path
    (wt / LEFT).write_text("from the earlier pass\n")
    admin = (wt / _git(wt, "rev-parse", "--git-dir")).resolve()
    assert admin.parent == _common(repo) / "worktrees", admin
    shutil.rmtree(admin)
    assert str(wt.resolve()) not in _registered(repo)
    _assert_started_clean(_fresh(box, repo), wt, repo)


def test_after_the_cache_republishes_the_checkout_the_same_card_starts_again(tmp_path):
    """C1, the production door. The real `RepoCache` serves a snapshot; the forge's `main` moves;
    the next sync republishes the snapshot, which has no `.git/worktrees/`, and the box's root
    (`<served>.parent / ".openfactory-worktrees"`, as `factory.py` composes it) still holds the
    card's earlier tree. On c0a50f3 the second `prepare` raised `worktree add failed: … already
    exists` (reproduced 2026-10-18, git 2.43.0)."""
    forge = tmp_path / "forge.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(forge)],
                   capture_output=True, check=True)
    seed = _repository(tmp_path / "seed")
    _git(seed, "push", "-q", str(forge), "main")
    url = f"file://{forge}"
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("myapp", url, "main")
    assert served is not None, "the cache did not sync"
    box = WorktreeSandbox(root=served.parent / ".openfactory-worktrees")
    wt = _fresh(box, served, remote_url=url).path
    (wt / LEFT).write_text("from the earlier pass\n")

    _commit(seed, "README.md", "# app, again\n", "the base moves")
    _git(seed, "push", "-q", str(forge), "main")
    again = cache.sync("myapp", url, "main")
    assert again == served, (again, served)
    assert not (served / ".git" / "worktrees").exists(), "the republish kept the admin dirs"
    assert str(wt.resolve()) not in _registered(served)

    _assert_started_clean(_fresh(box, served, remote_url=url), wt, served)


def test_a_forgotten_tree_whose_gitdir_is_relative_is_recognised_as_this_repository_s(
        tmp_path, box_root):
    """C1, git 2.48+ with `worktree.useRelativePaths`. The `.git` file is relative to the tree's
    own directory; measured on git 2.49.1 (alpine:3.22, 2026-10-18) it reads
    `gitdir: ../../repo/.git/worktrees/x`, the format git-worktree(1) documents for that key. This
    machine's git (2.43.0) writes the absolute form, so the file is rewritten to the relative one
    2.49.1 writes, relative to the tree's real directory. On c0a50f3: `worktree add failed: …
    already exists`."""
    repo = _repository(tmp_path / "myapp")
    box = WorktreeSandbox(root=box_root)
    wt = _pruned_while_away(tmp_path, repo, box)
    absolute = (wt / ".git").read_text().split("gitdir:", 1)[1].strip()
    relative = os.path.relpath(absolute, wt.resolve())
    assert not os.path.isabs(relative) and relative.startswith(".."), relative
    (wt / ".git").write_text(f"gitdir: {relative}\n")
    _assert_started_clean(_fresh(box, repo), wt, repo)


def test_a_forgotten_tree_is_kept_when_the_working_tree_list_cannot_be_read(tmp_path, monkeypatch):
    """C4, engineering lessons §2: "could not see" is not "git does not list it". When the porcelain
    cannot be read, the leftover is not removed and git's own refusal is passed on, as before.
    REVERSE GUARD: green on c0a50f3 (which removes nothing unlisted) and it stays green; the
    mutation that lets the removal run on an unread list turns it red."""
    repo = _repository(tmp_path / "myapp")
    box = WorktreeSandbox(root=tmp_path / "boxes")
    wt = _pruned_while_away(tmp_path, repo, box)
    monkeypatch.setattr(worktree_box, "_working_trees", lambda repo_path: None)
    with pytest.raises(RuntimeError) as caught:
        _fresh(box, repo)
    assert type(caught.value) is RuntimeError, type(caught.value)
    assert "worktree add failed" in str(caught.value), str(caught.value)
    assert (wt / LEFT).read_text() == "from the earlier pass\n", "the unread leftover was removed"
