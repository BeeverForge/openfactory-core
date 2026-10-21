"""Every call into the action layer leaves one durable, typed record of who asked and what came of
it (#694).

WHAT WAS TRUE BEFORE. `actions.perform` is the one gate every transport goes through, and its only
record of who asked was one INFO line (`action=… by=…`). Eight of its nine return paths never wrote
it (the unknown action, bad parameters, a bad ref, both denials, the engine not answering, a row
that raised, a row that reported nothing), and nothing durable held it at all: measured on bb929e49
with an empty `HOME` and a temp registry, `openfactory act product_status -p nosuch` printed only
the refusal, and the line reached nobody. *Who approved that production release* had no answer an
auditor could read back.

WHAT HOLDS NOW, in this file: the record is a type with every field the issue names (read off the
type, not its source), it cannot be changed once made, and it names the product a project belongs
to when there is one, and the identity provider that named the caller is the one the transport
resolved — the panel's provider, or the shell login on the command line. And `perform` leaves
exactly one record in the deployment's store on every way out of it — each reason it can refuse
with, a row's own refusal and success, the set read off the reasons it exports — and a row that
relays to another leaves one per call under the caller's one correlation id.
"""

from __future__ import annotations

import dataclasses

import pytest

from openfactory import actions
from openfactory.actions import base
from openfactory.contracts.project import Project
from openfactory.product.key import product_key
from openfactory.registry import ProjectRegistry

#: The fields #694's first criterion lists, in its words: who (id and display), through which
#: identity provider and which transport, what (the action and its parameters, redacted), what came
#: of it (ok, code, reason), and the correlation, deployment, project, product and time.
THE_ISSUES_FIELDS = frozenset({
    "actor_id", "actor_display", "provider", "via", "action", "params", "ok", "code", "reason",
    "correlation_id", "deployment", "project", "product", "ts",
})


def _record(params: dict | None = None, outcome: actions.Outcome | None = None):
    """One record made the way `perform` makes it: from the action's name, who asked, what they
    passed and what came back."""
    from openfactory.observability.audit import AuditRecord

    by = actions.Actor(id="alice", display="Alice Ferreira", via="panel")
    return AuditRecord.of("product_status", by, params if params is not None else {"project": "x"},
                          outcome or actions.done("fine"))


@pytest.fixture
def registry(tmp_path, monkeypatch) -> ProjectRegistry:
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    return ProjectRegistry()


def test_the_audit_record_carries_every_field_the_issue_names():
    """Criterion 1: a typed record with actor id and display, identity provider and transport,
    action, redacted parameters, outcome ok, code and reason, correlation id, deployment, project,
    product and time. Before #694 there was no such type (`openfactory.observability.audit` did not
    exist) and the only record was a log line."""
    from openfactory.observability.audit import AuditRecord

    assert dataclasses.is_dataclass(AuditRecord)
    missing = THE_ISSUES_FIELDS - {f.name for f in dataclasses.fields(AuditRecord)}
    assert not missing, f"the audit record lacks {sorted(missing)}"


def test_an_audit_record_cannot_be_changed_once_it_is_made():
    """Criterion 1, "immutable": a record that a later step could rewrite is not a record of what
    happened. Every field refuses assignment, and the parameters are a read-only mapping, so even
    the one mutable-looking value cannot be edited in place."""
    record = _record({"project": "x", "issue": "7"})

    for f in dataclasses.fields(record):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(record, f.name, getattr(record, f.name))
    with pytest.raises(TypeError):
        record.params["x"] = 1  # type: ignore[index]


def test_a_project_with_a_product_names_it_and_one_without_leaves_it_empty(registry):
    """Criterion 1, "product when there is one": a registry project linked to a context repository
    is recorded under its product (`product_key`, ADR-0051 — the key its conversations and memory
    share), one with no `product:` section leaves the field empty rather than inventing a product
    of one, and a name the registry does not know is recorded as asked, never a raise — `perform`
    must leave a record for exactly that refusal."""
    for name in ("linked", "alone"):
        registry.add(Project(name=name, repo_path=f"https://github.com/acme/{name}.git"))
    registry.set_docs_repo("linked", "acme/linked-docs")
    linked = registry.get("linked")
    assert linked.product is not None and product_key(linked).startswith("repo:")

    assert _record({"project": "linked"}).product == product_key(linked)
    assert _record({"project": "alone"}).product == ""
    nobody = _record({"project": "nosuch"}, actions.refused(actions.NOT_FOUND, "no such project"))
    assert (nobody.project, nobody.product) == ("nosuch", "")


def test_a_long_value_is_kept_to_its_bound_and_the_cut_is_said(caplog):
    """Criterion 1's record is held by a store that writes one row per call, and a parameter's
    value is whatever a caller sent: before this bound a 5,000-character `target` was kept whole,
    in every row a refused call left. Now a value is kept to its first 2,000 characters (#694 Q11)
    with a marker saying how many were cut, and the cut is logged naming the action and the
    parameter — a silent truncation reads as "that was everything" (engineering-lessons §6)."""
    sent = "a" * 2_000 + "b" * 3_000

    with caplog.at_level("INFO", logger="openfactory.observability.audit"):
        kept = _record({"project": "x", "target": sent}).params["target"]

    assert isinstance(kept, str) and kept.startswith("a" * 2_000) and "b" not in kept[:2_000], kept
    assert len(kept) < len(sent) and "3000" in kept, kept
    said = [r.getMessage() for r in caplog.records if "target" in r.getMessage()]
    assert any("product_status" in line and "5000" in line for line in said), said


# ── which identity provider named the caller ─────────────────────────────────────────────────────


@pytest.fixture
def recorded(monkeypatch):
    """The records the calls made in this test leave, in order.

    Wraps the real `actions.perform` — which every transport reaches through the module attribute
    (`api/app.py::act`, `cli.py::act_cmd`) — and makes the record from exactly what it was given
    and what it returned, as `perform` itself does (`AuditRecord.of(name, by, params, outcome)`).
    What this holds is what the TRANSPORT put on `by`; that `perform` writes the record on every
    path is the parametrised test's claim, not this one's."""
    from openfactory.observability.audit import AuditRecord

    real = actions.perform
    out: list = []

    async def spy(name, *, by, **params):
        outcome = await real(name, by=by, **params)
        out.append(AuditRecord.of(name, by, params, outcome))
        return outcome

    monkeypatch.setattr(actions, "perform", spy)
    return out


def test_the_panel_records_which_identity_provider_named_the_caller(registry, recorded,
                                                                     monkeypatch):
    """Criterion 1, "identity provider and transport": through the real FastAPI app, a person's own
    token is recorded as the `local` provider's, and the shared token as `anonymous` — never the
    same word for both. Before #694 the panel resolved the `Subject` and dropped it in `_actor_of`
    (`Actor` had no field for it), so the record could only say `provider=""` for every caller."""
    from fastapi.testclient import TestClient

    from openfactory.api.app import app

    for name in ("OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_IDENTITY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKENS", "mine:alice:Alice Ferreira")
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", "shared")
    client = TestClient(app)

    for token in ("mine", "shared"):
        client.post("/api/act/product_status", json={"params": {"project": "nosuch"}},
                    headers={"Authorization": f"Bearer {token}"})

    assert [(r.action, r.via) for r in recorded] == [("product_status", "panel")] * 2, recorded
    alice, shared = recorded
    assert (alice.provider, alice.actor_id) == ("local", "alice"), alice
    assert (shared.provider, shared.actor_id) == ("anonymous", ""), shared


def test_the_command_line_records_the_shell_login_as_its_own_provider(registry, recorded,
                                                                      monkeypatch):
    """Criterion 1, for the CLI: `openfactory act` is recorded under the provider `cli` and the
    shell login, as ADR-0057 D1 spells the CLI's subject (`Subject(id=<shell login>, via="cli")`).
    Before #694 the CLI built a bare `Actor(via="cli")` with no subject, so the record said
    `provider=""` — indistinguishable from a transport that resolved nobody."""
    import getpass

    from typer.testing import CliRunner

    from openfactory.cli import app

    monkeypatch.setattr(getpass, "getuser", lambda: "carol")
    result = CliRunner().invoke(app, ["act", "product_status", "-p", "nosuch"])

    assert result.exit_code == 1, result.output  # the project is unknown: a refusal, recorded
    [record] = recorded
    assert (record.via, record.provider, record.actor_id) == ("cli", "cli", "carol"), record


# ── which deployment wrote the record ───────────────────────────────────────────────────────────


@pytest.fixture
def unnamed(monkeypatch):
    """A deployment that names itself nowhere: neither variable set."""
    for name in ("OPENFACTORY_DEPLOYMENT", "TEMPORAL_NAMESPACE"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_the_record_names_the_deployment_its_operator_named(unnamed):
    """Criterion 1, "deployment": an operator who runs more than one deployment against one store
    names each, and the record carries that name. Before #694 no deployment identifier existed in
    the tree, and the record wrote `deployment=""` for every call."""
    unnamed.setenv("OPENFACTORY_DEPLOYMENT", "acme-prod")
    unnamed.setenv("TEMPORAL_NAMESPACE", "acme.abc12")

    assert _record().deployment == "acme-prod"


def test_a_deployment_nobody_named_is_named_by_its_engine_namespace(unnamed):
    """Criterion 1, "deployment", with no name given: the record carries the namespace the engine
    connection uses (`runtime.temporal.connection.namespace()`, read here off the function itself),
    so two deployments on one Temporal account are still told apart — and with neither variable set
    it is that function's own default, never `""`. Before #694 it was `""` either way."""
    from openfactory.runtime.temporal import connection

    unnamed.setenv("TEMPORAL_NAMESPACE", "acme.abc12")
    assert _record().deployment == connection.namespace() == "acme.abc12"

    unnamed.delenv("TEMPORAL_NAMESPACE")
    assert _record().deployment == connection.namespace() != ""


def test_naming_the_deployment_does_not_import_the_engines_client():
    """The panel serves without the `runtime` extra (`tests/test_the_panel_serves_without_the_
    engines_client.py`) and makes a record on every action, so naming the deployment must not
    import `temporalio` — which `runtime.temporal.connection` does at its top. Run in a fresh
    interpreter: this one has imported the client already."""
    import subprocess
    import sys

    script = ("import sys; from openfactory.observability import audit; audit.deployment(); "
              "print(sorted(m for m in sys.modules if m.split('.')[0] == 'temporalio'))")
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                          timeout=60, check=False)

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]", done.stdout


# ── one record for every way out of `perform` ───────────────────────────────────────────────────


@pytest.fixture
def stored(monkeypatch):
    """The store this deployment writes its records to, read back: the `memory` metrics sink,
    named by `OPENFACTORY_METRICS_SINK` as an operator names one, with its builder pinned to ONE
    instance so what `perform` wrote is still there when the test reads it (the shipped builder
    makes a fresh, empty store per call).

    Read through the registry rather than a spy on `perform`, because the claim is that the record
    REACHES the store — a spy that built the record itself (as `recorded` does above) would be
    green on a `perform` that wrote nothing."""
    from openfactory.observability import registry as sinks
    from openfactory.observability.metrics import InMemoryMetricsSink

    sink = InMemoryMetricsSink()
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "memory")
    monkeypatch.setitem(sinks.METRICS_SINKS, "memory", lambda **_kw: sink)
    return sink


def _audit_rows(sink) -> list:
    return [rec for rec in sink.records if rec.kind == "audit"]


def _runs(outcome):
    """A row whose runner does exactly one thing — so a path `perform` takes AROUND the row (the
    engine not answering, the row raising, the row reporting nothing) can be driven without the
    row's own side effects."""
    async def runner(**_kw):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
    return runner


def _engine_down():
    from openfactory.runtime.temporal.vocabulary import EngineUnreachable

    return EngineUnreachable("the engine did not answer")


#: A row's own refusal, as opposed to one `perform` makes around it.
ROWS_OWN = "a_rows_own_refusal"

#: Every way out of `perform`, by the reason it says — each as (row, who asks, what they pass, the
#: runner that replaces the row's own, or None to run the real one). `skip` is the row driven
#: around: it takes an `issue` (so it can be refused a bad ref) and needs an admin.
_ADMIN = actions.Actor(id="op", display="Operator", via="panel", admin=True)
WAYS_OUT = {
    actions.UNKNOWN_ACTION: ("teleport", actions.SYSTEM, {}, None),
    actions.BAD_PARAMETERS: ("skip", actions.SYSTEM, {"project": "demo"}, None),
    actions.BAD_REF: ("skip", actions.SYSTEM, {"project": "demo", "issue": "../x"}, None),
    actions.OUT_OF_SCOPE: ("product_status",
                           actions.Actor(id="ba", via="panel", admin=True,
                                         scopes=frozenset({actions.FLOOR})),
                           {"project": "demo"}, None),
    actions.NOT_ADMIN: ("skip", actions.Actor(id="U9", via="slack"),
                        {"project": "demo", "issue": "1"}, None),
    actions.ENGINE_UNREACHABLE: ("skip", _ADMIN, {"project": "demo", "issue": "1"}, _engine_down),
    actions.RAISED: ("skip", _ADMIN, {"project": "demo", "issue": "1"},
                     lambda: RuntimeError("nope")),
    actions.REPORTED_NOTHING: ("skip", _ADMIN, {"project": "demo", "issue": "1"}, lambda: None),
    ROWS_OWN: ("product_status", actions.SYSTEM, {"project": "nosuch"}, None),
    "ok": ("skip", _ADMIN, {"project": "demo", "issue": "1"}, lambda: actions.done("skipped")),
}


@pytest.mark.parametrize("way_out", list(WAYS_OUT))
async def test_each_way_out_of_perform_leaves_one_record_and_only_one(way_out, registry, stored,
                                                                      monkeypatch):
    """Criterion 2: every call leaves exactly one record, on every path — the early refusals, both
    denials, the three ways a row can fail around its runner, a row's own refusal, and success —
    and the record says what the caller was told (`ok`, `code`, `reason` equal the `Outcome`'s).

    Before #694 `perform` wrote nothing durable on any path: the store received 0 records of kind
    `audit` for each of these ten calls, and the only trace was one INFO line written on two of
    them (a row's answer, a row's refusal) — the other eight left at most a WARNING."""
    from openfactory.actions import catalog

    name, by, params, runner = WAYS_OUT[way_out]
    if runner is not None:
        monkeypatch.setitem(catalog.CATALOG, name,
                            dataclasses.replace(catalog.CATALOG[name], run=_runs(runner())))

    outcome = await actions.perform(name, by=by, **params)

    said = outcome.data.get("reason", "")
    assert (outcome.ok, said) == ((True, "") if way_out == "ok" else
                                  (False, actions.NOT_FOUND if way_out == ROWS_OWN else way_out)), (
        f"the {way_out} case drove another path: {outcome}")
    rows = _audit_rows(stored)
    assert len(rows) == 1, f"{way_out}: {len(rows)} audit records for one call (1 expected)"
    [row] = rows
    assert (row.extra["ok"], row.extra["code"], row.extra["reason"]) == (
        outcome.ok, outcome.code, said), row.extra


def test_every_reason_perform_can_say_is_a_path_this_test_drives():
    """Criterion 2, kept true: the ways out above are read against the reasons `perform` exports
    (`UNKNOWN_ACTION` and `AROUND_EVERY_ROW`, `actions/base.py`), so a reason `perform` learns
    later is a path the parametrised test must drive — not one that skips the record unseen.
    Green before #694 by construction; it holds the table, not the record."""
    missing = {actions.UNKNOWN_ACTION, *base.AROUND_EVERY_ROW} - set(WAYS_OUT)

    assert not missing, f"perform can say {sorted(missing)}, and no case above drives it"


async def test_a_relayed_row_leaves_its_own_record_under_the_callers_correlation(
        registry, stored, monkeypatch):
    """Criterion 2, relays: a row that performs another row (`ask` answering a plain "yes" runs
    what the tech-lead staged, through `run_staged`, `actions/catalog.py`) is two calls, and leaves
    two records — one per action — under the ONE correlation id the caller carried, so an auditor
    can read the yes and the skip it caused as one request. Before #694 the store received 0
    records for either."""
    from openfactory.actions import catalog
    from openfactory.memory import messages as channel

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
                        dataclasses.replace(catalog.CATALOG["skip"],
                                            run=_runs(actions.done("skipped"))))
    by = dataclasses.replace(_ADMIN, correlation="req-7f3a")

    outcome = await actions.perform("ask", by=by, project="demo", question="sim")

    assert outcome.ok and outcome.data.get("action") == "skip", outcome  # the relay happened
    rows = _audit_rows(stored)
    assert sorted(r.extra["action"] for r in rows) == ["ask", "skip"], rows
    assert {r.extra["correlation_id"] for r in rows} == {"req-7f3a"}, rows


async def test_a_cancelled_call_still_leaves_one_record(registry, stored, monkeypatch):
    """Criterion 2, the way out no `return` takes: a call cancelled while its row runs (a panel
    request whose client hung up, a worker shutting down) is still a call, and leaves one record
    saying it did not finish — `ok` false, code `failed`, reason `cancelled` — while the
    `CancelledError` reaches the caller unchanged, so whoever cancelled it still sees the cancel.

    Before #694 the store received 0 records for it: `perform` wrote its one INFO line only after
    the row returned, and a cancelled row never returns."""
    import asyncio

    from openfactory.actions import catalog

    started = asyncio.Event()

    async def hangs(**_kw):
        started.set()
        await asyncio.Event().wait()  # nobody sets it: only the cancel ends this row

    monkeypatch.setitem(catalog.CATALOG, "skip",
                        dataclasses.replace(catalog.CATALOG["skip"], run=hangs))
    call = asyncio.ensure_future(actions.perform("skip", by=_ADMIN, project="demo", issue="1"))
    await started.wait()
    call.cancel()

    with pytest.raises(asyncio.CancelledError):
        await call
    rows = _audit_rows(stored)
    assert len(rows) == 1, f"cancelled: {len(rows)} audit records for one call (1 expected)"
    assert (rows[0].extra["ok"], rows[0].extra["code"], rows[0].extra["reason"]) == (
        False, actions.FAILED, "cancelled"), rows[0].extra


async def test_a_call_that_raises_outside_the_rows_guard_leaves_one_record_and_raises(
        registry, stored, monkeypatch):
    """Criterion 2, the last way out: an exception `_decide` raises outside the row's own guard
    (here the catalog failing to load) is no answer, so `perform` lets it go on to the caller —
    and still leaves one record of the call, `ok` false, code `failed`, reason `raised`, so the
    trail holds the call that failed rather than nothing. Written with the mutation plan
    (2026-10-20): `perform`'s `outcome is None` branch had no test, and returning from the
    `finally` there without a record left the suite green."""
    def broken() -> dict:
        raise RuntimeError("the catalog did not load")

    monkeypatch.setattr(actions, "_catalog", broken)

    with pytest.raises(RuntimeError, match="the catalog did not load"):
        await actions.perform("skip", by=_ADMIN, project="demo", issue="1")
    rows = _audit_rows(stored)
    assert len(rows) == 1, f"raised outside the guard: {len(rows)} audit records (1 expected)"
    assert (rows[0].extra["ok"], rows[0].extra["code"], rows[0].extra["reason"]) == (
        False, actions.FAILED, actions.RAISED), rows[0].extra


# ── the INFO line shows what the record keeps ───────────────────────────────────────────────────


#: A client's words, as a `product_say` message carries them — measured in the line on the #694
#: branch at 4b644c36, before the line logged what the record keeps.
_WORDS = "my salary is 9000 and my CPF is 123"


def _the_line(caplog) -> tuple[str, dict]:
    """The one `action=` line the call wrote, and the parameters it printed, read back as the
    value they are (`ast.literal_eval` of what follows `params=`), not searched for as text."""
    import ast

    lines = [r.getMessage() for r in caplog.records
             if r.levelname == "INFO" and r.getMessage().startswith("action=")]
    assert len(lines) == 1, f"{len(lines)} action lines for one call (1 expected): {lines}"
    return lines[0], ast.literal_eval(lines[0].split(" params=", 1)[1])


#: Three ways out, each carrying a person's words: refused before any check of who asked (an
#: unexpected `password`, so a secret rides along), refused for the caller's scope, and answered
#: by the row itself.
_WORDS_WAYS = {
    actions.BAD_PARAMETERS: (actions.SYSTEM,
                             {"project": "nosuch", "message": _WORDS, "password": "hunter2"}),
    actions.OUT_OF_SCOPE: (actions.Actor(id="ba", via="panel", admin=True,
                                         scopes=frozenset({actions.FLOOR})),
                           {"project": "nosuch", "message": _WORDS}),
    ROWS_OWN: (actions.SYSTEM, {"project": "nosuch", "message": _WORDS}),
}


@pytest.mark.parametrize("way_out", list(_WORDS_WAYS))
async def test_the_info_line_shows_a_persons_words_only_as_the_record_keeps_them(
        way_out, registry, stored, caplog):
    """Criterion 6 and the human's decision of 2026-10-21 (option b): the INFO line beside the
    record prints the parameters as the record keeps them — a `FREE_TEXT` value as its length and
    sha256, a `SECRET` value as `***` — on every way out, so the line and the record are one view.

    Before, on this branch at 4b644c36, the line printed `audit.redact(params)`, which masks
    secrets only: `params={'project': 'nosuch', 'message': 'my salary is 9000 and my CPF is
    123', …}` beside a record holding `{'chars': 35, 'sha256': …}` — and #694 had made the line
    run on all ten ways out, so a refusal before any row wrote the words to stderr too. Red on
    all three ways out then: `a person's words reached a log line`."""
    import hashlib

    by, params = _WORDS_WAYS[way_out]

    with caplog.at_level("INFO"):
        outcome = await actions.perform("product_say", by=by, **params)

    said = outcome.data.get("reason", "")
    assert said == (actions.NOT_FOUND if way_out == ROWS_OWN else way_out), outcome
    # THE DENIALS' OWN WARNING (`DENIED_SCOPE …`, `DENIED …`) predates #694 and still prints
    # `audit.redact(params)`: the decision was about the action's line, and that warning is a
    # follow-up of its own (*The denial warnings log a person's words in full*).
    leaked = [r.getMessage() for r in caplog.records
              if _WORDS in r.getMessage() and not r.getMessage().startswith("DENIED")]
    assert not leaked, f"a person's words reached a log line: {leaked}"
    assert "hunter2" not in caplog.text
    _line, printed = _the_line(caplog)
    assert printed["message"] == {"chars": len(_WORDS),
                                  "sha256": hashlib.sha256(_WORDS.encode()).hexdigest()}, printed
    if "password" in params:
        assert printed["password"] == "***", printed
    [row] = _audit_rows(stored)
    assert printed == row.extra["params"], (printed, row.extra["params"])


async def test_a_value_cut_for_the_record_is_cut_in_the_line_and_the_cut_is_said_once(
        registry, stored, caplog):
    """The line and the record are made from one view of the parameters (`audit._kept`), computed
    once per call: a 5,000-character value is printed in the line as the record keeps it, cut to
    its first 2,000 characters with the cut said, and the INFO line saying it was cut is written
    once — not once for the line and again for the record.

    Before, on this branch at 4b644c36, the line printed the 5,000 characters whole."""
    sent = "c" * 5_000

    with caplog.at_level("INFO"):
        await actions.perform("product_say", by=actions.SYSTEM, project="nosuch", message="hi",
                              context=sent)

    _line, printed = _the_line(caplog)
    [row] = _audit_rows(stored)
    assert printed["context"] == row.extra["params"]["context"], printed["context"][-60:]
    assert len(printed["context"]) < len(sent), len(printed["context"])
    cut = [r.getMessage() for r in caplog.records
           if r.name == "openfactory.observability.audit" and "context was 5000" in r.getMessage()]
    assert len(cut) == 1, f"the cut was said {len(cut)} times for one call (1 expected): {cut}"


class _Unreadable:
    """A parameter value that cannot be turned into text — what an internal caller could hand
    `perform`, and the one way `audit._kept` can fail."""

    def __str__(self) -> str:
        raise ValueError("this value cannot be read")

    __repr__ = __str__


async def test_parameters_that_cannot_be_read_leave_the_line_saying_so_and_the_outcome_stands(
        registry, stored, caplog):
    """The line is written on every way out even when the parameters cannot be read as the record
    keeps them: it says so in their place, a WARNING names the record that was not kept, and the
    caller still gets the row's answer — never the parameters as sent, and never an exception.

    Before, on this branch at 4b644c36, the line was lost: formatting it raised in the handler, a
    stream handler printed `--- Logging error --- … ValueError: this value cannot be read` in its
    place (measured 2026-10-21), and pytest's capture re-raised it out of `perform`."""
    with caplog.at_level("INFO"):
        outcome = await actions.perform("product_say", by=actions.SYSTEM, project="nosuch",
                                        context=_Unreadable())

    assert outcome.data.get("reason") == actions.NOT_FOUND, outcome
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("action="))
    assert line.endswith("params=<not shown: they could not be read (this value cannot be read)>"), (
        line)
    warned = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"
              and "record of product_say" in r.getMessage()]
    assert len(warned) == 1, warned
    assert _audit_rows(stored) == []


async def test_words_holding_a_lone_surrogate_are_still_kept_as_their_length_and_digest(
        registry, stored, caplog):
    """A JSON body may carry a lone surrogate (`"\\ud800"` decodes to a `str` Python cannot
    encode as UTF-8), and a panel caller's message is whatever they sent: it is still kept as its
    length and digest, in the line and in the record, and the call is recorded.

    Before, on this branch at 5be3fa0e, `audit._words` encoded it strictly and raised
    `UnicodeEncodeError: … surrogates not allowed`: the line said the parameters could not be
    read and the store received 0 records of the call."""
    import re

    words = "hello \ud800 there"

    with caplog.at_level("INFO"):
        await actions.perform("product_say", by=actions.SYSTEM, project="nosuch", message=words)

    rows = _audit_rows(stored)
    assert len(rows) == 1, f"{len(rows)} audit records for one call (1 expected)"
    kept = rows[0].extra["params"]["message"]
    assert kept["chars"] == len(words) and re.fullmatch(r"[0-9a-f]{64}", kept["sha256"]), kept
    _line, printed = _the_line(caplog)
    assert printed["message"] == kept, printed


def test_a_registry_that_cannot_be_read_names_the_product_unread_not_none(tmp_path, monkeypatch):
    """Criterion 1's "product when there is one", and lesson §2: "the registry did not answer" and
    "this project belongs to no product" never share a value — an unreadable registry gives
    `PRODUCT_UNREAD`, not `""`. No test held it: the branch review's cut answering `""` there
    survived 133 tests."""
    from openfactory.observability.audit import PRODUCT_UNREAD, _product_of

    bad = tmp_path / "registry.yaml"
    bad.write_text("projects: [: not yaml\n")
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(bad))

    assert _product_of("demo") == PRODUCT_UNREAD
