"""Where a stored secret comes from — named by a reference, resolved where it is used (#742).

THE GAP THIS CLOSES. Every secret a deployment stored was an environment variable, read by the
module that used it: the per-axis tokens in `credentials._axis_credential`, the GitHub App key in
`app_private_key` (the one credential that could also come from a file, inside its own function),
the harness tokens in the harness row, the panel's and the engine's keys in their own modules.
Nothing abstracted where a stored secret comes FROM. A deployment whose secrets are mounted as
files, which is how container platforms deliver what cannot be keyless, had to copy each one into
a variable first, and an add-on had no way to read them from anywhere else.

A REFERENCE is `<kind>:<name>`: `env:JIRA_API_TOKEN` is a variable, `file:jira-token` a file in the
credential directory, and another kind is whatever an installed store reads. A BARE NAME, which is
every `token_env` written before this existed and every variable name the core reads, is a
DEPLOYMENT CREDENTIAL by that name (`stored`).

A DEPLOYMENT CREDENTIAL IS ASKED OF THE DECLARED STORE FIRST, THEN OF THE ENVIRONMENT.
`OPENFACTORY_CREDENTIAL_STORE` names the store. Unset, it is `env`, and that is exactly the
behaviour before this module: one lookup, the variable. Set to `file`, the credential `X` is the
file `X` in the credential directory when there is one and the variable `X` when there is not, so
an installation moves its secrets one at a time and a variable it has not moved keeps working. A
store that REFUSES what it holds (`CredentialRefused`) is never a fallback, and neither is an
unknown kind: a secret the deployment did not choose is not replaced by another one in silence.

NAMES AND REFERENCES, NEVER VALUES. What this module logs, and what `describe` and `source`
answer, say where a secret is and whether it is there. A value leaves only through `stored` and
`resolve`, to the caller that uses it, and nothing here keeps one.

THE AXIS. `credential_store.<kind>` in the `openfactory.adapters` entry-point group names a
zero-argument builder returning a `CredentialStore`. A built-in wins a collision and an unknown
kind refuses naming what is installed, as on every axis.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable

from openfactory import plugins
from openfactory.adapters.credential_store.base import CredentialRefused, CredentialStore

log = logging.getLogger("openfactory.credential_store")

#: The entry-point axis name: `credential_store.<kind>`.
AXIS = "credential_store"
ENV = "env"
FILE = "file"

#: Which store this deployment's own credentials are asked of before the environment. A selector,
#: not a secret: it names a kind.
STORE_VAR = "OPENFACTORY_CREDENTIAL_STORE"


def _env() -> CredentialStore:
    from openfactory.adapters.credential_store.env import EnvStore

    return EnvStore()


def _file() -> CredentialStore:
    from openfactory.adapters.credential_store.file import FileStore

    return FileStore()


#: kind → the builder of its store. Built at each use, so a store reads its own configuration (the
#: file store's directory) at the moment a credential is asked for, never at import.
STORES: dict[str, Callable[[], CredentialStore]] = {
    ENV: _env,
    FILE: _file,
}


def known() -> list[str]:
    """Every store kind this deployment can read from: shipped plus installed."""
    return plugins.known(AXIS, STORES)


def build_store(kind: str) -> CredentialStore:
    """The store for `kind`. Raises on a kind nobody installed, naming the ones that are."""
    key = (kind or "").strip().lower()
    builder = STORES.get(key) or plugins.builder(AXIS, key, builtin=STORES)
    if builder is None:
        raise ValueError(f"unknown credential store {key!r} — known: {', '.join(known())}"
                         f"{plugins.install_hint(AXIS, key)}")
    return builder()


def parse(reference: object) -> tuple[str, str]:
    """`(kind, name)` of a reference; the kind is `""` for a bare name. A variable name cannot hold
    a colon, so the first one is where the kind ends."""
    text = str(reference or "").strip()
    kind, sep, name = text.partition(":")
    if not sep:
        return "", text
    return kind.strip().lower(), name.strip()


def deployment_store() -> str:
    """The store this deployment's own credentials are asked of first (`STORE_VAR`), `env` unset."""
    return (os.environ.get(STORE_VAR) or "").strip().lower() or ENV


def _ask(kind: str, name: str) -> tuple[str, str | None, bool]:
    """`(reference, value, refused)` from the store `kind` for `name`. Never raises: an unknown kind
    and a store that refuses or fails are said, by reference, and answer nothing."""
    reference = f"{kind}:{name}"
    try:
        store = build_store(kind)
    except ValueError as exc:
        log.warning("the credential `%s` cannot be read: %s — nothing is used in its place",
                    reference, exc)
        return reference, None, True
    try:
        value = store.resolve(name)
    except CredentialRefused as exc:
        log.warning("the credential `%s` is refused: %s — nothing is used in its place",
                    reference, exc)
        return reference, None, True
    except Exception:  # noqa: BLE001 — an add-on's store may not take a credential path down
        log.warning("the %s credential store failed reading `%s`; it is treated as a refusal and "
                    "nothing is used in its place", kind, name, exc_info=True)
        return reference, None, True
    return reference, (value or None), False


def _declared(name: str) -> tuple[str, str | None] | None:
    """What the declared store answers for `name`: `(reference, value)` when it holds it,
    `("", None)` when it refused, and None when the environment is the next to ask."""
    kind = deployment_store()
    if kind == ENV:
        return None
    reference, value, refused = _ask(kind, name)
    if refused:
        return "", None
    return (reference, value) if value is not None else None


def stored(name: str) -> str | None:
    """The deployment credential the core knows as `name`: the declared store's, else the variable.

    THE READ STAYS IN THIS BODY ON PURPOSE. `environ.names_read` counts a literal handed to a
    function that reads its parameter from the environment, so every name a module asks for here
    stays reserved against an add-on claiming it, and stays in the measured table of what reaches
    a workload, exactly as it was when that module read the variable itself."""
    declared = _declared(name)
    if declared is not None:
        return declared[1]
    return os.environ.get(name) or None


def stored_answer(name: str) -> tuple[str, str | None]:
    """`(the reference that answered, value)` for the deployment credential `name`; `("", None)`
    when nothing answered. The reference is what a reader keys a credential by and what the doctor
    says, so two credentials can be told apart without comparing their values."""
    declared = _declared(name)
    if declared is not None:
        return declared
    value = os.environ.get(name) or None
    return (f"{ENV}:{name}", value) if value else ("", None)


def held(names: Iterable[str]) -> dict[str, str]:
    """`{name: value}` for each of `names` that answers now — a snapshot for a reader that takes
    its settings once, as a mapping (the panel's identity provider)."""
    return {name: value for name in names if (value := stored(name)) is not None}


def answer(reference: object) -> tuple[str, str | None]:
    """`(the reference that answered, value)` for `reference`, or `("", None)`. A bare name is a
    deployment credential; `<kind>:<name>` asks that store alone."""
    kind, name = parse(reference)
    if not name:
        return "", None
    if not kind:
        return stored_answer(name)
    found, value, _refused = _ask(kind, name)
    return (found, value) if value else ("", None)


def resolve(reference: object) -> str | None:
    """The secret `reference` names, read now — or None."""
    return answer(reference)[1]


def source(reference: object) -> str:
    """The reference that answers for `reference` (`env:X`, `file:x`, …), or `""`; never a
    value."""
    return answer(reference)[0]


def describe(reference: object) -> str:
    """Where `reference` is looked for and whether it is there, in the order it is asked — what
    `openfactory doctor` prints. Never the value."""
    kind, name = parse(reference)
    if kind:
        try:
            store = build_store(kind)
        except ValueError as exc:
            return f"`{reference}`: {exc}"
        try:
            return str(store.describe(name))
        except Exception:  # noqa: BLE001 — an add-on's words may not take the diagnostic down
            log.warning("the %s credential store could not describe `%s`", kind, name,
                        exc_info=True)
            return f"`{reference}`: the {kind} store could not say where it is"
    first = deployment_store()
    if first == ENV:
        return describe(f"{ENV}:{name}")
    return f"{describe(f'{first}:{name}')}, then {describe(f'{ENV}:{name}')}"


def unusable(kind: str) -> str:
    """Why the store `kind` cannot be read at all, in one sentence, or `""`: an unknown kind, or
    the store's own answer to `unusable()` — an optional method, asked when a row defines it, so
    a store that has nothing to say about itself is not made to."""
    try:
        store = build_store(kind)
    except ValueError as exc:
        return str(exc)
    asked = getattr(store, "unusable", None)
    if not callable(asked):
        return ""
    try:
        return str(asked() or "")
    except Exception as exc:  # noqa: BLE001 — an add-on's answer may not take the doctor down
        log.warning("the %s credential store could not say whether it is usable", kind,
                    exc_info=True)
        return f"the {kind} store could not say whether it can be read ({type(exc).__name__})"


def refusal(reference: object) -> str:
    """Why `reference` can never answer as it stands — a store nobody installed, or one that
    refuses what it holds — or `""` when it can be asked. Holding nothing is not a refusal: that
    is a missing secret, which the reader that needs it reports."""
    kind, name = parse(reference)
    asked = [kind] if kind else [k for k in (deployment_store(),) if k != ENV]
    for each in asked:
        try:
            store = build_store(each)
        except ValueError as exc:
            return str(exc)
        try:
            store.resolve(name)
        except CredentialRefused as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 — an add-on's store may not take the doctor down
            log.warning("the %s credential store failed reading `%s`", each, name,
                        exc_info=True)
            return f"the {each} store failed reading `{name}` ({type(exc).__name__})"
    return ""


class Stored:
    """The deployment's credentials as a mapping of names, each looked up through `stored` when it
    is asked: for a reader that takes a mapping of settings (`claude_code.credential_in`) and is
    asked about THIS deployment rather than about a file of settings.

    LOOKUPS ONLY: `get`, `[]` and `in`. A store can be asked for a name and cannot always list its
    names, so this does not pretend to iterate."""

    def get(self, name: str, default: str | None = None) -> str | None:
        value = stored(name)
        return value if value is not None else default

    def __getitem__(self, name: str) -> str:
        value = stored(name)
        if value is None:
            raise KeyError(name)
        return value

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and stored(name) is not None
