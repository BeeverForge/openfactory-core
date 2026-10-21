"""The doors that change the deployment without going through `perform` leave one audit record
each, in the record's own shape (#694, PR #1039 review, hermesfelipe's follow-up).

WHAT WAS TRUE BEFORE. `POST /api/projects`, `POST /api/messages/{project}/answer` and the command
line's `project add`, `project init`, `init`, `product init` and `approver add` call no catalog
row, so they left no record at all: read off the parsed tree at ade4f5a1 (none calls
`perform`), and by hand `openfactory project add demo <repo>` printed `registered project 'demo'`
and `openfactory audit` then said `audit.db … holds no audit record yet`.

WHAT HOLDS NOW: each door is wrapped in `actions.door_recorded(name, by=…, params=…)`, which
leaves the INFO line and the record `perform` leaves — the same `_leave_record` — once, whatever
way the door ends: `ok` when it returned, `failed` with the HTTP status or the exit code when it
refused, `raised` when it raised. One test per door; each reads the store the record went to.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

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
    monkeypatch.setenv("OPENFACTORY_APPROVERS_FILE", str(tmp_path / "approvers.json"))
    return SqliteMetricsSink(tmp_path / "metrics.db")


def _the_record(store: SqliteMetricsSink) -> dict:
    """The one audit record the door left."""
    records = [r["extra"] for r in store.scan() if r.get("kind") == "audit"]
    assert len(records) == 1, f"{len(records)} audit records for one call at a door (1 expected)"
    return records[0]


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _cli(*args: str, input: str | None = None):
    from openfactory.cli import app

    return CliRunner().invoke(app, list(args), input=input)


def test_registering_a_project_on_the_panel_leaves_one_record(store, tmp_path):
    """`POST /api/projects` registers a project; it leaves one `project_add` record by the panel's
    caller, `ok`, with what was asked. On c310ba28 it left none."""
    from openfactory.api.app import app

    answer = TestClient(app).post("/api/projects", json={
        "name": "demo", "repo_path": str(_repo(tmp_path))})

    assert answer.status_code == 200, answer.text
    record = _the_record(store)
    assert (record["action"], record["via"], record["ok"], record["params"]["name"]) == (
        "project_add", "panel", True, "demo"), record


def test_answering_a_question_on_the_panel_leaves_one_record(store):
    """`POST /api/messages/{project}/answer` is a person's decision; even refused (no token) it
    leaves one `message_answer` record, `failed` with the status the door answered. On c310ba28
    it left none."""
    from openfactory.api.app import app

    answer = TestClient(app).post("/api/messages/demo/answer", json={"answer": "approve"})

    assert answer.status_code == 400, answer.text
    record = _the_record(store)
    assert (record["action"], record["project"], record["ok"], record["reason"]) == (
        "message_answer", "demo", False, "http_400"), record


def test_adding_a_project_on_the_command_line_leaves_one_record(store, tmp_path):
    """`openfactory project add demo <repo>`: one `project_add` record by the shell login, `cli`.
    On c310ba28: `registered project 'demo'`, and no record."""
    done = _cli("project", "add", "demo", str(_repo(tmp_path)))

    assert done.exit_code == 0, done.output
    record = _the_record(store)
    assert (record["action"], record["via"], record["provider"], record["ok"]) == (
        "project_add", "cli", "cli", True), record


@pytest.mark.parametrize(("args", "action"), [
    pytest.param(("project", "init", "nosuch"), "project_init", id="project_init"),
    pytest.param(("product", "init", "nosuch"), "product_init", id="product_init"),
    pytest.param(("init", "--runtime", "nosuch-runtime"), "init", id="init"),
])
def test_a_command_line_door_that_refuses_still_leaves_one_record(store, args, action):
    """`project init`, `product init` and `init`, each refused before it changes anything (a
    project nobody registered, a runtime no row answers to): one record each, `failed` with the
    exit code. On c310ba28 each left none."""
    done = _cli(*args)

    assert done.exit_code != 0, done.output
    record = _the_record(store)
    assert (record["action"], record["ok"], record["reason"]) == (
        action, False, f"exit_{done.exit_code}"), record


def test_adding_an_approver_leaves_one_record_and_never_the_password(store):
    """`openfactory approver add bob`: one `approver_add` record naming the login, and the
    password typed at the prompt is in neither the record nor the store's file. On c310ba28 it
    left no record."""
    done = _cli("approver", "add", "bob", input="fictitious-approver-pw\nfictitious-approver-pw\n")

    assert done.exit_code == 0, done.output
    record = _the_record(store)
    assert (record["action"], record["params"], record["ok"]) == (
        "approver_add", {"login": "bob"}, True), record
    assert b"fictitious-approver-pw" not in store.path.read_bytes()
