"""Who asked for what, and what came of it: one typed, immutable record per call into the action
layer (#694).

WHY A RECORD AND NOT ONLY THE LINE. `actions.perform` is the one gate every transport goes
through, and until #694 its only trace of who asked was one INFO line. Eight of its nine ways out
never wrote it, and nothing kept it: measured on bb929e49 with an empty `HOME` and a temp registry,
`openfactory act product_status -p nosuch` printed only the refusal and the `action=… by=…` line
reached nobody. *Who approved that production release* had no answer an auditor could read back.
The record is that answer, as a value: the line stays beside it (ADR-0039 §2).

ONE REDACTION FOR BOTH. `redact` is the function the log line uses too (`actions._loggable` is
its alias), so a parameter that is masked in one is masked in the other — there is no second
list of secrets to forget to update.

WHERE IT IS KEPT. `write` hands each record to `sink()` as one row of kind `audit` in the metrics
store, off the event loop; a deployment that declares no store keeps them in `audit.db` beside
`registry.yaml`. A person's words are kept as their length and digest, never as text (ADR-0024),
and every other value is bounded.

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
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from openfactory.observability.events import now_iso

if TYPE_CHECKING:
    from openfactory.actions.base import Actor, Outcome
    from openfactory.observability.metrics import MetricRecord, MetricsSink

log = logging.getLogger(__name__)

#: Parameters whose VALUE must never reach a log line or an audit record. `approve_prod` and
#: `promote` take the approver's password, and `perform` writes its line and its record on every
#: call including the refusals — which is precisely the path a wrong password takes. Read by
#: `redact`, which both the line (`actions._loggable`) and the record (`AuditRecord.of`) call.
SECRET = frozenset({"password", "token", "secret", "key"})

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

#: The variable an operator names a deployment by, for the records it writes.
DEPLOYMENT_ENV = "OPENFACTORY_DEPLOYMENT"

#: The most characters of one parameter's value a record keeps (#694 Q11). A value is whatever the
#: caller sent, and a refused call is recorded as faithfully as a kept one, so without a bound one
#: caller could write a row of any size per call into a store kept for a year. Two thousand holds
#: every URL, ref and name the catalog takes; what is cut is said in the value and in the log.
VALUE_CHARS = 2_000

#: How long a record is read, in days (#694 Q3): who did what, when, and on which deployment is
#: a question a security review asks of the last year, not forever — the precedent of the board's
#: own audit line, `adapters/tracker/local.py` `_REMOVED_KEPT_DAYS` (365, #384). Carried by each
#: row as `expires_at`, which the sqlite store hides on read (its bytes stay until
#: `purge_expired` runs, and nothing in this tree runs it yet) and which a store that deletes by
#: a TTL on that field deletes — so the period is the record's own, in every store.
#: Stated with its value in `docs/rotation-and-retention.md`; change both together.
AUDIT_KEPT_DAYS = 365

#: The file the records go to on a deployment that declares no metrics store (`null`, a host CLI
#: with no compose environment), beside `registry.yaml` — see `sink`.
AUDIT_FILE = "audit.db"


def deployment() -> str:
    """Which deployment this process is: `OPENFACTORY_DEPLOYMENT` when set, else the Temporal
    namespace the engine connection uses (`TEMPORAL_NAMESPACE`, `default` when unset).

    No deployment identifier existed before #694 (`OPENFACTORY_PLATFORM_NAME` is branding, not an
    identity), and the namespace is the one name two deployments sharing a Temporal account cannot
    share. It is read from the environment exactly as `runtime.temporal.connection.namespace()`
    reads it rather than by calling it: that module imports `temporalio` at its top, and the panel
    makes a record on every action without the `runtime` extra. The two are held equal by
    `tests/test_every_action_leaves_one_audit_record.py`."""
    named = os.environ.get(DEPLOYMENT_ENV, "").strip()
    return named or os.environ.get("TEMPORAL_NAMESPACE", "default")


def redact(params: Mapping[str, object]) -> dict[str, object]:
    """`params` with the value of every `SECRET` name replaced by `MASK`; the names stay, so the
    line and the record still say that a password was given."""
    return {k: (MASK if k in SECRET else v) for k, v in params.items()}


def _words(value: object) -> dict[str, object]:
    """A person's words as the record keeps them: how many characters, and their sha256 — that and
    when they spoke, never what they said (`actions.base.FREE_TEXT`)."""
    text = str(value)
    return {"chars": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def _kept(action: str, params: Mapping[str, object]) -> dict[str, object]:
    """`params` as a record keeps them: `SECRET` values masked (`redact`, the line's own function),
    each `FREE_TEXT` value as its length and digest, and every other value cut to `VALUE_CHARS`
    with the cut said — in the value, and in one INFO line naming the action and the parameter."""
    from openfactory.actions.base import FREE_TEXT

    kept: dict[str, object] = {}
    for name, value in redact(params).items():
        if name in FREE_TEXT and name not in SECRET and value is not None:
            kept[name] = _words(value)
            continue
        text = value if isinstance(value, str) else str(value)
        if len(text) <= VALUE_CHARS:
            kept[name] = value
            continue
        cut = len(text) - VALUE_CHARS
        kept[name] = f"{text[:VALUE_CHARS]}… [{cut} more characters not kept]"
        log.info("audit: %s's %s was %d characters; the record keeps the first %d", action, name,
                 len(text), VALUE_CHARS)
    return kept


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
    #: The action as `perform` resolved it (lower-cased, stripped), or as asked when no row has it.
    action: str
    #: What was passed, as `_kept` keeps it: every `SECRET` value masked by `redact`, a person's
    #: words (`actions.base.FREE_TEXT`) as `{"chars", "sha256"}`, other values cut to `VALUE_CHARS`.
    #: Read-only.
    params: Mapping[str, object]
    ok: bool
    #: `Outcome.code` (one of `actions.CODES`), and the refusal's `reason` (`""` when it worked).
    code: str
    reason: str
    #: The id that ties this call to the request that caused it and to what it caused
    #: (`Actor.correlation`); `""` when the transport carried none.
    correlation_id: str
    #: Which deployment wrote the record (`deployment()`): the operator's name for it, else the
    #: engine's namespace.
    deployment: str
    #: The `project` parameter as passed (`""` when the action takes none), and its product.
    project: str
    product: str
    #: When, ISO-8601 in UTC.
    ts: str = field(default_factory=now_iso)

    @classmethod
    def of(cls, name: str, by: Actor, params: Mapping[str, object], outcome: Outcome, *,
           product_of: Callable[[str], str] = _product_of) -> AuditRecord:
        """The record of one `perform(name, by=by, **params)` that returned `outcome`."""
        from openfactory.actions.base import SYSTEM

        # ADR-0057 D1 names the factory's own actor `system`; it acts on nobody's behalf, so it
        # carries no subject and the name is written here rather than invented on `Actor`.
        provider = "system" if by is SYSTEM else (by.subject.via if by.subject else "")
        project = str(params.get("project") or "")
        action = (name or "").strip().lower() or name
        return cls(
            record_id=uuid.uuid4().hex,
            actor_id=by.id,
            actor_display=by.display or by.id,
            provider=provider,
            via=by.via,
            action=action,
            params=MappingProxyType(_kept(action, params)),
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


def sink() -> MetricsSink:
    """The store the records are written to and `openfactory audit` reads: ONE definition for
    both, because a writer and a reader that resolved their file apart is how a deployment came to
    write rows its own readers could not open (`registry.metrics_db_path`'s docstring).

    The deployment's metrics sink (`deployment_metrics_sink`) when it declares one; when it is
    `null` — a host CLI with no compose environment, the transport ADR-0039 §2 says outranks every
    gate — a sqlite file at `audit_path()`, so every call still leaves a record. Built at each call,
    not at import, so the store the environment names now is the one written. `metrics_sink_kind`'s
    own inference is not changed: it decides where a deployment's cost dashboard reads."""
    from openfactory.observability.registry import deployment_metrics_sink, metrics_sink_kind

    if metrics_sink_kind() != "null":
        return deployment_metrics_sink()
    from openfactory.observability.sqlite_metrics import SqliteMetricsSink

    return SqliteMetricsSink(audit_path())


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
    extra["params"] = dict(record.params)  # a store serialises a dict, not a read-only view
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


def _keep(record: AuditRecord) -> bool:
    """`write`'s body, on a worker thread: True only when the store took the row; a store that
    answered False or raised is said here, once, naming the action and the store."""
    row = metric_of(record)
    store = sink()
    try:
        landed = bool(store.record(row))
    except Exception as exc:  # noqa: BLE001 — said below and answered False; the call stands
        log.warning("audit: the record of %s by %s was not kept: %s raised (%s)", record.action,
                    record.actor_id, _named(store), exc)
        return False
    if not landed:
        # A STORE'S False IS A WRITE THAT DID NOT LAND. The sqlite sink catches its own failures
        # and answers False (a locked or unopenable file), and its own line names a project and a
        # record id — not the action, not that it was the audit trail (#694: before this, that
        # answer was dropped and the action layer said nothing).
        log.warning("audit: the record of %s by %s was not kept: %s did not take it",
                    record.action, record.actor_id, _named(store))
    return landed


async def write(record: AuditRecord) -> bool:
    """Write `record` to `sink()` as one row of kind `audit`; True only when the store says it
    landed. The one seam `actions.perform` writes through, once per call.

    OFF THE EVENT LOOP (`asyncio.to_thread`): the panel performs on its loop, and a sqlite write
    waits on the file's lock for up to its busy timeout — every other request would wait with it
    (the #748 lesson). A store that answers False or raises is said here at WARNING, naming the
    action and the store, and answered False; what fails before a store is reached (the sink
    cannot be built) is raised, and `perform` says it at WARNING. Either way the outcome stands."""
    return await asyncio.to_thread(_keep, record)
