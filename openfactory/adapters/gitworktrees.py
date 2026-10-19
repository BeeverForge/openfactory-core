"""Who has which branch out: `git worktree list --porcelain`, read once, for every caller.

ONE PARSER. The local forge reads it to know whether a merge may write a person's tree (#142,
#622), and the worktree box reads it to know whether the card's branch is out somewhere else
before it asks git to check it out (#623). Two copies of a parser drift, and this one encodes a
measured format.

THE PLAIN PORCELAIN, NEVER `-z`: `git worktree list --porcelain -z` does not exist on git 2.34.1
(`error: unknown switch 'z'`, exit 129, ubuntu:22.04), the oldest git a deployment meets in
practice. The plain porcelain is the same on 2.34.1 and 2.43.0: one block per working tree, blank
line between blocks, `worktree <path>` first, then `HEAD <sha>`, then `branch refs/heads/<b>` or
`detached` (or `bare` alone), and optionally `locked [reason]` and `prunable [reason]`. The FIRST
block is the repository's main working tree. A path with a space or a non-ASCII character is
printed as is, unquoted (git 2.43.0, measured 2026-10-17); the line is read to its end, never
split on spaces.

PORCELAIN, NOT GIT'S SENTENCES: what git says when it refuses a held branch changes with its
version (2.34.1 "is already checked out at", 2.43.0 "is already used by worktree at") and with the
locale, and the porcelain does not.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkingTree:
    """One block of the porcelain.

    `branch` is the short name (`openfactory/28`), or `""` for a detached HEAD or a bare
    repository. `main` is the repository's own working tree (the first block), which git cannot
    remove. `locked` was set by `git worktree lock`, which `git worktree remove` then refuses.

    NO `prunable` FIELD: git's word for a tree whose directory is gone is absent from a LOCKED one
    (listed `locked` only, 2.34.1 and 2.43.0), so whether a directory is there is asked of the
    filesystem, which answers both."""

    path: str
    branch: str
    main: bool
    locked: bool


def parse(porcelain: str) -> list[WorkingTree]:
    """Every working tree in `git worktree list --porcelain`'s output, main first."""
    trees: list[WorkingTree] = []
    path, branch, locked = "", "", False

    def close() -> None:
        if path:
            trees.append(WorkingTree(path=path, branch=branch, main=not trees, locked=locked))

    for line in (porcelain or "").splitlines():
        if line.startswith("worktree "):
            close()
            path, branch, locked = line[len("worktree "):], "", False
        elif line.startswith("branch refs/heads/"):
            branch = line[len("branch refs/heads/"):]
        elif line == "locked" or line.startswith("locked "):
            locked = True
    close()
    return trees


def holder(porcelain: str, branch: str) -> WorkingTree | None:
    """The first working tree that has `branch` checked out, or `None` when none has.

    `None` here means the porcelain was read and nobody holds it. A caller whose read FAILED must
    not call this with an empty string and conclude the same (engineering lessons §2)."""
    return holder_of(parse(porcelain), branch)


def holder_of(trees: list[WorkingTree], branch: str) -> WorkingTree | None:
    """`holder`, over working trees already parsed."""
    return next((t for t in trees if branch and t.branch == branch), None)


# ── a job's worktree, marked where git cleans up (#747) ─────────────────────────────────────────

#: The file the worktree box writes into the admin directory of the worktree it adds, and the
#: repository cache reads before it swaps a served tree. One name, one writer, one reader.
JOB_MARKER = "openfactory-job"

#: How long a marker holds. A job killed without `cleanup` leaves its directory, and git prunes no
#: tree whose directory is still there, so a marker that held for ever would freeze its key's
#: served tree for good. A day is longer than the longest job the default timeouts let run
#: (`sandbox.timeouts.ACTIVITY_CEILING`, 4 h 30 min), and short enough that a crash costs a day of
#: a stale cache, not a stale cache for ever.
JOB_MARKER_MAX_AGE = 24 * 60 * 60


@dataclass(frozen=True)
class JobMark:
    """One marked worktree that is still on disk: its path, as git wrote it in the admin
    directory's `gitdir` file without the trailing `/.git`, and its marker's age in seconds."""

    worktree: str
    age: float


@dataclass(frozen=True)
class JobMarks:
    """The marked worktrees of one repository that are still on disk. `live` hold its tree;
    `stale` are older than `JOB_MARKER_MAX_AGE` and were passed over, for the caller to say so."""

    live: list[JobMark]
    stale: list[JobMark]


def mark_as_job(worktree: Path) -> None:
    """Write `JOB_MARKER` into the admin directory of the linked worktree at `worktree`.

    THE WORKTREE'S OWN ADMIN DIRECTORY, asked of git: `git -C <wt> rev-parse --absolute-git-dir`
    answers `<repo>/.git/worktrees/<name>` for a linked worktree (git 2.43.0 and 2.34.1, measured
    2026-10-19; the option exists since 2.13). Git deletes that directory, foreign files included,
    on `git worktree remove` and on `git worktree prune` once the worktree's directory is gone,
    so nothing has to remember to delete the marker.

    The content is for a person reading the directory: the worktree and the UTC time it was
    written. The age the cache reads is the file's mtime. Raises `OSError` when git cannot answer
    or the file cannot be written; the caller says so."""
    done = subprocess.run(["git", "-C", str(worktree), "rev-parse", "--absolute-git-dir"],
                          capture_output=True, text=True, timeout=60, check=False)
    admin = (done.stdout or "").strip()
    if done.returncode != 0 or not admin:
        raise OSError(f"git could not name the admin directory of {worktree} "
                      f"(exit {done.returncode}): {(done.stderr or '').strip()[:200]}")
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (Path(admin) / JOB_MARKER).write_text(f"{worktree}\n{stamp}\n", encoding="utf-8")


def live_job_marks(repo: Path, *, now: float | None = None) -> JobMarks | None:
    """The marked worktrees of the repository at `repo` whose directories are still on disk, read
    from the filesystem alone — no git process, so asking costs no more than a directory listing.

    A MARK HOLDS ONLY WHILE ITS WORKTREE STANDS. Each `<repo>/.git/worktrees/<name>/` carries a
    `gitdir` file naming the worktree's `<wt>/.git` as git wrote it (absolute on git 2.34.1 and
    2.43.0; resolved against the admin directory when a newer git writes it relative). A marked
    admin directory whose `<wt>/.git` is gone — a job's directory deleted without `prune` — holds
    nothing. A marker older than `JOB_MARKER_MAX_AGE` is `stale`: listed, not live.

    `None` WHEN `.git/worktrees` EXISTS AND CANNOT BE READ, or a marked admin directory cannot be
    (engineering lessons §2): "could not see" is never "there is nothing", and the caller holds
    on `None`. A repository with no `.git/worktrees` has no marks: `JobMarks([], [])`."""
    admin_root = Path(repo) / ".git" / "worktrees"
    now = time.time() if now is None else now
    live: list[JobMark] = []
    stale: list[JobMark] = []
    try:
        try:
            with os.scandir(admin_root) as entries:
                admins = [Path(e.path) for e in entries if e.is_dir(follow_symlinks=False)]
        except (FileNotFoundError, NotADirectoryError):
            return JobMarks([], [])     # no worktree was ever added here, or `.git` is a file
        for admin in admins:
            try:
                marked = (admin / JOB_MARKER).stat()
            except FileNotFoundError:
                continue
            try:
                gitdir = (admin / "gitdir").read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                continue    # git is midway through removing it: nothing stands on the tree
            where = Path(os.path.normpath(admin / gitdir))
            if not where.exists():
                continue
            mark = JobMark(worktree=str(where.parent), age=max(0.0, now - marked.st_mtime))
            (live if mark.age < JOB_MARKER_MAX_AGE else stale).append(mark)
    except OSError:
        return None
    return JobMarks(live, stale)
