"""Rows past their period are deleted, not only hidden, each time the worker or the panel starts
(#694, #1027, PR #1039 review).

WHAT WAS TRUE BEFORE. `SqliteMetricsSink.purge_expired` deletes the rows whose `expires_at` has
passed, and nothing in the tree called it: `git grep purge_expired -- openfactory/` found its
definition and nothing else (#1027). So a sqlite store hid an expired row on read and kept its
bytes for ever — an audit record past its 365 days, a client's message past ADR-0024's period.

WHAT HOLDS NOW: `observability.retention.purge_expired` deletes them from every store this
process keeps rows in — the deployment's metrics store and the audit fallback file — at most
`PURGE_BOUND` rows a store per run, said at INFO with the count and when the bound was hit; the
worker runs it as it starts and `openfactory serve` before it serves.
"""

from __future__ import annotations

import ast
import inspect
import logging
import time

import pytest
from typer.testing import CliRunner

from openfactory.observability.metrics import MetricRecord
from openfactory.observability.sqlite_metrics import SqliteMetricsSink


@pytest.fixture
def store(tmp_path, monkeypatch) -> SqliteMetricsSink:
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(tmp_path / "metrics.db"))
    return SqliteMetricsSink(tmp_path / "metrics.db")


def _rows(sink: SqliteMetricsSink, *expires: int | None) -> None:
    for i, at in enumerate(expires):
        assert sink.record(MetricRecord(kind="message", project="acme", ticket=str(i),
                                        ts=f"2026-10-21T10:00:0{i}+00:00", expires_at=at))


def _bytes_left(sink: SqliteMetricsSink) -> int:
    import sqlite3

    with sqlite3.connect(sink.path) as conn:
        count = conn.execute("SELECT count(*) FROM metrics").fetchone()[0]
    conn.close()
    return count


def _serve(monkeypatch) -> None:
    """`openfactory serve`, up to the moment it would hand the process to uvicorn."""
    import uvicorn

    from openfactory.cli import app

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    done = CliRunner().invoke(app, ["serve", "--port", "18999"])
    assert done.exit_code == 0, done.output


def test_an_expired_row_is_deleted_and_one_in_its_period_is_kept(store, caplog, monkeypatch):
    """#1027: one row past its period, one inside it, one with none. Starting the panel deletes
    the first from the file — not only from reads — keeps the other two, and says it at INFO
    naming the store. On 362e77aa all three were still in the file."""
    now = int(time.time())
    _rows(store, now - 60, now + 86_400, None)

    with caplog.at_level(logging.INFO):
        _serve(monkeypatch)

    assert _bytes_left(store) == 2, "the expired row is still in the file"
    said = [r.getMessage() for r in caplog.records if "expired" in r.getMessage()]
    assert said and str(store.path) in said[0], said


def test_the_purge_is_bounded_and_says_when_the_bound_was_hit(store, caplog, monkeypatch):
    """A store with more expired rows than the bound (10,000) loses that many this start, and the
    line says more remain — a start never holds the store's lock for an unbounded delete. On
    362e77aa none was deleted."""
    import json
    import sqlite3

    _rows(store, None)
    expired = int(time.time()) - 60
    with sqlite3.connect(store.path) as conn:
        conn.executemany(
            "INSERT INTO metrics (pk, sk, kind, ts, ticket, expires_at, data) VALUES (?,?,?,?,?,?,?)",
            [("acme", f"x#{i}", "message", "2026-10-21", str(i), expired, json.dumps({}))
             for i in range(10_001)])
    conn.close()

    with caplog.at_level(logging.INFO):
        _serve(monkeypatch)

    assert _bytes_left(store) == 2, _bytes_left(store)
    assert [r for r in caplog.records if "more remain" in r.getMessage()], caplog.text


def test_the_worker_purges_as_it_starts():
    """Reachability, read off `worker.main`: it calls `retention.purge_expired`."""
    from openfactory.runtime.temporal import worker

    calls = [n for n in ast.walk(ast.parse(inspect.getsource(worker.main)))
             if isinstance(n, ast.Call)]
    assert [n for n in calls if getattr(n.func, "attr", "") == "purge_expired"
            or getattr(n.func, "id", "") == "purge_expired"
            or any(getattr(a, "attr", "") == "purge_expired" for a in n.args)], (
        "the worker never purges")
