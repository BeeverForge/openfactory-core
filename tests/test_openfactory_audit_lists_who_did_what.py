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


@pytest.mark.parametrize("kind", ["memory", "write_only"])
def test_a_deployment_that_keeps_nothing_says_so_rather_than_listing_nothing(tmp_path, monkeypatch,
                                                                            kind):
    """A deployment whose metrics sink records and cannot be read back — `memory`, which keeps a
    row only in the process that wrote it, or an add-on's sink without `scan` — has nothing this
    command can read. It exits 2 naming the sink and the variable that chooses it, rather than
    printing an empty list about records it never looked for."""
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
