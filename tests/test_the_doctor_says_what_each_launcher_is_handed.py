"""The doctor says, for each remote box, what its launcher is handed for a stored secret (#903).

Criterion 4 of #903: "The doctor line exists and is tested."

WHAT THE DOCTOR SAID BEFORE. Nothing. A remote box's launcher that declares nothing is refused a
secret the credential store holds (`credentials.box_launch_credentials`), and that refusal was
first met at the first job: measured on `cf7ec0f5` (2026-10-21), `doctor.probes_for` had no
`launcher_credentials` probe and `diagnose` no such line, so a deployment whose forge token sat in
a `file:` store and whose box was remote read a doctor with no word about the job it would refuse
(#822's review, "the doctor cannot see it").

THE LINE IS READ WHERE A PERSON READS IT: `probes_for(project)`'s own probe, run through
`diagnose`, every other probe pinned green (`tests/pinned_probes.py`). The launchers are real rows:
the stranger's distribution (`tests/stranger_addon.py`) serves its remote row with a runner that
declares or does not, and the core's `fargate` row has no runner in this tree.
"""

from __future__ import annotations

import pytest
from pinned_probes import a_fully_pinned_probe_set
from test_a_launcher_declares_whether_it_resolves_credential_references import (
    _serve_remote_runner,
    _TakesReferences,
)
from vendor_addons import install

from openfactory import credentials, doctor, plugins
from openfactory.adapters.credential_store import registry as store_registry
from openfactory.adapters.credential_store.file import DIR_VAR
from openfactory.adapters.sandbox import registry
from openfactory.adapters.sandbox.timeouts import LAUNCHER_TIMEOUT
from openfactory.contracts.project import Project, ProviderRef

#: A fictitious secret, recognisable in any output that should not hold it.
SECRET = "fictitious-stored-secret-903d"

#: The store entry the forge's secret is held under, and the reference the project writes.
NAME = "acme-forge-token"
REFERENCE = f"{store_registry.FILE}:{NAME}"


class _DeclaresNothing:
    """A launcher with the signature every launcher had before the declaration (`AcmeRunner`)."""

    def launch(self, box, *, journal=None, variant="", extra_env=None,
               timeout=LAUNCHER_TIMEOUT, run_id=None):
        raise AssertionError("the doctor never launches")

    def stop(self, box):
        return 0

    def tail(self, project, issue):
        raise AssertionError("the doctor never tails")


@pytest.fixture
def stored(tmp_path, monkeypatch):
    """A project whose forge reads `file:acme-forge-token`, held at 0600 in a 0700 directory (the
    modes explicit, so the host's umask does not decide — #822's review)."""
    monkeypatch.delenv(store_registry.STORE_VAR, raising=False)
    directory = tmp_path / "credentials"
    directory.mkdir()
    directory.chmod(0o700)
    (directory / NAME).write_text(SECRET)
    (directory / NAME).chmod(0o600)
    monkeypatch.setenv(DIR_VAR, str(directory))
    return Project(name="deskline", repo_path="/tmp/deskline",
                   tracker=ProviderRef(kind="local", repo="deskline"),
                   forge=ProviderRef(kind="github", repo="acme/deskline",
                                     options={"token_env": REFERENCE}))


def _line(project) -> doctor.Finding:
    """The `launcher_credentials` finding, from the probe `probes_for` wires."""
    probes = a_fully_pinned_probe_set(
        launcher_credentials=doctor.probes_for(project).launcher_credentials)
    found = [f for f in doctor.diagnose(probes).findings if f.check == "launcher_credentials"]
    assert len(found) == 1, [f.check for f in doctor.diagnose(probes).findings]
    return found[0]


def _remote_rows() -> list[str]:
    return [kind for kind in plugins.known(registry.AXIS, registry.BOXES)
            if registry.installed_box_traits(kind).remote]


@pytest.mark.parametrize("runner", [_TakesReferences, _DeclaresNothing],
                         ids=["a-launcher-that-declares", "a-launcher-that-declares-nothing"])
def test_each_remote_row_is_said_as_receiving_references_or_values(
        runner, stored, tmp_path, monkeypatch):
    """Every remote row there is (the core's and a stranger's) is named with what its launcher is
    handed, in the words the doctor exports for that answer; a local row is not a launcher."""
    kind = _serve_remote_runner(tmp_path, monkeypatch, runner())
    monkeypatch.setenv("OPENFACTORY_SANDBOX", "worktree")
    said = doctor.LAUNCHER_SAID
    expected = {kind: "references" if runner is _TakesReferences else "values",
                "fargate": "not installed"}
    assert set(_remote_rows()) == set(expected)

    finding = _line(stored)

    assert finding.ok, finding
    for row, answer in expected.items():
        assert f"`{row}` {said[answer]}" in finding.message, finding.message
    assert SECRET not in finding.message + finding.remedy


def test_a_stored_secret_for_a_launcher_that_declares_nothing_fails_before_the_first_job(
        stored, tmp_path, monkeypatch):
    """The deployment's box is remote, its launcher declares nothing, and the forge's secret is in
    the store: the line FAILS, naming the box, the reference and the missing declaration, and the
    remedy names the three ways out — the refusal the first job would meet, said before it."""
    kind = _serve_remote_runner(tmp_path, monkeypatch, _DeclaresNothing())
    monkeypatch.setenv("OPENFACTORY_SANDBOX", kind)

    finding = _line(stored)

    assert not finding.ok, finding
    for named in (f"`{kind}`", f"`{REFERENCE}`", credentials.RESOLVES_REFERENCES, "forge"):
        assert named in finding.message, (named, finding.message)
    for way_out in ("`env:", "`identity: workload`",
                    f"`{registry.RESOLVES_REFERENCES_ATTR} = True`"):
        assert way_out in finding.remedy, (way_out, finding.remedy)
    assert SECRET not in finding.message + finding.remedy

    # …and the same deployment on a launcher that declares is not failed
    _serve_remote_runner(tmp_path, monkeypatch, _TakesReferences())
    assert _line(stored).ok


def test_a_runner_not_installed_is_said_and_not_failed(stored, monkeypatch):
    """`fargate` with no add-on to supply its runner (the public tree, CI): the line says the
    runner is not installed here, and does not fail, even with the deployment's box on it and a
    stored secret — whether its launcher declares cannot be seen from this machine."""
    install(monkeypatch, declared_rows=False)
    monkeypatch.setenv("OPENFACTORY_SANDBOX", "fargate")
    assert _remote_rows() == ["fargate"]

    finding = _line(stored)

    assert finding.ok, finding
    assert f"`fargate` {doctor.LAUNCHER_SAID['not installed']}" in finding.message
    assert SECRET not in finding.message + finding.remedy
