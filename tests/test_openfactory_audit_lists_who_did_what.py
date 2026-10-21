"""`openfactory audit` lists the action layer's records by who asked, what they asked for, on which
project, what came of it and when (#694).

WHAT WAS TRUE BEFORE. Every call into `actions.perform` now leaves one row of kind `audit` in the
deployment's store, and nothing could read one back short of opening the sqlite file by hand: on
62db04c5 `openfactory audit` answered `No such command 'audit'` and exited 2. "Who approved that
production release" had a row and no reader.

WHAT HOLDS NOW, in this file, against rows the real `perform` wrote (two people, three actions, two
projects, two that worked and two refused, two days apart): the command lists them by actor, by
action, by project, by outcome — `ok`, `refused`, or the refusal's own code or reason — and by a
period of UTC dates, each record once, one line per record and oldest first; `--json` prints the
records' own fields. It reads the store the records were written to (`audit.sink()`, the one
definition the write uses), so a host CLI with no store named finds them in `audit.db` beside
`registry.yaml`. A store it cannot read exits 2 naming it, a sink that keeps nothing it can read
back exits 2 naming the sink, and an empty store says it is empty — three answers, never one
empty list for all of them. A list cut at `--limit` keeps the most recent records and says it
was cut.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from openfactory import actions

#: Today at 10:00 UTC, and two days before it: the two days the records were made on. Read off the
#: real clock, so the rows are inside their kept period whenever this runs.
TODAY = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)
BEFORE = TODAY - timedelta(days=2)

ALICE = actions.Actor(id="alice", display="Alice Ferreira", via="panel")
BOB = actions.Actor(id="bob", display="Bob", via="panel", admin=True)
#: Alice asking where she is an admin — the same person, so the same `actor_id` in the record.
ALICE_AS_ADMIN = dataclasses.replace(ALICE, admin=True)

#: What the deployment did, in the order it did it: (when, who, action, project) — `skip` is run
#: with its runner replaced so it answers `done`; `product_status` on a project nobody registered
#: is refused by the row (`not_found`); `ack` asked by a person who is not an admin is refused by
#: `perform` itself (`denied`, reason `not_admin`).
CALLS = (
    (BEFORE, ALICE_AS_ADMIN, "skip", "alpha"),
    (BEFORE + timedelta(hours=1), BOB, "product_status", "beta"),
    (TODAY, BOB, "skip", "beta"),
    (TODAY + timedelta(hours=1), ALICE, "ack", "alpha"),
)


def _stop_the_clock_at(mp: pytest.MonkeyPatch, instant: datetime) -> None:
    """Every `now_iso()` — the record's `ts` — reads `instant` until the next call."""
    from openfactory.observability import events

    class _Stopped(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant

    mp.setattr(events, "datetime", _Stopped)


async def _do_what_the_deployment_did() -> None:
    """Run `CALLS` through the real `perform`, each at its own instant. The clock and the `skip`
    row are patched for these calls only, and put back before the command reads anything."""
    from openfactory.actions import catalog

    async def skipped(**_kw):
        return actions.done("skipped")

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(catalog.CATALOG, "skip", dataclasses.replace(catalog.CATALOG["skip"],
                                                                run=skipped))
        for when, by, name, project in CALLS:
            _stop_the_clock_at(mp, when)
            params = {"project": project} if name == "product_status" else {
                "project": project, "issue": "7"}
            outcome = await actions.perform(name, by=by, **params)
            assert outcome.ok == (name == "skip"), (name, outcome)  # each call took its path


@pytest.fixture
async def deployment(tmp_path, monkeypatch):
    """A sqlite deployment named as an operator names one (`OPENFACTORY_METRICS_SINK=sqlite`, the
    file in `OPENFACTORY_METRICS_DB`, a registry of its own), holding the four records `CALLS`
    left. Returns the database file."""
    db = tmp_path / "metrics.db"

    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(db))
    await _do_what_the_deployment_did()
    return db


def _audit(*args: str):
    from openfactory.cli import app

    return CliRunner().invoke(app, ["audit", *args])


def _listed(*args: str) -> list[tuple[str, str, str]]:
    """What `openfactory audit <args> --json` lists, as (actor, action, project), in its order."""
    result = _audit(*args, "--json")
    assert result.exit_code == 0, (result.exit_code, result.output)
    return [(r["actor_id"], r["action"], r["project"])
            for r in json.loads(result.stdout)["records"]]


def test_it_lists_by_actor(deployment):
    """Criterion 4, "lists records by actor": `--actor alice` lists what Alice asked for and
    nothing Bob did. Before #694: `No such command 'audit'`, exit 2."""
    assert _listed("--actor", "alice") == [("alice", "skip", "alpha"), ("alice", "ack", "alpha")]


def test_it_lists_by_action(deployment):
    """Criterion 4, "by action": `--action skip` lists both skips, whoever asked."""
    assert _listed("--action", "skip") == [("alice", "skip", "alpha"), ("bob", "skip", "beta")]


def test_it_lists_by_project(deployment):
    """Criterion 4, "by project": `--project beta` lists what was done on `beta` only."""
    assert _listed("--project", "beta") == [("bob", "product_status", "beta"),
                                            ("bob", "skip", "beta")]


@pytest.mark.parametrize(("outcome", "expected"), [
    ("ok", [("alice", "skip", "alpha"), ("bob", "skip", "beta")]),
    ("refused", [("bob", "product_status", "beta"), ("alice", "ack", "alpha")]),
    (actions.NOT_FOUND, [("bob", "product_status", "beta")]),   # a refusal's code
    (actions.DENIED, [("alice", "ack", "alpha")]),               # a refusal's code ...
    (actions.NOT_ADMIN, [("alice", "ack", "alpha")]),            # ... and its finer reason
])
def test_it_lists_by_outcome(deployment, outcome, expected):
    """Criterion 4, "by outcome": `--outcome ok` lists what worked, `refused` what did not, and a
    refusal's code (`denied`) or its reason (`not_admin`) lists the refusals that said it."""
    assert _listed("--outcome", outcome) == expected


def test_it_lists_by_period(deployment):
    """Criterion 4, "by period": `--since` and `--until` take UTC dates and both are inclusive of
    their day — the day before yesterday's records, then today's, then one day alone."""
    day = BEFORE.date().isoformat()
    between = (BEFORE + timedelta(days=1)).date().isoformat()

    assert _listed("--until", between) == [("alice", "skip", "alpha"),
                                           ("bob", "product_status", "beta")]
    assert _listed("--since", between) == [("bob", "skip", "beta"), ("alice", "ack", "alpha")]
    assert _listed("--since", day, "--until", day) == [("alice", "skip", "alpha"),
                                                       ("bob", "product_status", "beta")]


@pytest.mark.parametrize("flag", ["--since", "--until"])
@pytest.mark.parametrize("text", ["2026-13-01", "yesterday"])
def test_a_date_that_is_not_one_is_refused_by_name_rather_than_read_as_no_bound(deployment, flag,
                                                                                text):
    """Criterion 4's period, and "failures speak by name": a `--since` or `--until` that is not a
    UTC date exits 2 naming the flag and what was given, and lists nothing — never read as "no
    bound", which would list the whole kept year as if it were the period asked for. Written with
    the mutation plan (2026-10-20): the refusal was driven only by hand when the command landed."""
    result = _audit(flag, text)

    assert result.exit_code == 2, (result.exit_code, result.output)
    assert flag in result.stderr and repr(text) in result.stderr, result.stderr
    assert result.stdout == "", result.stdout


def test_each_record_is_one_line_oldest_first_in_utc(deployment):
    """Without `--json`, one line per record, oldest first, each starting with its UTC time and
    then who asked, the action and the project, and saying `ok` or `refused` with the code."""
    result = _audit()

    assert result.exit_code == 0, (result.exit_code, result.output)
    lines = result.stdout.splitlines()
    assert len(lines) == len(CALLS), lines
    for line, (when, by, name, project) in zip(lines, CALLS, strict=True):
        words = line.split()
        assert datetime.fromisoformat(words[0]) == when, line
        assert words[0].endswith("+00:00"), line
        assert words[1:4] == [by.id, name, project], line
    assert [line.split()[4] for line in lines] == ["ok", "refused", "ok", "refused"], lines
    assert lines[3].split()[5:7] == [actions.DENIED, actions.NOT_ADMIN], lines[3]


def test_json_prints_the_records_own_fields(deployment):
    """`--json` prints each record with every field the record has — the issue's list, read off
    the type — not a summary of it."""
    from openfactory.observability.audit import AuditRecord

    result = _audit("--actor", "bob", "--action", "skip", "--json")

    assert result.exit_code == 0, (result.exit_code, result.output)
    [record] = json.loads(result.stdout)["records"]
    assert set(record) >= {f.name for f in dataclasses.fields(AuditRecord)}, record
    assert (record["actor_display"], record["via"], record["ok"], record["ts"]) == (
        "Bob", "panel", True, TODAY.isoformat()), record


async def test_it_reads_the_store_the_record_was_written_to(tmp_path, monkeypatch):
    """Q9: a host CLI whose environment names no metrics store keeps its records in `audit.db`
    beside `registry.yaml` (`audit.sink()`), and `openfactory audit` reads that same file — not
    the deployment's `null` sink, which would answer an empty list about rows that are on disk."""
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    await _do_what_the_deployment_did()

    assert (tmp_path / "audit.db").exists(), sorted(p.name for p in tmp_path.iterdir())
    assert len(_listed()) == len(CALLS)


@pytest.mark.parametrize("why", ["a directory where the file should be",
                                 "a sink kind nothing answers to"])
def test_a_store_that_cannot_be_read_exits_2_naming_it(tmp_path, monkeypatch, why):
    """Lesson §2, "could not see" is not "there is nothing": a store that will not answer exits 2
    with a sentence naming it — the file, or the sink kind that could not be built — and lists
    nothing, rather than an empty list that reads as a deployment where nobody did anything."""
    db = tmp_path / "metrics.db"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(db))
    if why.startswith("a directory"):
        db.mkdir()
        monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
        named = str(db)
    else:
        monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlit")
        named = "sqlit"

    result = _audit()

    assert result.exit_code == 2, (result.exit_code, result.output)
    assert named in result.stderr, result.stderr
    assert result.stdout == "", result.stdout


@pytest.mark.parametrize("kind", ["write_only"])
def test_a_deployment_that_keeps_nothing_says_so_rather_than_listing_nothing(tmp_path, monkeypatch,
                                                                            kind):
    """A deployment whose metrics sink records and cannot be read back — an add-on's sink without
    `scan` — has nothing this command can read. It exits 2 naming the sink and the variable that
    chooses it, rather than printing an empty list about records it never looked for. (`memory`
    was the other case until the PR #1039 review: its records now go to the fallback file, which
    this command reads — `test_an_audit_record_that_is_not_kept_is_seen.py`.)"""
    from openfactory.observability import registry as sinks

    class _WriteOnly:
        def record(self, rec) -> bool:
            return True

    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", kind)
    if kind == "write_only":
        monkeypatch.setitem(sinks.METRICS_SINKS, kind, lambda **_kw: _WriteOnly())

    result = _audit()

    assert result.exit_code == 2, (result.exit_code, result.output)
    assert kind in result.stderr and "OPENFACTORY_METRICS_SINK" in result.stderr, result.stderr
    assert result.stdout == "", result.stdout


def test_an_empty_store_says_it_holds_no_record_and_names_it(tmp_path, monkeypatch):
    """The third answer: a store that answered and holds no record of kind `audit` says so, naming
    the store, and exits 0 — told apart from the two above by its exit code and its sentence."""
    db = tmp_path / "metrics.db"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(db))

    result = _audit()

    assert result.exit_code == 0, (result.exit_code, result.output)
    assert "no audit record" in result.output and str(db) in result.output, result.output


def test_rows_of_other_kinds_in_the_store_are_not_read_as_audit_records(tmp_path, monkeypatch):
    """The store the records share holds every other kind too — a job's cost rows, the people
    store's registrations under the same deployment-wide key. A store holding only those holds no
    audit record, and says so, even when another kind's row carries the field names a record has:
    nothing of it is listed. Written with the mutation plan (2026-10-20): every row this file
    wrote was of kind `audit`, so listing every kind left the suite green."""
    from openfactory.identity.people import PROJECT
    from openfactory.observability.metrics import MetricRecord
    from openfactory.observability.sqlite_metrics import SqliteMetricsSink

    db = tmp_path / "metrics.db"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(db))
    ts = TODAY.isoformat()
    sink = SqliteMetricsSink(db)
    assert sink.record(MetricRecord(kind="person", project=PROJECT, ticket="invited.1", ts=ts,
                                    role="invited", extra={"event": "invited"}))
    assert sink.record(MetricRecord(kind="agent_run", project="alpha", ticket="7", ts=ts,
                                    extra={"ts": ts, "actor_id": "alice", "action": "skip",
                                           "project": "alpha", "ok": True}))

    result = _audit()

    assert result.exit_code == 0, (result.exit_code, result.output)
    assert result.stdout == "", result.stdout
    assert "holds no audit record" in result.stderr, result.stderr


def test_the_bound_is_said_when_it_is_hit(deployment):
    """Lesson "bounds are logged when hit": `--limit 2` over four records lists the two most
    recent, oldest first, and says the list was cut and how to see more; `--json` says
    `"cut": true`. At a limit the records fit in, nothing is said."""
    result = _audit("--limit", "2")
    as_json = json.loads(_audit("--limit", "2", "--json").stdout)

    assert result.exit_code == 0, (result.exit_code, result.output)
    assert [line.split()[1:3] for line in result.stdout.splitlines()] == [
        ["bob", "skip"], ["alice", "ack"]], result.stdout
    assert "--limit" in result.stderr and "2" in result.stderr, result.stderr
    assert (len(as_json["records"]), as_json["cut"]) == (2, True), as_json
    whole = _audit("--limit", str(len(CALLS)))
    assert whole.stderr == "", whole.stderr
    assert json.loads(_audit("--limit", str(len(CALLS)), "--json").stdout)["cut"] is False


async def test_a_caller_the_panel_could_not_name_is_listed_as_a_dash_keeping_each_line_in_columns(
        tmp_path, monkeypatch):
    """A record whose `actor_id` is empty — the panel's anonymous caller, `somebody with the panel
    token` — lists `-` where who asked goes, as an absent project does, so the action and the
    project stay the third and fourth words. Measured by hand on 2026-10-21 (`openfactory serve`,
    one `curl -X POST /api/act/product_status`): the line read `<ts>    product_status  nosuch …`,
    an empty column, so `split()` put the action where who asked goes."""
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(tmp_path / "metrics.db"))
    nobody = actions.Actor(id="", display="somebody with the panel token", via="panel")
    await actions.perform("product_status", by=nobody, project="nosuch")

    result = _audit()

    assert result.exit_code == 0, (result.exit_code, result.output)
    [line] = result.stdout.splitlines()
    assert line.split()[1:4] == ["-", "product_status", "nosuch"], line


def test_an_action_asked_in_capitals_is_recorded_and_listed_by_its_name(tmp_path, monkeypatch):
    """An action is resolved lower-cased and stripped (`perform`), so the record keeps the name it
    resolved to and `--action` matches it however it is typed. No test held either half: the
    branch review's cuts keeping the name as asked, and not lower-casing `--action`, each survived
    133 tests."""
    import asyncio

    from openfactory.cli import app

    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(tmp_path / "m.db"))
    asyncio.run(actions.perform(" Product_Status ", by=actions.SYSTEM, project="nosuch"))

    out = CliRunner().invoke(app, ["audit", "--action", "PRODUCT_STATUS", "--json"])
    assert [r["action"] for r in json.loads(out.stdout)["records"]] == ["product_status"], out.output


# ── the read is bounded (PR #1039 review) ───────────────────────────────────────────────────────

def _written(db, records) -> None:
    """`records` (`MetricRecord`s) in the store, each written as `SqliteMetricsSink.record` writes
    one, in one transaction (a `record` per row costs a connection and a commit each)."""
    import sqlite3

    rows = []
    for rec in records:
        key = rec.dynamo_key()
        rows.append((key["pk"], key["sk"], rec.kind, rec.ts, rec.ticket, rec.expires_at,
                     json.dumps({**rec.model_dump(), **key}, default=str)))
    with sqlite3.connect(db) as conn:
        conn.executemany("INSERT INTO metrics (pk, sk, kind, ts, ticket, expires_at, data)"
                         " VALUES (?,?,?,?,?,?,?)", rows)
    conn.close()


def _rows_of_another_kind(db, count: int) -> None:
    """`count` rows of a job's cost (`agent_run`) in the store the records share — what a busy
    deployment's metrics store mostly holds."""
    from openfactory.observability.metrics import MetricRecord

    _written(db, (MetricRecord(kind="agent_run", project="alpha", ticket=str(i),
                               ts=TODAY.isoformat(), extra={"cost_usd": 0.01})
                  for i in range(count)))


def _older_records(db, count: int) -> None:
    """`count` audit records made a week before `BEFORE`, an hour apart, as `audit.metric_of`
    makes the row."""
    from openfactory.observability import audit

    def made(i: int):
        record = audit.AuditRecord.of("product_status", actions.SYSTEM, {"project": "old"},
                                      actions.done("fine"), product_of=lambda _name: "")
        ts = (BEFORE - timedelta(days=7, hours=i)).isoformat()
        return audit.metric_of(dataclasses.replace(record, ts=ts))

    _written(db, (made(i) for i in range(count)))


@pytest.fixture
def parsed(monkeypatch) -> list[int]:
    """How many rows the sqlite store turned into a dict for the command — every row a reader
    holds in memory passes through `SqliteMetricsSink._row`."""
    from openfactory.observability.sqlite_metrics import SqliteMetricsSink

    count = [0]
    real = SqliteMetricsSink._row

    def counted(data: str) -> dict:
        count[0] += 1
        return real(data)

    monkeypatch.setattr(SqliteMetricsSink, "_row", staticmethod(counted))
    return count


def test_the_store_is_asked_for_audit_rows_and_never_scanned_whole(deployment, monkeypatch):
    """The review's point: `openfactory audit` read the whole store (`scan()`, every kind, every
    row's JSON) into memory to keep the audit rows. A sqlite store is asked for rows of kind
    `audit` alone, a page at a time; its `scan` is never called. On c310ba28 it was: exit 2, `scan read the whole
    store`."""
    from openfactory.observability.sqlite_metrics import SqliteMetricsSink

    def whole(_self):
        raise AssertionError("scan read the whole store")

    monkeypatch.setattr(SqliteMetricsSink, "scan", whole)

    result = _audit()

    assert result.exit_code == 0, (result.exit_code, result.output)
    assert len(result.stdout.splitlines()) == len(CALLS), result.stdout


def test_the_store_is_read_to_the_limit_and_one_more_however_many_rows_it_holds(deployment,
                                                                               parsed):
    """`--limit 1` over a store of 4 records and 200 rows of another kind turns 2 rows into
    memory — the most recent record, and one more to know the list was cut — not 204. Measured
    on c310ba28: 204 rows parsed for one line printed."""
    _rows_of_another_kind(deployment, 200)
    parsed[0] = 0

    result = _audit("--limit", "1")

    assert result.exit_code == 0, (result.exit_code, result.output)
    assert [line.split()[1:3] for line in result.stdout.splitlines()] == [["alice", "ack"]]
    assert "--limit" in result.stderr, result.stderr
    assert parsed[0] <= 2, f"{parsed[0]} rows read for --limit 1"


def test_the_store_is_read_back_to_since_and_no_further(deployment, parsed, monkeypatch):
    """Pages come newest first, so `--since` ends the read at the first record older than it: in
    pages of 2, over today's two records and 22 older ones, two pages are read — 4 rows — not
    twelve. On c310ba28 every row of the store was: 74, the 50 cost rows among them."""
    from openfactory import cli

    _rows_of_another_kind(deployment, 50)
    _older_records(deployment, 20)
    monkeypatch.setattr(cli, "AUDIT_PAGE", 2, raising=False)   # c310ba28 has no pages
    parsed[0] = 0

    listed = _listed("--since", TODAY.date().isoformat())

    assert listed == [("bob", "skip", "beta"), ("alice", "ack", "alpha")], listed
    assert parsed[0] <= 4, f"{parsed[0]} rows read for two records since today"


def test_a_page_boundary_neither_skips_nor_repeats_a_record(deployment, monkeypatch):
    """Each page starts after the last row of the one before (`(sk, pk)`, the primary key), so in
    pages of 2 the four records are listed once each, in their order. Green on c310ba28 (one scan,
    no pages); the cuts that start a page at its predecessor's first row, or at its last row
    inclusive, list a record twice."""
    from openfactory import cli

    monkeypatch.setattr(cli, "AUDIT_PAGE", 2, raising=False)

    assert _listed() == [(by.id, name, project) for _when, by, name, project in CALLS]


def test_a_store_that_cannot_ask_by_kind_is_still_listed_through_its_scan(tmp_path, monkeypatch):
    """`KindPagingSink` is optional: a store that reads back (`ReadableSink`) without it — an
    add-on's, as the DynamoDB one is today — is listed as before, through its `scan`, its other
    kinds left out (a cost row carrying a record's field names among them), cut here to the most
    recent. Green on c310ba28 (that was the only path); the cuts that drop the fallback, or its
    filter on the kind, turn it red."""
    import asyncio

    from openfactory.observability import registry as sinks
    from openfactory.observability.metrics import MetricRecord
    from openfactory.observability.sqlite_metrics import SqliteMetricsSink

    class _ScanOnly:
        def __init__(self, path):
            self._inner = SqliteMetricsSink(path)

        def record(self, rec) -> bool:
            return self._inner.record(rec)

        def scan(self) -> list[dict]:
            return self._inner.scan()

        def records_of_kind(self, project, kind, *, limit=500) -> list[dict]:
            return self._inner.records_of_kind(project, kind, limit=limit)

    db = tmp_path / "scan-only.db"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "scan_only")
    monkeypatch.setitem(sinks.METRICS_SINKS, "scan_only", lambda **_kw: _ScanOnly(db))
    for project in ("one", "two", "three"):
        asyncio.run(actions.perform("product_status", by=actions.SYSTEM, project=project))
    ts = datetime.now(UTC).isoformat()
    assert _ScanOnly(db).record(MetricRecord(
        kind="agent_run", project="alpha", ticket="7", ts=ts,
        extra={"ts": ts, "actor_id": "alice", "action": "skip", "project": "alpha", "ok": True}))

    assert [p for _a, _b, p in _listed("--limit", "2")] == ["two", "three"]


# ── a call that failed is not a refusal (PR #1039 review N5) ───────────────────────────────────

def _a_store_of_three_ends(tmp_path, monkeypatch):
    """A refusal, a row that raised, and a call cancelled mid-row, as `perform` records each."""
    from openfactory.observability import audit
    from openfactory.observability.sqlite_metrics import SqliteMetricsSink

    db = tmp_path / "metrics.db"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(db))
    ends = [actions.refused(actions.NOT_FOUND, "no such project", reason=actions.NOT_FOUND),
            actions.Outcome(ok=False, code=actions.FAILED, message="raised",
                            data={"reason": actions.RAISED}),
            actions.Outcome(ok=False, code=actions.FAILED, message="cancelled",
                            data={"reason": audit.CANCELLED})]
    for i, outcome in enumerate(ends):
        record = audit.AuditRecord.of("merge", actions.SYSTEM, {"project": f"p{i}"}, outcome,
                                      product_of=lambda _name: "")
        record = dataclasses.replace(record, ts=(TODAY + timedelta(minutes=i)).isoformat())
        assert SqliteMetricsSink(db).record(audit.metric_of(record))


def test_a_call_that_raised_or_was_cancelled_is_listed_as_failed_not_refused(tmp_path,
                                                                            monkeypatch):
    """N5: a row that raised after its side effect, or a call cancelled mid-row, may have done
    what it was asked; "refused" told an auditor it did not. Code `failed` is listed `failed`,
    with its reason; a refusal is still `refused`. On c310ba28 all three read `refused …`."""
    _a_store_of_three_ends(tmp_path, monkeypatch)

    said = [" ".join(line.split()[4:]) for line in _audit().stdout.splitlines()]

    assert said == ["refused not_found not_found", "failed raised", "failed cancelled"], said


def test_outcome_refused_lists_refusals_and_outcome_failed_lists_failures(tmp_path,
                                                                         monkeypatch):
    """`--outcome refused` is the refusals alone, and `--outcome failed` the calls that failed:
    the listing's two words are the filter's two words. On c310ba28 `refused` listed all three."""
    _a_store_of_three_ends(tmp_path, monkeypatch)

    assert [p for _a, _b, p in _listed("--outcome", "refused")] == ["p0"]
    assert [p for _a, _b, p in _listed("--outcome", "failed")] == ["p1", "p2"]
