"""The audit rows in the metrics store do not weigh on the readers that scan it, nor change what
they read (#694, PR #1039 review N2).

WHAT WAS TRUE BEFORE. Every full read of the metrics store — the cost dashboard, the worker's
watch, sweep and repoint reads, `openfactory autonomy`, the outcome aggregates, the knowledge
experiment, all through `metrics_view.scan_records`/`scan_all_or_raise` or `query._store_rows` —
parsed every row and filtered by kind afterwards, and since #694 one row is written per action
call and kept for a year (one opening of the product page posts five). Measured by the review on
c310ba28: `cost_dashboard(project="books")` took 0.002 s over 50 cost rows and 9.99 s with
100,000 audit rows beside them.

WHAT HOLDS NOW: those reads ask the store for every kind but `audit` (`metrics.SCANNED_APART`),
which the sqlite store answers without parsing an audit row (`KindExcludingSink.scan_except`); a
store without the capability is scanned and the audit rows dropped, so what the readers get is
the same either way. `openfactory audit` reads the audit rows by their kind, apart.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

import pytest

from openfactory import actions
from openfactory.observability.metrics import MetricRecord
from openfactory.observability.sqlite_metrics import SqliteMetricsSink

NOW = datetime.now(UTC).replace(microsecond=0).isoformat()


def _written(db, records) -> None:
    """Each record written as `SqliteMetricsSink.record` writes it, in one transaction."""
    SqliteMetricsSink(db).record(MetricRecord(kind="job", project="books", ticket="0", ts=NOW))
    rows = []
    for rec in records:
        key = rec.dynamo_key()
        rows.append((key["pk"], key["sk"], rec.kind, rec.ts, rec.ticket, rec.expires_at,
                     json.dumps({**rec.model_dump(), **key}, default=str)))
    with sqlite3.connect(db) as conn:
        conn.executemany("INSERT INTO metrics (pk, sk, kind, ts, ticket, expires_at, data)"
                         " VALUES (?,?,?,?,?,?,?)", rows)
    conn.close()


def _audit_rows(count: int):
    from openfactory.observability import audit

    for _ in range(count):
        record = audit.AuditRecord.of("product_status", actions.SYSTEM, {"project": "books"},
                                      actions.done("fine"), product_of=lambda _name: "")
        yield audit.metric_of(record)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A sqlite deployment holding one job row, two cost rows of `books` and 50 audit rows."""
    db = tmp_path / "metrics.db"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(db))
    cost = [MetricRecord(kind="agent_run", project="books", ticket=str(i), ts=NOW, role="dev",
                         cost_usd=0.5) for i in range(2)]
    _written(db, [*cost, *_audit_rows(50)])
    return db


@pytest.fixture
def parsed(monkeypatch) -> list[int]:
    """How many rows the sqlite store turned into a dict: every row a reader holds passes
    through `SqliteMetricsSink._row`."""
    count = [0]
    real = SqliteMetricsSink._row

    def counted(data: str) -> dict:
        count[0] += 1
        return real(data)

    monkeypatch.setattr(SqliteMetricsSink, "_row", staticmethod(counted))
    return count


def test_the_cost_dashboard_parses_no_audit_row(store, parsed):
    """The review's measurement, in rows: the dashboard over one job, two cost rows and 50 audit
    rows parses the three, not 53. On c310ba28 it parsed 53."""
    from openfactory.api.metrics_view import cost_dashboard

    payload = cost_dashboard(project="books")

    assert payload["project"] == "books", payload["projects"]
    assert parsed[0] == 3, f"{parsed[0]} rows parsed for three that are not audit rows"


def test_a_full_scan_of_the_store_hands_its_readers_no_audit_row(store):
    """What every scanning reader gets (`scan_records`, `scan_all_or_raise`): the store's rows
    of every other kind, and no audit row. On c310ba28 it was 53 rows, 50 of them `audit`."""
    from openfactory.api.metrics_view import scan_all_or_raise, scan_records

    for rows in (scan_records(), scan_all_or_raise(), scan_all_or_raise(must_answer=True)):
        assert sorted(r["kind"] for r in rows) == ["agent_run", "agent_run", "job"], rows


def test_the_outcome_aggregates_read_no_audit_row(store, parsed):
    """`query._store_rows`, the outcome aggregates' one read, reads the project's rows of every
    kind but `audit`. On c310ba28: all 53, parsed."""
    from openfactory.observability.query import _store_rows

    rows, gap = _store_rows(["books"])

    assert gap == "" and sorted(r["kind"] for r in rows) == ["agent_run", "agent_run", "job"]
    assert parsed[0] == 3, parsed[0]


def test_a_store_that_cannot_leave_a_kind_out_is_scanned_and_its_audit_rows_dropped(
        store, monkeypatch):
    """`KindExcludingSink` is optional: a store that only scans (an add-on's) is read through
    `scan`, and the audit rows are dropped here, so its readers get what the sqlite store's get.
    On c310ba28 they got the audit rows too."""
    from openfactory.api.metrics_view import scan_records
    from openfactory.observability import registry as sinks

    class _ScanOnly:
        def __init__(self, path):
            self._inner = SqliteMetricsSink(path)

        def record(self, rec) -> bool:
            return self._inner.record(rec)

        def scan(self) -> list[dict]:
            return self._inner.scan()

        def records_of_kind(self, project, kind, *, limit=500) -> list[dict]:
            return self._inner.records_of_kind(project, kind, limit=limit)

    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "scan_only")
    monkeypatch.setitem(sinks.METRICS_SINKS, "scan_only", lambda **_kw: _ScanOnly(store))

    assert sorted(r["kind"] for r in scan_records()) == ["agent_run", "agent_run", "job"]
