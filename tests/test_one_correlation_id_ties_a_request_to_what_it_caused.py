"""One correlation id ties a request to every record it caused (#694, criterion 5, the record half).

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
    """The deployment's store, read back: the `memory` metrics sink named as an operator names one,
    its builder pinned to ONE instance so what `perform` wrote is still there when the test reads
    it (the shipped builder makes a fresh, empty store per call)."""
    from openfactory.observability import registry as sinks
    from openfactory.observability.metrics import InMemoryMetricsSink

    sink = InMemoryMetricsSink()
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "memory")
    monkeypatch.setitem(sinks.METRICS_SINKS, "memory", lambda **_kw: sink)
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
