"""The record of each call into the action layer is kept in the deployment's metrics store, under a
kind of its own, one row per call, with nothing secret in the file (#694).

WHAT WAS TRUE BEFORE. `actions.perform` left nothing durable: its one trace of who asked was an INFO
line, and on a sqlite deployment (`OPENFACTORY_METRICS_SINK=sqlite`, what the compose file sets on
the worker and the panel) the store held 0 rows of kind `audit` after any call — `audit` was not a
`MetricKind` at all. Measured on bb929e49 with an empty `HOME`: `openfactory act product_status -p
nosuch` printed the refusal and kept nothing an auditor could read back.

WHAT HOLDS NOW, in this file, read off the sqlite file itself rather than a mock: a call leaves one
row of kind `audit` under its project; two records made in the same instant are two rows (the
store's `INSERT OR REPLACE` on `<ts>#<ticket>#<role>` would otherwise keep one); a password passed
to the action is masked in the row and its bytes are in neither the database nor its `-wal`; and
the INFO line is still written, once per call, beside the row; and a row is read for
`audit.AUDIT_KEPT_DAYS` and not a day longer, the period stated with its value on the page that
states every other retention.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from openfactory import actions
from openfactory.observability.sqlite_metrics import SqliteMetricsSink


@pytest.fixture
def store(tmp_path, monkeypatch) -> SqliteMetricsSink:
    """A sqlite deployment, named as an operator names one: `OPENFACTORY_METRICS_SINK=sqlite` and
    the file in `OPENFACTORY_METRICS_DB`, with a registry of its own. The sink returned is a second
    handle on the same file — what the test reads is what `perform` wrote there, not a copy."""
    db = tmp_path / "metrics.db"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(db))
    return SqliteMetricsSink(db)


def _audit_rows(store: SqliteMetricsSink) -> list[dict]:
    """Every live row of kind `audit` in the file, whichever key it is under."""
    return [row for row in store.scan() if row.get("kind") == "audit"]


async def test_an_action_on_a_sqlite_deployment_leaves_a_row_of_kind_audit(store):
    """Criterion 3, "the local default sink writes audit records to the metrics store under their
    own kind": one real `perform` — a person asking for the status of a project nobody registered,
    refused by the row — leaves one row of kind `audit` under that project, saying who asked and
    what they were told. Before #694 the file held 0 such rows."""
    by = actions.Actor(id="alice", display="Alice Ferreira", via="panel")

    outcome = await actions.perform("product_status", by=by, project="nosuch")

    assert not outcome.ok and outcome.data.get("reason") == actions.NOT_FOUND, outcome
    rows = store.records_of_kind("nosuch", "audit")
    assert len(rows) == 1, f"{len(rows)} rows of kind audit for one call (1 expected)"
    [row] = rows
    assert (row["extra"]["action"], row["extra"]["actor_id"], row["extra"]["ok"],
            row["extra"]["reason"]) == ("product_status", "alice", False, actions.NOT_FOUND), row


async def test_two_records_in_the_same_instant_are_both_kept(store, monkeypatch):
    """Criterion 3, "append-only": the sqlite sink writes `INSERT OR REPLACE` on `sk =
    <ts>#<ticket>#<role|kind>` (`sqlite_metrics.py`), so two records that shared a time and a key
    would leave one row and lose the other without a word. With the clock stopped, two calls of the
    same action by the same person are two rows, at one `ts`."""
    from openfactory.observability import events

    instant = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)

    class _Stopped(datetime):
        @classmethod
        def now(cls, tz=None):  # every `now_iso()` reads this one instant
            return instant

    monkeypatch.setattr(events, "datetime", _Stopped)
    by = actions.Actor(id="alice", via="panel")

    for _ in range(2):
        await actions.perform("product_status", by=by, project="nosuch")

    rows = store.records_of_kind("nosuch", "audit")
    assert len(rows) == 2, f"{len(rows)} rows for two calls in one instant (2 expected)"
    assert {row["ts"] for row in rows} == {instant.isoformat()}, rows  # the clock did stop


async def test_a_password_reaches_neither_the_record_nor_the_store_file(store):
    """Criterion 6, "secrets are redacted in the record as they are in the line": `approve_prod`
    takes the approver's password, and a refused call — the path a wrong password takes — is still
    recorded. The row says a password was given (`***`), and the password's bytes are nowhere in
    the database file or its write-ahead log, where an uncheckpointed row lives. Before #694 there
    was no row, so nothing here could be read back at all."""
    secret = "hunter2"

    await actions.perform("approve_prod", by=actions.SYSTEM, project="nosuch", issue="1",
                          version="1.0.0", approver="alice", password=secret)

    rows = store.records_of_kind("nosuch", "audit")
    assert [row["extra"]["action"] for row in rows] == ["approve_prod"], rows
    assert rows[0]["extra"]["params"]["password"] == "***", rows[0]["extra"]["params"]
    files = [p for p in (store.path, store.path.with_name(store.path.name + "-wal")) if p.exists()]
    assert store.path in files, files
    leaked = [p.name for p in files if secret.encode() in p.read_bytes()]
    assert not leaked, f"the password is in {leaked}"


async def test_the_info_line_is_still_written_beside_the_record(store, caplog):
    """Criterion 6, "the INFO log line stays": the record does not replace the line. Each call —
    an unknown action, and a row's refusal — writes exactly one `action=<name> by=` line at INFO
    and leaves exactly one row of kind `audit`. Before #694 the unknown action wrote no line, and
    neither call left a row."""
    by = actions.Actor(id="alice", via="panel")
    calls = [("teleport", {}), ("product_status", {"project": "nosuch"})]

    with caplog.at_level("INFO", logger="openfactory.actions"):
        for name, params in calls:
            await actions.perform(name, by=by, **params)

    lines = [r.getMessage() for r in caplog.records
             if r.levelname == "INFO" and r.getMessage().startswith("action=")]
    assert [line.split()[0] for line in lines] == [f"action={name}" for name, _ in calls], lines
    assert all(" by=" in line for line in lines), lines
    rows = _audit_rows(store)
    assert sorted(row["extra"]["action"] for row in rows) == sorted(n for n, _ in calls), rows


# ── how long a record is kept, and where that is said ───────────────────────────────────────────

_DAY = 24 * 60 * 60


async def test_a_record_is_still_read_the_day_before_its_period_ends_and_not_after(store,
                                                                                    monkeypatch):
    """Criterion 3, "they survive the store's retention rules for a documented period": a record
    written at a known instant is read back on the last day of `audit.AUDIT_KEPT_DAYS` and is
    gone the day after; a purge run on that last day deletes none of it. The store honours a row's
    `expires_at` on every read (`sqlite_metrics.py`), so the period is the one the record carries.
    Before #694 there was no period at all: `AUDIT_KEPT_DAYS` did not exist, and the store held no
    row of kind `audit` to keep or to expire."""
    from openfactory.observability import events, sqlite_metrics
    from openfactory.observability.audit import AUDIT_KEPT_DAYS

    instant = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)

    class _Stopped(datetime):
        @classmethod
        def now(cls, tz=None):  # the record's `ts` is this instant
            return instant

    monkeypatch.setattr(events, "datetime", _Stopped)
    await actions.perform("product_status", by=actions.Actor(id="alice", via="panel"),
                          project="nosuch")
    written = int(instant.timestamp())
    last_day = written + AUDIT_KEPT_DAYS * _DAY - _DAY
    day_after = written + AUDIT_KEPT_DAYS * _DAY + _DAY

    monkeypatch.setattr(sqlite_metrics.time, "time", lambda: last_day)
    assert len(store.records_of_kind("nosuch", "audit")) == 1, (
        f"a record written {AUDIT_KEPT_DAYS - 1} days ago is no longer read "
        f"(its period is {AUDIT_KEPT_DAYS} days)")
    assert store.purge_expired(now=last_day) == 0, (
        "a purge on the last day of the period deleted a record still inside it")

    monkeypatch.setattr(sqlite_metrics.time, "time", lambda: day_after)
    assert store.records_of_kind("nosuch", "audit") == [], (
        f"a record written {AUDIT_KEPT_DAYS + 1} days ago is still read "
        f"(its period is {AUDIT_KEPT_DAYS} days)")


def test_the_period_is_stated_where_the_other_retentions_are():
    """Criterion 3, "a documented period": `docs/rotation-and-retention.md` is the page that says
    how long everything this tree keeps is kept, and a person asking how long the record of who
    did what lasts must find `AUDIT_KEPT_DAYS` there with its value. Before #694 the page named no
    audit record, and the constant did not exist."""
    from pathlib import Path

    from openfactory.observability.audit import AUDIT_KEPT_DAYS

    doc = Path(__file__).resolve().parents[1] / "docs" / "rotation-and-retention.md"
    lines = doc.read_text(encoding="utf-8").splitlines()

    # THE CONSTANT AND ITS VALUE ON ONE LINE, as the conversation's retention is guarded
    # (`test_a_staged_decision_survives_a_refresh.py`): checked apart, the name in the "where it
    # lives" list and the number anywhere else on the page would pass while the period read "a
    # while".
    assert any("AUDIT_KEPT_DAYS" in ln and str(AUDIT_KEPT_DAYS) in ln for ln in lines), (
        f"AUDIT_KEPT_DAYS is not documented with its value ({AUDIT_KEPT_DAYS}) in {doc.name}")
