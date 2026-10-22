"""Who asked for what, and what came of it: one typed, immutable record per call into the action
layer (#694).

WHY A RECORD AND NOT ONLY THE LINE. `actions.perform` is the one gate every transport goes
through, and until #694 its only trace of who asked was one INFO line. Eight of its nine ways out
never wrote it, and nothing kept it: measured on bb929e49 with an empty `HOME` and a temp registry,
`openfactory act product_status -p nosuch` printed only the refusal and the `action=… by=…` line
reached nobody. *Who approved that production release* had no answer an auditor could read back.
The record is that answer, as a value: the line stays beside it (ADR-0039 §2).

ONE VIEW FOR BOTH. `perform`'s INFO line prints what the record keeps, `_kept(params)`, made
once per call and handed to `AuditRecord.of` (#694, the human's decision of 2026-10-21): a secret
masked, a person's words as their length and digest, every other value bounded — in the line as
in the record, so there is no second list of secrets or of free-text names to forget to update.
`redact` alone (secrets only) is what the denial warnings print (`actions._loggable`).

NO CREDENTIAL, HOWEVER SENT. Both views mask a value by its name's pattern (`is_secret`), at every
depth of a mapping or a list (`_clean`), and scrub every string of credentials before it is cut
(`product.model.scrub_credentials`: a URL's userinfo, a credential's shape, this process's
secrets). On c310ba28 four exact names were masked at the top level only, and the PR #1039 review
read a GitHub token in a URL, `api_key`, `Password`, `github_pat` and a nested `password` back out
of `audit.db` (2026-10-21).

WHERE IT IS KEPT. `write` hands each record to `sink()` as one row of kind `audit` in the metrics
store, off the event loop; a deployment that declares no store keeps them in `audit.db` beside
`registry.yaml`. A person's words are kept as their length and digest, never as text (ADR-0024),
and every other value is bounded. The digest is an unsalted sha256: it proves a known text and
reveals a short one (a six-digit message was read back from it in 0.22 s, 2026-10-21).

NO ENGINE AT IMPORT. This module is imported by `openfactory.actions`, which the panel imports;
the panel serves without the `runtime` extra (`tests/test_the_panel_serves_without_the_engines_
client.py`), so nothing here imports `temporalio` or `openfactory.runtime` at module level.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import logging
import os
import re
import threading
import unicodedata
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from openfactory.observability.events import now_iso
from openfactory.observability.logs import DEPLOYMENT_VARIABLE

if TYPE_CHECKING:
    from openfactory.actions.base import Actor, Outcome
    from openfactory.observability.metrics import MetricRecord, MetricsSink

log = logging.getLogger(__name__)

#: Parameters whose VALUE must never reach a log line or an audit record. `approve_prod` and
#: `promote` take the approver's password, and `perform` writes its line and its record on every
#: call including the refusals — which is precisely the path a wrong password takes. The catalog's
#: own secret names, exactly: `actions._ADDRESSABLE` is held apart from them. What masks a value is
#: `is_secret`, which matches these and every name of their shape; `redact` and `_kept` read it.
SECRET = frozenset({"password", "token", "secret", "key"})

#: What makes a parameter's name a secret's wherever it sits in the name, in any case (`api_key`,
#: `Password`, `x-auth-token`, `client_secret`). Measured on c310ba28 (PR #1039 review): with four
#: exact names, a refused `product_status` sent `api_key`, `Password` and `github_pat` and the
#: record kept all three values — the panel hands `perform` every name a request body holds.
SECRET_WORDS = ("passw", "secret", "token", "key")

#: What makes a name a secret's only as a WORD of it (`pat`, `github_pat`, `githubPat`): as a
#: substring, `pat` is in `path` (`product_ingest`) and `repo_path` (`product_first_source`), two
#: parameters the catalog takes whose values are file names, not credentials — read off every
#: catalog row's parameters on 2026-10-21. No other word of `SECRET_WORDS` meets a catalog name;
#: `token_env` (`product_start`) is masked, and loses only the name of a variable a person could
#: as easily have pasted the token into.
SECRET_TOKENS = frozenset({"pat"})

#: A name split into its words: a run of letters or digits, a capital starting a new one.
_WORD = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")

#: What a masked value reads as, in the line and in the record alike.
MASK = "***"

#: The record's `product` when the registry could not be read, so that "this project belongs to
#: no product" (`""`) and "the registry did not answer" never share a value
#: (`docs/engineering-lessons.md` §2). No `product_key` can spell it: those carry `repo:`.
PRODUCT_UNREAD = "unread"

#: The record's `reason` for a call cancelled before its row answered (a panel client that hung
#: up, a worker shutting down). Not one of `actions.REASONS`: no caller is ever told it — `perform`
#: re-raises the `CancelledError` — so it is the record's word alone, and no row declares it.
CANCELLED = "cancelled"

#: The variable an operator names a deployment by, for the records it writes. The JSON log line
#: reads the same one (#681), so it is that module's constant rather than a second spelling that
#: could drift from it; only the unset case differs (`deployment`'s docstring).
DEPLOYMENT_ENV = DEPLOYMENT_VARIABLE

#: The most characters of one parameter's value a record keeps (#694 Q11). A value is whatever the
#: caller sent, and a refused call is recorded as faithfully as a kept one, so without a bound one
#: caller could write a row of any size per call into a store kept for a year. Two thousand holds
#: every URL, ref and name the catalog takes; what is cut is said in the value and in the log.
VALUE_CHARS = 2_000

#: The most parameters one record keeps, and the most characters of a parameter's name it keeps:
#: the catalog's widest row takes 4 and its longest name has 10, but the panel hands `perform`
#: every name a request body holds. With `VALUE_CHARS` alone, one refused `POST /api/act/
#: product_status` with 5,000 parameters of 2,000 characters wrote a 10,065,008-character row
#: and a 10 MB `audit.db` (branch review round 2, 2026-10-21, a real `openfactory serve`).
PARAMS_KEPT = 32
NAME_CHARS = 64

#: How many mappings or lists deep a parameter's value is read (`_clean`): `product_say`'s
#: `context` is one level, and nothing the catalog takes is more than two. What sits deeper is
#: not kept — it is `TOO_DEEP` in its place — because the record cannot read the names under it,
#: and a secret's name it cannot read is a secret it would keep.
NESTED_DEPTH = 4
TOO_DEEP = f"[nested deeper than {NESTED_DEPTH} levels; not kept]"

#: How long a record is read, in days (#694 Q3): who did what, when, and on which deployment is
#: a question a security review asks of the last year, not forever — the precedent of the board's
#: own audit line, `adapters/tracker/local.py` `_REMOVED_KEPT_DAYS` (365, #384). Carried by each
#: row as `expires_at`, which the sqlite store hides on read and deletes at the next start of the
#: worker or the panel (`observability.retention`), and which a store that deletes by a TTL on
#: that field deletes — so the period is the record's own, in every store.
#: Stated with its value in `docs/rotation-and-retention.md`; change both together.
AUDIT_KEPT_DAYS = 365

#: The file the records go to on a deployment that declares no metrics store (`null`, a host CLI
#: with no compose environment), beside `registry.yaml` — see `sink`.
AUDIT_FILE = "audit.db"


def deployment() -> str:
    """Which deployment this process is: `OPENFACTORY_DEPLOYMENT` when set, else the Temporal
    namespace the engine connection uses (`TEMPORAL_NAMESPACE`, `default` when unset).

    The JSON log line reads the same variable (`logs.DEPLOYMENT_VARIABLE`, #681) and leaves its
    `deployment` key out when it is unset; a record always names a deployment, so it falls back
    to the namespace, the one name two deployments sharing a Temporal account cannot share
    (`OPENFACTORY_PLATFORM_NAME` is branding, not an identity). It is read from the environment
    exactly as `runtime.temporal.connection.namespace()` reads it rather than by calling it: that
    module imports `temporalio` at its top, and the panel makes a record on every action without
    the `runtime` extra. The two are held equal by
    `tests/test_every_action_leaves_one_audit_record.py`."""
    named = os.environ.get(DEPLOYMENT_ENV, "").strip()
    return named or os.environ.get("TEMPORAL_NAMESPACE", "default")


#: What a correlation id a transport was handed may look like to be kept as sent (#694 Q4): the
#: characters a request id from nginx (`$request_id`, 32 hex), a load balancer or a UUID is made
#: of, and at most 128 of them. Anything else — a newline that would split the INFO line, a space,
#: a header the size of a document — is replaced, never cut down, because a record kept for a
#: year must not carry what a caller wrote into it.
_CORRELATION = re.compile(r"[A-Za-z0-9._:-]{1,128}")


def new_correlation_id() -> str:
    """A fresh correlation id: `uuid4().hex`, 32 lower-case hex digits — the shape nginx's own
    `$request_id` has, so a minted id and a proxy's read alike in a record."""
    return uuid.uuid4().hex


def correlation_or_new(value: object) -> str:
    """`value` when it is a correlation id (`_CORRELATION`), else a new one — none of `value` is
    kept, so a header that was not an id never reaches the record, even in part."""
    if isinstance(value, str) and _CORRELATION.fullmatch(value):
        return value
    return new_correlation_id()


def is_secret(name: object) -> bool:
    """Whether a parameter named `name` holds a secret: a `SECRET_WORDS` word anywhere in it, or a
    `SECRET_TOKENS` word as one of its words, whatever the case."""
    text = str(name)
    lowered = text.lower()
    if any(word in lowered for word in SECRET_WORDS):
        return True
    return any(word.lower() in SECRET_TOKENS for word in _WORD.findall(text))


def _scrub(text: str) -> str:
    """`text` with every credential withheld, as a facts file is (`product.model.
    scrub_credentials`): a URL's userinfo, a credential's shape, a value of this process's secrets.
    Imported here: `openfactory.product` costs 64 ms to import (measured 2026-10-21), and the panel
    imports this module at start."""
    from openfactory.product.model import scrub_credentials

    return scrub_credentials(text)


def _name(name: object) -> str:
    """A parameter's name as a record keeps it: scrubbed, and cut to `NAME_CHARS` with the cut
    said in it — a name is whatever a caller's body held, a token included."""
    text = _scrub(str(name))
    if len(text) <= NAME_CHARS:
        return text
    return f"{text[:NAME_CHARS]}… [{len(text) - NAME_CHARS} more characters not kept]"


def _clean(value: object, *, depth: int, words: bool) -> object:
    """`value` with no credential in it, at every depth: each string scrubbed (`_scrub`); each
    mapping's names read as a parameter's are — a secret's masked, and, when `words`, a person's
    words (`FREE_TEXT`) as their length and digest — and its values cleaned in turn; each list's
    items cleaned. At most `PARAMS_KEPT` names or items of each, the rest counted; nothing past
    `NESTED_DEPTH` levels. Numbers, booleans and None as they are; anything else as its scrubbed
    `str`."""
    from itertools import islice

    from openfactory.actions.base import FREE_TEXT

    if isinstance(value, str):
        return _scrub(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Mapping | list | tuple | set | frozenset) and depth >= NESTED_DEPTH:
        return TOO_DEEP
    if isinstance(value, Mapping):
        cleaned: dict[str, object] = {}
        for name, inner in islice(value.items(), PARAMS_KEPT):
            if is_secret(name):
                cleaned[_name(name)] = MASK
            elif words and name in FREE_TEXT and inner is not None:
                cleaned[_name(name)] = _words(inner)
            else:
                cleaned[_name(name)] = _clean(inner, depth=depth + 1, words=words)
        if len(value) > PARAMS_KEPT:
            cleaned["…"] = f"{len(value) - PARAMS_KEPT} more entries not kept"
        return cleaned
    if isinstance(value, list | tuple | set | frozenset):
        items = [_clean(inner, depth=depth + 1, words=words)
                 for inner in islice(value, PARAMS_KEPT)]
        if len(value) > PARAMS_KEPT:
            items.append(f"… {len(value) - PARAMS_KEPT} more items not kept")
        return items
    return _scrub(str(value))


#: The two categories that are no `C` and still end a line: Zl and Zp (U+2028, U+2029), on both
#: of which `str.splitlines()` breaks. On 58cbd307 a U+2028 in a project was two lines of the
#: listing, the second the caller's forged record (branch review, 2026-10-22).
_BREAKS = ("Zl", "Zp")

#: The three control characters a reader knows by name, written as Python writes them.
_NAMED_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def printable(text: object) -> str:
    """`text` as one line a person reads: each control or other non-printing character (a
    `unicodedata` category starting with `C`: a newline, a carriage return, an escape, a lone
    surrogate, U+0085) and each line or paragraph separator (`Zl`, `Zp`: U+2028, U+2029) written
    as its escape — `\\n`, `\\r`, `\\t`, else `\\xNN`, `\\uNNNN` or
    `\\UNNNNNNNN`; every other character as it is. For what is SHOWN — the `openfactory audit`
    listing, the action's log lines — never for what is kept: the record keeps what was sent, and
    `--json` escapes it on its own.

    WHY. A record's `action` and `project` are whatever a caller sent, and on c310ba28 the listing
    printed them as stored: three `POST /api/act/*` calls by an anonymous caller became six lines,
    one reading `… alice  approve_prod  books  ok`, and `\\x1b[2K\\r` erased its own line on a
    terminal; the unknown-action INFO line was one log record of two lines (PR #1039 review
    B1, 2026-10-21)."""
    text = str(text)
    if text.isprintable():
        return text
    shown = []
    for char in text:
        if char in _NAMED_ESCAPES:
            shown.append(_NAMED_ESCAPES[char])
        elif unicodedata.category(char)[0] == "C" or unicodedata.category(char) in _BREAKS:
            code = ord(char)
            shown.append(f"\\x{code:02x}" if code < 0x100 else
                         f"\\u{code:04x}" if code < 0x10000 else f"\\U{code:08x}")
        else:
            shown.append(char)
    return "".join(shown)


def redact(params: Mapping[str, object]) -> dict[str, object]:
    """`params` with the value of every secret's name (`is_secret`) replaced by `MASK`, at every
    depth, and every string scrubbed (`_clean`); the names stay, so the line and the record still
    say that a password was given. What the denial warnings print (`actions._loggable`)."""
    return {_scrub(str(k)): (MASK if is_secret(k) else _clean(v, depth=1, words=False))
            for k, v in params.items()}


def _words(value: object) -> dict[str, object]:
    """A person's words as the record keeps them: how many characters, and their sha256 — that and
    when they spoke, never the text (`actions.base.FREE_TEXT`). Unsalted, so the digest proves a
    known text and reveals a short one: a six-digit message was read back from it in 0.22 s of
    plain Python (measured 2026-10-21)."""
    text = str(value)
    # `surrogatepass`: a JSON body may carry a lone surrogate (`"\ud800"`), which a strict encode
    # refuses with `UnicodeEncodeError` — and the call then left no record (measured 2026-10-21).
    digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
    return {"chars": len(text), "sha256": digest}


def _cut(text: str) -> str:
    """`text` as a record keeps it: whole up to `VALUE_CHARS`, else its first `VALUE_CHARS` and
    how many characters were left out."""
    if len(text) <= VALUE_CHARS:
        return text
    return f"{text[:VALUE_CHARS]}… [{len(text) - VALUE_CHARS} more characters not kept]"


def _kept(action: str, params: Mapping[str, object]) -> dict[str, object]:
    """`params` as a record keeps them, and as `perform`'s INFO line prints them: every secret's
    name (`is_secret`) masked, each `FREE_TEXT` value as its length and digest, and every other
    value cleaned (`_clean`: scrubbed, at every depth, under the same rules) and then cut to
    `VALUE_CHARS` with the cut said — in the value, and in one INFO line naming the action and the
    parameter. At most `PARAMS_KEPT` parameters are kept, `project` first, each name scrubbed and
    cut to `NAME_CHARS`; the parameters not kept are counted under the name `…` and said in one
    INFO line. Called once per call, so each INFO line is written once."""
    from openfactory.actions.base import FREE_TEXT

    kept: dict[str, object] = {}
    # `project` first, so the parameters the record lists still name it: a caller's extra names
    # must not push it out of the `PARAMS_KEPT` kept.
    names = sorted(params, key=lambda n: n != "project")
    for name in names[:PARAMS_KEPT]:
        value = params[name]
        shown = _name(name)
        if is_secret(name):
            kept[shown] = MASK
            continue
        if name in FREE_TEXT and value is not None:
            kept[shown] = _words(value)
            continue
        # SCRUBBED WHOLE, THEN CUT: cut first, a token that began just before `VALUE_CHARS` kept
        # its first characters — `ghp_A1b2C3`, which no credential's shape matches once cut.
        clean = _clean(value, depth=1, words=True)
        text = clean if isinstance(clean, str) else str(clean)
        if len(text) <= VALUE_CHARS:
            kept[shown] = clean
            continue
        kept[shown] = _cut(text)
        log.info("audit: %s's %s was %d characters; the record keeps the first %d",
                 printable(action), printable(shown),
                 len(text), VALUE_CHARS)
    if len(names) > PARAMS_KEPT:
        kept["…"] = f"{len(names) - PARAMS_KEPT} more parameters not kept"
        log.info("audit: %s was passed %d parameters; the record keeps %d", printable(action),
                 len(names), PARAMS_KEPT)
    return kept


def _frozen(value: object) -> object:
    """`value` read-only all the way down: a mapping as a read-only mapping, a list or tuple as a
    tuple, each of their values frozen in turn — so a record's parameters cannot be edited below
    the top level either (PR #1039 review, robertocsp: on ecde14fc a nested dict and list were
    plain). The depth is `_clean`'s, `NESTED_DEPTH` at most."""
    if isinstance(value, Mapping):
        return MappingProxyType({k: _frozen(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_frozen(v) for v in value)
    return value


def _thawed(value: object) -> object:
    """`_frozen` undone, for a store that serialises a dict and a list, not their read-only
    views (`metric_of`)."""
    if isinstance(value, Mapping):
        return {k: _thawed(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thawed(v) for v in value]
    return value


def _storable(text: str) -> str:
    """`text` as a store can key a row by: each lone surrogate written as its escape (`\\ud800`),
    every other character as it is — sqlite binds a key column as strict UTF-8 and refuses one."""
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def _product_of(name: str) -> str:
    """The product a registry project belongs to (`product_key`, ADR-0051), or `""` when it is not
    linked to a context repository or the registry does not know the name.

    A project with no `product:` section is "a product of one" to the product role, keyed
    `project:<name>`; the record leaves the field empty instead, because the issue asks for the
    product *when there is one* and a project's own name is already in `project`. Never raises:
    `perform` leaves a record for exactly the call that named a project nobody registered."""
    if not name:
        return ""
    # Imported here, not above: the registry pulls pydantic and yaml, and a record made for an
    # unknown action has no project to look up.
    from openfactory.product.key import product_key
    from openfactory.registry import ProjectRegistry

    registry = ProjectRegistry()
    try:
        project = registry.get(name)
    except KeyError:
        return ""
    except (OSError, ValueError) as exc:
        log.warning("audit: could not read the registry at %s to name the product of %r (%s); "
                    "the record says product=%s", registry.path, name, exc, PRODUCT_UNREAD)
        return PRODUCT_UNREAD
    key = product_key(project)
    return key if key.startswith("repo:") else ""


@dataclass(frozen=True)
class AuditRecord:
    """One call into the action layer, as it happened. Frozen, and its `params` a read-only
    mapping: a record a later step could rewrite is not a record of what happened.

    Made by `AuditRecord.of` from exactly what `perform` holds — the action's name, who asked, what
    they passed and the `Outcome` — so every transport's call is recorded in one shape."""

    #: The append-only key: two records made in the same instant for the same action are still
    #: two records (uuid4 hex).
    record_id: str
    #: Who asked: `Actor.id`, and the name a human reads (`Actor.display`, else the id).
    actor_id: str
    actor_display: str
    #: Which identity provider named the caller: `Actor.subject.via` (`local`, `oidc`, `anonymous`,
    #: `cli`), `system` for the factory acting on nobody's behalf (`actions.SYSTEM`), `""` when the
    #: transport resolved no subject.
    provider: str
    #: Which transport carried the request (`Actor.via`: `panel`, `slack`, `cli`, …).
    via: str
    #: The action as `perform` resolved it (lower-cased, stripped), or as asked when no row has
    #: it — scrubbed of credentials, a lone surrogate written as its escape (it is in the row's
    #: key), cut to `VALUE_CHARS`.
    action: str
    #: What was passed, as `_kept` keeps it: every secret's name (`is_secret`) masked at every
    #: depth, a person's words (`actions.base.FREE_TEXT`) as `{"chars", "sha256"}`, every string
    #: scrubbed of credentials, other values cut to `VALUE_CHARS`; at most `PARAMS_KEPT` of them,
    #: `project` first, each name cut to `NAME_CHARS`, nothing past `NESTED_DEPTH`. Read-only all
    #: the way down (`_frozen`).
    params: Mapping[str, object]
    ok: bool
    #: `Outcome.code` (one of `actions.CODES`), and the refusal's `reason` (`""` when it worked).
    code: str
    reason: str
    #: The id that ties this call to the request that caused it and to what it caused
    #: (`Actor.correlation`): the panel's `X-Request-ID` when it was an id, the CLI's own per call,
    #: else the one `perform` minted for the call before its row ran — never `""` from `perform`.
    correlation_id: str
    #: Which deployment wrote the record (`deployment()`): the operator's name for it, else the
    #: engine's namespace.
    deployment: str
    #: The `project` parameter, scrubbed of credentials, each lone surrogate written as its
    #: escape and then cut to `VALUE_CHARS` as `_kept` cuts a value, because it is also the row's
    #: key (`""` when the action takes none) — and its product.
    project: str
    product: str
    #: When, ISO-8601 in UTC.
    ts: str = field(default_factory=now_iso)

    @classmethod
    def of(cls, name: str, by: Actor, params: Mapping[str, object], outcome: Outcome, *,
           product_of: Callable[[str], str] = _product_of,
           kept: Mapping[str, object] | None = None) -> AuditRecord:
        """The record of one `perform(name, by=by, **params)` that returned `outcome`.

        `kept` is `_kept(params)` when the caller already made it — `perform` does, to print the
        same view in its INFO line — so it is made once per call; else it is made here."""
        from openfactory.actions.base import SYSTEM

        # ADR-0057 D1 names the factory's own actor `system`; it acts on nobody's behalf, so it
        # carries no subject and the name is written here rather than invented on `Actor`. Asked
        # with its id aside, not `by is SYSTEM`: `perform` hands the row a copy of `SYSTEM` that
        # carries the call's correlation id, and that copy is still the factory.
        system = by is SYSTEM or dataclasses.replace(by, correlation="") == SYSTEM
        provider = "system" if system else (by.subject.via if by.subject else "")
        # THE ROW'S KEY IS BOUNDED AND STORABLE TOO. `metric_of` makes `project` the row's `pk`
        # and `action` part of its `sk`, which sqlite binds as strict UTF-8 — unlike `data`, which
        # `json.dumps` escapes. On cd7dbcd3 both were taken as sent: a lone surrogate in either
        # (`"nosuch\ud800"`) made the store refuse the row, so the call left no record, and a
        # 1,000,000-character project wrote a 1,000,000-character `pk` and grew `audit.db` to
        # 7,041,024 bytes from one request (branch review of 2026-10-21, a real `openfactory
        # serve`). So both are escaped and then cut to `VALUE_CHARS`: in that order, because an
        # escape is six characters, and a project cut first and escaped after gave 1,000,000 ×
        # `\ud800` a `pk` of 12,035 characters (branch review round 2). `_kept` has already said
        # in its INFO line that a long project was cut, so this cut is not said again.
        # SCRUBBED AS A PARAMETER IS, before it is lower-cased (an `AKIA…` key's shape is upper
        # case): both are whatever a caller typed, and both are in the row's key.
        asked = _scrub((name or "").strip()).lower() or _scrub(name or "")
        action = _storable(asked)[:VALUE_CHARS]
        if len(asked) > VALUE_CHARS:
            log.info("audit: an action name of %d characters was asked; the record keeps the "
                     "first %d", len(asked), VALUE_CHARS)
        view = dict(kept) if kept is not None else _kept(action, params)
        project = _cut(_storable(_scrub(str(params.get("project") or ""))))
        return cls(
            record_id=uuid.uuid4().hex,
            actor_id=by.id,
            actor_display=by.display or by.id,
            provider=provider,
            via=by.via,
            action=action,
            params=_frozen(view),
            ok=outcome.ok,
            code=outcome.code,
            reason=str(outcome.data.get("reason", "") or ""),
            correlation_id=by.correlation,
            deployment=deployment(),
            project=project,
            product=product_of(project),
        )


def audit_path() -> Path:
    """The file `sink` keeps records in when the deployment declares no metrics store:
    `OPENFACTORY_METRICS_DB` when set, else `audit.db` beside `registry.yaml` — resolved as ADR-0049
    D5 resolves the board's file, so a host installation's `act`, `serve` and `openfactory audit`
    meet in the operator's directory, and never a file relative to wherever the shell stood."""
    if named := os.environ.get("OPENFACTORY_METRICS_DB", "").strip():
        return Path(named)
    from openfactory.registry import ProjectRegistry

    return ProjectRegistry().path.parent / AUDIT_FILE


#: The metrics sinks that keep no audit record: `null` keeps nothing, and `memory` keeps a row only
#: as long as the object it was handed to — the shipped builder makes a new one per call, so on
#: c310ba28 a `memory` deployment's store said True and the record was gone when the call
#: returned (PR #1039 review, 2026-10-21). Their records go to the fallback file (`sink`).
KEEPS_NO_RECORD = frozenset({"null", "memory"})


def sink() -> MetricsSink:
    """The store the records are written to and `openfactory audit` reads: ONE definition for
    both, because a writer and a reader that resolved their file apart is how a deployment came to
    write rows its own readers could not open (`registry.metrics_db_path`'s docstring).

    The deployment's metrics sink (`deployment_metrics_sink`) when it declares one that keeps a
    record; when it is `null` — a host CLI with no compose environment, the transport ADR-0039 §2
    says outranks every gate — or `memory`, a sqlite file at `audit_path()`, so every call still
    leaves a record. `memory` is said once per process at WARNING: an operator who chose it chose a
    store that keeps nothing, and learns here where the trail went instead. Built at each call,
    not at import, so the store the environment names now is the one written. `metrics_sink_kind`'s
    own inference is not changed: it decides where a deployment's cost dashboard reads."""
    from openfactory.observability.registry import deployment_metrics_sink, metrics_sink_kind

    kind = metrics_sink_kind()
    if kind not in KEEPS_NO_RECORD:
        return deployment_metrics_sink()
    from openfactory.observability.sqlite_metrics import SqliteMetricsSink

    where = _private(audit_path())
    if kind != "null" and _KEEPING.first_fallback(kind):
        log.warning("audit: OPENFACTORY_METRICS_SINK=%s keeps no audit record past the call that "
                    "wrote it, so this process keeps them in %s", kind, where)
    return SqliteMetricsSink(where)


def _private(path: Path) -> Path:
    """`path`, created readable and writable by its owner alone (`0600`) when it does not exist,
    and made so when it exists with wider bits — said once at INFO, naming the file and the mode
    it had; one this process cannot change is said at WARNING and used as it is.

    WHY. `SqliteMetricsSink` lets `sqlite3.connect` create its file, which under the usual umask
    `0022` is `0644`: on c310ba28 the fallback `audit.db`, who did what for a year, was readable by
    every account on the host (PR #1039 review, 2026-10-21). SQLite creates the `-wal` and `-shm`
    beside a database with the database's own mode, so they follow it. Only this fallback file:
    a deployment's own metrics store is the store's to set, and it already holds client messages
    (`kind="message"`) as text on `main`."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = os.open(path, os.O_RDONLY | os.O_CREAT, 0o600)
    except OSError as exc:  # the write that follows fails on the same cause, and says it
        log.info("audit: could not create %s as its owner's alone (%s)", path, exc)
        return path
    had = 0
    try:
        had = os.fstat(handle).st_mode & 0o777
        if had & 0o077:
            os.fchmod(handle, 0o600)
            log.info("audit: %s was mode %s, readable by others; it is now 0o600", path, oct(had))
    except OSError as exc:
        log.warning("audit: %s is mode %s, readable by others, and could not be made 0o600 (%s)",
                    path, oct(had), exc)
    finally:
        os.close(handle)
    return path


def metric_of(record: AuditRecord) -> MetricRecord:
    """`record` as one row of kind `audit`: under its project, or the deployment-wide key the
    people store uses when the call named none (#694 Q7); `ticket` its own record id, so the row's
    key `<ts>#<record_id>#<action>` is one no other record shares and no write replaces; `ts` the
    record's own, never a second read of the clock; `expires_at` that `ts` plus `AUDIT_KEPT_DAYS`,
    so the row is read for its period and not a day longer; and every field of the record in
    `extra`."""
    from datetime import datetime

    from openfactory.identity.people import PROJECT as DEPLOYMENT_KEY
    from openfactory.observability.metrics import MetricRecord

    extra = {f.name: getattr(record, f.name) for f in dataclasses.fields(record)}
    extra["params"] = _thawed(record.params)  # a store serialises a dict, not a read-only view
    return MetricRecord(kind="audit", project=record.project or DEPLOYMENT_KEY,
                        ticket=record.record_id, ts=record.ts, role=record.action,
                        expires_at=int(datetime.fromisoformat(record.ts).timestamp())
                        + AUDIT_KEPT_DAYS * 86_400,
                        extra=extra)


def _named(store: object) -> str:
    """How a WARNING names a store: its file (`SqliteMetricsSink.path`), else its table, else its
    class — the thing an operator goes and looks at."""
    for attr in ("path", "table"):
        if where := getattr(store, attr, None):
            return f"{type(store).__name__} at {where}"
    return type(store).__name__


class _Keeping:
    """What this process's audit writes came to, for readiness (`health`'s `audit` check): how
    many records were not kept since the process started, and why the last write did not land —
    `""` once one lands. Two numbers and a sentence, not a list: bounded whatever the traffic.

    WHY READINESS. On c310ba28 a record not kept was one WARNING line, and nothing a supervisor
    reads could tell a panel whose every action went unrecorded from one whose trail was whole
    (PR #1039 review, 2026-10-21). The deployment exposes no metrics endpoint, and a metric written
    to the store that just refused the record would be lost with it; `/readyz` is what the compose
    file's healthcheck asks every fifteen seconds and what `docker ps` shows as `unhealthy`. THE
    LAST WRITE, NOT EVERY WRITE SINCE START: a repaired store's next record makes the check pass
    again — a process no action reaches stays unready until one does, or it restarts.

    Written from worker threads (`write` runs `_keep` in `asyncio.to_thread`), so under a lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.not_kept = 0
        self.why = ""
        self._fell_back: set[str] = set()

    def kept(self) -> None:
        with self._lock:
            self.why = ""

    def lost(self, why: str) -> None:
        with self._lock:
            self.not_kept += 1
            self.why = why

    def read(self) -> tuple[int, str]:
        with self._lock:
            return self.not_kept, self.why

    def first_fallback(self, kind: str) -> bool:
        """True the first time this process sends `kind`'s records to the fallback file: at most
        one entry per sink kind in `KEEPS_NO_RECORD`."""
        with self._lock:
            if kind in self._fell_back:
                return False
            self._fell_back.add(kind)
            return True

    def forget(self) -> None:
        with self._lock:
            self.not_kept, self.why = 0, ""
            self._fell_back.clear()


_KEEPING = _Keeping()


def not_kept() -> tuple[int, str]:
    """`(records not kept since this process started, why the last write did not land)`; the
    second is `""` while the last write landed, or none was made."""
    return _KEEPING.read()


def lost(why: str) -> None:
    """Count one record not kept, and why — for `perform`, when no store could be built."""
    _KEEPING.lost(why)


def forget() -> None:
    """Drop what this process's writes came to. A seam for the suite."""
    _KEEPING.forget()


def _keep(record: AuditRecord) -> bool:
    """`write`'s body, on a worker thread: True only when the store took the row; a store that
    answered False or raised is said here, once, naming the action and the store, and counted
    (`not_kept`)."""
    row = metric_of(record)
    store = sink()
    try:
        landed = bool(store.record(row))
    except Exception as exc:  # noqa: BLE001 — said below and answered False; the call stands
        log.warning("audit: the record of %s by %s was not kept: %s raised (%s)",
                    printable(record.action), printable(record.actor_id), _named(store), exc)
        _KEEPING.lost(f"{_named(store)} raised ({exc})")
        return False
    if not landed:
        # A STORE'S False IS A WRITE THAT DID NOT LAND. The sqlite sink catches its own failures
        # and answers False (a locked or unopenable file), and its own line names a project and a
        # record id — not the action, not that it was the audit trail (#694: before this, that
        # answer was dropped and the action layer said nothing).
        log.warning("audit: the record of %s by %s was not kept: %s did not take it",
                    printable(record.action), printable(record.actor_id), _named(store))
        _KEEPING.lost(f"{_named(store)} did not take it")
        return False
    _KEEPING.kept()
    return True


async def write(record: AuditRecord) -> bool:
    """Write `record` to `sink()` as one row of kind `audit`; True only when the store says it
    landed. The one seam `actions.perform` writes through, once per call.

    OFF THE EVENT LOOP (`asyncio.to_thread`): the panel performs on its loop, and a sqlite write
    waits on the file's lock for up to its busy timeout — every other request would wait with it
    (the #748 lesson). A store that answers False or raises is said here at WARNING, naming the
    action and the store, and answered False; what fails before a store is reached (the sink
    cannot be built) is raised, and `perform` says it at WARNING. Either way the outcome stands,
    and the record not kept is counted for readiness (`not_kept`)."""
    return await asyncio.to_thread(_keep, record)
