"""A re-run starts again after the box's own `git worktree add` was interrupted, and a lock a person
made is never removed.

THE SECOND SHAPE OF #746, "an interrupted earlier run". The box's process dies (SIGKILL, the OOM
killer, power loss) while git checks the card's tree out, or `_run`'s timeout kills the git parent
of a slow checkout. Git leaves the tree registered at the box's path and LOCKED, and on c0a50f3
the re-run refused with `BranchHeldElsewhere` ("… the job's own from an earlier pass, which
somebody locked, so it was left as it is …", then a `worktree unlock` command): the person was
told to undo a lock no person made. Reproduced on c0a50f3 for both shapes (2026-10-18).

WHAT `git worktree add` WRITES, AND WHEN (source: `builtin/worktree.c` `add_worktree`, v2.34.1
:306-309, v2.47.3 :480-483). `<common>/worktrees/<id>/locked` is written right after the admin
directory is made, BEFORE `gitdir`, `.git`, `HEAD`, `commondir` and the checkout, and unlinked only
after the checkout returns (v2.47.3 :555-558). Its bytes are git's TRANSLATED `_("initializing")`
plus a newline: `initializing\\n`, 13 bytes, under `C` on every version measured (2.34.1, 2.39.5,
2.43.0, 2.47.3) and under `pt_BR.UTF-8` where no catalogue translates it; but on 2.39.5 with its
catalogues (`debian:bookworm`) `de_DE.UTF-8` writes `initialisiere\\n` and `es_ES.UTF-8` writes
`inicializando\\n`. `LC_ALL=C` gives `initializing\\n` even with `LANG=de_DE.UTF-8` or
`LANGUAGE=de` set (2.39.5, measured). On 2.28 the string is not marked for translation.

THE SHAPES IT LEAVES, measured on 2.43.0 through the box's own `prepare` (2026-10-18):
- the whole process group killed during the checkout: the tree is registered, `locked
  initializing`, the admin directory holds `index.lock` and no `index`;
- the add timed out (`subprocess.run(timeout=…)` kills its direct child only): the git parent
  dies, the `reset --hard` child finishes the checkout, the admin directory holds `index` and
  `ORIG_HEAD`, and the lock stays for good;
- the box's Python alone killed during the checkout: git loses the reader of its output pipe,
  a git process dies of SIGPIPE (strace), and git removes its half-made tree and admin directory
  itself; only the branch is left;
- the box's Python killed in the instant after the add returned: a finished, unlocked tree.

AND NOTHING GIT LEAVES TELLS THE TIMED-OUT ADD FROM A PERSON. `git worktree lock --reason
initializing` writes `initializing\\n`, byte for byte the add's, and the same porcelain, on 2.34.1,
2.43.0 and 2.47.3; a bare `git worktree lock` writes an empty file. So the human chose (option A,
2026-10-18) that the box marks its own add before it runs it, runs that one add under `LC_ALL=C`,
and removes a locked tree at its path only when git's lock bytes are `initializing\\n` AND its own
mark names this repository and that path. Any other lock is a person's "keep this" (#623's
guarantee) and is left with what is in it.

Every interrupted state is made the way it happens: a real child process runs `prepare` (or plain
`git worktree add`) in a session of its own, a smudge filter holds the checkout open, and the test
kills only the process group it started. No `locked` file is written by hand.
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from openfactory.adapters.sandbox import worktree as worktree_box
from openfactory.adapters.sandbox.base import BranchHeldElsewhere
from openfactory.adapters.sandbox.worktree import WorktreeSandbox
from openfactory.techlead.classify import TREE, classify

BRANCH = "openfactory/28"
NAME = BRANCH.replace("/", "-")
#: Bounds on every wait, so a test that fails never leaves a process waiting on a file.
WAIT = 60.0


def _git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"git {' '.join(args)}: {p.stderr}"
    return p.stdout.strip()


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgSign=false",
         "commit", "-q", "-m", message)


class Slow:
    """A repository whose checkout of `slow.txt` waits, through a smudge filter, until the test
    touches `release`; the filter touches `started` first."""

    def __init__(self, where: Path):
        self.repo = where
        self.started = where.parent / f"{where.name}.started"
        self.release = where.parent / f"{where.name}.release"
        subprocess.run(["git", "init", "-q", "-b", "main", str(where)], capture_output=True,
                       check=True)
        (where / "README.md").write_text("# app\n")
        (where / ".gitattributes").write_text("slow.txt filter=slow\n")
        (where / "slow.txt").write_text("checked out slowly\n")
        _commit(where, "base")
        _git(where, "switch", "-q", "-c", BRANCH)
        (where / "work.py").write_text("WORK = True\n")
        _commit(where, "the job's work")
        _git(where, "switch", "-q", "main")
        smudge = where.parent / f"{where.name}.smudge.sh"
        smudge.write_text(textwrap.dedent(f"""\
            #!/bin/sh
            touch {shlex.quote(str(self.started))}
            i=0
            while [ ! -e {shlex.quote(str(self.release))} ] && [ $i -lt 600 ]; do
                sleep 0.1; i=$((i+1))
            done
            cat
            """))
        smudge.chmod(0o755)
        # repository config, under `tmp_path` only; git runs the filter through a shell
        _git(where, "config", "filter.slow.smudge", shlex.quote(str(smudge)))

    @property
    def admin(self) -> Path:
        return (self.repo / ".git" / "worktrees" / NAME)


def _wait_for(what, why: str) -> None:
    deadline = time.monotonic() + WAIT
    while not what():
        assert time.monotonic() < deadline, f"timed out waiting: {why}"
        time.sleep(0.05)


def _group_gone(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    return False


_CHILD = textwrap.dedent("""\
    import os, signal, sys
    from pathlib import Path
    from openfactory.adapters.sandbox import worktree as w
    shape, root, repo, branch = sys.argv[1:5]
    real = w._run
    def run(cmd, **kw):
        is_add = cmd[3:5] == ["worktree", "add"]
        if is_add and shape == "add_timed_out":
            kw["timeout"] = 2
        answer = real(cmd, **kw)
        if is_add and shape == "python_killed_after_the_add_returned":
            os.kill(os.getpid(), signal.SIGKILL)
        return answer
    w._run = run
    w.WorktreeSandbox(root=Path(root)).prepare(repo_path=Path(repo), base_branch="main",
                                               branch=branch)
    """)


def _interrupt(slow: Slow, root: Path, shape: str, *, env: dict[str, str] | None = None,
               plain_git: bool = False) -> None:
    """Run the box's own `prepare` (or, `plain_git`, a bare `git worktree add -b` as a release
    before this one or a person would) in a session of its own, and interrupt it as `shape` says.
    Kills only the process group it started; returns once every process of it has ended."""
    wt = root / NAME
    if plain_git:
        root.mkdir(parents=True, exist_ok=True)
        # as the box's `prepare` did before it: the branch is deleted, then made by the add
        _git(slow.repo, "branch", "-D", BRANCH)
        argv = ["git", "-C", str(slow.repo), "worktree", "add", "-b", BRANCH, str(wt), "main"]
    else:
        argv = [sys.executable, "-c", _CHILD, shape, str(root), str(slow.repo), BRANCH]
    if shape == "python_killed_after_the_add_returned":
        slow.release.touch()
    child = subprocess.Popen(argv, start_new_session=True, env=env, cwd=slow.repo.parent,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        if shape != "python_killed_after_the_add_returned":
            _wait_for(slow.started.exists, "the checkout to start")
        if shape == "process_group_killed":
            os.killpg(child.pid, signal.SIGKILL)
        elif shape == "python_killed_during_checkout":
            os.kill(child.pid, signal.SIGKILL)
        child.wait(timeout=WAIT)
        slow.release.touch()
        _wait_for(lambda: _group_gone(child.pid), "the interrupted add's processes to end")
    finally:
        slow.release.touch()
        if not _group_gone(child.pid):
            os.killpg(child.pid, signal.SIGKILL)
        if child.poll() is None:
            child.kill()
        child.wait()
        child.stdout.close()


def _porcelain_of(repo: Path, wt: Path) -> list[str]:
    """The porcelain's lines for the tree at `wt`, or `[]`."""
    for block in _git(repo, "worktree", "list", "--porcelain").split("\n\n"):
        lines = block.splitlines()
        if lines and lines[0] == f"worktree {wt.resolve()}":
            return lines
    return []


def _snapshot(path: Path) -> dict[str, bytes | None]:
    seen: dict[str, bytes | None] = {}
    for top, dirs, files in os.walk(path):
        for d in dirs:
            seen[os.path.relpath(Path(top) / d, path)] = None
        for f in files:
            seen[os.path.relpath(Path(top) / f, path)] = (Path(top) / f).read_bytes()
    return seen


def _beside(root: Path, wt: Path) -> list[str]:
    """What the root holds besides the tree itself: a mark the box left would be here."""
    return sorted(n for n in os.listdir(root) if n != wt.name)


def _assert_started_clean(ws, wt: Path, slow: Slow, root: Path) -> None:
    assert ws.path == wt
    common = (ws.path / _git(ws.path, "rev-parse", "--git-common-dir")).resolve()
    assert common == (slow.repo / ".git").resolve(), common
    assert _git(ws.path, "symbolic-ref", "--short", "HEAD") == BRANCH
    lines = _porcelain_of(slow.repo, wt)
    assert lines, "the new tree is not registered"
    assert not any(line.split(" ", 1)[0] == "locked" for line in lines), lines
    assert _beside(root, wt) == [], f"the root still holds {_beside(root, wt)}"


@pytest.fixture(params=["boxes", "my boxes", "symlinked"])
def box_root(tmp_path, request):
    """Plain, with a space, and through a symlink (copied from the #623 file)."""
    if request.param != "symlinked":
        return tmp_path / request.param
    real = tmp_path / "real-boxes"
    real.mkdir()
    link = tmp_path / "linked-boxes"
    os.symlink(real, link)
    return link


def _again(root: Path, slow: Slow):
    return WorktreeSandbox(root=root).prepare(repo_path=slow.repo, base_branch="main",
                                              branch=BRANCH)


# ── the box's own interrupted add is cleared, and the job starts ────────────────────────────────

@pytest.mark.parametrize("shape", ["process_group_killed", "add_timed_out"])
def test_a_box_killed_while_git_checked_out_its_tree_starts_again_on_the_rerun(
        tmp_path, box_root, shape):
    """C6. On c0a50f3 the re-run raised `BranchHeldElsewhere: … the job's own from an earlier pass,
    which somebody locked, so it was left as it is …`, for both shapes."""
    slow = Slow(tmp_path / "myapp")
    wt = box_root / NAME
    _interrupt(slow, box_root, shape)
    assert (slow.admin / "locked").read_bytes() == b"initializing\n"
    if shape == "process_group_killed":
        assert (slow.admin / "index.lock").exists() and not (slow.admin / "index").exists()
    else:
        assert (slow.admin / "index").exists()
    _assert_started_clean(_again(box_root, slow), wt, slow, box_root)


def test_the_box_s_worktree_add_writes_its_lock_in_git_s_untranslated_words(tmp_path,
                                                                             monkeypatch):
    """C6. The deployment's locale reaches the add on c0a50f3: a `git` shim first on `PATH`
    recorded `LC_ALL=pt_BR.UTF-8` and `LANGUAGE=de` for it, and on a git with its catalogues
    (2.39.5, `de_DE.UTF-8`) that add writes `initialisiere\\n`. The box's add runs under `LC_ALL=C`
    without `LANGUAGE`, so the lock it leaves is `initializing\\n` whatever the locale."""
    real_git = shutil.which("git")
    assert real_git, "no git on PATH"
    shim_dir, log = tmp_path / "shim", tmp_path / "git-calls.txt"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        printf 'LC_ALL=%s LANGUAGE=%s ARGV=%s\\n' "${{LC_ALL-<unset>}}" "${{LANGUAGE-<unset>}}" \\
            "$*" >> {shlex.quote(str(log))}
        exec {shlex.quote(real_git)} "$@"
        """))
    shim.chmod(0o755)
    slow = Slow(tmp_path / "myapp")
    monkeypatch.setenv("LC_ALL", "pt_BR.UTF-8")
    monkeypatch.setenv("LANGUAGE", "de")
    env = {**os.environ, "PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}"}
    root = tmp_path / "boxes"
    _interrupt(slow, root, "process_group_killed", env=env)

    adds = [line for line in log.read_text().splitlines() if " worktree add " in f" {line} "]
    assert len(adds) == 1, log.read_text()
    assert adds[0].startswith("LC_ALL=C LANGUAGE=<unset> ARGV="), adds[0]
    assert (slow.admin / "locked").read_bytes() == b"initializing\n"


@pytest.mark.parametrize("outcome", ["succeeded", "refused"])
def test_no_mark_is_left_by_an_add_that_returned(tmp_path, monkeypatch, outcome):
    """C6. The box's mark lives only while its add runs. REVERSE GUARD: green on c0a50f3, which
    writes no mark at all; the mutation that stops unlinking it after the add returned turns it
    red. `refused`: free at the porcelain read, held by the time the add runs (the race of the
    #623 file), so git refuses the add and the box names the holder."""
    slow = Slow(tmp_path / "myapp")
    slow.release.touch()
    root = tmp_path / "boxes"
    wt = root / NAME
    if outcome == "refused":
        review = tmp_path / "review tree"
        real, calls = worktree_box._holder, []

        def late(repo_path, branch):
            calls.append(branch)
            if len(calls) == 1:
                _git(slow.repo, "worktree", "add", "-q", str(review), BRANCH)
                return None
            return real(repo_path, branch)

        monkeypatch.setattr(worktree_box, "_holder", late)
        with pytest.raises(BranchHeldElsewhere):
            WorktreeSandbox(root=root).prepare(repo_path=slow.repo, base_branch="main",
                                               branch=BRANCH, checkout_existing=True,
                                               remote_url=str(slow.repo))
    else:
        assert _again(root, slow).path == wt
    assert _beside(root, wt) == [], f"the root still holds {_beside(root, wt)}"


@pytest.mark.parametrize("shape", ["python_killed_during_checkout",
                                   "python_killed_after_the_add_returned"])
def test_a_mark_a_killed_box_left_goes_on_the_rerun(tmp_path, shape):
    """C6. The box's Python dies with its mark written and git not interrupted with it: during the
    checkout (git then removes its own half-made tree, measured: the tree and its admin directory
    are gone, the branch is left), or in the instant after the add returned (a finished, unlocked
    tree). The re-run starts and the root holds no mark. REVERSE GUARD: green on c0a50f3, which
    writes no mark and clears an unlocked tree of its own; the mutations that drop the mark's
    unlink turn it red."""
    slow = Slow(tmp_path / "myapp")
    root = tmp_path / "boxes"
    wt = root / NAME
    _interrupt(slow, root, shape)
    assert not (slow.admin / "locked").exists()
    _assert_started_clean(_again(root, slow), wt, slow, root)


# ── a lock a person made is never removed (#623's guarantee) ────────────────────────────────────

def _held_and_untouched(slow: Slow, root: Path) -> None:
    """Re-run, and assert the refusal is the hold naming the unlock, and that nothing of the tree,
    its porcelain line or its lock bytes changed."""
    wt = root / NAME
    (wt / "kept.txt").write_text("keep this\n")
    tree, lines, locked = (_snapshot(wt), _porcelain_of(slow.repo, wt),
                           (slow.admin / "locked").read_bytes())
    assert any(line.split(" ", 1)[0] == "locked" for line in lines), lines
    with pytest.raises(BranchHeldElsewhere) as caught:
        _again(root, slow)
    assert "worktree unlock" in str(caught.value), str(caught.value)
    assert _snapshot(wt) == tree, "the locked tree was changed"
    assert (wt / "kept.txt").read_text() == "keep this\n"
    assert _porcelain_of(slow.repo, wt) == lines
    assert (slow.admin / "locked").read_bytes() == locked


def test_a_person_s_lock_with_the_reason_initializing_on_a_finished_tree_is_left_with_what_is_in_it(  # noqa: E501
        tmp_path):
    """C6, #623's guarantee. `git worktree lock --reason initializing` writes the add's own bytes
    (`initializing\\n`, 2.34.1, 2.43.0 and 2.47.3, measured); on a tree whose add returned, the box
    holds no mark, so the lock is a person's. REVERSE GUARD: green on c0a50f3, which removes no
    lock; the mutation that drops the mark check turns it red."""
    slow = Slow(tmp_path / "myapp")
    slow.release.touch()
    root = tmp_path / "boxes"
    _again(root, slow)
    _git(slow.repo, "worktree", "lock", "--reason", "initializing", str(root / NAME))
    assert (slow.admin / "locked").read_bytes() == b"initializing\n"
    _held_and_untouched(slow, root)


@pytest.mark.parametrize("lock", [[], ["--reason", "keep this"]], ids=["bare", "with-a-reason"])
def test_a_person_s_lock_on_a_tree_whose_add_was_interrupted_is_left_with_what_is_in_it(
        tmp_path, lock):
    """C6, #623's guarantee. The box's own add was interrupted (its mark is there), then a person
    unlocked the tree and locked it again as theirs. REVERSE GUARD: green on c0a50f3; the mutations
    that drop the lock-bytes comparison, or that let a bare lock count, turn it red."""
    slow = Slow(tmp_path / "myapp")
    root = tmp_path / "boxes"
    _interrupt(slow, root, "process_group_killed")
    _git(slow.repo, "worktree", "unlock", str(root / NAME))
    _git(slow.repo, "worktree", "lock", *lock, str(root / NAME))
    _held_and_untouched(slow, root)


def test_an_interrupted_add_of_another_repository_at_the_box_s_path_is_left_as_it_was(tmp_path):
    """C6, ours means THIS repository's. In the shared root, another repository's box was killed
    mid-add at the same path, and its mark names that repository. This repository's re-run leaves
    that tree, its lock, and the root (where that box's mark is) as they were. REVERSE GUARD: green
    on c0a50f3 (git refused the add over the path); the mutation that stops comparing the mark's
    repository turns it red."""
    root = tmp_path / "boxes"
    theirs = Slow(tmp_path / "their app")
    _interrupt(theirs, root, "process_group_killed")
    wt = root / NAME
    ours = Slow(tmp_path / "myapp")
    ours.release.touch()
    tree, lines = _snapshot(wt), _porcelain_of(theirs.repo, wt)
    locked, beside = (theirs.admin / "locked").read_bytes(), _beside(root, wt)
    with pytest.raises(RuntimeError):
        _again(root, ours)
    assert _snapshot(wt) == tree, "the other repository's tree was changed"
    assert _porcelain_of(theirs.repo, wt) == lines
    assert (theirs.admin / "locked").read_bytes() == locked
    assert _beside(root, wt) == beside, "what the other repository's box left beside it changed"


def test_an_interrupted_tree_is_kept_when_the_working_tree_list_cannot_be_read(tmp_path,
                                                                               monkeypatch):
    """C6, engineering lessons §2. With the porcelain unreadable the box cannot see that the locked
    tree at its path is its own, so nothing is unlocked or removed, and git's refusal is passed on
    as before. REVERSE GUARD: green on c0a50f3; the mutation that runs the removal on an unread
    list turns it red."""
    slow = Slow(tmp_path / "myapp")
    root = tmp_path / "boxes"
    wt = root / NAME
    _interrupt(slow, root, "process_group_killed")
    tree, lines = _snapshot(wt), _porcelain_of(slow.repo, wt)
    monkeypatch.setattr(worktree_box, "_working_trees", lambda repo_path: None)
    with pytest.raises(RuntimeError) as caught:
        _again(root, slow)
    assert type(caught.value) is RuntimeError, type(caught.value)
    assert "worktree add failed" in str(caught.value), str(caught.value)
    monkeypatch.undo()
    assert _snapshot(wt) == tree
    assert _porcelain_of(slow.repo, wt) == lines
    assert (slow.admin / "locked").read_bytes() == b"initializing\n"


def test_a_lock_the_box_cannot_prove_its_own_says_git_or_a_person_may_have_made_it(tmp_path):
    """C6. An interrupted add the box holds no mark for (plain `git worktree add`, as a release
    before this one ran it, killed by process group) is left, and the hold says what the lock may
    be: a person's, or an interrupted `git worktree add`'s, which the box could not tell apart. On
    c0a50f3 it said "which somebody locked". It still names the unlock, and it is classified as
    it was on c0a50f3 for this hold (`TREE`, "another tree holds the branch", measured)."""
    slow = Slow(tmp_path / "myapp")
    root = tmp_path / "boxes"
    _interrupt(slow, root, "process_group_killed", plain_git=True)
    assert (slow.admin / "locked").read_bytes() == b"initializing\n"
    with pytest.raises(BranchHeldElsewhere) as caught:
        _again(root, slow)
    said = str(caught.value)
    assert "somebody locked" not in said, said
    assert "person" in said and "git worktree add" in said and "interrupted" in said, said
    assert "worktree unlock" in said, said
    verdict = classify(said)
    assert (verdict.cause, verdict.detail) == (TREE, "another tree holds the branch"), verdict


def test_an_interrupted_add_is_still_the_box_s_own_after_a_rerun_that_could_not_read_the_list(
        tmp_path, monkeypatch):
    """C6 with lessons §2, one rerun later. A rerun that cannot read the working-tree list leaves
    the interrupted tree as it is, and runs its own `worktree add`, which git refuses. That add
    must not take the earlier add's mark with it: measured on ee7ba35 (2026-10-18), the refused
    add rewrote the mark and unlinked it on return, and the next rerun, with the list readable,
    held for a person with `BranchHeldElsewhere` ("… which is locked, by a person or by a git
    worktree add that was interrupted …") over the box's own interrupted add."""
    slow = Slow(tmp_path / "myapp")
    root = tmp_path / "boxes"
    wt = root / NAME
    _interrupt(slow, root, "process_group_killed")
    monkeypatch.setattr(worktree_box, "_working_trees", lambda repo_path: None)
    with pytest.raises(RuntimeError):
        _again(root, slow)
    monkeypatch.undo()
    _assert_started_clean(_again(root, slow), wt, slow, root)


def test_an_interrupted_add_whose_unlock_failed_is_still_the_box_s_own_on_the_next_rerun(
        tmp_path, monkeypatch):
    """C6, one rerun later (review of 35ac306). When `worktree unlock` of the box's own interrupted
    add fails, the tree and the box's mark are kept, so the next rerun can still prove the add was
    the box's own; with the mark lost, one transient unlock failure leaves every later rerun
    held behind "may be a person's lock"."""
    slow = Slow(tmp_path / "myapp")
    root = tmp_path / "boxes"
    wt = root / NAME
    _interrupt(slow, root, "process_group_killed")
    real = worktree_box._run

    def refuse_unlock(cmd, **kw):
        if cmd[3:5] == ["worktree", "unlock"]:
            return 128, "fatal: could not unlock\n"
        return real(cmd, **kw)

    monkeypatch.setattr(worktree_box, "_run", refuse_unlock)
    with pytest.raises(BranchHeldElsewhere):
        _again(root, slow)
    monkeypatch.undo()
    _assert_started_clean(_again(root, slow), wt, slow, root)
