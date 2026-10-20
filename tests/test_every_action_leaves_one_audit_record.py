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
resolved — the panel's provider, or the shell login on the command line.
"""

from __future__ import annotations

import dataclasses

import pytest

from openfactory import actions
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
