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

NO ENGINE AT IMPORT. This module is imported by `openfactory.actions`, which the panel imports;
the panel serves without the `runtime` extra (`tests/test_the_panel_serves_without_the_engines_
client.py`), so nothing here imports `temporalio` or `openfactory.runtime` at module level.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from openfactory.observability.events import now_iso

if TYPE_CHECKING:
    from openfactory.actions.base import Actor, Outcome

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
    #: What was passed, with every `SECRET` value masked by `redact`. Read-only.
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
        return cls(
            record_id=uuid.uuid4().hex,
            actor_id=by.id,
            actor_display=by.display or by.id,
            provider=provider,
            via=by.via,
            action=(name or "").strip().lower() or name,
            params=MappingProxyType(redact(params)),
            ok=outcome.ok,
            code=outcome.code,
            reason=str(outcome.data.get("reason", "") or ""),
            correlation_id=by.correlation,
            deployment=deployment(),
            project=project,
            product=product_of(project),
        )


async def write(record: AuditRecord) -> bool:
    """Hand `record` to the deployment's store; True only when it was kept.

    The one seam `actions.perform` writes through, once per call. The store does not know the
    record's kind yet (`MetricKind` has no `audit`), so nothing is kept and this answers False —
    said at DEBUG rather than WARNING, because it is every call, not a store that refused one."""
    log.debug("audit: no store keeps action records yet; %s by %s not kept", record.action,
              record.actor_id)
    return False
