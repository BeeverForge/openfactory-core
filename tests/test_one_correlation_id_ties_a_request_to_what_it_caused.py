"""One correlation id ties a request to every record it caused (#694, criterion 5).

WHAT WAS TRUE BEFORE. No correlation id existed anywhere in the tree (`git grep -i correlation
openfactory/` on bb929e49 found only two CI adapters' unrelated words). `Actor` gained a
`correlation` field earlier on this branch, but no transport filled it: the panel ignored the
request's `X-Request-ID` (the header nginx `$request_id` and most load balancers already set), the
CLI built every actor with none, and `perform` passed the empty string through — so every audit
record said `correlation_id=""`, and an auditor could not read a "yes" and the release it caused as
one request, nor line a panel record up with the proxy's access log.

WHAT HOLDS NOW, in this file: the panel takes the id from `X-Request-ID` when it is one
(`^[A-Za-z0-9._:-]{1,128}$`), and mints one in its place — never storing what was sent — when it is
not or is absent; the CLI mints one per call; a caller that carries none (the factory itself, the
product chat's socket) is given one by `perform`, before the row runs, so a row that relays to
another hands the relayed call the same id. Every assertion reads the record back from the
deployment's store, not from a spy on how it was made — except the CLI's, which reads the `by` the
CLI handed `perform`, because the claim there is that the CLI minted the id, not `perform`.

AND IN THE JOB'S EVENTS: an action that starts a job — `start` on either engine, `scan` for each
card it started and none it skipped — leaves in that job's journal (`paths.events_file`, read back
as JSON lines) one event whose `data.correlation_id` is the id its record carries.
"""

from __future__ import annotations

import dataclasses
import json
import re

import pytest

from openfactory import actions
from openfactory.registry import ProjectRegistry

#: The shape a minted id has: `uuid4().hex`, 32 lower-case hex digits. A test that only asked for
#: "non-empty" would be green on an id built from the header it was meant to replace.
MINTED = re.compile(r"[0-9a-f]{32}")

#: The header the panel reads (Q4's default): what a proxy in front of the panel already sets.
HEADER = "X-Request-ID"


@pytest.fixture
def registry(tmp_path, monkeypatch) -> ProjectRegistry:
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    return ProjectRegistry()


@pytest.fixture
def stored(monkeypatch):
    """The deployment's store, read back: an in-memory sink registered as a kind of its own,
    `kept`, named as an operator names one, its builder pinned to ONE instance so what `perform`
    wrote is still there when the test reads it. Not the shipped `memory` kind, whose records
    `audit.sink()` sends to the fallback file (PR #1039 review)."""
    from openfactory.observability import registry as sinks
    from openfactory.observability.metrics import InMemoryMetricsSink

    sink = InMemoryMetricsSink()
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "kept")
    monkeypatch.setitem(sinks.METRICS_SINKS, "kept", lambda **_kw: sink)
    return sink


def _audit_rows(sink) -> list:
    return [rec for rec in sink.records if rec.kind == "audit"]


# ── the panel ───────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def panel(registry, monkeypatch):
    """The real FastAPI app, with one person's token, posting the one action every test here asks
    for — `product_status` of a project that does not exist, a refusal, which is recorded like any
    other call. Returns a function that posts with the headers it is given."""
    from fastapi.testclient import TestClient

    from openfactory.api.app import app

    for name in ("OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_IDENTITY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKENS", "mine:alice:Alice Ferreira")
    client = TestClient(app)

    def post(**headers: str):
        return client.post("/api/act/product_status", json={"params": {"project": "nosuch"}},
                           headers={"Authorization": "Bearer mine", **headers})
    return post


def test_the_panel_takes_the_correlation_id_from_the_header(panel, stored):
    """Criterion 5, "the panel takes it from a request header": a request carrying
    `X-Request-ID: abc-123` leaves a record whose `correlation_id` is `abc-123`. Before #694 the
    panel never read the header and the record said `""`."""
    panel(**{HEADER: "abc-123"})

    [row] = _audit_rows(stored)
    assert row.extra["correlation_id"] == "abc-123", row.extra


@pytest.mark.parametrize("sent", ["x" * 129, "abc\n123", "abc 123"],
                         ids=["129_characters", "a_newline", "a_space"])
def test_a_header_that_is_not_an_id_is_replaced_not_stored(sent, panel, stored):
    """Criterion 5, read with the bound the plan sets (Q4): a header that is not an id — longer
    than 128 characters, or holding a character outside `[A-Za-z0-9._:-]`, such as a newline that
    would split a log line or a space — is replaced by a minted id, and what was sent is nowhere in
    the record. Before #694 no id was read at all (`""`); a panel that stored the header as sent
    would write a 129-character value, or a newline, into a record that is kept for a year."""
    panel(**{HEADER: sent})

    [row] = _audit_rows(stored)
    assert MINTED.fullmatch(row.extra["correlation_id"]), row.extra["correlation_id"]
    assert sent not in json.dumps(row.extra, default=str), row.extra


def test_a_panel_request_without_one_is_given_one(panel, stored):
    """Criterion 5: a panel request that sends no header still leaves a record with an id, in the
    minted shape — so two requests nobody tagged are never one request to an auditor. Before #694
    the record said `""`."""
    panel()

    [row] = _audit_rows(stored)
    assert MINTED.fullmatch(row.extra["correlation_id"]), row.extra["correlation_id"]


# ── the command line ────────────────────────────────────────────────────────────────────────────


def test_the_cli_generates_one_per_call(registry, monkeypatch):
    """Criterion 5, "the CLI generates one": two `openfactory act` runs hand `perform` two actors
    each carrying an id, in the minted shape, and not the same one. Read off the `by` the CLI
    passed — before `perform` could mint one itself — because the claim is that the CLI minted it
    (`cli.py::_cli_actor`, the one CLI actor builder). Before #694 both were `""`."""
    from typer.testing import CliRunner

    from openfactory.cli import app

    real = actions.perform
    carried: list[str] = []

    async def spy(name, *, by, **params):
        carried.append(by.correlation)
        return await real(name, by=by, **params)

    monkeypatch.setattr(actions, "perform", spy)
    for _ in range(2):
        result = CliRunner().invoke(app, ["act", "product_status", "-p", "nosuch"])
        assert result.exit_code == 1, result.output  # the project is unknown: a refusal

    assert len(carried) == 2, carried
    assert all(MINTED.fullmatch(c) for c in carried), carried
    assert carried[0] != carried[1], carried


# ── a caller that carries none ──────────────────────────────────────────────────────────────────


def _the_product_sockets_actor():
    """The actor the product chat's socket hands its rows (`api/app.py::product_stream`): built by
    `_actor_of` from the subject the socket's credential named, with no request header to read an
    id from — a browser cannot set one on a socket."""
    from openfactory.api.app import _actor_of
    from openfactory.identity.base import UNKNOWN

    return _actor_of(object(), UNKNOWN)


@pytest.mark.parametrize("caller", ["system", "the_product_socket"])
async def test_a_caller_that_carries_none_still_gets_one(caller, registry, stored):
    """Criterion 5, for every other caller: the factory's own `SYSTEM` actor, and the product
    socket's, carry no id, and `perform` gives the call one, in the minted shape. Before #694 the
    record said `""`, so a call the factory made on its own could not be told from the next."""
    by = actions.SYSTEM if caller == "system" else _the_product_sockets_actor()
    assert by.correlation == "", by  # the premise: this caller carries none

    await actions.perform("product_status", by=by, project="nosuch")

    [row] = _audit_rows(stored)
    assert MINTED.fullmatch(row.extra["correlation_id"]), row.extra["correlation_id"]


async def test_the_factorys_own_call_is_still_recorded_as_the_system_once_it_carries_an_id(
        registry, stored):
    """ADR-0057 D1 with criterion 5: giving `SYSTEM`'s call an id must not make it somebody else.
    The record names the factory's own actor `system` by recognising `actions.SYSTEM`, and the id
    `perform` mints rides on a copy of the actor (`dataclasses.replace`) — a copy that is not
    `SYSTEM` by identity. Before this commit no copy was made and the record said `system`; a
    `perform` that minted the id and a record that asked `by is SYSTEM` would write `""` for every
    call the factory made on its own, the one caller a record has to be able to single out."""
    await actions.perform("product_status", by=actions.SYSTEM, project="nosuch")

    [row] = _audit_rows(stored)
    assert (row.extra["provider"], row.extra["actor_id"]) == ("system", "system"), row.extra
    assert MINTED.fullmatch(row.extra["correlation_id"]), row.extra["correlation_id"]


async def test_a_relayed_call_shares_the_id_perform_minted_for_its_caller(registry, stored,
                                                                          monkeypatch):
    """Criterion 5 with criterion 2's relays: when `perform` mints the id for a caller that carried
    none, it does so before the row runs, so a row that performs another (`ask` answering "yes"
    runs what was staged, through `run_staged`) hands the relayed call the SAME id — two records,
    one request. An id minted only when the record is written would give the two records two ids,
    and the yes and the skip it caused would read as unrelated. Before #694 both said `""`."""
    from openfactory.actions import catalog
    from openfactory.contracts.project import Project
    from openfactory.memory import messages as channel

    async def skipped(**_kw):
        return actions.done("skipped")

    registry.add(Project(name="demo", repo_path="https://github.com/acme/demo.git"))
    staged = channel.Message(
        kind=channel.SAID, text="I'd skip it", ts="2026-10-20T00:00:00+00:00",
        token=channel.suggestion_token("skip", "87"),
        payload='{"suggestion": ["skip", "87"]}')
    monkeypatch.setattr(channel, "staged", lambda *_a, **_k: (staged, ""))
    monkeypatch.setattr(channel, "answer", lambda *_a, **_k: True)
    monkeypatch.setattr(channel, "say", lambda *_a, **_k: True)
    monkeypatch.setattr(catalog, "_remember", lambda *_a, **_k: None)
    monkeypatch.setitem(catalog.CATALOG, "skip",
                        dataclasses.replace(catalog.CATALOG["skip"], run=skipped))
    by = actions.Actor(id="op", display="Operator", via="panel", admin=True)

    outcome = await actions.perform("ask", by=by, project="demo", question="sim")

    assert outcome.ok and outcome.data.get("action") == "skip", outcome  # the relay happened
    rows = _audit_rows(stored)
    assert sorted(r.extra["action"] for r in rows) == ["ask", "skip"], rows
    ids = {r.extra["correlation_id"] for r in rows}
    assert len(ids) == 1, f"one request left {len(ids)} correlation ids: {sorted(ids)}"
    assert MINTED.fullmatch(ids.pop()), rows


# ── the job's own events ────────────────────────────────────────────────────────────────────────
#
# Criterion 5's second half: the id "is in the job's events when the action starts a job". Each
# test drives the real row through `perform`, with the engine, the board or `Popen` stubbed as the
# action layer's own tests stub them, and then READS the job's journal — the JSON-lines file
# `paths.events_file(project, issue)` names, the file the panel's Logs tab and `query` read — and
# requires one event carrying the id the action's audit record carries. Before #694 the record
# had no id and nothing an action did wrote one into a journal.


def _journal(project, issue: str) -> list[dict]:
    """The job's journal, parsed: one dict per JSON line, `[]` when the file was never written."""
    from openfactory.paths import events_file

    path = events_file(project, issue)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _carrying(events: list[dict], correlation: str) -> list[dict]:
    return [e for e in events if (e.get("data") or {}).get("correlation_id") == correlation]


def _recorded_id(sink, action: str) -> str:
    """The correlation id the one audit record of `action` carries — minted, as `perform` mints it
    for `SYSTEM`, so a journal that held some other id would not match it."""
    [row] = [r for r in _audit_rows(sink) if r.extra["action"] == action]
    correlation = row.extra["correlation_id"]
    assert MINTED.fullmatch(correlation), row.extra  # the premise: the record carries one
    return correlation


@pytest.fixture
def logs(tmp_path, monkeypatch):
    """Where the journals are written: the deployment's `OPENFACTORY_LOG_DIR`, in a temporary
    directory, so `events_file` names a file this test alone writes."""
    monkeypatch.setenv("OPENFACTORY_LOG_DIR", str(tmp_path / "logs"))
    return tmp_path / "logs"


@pytest.fixture
def start_project(monkeypatch, logs):
    """The project `start` launches for, resolved as `tests/test_the_action_layer.py::_start_env`
    resolves it, and a box image that resolves without asking any registry."""
    from tests.test_the_action_layer import _start_project

    project = _start_project()
    monkeypatch.setattr(ProjectRegistry, "get", lambda self, name: project)
    monkeypatch.setattr("openfactory.factory.resolve_box_image",
                        lambda *_a, **_kw: "openfactory-python")
    return project


@pytest.fixture
def scan_project(monkeypatch, logs):
    """The project `scan` reads the board of, pinned as `tests/test_the_action_layer.py::_scan_env`
    pins it: resolvable, a token that needs no credential, a box image that needs no registry."""
    from tests.test_the_action_layer import _scan_project

    project = _scan_project()
    monkeypatch.setattr(ProjectRegistry, "get", lambda self, name: project)
    monkeypatch.setattr("openfactory.credentials.tracker_token", lambda: "tok")
    monkeypatch.setattr("openfactory.factory.resolve_box_image",
                        lambda *_a, **_kw: "openfactory-python")
    return project


def _engine(monkeypatch, **kw):
    """The action layer's fake engine (`_FakeTemporalClient`), reached where the rows connect."""
    from tests.test_the_action_layer import _AsyncReturns, _FakeTemporalClient

    client = _FakeTemporalClient(**kw)
    monkeypatch.setattr("openfactory.runtime.temporal.view.connect", lambda: _AsyncReturns(client))
    return client


async def test_a_durable_start_writes_it_into_the_jobs_events(start_project, stored, monkeypatch):
    """Criterion 5, "in the job's events when the action starts a job", on the durable engine: a
    `start --durable` the engine accepted leaves, in the journal of the job it started, one event
    whose `data.correlation_id` is the id the action's record carries. Before #694 the journal of
    a started job held no such event — the engine was told nothing, and neither was the file."""
    client = _engine(monkeypatch)

    out = await actions.perform("start", by=actions.SYSTEM, project="demo", issue="7",
                                durable=True, sandbox="container")

    assert out.ok and client.launched, out  # the premise: the engine took the job
    correlation = _recorded_id(stored, "start")
    events = _journal(start_project, "7")
    assert len(_carrying(events, correlation)) == 1, (
        f"{len(_carrying(events, correlation))} events in #7's journal carry the start's "
        f"correlation id {correlation} (1 expected): {events}")


async def test_a_local_start_writes_it_into_the_jobs_events(start_project, stored, monkeypatch):
    """Criterion 5 on the local engine: a `start` that launched `openfactory run` as a detached
    process (`Popen`, stubbed here) leaves the same one event in the job's journal, carrying the
    record's id. Before #694 nothing but the run log was written before the process was spawned."""
    launched: list = []
    monkeypatch.setattr("subprocess.Popen", lambda argv, **kw: launched.append(argv))

    out = await actions.perform("start", by=actions.SYSTEM, project="demo", issue="7",
                                sandbox="worktree")

    assert out.ok and launched, out  # the premise: the process was launched
    correlation = _recorded_id(stored, "start")
    events = _journal(start_project, "7")
    assert len(_carrying(events, correlation)) == 1, (
        f"{len(_carrying(events, correlation))} events in #7's journal carry the start's "
        f"correlation id {correlation} (1 expected): {events}")


async def test_scan_writes_it_into_each_started_jobs_events(scan_project, stored, monkeypatch):
    """Criterion 5 through `scan`, the action that starts several jobs at once: each job it started
    has, in its own journal, one event carrying the id of the scan's one record — so every job a
    single click started reads back to that click. Before #694 neither journal held one."""
    from tests.test_the_action_layer import _FakeBoard

    monkeypatch.setattr("openfactory.adapters.board.build_board",
                        lambda *_a, **_kw: _FakeBoard(["1", "2"]))
    monkeypatch.setattr("openfactory.runtime.temporal.max_concurrent_jobs", lambda: 5)
    _engine(monkeypatch)

    out = await actions.perform("scan", by=actions.SYSTEM, project="demo")

    assert out.data["started"] == ["1", "2"], out  # the premise: both were started
    correlation = _recorded_id(stored, "scan")
    found = {issue: len(_carrying(_journal(scan_project, issue), correlation))
             for issue in ("1", "2")}
    assert found == {"1": 1, "2": 1}, (
        f"events carrying the scan's correlation id {correlation}, per started job's journal: "
        f"{found} (one each expected)")


async def test_scan_writes_it_only_into_the_jobs_it_started(scan_project, stored, monkeypatch):
    """Criterion 5's "when the action starts a job", read from the other side: a card `scan`
    found already running (the engine answered `AlreadyStarted`) and a card it left in TO-DO
    because the floor was full were not started by this scan, and their journals must not say
    they were. Card 1, the one it started, carries the id — the premise that this test reads the
    files the note is written to. Before #694 no journal carried it, card 1's included."""
    from tests.test_the_action_layer import _FakeBoard

    monkeypatch.setattr("openfactory.adapters.board.build_board",
                        lambda *_a, **_kw: _FakeBoard(["1", "2", "3"]))
    monkeypatch.setattr("openfactory.runtime.temporal.max_concurrent_jobs", lambda: 2)
    _engine(monkeypatch, fail_started={"2"})

    out = await actions.perform("scan", by=actions.SYSTEM, project="demo")

    assert (out.data["started"], out.data["skipped"]) == (["1"], ["2", "3"]), out  # the premise
    correlation = _recorded_id(stored, "scan")
    found = {issue: len(_carrying(_journal(scan_project, issue), correlation))
             for issue in ("1", "2", "3")}
    assert found == {"1": 1, "2": 0, "3": 0}, (
        f"events carrying the scan's correlation id {correlation}, per card's journal: {found} "
        f"(only the started card 1 expected)")


# ── a journal that cannot be written ────────────────────────────────────────────────────────────
#
# Task 28's own sentence: "a journal write failure is logged and does not undo or fail the start —
# the start happened, announce what happened" (lesson §9). The failure is one an operator can make:
# `OPENFACTORY_EVENT_SINK` naming a sink no build knows, so building the job's journal raises
# `ValueError: unknown event sink 'no-such-sink'`. The start must stand, and a WARNING must name the
# job and that cause; a silent start would be a job whose journal does not say who asked, with
# nothing anywhere saying why.

UNBUILDABLE_SINK = "no-such-sink"


def _not_journalled(caplog, issue: str) -> list:
    return [r for r in caplog.records
            if r.levelname == "WARNING" and "OPENFACTORY_START_NOT_JOURNALLED" in r.getMessage()
            and f"issue={issue}" in r.getMessage() and UNBUILDABLE_SINK in r.getMessage()]


async def test_a_start_whose_journal_cannot_be_written_still_starts_and_says_so(
        start_project, stored, monkeypatch, caplog):
    """A local `start` whose job journal cannot be built still launches the process, is still
    `ok`, and logs one WARNING naming the job and the cause. Before #694 nothing was written to the
    journal at start, so nothing could fail and nothing was logged: this test is red there on the
    missing warning, which is the half the new write must add."""
    launched: list = []
    monkeypatch.setattr("subprocess.Popen", lambda argv, **kw: launched.append(argv))
    monkeypatch.setenv("OPENFACTORY_EVENT_SINK", UNBUILDABLE_SINK)
    caplog.set_level("WARNING")

    out = await actions.perform("start", by=actions.SYSTEM, project="demo", issue="7",
                                sandbox="worktree")

    assert out.ok and len(launched) == 1, out
    assert len(_not_journalled(caplog, "7")) == 1, [r.getMessage() for r in caplog.records]


async def test_a_durable_start_whose_journal_cannot_be_written_still_starts_and_says_so(
        start_project, stored, monkeypatch, caplog):
    """The same, on the durable engine: the engine took the job before the note is written, so a
    journal that cannot be built must leave the start `ok` — a refusal there would tell the person
    no job runs while one does — and log one WARNING naming the job and the cause. Written with
    the mutation plan (2026-10-21): the durable call site was held only for writing the note, and a
    note written there outside `_journal_the_start`'s guard turned the started job into a failure
    with every other test green."""
    client = _engine(monkeypatch)
    monkeypatch.setenv("OPENFACTORY_EVENT_SINK", UNBUILDABLE_SINK)
    caplog.set_level("WARNING")

    out = await actions.perform("start", by=actions.SYSTEM, project="demo", issue="7",
                                durable=True, sandbox="container")

    assert out.ok and len(client.launched) == 1, out
    assert len(_not_journalled(caplog, "7")) == 1, [r.getMessage() for r in caplog.records]


async def test_a_scan_whose_journals_cannot_be_written_still_starts_every_card(
        scan_project, stored, monkeypatch, caplog):
    """`scan` writes one journal per card it started, inside its loop: a journal that cannot be
    built must not stop the next card from starting, nor turn the scan into a failure. Both cards
    start, and each is named in its own WARNING. Before #694: both started, nothing was logged."""
    from tests.test_the_action_layer import _FakeBoard

    monkeypatch.setattr("openfactory.adapters.board.build_board",
                        lambda *_a, **_kw: _FakeBoard(["1", "2"]))
    monkeypatch.setattr("openfactory.runtime.temporal.max_concurrent_jobs", lambda: 5)
    client = _engine(monkeypatch)
    monkeypatch.setenv("OPENFACTORY_EVENT_SINK", UNBUILDABLE_SINK)
    caplog.set_level("WARNING")

    out = await actions.perform("scan", by=actions.SYSTEM, project="demo")

    assert out.ok and out.data["started"] == ["1", "2"] and len(client.launched) == 2, out
    assert [len(_not_journalled(caplog, i)) for i in ("1", "2")] == [1, 1], (
        [r.getMessage() for r in caplog.records])
