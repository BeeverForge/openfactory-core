"""A card body GitHub accepts is created whatever its bytes (#807).

GITHUB COUNTS CHARACTERS; THE KERNEL COUNTS BYTES. `GitHubIssuesTracker.create_ticket` passed the
body to `gh` as one argv element (`--body body`). Linux refuses one argv element longer than
`MAX_ARG_STRLEN` (131,072 bytes) with `E2BIG`, while GitHub's limit (`body_limit`) is 65,536
characters, so a body GitHub would accept failed to create once it was multi-byte. The failure is
not a refused `gh`: `subprocess.run` raises `OSError: [Errno 7] Argument list too long: 'gh'`
before `gh` starts (measured 2026-10-19, Python 3.12, Linux, gh 2.102.0), and `_gh` catches only
`FileNotFoundError`, so the create escaped as a raw `OSError`.

The issue measured `_child_body` at the 65,536-character limit (#624), which is the input a split
now produces, since a child carries its parent's other sections up to the tracker's limit:

    | text                | chars  | UTF-8 bytes |
    |---------------------|--------|-------------|
    | ASCII               | 65,502 | 65,502      |
    | accented Portuguese | 65,502 | 97,493      |
    | 3-byte CJK          | 65,502 | 193,462     |
    | 4-byte emoji        | 65,502 | 257,442     |

A 3-byte script crosses `MAX_ARG_STRLEN` at about 43,690 characters. The fix sends the body on
stdin with `--body-file -`, as `update_body` already did, and never in argv.

WHAT IS DRIVEN HERE IS THE PRODUCTION PATH: `create_ticket` → `_gh` → `subprocess.run`, with
`subprocess.run` replaced by a fake that refuses an argv element the way the kernel does. Local
`gh` shares the production App's rate limit and the suite has no `gh` login, so the fake never
spawns it. Both numbers are read from the values the code exports, never written here.
"""

from __future__ import annotations

import errno
import os
import subprocess
import time

import pytest

from openfactory.adapters.agent.base import MAX_ARG_STRLEN
from openfactory.adapters.tracker.github import GitHubIssuesTracker
from openfactory.adapters.tracker.parse import carried_sections
from openfactory.runtime.temporal import activities as acts

#: The character count of every row of the issue's table: `_child_body` at GitHub's limit.
TABLE_CHARS = 65_502

_CREATED = "https://github.com/o/r/issues/12\n"
_SECONDARY = "You have exceeded a secondary rate limit. Please wait a few minutes before you try again."


class KernelGH:
    """Stands in for `subprocess.run(["gh", ...])` as `execve` would see it, recording argv and
    stdin (`input=`) per call.

    The refusal is the kernel's own rule (`fs/exec.c::copy_strings`): an argument whose length,
    with its terminating NUL, exceeds `MAX_ARG_STRLEN` is refused with `E2BIG`, and
    `subprocess.run` raises it as `OSError: [Errno 7] Argument list too long: 'gh'` before `gh`
    exists. `issue create` answers with an issue URL, as `gh` prints it."""

    def __init__(self, *, rate_limited_creates: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.stdins: list[str | None] = []
        self._rate_limited = rate_limited_creates

    def __call__(self, argv, **kw):
        for arg in argv:
            if len(os.fsencode(arg)) + 1 > MAX_ARG_STRLEN:
                raise OSError(errno.E2BIG, os.strerror(errno.E2BIG), argv[0])
        self.calls.append(list(argv))
        self.stdins.append(kw.get("input"))
        if argv[1:3] == ["issue", "create"]:
            if self._rate_limited:
                self._rate_limited -= 1
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr=_SECONDARY)
            return subprocess.CompletedProcess(argv, 0, stdout=_CREATED, stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def creates(self) -> list[tuple[list[str], str | None]]:
        return [(argv, stdin) for argv, stdin in zip(self.calls, self.stdins, strict=True)
                if argv[1:3] == ["issue", "create"]]


def _install(monkeypatch, fake: KernelGH) -> KernelGH:
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


def _short(argv: list[str]) -> list[str]:
    return [a if len(a) <= 40 else f"<{len(a)} characters>" for a in argv]


def _assert_on_stdin_and_never_in_argv(argv: list[str], stdin: str | None, body: str) -> None:
    assert "--body" not in argv, _short(argv)
    assert "--body-file" in argv and argv[argv.index("--body-file") + 1] == "-", _short(argv)
    assert not any(body in arg for arg in argv), "the body is still an argv element"
    assert stdin == body, "the body did not reach gh on stdin"


def test_a_body_over_one_argv_element_in_bytes_and_within_githubs_limit_reaches_gh_on_stdin(
        monkeypatch):
    """The issue's criterion, in its words: "a create with a body over 131,072 UTF-8 bytes and
    under 65,536 characters reaches `gh` with the body on stdin, not in argv". On `main` the
    `--body` element is refused with `OSError [Errno 7]` and `create_ticket` lets it escape."""
    gh = _install(monkeypatch, KernelGH())
    body = "語" * 50_000
    assert len(body) < GitHubIssuesTracker.body_limit
    assert len(body.encode()) > MAX_ARG_STRLEN

    ref = GitHubIssuesTracker("o/r").create_ticket(title="t", body=body)

    assert ref == "#12"
    [(argv, stdin)] = gh.creates()
    _assert_on_stdin_and_never_in_argv(argv, stdin, body)


@pytest.mark.parametrize("char", ["a", "ã", "語", "😀"],
                         ids=["ascii", "accented", "cjk", "emoji"])
def test_every_script_at_githubs_limit_reaches_gh_on_stdin_and_never_in_argv(monkeypatch, char):
    """Each script of the issue's table, at the table's 65,502 characters. On `main` the 3- and
    4-byte rows fail with `OSError [Errno 7]`; the ASCII and accented rows still fit one argv
    element, so they fail the stdin assertion instead: the body went to argv, not to stdin."""
    gh = _install(monkeypatch, KernelGH())
    body = char * TABLE_CHARS
    assert len(body) <= GitHubIssuesTracker.body_limit

    ref = GitHubIssuesTracker("o/r").create_ticket(title="t", body=body)

    assert ref == "#12"
    [(argv, stdin)] = gh.creates()
    _assert_on_stdin_and_never_in_argv(argv, stdin, body)


def test_the_rate_limit_retry_sends_the_body_on_stdin_again(monkeypatch):
    """`_gh` retries a create GitHub refused for a secondary rate limit. The body must reach `gh`
    on stdin on the retry as well as on the first run: a retry with `--body-file -` and nothing on
    stdin would create an empty card. On `main` the first run raises `OSError [Errno 7]`."""
    gh = _install(monkeypatch, KernelGH(rate_limited_creates=1))
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    body = "語" * 50_000

    ref = GitHubIssuesTracker("o/r").create_ticket(title="t", body=body)

    assert ref == "#12"
    creates = gh.creates()
    assert len(creates) == 2, [argv[:3] for argv, _ in creates]
    for argv, stdin in creates:
        _assert_on_stdin_and_never_in_argv(argv, stdin, body)


def test_a_split_child_built_to_githubs_limit_in_a_three_byte_script_is_created(monkeypatch):
    """Why it matters (#624): a split child carries its parent's other sections up to the
    tracker's limit, so a parent with a long CJK `## Scope` yields a child within GitHub's
    characters and over one argv element's bytes. On `main` its create raises `OSError [Errno 7]`
    partway through the split."""
    gh = _install(monkeypatch, KernelGH())
    scope = "\n".join(["語" * 100] * 1_000)
    parent = (f"Filed from the field.\n\n## Objective\no\n\n## Scope\n{scope}\n\n"
              "## Acceptance criteria\n- c")
    child = {"title": "f", "objective": "o", "criteria": ["c"]}
    child_body = acts._child_body(child, "#79", 1, 2, carried=carried_sections(parent),
                                  limit=GitHubIssuesTracker.body_limit, parent_url="u", title="t")
    assert len(child_body) <= GitHubIssuesTracker.body_limit
    assert len(child_body.encode()) > MAX_ARG_STRLEN

    ref = GitHubIssuesTracker("o/r").create_ticket(title="t", body=child_body)

    assert ref == "#12"
    [(argv, stdin)] = gh.creates()
    _assert_on_stdin_and_never_in_argv(argv, stdin, child_body)
