"""WorktreeSandbox — lightweight local/test sandbox via `git worktree`.

Isolates the code state only (no CPU/mem/network/secret isolation). Use it for fast
orchestrator tests and local debugging without Docker; real jobs run in
ContainerSandbox. Same Protocol, so the orchestrator is identical against both.

IT WORKS IN THE PERSON'S REPOSITORY, SO IT NEVER REMOVES, PRUNES OR FORCES A WORKTREE IT DID NOT
CREATE (#623). Its own is exactly `root / <branch>`, compared resolved. A card's branch out in any
other working tree (a review tree, or the person's own checkout) is refused before anything is
written, with `BranchHeldElsewhere`, read from `git worktree list --porcelain` and not from git's
sentence, which changes with git's version and the locale.

ITS OWN INCLUDES WHAT A RE-RUN FINDS LEFT OF IT (#746): its tree that git has forgotten is
recognised by the `.git` file naming this repository, its own `worktree add` that was interrupted
by git's lock bytes and the box's own mark, and both are removed; anything else at its path is
refused by name, and left as it is.

IT MARKS THE ONE WORKTREE IT ADDS AS A RUNNING JOB'S, AND NEVER ANOTHER (#747). On a project
registered by clone URL the repository is the cache's served checkout, which a sync would swap
out from under the job; the marker in that worktree's own admin directory is what holds the swap,
and git removes it with the worktree.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from openfactory.adapters import gitworktrees
from openfactory.adapters.sandbox.base import (
    BranchHeldElsewhere,
    OutputBuffer,
    SandboxAdapter,
    Workspace,
    run_and_stream,
)

log = logging.getLogger("openfactory.sandbox.worktree")

#: Where `stage_input` writes, under this box's worktree root — NEVER inside a workspace, because
#: the job's own `git add -A` would commit it into the ticket's pull request.
_INPUT_DIRNAME = ".inputs"

#: What git says when the remote ANSWERED and holds no such branch — the one failure that
#: legitimately degrades a resume to a fresh start. Every other failure (no credential, no
#: network, no such host) means we could not ask, and "could not ask" is never "it is not there".
_NO_SUCH_REF = ("couldn't find remote ref", "could not find remote ref")


def _remote_has_no_such_branch(fetch_output: str) -> bool:
    return any(marker in (fetch_output or "").lower() for marker in _NO_SUCH_REF)


def _is_this_repo(remote_url: str | None, repo_path) -> bool:
    """Whether the 'remote' is the repository we are already standing in (ADR-0049 D3).

    A PATH, NEVER A URL, is the only thing that can be: `https://…` and `git@…` name somewhere
    else by construction. Resolved on both sides, because the registry may hold a relative or
    symlinked path and git answers with the real one."""
    where = (remote_url or "").strip()
    if not where or "://" in where or where.startswith("git@"):
        return False
    try:
        return Path(where).resolve() == Path(repo_path).resolve()
    except OSError:
        return str(where) == str(repo_path)


def _resolves(repo_path, rev: str) -> bool:
    """Whether `rev` names a commit in `repo_path` — a branch, a remote-tracking ref, anything."""
    rc, _ = _run(["git", "-C", str(repo_path), "rev-parse", "--verify", "--quiet",
                  f"{rev}^{{commit}}"])
    return rc == 0


def no_such_base(base_branch: str, where: str) -> str:
    """The refusal for a base nobody holds (#354) — one sentence for both boxes."""
    return (f"{where} has no branch {base_branch!r}, which this job was asked to start from (the "
            f"card's `base_branch`, or the manifest's) — it does not start from another base "
            f"instead. Push that branch, or name a base {where} has.")


#: What `path_taken` can say is at the box's path, and what each is called in the sentence.
_TAKEN_BY = ("tree", "forgotten", "repository", "file", "symlink", "directory")


def path_taken(branch: str, path: str, *, repo: str, what: str, owner: str = "",
               locked: bool = False) -> str:
    """The refusal for the box's path taken by something not provably this repository's (#746):
    one sentence naming the card's branch, the path, what is there and whose, that it was left as
    it is, and the command that moves it, then resume.

    BUILT FROM WHAT THE BOX READ AT THE PATH, NEVER FROM GIT'S `already exists`, which names no
    owner and no remedy. English, like every hold note: notes are classified and hashed. Every
    path in a command is shell-quoted, so a root with a space pastes whole.

    `what`: `tree`, a working tree that the repository at `owner` lists there (moved with `git -C
    <owner> worktree move`, which keeps its registration; `locked` puts the unlock first, since
    `move` refuses a locked tree); `forgotten`, one that repository no longer lists (`worktree
    move` answers rc 128 `is not a working tree`, 2.43.0, measured 2026-10-18, so it is moved with
    `mv`); `repository`, a clone; `file`, `symlink`, or a `directory` that is none of these."""
    if what not in _TAKEN_BY:
        raise ValueError(f"unknown kind of thing at the box's path: {what!r}")
    where, mine = shlex.quote(path), "<a path of yours>"
    there = {
        "tree": f"a working tree of the repository at {owner}{', locked' if locked else ''}",
        "forgotten": f"a working tree that the repository at {owner} no longer lists",
        "repository": "a repository of its own",
        "file": "a file",
        "symlink": "a symbolic link",
        "directory": f"a directory that is not a working tree of {repo}",
    }[what]
    if what == "tree":
        git = f"git -C {shlex.quote(owner)} worktree"
        unlock = f"`{git} unlock {where}`, then " if locked else ""
        move = f"{unlock}`{git} move {where} {mine}`"
    else:
        move = f"`mv {where} {mine}`"
    return (f"{branch} cannot be checked out at {path}, the path this job's working tree takes, "
            f"because {there} is there; it was left as it is, and this job did not start. Move "
            f"it with {move}, then resume.")


def branch_held(branch: str, path: str, *, main: bool, locked: bool, repo: str = "",
                gone: bool = False, rebuilt: bool = False, ours: bool = False) -> str:
    """The refusal for a card's branch somebody else has out (#623): one sentence naming the
    branch, the working tree that holds it, and what frees it.

    BUILT FROM WHAT THE PORCELAIN SAID, NEVER FROM GIT'S PROSE, which changes with the version
    (2.34.1 "is already checked out at", 2.43.0 "is already used by worktree at") and the locale.
    English, like every hold note: notes are classified and hashed, and the channel line is the
    translated one.

    `main`: the holder is the repository's own checkout, which `git worktree remove` refuses
    (`is a main working tree`), so the remedy is to switch it away. `locked`: a locked tree is
    refused by `remove` (`cannot remove a locked working tree`, git 2.43.0), so the unlock comes
    first. Every path is shell-quoted where it is a command, so a path with a space pastes whole.

    EVERY COMMAND NAMES THE REPOSITORY (`git -C <repo>`), because a person pastes it from wherever
    their shell is, and `git worktree remove <path>` run outside the repository answers `is not a
    working tree` (review of 268c726: a test running the sentence's own command found it).

    WHAT THE PERSON IS TOLD TO KEEP MUST SURVIVE THE RESUME (review of 268c726). `rebuilt`: this
    door runs `branch -D` and builds the branch again, from the base or from the forge (every door
    but the local forge's continuing one), so a commit left on it would be on no branch afterwards.
    There the remedy is `git -C <tree> switch -c <a branch of yours>`, which keeps what is there on
    a branch of theirs and frees the card's branch in one command, in a locked tree too (2.34.1 and
    2.43.0, measured). `gone`: the tree's directory is not there (deleted by hand, or on a disk
    not mounted), and git still counts the branch as out there; `remove` frees it, after a mount
    (a removed registration orphans the tree when the disk comes back) and, on a rebuild door,
    after `git branch` keeps what was committed there. `ours`: the box's own tree from an earlier
    pass that it could not remove: locked, by a person or by a `git worktree add` interrupted
    before the box could mark it (#746), which the box cannot tell apart; the box leaves it as it
    is, and on a rebuild door it is moved off the box's path too, or `worktree add` meets it
    there."""
    where = shlex.quote(path)
    git = f"git -C {shlex.quote(repo)}" if repo else "git"
    unlock = f"`{git} worktree unlock {where}`, then " if locked else ""
    remove = f"{unlock}`{git} worktree remove {where}`"
    switch_new = f"`git -C {where} switch -c <a branch of yours>`"
    again = (f"This job builds {branch} again from the forge or the base, so a commit left on it "
             f"would not be in the job: ")
    once = "git lets a branch be checked out in only one place, so this job did not start"
    if gone:
        head = (f"{branch} is checked out in another working tree, at {path}, whose directory is "
                f"not there: git still counts the branch as out there, and {once}. If it is on a "
                f"disk that is not mounted, mount it and resume.")
        if rebuilt:
            # a commit made there is on the branch, which outlived the directory; `branch -D`
            # would drop it (review of 83973c2)
            return (f"{head} Otherwise keep any commit made there with "
                    f"`{git} branch <a branch of yours> {branch}`, then free it with {remove}, "
                    f"then resume.")
        return f"{head} Otherwise free it with {remove}, then resume."
    if main:
        head = (f"{branch} is checked out in your repository at {path}, and {once}, and nothing in "
                f"that checkout was touched.")
        if rebuilt:
            return (f"{head} {again}move that checkout with {switch_new}, which keeps what is "
                    f"there on a branch of yours and frees {branch}, then resume.")
        return (f"{head} Switch that checkout to another branch "
                f"(`git -C {where} switch <another branch>`), then resume.")
    # A LOCK ON THE BOX'S OWN TREE IS A PERSON'S OR AN INTERRUPTED `git worktree add`'s (#746):
    # git's add locks the tree `initializing` while it checks out, a person's `--reason
    # initializing` writes the same bytes, and a tree interrupted before this release carries no
    # mark of the box's, so the box cannot always tell which, and says so rather than naming
    # somebody.
    # (no backticks around git's verb: in these sentences a backticked `git …` is a command to
    # paste, and the #623 tests run every one of them as written)
    whose = (", the job's own from an earlier pass, which is locked, by a person or by a "
             "git worktree add that was interrupted, and the box could not tell which, so it "
             "was left as it is" if ours and locked else
             ", the job's own from an earlier pass, which could not be removed, so it was left "
             "as it is" if ours else "")
    head = (f"{branch} is checked out in another working tree, at {path}{whose}, and {once}, and "
            f"nothing in that tree was touched.")
    if rebuilt and ours:
        # the tree still stands at the box's own path after `switch -c`, and `worktree add` there
        # fails with git's `already exists` (review of 83973c2): the path is freed too
        return (f"{head} {again}free it with {switch_new}, then {unlock}"
                f"`{git} worktree move {where} <a path of yours>`, which keeps what is there on a "
                f"branch and in a directory of yours, then resume.")
    if rebuilt:
        return (f"{head} {again}free it with {switch_new}, which keeps what is there on a branch "
                f"of yours, then resume. With nothing there to keep, {remove} frees it too.")
    return (f"{head} Free it with {remove} (commit or stash anything there first), or switch "
            f"that checkout to another branch, then resume.")


def _branch_exists(repo_path, branch: str) -> bool:
    rc, _ = _run(["git", "-C", str(repo_path), "rev-parse", "--verify", "--quiet",
                  f"refs/heads/{branch}"])
    return rc == 0


def _same_dir(a, b) -> bool:
    """Whether two paths name the same directory: resolved on both sides, because git lists the
    real path and the box's root may be relative or reached through a symlink.

    A path that cannot be resolved is compared as written. On a symlink loop, `resolve()` raises
    `RuntimeError` on 3.12 (3.12.3, and 3.12.15 in the worker image), while 3.13.16 and 3.14.8
    return the path unchanged (non-strict; measured 2026-10-20). Either way a loop is not the box's
    own tree, and the caller goes on to ask about it rather than stopping the job."""
    try:
        return Path(a).resolve() == Path(b).resolve()
    except (OSError, RuntimeError):  # 3.12's resolve() raises RuntimeError on a symlink loop
        return str(a) == str(b)


def _working_trees(repo_path) -> list[gitworktrees.WorkingTree] | None:
    """The repository's working trees, or `None` when git could not be asked — which is NOT "there
    are none" (engineering lessons §2)."""
    rc, out = _run(["git", "-C", str(repo_path), "worktree", "list", "--porcelain"])
    if rc != 0:
        log.debug("could not read the working trees of %s: %s", repo_path, out.strip())
        return None
    return gitworktrees.parse(out)


def _common_dir(repo_path) -> Path | None:
    """The repository's common git directory, resolved, or `None` when git could not be asked.

    `--git-common-dir` answers RELATIVE to `repo_path` (`.git`) in the main checkout and absolute
    in a linked one, so it is joined to `repo_path`, never to the process's cwd. Never
    `--path-format=absolute`: that is git 2.31+, above CONTRIBUTING's 2.28 floor."""
    rc, out = _run(["git", "-C", str(repo_path), "rev-parse", "--git-common-dir"])
    if rc != 0 or not out.strip():
        log.debug("could not read the common git directory of %s: %s", repo_path, out.strip())
        return None
    try:
        return (Path(repo_path) / out.strip()).resolve()
    except OSError:
        return None


def _gitdir_named_by(wt) -> Path | None:
    """The directory a linked working tree's `.git` FILE names, resolved, or `None` when `wt` or
    its `.git` is a symlink, `.git` is not a regular file (a clone's `.git` is a directory), it
    cannot be read, its first line is not `gitdir: <path>`, or that path cannot be resolved (a
    symlink loop in it: `RuntimeError` on 3.12.3, while 3.13.16 and 3.14.8 return it unchanged,
    measured 2026-10-20).

    A RELATIVE gitdir IS RELATIVE TO THE TREE: git 2.48+ under `worktree.useRelativePaths` writes
    `gitdir: ../../repo/.git/worktrees/x` (2.49.1, alpine:3.22, measured 2026-10-18). `wt / target`
    lets an absolute value win, which is exactly the meaning here (engineering lessons §12)."""
    wt = Path(wt)
    try:
        dotgit = wt / ".git"
        if wt.is_symlink() or dotgit.is_symlink() or not dotgit.is_file():
            return None
        with open(dotgit, "rb") as fh:
            first = fh.readline(4096)
    except OSError:
        return None
    line = os.fsdecode(first).rstrip("\r\n")
    if not line.startswith("gitdir:"):
        return None
    target = line[len("gitdir:"):].strip()
    if not target:
        return None
    try:
        return (wt / target).resolve()
    except (OSError, RuntimeError):  # 3.12's resolve() raises RuntimeError on a loop in it
        return None


def _admin_dir_of(repo_path, wt) -> Path | None:
    """The admin directory under THIS repository's `<common>/worktrees/` that `wt/.git` names, or
    `None` when it names none (another repository's, nothing, or unreadable). Whether that admin
    directory still exists is not asked: git removes it when it forgets a tree."""
    named = _gitdir_named_by(wt)
    if named is None:
        return None
    common = _common_dir(repo_path)
    if common is None:
        return None
    return named if _same_dir(named.parent, common / "worktrees") else None


def _a_tree_this_repository_forgot(repo_path, wt, trees) -> bool:
    """Whether `wt` is a working tree of THIS repository that git has forgotten (#746): the list
    was read, it does not list `wt`, and `wt/.git` names this repository's `<common>/worktrees/`.

    What git leaves when it forgets a tree (pruned while its directory was away, the admin
    directory lost, or the repository cache republishing a snapshot with no `.git/worktrees/`),
    measured on 2.34.1 and 2.43.0: `<wt>/.git` still names `<common>/worktrees/<name>`, `worktree
    remove --force <wt>` answers rc 128 `is not a working tree`, and `worktree add` over it rc 128
    `already exists`. `trees` is `None` when the list could not be read, and then nothing is
    "forgotten" (engineering lessons §2). The admin directory is not required to be gone: a name
    git reused for another path still leaves `wt` an orphan, and the list is the evidence."""
    if trees is None:
        return False
    if any(_same_dir(tree.path, wt) for tree in trees):
        return False
    return _admin_dir_of(repo_path, wt) is not None


def _where(wt: Path) -> Path:
    """`wt` with its parent resolved and its own name kept, so a symlink AT `wt` is named (and
    moved) itself, not its target."""
    try:
        return wt.parent.resolve() / wt.name
    except OSError:
        return wt


def _what_is_at(wt: Path) -> tuple[str, str, bool] | None:
    """What takes the box's path, as `(what, owner, locked)` for `path_taken`, or `None` when the
    path is free: missing, or an EMPTY directory, which git accepts as the add's path (rc 0,
    2.34.1 and 2.43.0). `None` also when the path cannot be looked at: then git judges, as for
    `_holder`. Asked only after `_clear_our_own` removed what was provably the box's own."""
    try:
        if wt.is_symlink():
            return "symlink", "", False
        if not wt.exists():
            return None
        if not wt.is_dir():
            return "file", "", False
        with os.scandir(wt) as entries:
            if next(entries, None) is None:
                return None
        dotgit = wt / ".git"
        if dotgit.is_dir() and not dotgit.is_symlink():
            return "repository", "", False
    except OSError:
        return None
    named = _gitdir_named_by(wt)
    if named is None or named.parent.name != "worktrees":
        return "directory", "", False
    common = named.parent.parent
    try:
        if not common.is_dir():  # a `.git` file naming no repository
            return "directory", "", False
    except OSError:
        return "directory", "", False
    owner = common.parent if common.name == ".git" else common
    listed = _working_trees(owner)
    if listed is None:
        # could not ask the owner: `worktree move` refuses loudly where `mv` would break a live
        # registration
        return "tree", str(owner), False
    tree = next((t for t in listed if not t.main and _same_dir(t.path, wt)), None)
    if tree is None:
        return "forgotten", str(owner), False
    return "tree", str(owner), tree.locked


def _add_mark(wt: Path) -> Path:
    """Where the box marks its own `worktree add` while it runs: beside `wt`, in the box's root."""
    return wt.parent / f".{wt.name}.adding"


def _mark_bytes(common: Path, wt: Path) -> bytes:
    """What the mark holds: the repository's common directory and the tree's path, resolved, one
    per line, so a mark names exactly one repository's add at exactly one path."""
    return os.fsencode(str(common)) + b"\n" + os.fsencode(str(_where(wt))) + b"\n"


def _write_mark(repo_path, wt: Path) -> Path | None:
    """Write the mark for this repository's add at `wt`, atomically, and answer it; `None` (said in
    the log) when it could not be written, and the add then runs unmarked, as before #746."""
    common = _common_dir(repo_path)
    if common is None:
        log.warning("could not read the common git directory of %s — its worktree add at %s "
                    "runs unmarked", repo_path, wt)
        return None
    mark = _add_mark(wt)
    # A MARK ALREADY THERE IS NOT THIS ADD'S TO TAKE: it is an earlier interrupted add's, of this
    # repository (left when the list could not be read, so `_clear_our_own` could not prove it) or
    # of another one's box in the shared root. Rewritten and unlinked when this add returned, the
    # tree it proves was then held for a person on the next rerun (measured on ee7ba35,
    # 2026-10-18). This add runs unmarked instead, and the mark goes with its own tree.
    try:
        if os.path.lexists(mark):
            log.warning("a mark of an earlier worktree add is at %s — left, and the add at %s "
                        "runs unmarked", mark, wt)
            return None
    except OSError:
        return None
    tmp = mark.with_name(f"{mark.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(_mark_bytes(common, wt))
        os.replace(tmp, mark)
    except OSError as exc:
        log.warning("could not mark the worktree add at %s (%s) — it runs unmarked", wt, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            log.debug("could not remove %s", tmp)
        return None
    return mark


def _unlink_mark(mark: Path | None) -> None:
    if mark is None:
        return
    try:
        mark.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("could not remove the mark %s (%s)", mark, exc)


def _in_gits_own_words() -> dict[str, str]:
    """The process environment with `LC_ALL=C` and no `LANGUAGE`: what the box's add runs under.

    THE LOCK GIT WRITES DURING THE CHECKOUT IS ITS TRANSLATED `_("initializing")`: on 2.39.5 with
    its catalogues `de_DE.UTF-8` writes `initialisiere\\n` and `es_ES.UTF-8` `inicializando\\n`;
    `LC_ALL=C` writes `initializing\\n` even with `LANG=de_DE.UTF-8` or `LANGUAGE=de` set (measured
    2026-10-18). There is no `-c` key for the reason, and `add --lock --reason` is git 2.33+, above
    CONTRIBUTING's 2.28 floor. `LANGUAGE` is dropped too, for the gettext builds that read it."""
    env = {k: v for k, v in os.environ.items() if k != "LANGUAGE"}
    env["LC_ALL"] = "C"
    return env


#: What git's `worktree add` writes to `<admin>/locked` while it checks out, under `LC_ALL=C`: its
#: `_("initializing")` and a newline, 13 bytes (2.34.1, 2.39.5, 2.43.0 and 2.47.3, measured). The
#: box's add runs under `_in_gits_own_words`, so its own lock is never a translation.
_GITS_OWN_LOCK = b"initializing\n"


def _a_mark_of(repo_path, wt: Path) -> bool:
    """Whether the mark at `_add_mark(wt)` is a regular file (not a symlink) whose bytes name
    exactly THIS repository's common directory and `wt`, as `_write_mark` writes them."""
    mark = _add_mark(wt)
    try:
        if mark.is_symlink() or not mark.is_file():
            return False
        held = mark.read_bytes()
    except OSError:
        return False
    common = _common_dir(repo_path)
    return common is not None and held == _mark_bytes(common, wt)


def _an_add_this_box_never_finished(repo_path, wt: Path,
                                    tree: gitworktrees.WorkingTree) -> bool:
    """Whether the locked tree git lists at `wt` is the box's own `worktree add`, interrupted
    (#746, option A): this repository's tree at `wt`, its `<admin>/locked` exactly git's own
    `initializing\\n`, and the box's mark naming this repository and `wt`. Read from the
    filesystem, never from the porcelain's `locked <reason>`, which is translated and, from 2.36,
    C-quoted. Anything that cannot be read answers False: not proven is a person's lock."""
    if tree.main or not tree.locked or not _same_dir(tree.path, wt):
        return False
    try:
        if wt.is_symlink():
            return False
    except OSError:
        return False
    admin = _admin_dir_of(repo_path, wt)
    if admin is None:
        return False
    try:
        fd = os.open(admin / "locked", os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as fh:
            locked = fh.read(len(_GITS_OWN_LOCK) + 1)
    except OSError:
        return False
    return locked == _GITS_OWN_LOCK and _a_mark_of(repo_path, wt)


def _say_what_was_not_removed(function, path, exc) -> None:
    """`shutil.rmtree`'s `onexc`: what could not be removed is logged, never ignored, so a refusal
    by name that follows does not read as the box having found the path taken by somebody."""
    log.warning("could not remove %s from the box's forgotten tree (%s)", path, exc)


def _holder(repo_path, branch: str) -> gitworktrees.WorkingTree | None:
    """The working tree that has `branch` out, or `None`.

    ASKED AFTER `_clear_our_own`, so the box's own tree is gone and whoever is listed is somebody
    else. (An exclusion of `wt` here was dead code: the mutation that dropped it survived.)

    `None` also when the list could not be read: then `worktree add` is the judge, and its refusal
    is passed on as before — never read as "free" and never a start from the base."""
    trees = _working_trees(repo_path)
    if trees is None:
        return None
    held = gitworktrees.holder_of(trees, branch)
    if held is None:
        log.debug("nobody has %s out in %s", branch, repo_path)
    return held


def _not_there(path: Path) -> bool:
    """True only when the lookup searched every directory above `path` and found nothing.

    `Path.exists()` cannot say that: under a directory the box cannot search it raised on 3.12 and
    answers False from 3.14 (#827). Not looked at is not "not there"."""
    try:
        os.stat(path)
    except (FileNotFoundError, NotADirectoryError):  # no such entry, or a parent is now a file
        return True
    except OSError:  # a parent the box cannot search, among others: could not tell
        return False
    return False


def _branch_held_elsewhere(branch: str, tree: gitworktrees.WorkingTree, *, repo_path,
                           rebuilt: bool, ours: Path) -> BranchHeldElsewhere:
    # asked of the filesystem, not of git's `prunable`, which a locked tree whose directory is gone
    # never carries (listed `locked` only, 2.34.1 and 2.43.0, measured)
    gone = not tree.main and _not_there(Path(tree.path))
    return BranchHeldElsewhere(
        branch_held(branch, tree.path, main=tree.main, locked=tree.locked, repo=str(repo_path),
                    gone=gone, rebuilt=rebuilt, ours=_same_dir(tree.path, ours)),
        branch=branch, path=tree.path, main=tree.main, locked=tree.locked)

# A job clones/pushes over git and talks to GitHub — it never needs AWS. But a Fargate
# task inherits the ECS task-role credentials (chiefly via
# AWS_CONTAINER_CREDENTIALS_RELATIVE_URI), and those leak into the agent and into the
# app/tests it runs: an app that reaches a cloud service at boot picks up the ambient
# role and fails with a permission error instead of booting offline — which once pushed
# an agent into an out-of-scope "fix" that weakened a prod safety contract and evaded the
# coverage gate. Strip them so the workload sees a clean, credential-less environment.
# (engineering.md #4 — creds mint-at-use, never ambient; #11 — stay in scope.)
_AWS_CRED_VARS = (
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_SECURITY_TOKEN",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AWS_ROLE_ARN",
    "AWS_PROFILE",
)

# The forge (GitHub) push credentials live in the task env so the FRAMEWORK can push the
# branch + open the PR — but the agent must never wield them. If the agent can read a bot
# token it can `git push`/`gh pr create` and bypass the pipeline's control of version
# control (which #232 did). The framework pushes via an explicit authenticated remote
# (forge.push_remote(), resolved from the host env), so stripping these from the *workload*
# env costs it nothing. (engineering.md #4 — creds mint-at-use, never ambient.)
# A DENIAL LIST NAMES EVERY SPELLING THE SECRET CAN SIT UNDER, AND "ONE NAME PER SECRET" IS A
# DIFFERENT CLAIM THAT MISLED THIS LIST. No adoption shim serves a second spelling of a name any
# more (the retired prefix left on 2026-08-25) — but `credentials.py` still serves ONE bot
# credential under THREE names, by fallback rather than by alias: `forge_token()` reads
# OPENFACTORY_FORGE_TOKEN then OPENFACTORY_BOT_TOKEN, `tracker_token()` reads
# OPENFACTORY_TRACKER_TOKEN then the same OPENFACTORY_BOT_TOKEN. This list carried two of the
# three, so a deployment that filled the tracker override handed the agent that credential under
# the one name no scrub removed — and on a personal GitHub account that override is the classic
# PAT `docs/setup/github.md` scopes `repo` + `project`, which pushes (measured 2026-08-26).
# The rule is the FALLBACK CHAIN, not the prefix: a name any reader serves for a listed secret is
# listed with it. Held by `tests/test_the_environment_carries_the_products_name.py`, which derives
# the chains from `credentials.py` rather than repeating them here.
_FORGE_CRED_VARS = (
    "OPENFACTORY_FORGE_TOKEN",
    "OPENFACTORY_BOT_TOKEN",
    "OPENFACTORY_TRACKER_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "OPENFACTORY_GH_APP_KEY",
    "OPENFACTORY_GH_APP_KEY_CONTENT",
    "OPENFACTORY_GH_APP_ID",
    "OPENFACTORY_GH_APP_INSTALLATION_ID",
    # THE TOKEN A WORKER MINTED FROM THE MACHINE'S OWN IDENTITY, as a remote box receives it
    # (`credentials.BOX_TOKEN_ENV`, #373). The framework in the box pushes and opens the PR with
    # it; the agent in the box must not, for the reason every name above is here.
    "OPENFACTORY_BOX_TRACKER_TOKEN",
    "OPENFACTORY_BOX_FORGE_TOKEN",
)

# The Claude token POOL — every failover token — is read by the agent ADAPTER in the
# framework's OWN process (claude_code.py picks the active one and delivers it to the CLI
# separately via CLAUDE_CODE_OAUTH_TOKEN/ANTHROPIC_API_KEY). The workload subprocess must
# never see the whole pool: a compromised agent, or the project's own app/tests booting
# inside the sandbox, could read `OPENFACTORY_AGENT_TOKENS` and exfiltrate EVERY token at once.
# Stripping it costs the CLI nothing (its active token still arrives via the auth var).
# (engineering.md #4 — creds mint-at-use, never ambient; the pool is the crown jewels.)
_AGENT_CRED_VARS = ("OPENFACTORY_AGENT_TOKENS",)

# The key the panel signs a card preview's entry tokens with (ADR-0050). Only the panel needs it;
# a workload holding it could mint its own way into any preview on the deployment. Stripped for
# the reason the token pool is: nothing the agent does needs it.
#
# …and the key a human gate's answer is sealed with (`gate_seal`). A workload holding it could seal
# its own production approval or merge — the exact bypass the seal exists to close.
#
# …and the board's credentials (#562), new, and stripped from the day they exist: a workload
# holding one could act on the board as whoever it names. (The panel's and the product's own still
# reach a worktree workload, as SECURITY.md's measured table says.)
_PANEL_SECRET_VARS = ("OPENFACTORY_PREVIEW_SECRET", "OPENFACTORY_GATE_SECRET",
                      "OPENFACTORY_BOARD_TOKEN", "OPENFACTORY_BOARD_TOKENS")


def _scrubbed_env(keep: tuple[str, ...] = ()) -> dict[str, str]:
    """The process env minus ambient AWS credentials, forge push tokens, and the Claude
    token pool — so the sandboxed workload cannot reach cloud services with the task's
    identity (boots offline as designed), nor push/PR with the bot's GitHub credentials
    (version control is the pipeline's job, not the agent's), nor read the whole failover
    token pool (only the framework picks the active token, delivered to the CLI directly).

    `keep` IS THE PROJECT'S `box.env`, AND IT EXISTS BECAUSE THE SCRUB HAD A SECOND EFFECT NOBODY
    HAD LOOKED AT. When the harness authenticates through the client's own cloud — Bedrock — the
    variables it needs to reach the MODEL are the same ones stripped here to keep the agent away
    from our INFRASTRUCTURE. The container box already solved this: `box.env` names what passes
    through. The worktree had no such seam, and every judging role runs in a worktree — the sizer,
    the tech-lead's chat and diagnosis, the whole product module. So on a Bedrock deployment the
    executor and reviewer would work (they run in the box) while the tech-lead answered "could not
    answer" to every question and the size gate silently degraded. Nothing would have said why.

    The security property is UNCHANGED for anyone who declares nothing, and it is narrower than it
    looks even for those who do: what the operator names should be a credential scoped to invoking
    a model and nothing else, never the deployment's own task role. Naming it is an explicit,
    per-project decision made by whoever runs the factory — the same contract `box.env` already
    documents — rather than the blanket ambient identity this function exists to remove.
    """
    env = dict(os.environ)
    kept = {v for v in keep if v}
    for var in _AWS_CRED_VARS + _FORGE_CRED_VARS + _AGENT_CRED_VARS:
        if var not in kept:
            env.pop(var, None)
    # never kept, whatever `box.env` says: no harness authenticates with the preview key
    for var in _PANEL_SECRET_VARS:
        env.pop(var, None)
    return env


def _redact(text: str) -> str:
    """Strip any embedded credential from an authenticated URL before logging."""
    return re.sub(r"(https://)[^@/\s]+@", r"\1***@", text)


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 120,
         env: Mapping[str, str] | None = None) -> tuple[int, str]:
    # `env=None` inherits the process environment, as every caller but the box's own add does
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


class WorktreeSandbox(SandboxAdapter):
    def __init__(self, *, root: Path | str, extra_env: tuple[str, ...] = ()) -> None:
        # where worktrees are created, and where `stage_input` stages a prompt beside them.
        # THE BOX OWNS ITS TYPE (#380). It kept whatever it was handed, and most judging callers
        # hand it a `str` (a `TemporaryDirectory()`, a room, a checkout — all through
        # `judging_worktree`). Nothing on that path used it as a path until `stage_input` (#349)
        # divided it, and every product, tech-lead, sizer and extraction turn died on a TypeError
        # before the harness started. Normalised here, once, rather than at each call site.
        self.root = Path(root)
        #: `box.env` — the NAMES the project declares its harness needs (see `_scrubbed_env`).
        #: Validated like the container's, because the two must not disagree about what a "name"
        #: is: a project that works in the box and is rejected here would be the worse failure.
        bad = [v for v in extra_env if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v or "")]
        if bad:
            raise ValueError(
                f"box.env entries must be environment variable NAMES, got {bad!r}")
        self.extra_env = tuple(extra_env)
        self._repo_root: Path | None = None
        #: What `stage_input` wrote for THIS box, so `cleanup` can remove it. Per instance rather
        #: than per directory: a deployment may raise `OPENFACTORY_MAX_CONCURRENT_JOBS`, and
        #: sweeping the whole directory would delete another job's prompt mid-pass.
        self._staged: list[Path] = []
        #: What the command currently running has written — the buffer `tail()` reads (C-39).
        self._output = OutputBuffer()

    def guidelines_path(self, host_dir: Path) -> str | None:
        """Where the operator's guidelines directory is readable FROM INSIDE THIS BOX (#318).

        THE BOX ANSWERS BECAUSE ONLY THE BOX KNOWS — the same seam as `harness_path`, and it
        exists for the same reason: the index tells the agent to open a document on demand, and
        an entry it cannot open is worse than no entry at all (review of #328). Here the box is
        the host, so the host path IS the in-box path; a container answers with its mount.

        OPTIONAL BY DESIGN. Callers ask through `getattr`, so a box from outside this tree that
        has never heard of the operator tier says nothing rather than failing a contract check —
        and the caller then indexes nothing instead of advertising a path that resolves nowhere.
        """
        try:
            return str(Path(host_dir).resolve())
        except OSError:
            return None

    def prepare(
        self, *, repo_path: Path, base_branch: str, branch: str, checkout_existing: bool = False,
        remote_url: str | None = None,
    ) -> Workspace:
        self._repo_root = repo_path
        self.root.mkdir(parents=True, exist_ok=True)
        wt = self.root / branch.replace("/", "-")
        # Re-running the same ticket must start clean, so the box's OWN worktree of this branch
        # goes first — and only that one. "Ours" is exactly `wt`, compared resolved: every other
        # `worktree add` in the package is `--detach`, so this is the only platform worktree that
        # holds a card's branch. It used to be a blanket `git worktree prune`, which drops EVERY
        # registration whose directory is missing at that moment, a person's worktree on an
        # unmounted disk included — the rule the local forge's scratch rebase already wrote down
        # (`LocalForge._rebase_in_a_scratch_tree`, "NEVER `worktree prune`"). `remove --force`
        # takes our registration whether or not its directory is still there (rc 0 on a missing
        # directory, git 2.43.0, measured 2026-10-17). Ours is also the tree git has FORGOTTEN at
        # `wt` (the repository cache's republish forgets every one) and the tree our own add left
        # locked when it was interrupted, each removed only on proof (#746, `_clear_our_own`);
        # anything else at `wt` is refused by name below, before anything is written.
        trees = self._clear_our_own(repo_path, wt)
        # DECIDE BEFORE YOU WRITE (engineering lessons §12). A card's branch somebody else has
        # out — a review tree, or their own checkout — cannot be checked out here, and git says so
        # only at `worktree add`: after `branch -D` was tried, and after the fetch below wrote
        # `refs/remotes/origin/<branch>` into their clone. Asked first, of the porcelain rather
        # than of git's sentence, which changes with git's version and the locale (#623).
        # Which door this is decides what the refusal tells the person to keep: only the local
        # forge's continuing door keeps the branch (`keep` below), every other one builds it again.
        rebuilt = not (checkout_existing and _is_this_repo(remote_url, repo_path))
        held = _holder(repo_path, branch)
        if held is not None:
            raise _branch_held_elsewhere(branch, held, repo_path=repo_path, rebuilt=rebuilt,
                                         ours=wt)
        # THE PATH ITSELF MAY BE TAKEN (#746), and git says so only at `worktree add`, with rc 128
        # `fatal: '<wt>' already exists` (2.34.1 and 2.43.0): after `branch -D` below, after `add
        # -b` made the branch again at the base (2.43.0, measured 2026-10-18: the job's work was
        # replaced by `main`), and after a hosted resume's fetch wrote `refs/remotes/origin/<b>`.
        # Decided here, before any of that (engineering lessons §12). Only when the list was read:
        # unread, `_clear_our_own` could not tell what is ours, and git judges as before.
        taken = _what_is_at(wt) if trees is not None else None
        if taken is not None:
            what, owner, locked = taken
            raise RuntimeError(path_taken(branch, str(_where(wt)), repo=str(repo_path),
                                          what=what, owner=owner, locked=locked))
        # WHEN THE REMOTE IS THIS REPOSITORY, THE BRANCH IS THE WORK (ADR-0049 D3). On a forge that
        # hosts a copy, deleting the local branch is free: the resume fetches it back from the
        # remote. Here `remote_url` IS `repo_path`, so the delete below removes the only copy — and
        # the fetch that follows then answers "couldn't find remote ref", which `_NO_SUCH_REF`
        # reads as *the branch is gone, start fresh*.
        #
        # MEASURED, NOT REASONED: driving a publish and then a resume against a local repository
        # dropped the agent's implemented work and logged `OPENFACTORY_BRANCH_GONE` about a branch
        # the same repository was holding. The runner then force-pushes the fresh start over the
        # open pull request, which is the exact destruction the paragraph below was written to stop
        # — arriving through the one door it did not cover.
        keep = checkout_existing and _is_this_repo(remote_url, repo_path)
        if not keep:
            _run(["git", "-C", str(repo_path), "branch", "-D", branch])
        # A CI-repair / C2 resume works on the ALREADY-PUSHED branch (ADR-0004/0012), so start
        # the worktree from the remote branch's tip; a normal job starts fresh off base. If the
        # remote branch is GONE (deleted by a human, cleanup automation, or a preserve that
        # never landed) we FALL BACK to base instead of raising — a lost branch must degrade a
        # resume to a fresh start, never brick it into a crash-park (audit HIGH).
        #
        # BUT ONLY WHEN THE REMOTE ACTUALLY ANSWERED. A fetch that FAILED is not evidence of
        # absence, and this fallback used to accept both: on a private repository the tokenless
        # cache origin fails for want of a password, the branch reads as "gone", the resume
        # starts from base — and `publish_branch` then force-pushes that over the open PR,
        # DESTROYING the work it was sent to repair. Anything not positively identified as
        # "the remote has no such ref" raises, naming the real git error (credential scrubbed).
        # Same asymmetry the impediment classifier uses: unknown never degrades toward acting.
        start = base_branch
        if keep:
            # NOTHING IS FETCHED. The branch is in this repository already, and a fetch would write
            # `refs/remotes/origin/<branch>` into a repository that has no `origin` — inventing a
            # remote-tracking ref for a remote that does not exist.
            if not _branch_exists(repo_path, branch):
                log.warning("OPENFACTORY_BRANCH_GONE %s is not in %s — this resume starts fresh "
                            "from %s instead of continuing preserved work",
                            branch, repo_path, base_branch)
                keep = False
        elif checkout_existing:
            source = remote_url or "origin"
            rc, out = _run(["git", "-C", str(repo_path), "fetch", source,
                            f"+{branch}:refs/remotes/origin/{branch}"], timeout=180)
            if rc == 0:
                start = f"origin/{branch}"
            elif _remote_has_no_such_branch(out):
                log.warning("OPENFACTORY_BRANCH_GONE %s is not on the remote — this resume starts "
                            "fresh "
                            "from %s instead of continuing preserved work", branch, base_branch)
            else:
                raise RuntimeError(
                    f"could not ask the remote for {branch!r}, so this workspace cannot start "
                    f"from the open PR's branch: {_redact(out).strip()[:300]}")
        # THE BASE THE CARD NAMED MAY NOT BE IN THIS CLONE (#354). The worker's clone is synced to
        # the manifest's base, and a card's `base_branch` — stacked work, starting from a
        # predecessor still in review — was never fetched into it, so `worktree add` died on
        # "invalid reference" and the job never started from the base it was given. On a hosted
        # forge the base is read from the forge right after (`_read_the_forges_base`), so the
        # worktree only needs a commit to be cut from until then; with no forge (the repository IS
        # the remote) there is nowhere else to read it, and a base the repository lacks is refused
        # by name. NEVER ANOTHER BASE INSTEAD: running against a base the card did not name is the
        # defect.
        placeholder = False
        if not keep and start == base_branch and not _resolves(repo_path, base_branch):
            if not remote_url or _is_this_repo(remote_url, repo_path):
                raise RuntimeError(no_such_base(base_branch, str(repo_path)))
            start, placeholder = "HEAD", True
        # `-b` CREATES the branch and fails when it already exists, which is exactly the case
        # `keep` describes: the branch is here and holds the work, so the worktree checks it out
        # rather than making a second one over the base.
        add = (["worktree", "add", str(wt), branch] if keep
               else ["worktree", "add", "-b", branch, str(wt), start])
        # THE BOX MARKS ITS OWN ADD (#746, option A, chosen 2026-10-18). Git writes
        # `<admin>/locked` = `initializing\n` before the checkout and unlinks it after; a box killed
        # in between (SIGKILL of its process group, OOM, power loss, or `_run`'s timeout, which
        # kills the git parent only; its `reset --hard` child finishes on 2.43.0 and dies with the
        # closed pipes on 2.55.0, measured 2026-10-19) leaves the tree
        # registered and locked, byte for byte what a person's `git worktree lock --reason
        # initializing` leaves (2.34.1, 2.43.0 and 2.47.3, measured). The mark, written BEFORE the
        # add and removed only once `_run` returned, is what tells the box's own interrupted add
        # from a person's lock. Never in a `finally`: a `TimeoutExpired` is exactly the case the
        # mark must outlive.
        mark = _write_mark(repo_path, wt)
        rc, out = _run(["git", "-C", str(repo_path), *add], env=_in_gits_own_words())
        _unlink_mark(mark)
        if rc != 0:
            # Somebody may have checked the branch out between the read above and this add, or
            # the read may have failed; the porcelain is asked once more before git's sentence is
            # passed on.
            held = _holder(repo_path, branch)
            if held is not None:
                raise _branch_held_elsewhere(branch, held, repo_path=repo_path, rebuilt=rebuilt,
                                             ours=wt)
            raise RuntimeError(f"worktree add failed: {out}")
        # THIS WORKTREE IS A JOB'S, AND THE REPOSITORY CACHE MUST KNOW IT (#747). For a project
        # registered by clone URL `repo_path` is the cache's served checkout, so the job's admin
        # directory, branch and objects live in the served `.git`. A sync that found the base
        # moved swapped that tree into `.trash/<key>~<hex>`, and every git command in the job then
        # exited 128, `fatal: not a git repository: <root>/<key>/.git/worktrees/<name>` — the
        # push included (82500f9, git 2.43.0). The marker goes into THIS worktree's own admin
        # directory and nowhere else, right after the add, so the forge read below is covered and
        # its `worktree remove --force` on failure takes the marker with it.
        try:
            gitworktrees.mark_as_job(wt)
        except OSError as exc:
            # the job still starts: refusing it would cost the work the marker protects
            log.warning("could not mark %s as a running job's worktree (%s) — a repository "
                        "cache sync may swap the checkout it stands on while it runs",
                        wt, exc)
        base_commit = None
        if not keep and remote_url and not _is_this_repo(remote_url, repo_path):
            base_commit = self._read_the_forges_base(
                repo_path=repo_path, wt=wt, base_branch=base_branch, branch=branch,
                remote_url=remote_url, from_base=start == base_branch or placeholder)
        # host_path == path here: the worktree IS on the orchestrator's filesystem.
        return Workspace(path=wt, host_path=wt, branch=branch, base_branch=base_branch,
                         base_commit=base_commit)

    @staticmethod
    def _clear_our_own(repo_path: Path, wt: Path) -> list[gitworktrees.WorkingTree] | None:
        """Remove the box's own worktree at `wt`, registration and directory, and answer the
        working trees it read (`None`: the list could not be read), so `prepare` does not ask git
        for them again. Nothing else is removed, pruned or forced.

        ITS OWN IS WHAT THIS REPOSITORY LISTS AT `wt`, OR WHAT IT HAS FORGOTTEN THERE (#746). A
        tree git no longer lists stays on disk, and `worktree add` over it fails with `fatal:
        '<wt>' already exists` (rc 128, 2.34.1 and 2.43.0). The common cause is the repository
        cache: `RepoCache._publish` replaces the served checkout with a snapshot that has no
        `.git/worktrees/`, so every tree the box made from the old one is forgotten at once. Such a
        directory is removed only when `wt/.git` names THIS repository's `<common>/worktrees/` and
        the list, read, does not list `wt` (`_a_tree_this_repository_forgot`).

        ANYTHING ELSE AT `wt` IS LEFT ALONE. The default root is `.openfactory-worktrees` beside
        the served checkouts, shared by every project the process serves, so `wt` can be another
        repository's worktree of a branch with the same name, or a person's directory; `prepare`
        refuses by name over it rather than this deleting it. A job's branch can meet that case;
        a proof's no longer does, since each key proves on a branch of its own (`box_probes`),
        and a second proof of one key, which would take the first one's live tree for its own
        here, is refused before it reaches `prepare` (#745)."""
        if wt.is_symlink():
            # A LINK AT `wt` IS NEVER THE BOX'S OWN: git lists the real path and `_same_dir`
            # resolves through the link, and `worktree remove --force <link>` removes the linked
            # tree it names (rc 0, 2.43.0). `prepare` refuses it by name below.
            return _working_trees(repo_path)
        trees = _working_trees(repo_path)
        if trees is None:
            # Could not read the list: remove by our own path, whether or not its directory is
            # still there (rc 0 on a missing one). Git removes only a working tree of THIS
            # repository, so the path names nothing but ours. A forgotten tree is NOT removed
            # here: unread is not "not listed" (engineering lessons §2).
            _run(["git", "-C", str(repo_path), "worktree", "remove", "--force", str(wt)])
            return None
        kept = False
        for tree in trees:
            if not tree.main and _same_dir(tree.path, wt):
                if tree.locked:
                    # A LOCK IS A PERSON'S "KEEP THIS" (review of 268c726) UNLESS IT IS THE BOX'S
                    # OWN ADD, INTERRUPTED (#746). Git's own `worktree add` locks the tree while it
                    # checks out, so the platform does lock a tree, for that long; one killed then
                    # leaves the lock for good. It is the box's only when git's lock bytes are
                    # `initializing\n` AND the box's mark names this repository and `wt`: the bytes
                    # alone are also what `git worktree lock --reason initializing` writes. Any
                    # other lock is left as it is: one `--force` refuses it anyway (rc 128, 2.34.1
                    # and 2.43.0), and the `rmtree` below then deleted what they kept and the
                    # refusal said nothing was touched. `_holder` names it, unlock first.
                    if not _an_add_this_box_never_finished(repo_path, wt, tree):
                        log.warning("the box's own tree %s is locked — left as it is", tree.path)
                        kept = True
                        continue
                    log.warning("the box's own tree %s was left by its own worktree add, "
                                "interrupted (locked 'initializing', marked) — removed", wt)
                    rc, out = _run(["git", "-C", str(repo_path), "worktree", "unlock",
                                    tree.path])
                    if rc != 0:
                        log.warning("could not unlock the box's own tree %s (%s) — left as it "
                                    "is", tree.path, out.strip())
                        kept = True
                        continue
                _run(["git", "-C", str(repo_path), "worktree", "remove", "--force", tree.path])
                # what a failed remove left on disk is ours too: git listed it as this box's tree
                if wt.exists():
                    shutil.rmtree(wt, ignore_errors=True)
        if _a_tree_this_repository_forgot(repo_path, wt, trees):
            log.warning("the box's own tree %s is one git has forgotten (its .git file names "
                        "this repository, which no longer lists it) — removed", wt)
            shutil.rmtree(wt, onexc=_say_what_was_not_removed)
        # THE BOX'S OWN MARK GOES WITH ITS TREE, and only its own: the root is shared, and a mark
        # naming another repository is that repository's interrupted add, which only its own box
        # can prove (as measured 2026-10-18). Kept while a locked tree it may prove stays.
        if not kept and _a_mark_of(repo_path, wt):
            _unlink_mark(_add_mark(wt))
        return trees

    @staticmethod
    def _read_the_forges_base(*, repo_path: Path, wt: Path, base_branch: str, branch: str,
                              remote_url: str, from_base: bool) -> str | None:
        """Read `base_branch` from the FORGE, cut a new job from it, and answer the commit the
        workspace's diff is measured from (#168).

        THE LOCAL BASE IS WHATEVER WAS LAST FETCHED. On a hosted forge a project registered by
        path points at somebody's clone, and nothing here fetched it: measured on the first day
        of the deployment that reported this, the clone was already a merge behind the forge's
        `main`. Every new card was then planned, written, validated and reviewed against code that
        was no longer on the base, and its pull request opened against the real one — with
        conflicts, or with the merged change missing from everything the gates had proved.

        FETCHED INTO THIS WORKTREE'S OWN `FETCH_HEAD`, AND NO REF IS WRITTEN. `FETCH_HEAD` is a
        pseudo-ref, and git keeps one per linked worktree, so two jobs on the same repository
        cannot read each other's — where a shared `refs/remotes/origin/<base>` would have two
        concurrent fetches contend for its lock, and would move a tracking ref in a clone whose
        `origin` may not even be this forge. The person's `main`, their `origin/main` and their
        working tree stay where they were; the job's own branch is the only ref that moves. The
        credential in the URL does not stay behind for the agent to read: git writes `FETCH_HEAD`
        with the URL anonymised (git 2.43, an HTTP URL carrying `user:secret@` — the secret was in
        no file under `.git` afterwards).

        A NEW JOB IS RESET ONTO IT; A REOPENED PULL REQUEST IS NOT. A branch fetched back for a
        repair or a review pass is the work, and its diff is measured from where it left the base
        (`merge-base`), which is what the forge itself shows as the pull request's change — not
        what separates it from a base that has moved on since.

        A FETCH THAT FAILS STOPS THE JOB, NAMING WHY. Falling back to the local base is the
        defect itself, arriving silently. And nothing after `prepare` can succeed without the
        forge anyway — the job ends by pushing to it — so refusing here costs nothing the job
        could have kept, and it refuses before an agent has spent anything. The half-made worktree
        and branch are removed first, so a retry starts clean."""
        wp = str(wt)
        rc, out = _run(["git", "-C", wp, "fetch", remote_url, f"refs/heads/{base_branch}"],
                       timeout=180)
        read = rc == 0
        if read and from_base:
            rc, out = _run(["git", "-C", wp, "reset", "--hard", "--quiet", "FETCH_HEAD"])
        if rc != 0:
            _run(["git", "-C", str(repo_path), "worktree", "remove", "--force", wp])
            _run(["git", "-C", str(repo_path), "branch", "-D", branch])
            # THE STEP THAT FAILED IS THE ONE NAMED (review of #355). The fetch and the reset share
            # `rc`/`out`, and a reset that failed used to be read as the forge's answer and said as
            # "could not read … from the forge" — naming a fetch that had in fact succeeded.
            if read:
                raise RuntimeError(
                    f"read {base_branch!r} from the forge, but could not reset the new job's "
                    f"worktree onto it: {_redact(out).strip()[:300]}")
            if _remote_has_no_such_branch(out):
                raise RuntimeError(no_such_base(base_branch, "the forge"))
            raise RuntimeError(
                f"could not read {base_branch!r} from the forge, so this job would start from the "
                f"copy last fetched into {repo_path}, which may be behind the base its pull "
                f"request merges into. Check the forge's network and the credential this "
                f"deployment holds for it: {_redact(out).strip()[:300]}")
        rc, out = _run(["git", "-C", wp, "merge-base", "FETCH_HEAD", "HEAD"])
        # No common history is a branch that never came from this base — nothing to measure from,
        # and `base_branch` is then read as it always was.
        return out.strip() if rc == 0 else None

    def harness_path(self, name: str) -> str:
        """The bare name: this runs on the host, where the operator installed the harness and
        `PATH` is theirs to own. An absolute path here would break every local run."""
        return name

    def stage_input(self, *, workspace: Workspace, text: str) -> str | None:
        """Put `text` in a file this box can read, and return its path INSIDE the box (#326).

        WHY THE PORT DOES NOT GROW A METHOD FOR THIS. Every command reaches a box as one shell
        string, so a prompt reaches it as an argv element — and Linux caps a single argument at
        `MAX_ARG_STRLEN`, 128 KiB, whatever `ARG_MAX` says. A project whose documents are large
        therefore kills the invocation with `OSError: [Errno 7] Argument list too long` before the
        harness exists as a process. What a caller needs is a way to hand the box the TEXT and put
        only a short path on the command line (`cat <path> | harness …`).

        AN OPTIONAL CAPABILITY, REACHED BY `getattr`, exactly like `guidelines_path` above and
        `recognises_model` on the harness port. `SandboxAdapter` is `@runtime_checkable` and
        conformance lists every missing method as a finding, so a method added to the PROTOCOL is
        instantly required of the container box, a cloud box from an add-on package and every test
        double in this suite. Three agent passes died on that (#5, #8): the seam is only small
        while it stays off the port.

        OUTSIDE THE WORKSPACE, WHICH IS THE ONE THING THIS MUST NOT GET WRONG. A job commits with
        `git add -A`, so a file staged inside the checkout would be committed into the ticket's own
        pull request. It goes beside the worktrees instead, with `0600` on it, because the text is a
        prompt and a prompt carries the ticket — and `cleanup` removes what this box staged, which
        is a claim the code keeps rather than one this docstring makes (review of #349).

        `None` when the text cannot be staged; the caller then keeps whatever it does today."""
        try:
            root = self.root / _INPUT_DIRNAME
            root.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix="prompt-", suffix=".txt", dir=str(root))
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(name, 0o600)
            self._staged.append(Path(name))
            return name
        except (OSError, ValueError) as exc:
            # `ValueError` IS THE UNICODE HALF (review of #349). `fh.write` raises
            # `UnicodeEncodeError` — a `ValueError` — on a lone surrogate, which is what a
            # `surrogateescape`-decoded file becomes, so it is not an invented input. The docstring
            # promises None and the caller's own command line whenever the text cannot be staged;
            # catching only OSError kept that promise for a full disk and broke it for a string.
            log.warning("could not stage %d characters for the box (%s) — the caller keeps the "
                        "command line it has", len(text or ""), exc)
            return None

    def run(self, *, workspace: Workspace, command: str, timeout: int,
            on_output: Callable[[str], None] | None = None) -> tuple[int, str]:
        """`capture_output=True` MEANT THE OUTPUT DID NOT EXIST UNTIL THE PROCESS DIED (C-39).

        A timeout is still an OUTCOME, not a crash — letting `TimeoutExpired` propagate lost the
        reason, the job parked as a generic "errored" and the tech-lead diagnosed a crash that
        never happened — but the conversion now happens inside `run_and_stream`, in one place for
        both local boxes, with whatever the process had already written kept either way.

        `errors="replace"` is new and deliberate: `text=True` alone decodes strictly, so a single
        stray byte anywhere in four hours of agent output raised `UnicodeDecodeError` out of the
        sandbox — losing the entire pass to a mojibake character in a filename."""
        return run_and_stream(
            subprocess.Popen(
                command, shell=True, cwd=workspace.path,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace", bufsize=1,
                env=_scrubbed_env(self.extra_env),
            ),
            command=command, timeout=timeout, buffer=self._output, on_output=on_output,
        )

    def tail(self) -> list[str] | None:
        """Never None: a local subprocess's pipe is the shortest read there is, and this box says
        so as `streams=True` in the registry. The two answers are one claim — see the guard in
        `tests/test_the_box_transmits_while_it_runs.py` that checks the trait against the box."""
        return self._output.take()

    @staticmethod
    def _in_home(relative: str) -> Path | None:
        """`$HOME/relative`, or None when `relative` is not a plain relative path — the same rule
        the container box applies, because the two boxes must not disagree about what a caller is
        allowed to name (`..` would reach outside the harness's own state)."""
        rel = (relative or "").strip()
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            log.warning("refusing %r as a path inside HOME — it must be relative and must not "
                        "climb out of it", relative)
            return None
        return Path.home() / rel

    @staticmethod
    def _no_symlinks(directory: str, names: list[str]) -> list[str]:
        """Symlinks are dropped rather than followed. A harness home can hold links into the
        checkout or into the operator's own dotfiles, and restoring one into the NEXT box would be
        a persistence channel — the property the session snapshot has always had, kept here now
        that the copy happens through the box instead of through a tar."""
        return [n for n in names if (Path(directory) / n).is_symlink()]

    def export_home_dir(self, *, workspace: Workspace, relative: str, dest: Path) -> bool:
        """See the port. This box IS the host, so the transfer is a copy — but still a COPY, not a
        path handed out: the caller archives and stores what it is given, and a directory the
        harness is still writing to would otherwise change underneath it."""
        src = self._in_home(relative)
        if src is None or not src.is_dir():
            return False
        try:
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dest, symlinks=False, ignore=self._no_symlinks)
        except OSError as exc:
            log.warning("could not copy %s out of the worktree box (%s)", relative, exc)
            return False
        return dest.is_dir()

    def import_home_dir(self, *, workspace: Workspace, src: Path, relative: str) -> bool:
        """See the port. MERGES — on this box HOME belongs to the process, not to the job."""
        target = self._in_home(relative)
        if target is None or not src.is_dir():
            return False
        try:
            target.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, target, symlinks=False, ignore=self._no_symlinks,
                            dirs_exist_ok=True)
        except OSError as exc:
            log.warning("could not copy %s back into the worktree box (%s)", relative, exc)
            return False
        return target.is_dir()

    def diff_paths(self, *, workspace: Workspace) -> list[str] | None:
        rc, out = _run(
            ["git", "diff", "--name-only", f"{workspace.diff_base}..HEAD"], cwd=workspace.path
        )
        if rc != 0:
            # NONE, NOT `[]` (#251): a missing base ref, a pruned object, a timeout — see the
            # port. An empty list here says the change touched nothing, which three gates read.
            log.warning("could not read the diff of %s against %s (exit %s): %s",
                        workspace.branch, workspace.diff_base, rc, out.strip()[:200])
            return None
        return [ln for ln in out.splitlines() if ln.strip()]

    def publish_branch(self, *, workspace: Workspace, remote_url: str | None = None) -> None:
        # push to the authenticated bot remote if given, else the shared origin.
        # --force so a retry after a partial failure (branch already pushed, then the task
        # died) overwrites the bot's OWN dedicated openfactory/<id> branch instead of dead-locking
        # on a non-fast-forward forever. Safe: this branch is unique per job and only ever
        # the bot's; execution is serial (idempotency, engineering.md #3).
        target = remote_url or "origin"
        rc, out = _run(
            ["git", "-C", str(workspace.path), "push", "--force", target, workspace.branch]
        )
        if rc != 0:
            raise RuntimeError(f"push failed: {_redact(out)}")

    def rebase_onto_base(
        self, *, workspace: Workspace, base: str, remote_url: str | None = None
    ) -> str:
        # Framework-side (host creds), like publish_branch: fetch the latest base and, if the
        # branch is behind it, rebase onto it. Returns "up_to_date" (base already an ancestor
        # → nothing to do), "rebased" (moved onto newer base → caller must re-validate), or
        # "conflict" (textual conflict → aborted, tree left clean for a human).
        wp = str(workspace.path)
        target = remote_url or "origin"
        rc, out = _run(["git", "-C", wp, "fetch", target, base], timeout=180)
        if rc != 0:
            raise RuntimeError(f"fetch failed: {_redact(out)}")
        # already on top of the latest base? (fetched base is an ancestor of HEAD)
        rc, _ = _run(["git", "-C", wp, "merge-base", "--is-ancestor", "FETCH_HEAD", "HEAD"])
        if rc == 0:
            return "up_to_date"
        rc, out = _run(["git", "-C", wp, "rebase", "FETCH_HEAD"])
        if rc != 0:
            _run(["git", "-C", wp, "rebase", "--abort"])
            return "conflict"
        return "rebased"

    def cleanup(self, *, workspace: Workspace) -> None:
        # WHAT THIS BOX STAGED GOES WITH IT (review of #349). The docstring above said the prompt
        # goes "beside the worktrees — the directory this box already owns and already removes",
        # and nothing removed it: every staged prompt, each carrying its ticket, stayed on the
        # machine for good. A claim in a docstring that no code keeps is the thing this repository
        # hunts; the container's half needed nothing, because the file dies with the container.
        for staged in self._staged:
            try:
                staged.unlink(missing_ok=True)
            except OSError as exc:
                log.warning("could not remove the staged prompt %s (%s) — it carries a ticket, so "
                            "it is worth removing by hand", staged, exc)
        self._staged.clear()
        if self._repo_root:
            _run(
                ["git", "-C", str(self._repo_root), "worktree", "remove", "--force",
                 str(workspace.path)]
            )
        # A LOCK IS A PERSON'S "KEEP THIS" (#623, review of 83973c2): one `--force` refuses a
        # locked tree, and the `rmtree` deleted it anyway. Git's own add locks the tree while it
        # checks out (#746), but a workspace `cleanup` receives is one whose add returned, so a
        # lock here is still a person's; nothing here removes one.
        locked = self._repo_root is not None and any(
            t.locked and _same_dir(t.path, workspace.path)
            for t in (_working_trees(self._repo_root) or []))
        if locked:
            log.warning("the box's own tree %s is locked — left as it is", workspace.path)
        elif workspace.path.exists():
            shutil.rmtree(workspace.path, ignore_errors=True)
