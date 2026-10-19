"""The worktree box marks the one worktree it adds as a job's, and nothing else (#747).

WHY A MARK. A job's worktree added to the repository cache's served checkout lives in that
checkout's `.git`: its admin directory is `<served>/.git/worktrees/<name>`. The cache could not
tell a job's worktree from nothing, swapped the served tree when the base moved, and the job's
`<wt>/.git` pointed at an admin directory that no longer existed (`fatal: not a git repository`,
exit 128, 82500f9, git 2.43.0). So `prepare` writes `openfactory-job` into the admin directory of
the worktree it just added — `$(git -C <wt> rev-parse --absolute-git-dir)` — where git deletes it
with the admin directory on `worktree remove` and `worktree prune`.

THE RULE THIS FILE HOLDS:
  1. every door of `prepare` (a fresh job, a resume from the forge, the local forge's continuing
     door) marks the worktree it added, in that worktree's own admin directory;
  2. no other working tree of the repository — a person's own worktree, the main `.git` — is
     marked (reverse guard: the box never writes into a tree it did not create, #623);
  3. a marker that cannot be written is said, naming the worktree, and the job still starts
     (engineering lessons §6: silence is a failure mode).

The marker path is the issue's contract spelt out, not imported, so the code before the fix fails
these tests for the absent marker and not for an import.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from openfactory.adapters import gitworktrees
from openfactory.adapters.sandbox.worktree import WorktreeSandbox

#: The marker's name, as the issue states the contract
MARKER = "openfactory-job"
BRANCH = "openfactory/747"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def _admin(wt: Path) -> Path:
    return Path(_git("rev-parse", "--absolute-git-dir", cwd=wt).strip())


@pytest.fixture
def repo(tmp_path) -> Path:
    """A person's repository with one commit on `main`, and a bare forge it pushes to."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / "app.py").write_text("x = 1\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "first", cwd=repo)
    _git("clone", "-q", "--bare", str(repo), str(tmp_path / "forge.git"), cwd=tmp_path)
    return repo


def _door(name: str, repo: Path, forge: Path) -> dict:
    """The arguments one door of `prepare` is reached with, the repository made ready for it."""
    if name == "fresh":
        return {"checkout_existing": False, "remote_url": str(forge)}
    if name == "resume_from_remote":
        # the job's branch was pushed by an earlier pass and is fetched back from the forge
        _git("branch", BRANCH, cwd=repo)
        _git("push", "-q", str(forge), BRANCH, cwd=repo)
        _git("branch", "-D", BRANCH, cwd=repo)
        return {"checkout_existing": True, "remote_url": str(forge)}
    # the local forge's continuing door (ADR-0049 D3): the branch is in this repository and kept
    _git("branch", BRANCH, cwd=repo)
    return {"checkout_existing": True, "remote_url": str(repo)}


def test_prepare_writes_the_job_marker_into_the_new_worktrees_own_admin_directory(
        tmp_path, repo):
    """C2. Before the fix there was no such file in the worktree's admin directory."""
    ws = WorktreeSandbox(root=tmp_path / "jobs").prepare(
        repo_path=repo, base_branch="main", branch=BRANCH)

    admin = _admin(ws.path)
    assert admin.parent == (repo / ".git" / "worktrees").resolve(), admin
    assert (admin / MARKER).is_file(), f"no job marker in {admin}"


@pytest.mark.parametrize("door", ["fresh", "resume_from_remote", "local_continuing"])
def test_every_door_of_prepare_marks_the_worktree_it_added(tmp_path, repo, door):
    """C2, every door: a fresh job, a resume that fetches the branch back from the forge, and the
    local forge's continuing door that keeps the branch. Before the fix no door wrote a marker."""
    kwargs = _door(door, repo, tmp_path / "forge.git")
    ws = WorktreeSandbox(root=tmp_path / "jobs").prepare(
        repo_path=repo, base_branch="main", branch=BRANCH, **kwargs)

    assert (_admin(ws.path) / MARKER).is_file(), f"the {door} door left its worktree unmarked"


def test_no_other_working_trees_admin_directory_is_marked(tmp_path, repo):
    """C2, reverse: a person's own worktree of the same repository and the main `.git` carry no
    marker after the box prepared a job beside them — the box writes only into the admin
    directory of the tree it just added. REVERSE GUARD: green before the fix (nothing wrote a
    marker anywhere); held red by the mutation that writes it into the repository's `.git`."""
    theirs = tmp_path / "their-own-tree"
    _git("worktree", "add", "-q", "-b", "their-work", str(theirs), "main", cwd=repo)

    ws = WorktreeSandbox(root=tmp_path / "jobs").prepare(
        repo_path=repo, base_branch="main", branch=BRANCH)

    ours = _admin(ws.path) / MARKER
    elsewhere = [p for p in (repo / ".git").resolve().rglob(MARKER) if p != ours]
    assert elsewhere == [], f"the box marked a tree it did not create: {elsewhere}"
    assert not (_admin(theirs) / MARKER).exists()


def test_a_marker_that_cannot_be_written_is_said_and_the_job_still_starts(
        tmp_path, repo, monkeypatch, caplog):
    """C2, engineering lessons §6. A marker the disk refused leaves the job unprotected from a
    cache swap, which nobody would know without a line saying so — and refusing the job over it
    would cost the work the marker exists to protect. Before the fix no WARNING was logged:
    nothing tried to write a marker."""
    def refused(worktree, *a, **kw):
        raise OSError(28, "No space left on device", str(worktree))

    monkeypatch.setattr(gitworktrees, "mark_as_job", refused, raising=False)
    with caplog.at_level(logging.WARNING, logger="openfactory.sandbox.worktree"):
        ws = WorktreeSandbox(root=tmp_path / "jobs").prepare(
            repo_path=repo, base_branch="main", branch=BRANCH)

    assert _git("rev-parse", "--abbrev-ref", "HEAD", cwd=ws.path).strip() == BRANCH
    said = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(str(ws.path) in line for line in said), f"the refused marker was not said: {said}"
