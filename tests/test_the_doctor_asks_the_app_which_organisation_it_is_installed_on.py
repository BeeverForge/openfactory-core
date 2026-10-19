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
