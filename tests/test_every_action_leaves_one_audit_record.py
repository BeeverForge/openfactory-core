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
to when there is one.
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
