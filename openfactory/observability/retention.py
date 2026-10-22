"""Rows past their period are deleted, not only hidden (#1027, #694).

A sqlite metrics store hides a row whose `expires_at` has passed on every read, and keeps its
bytes until `SqliteMetricsSink.purge_expired` runs — and on the #694 branch nothing called it, so
an audit record past its 365 days and a client's message past ADR-0024's period stayed in the
file for ever (PR #1039 review, hermesfelipe; `git grep purge_expired -- openfactory/` found the
definition alone).

`purge_expired` here runs it on every store this process keeps rows in: the deployment's metrics
store, and the audit fallback file when the deployment declares none (`audit.sink`). The worker
calls it as it starts and `openfactory serve` before it serves — the two processes that start
on every deployment, compose or host. BOUNDED: at most `PURGE_BOUND` rows a store per run, so a
start never holds the store's lock for an unbounded delete; a bound hit is said, and the next
start deletes the next. A store that deletes by a TTL of its own (the DynamoDB add-on) has no
`purge_expired` and is left to it. Never raises: a purge that fails is said at WARNING by the
store, and the process starts.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

#: The most rows one run deletes from one store. Ten thousand rows of the sqlite store go in well
#: under a second; a store further behind than that catches up one start at a time.
PURGE_BOUND = 10_000


def _stores() -> list[object]:
    """The stores this process keeps rows in, each once: the deployment's metrics sink and the
    audit's (`audit.sink`), which is the same one unless the deployment declares none."""
    from openfactory.observability import audit
    from openfactory.observability.registry import deployment_metrics_sink

    found: list[object] = []
    for build in (deployment_metrics_sink, audit.sink):
        try:
            store = build()
        except Exception as exc:  # noqa: BLE001 — a store that cannot be built is said, not raised
            log.warning("retention: a store could not be built, so its expired rows stay (%s)",
                        exc)
            continue
        where = getattr(store, "path", None) or getattr(store, "table", None) or id(store)
        if all((getattr(s, "path", None) or getattr(s, "table", None) or id(s)) != where
               for s in found):
            found.append(store)
    return found


def purge_expired() -> list[str]:
    """Delete the rows past their period from every store this process keeps rows in, at most
    `PURGE_BOUND` from each; say each store's count at INFO, and when the bound was hit. Returns
    the sentences said."""
    from openfactory.observability.audit import _named

    said: list[str] = []
    for store in _stores():
        purge = getattr(store, "purge_expired", None)
        if not callable(purge):
            continue
        gone = purge(limit=PURGE_BOUND)
        line = f"retention: {gone} expired rows deleted from {_named(store)}"
        if gone >= PURGE_BOUND:
            line += f"; more remain, and the next start deletes up to {PURGE_BOUND} more"
        log.info("%s", line)
        said.append(line)
    return said
