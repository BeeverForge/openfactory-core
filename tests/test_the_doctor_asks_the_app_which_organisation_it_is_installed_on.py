"""The doctor asks the App which organisation it is installed on, and compares (#743, S1).

One deployment authenticates as one GitHub App installation, and an installation belongs to one
account. `ProjectRegistry.add` refuses a registry that would span two organisations, and the
registry's `_warn_if_spanning` docstring promised "`doctor`'s `installation_scope` check" to tell
a registry from an installation on another account. Before #743 no such check existed:
`doctor.diagnose` emitted no `installation_scope` line, so an App installed on `othercorp` serving
a registry of `acme` projects read "OK — can run a ticket" and 404'd on every forge read.

Every test here goes through `doctor.diagnose` over a fully pinned probe set
(`tests/pinned_probes.py`), with the one probe it measures answering a `doctor.InstallationScope`.
The reasons below are the ones `github_app.installation_account` gives for what GitHub answered on
2026-10-19 (no `Authorization` → `401 Requires authentication`; a JWT for an App GitHub does not
know → `404 Integration not found`; an unroutable host → a timeout).
"""

from __future__ import annotations

import json

import pytest

from openfactory import doctor
from tests.pinned_probes import a_fully_pinned_probe_set


def _scope(by_owner: dict[str, list[str]], installed) -> doctor.Finding:
    probes = a_fully_pinned_probe_set(installation_scope=lambda: doctor.InstallationScope(
        by_owner=by_owner, installed=installed))
    report = doctor.diagnose(probes)
    return next(f for f in report.findings if f.check == doctor.INSTALLATION_SCOPE)


def test_an_installation_on_another_organisation_fails_naming_both_and_the_repair():
    """S1: "fails with a sentence naming both, and the repair"; T: "A fake installation on another
    organisation fails the check". Before #743 the line did not exist and the report was green."""
    probes = a_fully_pinned_probe_set(installation_scope=lambda: doctor.InstallationScope(
        by_owner={"acme": ["api", "web"]}, installed=("othercorp", "")))
    report = doctor.diagnose(probes)
    finding = next(f for f in report.findings if f.check == doctor.INSTALLATION_SCOPE)

    assert finding.ok is False
    for word in ("othercorp", "acme", "api", "web"):
        assert word in finding.message, (word, finding.message)
    assert "one deployment per organisation" in finding.remedy, finding.remedy
    assert "api" in finding.remedy and "web" in finding.remedy, finding.remedy
    assert report.ok is False
    assert doctor.verdict(report, "demo").kind == "not_ready"


def test_the_organisation_the_registry_names_passes():
    """T: "The matching organisation passes" — and says which account it read."""
    finding = _scope({"acme": ["api", "web"]}, ("acme", ""))

    assert finding.ok is True, finding.message
    assert "acme" in finding.message


def test_the_organisation_is_compared_as_github_compares_logins_without_case():
    """GitHub logins are case-insensitive: `Acme/api` in the registry and an installation on
    `acme` are the same account. A case-sensitive comparison would fail a correct deployment."""
    finding = _scope({"Acme": ["api"]}, ("acme", ""))

    assert finding.ok is True, finding.message


@pytest.mark.parametrize("reason", [
    "https://api.github.com/app/installations/55512345 did not answer within 10 s (timed out)",
    "401 Requires authentication",
    "404 Integration not found",
    "404 Not Found",
])
def test_an_installation_that_could_not_be_read_is_not_a_pass(reason):
    """Lesson §2: "could not see" and "there is nothing wrong" never share a value. An App that is
    configured and could not be asked is a red line carrying the reason, never a green one."""
    finding = _scope({"acme": ["api"]}, (None, reason))

    assert finding.ok is False
    assert reason in finding.message, finding.message
    assert finding.remedy.strip(), "a failing line with no remedy"


def test_no_app_is_reported_as_not_applicable_and_not_as_a_verified_scope():
    """S1: "When no App is configured, it reports the check as not applicable rather than passing
    it". Decided 2026-10-19 (Q1-B): `openfactory.doctor/1` stays, so the result is `ok` and the
    line BEGINS with the not-applicable wording, naming no organisation as verified."""
    finding = _scope({"acme": ["api"]}, None)

    assert finding.ok is True
    assert finding.message.startswith(doctor.NOT_APPLICABLE), finding.message
    assert "acme" not in finding.message, "an organisation named as verified with no App to ask"


def test_a_registry_that_names_no_github_organisation_has_nothing_to_compare():
    """An App on `acme` and a registry with no GitHub project: nothing to disagree with, and the
    line says that nothing was compared rather than that a scope was verified."""
    finding = _scope({}, ("acme", ""))

    assert finding.ok is True
    assert "nothing" in finding.message.lower() and "compare" in finding.message.lower(), \
        finding.message


def test_the_check_is_a_line_of_the_json_document_under_its_own_id(tmp_path, monkeypatch):
    """S1: "It appears in `openfactory doctor --json` (`openfactory.doctor/1`) as a new check id"
    — through the real command, with the probe set pinned the way the contract test pins it."""
    from typer.testing import CliRunner

    from openfactory.cli import app

    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    runner = CliRunner()
    assert runner.invoke(app, ["project", "add", "demo", str(tmp_path)]).exit_code == 0
    monkeypatch.setattr(doctor, "probes_for", lambda _p: a_fully_pinned_probe_set())

    result = runner.invoke(app, ["doctor", "demo", "--json"])
    document = json.loads(result.stdout)

    assert document["schema"] == "openfactory.doctor/1"
    checks = {c["id"]: c for c in document["checks"]}
    assert doctor.INSTALLATION_SCOPE in checks, sorted(checks)
    assert checks[doctor.INSTALLATION_SCOPE]["result"] in doctor.RESULTS


def _line_from_the_live_probe(monkeypatch, project, env: dict[str, str]):
    """The REAL probe `probes_for` builds, over a registry holding `project`, with `env` set and
    `github_app.installation_account` stubbed to answer `othercorp`; `(finding, asked)` where
    `asked` lists every installation id the stub was asked about."""
    import dataclasses

    from openfactory.adapters import github_app
    from openfactory.registry import ProjectRegistry

    ProjectRegistry().add(project)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    asked: list[str] = []

    def installation_account(*, app_id, private_key, installation_id, **_kw):
        asked.append(installation_id)
        return "othercorp", ""

    monkeypatch.setattr(github_app, "installation_account", installation_account)
    probes = dataclasses.replace(
        a_fully_pinned_probe_set(),
        installation_scope=doctor.probes_for(project).installation_scope)
    finding = next(f for f in doctor.diagnose(probes).findings
                   if f.check == doctor.INSTALLATION_SCOPE)
    return finding, asked


_APP_TRIO = {"OPENFACTORY_GH_APP_ID": "7", "OPENFACTORY_GH_APP_KEY_CONTENT": "a key",
             "OPENFACTORY_GH_APP_INSTALLATION_ID": "7"}


def test_a_deployment_whose_github_projects_use_a_token_beside_the_app_is_not_applicable(
        monkeypatch):
    """Q5 (decided 2026-10-19: (a)): when a static token, not the App, is what every GitHub axis
    uses, the line is not applicable and asks the App nothing. Before, measured on d744ba8 with the
    App trio, `OPENFACTORY_BOT_TOKEN` and an installation on `othercorp`: the line FAILED a working
    deployment ("the GitHub App installation this deployment authenticates as is on othercorp …
    every forge read of those projects would 404"), told the operator to remove a working project,
    and asked installation 7 — while every forge read went through the token."""
    from openfactory import credentials
    from openfactory.contracts.project import Project, ProviderRef

    project = Project(name="demo", repo_path="/tmp/demo",
                      tracker=ProviderRef(kind="github", repo="acme/demo"))
    finding, asked = _line_from_the_live_probe(
        monkeypatch, project, {**_APP_TRIO, "OPENFACTORY_BOT_TOKEN": "ghp_stub"})

    assert finding.ok is True, finding.message
    assert finding.message.startswith(doctor.NOT_APPLICABLE), finding.message
    assert credentials.describe_source("generic:forge") in finding.message, finding.message
    assert asked == [], f"the App was asked about installation {asked} it does not serve"


def test_a_github_axis_that_still_uses_the_app_asks_the_app(monkeypatch):
    """The positive twin of the above: a token for the forge alone (`OPENFACTORY_FORGE_TOKEN`)
    leaves the GitHub tracker on the App, so the installation IS what reaches that project, and it
    is asked and compared — on `othercorp` against `acme`, a red line."""
    from openfactory.contracts.project import Project, ProviderRef

    project = Project(name="demo", repo_path="/tmp/demo",
                      tracker=ProviderRef(kind="github", repo="acme/demo"))
    finding, asked = _line_from_the_live_probe(
        monkeypatch, project, {**_APP_TRIO, "OPENFACTORY_FORGE_TOKEN": "ghp_forge_only"})

    assert asked == ["7"]
    assert finding.ok is False and "othercorp" in finding.message, finding.message


def test_a_token_on_the_tracker_alone_leaves_the_forge_on_the_app_and_the_app_is_asked(
        monkeypatch):
    """The mirror of the forge-only twin: `OPENFACTORY_TRACKER_TOKEN` answers the GitHub tracker,
    and the forge, with no token of its own, mints on the App — so the installation IS what every
    forge read goes through, and it is asked and compared."""
    from openfactory.contracts.project import Project, ProviderRef

    project = Project(name="demo", repo_path="/tmp/demo",
                      tracker=ProviderRef(kind="github", repo="acme/demo"))
    finding, asked = _line_from_the_live_probe(
        monkeypatch, project, {**_APP_TRIO, "OPENFACTORY_TRACKER_TOKEN": "ghp_tracker_only"})

    assert asked == ["7"]
    assert finding.ok is False and "othercorp" in finding.message, finding.message


def test_a_scope_probe_that_raises_is_a_red_line_not_a_crash():
    """The line's probe reads the whole registry, and a malformed sibling project makes `list()`
    raise `ValueError`. Measured in review round 1 on d744ba8: `doctor demo --json` then fails the
    line with `project 'broken' is invalid`; a cut that removed the `_guarded` wrapper survived
    every test, and would have crashed `doctor` with a traceback instead."""
    def boom():
        raise ValueError("registry.yaml: project 'x' is invalid")
    report = doctor.diagnose(a_fully_pinned_probe_set(installation_scope=boom))
    finding = next(f for f in report.findings if f.check == doctor.INSTALLATION_SCOPE)
    assert finding.ok is False and "is invalid" in finding.message


def test_an_app_that_is_not_fully_configured_is_said_as_such_and_not_as_no_app(
        monkeypatch, tmp_path):
    """Q4 holds (an incomplete trio is not asked), but the sentence must be true. Measured in
    review round 1 on d744ba8 with `OPENFACTORY_GH_APP_ID=1`, `OPENFACTORY_GH_APP_INSTALLATION_ID=1`
    and `OPENFACTORY_GH_APP_KEY` naming a missing file: the line said "not applicable — no GitHub
    App installation is configured for this deployment", beside an installation id that was."""
    from openfactory.contracts.project import Project, ProviderRef

    project = Project(name="demo", repo_path="/tmp/demo",
                      tracker=ProviderRef(kind="github", repo="acme/demo"))
    finding, asked = _line_from_the_live_probe(monkeypatch, project, {
        "OPENFACTORY_GH_APP_ID": "1", "OPENFACTORY_GH_APP_INSTALLATION_ID": "1",
        "OPENFACTORY_GH_APP_KEY": str(tmp_path / "missing.pem")})

    assert finding.ok is True and finding.message.startswith(doctor.NOT_APPLICABLE), \
        finding.message
    assert "not fully configured" in finding.message, finding.message
    assert asked == []
