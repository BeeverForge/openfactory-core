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
import re
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


def _git_in(repo: Path, verb: str, path: Path) -> str:
    """`git -C <repo> worktree <verb> <path>`, quoted as the sentence quotes it: every command
    names the repository, so it works from wherever the person's shell is."""
    return (f"git -C {shlex.quote(str(repo))} worktree {verb} "
            f"{shlex.quote(str(Path(path).resolve()))}")


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
        assert words not in said.lower(), f"git's own sentence reached the person: {said!r}"
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
        assert words not in said.lower(), f"git's own sentence reached the person: {said!r}"
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
        assert words not in said.lower(), f"git's own sentence reached the person: {said!r}"
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
    assert f"{_git_in(repo, 'remove', review)}`" in said, said
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
        assert words not in said.lower(), f"git's own sentence reached the person: {said!r}"
    assert str(repo.resolve()) in said, said
    assert "switch" in said, said
    assert "worktree remove" not in said, said  # in any spelling, `-C <repo>` or not

    assert caught.value.main is True


def test_a_locked_review_tree_is_told_to_unlock_first(held):
    """`git worktree remove` of a locked tree is `fatal: cannot remove a locked working tree`
    (git 2.43.0, measured for #623), so a remedy that skips the unlock is one that fails."""
    repo, review, box = held
    _git(repo, "worktree", "lock", "--reason", "on a usb disk", str(review))
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    said = str(caught.value)
    unlock, remove = _git_in(repo, "unlock", review), _git_in(repo, "remove", review)
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
        assert words not in said.lower(), f"git's own sentence reached the person: {said!r}"
    assert "fatal" not in said and "já" not in said, said

    from openfactory.adapters.sandbox.worktree import branch_held

    assert said == branch_held(BRANCH, str(review.resolve()), main=False, locked=False,
                               repo=str(repo))


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


def test_a_lock_without_a_reason_is_told_to_unlock_first(held):
    """`git worktree lock` with no `--reason` prints a bare `locked` line (2.34.1 and 2.43.0,
    measured 2026-10-17), and `remove` refuses that tree as it refuses one locked with a reason."""
    repo, review, box = held
    _git(repo, "worktree", "lock", str(review))
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    assert _git_in(repo, "unlock", review) in str(caught.value)
    assert caught.value.locked is True


def test_a_branch_checked_out_between_the_read_and_the_add_is_named_too(tmp_path, monkeypatch):
    """The race window: free at the first read, held by the time `worktree add` runs. The
    porcelain is asked again after git refuses, so the person still reads the tree's name and not
    git's sentence (review of 24e59fe: without the second read, all of this file stayed green)."""
    repo = _repository(tmp_path / "myapp")
    review = tmp_path / "review tree"
    box = WorktreeSandbox(root=tmp_path / "boxes")
    real, calls = worktree_box._holder, []

    def late(repo_path, branch):
        calls.append(branch)
        if len(calls) == 1:
            _git(repo, "worktree", "add", "-q", str(review), BRANCH)
            return None
        return real(repo_path, branch)

    monkeypatch.setattr(worktree_box, "_holder", late)
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    from openfactory.adapters.sandbox.base import BranchHeldElsewhere
    assert isinstance(caught.value, BranchHeldElsewhere), str(caught.value)
    assert caught.value.path == str(review.resolve())


# ── follow the sentence, then resume: what it told the person to keep is still there ────────────
#
# Review of 268c726. The sentence said "commit or stash anything there first", then remove the
# tree, then resume. Only the local forge's continuing door keeps the local branch: every other
# door runs `branch -D` and builds it again, from the base or from the forge, so a commit made
# where the sentence said ended up on no branch. These tests run the command the sentence gives,
# word for word, and then resume.

def _commands(said: str) -> list[str]:
    """Every command the sentence gives, in order, as it is written between backticks."""
    return re.findall(r"`(git [^`]+)`", said)


def _run_as_written(command: str, name: str = "keep-mine", where: Path | None = None) -> None:
    command = command.replace("<a branch of yours>", name)
    if where is not None:
        command = command.replace("<a path of yours>", shlex.quote(str(where)))
    argv = shlex.split(command)
    p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"{command}: {p.stderr}"


def _is_on(repo: Path, sha: str, branch: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", sha, branch],
                          capture_output=True).returncode == 0


def test_on_the_continuing_local_door_a_commit_made_where_it_says_reaches_the_job(held):
    """The local forge's continuing door keeps the branch: commit there, remove the tree as told,
    resume, and the commit is in the job's tree."""
    repo, review, box = held
    _commit(review, "notes.txt", "what I noticed reviewing\n", "mine")
    mine = _sha(review, "HEAD")
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    said = str(caught.value)
    assert "commit" in said, said
    _run_as_written(next(c for c in _commands(said) if "worktree remove" in c))
    ws = _keep(box, repo)
    assert _is_on(ws.path, mine, "HEAD"), "the commit the sentence asked for is not in the job"


def _follow_the_switch_then_resume(repo: Path, review: Path, go) -> None:
    """Commit in the review tree, run the `switch -c` the refusal gives, resume: the commit is on
    the person's own branch, and the job starts."""
    _commit(review, "notes.txt", "what I noticed reviewing\n", "mine")
    mine = _sha(review, "HEAD")
    with pytest.raises(RuntimeError) as caught:
        go()
    said = str(caught.value)
    assert "commit or stash anything there first" not in said, said
    (switch,) = [c for c in _commands(said) if "switch -c" in c]
    _run_as_written(switch)
    go()
    assert _is_on(repo, mine, "keep-mine"), "the person's commit is on no branch of theirs"


def test_on_a_fresh_door_what_the_person_follows_keeps_their_commit(held):
    """A fresh job builds the branch again from the base. The sentence must not send the person's
    commit onto it: it gives `switch -c`, which keeps the commit on a branch of theirs and frees
    the card's branch in one command, in a locked tree too (2.34.1 and 2.43.0, measured)."""
    repo, review, box = held
    _follow_the_switch_then_resume(repo, review, lambda: box.prepare(
        repo_path=repo, base_branch="main", branch=BRANCH, checkout_existing=False))


def test_on_a_hosted_continuing_door_what_the_person_follows_keeps_their_commit(hosted):
    """The hosted forge's continuing door builds the branch again from the forge's copy, so a
    commit made in the person's clone and not pushed would be left on no branch."""
    repo, review, remote, box = hosted
    _follow_the_switch_then_resume(repo, review, lambda: box.prepare(
        repo_path=repo, base_branch="main", branch=BRANCH, checkout_existing=True,
        remote_url=remote))


def test_the_persons_own_checkout_on_a_fresh_door_is_told_to_switch_to_a_new_branch(tmp_path):
    """The person's own checkout, on a door that builds the branch again: `switch <another
    branch>` would leave their commits on the branch the job then deletes."""
    repo = _repository(tmp_path / "myapp")
    _git(repo, "switch", "-q", BRANCH)
    _commit(repo, "notes.txt", "mine\n", "mine")
    mine = _sha(repo, "HEAD")
    box = WorktreeSandbox(root=tmp_path / "boxes")
    go = lambda: box.prepare(repo_path=repo, base_branch="main", branch=BRANCH,  # noqa: E731
                             checkout_existing=False)
    with pytest.raises(RuntimeError) as caught:
        go()
    (switch,) = [c for c in _commands(str(caught.value)) if "switch -c" in c]
    _run_as_written(switch)
    go()
    assert _is_on(repo, mine, "keep-mine")


# ── a tree whose directory is gone, and the box's own tree when a person locked it ─────────────

@pytest.mark.parametrize("locked", [False, True], ids=["unlocked", "locked"])
def test_a_review_tree_deleted_by_hand_says_the_directory_is_gone(held, locked):
    """`rm -rf` of a review tree leaves git's registration, and git still refuses the branch. The
    porcelain says `prunable gitdir file points to non-existent location`, or only `locked` for a
    locked one (2.34.1 and 2.43.0, measured). There is nothing in it to commit or stash: the
    sentence says the directory is gone, and the command it gives frees the branch."""
    repo, review, box = held
    if locked:
        _git(repo, "worktree", "lock", str(review))
    shutil.rmtree(review)
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    said = str(caught.value)
    assert "directory is not there" in said, said
    assert "commit or stash" not in said, said
    for command in _commands(said):
        _run_as_written(command)
    _keep(box, repo)


def test_the_box_s_own_tree_a_person_locked_is_left_with_what_is_in_it(tmp_path):
    """The platform never locks a tree, so a lock on the box's own tree is a person's "keep this".
    One `--force` does not remove a locked tree (rc 128, 2.34.1 and 2.43.0), and the `rmtree` after
    it deleted the directory anyway, then said nothing in it was touched."""
    repo = _repository(tmp_path / "myapp")
    box = WorktreeSandbox(root=tmp_path / "boxes")
    ws = _keep(box, repo)
    (ws.path / "kept.txt").write_text("keep this\n")
    _git(repo, "worktree", "lock", "--reason", "keep this", str(ws.path))
    with pytest.raises(RuntimeError) as caught:
        _keep(box, repo)
    from openfactory.adapters.sandbox.base import BranchHeldElsewhere
    assert isinstance(caught.value, BranchHeldElsewhere), str(caught.value)
    assert (ws.path / "kept.txt").read_text() == "keep this\n"
    said = str(caught.value)
    assert "the job's own" in said, said
    assert _git_in(repo, "unlock", ws.path) in said, said


# ── review of 83973c2: the same rule, where last round's fixes did not reach ────────────────────

def _fresh(box: WorktreeSandbox, repo: Path):
    """A fresh job on the local forge: the branch is built again from the base."""
    return box.prepare(repo_path=repo, base_branch="main", branch=BRANCH, checkout_existing=False,
                       remote_url=str(repo))


def _until_resume(said: str) -> list[str]:
    """The commands the person runs before resuming, in order."""
    return _commands(said.split("then resume")[0])


def test_the_box_s_own_locked_tree_on_a_fresh_door_frees_when_followed_and_keeps_its_work(tmp_path):
    """`switch -c` frees the branch, but the locked tree still stands at the box's own path, and
    `worktree add -b` then fails with git's `already exists`. The sentence frees the path too, by
    moving the tree somewhere of the person's: what is in it stays theirs."""
    repo = _repository(tmp_path / "myapp")
    box = WorktreeSandbox(root=tmp_path / "boxes")
    wt = _keep(box, repo).path
    _commit(wt, "kept.txt", "keep this\n", "mine")
    mine = _sha(wt, "HEAD")
    (wt / "draft.txt").write_text("not committed\n")
    _git(repo, "worktree", "lock", "--reason", "keep this", str(wt))
    with pytest.raises(RuntimeError) as caught:
        _fresh(box, repo)
    for command in _until_resume(str(caught.value)):
        _run_as_written(command, where=tmp_path / "mine")
    _fresh(box, repo)
    assert _is_on(repo, mine, "keep-mine"), "the person's commit is on no branch of theirs"
    assert (tmp_path / "mine" / "draft.txt").read_text() == "not committed\n", "the draft was lost"


def test_a_deleted_review_tree_on_a_fresh_door_keeps_the_commits_made_in_it(held):
    """A commit made in a review tree is on the card's branch, which outlives `rm -rf` of the tree.
    A door that builds the branch again would drop it: the sentence keeps it on a branch first."""
    repo, review, box = held
    _commit(review, "notes.txt", "what I noticed reviewing\n", "mine")
    mine = _sha(review, "HEAD")
    shutil.rmtree(review)
    with pytest.raises(RuntimeError) as caught:
        _fresh(box, repo)
    said = str(caught.value)
    assert "Nothing in it can be reached to lose" not in said, said
    assert "mount" in said, said
    for command in _until_resume(said):
        _run_as_written(command)
    _fresh(box, repo)
    assert _is_on(repo, mine, "keep-mine"), "the commit made in the deleted tree is on no branch"


def test_the_box_s_own_tree_a_person_locked_is_not_deleted_by_cleanup_either(tmp_path):
    """`cleanup` ends every run, repair and review, with the same `remove --force` a locked tree
    refuses, then an `rmtree`. The lock is a person's "keep this" there too."""
    repo = _repository(tmp_path / "myapp")
    box = WorktreeSandbox(root=tmp_path / "boxes")
    ws = _keep(box, repo)
    (ws.path / "kept.txt").write_text("keep this\n")
    _git(repo, "worktree", "lock", "--reason", "keep this", str(ws.path))
    box.cleanup(workspace=ws)
    assert (ws.path / "kept.txt").read_text() == "keep this\n", "cleanup deleted a locked tree"


def test_the_race_on_a_fresh_door_is_worded_for_the_fresh_door(tmp_path, monkeypatch):
    """The second porcelain read, after git refuses the add, names the door it is on too."""
    repo = _repository(tmp_path / "myapp")
    review = tmp_path / "review tree"
    box = WorktreeSandbox(root=tmp_path / "boxes")
    real, calls = worktree_box._holder, []

    def late(repo_path, branch):
        calls.append(branch)
        if len(calls) == 1:
            _git(repo, "worktree", "add", "-q", str(review), BRANCH)
            return None
        return real(repo_path, branch)

    monkeypatch.setattr(worktree_box, "_holder", late)
    with pytest.raises(RuntimeError) as caught:
        _fresh(box, repo)
    said = str(caught.value)
    assert "switch -c" in said and "commit or stash" not in said, said


@pytest.mark.skipif(os.geteuid() == 0, reason="root searches any directory")
def test_a_holder_under_a_directory_the_box_cannot_search_still_holds_the_job(held):
    """`Path.exists()` raises `PermissionError` under a directory the box cannot search (3.12).
    What cannot be looked at is not "not there": the job still holds, naming the tree."""
    from openfactory.adapters.sandbox.base import BranchHeldElsewhere
    repo, review, box = held
    closed = review.parent / "closed"
    closed.mkdir()
    _git(repo, "worktree", "move", str(review), str(closed / "review"))
    closed.chmod(0)
    try:
        with pytest.raises(BranchHeldElsewhere) as caught:
            _keep(box, repo)
        assert "is not there" not in str(caught.value), str(caught.value)
    finally:
        closed.chmod(0o755)


@pytest.mark.skipif(os.geteuid() == 0, reason="root searches any directory")
def test_a_holder_under_a_directory_the_box_cannot_search_still_holds_the_job_on_3_14(
        held, monkeypatch):
    """From 3.14 `Path.exists()` answers False under a directory the box cannot search instead of
    raising (#827). Pinned without a 3.14 interpreter: the tree is still not reported gone."""
    from openfactory.adapters.sandbox.base import BranchHeldElsewhere
    repo, review, box = held
    closed = review.parent / "closed"
    closed.mkdir()
    _git(repo, "worktree", "move", str(review), str(closed / "review"))
    real = Path.exists
    monkeypatch.setattr(Path, "exists", lambda self, *a, **kw: (
        False if closed in self.parents else real(self, *a, **kw)))
    closed.chmod(0)
    try:
        with pytest.raises(BranchHeldElsewhere) as caught:
            _keep(box, repo)
        assert "is not there" not in str(caught.value), str(caught.value)
    finally:
        closed.chmod(0o755)
