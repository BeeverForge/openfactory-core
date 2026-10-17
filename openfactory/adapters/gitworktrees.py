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

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkingTree:
    """One block of the porcelain.

    `branch` is the short name (`openfactory/28`), or `""` for a detached HEAD or a bare
    repository. `main` is the repository's own working tree (the first block), which git cannot
    remove. `locked` was set by `git worktree lock`, which `git worktree remove` then refuses."""

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
