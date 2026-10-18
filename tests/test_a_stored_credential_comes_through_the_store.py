"""A stored credential comes through one seam, the credential store, named by a reference (#742).

What exists before this: every secret the deployment stored was an environment variable, read by
the module that used it; the GitHub App key alone could also come from a file, inside its own
function; and the box image had no pull credential at all (ADR-0037 §7.2). What is held here:

  · THE AXIS IS BORN WITH TWO and a stranger adds the third: `env` and `file` ship, both reached
    through the open tree, and an installed `credential_store.<kind>` row answers the same way;
  · AN INSTALLATION THAT DECLARES NOTHING READS EXACTLY WHAT IT READ YESTERDAY, for every
    credential the core reads — derived from the code, not listed;
  · A DECLARED STORE IS ASKED FIRST and the environment second, and a refusal is never a fallback;
  · THE FILE STORE READS AT EACH USE and refuses, by name, a file it should not trust;
  · THE READERS THE ISSUE NAMES REACH A FILE-HELD SECRET: the per-axis tokens, the App key, the
    harness tokens, the box's pass-through, a remote box's credential and the image's pull
    credential, which is used for the pull and never handed to the box;
  · NAMES AND REFERENCES, NEVER VALUES, in what the store logs and the doctor says.

The rule that every credential is read through the store at all is a sweep over the package:
`tests/test_every_stored_credential_is_read_through_the_store.py`.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import stat
import subprocess
from pathlib import Path

import pytest
import stranger_addon
from test_the_environment_carries_the_products_name import _holds_a_credential

from openfactory import environ, plugins
from openfactory.adapters.credential_store import registry
from openfactory.adapters.credential_store.base import CredentialStore
from openfactory.adapters.credential_store.file import DIR_VAR, MAX_BYTES, FileStore
from openfactory.adapters.credential_store.registry import STORE_VAR, STORES, stored
from openfactory.contracts.project import BoxConfig, Project, ProviderRef

#: Fictitious secrets, recognisable in any output that should not hold them.
SECRET = "fictitious-secret-7f3a"
ROTATED = "fictitious-secret-rotated-91c2"


@pytest.fixture(autouse=True)
def _no_store_declared(monkeypatch):
    monkeypatch.delenv(STORE_VAR, raising=False)
    monkeypatch.delenv(DIR_VAR, raising=False)


@pytest.fixture
def secrets(tmp_path, monkeypatch):
    """A credential directory, declared for this test: `secrets(name, value)` writes a file."""
    directory = tmp_path / "secrets"
    directory.mkdir()
    directory.chmod(0o700)
    monkeypatch.setenv(DIR_VAR, str(directory))

    def put(name: str, value: str, mode: int = 0o600) -> Path:
        path = directory / name
        path.write_text(value)
        path.chmod(mode)
        return path

    put.directory = directory
    return put


@pytest.fixture
def file_store(secrets, monkeypatch):
    """The file store declared as this deployment's own."""
    monkeypatch.setenv(STORE_VAR, "file")
    return secrets


# ── the axis: born with two, and a stranger adds the third ──────────────────────────────────────

def _plant_env(tmp_path, monkeypatch, value):
    monkeypatch.setenv("ACME_PLANTED_TOKEN", value)
    monkeypatch.delenv("ACME_ABSENT_TOKEN", raising=False)
    return "ACME_PLANTED_TOKEN", "ACME_ABSENT_TOKEN"


def _plant_file(tmp_path, monkeypatch, value):
    directory = tmp_path / "planted"
    directory.mkdir()
    directory.chmod(0o700)
    (directory / "acme-planted").write_text(value + "\n")
    (directory / "acme-planted").chmod(0o400)
    monkeypatch.setenv(DIR_VAR, str(directory))
    return "acme-planted", "acme-absent"


#: kind → how a secret is put where that SHIPPED store reads it. Keyed by the table's own kinds
#: below, so a store added to `STORES` without a way to plant its secret fails by name.
PLANT = {"env": _plant_env, "file": _plant_file}


def test_the_axis_is_born_with_two_and_published():
    assert {"env", "file"} <= set(STORES), sorted(STORES)
    assert registry.AXIS in plugins.AXES


@pytest.mark.parametrize("kind", sorted(STORES))
def test_every_shipped_store_answers_what_it_holds_and_never_says_it(kind, tmp_path, monkeypatch):
    assert kind in PLANT, f"no way to plant a secret for the shipped `{kind}` store — add one here"
    name, absent = PLANT[kind](tmp_path, monkeypatch, SECRET)
    store = registry.build_store(kind)

    assert isinstance(store, CredentialStore)
    assert store.resolve(name) == SECRET
    assert store.resolve(absent) is None
    # reached by the open tree: a reference names the store, and the registry answers through it
    assert registry.answer(f"{kind}:{name}") == (f"{kind}:{name}", SECRET)
    said = store.describe(name) + registry.describe(f"{kind}:{name}") + store.describe(absent)
    assert name in said and SECRET not in said


def test_a_strangers_store_answers_a_reference_a_project_names_and_the_deployment(
        tmp_path, monkeypatch):
    """The third kind, installed as a real distribution, with no file of ours edited: a project's
    `token_env` names `acme:<entry>`, and a deployment that declares `acme` reads its own
    credentials there."""
    stranger_addon.installed(tmp_path, monkeypatch)
    from openfactory.credentials import _axis_credential, forge_token

    project = Project(name="acme", repo_path="/tmp/acme",
                      forge=ProviderRef(kind="github", repo="acme/app",
                                        options={"token_env": "acme:forge-token"}))
    assert _axis_credential(project, "forge", forge_token) == ("acme:forge-token",
                                                               "acme-vault-forge-token")
    monkeypatch.setenv(STORE_VAR, "acme")
    assert stored("forge-token") == "acme-vault-forge-token"
    assert "acme" in registry.known()


def test_an_unknown_store_refuses_by_name_and_is_never_a_fallback(monkeypatch, caplog):
    with pytest.raises(ValueError, match=r"unknown credential store 'vault' — known: .*env.*file"):
        registry.build_store("vault")
    with caplog.at_level(logging.WARNING, logger="openfactory.credential_store"):
        assert registry.resolve("vault:deploy-key") is None
    assert "vault:deploy-key" in caplog.text

    monkeypatch.setenv("ACME_DEPLOY_TOKEN", SECRET)
    monkeypatch.setenv(STORE_VAR, "vault")
    assert stored("ACME_DEPLOY_TOKEN") is None, (
        "a declared store nobody installed handed out the variable instead")


# ── an installation that declares nothing reads what it read yesterday ─────────────────────────

def _credentials_the_core_reads() -> list[str]:
    names = sorted(n for n in environ.names_read() if _holds_a_credential(n))
    assert len(names) > 20, names  # the derivation found the platform's credentials
    return names


def test_with_no_store_declared_every_credential_is_its_variable_byte_for_byte(monkeypatch):
    """Upgrade safety, over every credential-shaped variable the core reads: the same bytes,
    unstripped, and the same identity (`env:<NAME>`) a reader keys a credential by."""
    names = _credentials_the_core_reads()
    for name in names:
        monkeypatch.setenv(name, f"  value of {name}\n")

    for name in names:
        assert stored(name) == f"  value of {name}\n", name
        assert registry.answer(name) == (f"env:{name}", f"  value of {name}\n"), name


def test_with_no_store_declared_an_axis_credential_keeps_its_identity(monkeypatch):
    """`token_env`, a vendor's default variable and the generic pair answer as before — the
    vendors taken from the credential registry's own table."""
    from openfactory.adapters.credential.registry import SHIPPED_ENV
    from openfactory.credentials import _axis_credential, tracker_token

    monkeypatch.setenv("ACME_JIRA_TOKEN", SECRET)
    named = Project(name="a", repo_path="/tmp/a",
                    tracker=ProviderRef(kind="jira", repo="ACME",
                                        options={"token_env": "ACME_JIRA_TOKEN"}))
    assert _axis_credential(named, "tracker", tracker_token) == ("env:ACME_JIRA_TOKEN", SECRET)

    for kind, variable in sorted(SHIPPED_ENV.items()):
        monkeypatch.setenv(variable, f" {SECRET} ")
        vendor = Project(name="v", repo_path="/tmp/v",
                         tracker=ProviderRef(kind=kind, repo="ACME"))
        assert _axis_credential(vendor, "tracker", tracker_token) == (f"env:{variable}", SECRET)

    monkeypatch.setenv("OPENFACTORY_BOT_TOKEN", SECRET)
    generic = Project(name="g", repo_path="/tmp/g",
                      tracker=ProviderRef(kind="github", repo="acme/app"))
    assert _axis_credential(generic, "tracker", tracker_token) == ("generic:tracker", SECRET)


# ── a declared store first, the environment second, a refusal never a fallback ──────────────────

def test_a_declared_file_store_answers_first(file_store, monkeypatch):
    monkeypatch.setenv("ACME_SCANNER_TOKEN", "from-the-environment")
    file_store("ACME_SCANNER_TOKEN", SECRET)

    assert stored("ACME_SCANNER_TOKEN") == SECRET
    assert registry.stored_answer("ACME_SCANNER_TOKEN") == ("file:ACME_SCANNER_TOKEN", SECRET)


def test_a_secret_the_store_does_not_hold_is_the_variable_so_secrets_move_one_at_a_time(
        file_store, monkeypatch):
    monkeypatch.setenv("ACME_SCANNER_TOKEN", "from-the-environment")

    assert stored("ACME_SCANNER_TOKEN") == "from-the-environment"
    assert registry.source("ACME_SCANNER_TOKEN") == "env:ACME_SCANNER_TOKEN"


def test_a_refused_file_is_never_replaced_by_the_variable(file_store, monkeypatch, caplog):
    monkeypatch.setenv("ACME_SCANNER_TOKEN", "from-the-environment")
    file_store("ACME_SCANNER_TOKEN", SECRET, mode=0o620)

    with caplog.at_level(logging.WARNING, logger="openfactory.credential_store"):
        assert stored("ACME_SCANNER_TOKEN") is None
    assert "ACME_SCANNER_TOKEN" in caplog.text and "writable by its group" in caplog.text
    assert SECRET not in caplog.text and "from-the-environment" not in caplog.text


def test_a_declared_file_store_with_no_directory_refuses_every_credential(monkeypatch, caplog):
    monkeypatch.setenv(STORE_VAR, "file")
    monkeypatch.setenv("ACME_SCANNER_TOKEN", "from-the-environment")

    with caplog.at_level(logging.WARNING, logger="openfactory.credential_store"):
        assert stored("ACME_SCANNER_TOKEN") is None
    assert DIR_VAR in caplog.text


def test_a_bare_reference_is_a_deployment_credential_and_a_prefixed_one_asks_its_store_alone(
        secrets, monkeypatch):
    monkeypatch.setenv("ACME_SCANNER_TOKEN", "from-the-environment")
    secrets("ACME_SCANNER_TOKEN", SECRET)

    assert registry.resolve("ACME_SCANNER_TOKEN") == "from-the-environment"  # env declared
    assert registry.resolve("file:ACME_SCANNER_TOKEN") == SECRET
    assert registry.resolve("env:ACME_SCANNER_TOKEN") == "from-the-environment"
    monkeypatch.setenv(STORE_VAR, "file")
    assert registry.resolve("ACME_SCANNER_TOKEN") == SECRET
    assert registry.resolve("env:ACME_SCANNER_TOKEN") == "from-the-environment"


# ── the file store: read at each use, and refused by name when it should not be trusted ─────────

def test_the_file_is_read_at_each_use_and_kept_by_nobody(secrets):
    path = secrets("acme-token", SECRET + "\n")
    store = FileStore()

    assert store.resolve("acme-token") == SECRET
    path.chmod(0o600)
    path.write_text(ROTATED)
    assert store.resolve("acme-token") == ROTATED
    path.unlink()
    assert store.resolve("acme-token") is None


def test_an_empty_file_holds_nothing(secrets):
    secrets("acme-token", "\n")
    assert FileStore().resolve("acme-token") is None


def test_a_link_inside_the_directory_is_followed_as_a_cluster_mounts_its_secrets(secrets):
    """A cluster's secret volume links each name to a dated copy (`..data/<name>`)."""
    dated = secrets.directory / "..2026_10_18_00_00_00.1"
    dated.mkdir()
    (dated / "acme-token").write_text(SECRET)
    (dated / "acme-token").chmod(0o444)
    (secrets.directory / "..data").symlink_to(dated.name)
    (secrets.directory / "acme-token").symlink_to("..data/acme-token")

    assert FileStore().resolve("acme-token") == SECRET


def test_a_sticky_directory_anyone_may_write_to_is_read_for_this_users_files(secrets):
    secrets.directory.chmod(0o1777)
    secrets("acme-token", SECRET, mode=0o444)

    assert FileStore().resolve("acme-token") == SECRET


def _outside(secrets, tmp_path):
    (tmp_path / "elsewhere").write_text(SECRET)
    (secrets.directory / "acme-token").symlink_to(tmp_path / "elsewhere")


def _fifo(secrets, tmp_path):
    os.mkfifo(secrets.directory / "acme-token")


#: Each way the file store refuses, and the words its refusal names it by.
REFUSALS = {
    "a name with a separator": ("../acme-token", None, "not a file name"),
    "a name starting with a dot": (".acme-token", None, "not a file name"),
    "a link that leads outside": ("acme-token", _outside, "leads outside"),
    "a file its group may write": ("acme-token", lambda s, t: s("acme-token", SECRET, 0o620),
                                   "writable by its group"),
    "a file anyone may write": ("acme-token", lambda s, t: s("acme-token", SECRET, 0o602),
                                "writable by everyone"),
    "a pipe named like a secret": ("acme-token", _fifo, "not a regular file"),
    "a file too large to be a credential": (
        "acme-token", lambda s, t: s("acme-token", "x" * (MAX_BYTES + 1)), "at most"),
    "a file that is not text": (
        "acme-token", lambda s, t: (s("acme-token", ""), (s.directory / "acme-token")
                                    .write_bytes(b"\xff\xfe\x00")), "not text"),
    "a directory anyone may write to": (
        "acme-token", lambda s, t: (s("acme-token", SECRET), s.directory.chmod(0o777)),
        "writable by"),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_the_file_store_refuses_by_name_what_it_should_not_trust(case, secrets, tmp_path):
    from openfactory.adapters.credential_store.base import CredentialRefused

    name, arrange, words = REFUSALS[case]
    if arrange is not None:
        arrange(secrets, tmp_path)
    try:
        with pytest.raises(CredentialRefused, match=words) as refused:
            FileStore().resolve(name)
        said = FileStore().describe(name)
    finally:
        secrets.directory.chmod(0o700)
    assert SECRET not in str(refused.value) + said and "refused" in said


def test_the_file_store_says_when_it_cannot_be_read_at_all(tmp_path, monkeypatch):
    assert "names no directory" in FileStore().unusable()
    monkeypatch.setenv(DIR_VAR, str(tmp_path / "missing"))
    assert "cannot be read" in FileStore().unusable()
    (tmp_path / "a-file").write_text("")
    monkeypatch.setenv(DIR_VAR, str(tmp_path / "a-file"))
    assert "not a directory" in FileStore().unusable()
    monkeypatch.setenv(DIR_VAR, str(tmp_path))
    tmp_path.chmod(0o700)
    assert FileStore().unusable() == ""


# ── the readers the issue names reach a file-held secret ────────────────────────────────────────

def test_the_app_key_comes_through_the_store_as_content_or_as_a_path(file_store, tmp_path):
    from openfactory.credentials import app_private_key

    file_store("OPENFACTORY_GH_APP_KEY_CONTENT", "-----BEGIN KEY-----\nfictitious\n")
    assert app_private_key() == "-----BEGIN KEY-----\nfictitious"

    (file_store.directory / "OPENFACTORY_GH_APP_KEY_CONTENT").unlink()
    pem = tmp_path / "app.pem"
    pem.write_text("-----BEGIN KEY-----\nfrom-a-path\n")
    file_store("OPENFACTORY_GH_APP_KEY", str(pem))
    assert app_private_key() == "-----BEGIN KEY-----\nfrom-a-path\n"


def test_the_harness_runs_on_a_token_or_a_pool_held_in_a_file(file_store):
    from openfactory.adapters.agent.claude_code import _load_agent_token_pool

    file_store("CLAUDE_CODE_OAUTH_TOKEN", SECRET)
    assert _load_agent_token_pool() == [{"id": "single", "token": SECRET,
                                         "type": "subscription"}]
    file_store("OPENFACTORY_AGENT_TOKENS", json.dumps([{"id": "a", "token": SECRET},
                                                       {"id": "b", "token": ROTATED}]))
    assert [t["token"] for t in _load_agent_token_pool()] == [SECRET, ROTATED]


def test_a_projects_token_env_names_a_file_and_the_tracker_reads_it(secrets):
    from openfactory.credentials import tracker_credential_source, tracker_token_for

    secrets("acme-jira", SECRET)
    project = Project(name="acme", repo_path="/tmp/acme",
                      tracker=ProviderRef(kind="jira", repo="ACME",
                                          options={"token_env": "file:acme-jira"}))

    assert tracker_token_for(project) == SECRET
    assert tracker_credential_source(project) == "file:acme-jira"


def test_a_vendor_that_resolves_its_own_credential_reads_a_file_and_says_which(secrets):
    """The Azure rows answer through `credential_source`, which the doctor asks too."""
    from openfactory.adapters.azure_devops import credential_source, token_for
    from openfactory.credentials import describe_source, forge_credential_source, forge_token_for

    secrets("acme-ado", SECRET)
    options = {"token_env": "file:acme-ado"}
    project = Project(name="acme", repo_path="/tmp/acme",
                      forge=ProviderRef(kind="azure_devops", repo="Acme/app", options=options))

    assert credential_source(options)[0] == "file:acme-ado"
    assert token_for(options) == SECRET
    assert forge_token_for(project) == SECRET
    source = forge_credential_source(project)
    assert source == "file:acme-ado"
    said = describe_source(source)
    assert "file:acme-ado" in said and str(secrets.directory) in said and SECRET not in said


def test_the_container_box_passes_a_file_held_name_by_name_with_its_value_in_dockers_env(
        file_store, monkeypatch):
    import openfactory.adapters.sandbox.container as container
    from openfactory.adapters.sandbox.base import Workspace

    file_store("ACME_SCANNER_TOKEN", SECRET)
    box = container.ContainerSandbox(image="img", extra_env=("ACME_SCANNER_TOKEN",))
    box._container = "openfactory-acme-1"
    seen: dict = {}

    def popen(argv, **kw):
        seen.update(argv=argv, env=kw.get("env"))
        return object()

    monkeypatch.setattr(container.subprocess, "Popen", popen)
    monkeypatch.setattr(container, "run_and_stream", lambda proc, **kw: (0, ""))
    box.run(workspace=Workspace(path=Path("/workspace"), branch="b", base_branch="main"),
            command="true", timeout=5)

    assert "-e" in seen["argv"] and "ACME_SCANNER_TOKEN" in seen["argv"]
    assert not any(SECRET in part for part in seen["argv"]), "a value rode on the command line"
    assert seen["env"]["ACME_SCANNER_TOKEN"] == SECRET


def test_the_harness_token_the_adapter_chose_is_not_undone_by_a_file(file_store, monkeypatch):
    """`_apply_token` puts the pool's active token in this process's environment; a file holding
    the first one must not hand the box a token the pool rotated away from."""
    from openfactory.adapters.sandbox.container import ContainerSandbox

    file_store("CLAUDE_CODE_OAUTH_TOKEN", SECRET)
    assert ContainerSandbox(image="img")._passthrough()["CLAUDE_CODE_OAUTH_TOKEN"] == SECRET
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", ROTATED)
    assert ContainerSandbox(image="img")._passthrough()["CLAUDE_CODE_OAUTH_TOKEN"] == ROTATED


def test_a_worktree_workload_receives_a_declared_name_held_in_a_file_and_no_other(file_store):
    from openfactory.adapters.sandbox.worktree import _scrubbed_env

    file_store("ACME_SCANNER_TOKEN", SECRET)
    file_store("ACME_UNDECLARED_TOKEN", ROTATED)

    env = _scrubbed_env(keep=("ACME_SCANNER_TOKEN",))
    assert env.get("ACME_SCANNER_TOKEN") == SECRET
    assert "ACME_UNDECLARED_TOKEN" not in env
    assert DIR_VAR not in env, "the path to every secret reached the workload"


def test_a_remote_box_is_handed_a_file_held_secret_as_a_value_and_a_variable_by_name(
        secrets, monkeypatch):
    from openfactory.credentials import BOX_TOKEN_ENV, box_credential_env, box_options

    secrets("acme-jira", SECRET)
    held = Project(name="acme", repo_path="/tmp/acme",
                   tracker=ProviderRef(kind="jira", repo="ACME",
                                       options={"token_env": "file:acme-jira",
                                                "board": "7"}))
    assert box_options(held, "tracker") == {"token_env": BOX_TOKEN_ENV["tracker"], "board": "7"}
    # a project that names no forge is its tracker's forge too, so both axes travel
    assert box_credential_env(held) == {BOX_TOKEN_ENV["tracker"]: SECRET,
                                        BOX_TOKEN_ENV["forge"]: SECRET}

    monkeypatch.setenv("ACME_JIRA_TOKEN", SECRET)
    named = Project(name="acme", repo_path="/tmp/acme",
                    tracker=ProviderRef(kind="jira", repo="ACME",
                                        options={"token_env": "ACME_JIRA_TOKEN"}))
    assert box_options(named, "tracker") == {"token_env": "ACME_JIRA_TOKEN"}
    assert box_credential_env(named) == {}, "a value was written where a name sufficed"


def test_a_remote_box_is_handed_the_deployments_pair_when_a_file_holds_it(file_store):
    from openfactory.credentials import BOX_TOKEN_ENV, box_credential_env, box_options

    file_store("OPENFACTORY_BOT_TOKEN", SECRET)
    project = Project(name="acme", repo_path="/tmp/acme",
                      forge=ProviderRef(kind="github", repo="acme/app"))

    assert box_options(project, "forge")["token_env"] == BOX_TOKEN_ENV["forge"]
    assert box_credential_env(project)[BOX_TOKEN_ENV["forge"]] == SECRET


def test_readiness_counts_a_box_env_name_the_store_answers_for_as_set(file_store):
    """`env_names` read `box.env` against the environment alone, so a name held in a file — which
    the box does receive — was reported as not set at all."""
    from types import SimpleNamespace

    from openfactory.onboarding import readiness

    file_store("ACME_SCANNER_TOKEN", SECRET)
    probes = readiness.probes_for(Project(name="acme", repo_path="/tmp/acme",
                                          box=BoxConfig(env=["ACME_SCANNER_TOKEN"])))
    assert probes.stored("ACME_SCANNER_TOKEN") == SECRET

    seen = SimpleNamespace(box_env_names=lambda: ["ACME_SCANNER_TOKEN", "ACME_TYPO_TOKEN"],
                           environ=lambda: {}, stored=probes.stored)
    finding, _ = readiness._env_names(seen, "the worker")
    assert not finding.ok and "ACME_TYPO_TOKEN" in finding.message
    assert "ACME_SCANNER_TOKEN" not in finding.message and SECRET not in finding.message


# ── the image's pull credential: for the pull, and never for the box ────────────────────────────

class _Docker:
    """A `docker` client that records what it was asked and what its configuration held."""

    def __init__(self, rc: int = 0, said: str = "sha256:ok"):
        self.rc, self.said, self.argv, self.config, self.modes = rc, said, None, None, None

    def __call__(self, argv, **kw):
        self.argv = list(argv)
        directory = argv[argv.index("--config") + 1]
        path = os.path.join(directory, "config.json")
        self.config = json.loads(Path(path).read_text())
        self.modes = (stat.S_IMODE(os.stat(directory).st_mode),
                      stat.S_IMODE(os.stat(path).st_mode))
        self.directory = directory
        return subprocess.CompletedProcess(argv, self.rc, self.said, "")


def test_the_pull_reads_the_credential_now_in_a_configuration_of_its_own_and_keeps_nothing(
        secrets):
    from openfactory.adapters.sandbox.pull import PullCredential, pull

    secrets("acme-registry", SECRET)
    docker = _Docker()
    pulled, _said = pull("registry.acme.example/ci:1",
                         PullCredential("file:acme-registry", "ci-bot"), run=docker)

    assert pulled
    assert docker.argv[-1] == "registry.acme.example/ci:1" and "pull" in docker.argv
    assert not any(SECRET in part for part in docker.argv)
    auth = docker.config["auths"]["registry.acme.example"]["auth"]
    assert base64.b64decode(auth).decode() == f"ci-bot:{SECRET}"
    assert docker.modes == (0o700, 0o600)
    assert not os.path.exists(docker.directory), "the login outlived the pull"


def test_an_image_with_no_host_is_logged_in_where_the_docker_client_files_the_hub(secrets):
    from openfactory.adapters.sandbox.pull import PullCredential, pull

    secrets("acme-registry", SECRET)
    docker = _Docker()
    pull("acme/ci:1", PullCredential("file:acme-registry", "ci-bot"), run=docker)

    assert list(docker.config["auths"]) == ["https://index.docker.io/v1/"]


def test_a_pull_credential_that_cannot_be_used_says_why_by_reference(secrets):
    from openfactory.adapters.sandbox.pull import PullCredential, pull

    docker = _Docker()
    pulled, said = pull("registry.acme.example/ci:1",
                        PullCredential("file:acme-registry", "ci-bot"), run=docker)
    assert not pulled and "file:acme-registry" in said and docker.argv is None

    secrets("acme-registry", SECRET)
    pulled, said = pull("registry.acme.example/ci:1", PullCredential("file:acme-registry"),
                        run=docker)
    assert not pulled and "box.pull_username" in said and SECRET not in said


def test_the_box_pulls_its_image_only_when_absent_and_never_carries_the_credential(
        secrets, monkeypatch):
    import openfactory.adapters.sandbox.container as container
    import openfactory.adapters.sandbox.pull as pulling
    from openfactory.adapters.sandbox.pull import PullCredential

    secrets("acme-registry", SECRET)
    asked: list[str] = []
    present = {"answer": 0}
    monkeypatch.setattr(container, "_host",
                        lambda argv, timeout=120, env=None: (asked.append(" ".join(argv)),
                                                             (present["answer"], ""))[1])
    pulls: list[str] = []
    monkeypatch.setattr(pulling, "pull", lambda image, cred, **kw: (pulls.append(image),
                                                                    (True, ""))[1])
    box = container.ContainerSandbox(
        image="registry.acme.example/ci:1",
        pull_credential=PullCredential("file:acme-registry", "ci-bot"))

    box._pull_if_absent()
    assert pulls == [], "an image the daemon holds was pulled again, and its proof may move"
    present["answer"] = 1
    box._pull_if_absent()
    assert pulls == ["registry.acme.example/ci:1"]
    assert SECRET not in json.dumps(box._passthrough()) and not any(SECRET in a for a in asked)

    monkeypatch.setattr(pulling, "pull", lambda image, cred, **kw: (False, "unauthorized"))
    with pytest.raises(RuntimeError, match="file:acme-registry") as refused:
        box._pull_if_absent()
    assert SECRET not in str(refused.value)


def test_box_prove_pulls_with_the_projects_credential(secrets, monkeypatch, tmp_path):
    """The proof obtains the image the way a job will, so a private image is provable."""
    from types import SimpleNamespace

    import openfactory.adapters.sandbox.pull as pulling
    from openfactory import box_prove
    from openfactory.adapters.sandbox import registry as sandboxes
    from openfactory.contracts import Manifest

    class _Box:
        def prepare(self, **_kw):
            return SimpleNamespace(path=str(tmp_path))

        def cleanup(self, **_kw):
            pass

    pulls: list[tuple[str, object]] = []
    monkeypatch.setattr(pulling, "pull", lambda image, cred, **kw: (pulls.append((image, cred)),
                                                                    (True, ""))[1])
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(
        argv, 0, "registry.acme.example/ci@sha256:" + "a" * 64, ""))
    monkeypatch.setattr(sandboxes, "installed_box_traits",
                        lambda _kind: SimpleNamespace(honours_image=True))
    monkeypatch.setattr(sandboxes, "build_sandbox", lambda *_a, **_kw: _Box())
    project = SimpleNamespace(name="acme", box=BoxConfig(pull_credential="file:acme-registry",
                                                         pull_username="ci-bot"))

    with box_prove.box_probes(project, "registry.acme.example/ci:1", repo_path=tmp_path,
                              manifest=Manifest(version=1, base_branch="main"), key="acme",
                              sandbox="container") as probes:
        assert probes.resolve_digest("registry.acme.example/ci:1") == "sha256:" + "a" * 64

    assert [(image, cred.reference) for image, cred in pulls] == [
        ("registry.acme.example/ci:1", "file:acme-registry")]


# ── the doctor says references and stores, never values ─────────────────────────────────────────

def test_the_doctor_reports_where_credentials_come_from_and_each_reference_a_project_names(
        secrets, monkeypatch):
    from openfactory.doctor import credential_store_line

    secrets("acme-jira", SECRET)
    secrets("acme-registry", SECRET)
    project = Project(name="acme", repo_path="/tmp/acme",
                      tracker=ProviderRef(kind="jira", repo="ACME",
                                          options={"token_env": "file:acme-jira"}),
                      box=BoxConfig(pull_credential="file:acme-registry", pull_username="ci-bot"))

    ok, said, remedy = credential_store_line(project)
    assert ok, said
    assert "from the environment" in said
    assert "`file:acme-jira` ← file:acme-jira" in said
    assert "`file:acme-registry` ← file:acme-registry" in said and "ci-bot" in said
    assert SECRET not in said + remedy

    monkeypatch.setenv(STORE_VAR, "file")
    ok, said, _ = credential_store_line(Project(name="b", repo_path="/tmp/b"))
    assert ok and "the `file` store, then from the environment" in said


#: Each way a project's credential configuration cannot work, and what the line names.
DOCTOR_FAILURES = {
    "a declared store nobody installed": (dict(store="vault"), {}, "unknown credential store"),
    "a declared file store with no directory": (dict(store="file", no_dir=True), {},
                                                "names no directory"),
    "a reference to a store nobody installed": (
        {}, dict(tracker=ProviderRef(kind="jira", repo="A", options={"token_env": "vault:x"})),
        "can never answer"),
    "a pull credential with no user name": (
        {}, dict(box=BoxConfig(pull_credential="file:acme-registry")), "box.pull_username"),
    "a pull credential that does not answer": (
        {}, dict(box=BoxConfig(pull_credential="file:missing", pull_username="ci-bot")),
        "does not answer"),
}


@pytest.mark.parametrize("case", sorted(DOCTOR_FAILURES))
def test_the_doctor_fails_a_credential_that_can_never_be_read_by_name(case, secrets, monkeypatch):
    from openfactory.doctor import credential_store_line

    deployment, fields, words = DOCTOR_FAILURES[case]
    secrets("acme-registry", SECRET)
    if "store" in deployment:
        monkeypatch.setenv(STORE_VAR, deployment["store"])
    if deployment.get("no_dir"):
        monkeypatch.delenv(DIR_VAR)

    ok, said, remedy = credential_store_line(Project(name="acme", repo_path="/tmp/acme",
                                                     **fields))
    assert not ok and words in said, said
    assert remedy and SECRET not in said + remedy


def test_the_doctor_runs_the_line_and_says_which_reference_the_harness_token_came_from(
        file_store, monkeypatch):
    from openfactory import doctor

    file_store("CLAUDE_CODE_OAUTH_TOKEN", SECRET)
    probes = doctor.probes_for(Project(name="acme", repo_path="/tmp/acme"))

    assert probes.credential_store is not None and probes.credential_store()[0]
    present, said, *_ = probes.agent_credential()
    assert present and "file:CLAUDE_CODE_OAUTH_TOKEN" in said and SECRET not in said
    from pinned_probes import a_fully_pinned_probe_set

    checks = [f.check for f in doctor.diagnose(a_fully_pinned_probe_set()).findings]
    assert "credential_store" in checks


def test_nothing_the_store_logs_holds_a_value(file_store, monkeypatch, caplog):
    """Every path that speaks — a refusal, an unknown kind, a failing add-on, a missing file —
    says a name and never the secret it was about."""
    file_store("acme-refused", SECRET, mode=0o622)
    file_store("acme-held", SECRET)
    monkeypatch.setenv("ACME_SCANNER_TOKEN", SECRET)

    class Failing:
        def resolve(self, name):
            raise RuntimeError("the vault is down")

        def describe(self, name):
            raise RuntimeError("the vault is down")

    monkeypatch.setitem(STORES, "failing", lambda: Failing())
    with caplog.at_level(logging.DEBUG):
        for reference in ("file:acme-refused", "file:acme-held", "file:acme-missing",
                          "vault:acme", "failing:acme", "ACME_SCANNER_TOKEN", "acme-held"):
            registry.resolve(reference)
            registry.describe(reference)
            registry.refusal(reference)
    assert "acme-refused" in caplog.text and "failing" in caplog.text
    assert SECRET not in caplog.text
