"""A remote box's launcher that declares it resolves credential references is handed the reference (#903).

Criterion 3 of #903: "With the declaration, the launcher receives the reference, and a test
resolves it on the launcher's side."

WHAT THE CODE DID BEFORE. #822 refused a secret the credential store holds for EVERY remote box,
whatever its launcher could do: measured on `cf7ec0f5` (2026-10-21), a launcher whose class says
`resolves_references = True` and whose `launch` takes `references=` was refused the launch with
`CredentialUnavailable` ("none declares that it resolves credential references itself"), and no
channel existed to hand it a reference. So the one launcher that could keep a long-lived secret
out of its launch environment had no way to be given one.

THE REAL LAUNCH PATH IS DRIVEN, AND THE LAUNCHER RESOLVES ON ITS OWN SIDE. `activities._run_remote`
is called with a declaring runner served as the stranger's `box_runner` entry point. Inside its
`launch` the runner does what a launcher on another machine would: it reads each reference it was
handed with `credential_store.registry.resolve`, against ITS OWN credential directory (a second
`OPENFACTORY_CREDENTIAL_DIR`, standing for the launcher's machine), and builds the box's
environment from what it read. Files and directories are written with explicit modes (`0o600`,
`0o700`), so the host's umask does not decide — the point #822's review blocked on.

THE CASES ARE TASK 2'S, DERIVED (docs/engineering-lessons.md §5): every axis of
`credentials.BOX_TOKEN_ENV`, every store that is not the environment (shipped and the stranger's),
and every step `credentials._axis_answer` walks, so a secret the declaring launcher is handed is
asked for every way it can be held.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_a_launcher_declares_whether_it_resolves_credential_references import (
    _serve_remote_runner,
)
from test_a_launcher_that_declares_nothing_is_never_handed_a_stored_secret import (
    CASES,
    SECRET,
    _fields,
    _held,
    _launch,
    _project,
    _steps,
)

from openfactory import credentials
from openfactory.adapters import azure_devops as ado
from openfactory.adapters.credential.registry import IDENTITY_OPTION, WORKLOAD
from openfactory.adapters.credential_store import registry as store_registry
from openfactory.adapters.credential_store.file import DIR_VAR
from openfactory.adapters.sandbox.timeouts import LAUNCHER_TIMEOUT
from openfactory.contracts.project import ProviderRef
from openfactory.runtime.temporal import activities as acts

#: What the resolving runner answers when it is launched.
LAUNCHED = object()

#: The doctor's word for each axis's credential (`describe_source` reads it).
DOCTOR_SOURCE = {"forge": credentials.forge_credential_source,
                 "tracker": credentials.tracker_credential_source}


class ResolvingRunner:
    """A launcher that declares it resolves references and takes the `references` keyword. Its
    `launch` resolves each reference against `side` (the launcher machine's credential
    directory), as a launcher on another machine would, and records what it was handed and the
    environment it would start the box with."""

    resolves_references = True

    def __init__(self, side):
        self.side = side
        self.launches: list[dict] = []

    def launch(self, box, *, journal=None, variant="", extra_env=None,
               timeout=LAUNCHER_TIMEOUT, run_id=None, references=None):
        handed = dict(references or {})
        with pytest.MonkeyPatch.context() as its_machine:
            its_machine.setenv(DIR_VAR, str(self.side))
            resolved = {variable: store_registry.resolve(reference)
                        for variable, reference in handed.items()}
        self.launches.append({"box": box, "extra_env": dict(extra_env or {}),
                              "references": handed,
                              "box_env": {**dict(extra_env or {}), **resolved}})
        return LAUNCHED

    def stop(self, box):
        return 0

    def tail(self, project, issue):
        return SimpleNamespace(fetch_new=lambda: [])


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    """The stranger's distribution installed, its remote row served with a `ResolvingRunner`, a
    worker credential directory and a launcher one, and every `BoxConfig` `_run_remote` builds
    recorded. The same attributes as task 2's fixture, so its `_held` plants here unchanged."""
    monkeypatch.delenv(store_registry.STORE_VAR, raising=False)
    monkeypatch.setenv("OPENFACTORY_LOG_DIR", str(tmp_path / "logs"))
    directory = tmp_path / "worker-credentials"
    side = tmp_path / "launcher-credentials"
    for each in (directory, side):
        each.mkdir()
        each.chmod(0o700)  # explicit, so the host's umask does not decide (#822's review)
    monkeypatch.setenv(DIR_VAR, str(directory))
    runner = ResolvingRunner(side)
    kind = _serve_remote_runner(tmp_path, monkeypatch, runner)
    built: list = []
    real_box_for = acts._box_for

    def box_for(inp, **kw):
        built.append(real_box_for(inp, **kw))
        return built[-1]

    monkeypatch.setattr(acts, "_box_for", box_for)
    return SimpleNamespace(runner=runner, kind=kind, built=built, directory=directory, side=side)


def _held_on_both_sides(axis, step, store, launcher, monkeypatch):
    """Task 2's project for the case, with the secret ALSO mounted on the launcher's machine
    under the same name (a `file:` reference names a file in whichever directory resolves it)."""
    project = _held(axis, step, store, launcher, monkeypatch)
    if store == store_registry.FILE:
        path = launcher.side / _steps(axis, store)[step].planted
        path.write_text(SECRET)
        path.chmod(0o600)
    return project


def _launched_once(project, launcher, monkeypatch) -> dict:
    assert _launch(project, launcher, monkeypatch) is LAUNCHED
    (launched,) = launcher.runner.launches
    return launched


_IDS = [f"{a}-{s}-{k}" for a, s, k in CASES]


@pytest.mark.parametrize(("axis", "step", "store"), CASES, ids=_IDS)
def test_the_launcher_is_handed_the_reference_and_resolves_it_on_its_own_side(
        axis, step, store, launcher, monkeypatch):
    """The declaring launcher is handed, under the axis's box variable, the reference the secret
    was planted under — the one the doctor reports for the axis — and resolving it on the
    launcher's own machine gives the box the secret.

    On `cf7ec0f5` the launch raised `CredentialUnavailable` for every case: the declaration was
    not asked, and `launch` was never reached."""
    project = _held_on_both_sides(axis, step, store, launcher, monkeypatch)
    variable = credentials.BOX_TOKEN_ENV[axis]
    planted = f"{store}:{_steps(axis, store)[step].planted}"
    said = DOCTOR_SOURCE[axis](project)

    launched = _launched_once(project, launcher, monkeypatch)

    assert launched["references"] == {variable: planted}
    # One reference on both sides: the doctor's own, or, for the deployment's pair, the pair as
    # the doctor names it (`generic:<axis>`) with the reference one of its two variables.
    if said.startswith("generic:"):
        assert said == f"generic:{axis}"
        assert planted.partition(":")[2] in credentials._GENERIC[axis]
    else:
        assert said == planted
    assert launched["box_env"][variable] == SECRET


@pytest.mark.parametrize(("axis", "step", "store"), CASES, ids=_IDS)
def test_the_value_is_in_neither_extra_env_nor_the_box_options(
        axis, step, store, launcher, monkeypatch):
    """The worker hands the launcher no value: the secret is in no `extra_env`, no field of any
    `BoxConfig` the launch built, and not among the references either.

    On `cf7ec0f5` the launch raised `CredentialUnavailable`, so nothing was launched to look at."""
    project = _held_on_both_sides(axis, step, store, launcher, monkeypatch)

    launched = _launched_once(project, launcher, monkeypatch)

    assert SECRET not in repr(launched["extra_env"]), "the value was put into the launch env"
    assert SECRET not in repr(launched["references"]), "a value was handed as a reference"
    assert launcher.built, "no box configuration was built"
    assert all(SECRET not in _fields(box) for box in launcher.built), \
        "the secret was written into the box's configuration"


@pytest.mark.parametrize(("axis", "step", "store"), CASES, ids=_IDS)
def test_the_box_reads_the_axis_from_the_variable_the_launcher_fills(
        axis, step, store, launcher, monkeypatch):
    """The box's options for the axis name `BOX_TOKEN_ENV[axis]` as `token_env`, the variable the
    launcher fills from the reference, in place of the name or reference the project wrote — which
    on the launcher's machine would name nothing the box can read.

    On `cf7ec0f5` the launch raised `CredentialUnavailable` before any box was launched."""
    project = _held_on_both_sides(axis, step, store, launcher, monkeypatch)
    variable = credentials.BOX_TOKEN_ENV[axis]

    launched = _launched_once(project, launcher, monkeypatch)

    assert getattr(launched["box"], f"{axis}_options")["token_env"] == variable
    assert variable in launched["references"]


def test_a_declaring_launcher_is_still_handed_a_minted_workload_token_as_a_value(
        launcher, monkeypatch):
    """An axis that declares the machine's own identity is minted on the worker and handed as a
    short-lived value in `extra_env`, never as a reference, even to a launcher that resolves
    references: there is no stored secret to refer to (#373), and the declaration is dropped.

    Green on `cf7ec0f5`, where nothing was handed as a reference. It guards the path #903
    rewrites. A temporary cut that kept the minted token out of `extra_env` turned it red
    (measured 2026-10-21, `1 failed`); its `references == {}` is what holds a minted token from
    being handed as a reference."""
    minted = "fictitious-minted-token-903r"
    monkeypatch.setattr(ado, "_workload_mint", lambda client_id="": (minted, 4102444800.0))
    monkeypatch.setattr(ado, "_WORKLOAD", {})
    project = _project("forge", ProviderRef(
        kind="azure_devops", repo="api",
        options={"organization": "acme", "project": "Deskline", IDENTITY_OPTION: WORKLOAD}))

    launched = _launched_once(project, launcher, monkeypatch)

    variable = credentials.BOX_TOKEN_ENV["forge"]
    assert launched["extra_env"][variable] == minted
    assert launched["references"] == {}
    assert IDENTITY_OPTION not in launched["box"].forge_options
    assert launched["box"].forge_options["token_env"] == variable

