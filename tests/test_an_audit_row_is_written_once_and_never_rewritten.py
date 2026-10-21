"""An audit row is written once and never rewritten in the sqlite store (#694, PR #1039 review,
hermesfelipe's follow-up: no tamper evidence).

WHAT WAS TRUE BEFORE. An audit row shared the metrics table's `INSERT OR REPLACE`. Measured on
the #694 branch (2026-10-21, a scratch store): an `approve_prod` record by `alice` was written,
a second `record()` of a row with its key and `actor_id="mallory"` answered True and left one
row, now saying `mallory`, and a plain `UPDATE` then made it `eve` — neither left a trace.

WHAT HOLDS NOW: the sqlite store writes a row of kind `audit` with a plain `INSERT`, so a second
write under its key is refused (False, said) and the first stands; and a trigger refuses any
`UPDATE` of an audit row. Every other kind still replaces on its key, as a retried telemetry
write must. What this does not give is evidence against someone who can write the file and drop
the trigger: that needs a hash chain or a signature, a decision left to the maintainers.
"""

from __future__ import annotations

import sqlite3

import pytest

from openfactory import actions
from openfactory.observability import audit
from openfactory.observability.metrics import MetricRecord
from openfactory.observability.sqlite_metrics import SqliteMetricsSink


@pytest.fixture
def written(tmp_path):
    """A sqlite store holding one `approve_prod` record by alice, and that record's row."""
    sink = SqliteMetricsSink(tmp_path / "metrics.db")
    record = audit.AuditRecord.of("approve_prod", actions.Actor(id="alice", via="panel"),
                                  {"project": "acme", "issue": "7"}, actions.done("approved"),
                                  product_of=lambda _name: "")
    row = audit.metric_of(record)
    assert sink.record(row)
    return sink, row


def _actors(sink: SqliteMetricsSink) -> list[str]:
    return [r["extra"]["actor_id"] for r in sink.scan() if r.get("kind") == "audit"]


def test_a_second_write_under_an_audit_rows_key_is_refused_and_the_first_stands(written):
    """The review's first measurement: the same key with another actor is refused (False) and
    the row still says alice. On 98b1b59f the second write answered True and the row said
    mallory."""
    sink, row = written
    forged = row.model_copy(update={"extra": {**row.extra, "actor_id": "mallory"}})

    assert sink.record(forged) is False
    assert _actors(sink) == ["alice"]


def test_an_audit_row_cannot_be_updated_in_the_file(written):
    """The review's second measurement: a plain `UPDATE` of an audit row is refused by the store
    itself. On 98b1b59f it made the row say `eve`."""
    sink, _row = written

    with sqlite3.connect(sink.path) as conn, pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE metrics SET data = replace(data, 'alice', 'eve') "
                     "WHERE kind = 'audit'")
    assert _actors(sink) == ["alice"]


def test_any_other_kind_still_replaces_its_row_on_a_retried_write(tmp_path):
    """The store's promise for telemetry stands: a retried write of a job's cost under its key
    replaces the row rather than counting twice (`sqlite_metrics`'s docstring)."""
    sink = SqliteMetricsSink(tmp_path / "metrics.db")
    first = MetricRecord(kind="agent_run", project="acme", ticket="7", ts="2026-10-21T10:00:00",
                         role="dev", cost_usd=1.0)

    assert sink.record(first) and sink.record(first.model_copy(update={"cost_usd": 2.0}))
    assert [r["cost_usd"] for r in sink.scan()] == [2.0]
