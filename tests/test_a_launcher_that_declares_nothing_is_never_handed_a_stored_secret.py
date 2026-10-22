"""A remote box's launcher that declares nothing is never handed a secret the credential store holds (#903).

Criterion 2 of #903: "Without the declaration, a credential held in the store never reaches
`extra_env`. A test covers every credential `box_credential_env` can hand over."

WHAT THE CODE DID BEFORE. A remote launcher (`RemoteBox.launch`) is handed credentials as VALUES
in `extra_env`, and it may copy that environment where others can read it: an ECS `RunTask`
override is read back by `DescribeTasks`. A minted token lives an hour there; a secret from the
credential store (#742) lives there as long as it is valid. #822 refuses such a secret for EVERY
remote box, and its sentence names no launcher: measured on `cf7ec0f5` (2026-10-21), the refusal
read "a remote box's launcher is handed only short-lived minted tokens: none declares that it
resolves credential references itself", so an operator with two remote rows could not tell which
launcher refused, nor that the remedy is a declaration on the launcher.

THE REAL LAUNCH PATH IS DRIVEN. `activities._run_remote` is called with a recording runner served
as the stranger's `box_runner` entry point (a real distribution, `tests/stranger_addon.py`): what
is asserted is what a launcher would have received, not what a helper returns.

THE PARAMETERS ARE DERIVED (docs/engineering-lessons.md §5): the axes from
`credentials.BOX_TOKEN_ENV`, the store kinds from `credential_store.registry.STORES` minus `env`
plus the stranger's, and the steps in the order `credentials._axis_answer` walks them, the vendor
steps from the credential rows themselves. A step, a store or a row added later is asked here by
construction, and one this test cannot plant fails by name.
"""

from __future__ import annotations

import dataclasses
from types import ModuleType, SimpleNamespace

import pytest
import stranger_addon
from test_a_launcher_declares_whether_it_resolves_credential_references import (
    _serve_remote_runner,
)

from openfactory import credentials
from openfactory.adapters import azure_devops as ado
from openfactory.adapters.credential.registry import CREDENTIALS, IDENTITY_OPTION, WORKLOAD
from openfactory.adapters.credential_store import registry as store_registry
from openfactory.adapters.credential_store.file import DIR_VAR
from openfactory.adapters.sandbox.timeouts import LAUNCHER_TIMEOUT
from openfactory.contracts.project import Project, ProviderRef
from openfactory.runtime.temporal import activities as acts
from openfactory.runtime.temporal.io import RunJobInput

#: A fictitious secret, recognisable in any output that should not hold it.
SECRET = "fictitious-stored-secret-903c"

#: What the recording runner answers when it IS launched (the regressions below).
LAUNCHED = object()


def _kinds_on(axis: str, entry_points) -> list[str]:
    """The kinds an add-on declares on `axis`, read off its entry-point names (`<axis>.<kind>`)."""
    return [name.partition(".")[2] for name in entry_points if name.startswith(f"{axis}.")]


#: Every store a secret can be held in that is NOT the box's own environment: the shipped ones and
#: the stranger's. `env` is out because a variable is handed to the box by name, which is the
#: regression held below, not a stored secret.
STORE_KINDS = sorted((set(store_registry.STORES) - {store_registry.ENV})
                     | set(_kinds_on(store_registry.AXIS, stranger_addon.ENTRY_POINTS)))


def _credential_rows() -> dict[str, object]:
    """kind → its credential row, shipped and the stranger's. The stranger's is built from its
    package's own source, run into a throwaway module: the installed copy, whose `BUILT` other
    tests read, does not exist at collection and is never touched."""
    rows = {kind: build() for kind, build in CREDENTIALS.items()}
    package = ModuleType("acme_addons_rows")
    exec(compile(stranger_addon.SOURCE, "acme_addons", "exec"), package.__dict__)  # noqa: S102
    for kind in _kinds_on("credential", stranger_addon.ENTRY_POINTS):
        rows[kind] = getattr(package, stranger_addon.ENTRY_POINTS[f"credential.{kind}"])()
    return rows


_ROWS = _credential_rows()


@dataclasses.dataclass(frozen=True)
class Step:
    """One way `_axis_answer` reaches an axis's secret: the axis's provider, the name the secret
    is planted under in the store, and whether the store must be the deployment's declared one
    (`OPENFACTORY_CREDENTIAL_STORE`) for a bare name to be asked of it."""

    vendor: str
    token_env: str
    planted: str
    declares_store: bool


def _steps(axis: str, store: str) -> dict[str, Step]:
    """The steps for `axis` and `store`, keyed by id, in the order `_axis_answer` walks them."""
    steps = {
        # 1. `token_env` as every registry has written it, a bare name, held in the declared store
        "token_env-a-bare-name": Step("github", "ACME_AXIS_TOKEN", "ACME_AXIS_TOKEN", True),
        # 2. `token_env` as a reference to that store alone
        "token_env-a-reference": Step("github", f"{store}:acme-axis-token", "acme-axis-token",
                                      False),
    }
    # 3. the vendor's own default variable, for every row that names one and resolves nothing
    for kind, row in sorted(_ROWS.items()):
        if row.env and row.source is None and row.needs:
            steps[f"the-vendor-default-of-{kind}"] = Step(kind, "", row.env, True)
    # 4. a vendor that resolves its own credential (`CredentialRow.source`), from its variable
    for kind, row in sorted(_ROWS.items()):
        if row.source is not None and row.needs:
            steps[f"the-own-source-of-{kind}"] = Step(kind, "", row.env, True)
    # 5. the deployment's pair, the axis's own variable and then the bot's
    for name in credentials._GENERIC[axis]:
        steps[f"the-generic-pair-{name}"] = Step("github", "", name, True)
    return steps


CASES = [(axis, step, store)
         for axis in sorted(credentials.BOX_TOKEN_ENV)
         for store in STORE_KINDS
         for step in _steps(axis, store)]


class RecordingRunner:
    """A launcher that declares nothing, with exactly the signature every launcher had before
    the declaration existed (`AcmeRunner.launch`): handed a keyword it does not take, it raises
    `TypeError`, which is how a `references=` passed to it would show here."""

    def __init__(self):
        self.launches: list[dict] = []

    def launch(self, box, *, journal=None, variant="", extra_env=None,
               timeout=LAUNCHER_TIMEOUT, run_id=None):
        self.launches.append({"box": box, "extra_env": dict(extra_env or {})})
        return LAUNCHED

    def stop(self, box):
        return 0

    def tail(self, project, issue):
        return SimpleNamespace(fetch_new=lambda: [])


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    """The stranger's distribution installed, its remote row served with a `RecordingRunner`, the
    job's journal under `tmp_path`, and every `BoxConfig` `_run_remote` builds recorded — so a
    secret written into the box's configuration is seen even when `launch` is never reached."""
    monkeypatch.delenv(store_registry.STORE_VAR, raising=False)
    monkeypatch.setenv("OPENFACTORY_LOG_DIR", str(tmp_path / "logs"))
    directory = tmp_path / "credentials"
    directory.mkdir()
    directory.chmod(0o700)  # explicit, so the host's umask does not decide (#822's review)
    monkeypatch.setenv(DIR_VAR, str(directory))
    runner = RecordingRunner()
    kind = _serve_remote_runner(tmp_path, monkeypatch, runner)
    built: list = []
    real_box_for = acts._box_for

    def box_for(inp, **kw):
        built.append(real_box_for(inp, **kw))
        return built[-1]

    monkeypatch.setattr(acts, "_box_for", box_for)
    return SimpleNamespace(runner=runner, kind=kind, built=built, directory=directory)


def _plant(store: str, name: str, value: str, launcher, monkeypatch) -> None:
    """Put `value` where the `store` kind reads `name`. A store kind with no way to plant fails
    here by name, so a store added to `STORES` is never asked about vacuously."""
    if store == store_registry.FILE:
        path = launcher.directory / name
        path.write_text(value)
        path.chmod(0o600)
    elif store == stranger_addon.KIND:
        import sys

        # the INSTALLED copy's vault, which is the one the store registry built
        monkeypatch.setitem(sys.modules["acme_addons"].AcmeVault.SECRETS, name, value)
    else:
        pytest.fail(f"no way to plant a secret in the `{store}` store — add one to `_plant`")


def _project(axis: str, ref: ProviderRef) -> Project:
    """`ref` on `axis`, and on the other axis a vendor that needs no credential, so the only
    credential the launch can be handed is the one under test."""
    other = ProviderRef(kind="local", repo="deskline")
    axes = {"tracker": other, "forge": other, axis: ref}
    return Project(name="deskline", repo_path="/tmp/deskline", **axes)


def _launch(project: Project, launcher, monkeypatch):
    monkeypatch.setattr(acts, "ProjectRegistry", lambda: SimpleNamespace(get=lambda _n: project))
    return acts._run_remote(RunJobInput(project=project.name, issue="7", sandbox=launcher.kind),
                            run_id="run-903")


def _fields(box) -> str:
    """Every field of a `BoxConfig`, as one text a value would show up in."""
    return repr(dataclasses.asdict(box))


def _held(axis: str, step: str, store: str, launcher, monkeypatch) -> Project:
    """The project whose `axis` secret is held in `store` and reached through `step`."""
    found = _steps(axis, store)[step]
    if found.declares_store:
        monkeypatch.setenv(store_registry.STORE_VAR, store)
    _plant(store, found.planted, SECRET, launcher, monkeypatch)
    options = {"token_env": found.token_env} if found.token_env else {}
    return _project(axis, ProviderRef(kind=found.vendor, repo="deskline", options=options))


@pytest.mark.parametrize(("axis", "step", "store"), CASES,
                         ids=[f"{a}-{s}-{k}" for a, s, k in CASES])
def test_no_stored_secret_reaches_the_launch_of_a_launcher_that_declares_nothing(
        axis, step, store, launcher, monkeypatch):
    """The launch is refused before `launch`, and the secret is in no launch environment, no
    field of the box's configuration and not in the sentence.

    On `cf7ec0f5` #822's refusal already holds every case, so this is green there: it guards the
    path #903 rewrites (the launcher is now asked, and the credentials are computed by a new
    function), which mutation plan 903's cuts "the credentials computed after `launch`",
    "`references` passed to a launcher that declares nothing" and "`_held_in_a_store` skips the
    generic pair / the vendor default" turn red."""
    project = _held(axis, step, store, launcher, monkeypatch)
    assert credentials._held_in_a_store(project, axis), (
        f"the `{step}` step did not reach the secret planted in `{store}`: this case asks nothing")

    with pytest.raises(credentials.CredentialUnavailable) as refused:
        _launch(project, launcher, monkeypatch)

    assert launcher.runner.launches == [], "the launcher was launched before the refusal"
    assert SECRET not in str(refused.value), "the refusal said the secret"
    assert all(SECRET not in _fields(box) for box in launcher.built), \
        "the secret was written into the box's configuration"


def test_the_refusal_names_the_launcher_and_the_declaration_it_lacks(launcher, monkeypatch):
    """The sentence names the box kind whose launcher refused and the declaration it lacks, so an
    operator with two remote rows knows which launcher to change, and how.

    On `cf7ec0f5` it named the declaration and no launcher: "a remote box's launcher is handed
    only short-lived minted tokens: none declares that it resolves credential references itself"
    (`credentials.box_credential_env`)."""
    project = _held("forge", "token_env-a-reference", store_registry.FILE, launcher, monkeypatch)

    with pytest.raises(credentials.CredentialUnavailable) as refused:
        _launch(project, launcher, monkeypatch)

    sentence = str(refused.value)
    assert f"`{launcher.kind}`" in sentence, sentence
    assert credentials.RESOLVES_REFERENCES in sentence, sentence
    assert launcher.runner.launches == []


def test_a_variable_the_box_reads_for_itself_is_still_handed_over_by_name(
        launcher, monkeypatch):
    """A secret in the environment the box reads is handed over as its NAME, in the axis's
    options, and its value is in no launch environment: the behaviour before #742, kept."""
    monkeypatch.setenv("ACME_JIRA_TOKEN", SECRET)
    project = _project("tracker", ProviderRef(kind="jira", repo="DSK",
                                              options={"token_env": "ACME_JIRA_TOKEN"}))

    assert _launch(project, launcher, monkeypatch) is LAUNCHED

    (launched,) = launcher.runner.launches
    assert launched["box"].tracker_options == {"token_env": "ACME_JIRA_TOKEN"}
    assert SECRET not in repr(launched["extra_env"]), "a value was written where a name sufficed"


def test_a_minted_workload_token_is_still_handed_as_a_value(launcher, monkeypatch):
    """An axis that declares the machine's own identity is minted on the worker and handed to the
    box as a short-lived value, under `BOX_TOKEN_ENV`, with the declaration dropped (#373)."""
    minted = "fictitious-minted-token-903w"
    monkeypatch.setattr(ado, "_workload_mint", lambda client_id="": (minted, 4102444800.0))
    monkeypatch.setattr(ado, "_WORKLOAD", {})
    project = _project("forge", ProviderRef(
        kind="azure_devops", repo="api",
        options={"organization": "acme", "project": "Deskline", IDENTITY_OPTION: WORKLOAD}))

    assert _launch(project, launcher, monkeypatch) is LAUNCHED

    (launched,) = launcher.runner.launches
    assert launched["extra_env"][credentials.BOX_TOKEN_ENV["forge"]] == minted
    assert IDENTITY_OPTION not in launched["box"].forge_options
    assert launched["box"].forge_options["token_env"] == credentials.BOX_TOKEN_ENV["forge"]
