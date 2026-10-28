"""The transports the core's remote-reaching git calls may use (#931).

A git call that reaches a remote (clone, fetch, ls-remote, push, remote set-url) reads which
transports it may use from the machine's git configuration. A machine that sets
`protocol.ext.allow=always` lets a remote named `ext::sh -c …` run a command on the host. The
pin puts `-c protocol.<name>.allow=…` before the subcommand, so the call allows https, ssh and
file and refuses the rest, whatever the machine says. File transport is allowed only for
user-initiated calls, not recursive submodule operations.

A `-c` overrides only the same key: `protocol.allow=never` alone loses to a machine's
`protocol.ext.allow=always`. So the pin sets the default and every known transport by name.

A `GIT_ALLOW_PROTOCOL` variable in the core's environment still overrides every one of these
settings; that gap is named in docs/operations.md.
"""

from __future__ import annotations

from collections.abc import Sequence

ALLOWED = ("https", "ssh")
REFUSED = ("ext", "fd", "http", "git", "ftp", "ftps")

PIN: tuple[str, ...] = (
    "-c", "protocol.allow=never",
    *(w for name in ALLOWED for w in ("-c", f"protocol.{name}.allow=always")),
    "-c", "protocol.file.allow=user",
    *(w for name in REFUSED for w in ("-c", f"protocol.{name}.allow=never")),
)


def pinned(args: Sequence[str]) -> list[str]:
    """`args` with the pin in front, for a runner that puts "git" before them itself."""
    return [*PIN, *args]


def argv(args: Sequence[str]) -> list[str]:
    """The whole command line: `git`, the pin, then `args`."""
    return ["git", *PIN, *args]


def subcommand(args: Sequence[str]) -> str | None:
    """The git subcommand of `args`, with or without a leading "git", past any `-c X` and
    `-C X` pairs; None when there is none."""
    words = list(args)
    i = 1 if words[:1] == ["git"] else 0
    while i < len(words) and words[i] in ("-c", "-C"):
        i += 2
    return words[i] if i < len(words) else None


def without_pin(text: str) -> str:
    """`text` with the pin taken out where it spells a command: as a Python list (what a
    `CalledProcessError` prints) or as a command line. A log line keeps only the first 120
    characters of an error, and the pin would fill them before the command a person reads."""
    listed = "".join(f"{w!r}, " for w in PIN)
    spoken = "".join(f"{w} " for w in PIN)
    return text.replace(listed, "").replace(spoken, "")
