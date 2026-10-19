"""A registry that spans two organisations fails `openfactory doctor`, in the load path's words (#743, S2).

`ProjectRegistry.add` refuses a project in a second GitHub organisation, but a hand-edited or
seeded registry can still hold two, and `ProjectRegistry.list` only logs
`OPENFACTORY_REGISTRY_SPANS_INSTALLATIONS` — deliberately, because raising on the poller's tick
would turn one stale line into an outage for every project. Before #743 that log line was the only
place it was said: `openfactory doctor` read such a deployment as "OK — can run a ticket", while
every forge read outside the installation's organisation 404'd. And the docstring that explains
why `list` only logs promised a doctor check that did not exist.

These tests read the registry through the REAL probe `doctor.probes_for` builds, with no App
configured (conftest strips every `OPENFACTORY_*` variable first), from a hand-written YAML file —
the shape `add` refuses to write and `list` still loads.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import re

import yaml

from openfactory import doctor, registry
from openfactory.registry import ProjectRegistry
from tests.pinned_probes import a_fully_pinned_probe_set


def _hand_written(tmp_path, monkeypatch, projects: dict[str, str]):
    """`{name: "owner/repo"}` written as YAML (as `add` would refuse to), named by
    `OPENFACTORY_REGISTRY` so the probe reads it; returns the path."""
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"projects": {
        name: {"name": name, "repo_path": f"/tmp/{name}",
               "tracker": {"kind": "github", "repo": repo}}
        for name, repo in projects.items()}}))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(path))
    return path


def _line_from_the_live_probe(path) -> doctor.Finding:
    project = ProjectRegistry(path).list()[0]
    probes = dataclasses.replace(
        a_fully_pinned_probe_set(),
        installation_scope=doctor.probes_for(project).installation_scope)
    return next(f for f in doctor.diagnose(probes).findings
                if f.check == doctor.INSTALLATION_SCOPE)


def test_a_spanning_registry_fails_doctor_with_the_sentence_the_load_logs(
        tmp_path, monkeypatch, caplog):
    """S2: "What `_warn_if_spanning` logs becomes a doctor failure with the same sentence"; T: "A
    spanning registry fails doctor". The sentence is the value the code exports, compared whole —
    and the load path still logs it, so the doctor line replaces nothing."""
    path = _hand_written(tmp_path, monkeypatch, {"api": "acme/api", "web": "othercorp/web"})
    expected = registry.spanning_message(
        registry.spanning_installations(ProjectRegistry(path).list()))

    caplog.clear()
    with caplog.at_level("ERROR"):
        finding = _line_from_the_live_probe(path)

    assert finding.ok is False
    assert finding.message == expected
    assert finding.remedy.strip()
    assert "OPENFACTORY_REGISTRY_SPANS_INSTALLATIONS" in caplog.text, "the load path stopped logging"


def test_a_spanning_registry_fails_doctor_with_no_app_configured(tmp_path, monkeypatch):
    """S2 does not need an App: the registry alone says it spans, and asking GitHub would spend a
    network read on a question the spanning sentence already answers."""
    from openfactory import credentials

    asked: list[str] = []

    def _never_asked():
        asked.append("installed_on")
        raise AssertionError("the App was asked about a registry that already spans")

    real_row = credentials._row

    def _row(kind):
        row = real_row(kind)
        if kind == credentials._REFERENCE_KIND and row is not None:
            return dataclasses.replace(row, installed_on=_never_asked)
        return row

    monkeypatch.setattr(credentials, "_row", _row)
    path = _hand_written(tmp_path, monkeypatch, {"api": "acme/api", "web": "othercorp/web"})

    finding = _line_from_the_live_probe(path)

    assert finding.ok is False
    assert finding.message == registry.spanning_message(
        registry.spanning_installations(ProjectRegistry(path).list()))
    assert asked == []


def test_a_registry_in_one_organisation_is_not_reported_as_spanning(tmp_path, monkeypatch):
    """The positive twin: a registry in one organisation, no App — the line passes (as not
    applicable) and says nothing about spanning."""
    path = _hand_written(tmp_path, monkeypatch, {"api": "acme/api", "web": "acme/web"})

    finding = _line_from_the_live_probe(path)

    assert finding.ok is True, finding.message
    assert "spans" not in finding.message, finding.message


def test_the_check_the_registry_promises_is_a_check_doctor_runs():
    """The registry's `_warn_if_spanning` docstring names the doctor check that fails a spanning
    registry. Before #743 it named `installation_scope`, and `diagnose` ran no such check. The id is
    read from the docstring (parsed, not searched in the file's text) and from `doctor`'s constant."""
    ids = {f.check for f in doctor.diagnose(a_fully_pinned_probe_set()).findings}
    assert doctor.INSTALLATION_SCOPE in ids, sorted(ids)

    tree = ast.parse(inspect.getsource(registry))
    method = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "_warn_if_spanning")
    promised = re.findall(r"`(\w+)` (?:check|line)", ast.get_docstring(method) or "")
    assert promised, "the docstring no longer names the doctor check"
    assert set(promised) == {doctor.INSTALLATION_SCOPE}, promised
