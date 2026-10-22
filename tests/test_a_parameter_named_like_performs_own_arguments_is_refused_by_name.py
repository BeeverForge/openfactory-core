"""A parameter named `by` or `name` is refused by name and leaves its record, at every door (#694,
PR #1039 review N1).

WHAT WAS TRUE BEFORE. Both doors spread the parameters a caller sent into
`perform(name, *, by, **params)`, so a body naming `by` or `name` collided with `perform`'s own
arguments before it ran: measured by the review on c310ba28, `POST /api/act/product_status
{"params":{"project":"x","by":"mallory"}}` answered 500 (`TypeError: perform() got multiple values
for keyword argument 'by'`), and `openfactory act product_status -P project=nosuch -P by=mallory`
ended in that traceback — and neither call left a record. It is the one way a call at the action
door left no trace.

WHAT HOLDS NOW: the doors hand `perform` the parameters as one mapping (`params=`), so a name a
caller chose never meets `perform`'s own; the row refuses it as any parameter it does not take
(`bad_parameters`, naming it), and the call leaves one record.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from openfactory.observability.sqlite_metrics import SqliteMetricsSink


@pytest.fixture
def store(tmp_path, monkeypatch) -> SqliteMetricsSink:
    for name in ("OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_IDENTITY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(tmp_path / "metrics.db"))
    return SqliteMetricsSink(tmp_path / "metrics.db")


def _records(store: SqliteMetricsSink) -> list[dict]:
    return [r["extra"] for r in store.scan() if r.get("kind") == "audit"]


@pytest.mark.parametrize("reserved", ["by", "name"])
def test_the_panel_refuses_a_parameter_named_like_performs_own_and_records_the_call(store,
                                                                                   reserved):
    """N1 at the HTTP door: the body's `by` (or `name`) is a parameter the row does not take, so
    the answer is a 400 naming it, and the call leaves one record. On c310ba28: 500, `perform()
    got multiple values for keyword argument 'by'`, and no record."""
    from openfactory.api.app import app

    answer = TestClient(app, raise_server_exceptions=False).post(
        "/api/act/product_status", json={"params": {"project": "x", reserved: "mallory"}})

    assert answer.status_code == 400, (answer.status_code, answer.text)
    assert reserved in answer.json()["message"], answer.json()
    [record] = _records(store)
    assert (record["action"], record["reason"], record["params"][reserved]) == (
        "product_status", "bad_parameters", "mallory"), record


@pytest.mark.parametrize("reserved", ["by", "name"])
def test_the_command_line_refuses_a_parameter_named_like_performs_own_and_records_the_call(
        store, reserved):
    """N1 at the CLI door: `openfactory act product_status -P project=nosuch -P by=mallory`
    refuses by name (exit 1, the refusal naming `by`), not with a traceback, and leaves one
    record. On c310ba28 it ended in `TypeError` and left none."""
    from openfactory.cli import app

    done = CliRunner().invoke(app, ["act", "product_status", "-P", "project=nosuch",
                                    "-P", f"{reserved}=mallory"])

    assert done.exit_code == 1 and done.exception is None or isinstance(
        done.exception, SystemExit), (done.exit_code, repr(done.exception), done.output)
    assert f"does not take {reserved}" in done.output, done.output
    [record] = _records(store)
    assert (record["reason"], record["params"][reserved]) == ("bad_parameters", "mallory"), record


async def test_a_keyword_wins_over_the_same_name_in_the_mapping(store):
    """`perform`'s docstring promises that keywords and `params` merge, the keywords winning: code
    that names a parameter itself is not overridden by what a door handed on. No caller passes
    both today, and on 58cbd307 swapping the merge left every test green (branch review,
    2026-10-22)."""
    from openfactory import actions

    await actions.perform("product_status", by=actions.SYSTEM, params={"project": "a"},
                          project="b")

    [record] = _records(store)
    assert record["project"] == "b", record
