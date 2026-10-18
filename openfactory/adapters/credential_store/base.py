"""The port a credential store implements — two questions, and neither answer is ever logged.

`resolve(name)` is the secret, read NOW; `describe(name)` is where it is looked for and whether it
is there, for `openfactory doctor`, and never the value. `name` is the part of a reference after
`<kind>:` — a variable for `env`, a file for `file`, whatever an add-on's store calls an entry.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class CredentialRefused(Exception):  # noqa: N818 — a refusal is the store's answer, not a fault
    """The store HOLDS something under this name and will not hand it over, said in one sentence
    naming the name and the reason, never the value.

    ITS OWN ANSWER, DISTINCT FROM `None`. `None` means the store holds nothing there, and a
    deployment credential then falls back to the environment, which is how a deployment moves its
    secrets one at a time. A refusal is never a fallback: a file somebody else can rewrite, or one
    that resolves outside the directory, is a secret the deployment did not choose, and quietly
    taking the variable instead would hide that it is there."""


@runtime_checkable
class CredentialStore(Protocol):
    """Where stored secrets are read from. A row reads at each call and keeps nothing."""

    def resolve(self, name: str) -> str | None:
        """The secret stored under `name`, read now; None when the store holds nothing there.
        Raises `CredentialRefused` when it holds something it will not hand over."""
        ...

    def describe(self, name: str) -> str:
        """Where `name` is looked for and whether it is there, in a few words, never the value."""
        ...
