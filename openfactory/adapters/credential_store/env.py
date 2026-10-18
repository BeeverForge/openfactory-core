"""`env:<NAME>` — the process environment, exactly as every credential was read before the store.

The reference names a variable and the value is the variable's, unchanged: no stripping, no
decoding, because every reader that strips a value already did so on what the environment
handed it, and an upgrade must hand each of them the same bytes it read yesterday.
"""

from __future__ import annotations

import os


class EnvStore:
    """The variables of this process."""

    def resolve(self, name: str) -> str | None:
        return os.environ.get(name) or None

    def describe(self, name: str) -> str:
        state = "set" if os.environ.get(name) else "not set"
        return f"the environment variable `{name}` ({state})"
