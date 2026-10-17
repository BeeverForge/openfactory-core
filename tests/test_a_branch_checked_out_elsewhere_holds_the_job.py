"""A card's branch somebody else has out stops the box by name, and nothing of theirs is touched.

THE FIELD REPORT. Card 28 of the some2dgame run (field report of 2026-10, §A2), 2026-10-09: the
operator reviewed the pull request in a scratch `git worktree` of `openfactory/28`, answered the
gate with `adjust`, and the pass failed with git's own sentence, "already used by worktree". The
worktree box asked git to check the branch out a second time, and git lets a branch be out in one
working tree only. `resume` only reopened the gate.

TWO DOORS, ONE DEFECT. On the local forge's `keep` path the box runs `worktree add <wt> <branch>`
and passes git's refusal on. On a hosted forge, or a fresh job, it first runs `branch -D`, which
git refuses for a held branch with the return code ignored, then fetches into
`refs/remotes/origin/<branch>`, then `worktree add -b`, which fails with
`fatal: a branch named 'openfactory/28' already exists`: a sentence that names no path at all.

GIT'S OWN WORDS ARE NOT A CONTRACT. Measured for #623: git 2.34.1 (ubuntu:22.04) says
`is already checked out at '<path>'`, git 2.43.0 says `is already used by worktree at '<path>'`,
and a git with a `pt_BR` catalogue says it in Portuguese. `git worktree list --porcelain` prints
the same lines on both versions (`worktree <path>`, `HEAD`, `branch refs/heads/<b>`,
`locked [reason]`, `prunable …`), and does not quote a path with a space or a non-ASCII character
(2.43.0, measured 2026-10-17). `--porcelain -z` does not exist on 2.34.1 (`error: unknown switch
'z'`, exit 129), so the box reads the plain porcelain.

AND THE BOX PRUNED THE PERSON'S REPOSITORY. `prepare` ran a blanket `git worktree prune`, which drops
every registration whose directory is missing at that moment, a person's worktree on an unmounted
disk included. The local forge already forbids exactly that in its scratch-tree rebase.

Proven against REAL git repositories and real linked worktrees. Two tests here pass on `main` and
are reverse guards, the old behaviour this change must keep: nothing of the person's is touched by
the refusal (local forge), and the platform's own leftover is still cleared.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from openfactory.adapters.sandbox import worktree as worktree_box
from openfactory.adapters.sandbox.worktree import WorktreeSandbox

BRANCH = "openfactory/28"
#: git's own sentences for a held branch, by version (2.34.1, 2.43.0) and by the `-b` door. None of
#: them names what to do, and the last names no path.
GITS_WORDS = ("already used by worktree", "already checked out at", "a branch named")


def _git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"git {' '.join(args)}: {p.stderr}"
    return p.stdout.strip()


def _commit(repo: Path, name: str, text: str, message: str) -> None:
    (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgSign=false",
         "commit", "-q", "-m", message)


def _registered(repo: Path) -> list[str]:
    """Every working tree git lists for `repo`, as the porcelain names it."""
    return [line.split(" ", 1)[1] for line in _git(repo, "worktree", "list", "--porcelain")
            .splitlines() if line.startswith("worktree ")]


def _sha(repo: Path, ref: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
                       capture_output=True, text=True)
    return p.stdout.strip()


def _repository(where: Path) -> Path:
    """A person's repository: `main`, and the card's branch carrying the job's committed work."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(where)], capture_output=True, check=True)
    _commit(where, "README.md", "# app\n", "base")
    _git(where, "switch", "-q", "-c", BRANCH)
    _commit(where, "work.py", "WORK = True\n", "the job's work")
    _git(where, "switch", "-q", "main")
    return where


@pytest.fixture(params=["review", "review tree"], ids=["plain-path", "path-with-a-space"])
def held(tmp_path, request):
    """The local forge: the repository is the remote, and the person has the card's branch out in
    a review tree of their own, with an edit in it they have not committed."""
    repo = _repository(tmp_path / "myapp")
    review = tmp_path / request.param
    _git(repo, "worktree", "add", "-q", str(review), BRANCH)
    (review / "notes.txt").write_text("what I noticed reviewing\n")
    return repo, review, WorktreeSandbox(root=tmp_path / "boxes")


def _keep(box: WorktreeSandbox, repo: Path):
    """The local forge's resume of a pull request: the repository is the remote, the branch is
    kept and checked out."""
    return box.prepare(repo_path=repo, base_branch="main", branch=BRANCH,
                       checkout_existing=True, remote_url=str(repo))


@pytest.fixture
def hosted(tmp_path):
    """A hosted forge: a bare origin holds the card's branch, the person's clone has it out in a
    review tree, and the factory pushed again since, so the clone's tracking ref is behind."""
    origin = tmp_path / "forge.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    seed = _repository(tmp_path / "seed")
    _git(seed, "push", "-q", str(origin), "main", BRANCH)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], capture_output=True,
                   check=True)
    review = tmp_path / "review"
    _git(clone, "worktree", "add", "-q", str(review), BRANCH)
    (review / "notes.txt").write_text("what I noticed reviewing\n")
    _git(seed, "switch", "-q", BRANCH)
    _commit(seed, "work.py", "WORK = 2\n", "the factory's second pass")
    _git(seed, "push", "-q", str(origin), BRANCH)
    return clone, review, f"file://{origin}", WorktreeSandbox(root=tmp_path / "boxes")


# ── the refusal names the tree that holds the branch ─────────────────────────────────────────────

def test_a_branch_checked_out_in_a_second_worktree_is_refused_naming_that_worktree(held):
    """Criterion 1. On `main` the message was `worktree add failed: … is already used by worktree
    at …`: git's sentence, which a person reads as the factory breaking. The path is compared
    resolved on both sides, and the review tree's path may hold a space."""
    repo, review, box = held
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    said = str(caught.value)
    for words in GITS_WORDS:
        assert words not in said, f"git's own sentence reached the person: {said!r}"
    assert str(review.resolve()) in said, said

    from openfactory.adapters.sandbox.base import BranchHeldElsewhere

    assert isinstance(caught.value, BranchHeldElsewhere), type(caught.value)
    assert caught.value.path == str(review.resolve())
    assert caught.value.branch == BRANCH
    assert caught.value.main is False


def test_on_a_hosted_forge_the_held_branch_is_named_too_not_a_branch_that_already_exists(hosted):
    """On `main` the box ran `branch -D` (refused by git, return code ignored), fetched, then
    `worktree add -b`, which said `fatal: a branch named 'openfactory/28' already exists`."""
    clone, review, origin, box = hosted
    with pytest.raises(RuntimeError) as caught:
        box.prepare(repo_path=clone, base_branch="main", branch=BRANCH, checkout_existing=True,
                    remote_url=origin)
    said = str(caught.value)
    for words in GITS_WORDS:
        assert words not in said, f"git's own sentence reached the person: {said!r}"
    assert str(review.resolve()) in said, said


def test_a_fresh_job_whose_branch_is_held_is_refused_before_the_branch_is_deleted(held):
    """A fresh job deletes the branch to start clean. Held, git refused the delete and the
    `worktree add -b` after it said `a branch named … already exists`."""
    repo, review, box = held
    before = _sha(repo, f"refs/heads/{BRANCH}")
    with pytest.raises(RuntimeError) as caught:
        box.prepare(repo_path=repo, base_branch="main", branch=BRANCH, checkout_existing=False)
    said = str(caught.value)
    for words in GITS_WORDS:
        assert words not in said, f"git's own sentence reached the person: {said!r}"
    assert str(review.resolve()) in said, said
    assert _sha(repo, f"refs/heads/{BRANCH}") == before


# ── the sentence says what to do ─────────────────────────────────────────────────────────────────

def test_the_sentence_names_the_path_the_remedy_and_resume(held):
    """Criterion 2: the path, the command that frees it, the other way out, and `resume`. The
    command is shell-quoted, so a review tree whose path holds a space pastes as one argument."""
    repo, review, box = held
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    said = str(caught.value)
    assert f"git worktree remove {shlex.quote(str(review.resolve()))}`" in said, said
    assert "switch" in said, said
    assert "resume" in said, said


def test_the_persons_own_checkout_is_told_to_switch_not_to_be_removed(tmp_path):
    """The branch is out in the repository's MAIN working tree: git cannot remove that one
    (`fatal: '<path>' is a main working tree`), so the remedy is to switch it away."""
    repo = _repository(tmp_path / "myapp")
    _git(repo, "switch", "-q", BRANCH)
    box = WorktreeSandbox(root=tmp_path / "boxes")
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    said = str(caught.value)
    for words in GITS_WORDS:
        assert words not in said, f"git's own sentence reached the person: {said!r}"
    assert str(repo.resolve()) in said, said
    assert "switch" in said, said
    assert "git worktree remove" not in said, said

    assert caught.value.main is True


def test_a_locked_review_tree_is_told_to_unlock_first(held):
    """`git worktree remove` of a locked tree is `fatal: cannot remove a locked working tree`
    (git 2.43.0, measured for #623), so a remedy that skips the unlock is one that fails."""
    repo, review, box = held
    _git(repo, "worktree", "lock", "--reason", "on a usb disk", str(review))
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    said = str(caught.value)
    path = shlex.quote(str(review.resolve()))
    unlock, remove = f"git worktree unlock {path}", f"git worktree remove {path}"
    assert unlock in said and remove in said, said
    assert said.index(unlock) < said.index(remove), said

    assert caught.value.locked is True


def test_the_sentence_is_the_same_whatever_git_s_own_wording(held, monkeypatch):
    """The sentence is built from the porcelain, never from git's prose, so neither git's version
    nor the person's locale reaches it. On a machine without git's `pt_BR` catalogue (this one, on
    2026-10-17: git 2.43.0 answered in English under `LC_ALL=pt_BR.UTF-8`) this still proves the
    sentence does not quote git."""
    repo, review, box = held
    for var in ("LC_ALL", "LANG", "LANGUAGE"):
        monkeypatch.setenv(var, "pt_BR.UTF-8")
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    said = str(caught.value)
    for words in GITS_WORDS:
        assert words not in said, f"git's own sentence reached the person: {said!r}"
    assert "fatal" not in said and "já" not in said, said

    from openfactory.adapters.sandbox.worktree import branch_held

    assert said == branch_held(BRANCH, str(review.resolve()), main=False, locked=False)


# ── nothing that is not the platform's is touched ────────────────────────────────────────────────

def test_nothing_of_the_persons_is_touched_by_the_refusal(held):
    """Criterion 3, the reverse guard on the local forge: green on `main` too, because there git
    itself refused before anything moved. It holds the refusal to the same standard."""
    repo, review, box = held
    before = _sha(repo, f"refs/heads/{BRANCH}")
    with pytest.raises(RuntimeError):
        _keep(box, repo)
    assert review.is_dir()
    assert str(review.resolve()) in _registered(repo)
    assert _git(review, "symbolic-ref", "--short", "HEAD") == BRANCH
    assert (review / "notes.txt").read_text() == "what I noticed reviewing\n"
    assert _sha(repo, f"refs/heads/{BRANCH}") == before


def test_on_a_hosted_forge_the_refusal_writes_no_ref_of_the_persons(hosted):
    """Decide before you write (engineering lessons §12). On `main` the fetch ran before git's
    refusal, and moved the person's `refs/remotes/origin/openfactory/28` to the factory's newer
    push: a write to their clone by a job that then did not start."""
    clone, review, origin, box = hosted
    tracking, branch = (_sha(clone, f"refs/remotes/origin/{BRANCH}"),
                        _sha(clone, f"refs/heads/{BRANCH}"))
    with pytest.raises(RuntimeError):
        box.prepare(repo_path=clone, base_branch="main", branch=BRANCH, checkout_existing=True,
                    remote_url=origin)
    assert _sha(clone, f"refs/remotes/origin/{BRANCH}") == tracking
    assert _sha(clone, f"refs/heads/{BRANCH}") == branch
    assert (review / "notes.txt").read_text() == "what I noticed reviewing\n"
    assert str(review.resolve()) in _registered(clone)


def test_a_persons_worktree_on_a_missing_disk_keeps_its_registration(tmp_path):
    """A person's linked worktree of an UNRELATED branch, on a disk that is not mounted right now.
    On `main`, `prepare` ran `git worktree prune`, and the registration was gone."""
    repo = _repository(tmp_path / "myapp")
    usb = tmp_path / "usb" / "experiment"
    _git(repo, "worktree", "add", "-q", "-b", "experiment", str(usb))
    registered = str(usb.resolve())
    shutil.rmtree(tmp_path / "usb")

    box = WorktreeSandbox(root=tmp_path / "boxes")
    ws = box.prepare(repo_path=repo, base_branch="main", branch="openfactory/29")
    assert ws.path.is_dir()
    assert registered in _registered(repo), _registered(repo)


@pytest.fixture(params=["boxes", "my boxes", "symlinked"])
def box_root(tmp_path, request):
    """Where the box keeps its worktrees: plain, with a space, and through a symlink, which git
    lists by its real path, so `ours` must be resolved on both sides to be recognised."""
    if request.param != "symlinked":
        return tmp_path / request.param
    real = tmp_path / "real-boxes"
    real.mkdir()
    link = tmp_path / "linked-boxes"
    os.symlink(real, link)
    return link


def test_the_platforms_own_leftover_is_still_cleared(tmp_path, box_root):
    """The reverse guard of the prune's removal: green on `main`, and it stays green. A previous
    `prepare` of the same branch left its worktree (a) on disk, and (b) deleted but still
    registered. Both times the box's own registration is taken and the job starts."""
    repo = _repository(tmp_path / "myapp")
    box = WorktreeSandbox(root=box_root)
    first = _keep(box, repo)
    assert first.path.is_dir()

    again = _keep(box, repo)
    assert again.path.is_dir()

    shutil.rmtree(again.path)
    assert str(again.path.resolve()) in _registered(repo)
    third = _keep(box, repo)
    assert (third.path / "work.py").read_text() == "WORK = True\n"


def test_once_the_tree_is_removed_the_branch_is_checked_out_with_its_work(held):
    """Criterion 4, at the box: refused while held; freed, the same call checks the branch out at
    its tip, with the job's committed work in it."""
    repo, review, box = held
    tip = _sha(repo, f"refs/heads/{BRANCH}")
    with pytest.raises(RuntimeError):
        _keep(box, repo)
    _git(repo, "worktree", "remove", "--force", str(review))
    ws = _keep(box, repo)
    assert _git(ws.path, "rev-parse", "HEAD") == tip
    assert _git(ws.path, "symbolic-ref", "--short", "HEAD") == BRANCH
    assert (ws.path / "work.py").read_text() == "WORK = True\n"


def test_a_holder_git_cannot_be_asked_about_does_not_read_as_free(held, monkeypatch):
    """Engineering lessons §2: "could not see" is not "nobody holds it". When the porcelain cannot
    be read, `worktree add` is the judge: it still refuses, the error is git's as before, and no
    path the box never read is invented. Never a silent start from the base."""
    repo, review, box = held
    real = worktree_box._run

    def unreadable(cmd, **kw):
        if cmd[3:5] == ["worktree", "list"]:
            return 128, "fatal: could not read the worktree list\n"
        return real(cmd, **kw)

    monkeypatch.setattr(worktree_box, "_run", unreadable)
    before = _sha(repo, f"refs/heads/{BRANCH}")
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    assert type(caught.value) is RuntimeError, type(caught.value)
    assert "worktree add failed" in str(caught.value)
    assert _sha(repo, f"refs/heads/{BRANCH}") == before
    assert str(review.resolve()) in _registered(repo)
