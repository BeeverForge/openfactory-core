"""An audit record that is not kept is seen by whoever watches the process, and a deployment on the
`memory` metrics sink still keeps its records (#694, PR #1039 review).

WHAT WAS TRUE BEFORE. On c310ba28 a record the store did not take was one WARNING line and
nothing else: no supervisor, no healthcheck and no `docker ps` could tell a panel whose every
action went unrecorded from one whose trail was whole. And `audit.sink()` handed a deployment
naming `OPENFACTORY_METRICS_SINK=memory` the shipped builder's fresh `InMemoryMetricsSink` on every
call: the store said True, the record was gone when the call returned, and `openfactory audit`
there exited 2 saying the deployment keeps nothing.

WHAT HOLDS NOW: readiness has an `audit` check, failing while the last record this process wrote
was not kept — a store that answered False, one that raised, or no store that could be built — and
ready again once one is; the cause it logs counts the records not kept since the process started.
A `memory` deployment keeps its records in the fallback sqlite file (`audit.audit_path()`), as one
that declares no store does, said once at WARNING, and `openfactory audit` lists them.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from openfactory import actions
from openfactory.observability import audit, health
from openfactory.observability.sqlite_metrics import SqliteMetricsSink


@pytest.fixture
def store(tmp_path, monkeypatch) -> SqliteMetricsSink:
    """A sqlite deployment as an operator names one, with a registry of its own."""
    db = tmp_path / "metrics.db"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(db))
    return SqliteMetricsSink(db)


def _refusing(tmp_path: Path, monkeypatch) -> None:
    """`OPENFACTORY_METRICS_DB` naming a directory: the sqlite sink answers False."""
    where = tmp_path / "not-a-file.db"
    where.mkdir(exist_ok=True)
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(where))


def _raising(tmp_path: Path, monkeypatch) -> None:
    """A store whose `record` raises."""
    class _Gone:
        def record(self, rec) -> bool:
            raise RuntimeError("the store is gone")

    monkeypatch.setattr(audit, "sink", lambda: _Gone())


def _unbuildable(tmp_path: Path, monkeypatch) -> None:
    """A sink kind nothing answers to: no store can be built, so `perform` says it."""
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlit")


FAILING = [pytest.param(way, id=way.__name__.lstrip("_"))
           for way in (_refusing, _raising, _unbuildable)]


async def _verdict() -> dict | None:
    return (await health.ready())["checks"].get("audit")


@pytest.mark.parametrize("failing", FAILING)
async def test_readiness_names_the_audit_trail_while_the_last_record_was_not_kept(
        store, tmp_path, monkeypatch, failing):
    """The review's point: a failed write was only a WARNING. Readiness — what the compose
    file's healthcheck asks every fifteen seconds — now fails its `audit` check, in its own fixed
    sentence, after a record the store did not take, however it did not take it. On c310ba28
    there was no `audit` check: `None`."""
    failing(tmp_path, monkeypatch)

    await actions.perform("product_status", by=actions.Actor(id="alice", via="panel"),
                          project="nosuch")

    assert await _verdict() == {"ok": False, "detail": health.SAID.get("audit", "?")}


async def test_readiness_is_ready_again_once_a_record_is_kept(store, tmp_path, monkeypatch):
    """The check says the last write, not every write since start: after a refused record, one
    that lands makes the `audit` check pass again, the next window. Without this, a store
    repaired would hold the process unready until it restarted."""
    by = actions.Actor(id="alice", via="panel")
    good = store.path
    _refusing(tmp_path, monkeypatch)
    await actions.perform("product_status", by=by, project="nosuch")
    assert (await _verdict() or {}).get("ok") is False

    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(good))
    await actions.perform("product_status", by=by, project="nosuch")
    health.forget()   # the next window

    assert await _verdict() == {"ok": True}


async def test_readiness_counts_the_records_not_kept_in_the_cause_it_logs(store, tmp_path,
                                                                         monkeypatch, caplog):
    """The cause readiness logs once (`NOT_READY the audit check failed: …`) says how many records
    this process did not keep since it started, and why the last one was not — the count an
    operator needs to know how much of the trail is missing. Never in the body: a caller with no
    credential reads only the fixed sentence."""
    _refusing(tmp_path, monkeypatch)
    for _ in range(3):
        await actions.perform("product_status", by=actions.SYSTEM, project="nosuch")

    with caplog.at_level(logging.WARNING, logger="openfactory.health"):
        body = await health.ready()

    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith(
        "NOT_READY the audit check failed")]
    assert len(said) == 1 and "3 audit records not kept" in said[0], said
    assert "3 audit records" not in str(body), body


# ── the memory sink ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def on_memory(tmp_path, monkeypatch) -> Path:
    """A deployment naming `OPENFACTORY_METRICS_SINK=memory` and no file: the fallback is
    `audit.db` beside `registry.yaml`."""
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "memory")
    monkeypatch.delenv("OPENFACTORY_METRICS_DB", raising=False)
    monkeypatch.delenv("OPENFACTORY_METRICS_TABLE", raising=False)
    return tmp_path / "audit.db"


async def test_a_deployment_on_the_memory_sink_keeps_its_audit_records_in_the_fallback_file(
        on_memory):
    """The review's second half: a `memory` sink keeps a row only as long as the object that
    holds it, and the shipped builder makes a new one per call, so on c310ba28 the store said True
    and the record was gone when the call returned — `audit.db` did not exist. The records go to
    the fallback file, as a deployment's that declares no store do."""
    await actions.perform("product_status", by=actions.SYSTEM, project="nosuch")

    assert on_memory.exists(), "no record was kept anywhere"
    rows = [r for r in SqliteMetricsSink(on_memory).scan() if r.get("kind") == "audit"]
    assert [r["extra"]["action"] for r in rows] == ["product_status"], rows


async def test_the_memory_sink_is_said_once_when_its_records_go_to_the_fallback_file(on_memory,
                                                                                    caplog):
    """An operator who named `memory` is told, once per process at WARNING, that it keeps no
    audit record and where they go instead — naming the variable and the file — not on every
    call."""
    with caplog.at_level(logging.WARNING, logger="openfactory.observability.audit"):
        for _ in range(2):
            await actions.perform("product_status", by=actions.SYSTEM, project="nosuch")

    said = [r.getMessage() for r in caplog.records if "memory" in r.getMessage()]
    assert len(said) == 1, said
    assert "OPENFACTORY_METRICS_SINK" in said[0] and str(on_memory) in said[0], said


def test_openfactory_audit_on_a_memory_deployment_lists_what_its_commands_recorded(on_memory):
    """The reader reads where the writer wrote (`audit.sink()`, one definition for both): a
    command run on a `memory` deployment is listed by `openfactory audit` there. On c310ba28 it
    exited 2: "this deployment's metrics sink 'memory' keeps no record that can be read back"."""
    from typer.testing import CliRunner

    from openfactory.cli import app

    runner = CliRunner()
    runner.invoke(app, ["act", "product_status", "-p", "nosuch"])

    listed = runner.invoke(app, ["audit"])

    assert listed.exit_code == 0, listed.output
    assert [line.split()[2:4] for line in listed.stdout.splitlines()] == [
        ["product_status", "nosuch"]], listed.stdout
