"""Did a pass that must only read the workspace write to it? Asked of the box, before and after.

Kimi Code's planner is read-only by instruction only (`adapters/agent/base.py`,
`PLANNERS_READ_ONLY_BY_INSTRUCTION`), and it runs on the job's own workspace, the tree the executor
continues from and `JobRunner._commit` sweeps with `git add -A && git commit`. So the orchestrator
takes a `fingerprint` of that tree before the pass and after it, and `written` names what changed.

WHY NOT `git status --porcelain`. Measured on git 2.43.0 in a scratch worktree (2026-10-20): setup
can leave an untracked file, and a planner that appends to it leaves `?? u` reading the same before
and after; a planner that runs `git commit` leaves porcelain clean while HEAD moves and the commit
reaches the diff. The fingerprint is instead the tree `git add -A` would commit, which is exactly
what `_commit` sweeps (`.gitignore`, global excludes and `core.autocrlf` act on both alike), plus
`git rev-parse HEAD`. The tree hashes differed where porcelain did not, and `git diff --name-only`
between them named `u`.

THE REAL INDEX IS NEVER TOUCHED. `git add -A` writes into a COPY of the index, in the git dir (not
the working tree, which `_commit` would sweep, and not `/tmp`, so a client's image needs nothing
beyond `git`, `cp` and `rm`, ADR-0037 D1), removed in the same shell. Copying keeps the stat data,
so the add re-hashes only what changed. Measured 2026-10-20 on this repository's own tree (2196
tracked files), in a linked worktree, warm: 13-14 ms on git 2.43.0 (host), and in a clone inside
each image 14-16 ms on 2.47.3 (box image), 14 ms on 2.34.1, 30-34 ms on 2.28.0. With every file's
mtime bumped (stale stat data, a full re-hash) it took 228 ms on the host and 1059-1142 ms on the
box image's overlay filesystem, and every later run pays that again, because the real index is
never refreshed. A box that kills the shell at its timeout kills it before the `rm`; the copy then
sits in the admin dir of a workspace `cleanup` discards.

Every value is read from a hash or an exit code, never from git's prose, so a `pt_BR` locale changes
nothing that is parsed; git's prose is only carried, verbatim, to the person (`Unreadable`).
"""

from __future__ import annotations

import logging
import re
import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openfactory.adapters.sandbox.base import SandboxAdapter, Workspace

_log = logging.getLogger("openfactory.orchestrator.read_only_pass")

#: The POSIX `sh` command that fingerprints the workspace: the tree `git add -A` would commit,
#: written from a copy of the index, then HEAD. Prints two hash lines and exits 0, or exits non-zero
#: with git's own words. `rc` keeps the add/write-tree failure; a HEAD that cannot be read fails it
#: too. Every option is older than git 2.28, the oldest git CONTRIBUTING supports.
FINGERPRINT = (
    'idx="$(git rev-parse --git-path index)"; t="$idx.openfactory-plan-$$"; '
    'cp "$idx" "$t" 2>/dev/null; '
    'GIT_INDEX_FILE="$t" git add -A && GIT_INDEX_FILE="$t" git write-tree; rc=$?; '
    'rm -f "$t"; git rev-parse HEAD || rc=1; exit $rc'
)

#: How long the box may take to answer either question. The add re-hashes only what changed since
#: the index was written, so this is a wall for a stuck filesystem, not an estimate.
TIMEOUT_S = 300

#: How many written paths `written` names before it says "and N more" (a note a person reads).
SHOWN = 20

#: How much of git's output an `Unreadable` carries: its refusal is a few lines, and the tail is
#: where the `fatal:` line is.
_CARRIED = 2000

#: A git object name: SHA-1 (40) or SHA-256 (64) hex.
_HASH = re.compile(r"[0-9a-f]{40}([0-9a-f]{24})?")


@dataclass(frozen=True)
class Mark:
    """The workspace at one moment: the tree `git add -A` would commit, and HEAD."""

    tree: str
    head: str


@dataclass(frozen=True)
class Unreadable:
    """The box could not be asked: "could not see", which is never "nothing was written"
    (engineering lesson 2). `output` is git's own words, so a hold can name the cause (a client
    image without `safe.directory` for its mount answers "detected dubious ownership", exit 128)."""

    rc: int
    output: str


def fingerprint(sandbox: SandboxAdapter, ws: Workspace) -> Mark | Unreadable:
    """Run `FINGERPRINT` in `ws` through the box's own `run`, and read its two hashes.

    THE ANSWER IS A `Mark` OR AN `Unreadable`, AND ONLY A `Mark` MAY BE COMPARED. A non-zero exit,
    or output whose last two lines are not two hashes of one length, is `Unreadable`, carrying the
    exit code and git's output. It never reads as a clean workspace: a caller that cannot compare
    must stop, not proceed. Lines before the two hashes are allowed: the box merges stderr into the
    output, and `git add` warns there with exit 0 (measured on git 2.43.0 under
    `core.autocrlf=true`: one "LF will be replaced by CRLF" line per file, then the two hashes)."""
    rc, out = sandbox.run(workspace=ws, command=FINGERPRINT, timeout=TIMEOUT_S)
    lines = [line.strip() for line in (out or "").splitlines() if line.strip()]
    if rc == 0 and len(lines) >= 2:
        tree, head = lines[-2], lines[-1]
        if _HASH.fullmatch(tree) and _HASH.fullmatch(head) and len(tree) == len(head):
            return Mark(tree=tree, head=head)
    if rc == 0:
        # exit 0 without two hashes: the box answered something that is not git's fingerprint
        rc = -1
    words = out or ""
    if len(words) > _CARRIED:
        _log.warning("the workspace fingerprint answered %d characters with exit %d; the last %d "
                     "are carried", len(words), rc, _CARRIED)
        words = words[-_CARRIED:]
    return Unreadable(rc=rc, output=words)


def written(sandbox: SandboxAdapter, ws: Workspace, before: Mark, after: Mark) -> list[str]:
    """What changed in `ws` between two marks, as a person reads it: `[]` only when both are equal.

    A moved HEAD comes first, as one entry naming both commits, then the paths of the commits'
    diff and of the trees' diff, each once. Positive evidence is never lost: two trees that differ
    always give a non-empty list, even when git cannot name a path (its words are then the entry).
    At most `SHOWN` entries are named, then one "and N more"; hitting that bound is logged."""
    for value in (before.tree, before.head, after.tree, after.head):
        if not _HASH.fullmatch(value):
            raise ValueError(f"not a git object name: {value!r} (a Mark comes from fingerprint)")
    names: list[str] = []
    if before.head != after.head:
        names.append(f"a commit made during the pass (HEAD moved from {before.head[:12]} "
                     f"to {after.head[:12]})")
        names += _diff_names(sandbox, ws, before.head, after.head, "HEAD moved")
    if before.tree != after.tree:
        names += _diff_names(sandbox, ws, before.tree, after.tree, "the tree changed")
    seen: set[str] = set()
    unique = [n for n in names if not (n in seen or seen.add(n))]
    if len(unique) > SHOWN:
        _log.warning("the pass changed %d paths in %s; the first %d are named", len(unique),
                     ws.path, SHOWN)
        return [*unique[:SHOWN], f"and {len(unique) - SHOWN} more"]
    return unique


def _diff_names(sandbox: SandboxAdapter, ws: Workspace, a: str, b: str, what: str) -> list[str]:
    # `core.quotePath=false` so a non-ASCII name reads as itself in the note; `--no-renames` so a
    # rename names both paths (`diff.renames` defaults on since git 2.9 and would name only one).
    rc, out = sandbox.run(
        workspace=ws, timeout=TIMEOUT_S,
        command=(f"git -c core.quotePath=false diff --no-renames --name-only "
                 f"{shlex.quote(a)} {shlex.quote(b)}"),
    )
    paths = [line for line in (out or "").splitlines() if line.strip()] if rc == 0 else []
    if not paths:
        said = (out or "").strip()[-_CARRIED:] or f"exit {rc}, no output"
        return [f"{what}, and git named no path ({said})"]
    return paths
