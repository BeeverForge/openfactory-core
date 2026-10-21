"""Whatever is at the box's path that is not provably this repository's is left as it was, and the
job refuses by name before it writes anything.

THE RULE #746 KEEPS FROM #623. The box's path is `root / <branch>`, and in production the root
(`<cache>/.openfactory-worktrees`, `factory.py`) is shared by every project the cache serves, so
the directory at that path can be another repository's working tree of a branch with the same
name, a clone somebody made there, or anything a person put there. The issue's literal fix, an
`rmtree` of any leftover, would delete it. Only the box's own tree that THIS repository has
forgotten is removed (`tests/test_a_rerun_over_a_tree_git_has_forgotten_starts.py`); everything
else is left byte for byte, on every door.

THE REFUSAL ON c0a50f3 WAS GIT'S SENTENCE, AFTER THE WRITES. `worktree add` over a non-empty
directory or a file answers rc 128 `fatal: '<wt>' already exists` (git 2.34.1 and 2.43.0,
measured), and `prepare` passed it on as `worktree add failed: …`, which the classifier reads as
`unknown`. By then a fresh door had run `branch -D` on the card's branch, and a hosted resume had
fetched into `refs/remotes/origin/<branch>` (engineering lessons §12: decide before you write).
An EMPTY directory at the path is accepted by git (rc 0, 2.34.1 and 2.43.0), so it is used.

The C2 tests and the empty-directory test are REVERSE GUARDS: green on c0a50f3, where git itself
refused before touching the path, and they stay green; their mutation rows prove they can go red.
Every C3 test is red on c0a50f3.
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
from openfactory.adapters.sandbox.base import BranchHeldElsewhere
from openfactory.adapters.sandbox.worktree import WorktreeSandbox
from openfactory.techlead.classify import TREE, classify

BRANCH = "openfactory/28"
#: git's own words for a path that is taken, in English (2.34.1 and 2.43.0) and as `fatal:`.
GITS_WORDS = ("already exists", "fatal:")

CASES = ["another-repositorys-live-tree", "another-repositorys-forgotten-tree", "a-clone",
         "a-plain-directory", "a-git-file-naming-no-repository",
         "a-git-file-naming-a-symlink-loop", "a-regular-file"]
DOORS = ["fresh", "local-keep", "hosted-resume"]
#: The cases whose `.git` file names another repository, which the sentence names as the owner.
OWNED = {"another-repositorys-live-tree", "another-repositorys-forgotten-tree"}


def _git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"git {' '.join(args)}: {p.stderr}"
    return p.stdout.strip()


def _commit(repo: Path, name: str, text: str, message: str) -> None:
    (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgSign=false",
         "commit", "-q", "-m", message)


def _sha(repo: Path, ref: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
                       capture_output=True, text=True)
    return p.stdout.strip()


def _repository(where: Path, work: str = "WORK = True\n") -> Path:
    """`main`, and the card's branch carrying the job's committed work."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(where)], capture_output=True, check=True)
    _commit(where, "README.md", "# app\n", "base")
    _git(where, "switch", "-q", "-c", BRANCH)
    _commit(where, "work.py", work, "the job's work")
    _git(where, "switch", "-q", "main")
    return where


def _registered(repo: Path) -> list[str]:
    return [line.split(" ", 1)[1] for line in _git(repo, "worktree", "list", "--porcelain")
            .splitlines() if line.startswith("worktree ")]


class Door:
    """One way into `prepare`: the repository the box is handed, and the call."""

    def __init__(self, name: str, repo: Path, remote: str | None, box: WorktreeSandbox):
        self.name, self.repo, self.remote, self.box = name, repo, remote, box

    def prepare(self):
        if self.name == "fresh":
            return self.box.prepare(repo_path=self.repo, base_branch="main", branch=BRANCH)
        return self.box.prepare(repo_path=self.repo, base_branch="main", branch=BRANCH,
                                checkout_existing=True, remote_url=self.remote)


def _door(name: str, tmp_path: Path, root: Path) -> Door:
    box = WorktreeSandbox(root=root)
    if name == "fresh":
        return Door(name, _repository(tmp_path / "myapp"), None, box)
    if name == "local-keep":
        repo = _repository(tmp_path / "myapp")
        return Door(name, repo, str(repo), box)
    # a hosted forge: a bare origin holds the card's branch, the clone's tracking ref is behind it
    origin = tmp_path / "forge.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    seed = _repository(tmp_path / "seed")
    _git(seed, "push", "-q", str(origin), "main", BRANCH)
    clone = tmp_path / "myapp"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], capture_output=True,
                   check=True)
    _git(seed, "switch", "-q", BRANCH)
    _commit(seed, "work.py", "WORK = 2\n", "the factory's second pass")
    _git(seed, "push", "-q", str(origin), BRANCH)
    return Door(name, clone, f"file://{origin}", box)


def _put(case: str, wt: Path, tmp_path: Path) -> Path | None:
    """Put `case` at the box's path `wt`. Answers the other repository, where there is one."""
    wt.parent.mkdir(parents=True, exist_ok=True)
    if case in OWNED or case == "a-clone":
        other = _repository(tmp_path / "other app", work="THEIRS = True\n")
        if case == "a-clone":
            subprocess.run(["git", "clone", "-q", str(other), str(wt)], capture_output=True,
                           check=True)
            (wt / "draft.txt").write_text("a clone of somebody's\n")
            return None
        _git(other, "worktree", "add", "-q", str(wt), BRANCH)
        (wt / "draft.txt").write_text("their work in progress\n")
        if case == "another-repositorys-forgotten-tree":
            away = tmp_path / "away"
            shutil.move(str(wt), str(away))
            _git(other, "worktree", "prune")
            shutil.move(str(away), str(wt))
        return other
    if case == "a-plain-directory":
        wt.mkdir()
        (wt / "notes.txt").write_text("a person's notes\n")
    elif case == "a-git-file-naming-no-repository":
        wt.mkdir()
        (wt / ".git").write_text(f"gitdir: {tmp_path / 'nowhere' / '.git' / 'worktrees' / 'x'}\n")
        (wt / "notes.txt").write_text("a person's notes\n")
    elif case == "a-git-file-naming-a-symlink-loop":
        # 3.12's resolve() raises RuntimeError on a loop, 3.13+ returns it (measured 2026-10-20).
        # On 5c5b832d with 3.12.3, 7 tests here read `RuntimeError: Symlink loop from '.../loop/
        # worktrees/x'` out of `_gitdir_named_by` instead of the box's sentence.
        loop = tmp_path / "loop"
        os.symlink(loop, loop)
        wt.mkdir()
        (wt / ".git").write_text(f"gitdir: {loop / 'worktrees' / 'x'}\n")
        (wt / "notes.txt").write_text("a person's notes\n")
    elif case == "a-regular-file":
        wt.write_text("a file, where the box would put a directory\n")
    else:
        raise AssertionError(f"unknown case {case!r}")
    return None


def _snapshot(path: Path) -> dict[str, bytes | None]:
    """Everything at `path`, by relative name: a file's bytes (a `.git` file's included), `None`
    for a directory."""
    if path.is_file():
        return {".": path.read_bytes()}
    seen: dict[str, bytes | None] = {}
    for top, dirs, files in os.walk(path):
        for d in dirs:
            seen[os.path.relpath(Path(top) / d, path)] = None
        for f in files:
            seen[os.path.relpath(Path(top) / f, path)] = (Path(top) / f).read_bytes()
    return seen


@pytest.fixture(params=["boxes", "my boxes"], ids=["plain-root", "root-with-a-space"])
def root(tmp_path, request):
    return tmp_path / request.param


def _taken(case: str, door_name: str, tmp_path: Path, root: Path):
    door = _door(door_name, tmp_path, root)
    wt = root / BRANCH.replace("/", "-")
    other = _put(case, wt, tmp_path)
    return door, wt, other


# ── C2: what is there is left as it was ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("door_name", DOORS)
@pytest.mark.parametrize("case", CASES)
def test_what_is_at_the_box_s_path_is_left_as_it_was(tmp_path, root, case, door_name):
    """C2. REVERSE GUARD: green on c0a50f3, where git refused the add over it, and it stays green.
    Another repository's tree (live, or forgotten by that repository), a clone, a plain directory
    with a file, a `.git` file naming no repository or a symlink loop, and a regular file are none
    of them provably this repository's forgotten tree, so none is removed."""
    door, wt, other = _taken(case, door_name, tmp_path, root)
    before = _snapshot(wt)
    with pytest.raises(RuntimeError):
        door.prepare()
    assert _snapshot(wt) == before, f"{case} at the box's path was changed"
    if case == "another-repositorys-live-tree":
        assert str(wt.resolve()) in _registered(other), "the other repository lost its tree"


@pytest.mark.parametrize("door_name", DOORS)
def test_an_empty_directory_at_the_box_s_path_is_used(tmp_path, root, door_name):
    """C2, reverse. REVERSE GUARD: green on c0a50f3. Git accepts an empty directory as the add's
    path (rc 0, 2.34.1 and 2.43.0, measured), so the refusal of a taken path must not refuse it."""
    door = _door(door_name, tmp_path, root)
    wt = root / BRANCH.replace("/", "-")
    wt.mkdir(parents=True)
    ws = door.prepare()
    assert ws.path == wt
    assert _git(ws.path, "symbolic-ref", "--short", "HEAD") == BRANCH


# ── C3: the refusal is the box's own sentence, and comes before anything is written ─────────────

def _refusal(door: Door) -> RuntimeError:
    with pytest.raises(RuntimeError) as caught:
        door.prepare()
    return caught.value


@pytest.mark.parametrize("door_name", DOORS)
@pytest.mark.parametrize("case", CASES)
def test_the_refusal_names_the_path_whose_it_is_and_what_moves_it(tmp_path, root, case,
                                                                  door_name):
    """C3. On c0a50f3 the message was `worktree add failed: … fatal: '<wt>' already exists`: git's
    sentence, naming no owner and no remedy, classified `unknown`. It is one sentence of the box's
    own: the path, whose it is, that it was left as it is, the command that moves it (every path
    shell-quoted) and resume. Not a hold on the person's branch: a `RuntimeError`, not
    `BranchHeldElsewhere`, and never classified as an edit or a branch in the person's tree."""
    door, wt, other = _taken(case, door_name, tmp_path, root)
    error = _refusal(door)
    said = str(error)
    assert not isinstance(error, BranchHeldElsewhere), said
    for words in GITS_WORDS:
        assert words not in said, f"git's own sentence reached the person: {said!r}"
    assert str(wt.resolve()) in said, said
    if case in OWNED:
        assert str(other.resolve()) in said, f"the owning repository is not named: {said!r}"
        assert f"{other.resolve()}/.git" not in said, said
    if case == "a-clone":
        assert "a repository of its own" in said, said
    assert "left as it is" in said, said
    assert "resume" in said, said
    moves = _commands(said)
    assert moves, f"no command moves what is there: {said!r}"
    assert all(shlex.quote(str(wt.resolve())) in c for c in moves), said
    assert classify(said).cause != TREE, classify(said)


@pytest.mark.parametrize("case", CASES)
def test_the_refusal_comes_before_the_card_s_branch_is_deleted(tmp_path, root, case):
    """C3, decide before you write (engineering lessons §12). On c0a50f3 a fresh door ran
    `branch -D` before git refused the add, and `worktree add -b` made the branch again at the base
    before it refused the path (git 2.43.0, measured 2026-10-18: the tip moved from the job's work
    to `main`), so the card's branch no longer held what it held."""
    door, wt, other = _taken(case, "fresh", tmp_path, root)
    before = _sha(door.repo, f"refs/heads/{BRANCH}")
    assert before
    with pytest.raises(RuntimeError):
        door.prepare()
    assert _sha(door.repo, f"refs/heads/{BRANCH}") == before, (
        "the card's branch was deleted or moved")


@pytest.mark.parametrize("case", CASES)
def test_on_a_hosted_resume_the_refusal_writes_no_remote_tracking_ref(tmp_path, root, case):
    """C3, the same rule on a hosted resume. On c0a50f3 the fetch wrote the forge's newer push
    into `refs/remotes/origin/<branch>` of the clone, then git refused the add."""
    door, wt, other = _taken(case, "hosted-resume", tmp_path, root)
    tracking = _sha(door.repo, f"refs/remotes/origin/{BRANCH}")
    with pytest.raises(RuntimeError):
        door.prepare()
    assert _sha(door.repo, f"refs/remotes/origin/{BRANCH}") == tracking, "the fetch wrote a ref"


def _commands(said: str) -> list[str]:
    """Every command the sentence gives, as written between backticks."""
    return re.findall(r"`((?:git|mv) [^`]+)`", said)


def _run_as_written(command: str, where: Path) -> None:
    argv = shlex.split(command.replace("<a path of yours>", shlex.quote(str(where))))
    p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"{command}: {p.stderr}"


@pytest.mark.parametrize("case", CASES)
def test_following_the_sentence_frees_the_path_and_the_other_repository_s_tree_still_works(
        tmp_path, case):
    """C3, the command works as written. The root holds a space, so a path that is not quoted
    splits. Run as the sentence gives it, the command moves what was there to a path of the
    person's, with everything in it; the job then starts; and another repository's live tree,
    moved, is still a working tree of that repository (`worktree move`, not `mv`, which would
    break its registration). On c0a50f3 there was no command to follow."""
    root = tmp_path / "my boxes"
    door, wt, other = _taken(case, "fresh", tmp_path, root)
    before = _snapshot(wt)
    said = str(_refusal(door))
    moves = _commands(said)
    assert len(moves) == 1, f"one command moves it: {said!r}"
    mine = tmp_path / "mine, kept"
    _run_as_written(moves[0], mine)
    assert _snapshot(mine) == before, "what was there did not arrive whole"
    ws = door.prepare()
    assert ws.path == wt
    if case == "another-repositorys-live-tree":
        assert str(mine.resolve()) in _registered(other)
        _git(mine, "status", "--short")


@pytest.mark.parametrize("wording", [
    "Preparing worktree (new branch 'openfactory/28')\nfatal: '{wt}' already exists\n",
    "Preparando worktree (novo ramo 'openfactory/28')\nfatal: '{wt}' já existe\n",
], ids=["git-2.34.1", "pt_BR"])
def test_the_refusal_is_the_same_whatever_git_s_wording(tmp_path, monkeypatch, wording):
    """C3, version and locale. The sentence is built from what the box read at the path, never from
    git's prose: with the add answering in another wording, the refusal is the same sentence. On
    c0a50f3 git's sentence was passed through, so the two differed."""
    root = tmp_path / "boxes"
    door, wt, other = _taken("another-repositorys-live-tree", "fresh", tmp_path, root)
    plain = str(_refusal(door))

    real = worktree_box._run

    def worded(cmd, **kw):
        if cmd[3:5] == ["worktree", "add"]:
            return 128, wording.format(wt=wt)
        return real(cmd, **kw)

    monkeypatch.setattr(worktree_box, "_run", worded)
    said = str(_refusal(door))
    assert "já existe" not in said and "fatal:" not in said, said
    assert said == plain, (said, plain)


@pytest.mark.parametrize("door_name", DOORS)
def test_a_symbolic_link_at_the_box_s_path_is_refused_and_nothing_is_checked_out_where_it_points(
        tmp_path, root, door_name):
    """C2 and C3 for a symbolic link at the box's path (review of 35ac306). `git worktree add`
    over a link to an empty directory answers rc 0 on 2.43.0 and registers the link's TARGET,
    which `_same_dir` then read as the box's own: on c0a50f3 the first `prepare` checked the card
    out into the directory the link names, and the rerun's `remove --force` deleted that
    directory, with what had been written into it since. It is refused by name, and the link and
    what it names are left as they were."""
    door = _door(door_name, tmp_path, root)
    wt = root / BRANCH.replace("/", "-")
    theirs = tmp_path / "a directory of theirs"
    theirs.mkdir()
    root.mkdir(parents=True, exist_ok=True)
    os.symlink(theirs, wt)
    error = _refusal(door)
    said = str(error)
    assert not isinstance(error, BranchHeldElsewhere), said
    assert "a symbolic link" in said, said
    assert os.path.islink(wt) and os.readlink(wt) == str(theirs)
    assert os.listdir(theirs) == [], "the job checked out into the directory the link names"


def test_another_repository_s_tree_whose_list_cannot_be_read_is_told_to_move_with_git_not_mv(
        tmp_path, monkeypatch):
    """C3 with lessons §2, for the owner (review of 35ac306). When the other repository's list
    cannot be read, the box cannot tell its live tree from one it forgot; `worktree move` refuses
    loudly on a forgotten one, where `mv` would break a live registration, so the sentence gives
    `git -C <owner> worktree …`."""
    root = tmp_path / "boxes"
    door, wt, other = _taken("another-repositorys-live-tree", "fresh", tmp_path, root)
    real = worktree_box._working_trees
    monkeypatch.setattr(worktree_box, "_working_trees", lambda repo_path: None
                        if Path(repo_path).resolve() == other.resolve() else real(repo_path))
    said = str(_refusal(door))
    moves = _commands(said)
    git = f"git -C {shlex.quote(str(other.resolve()))} worktree "
    assert moves and all(c.startswith(git) for c in moves), said


@pytest.mark.parametrize("door_name", DOORS)
def test_a_symbolic_link_at_the_box_s_path_to_a_person_s_own_tree_of_this_repository_keeps_that_tree(
        tmp_path, root, door_name):
    """C2 for a link naming a linked working tree of THIS repository that a person made. Git lists
    the tree's real path and `_same_dir` resolves through the link, so `_clear_our_own` read it as
    the box's own and `worktree remove --force` deleted it with its uncommitted work (rc 0, 2.43.0);
    `worktree remove --force <link>`, on an unread list, does the same."""
    door = _door(door_name, tmp_path, root)
    mine = tmp_path / "my own tree"
    _git(door.repo, "worktree", "add", "-q", "-b", "mine", str(mine))
    (mine / "unsaved.txt").write_text("a person's uncommitted work\n")
    wt = root / BRANCH.replace("/", "-")
    root.mkdir(parents=True, exist_ok=True)
    os.symlink(mine, wt)
    said = str(_refusal(door))
    assert "a symbolic link" in said, said
    assert (mine / "unsaved.txt").read_text() == "a person's uncommitted work\n", said
    assert str(mine.resolve()) in _registered(door.repo)


def test_a_symbolic_link_at_the_box_s_path_to_a_person_s_own_tree_is_kept_when_the_list_cannot_be_read(
        tmp_path, root, monkeypatch):
    """The same, on an unread list: `worktree remove --force <link>` removes the tree it names."""
    door = _door("fresh", tmp_path, root)
    mine = tmp_path / "my own tree"
    _git(door.repo, "worktree", "add", "-q", "-b", "mine", str(mine))
    (mine / "unsaved.txt").write_text("a person's uncommitted work\n")
    wt = root / BRANCH.replace("/", "-")
    root.mkdir(parents=True, exist_ok=True)
    os.symlink(mine, wt)
    monkeypatch.setattr(worktree_box, "_working_trees", lambda repo_path: None)
    _refusal(door)
    assert (mine / "unsaved.txt").read_text() == "a person's uncommitted work\n"
