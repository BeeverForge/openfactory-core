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

A REFUSAL IS AN ANSWER, AND IT IS FINAL (review of #822). `stored` answers None for it, as for a
name nothing holds, and that fold is what opened the panel: the identity provider read "no
closing variable is held" as "nothing is configured", and a project whose reference was refused
was handed the deployment's own token by the next step of its chain. So the store says a refusal
as itself — `lookup` returns an `Answer` whose `refused` names why — and the two shapes a reader
asks in keep it: `chain` walks a fallback and stops AT a refusal, never past it, and `Stored`, a
mapping read as one walk, answers nothing from its first refusal on. A reader that asks "is a
credential configured?" asks `refusals` too, and a door a refused name would close stays closed.

NAMES AND REFERENCES, NEVER VALUES. What this module logs, and what `describe` and `source`
answer, say where a secret is and whether it is there. A value leaves only through `stored` and
`resolve`, to the caller that uses it, and nothing here keeps one.

THE AXIS. `credential_store.<kind>` in the `openfactory.adapters` entry-point group names a
zero-argument builder returning a `CredentialStore`. A built-in wins a collision and an unknown
kind refuses naming what is installed, as on every axis; a builder that raises is a store that
cannot be built, and refuses the same way (`build_store`).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

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
    """The store for `kind`. Raises `ValueError` on a kind nobody installed, naming the ones that
    are, and on one whose builder fails, naming the kind and what it raised.

    `ValueError` IS THE ONLY WAY A STORE CANNOT BE BUILT (review of bd178211 for #822). Every
    reader here catches it: a reference to such a store is refused by name, and a reader that walks
    every installed store (`held_values`, under the product's facts and the certify pack) passes it
    over. An add-on's builder reads its own settings and may raise anything on a deployment that
    installed it and never set it up — `RuntimeError("VAULT_ADDR is not set")` — and that stopped
    every product turn, from a store nobody declared or named. A store that cannot be built hands
    no value to anyone, so passing it over hides nothing."""
    key = (kind or "").strip().lower()
    builder = STORES.get(key) or plugins.builder(AXIS, key, builtin=STORES)
    if builder is None:
        raise ValueError(f"unknown credential store {key!r} — known: {', '.join(known())}"
                         f"{plugins.install_hint(AXIS, key)}")
    try:
        return builder()
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 — an add-on's store may not take a reader down
        raise ValueError(f"the {key} credential store could not be built "
                         f"({type(exc).__name__}) — see the settings its add-on reads") from exc


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


@dataclass(frozen=True)
class Answer:
    """What the store said for one name: the reference that answered and its value, or why it
    refused — never both. `value` stays out of the repr, so an answer printed or logged by
    accident says where a secret is and never what it is."""

    #: `env:X`, `file:x`, …: what answered, or what refused; `""` when nothing did either
    reference: str = ""
    value: str | None = field(default=None, repr=False)
    #: why the store will not hand over what it holds, in its own sentence; `""` when it did not
    #: refuse. Holding nothing is not a refusal.
    refused: str = ""


#: Nothing answered and nothing refused.
NOTHING = Answer()


def _ask(kind: str, name: str, *, quiet: bool = False) -> Answer:
    """What the store `kind` answers for `name`. Never raises: an unknown kind and a store that
    refuses or fails are an `Answer` that says why, by reference, and holds nothing. `quiet` is
    for a reader that asks only WHETHER it refuses (the doctor) and says so itself, or that uses
    nothing it reads (a scrub): what it is told goes to DEBUG, never to a warning."""
    reference = f"{kind}:{name}"
    try:
        store = build_store(kind)
    except ValueError as exc:
        if not quiet:
            log.warning("the credential `%s` cannot be read: %s — nothing is used in its place",
                        reference, exc)
        return Answer(reference=reference, refused=str(exc))
    try:
        value = store.resolve(name)
    except CredentialRefused as exc:
        if not quiet:
            log.warning("the credential `%s` is refused: %s — nothing is used in its place",
                        reference, exc)
        return Answer(reference=reference, refused=str(exc))
    except Exception as exc:  # noqa: BLE001 — an add-on's store may not take a credential path down
        # QUIET IS SAID AT DEBUG, never not at all (review of bd178211): a scrub reads every entry
        # of every store at each call, and a store that fails wrote one warning with a traceback
        # per entry per scrub, each about a credential nobody was about to use. A reader that
        # uses the credential asks loudly and says it at WARNING, with the traceback.
        log.log(logging.DEBUG if quiet else logging.WARNING,
                "the %s credential store failed reading `%s`; it is treated as a refusal and "
                "nothing is used in its place", kind, name, exc_info=not quiet)
        return Answer(reference=reference,
                      refused=f"the {kind} store failed reading `{name}` ({type(exc).__name__})")
    return Answer(reference=reference, value=value) if value else NOTHING


def _declared(name: str, *, quiet: bool = False) -> Answer | None:
    """What the declared store answers for `name` — its value, or its refusal — and None when it
    holds nothing there and the environment is the next to ask."""
    kind = deployment_store()
    if kind == ENV:
        return None
    found = _ask(kind, name, quiet=quiet)
    return found if (found.value or found.refused) else None


def stored(name: str) -> str | None:
    """The deployment credential the core knows as `name`: the declared store's, else the variable.

    THE READ STAYS IN THIS BODY ON PURPOSE. `environ.names_read` counts a literal handed to a
    function that reads its parameter from the environment, so every name a module asks for here
    stays reserved against an add-on claiming it, and stays in the measured table of what reaches
    a workload, exactly as it was when that module read the variable itself."""
    declared = _declared(name)
    if declared is not None:
        return declared.value
    return os.environ.get(name) or None


def lookup(name: str, *, quiet: bool = False) -> Answer:
    """What answers for the deployment credential `name` — the declared store's value or refusal,
    else the variable — as an `Answer`, so a reader can tell "refused" from "not held"."""
    declared = _declared(name, quiet=quiet)
    if declared is not None:
        return declared
    value = os.environ.get(name) or None
    return Answer(reference=f"{ENV}:{name}", value=value) if value else NOTHING


def stored_answer(name: str) -> tuple[str, str | None]:
    """`(the reference that answered, value)` for the deployment credential `name`; `("", None)`
    when nothing answered. The reference is what a reader keys a credential by and what the doctor
    says, so two credentials can be told apart without comparing their values. `lookup`'s, so the
    identity is built in one place."""
    found = lookup(name)
    return (found.reference, found.value) if found.value else ("", None)


def chain(names: Iterable[str]) -> Answer:
    """The first of `names` that answers — and NOTHING AFTER A REFUSAL: a refused name ends the
    walk with its refusal, because the next name is another credential, and a secret the
    deployment did not choose is not replaced by one it did not name for this (review of #822:
    a refused `OPENFACTORY_TRACKER_TOKEN` became `OPENFACTORY_BOT_TOKEN`). Spelled as a table at
    the call, `chain(("A", "B"))`, which is how `environ.names_read` keeps both names reserved."""
    for name in names:
        found = lookup(name)
        if found.value or found.refused:
            return found
    return NOTHING


def held(names: Iterable[str]) -> dict[str, str]:
    """`{name: value}` for each of `names` that answers now — a snapshot for a reader that takes
    its settings once, as a mapping (the panel's identity provider). A refused name is not in it;
    ask `refusals` for those, and keep the door they would close shut."""
    return {name: value for name in names if (value := stored(name)) is not None}


def refusals(names: Iterable[str]) -> dict[str, str]:
    """`{name: why}` for each of `names` the deployment's store refuses now — never a value. Asked
    quietly: the reader that asks says it, once, in its own words."""
    return {name: found.refused for name in names
            if (found := lookup(name, quiet=True)).refused}


def look(reference: object, *, quiet: bool = False) -> Answer:
    """What answers for `reference`: a bare name is a deployment credential (`lookup`), and
    `<kind>:<name>` asks that store alone."""
    kind, name = parse(reference)
    if not name:
        return NOTHING
    if not kind:
        return lookup(name, quiet=quiet)
    return _ask(kind, name, quiet=quiet)


def answer(reference: object) -> tuple[str, str | None]:
    """`(the reference that answered, value)` for `reference`, or `("", None)` — for a refusal
    too, which `look` tells apart. A bare name is a deployment credential; `<kind>:<name>` asks
    that store alone."""
    found = look(reference)
    return (found.reference, found.value) if found.value else ("", None)


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
    return look(reference, quiet=True).refused


def listed(kind: str) -> list[str] | None:
    """The names the store `kind` holds, when it can say — an optional `names()` on the row, asked
    when the row defines it, as `unusable()` is — and None when it cannot, which is not "it holds
    nothing". What the doctor walks to find a refused file nobody named: a planted panel-token
    file is refused, and is a credential no reader asked for by a name the doctor would think
    of."""
    try:
        store = build_store(kind)
    except ValueError:
        return None
    asked = getattr(store, "names", None)
    if not callable(asked):
        return None
    try:
        return sorted(str(n) for n in (asked() or ()))
    except Exception:  # noqa: BLE001 — an add-on's listing may not take the doctor down
        log.warning("the %s credential store could not list what it holds", kind, exc_info=True)
        return None


def held_values(named: Iterable[object] = ()) -> set[str]:
    """Every value the stores hold, for a reader that must never print one — the certify pack's
    redactor, the product role's facts (#742, review of 256c5b0): what each reference in `named`
    answers; every entry of every store this deployment can read that lists what it holds (the
    file store, whenever it has a directory — a `file:` reference works whatever store is
    declared); and, for a declared store that cannot list, every credential the core reads by name.
    Read quietly: a refusal here is one value fewer to hide, never a warning. The values are never
    logged; they exist to be withheld."""
    from openfactory import environ

    asked: set[object] = set(named)
    declared = deployment_store()
    for kind in known():
        if kind == ENV or unusable(kind):
            continue
        listing = listed(kind)
        if listing is not None:
            asked |= {f"{kind}:{name}" for name in listing}
        elif kind == declared:
            asked |= {n for n in environ.names_read() if environ.holds_a_credential(n)}
    return {v.strip() for ref in asked if (v := look(ref, quiet=True).value) and v.strip()}


class Stored:
    """The deployment's credentials as a mapping of names, for a reader that takes a mapping of
    settings (`claude_code.credential_in`, an auth route's `missing`) and is asked about THIS
    deployment rather than about a file of settings.

    ONE WALK, AND IT ENDS AT A REFUSAL. Such a reader asks its names in its own order and takes
    the first that answers — the token pool, then one token, then a key — so a refusal in the
    middle would be passed over for the next name exactly as `chain` refuses to. From the first
    refused name on, every name answers nothing, and `refused` says which and why: build one per
    walk. LOOKUPS ONLY: `get`, `[]` and `in`. A store can be asked for a name and cannot always
    list its names, so this does not pretend to iterate."""

    def __init__(self) -> None:
        #: `{name: why}` of the refusal that ended this walk — never a value
        self.refused: dict[str, str] = {}

    def get(self, name: str, default: str | None = None) -> str | None:
        if self.refused:
            return default
        found = lookup(name)
        if found.refused:
            self.refused[name] = found.refused
            return default
        return found.value if found.value is not None else default

    def __getitem__(self, name: str) -> str:
        value = self.get(name)
        if value is None:
            raise KeyError(name)
        return value

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self.get(name) is not None
