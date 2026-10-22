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
import shutil
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

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
    dated.chmod(0o755)  # not the umask's: 0002 (Ubuntu's, for users) makes it group-writable
    (dated / "acme-token").write_text(SECRET)
    (dated / "acme-token").chmod(0o444)
    (secrets.directory / "..data").symlink_to(dated.name)
    (secrets.directory / "acme-token").symlink_to("..data/acme-token")

    assert FileStore().resolve("acme-token") == SECRET


def test_a_file_read_through_a_shared_subdirectory_on_a_read_only_mount_is_this_users(
        secrets, monkeypatch):
    """On a mount that refuses writes a shared directory is read, and then every file read through
    it must be root's or this user's — a shared SUBDIRECTORY on the name's way too, not only the
    credential directory (review of 256c5b0, W7): `_located` answers "shared" for any directory
    asked on the way, and a file of another user's behind one is refused."""
    from openfactory.adapters.credential_store import file as store_file
    from openfactory.adapters.credential_store.base import CredentialRefused

    data = secrets.directory / "data"
    data.mkdir()
    data.chmod(0o777)
    (data / "acme-token").write_text(SECRET)
    (data / "acme-token").chmod(0o600)
    (secrets.directory / "acme-token").symlink_to("data/acme-token")
    monkeypatch.setattr(store_file, "_mount_refuses_writes", lambda fd=None, path="": True)
    real = os.fstat

    def another_users_file(fd):
        found = real(fd)
        if stat.S_ISREG(found.st_mode):
            fields = list(found)
            fields[stat.ST_UID] = os.geteuid() + 1
            return os.stat_result(fields)
        return found

    monkeypatch.setattr(os, "fstat", another_users_file)
    with pytest.raises(CredentialRefused, match="another user"):
        FileStore().resolve("acme-token")


def test_a_shared_directory_is_read_only_on_a_mount_that_refuses_writes(secrets, monkeypatch):
    """A cluster mounts its secret volume read-only, and that is the one layout a directory anyone
    may write to is read in (#822): a sticky bit stops a file being removed, not one being added."""
    from openfactory.adapters.credential_store.base import CredentialRefused

    secrets.directory.chmod(0o1777)
    secrets("acme-token", SECRET, mode=0o444)
    try:
        with pytest.raises(CredentialRefused, match="writable by"):
            FileStore().resolve("acme-token")
        _read_only(monkeypatch, file=False, directory=True)
        assert FileStore().resolve("acme-token") == SECRET
    finally:
        secrets.directory.chmod(0o700)


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


#: Each way a project's forge or tracker secret ends up held in the store: its own reference to a
#: file, and the deployment's pair moved into one.
HELD_IN_THE_STORE = {
    "a project's reference to a file": (
        {"tracker": ProviderRef(kind="jira", repo="ACME",
                                options={"token_env": "file:acme-jira", "board": "7"})},
        lambda put: put("acme-jira", SECRET), False),
    "the deployment's pair in a file": (
        {"forge": ProviderRef(kind="github", repo="acme/app")},
        lambda put: put("OPENFACTORY_BOT_TOKEN", SECRET), True),
}


@pytest.mark.parametrize("case", sorted(HELD_IN_THE_STORE))
def test_a_remote_box_is_refused_a_secret_the_store_holds_and_handed_a_variable_by_name(
        case, secrets, monkeypatch):
    """A REMOTE LAUNCHER IS HANDED SHORT-LIVED MINTED TOKENS ONLY (review of ef084ebd). A launcher
    may copy its launch environment where others can read it, and a store's secret lives as long
    as its owner keeps it, so it is refused for a remote box, by name and naming the declaration a
    launcher would need — never put into `extra_env`, never its value in the sentence."""
    from openfactory.credentials import (
        RESOLVES_REFERENCES,
        CredentialUnavailable,
        box_launch_credentials,
        box_options,
    )

    launcher = object()  # a remote launcher that declares nothing (#903)

    axes, put, declares_store = HELD_IN_THE_STORE[case]
    if declares_store:
        monkeypatch.setenv(STORE_VAR, "file")
    put(secrets)
    held = Project(name="acme", repo_path="/tmp/acme", **axes)
    with pytest.raises(CredentialUnavailable, match=RESOLVES_REFERENCES) as refused:
        box_launch_credentials(held, "fargate", launcher)
    assert SECRET not in str(refused.value)
    axis = next(iter(axes))
    assert box_options(held, axis) == dict(axes[axis].options or {}), \
        "the options were rewritten for a value that is never handed over"

    monkeypatch.delenv(STORE_VAR, raising=False)
    monkeypatch.setenv("ACME_JIRA_TOKEN", SECRET)
    named = Project(name="acme", repo_path="/tmp/acme",
                    tracker=ProviderRef(kind="jira", repo="ACME",
                                        options={"token_env": "ACME_JIRA_TOKEN"}))
    assert box_options(named, "tracker") == {"token_env": "ACME_JIRA_TOKEN"}
    assert box_launch_credentials(named, "fargate", launcher) == ({}, {}), \
        "a value was written where a name sufficed"


def test_readiness_counts_a_box_env_name_the_store_answers_for_as_set(file_store):
    """`env_names` read `box.env` against the environment alone, so a name held in a file — which
    the box does receive — was reported as not set at all."""
    from openfactory.onboarding import readiness

    file_store("ACME_SCANNER_TOKEN", SECRET)
    probes = readiness.probes_for(Project(name="acme", repo_path="/tmp/acme",
                                          box=BoxConfig(env=["ACME_SCANNER_TOKEN"])))
    assert probes.stored("ACME_SCANNER_TOKEN") == SECRET

    seen = SimpleNamespace(box_env_names=lambda: ["ACME_SCANNER_TOKEN", "ACME_TYPO_TOKEN"],
                           environ=lambda: {}, stored=probes.stored, refused=probes.refused)
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


def test_the_doctor_says_when_the_pull_credential_is_the_forges_own_token(secrets, monkeypatch):
    """A pull needs read scope only, and the forge's token writes (review of 256c5b0): the line
    says so beside the pull, bare or as `env:`, and the project still passes — the pull works."""
    from openfactory.doctor import credential_store_line

    secrets("acme-forge", SECRET)
    secrets("acme-registry", SECRET)
    monkeypatch.setenv("OPENFACTORY_BOT_TOKEN", "fictitious-bot-822e")
    own = Project(name="acme", repo_path="/tmp/acme",
                  forge=ProviderRef(kind="github", repo="acme/web",
                                    options={"token_env": "file:acme-forge"}),
                  box=BoxConfig(pull_credential="file:acme-forge", pull_username="ci-bot"))
    bot = Project(name="b", repo_path="/tmp/b",
                  box=BoxConfig(pull_credential="env:OPENFACTORY_BOT_TOKEN", pull_username="ci-bot"))
    its_own = Project(name="c", repo_path="/tmp/c",
                      box=BoxConfig(pull_credential="file:acme-registry", pull_username="ci-bot"))

    for project in (own, bot):
        ok, said, _ = credential_store_line(project)
        assert ok, said
        assert "the forge's own token" in said and "credential of its own" in said, said
        assert SECRET not in said and "fictitious-bot-822e" not in said
    ok, said, _ = credential_store_line(its_own)
    assert ok and "the forge's own token" not in said, said


#: `(the forge's token_env, the pull credential, the declared store, whether they are one)`. A
#: bare name is asked of the declared store and then of the environment, so it is the same
#: credential as a reference to either; a reference to one store is never one to another.
FORGE_AND_PULL = [
    ("acme-forge", "file:acme-forge", "file", True),
    ("file:acme-forge", "acme-forge", "file", True),
    (None, "file:OPENFACTORY_BOT_TOKEN", "file", True),
    ("acme-forge", "env:acme-forge", "file", True),
    ("acme-forge", "file:acme-forge", None, False),
    ("env:acme-forge", "file:acme-forge", "file", False),
]


@pytest.mark.parametrize(("forge", "pull", "declared", "one"), FORGE_AND_PULL)
def test_a_bare_name_is_the_forges_own_token_in_either_store_it_is_asked_of(
        forge, pull, declared, one, secrets, monkeypatch):
    """Under a `file` store a bare `acme-forge` is the file `acme-forge` when it is there, so a
    pull credential naming that file is the forge's own token (review of bd178211); with no store
    declared, the bare name is the variable alone, and the file is another credential."""
    from openfactory.doctor import credential_store_line

    secrets("acme-forge", SECRET)
    secrets("OPENFACTORY_BOT_TOKEN", SECRET)
    monkeypatch.setenv("acme-forge", SECRET)
    if declared:
        monkeypatch.setenv(STORE_VAR, declared)
    project = Project(name="acme", repo_path="/tmp/acme",
                      forge=(ProviderRef(kind="github", repo="acme/web",
                                         options={"token_env": forge}) if forge else None),
                      box=BoxConfig(pull_credential=pull, pull_username="ci-bot"))
    ok, said, _ = credential_store_line(project)
    assert ok, said
    assert ("the forge's own token" in said) is one, said
    assert SECRET not in said


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


# ── after the reviews of #822 ───────────────────────────────────────────────────────────────────

def _read_only(monkeypatch, *, file: bool = True, directory: bool = False) -> None:
    """Make the mount the file store reads through report `ST_RDONLY`, as compose's `secrets:`
    bind mount does — for the open file (`fstatvfs`) and/or the directory (`statvfs`)."""
    real_f, real_d = os.fstatvfs, os.statvfs

    def flagged(answer):
        return SimpleNamespace(f_flag=answer.f_flag | os.ST_RDONLY)

    if file:
        monkeypatch.setattr(os, "fstatvfs", lambda fd: flagged(real_f(fd)))
    if directory:
        monkeypatch.setattr(os, "statvfs", lambda path: flagged(real_d(path)))


#: Each write bit a secret or its directory can carry: who may write, and how it is set.
WRITE_BITS = {"its group": 0o020, "everyone": 0o002}


@pytest.mark.parametrize("who", sorted(WRITE_BITS))
def test_a_write_bit_is_moot_exactly_when_the_mount_refuses_writes(who, secrets, monkeypatch):
    """THE RULE (review of #822, Ubuntu's umask): on a mount that refuses writes nobody who sees
    the file can rewrite it through that mount, so its write bits are not a writer; on a writable
    mount they are, and the refusal names its repair. Both the file and the directory, both bits."""
    from openfactory.adapters.credential_store.base import CredentialRefused

    path = secrets("acme-token", SECRET, mode=0o600 | WRITE_BITS[who])
    with pytest.raises(CredentialRefused, match=f"writable by {who}") as refused:
        FileStore().resolve("acme-token")
    assert f"chmod go-w {path}" in str(refused.value) and "read-only" in str(refused.value)
    with monkeypatch.context() as mp:
        _read_only(mp)
        assert FileStore().resolve("acme-token") == SECRET

    path.chmod(0o600)
    secrets.directory.chmod(0o700 | WRITE_BITS[who])
    try:
        with pytest.raises(CredentialRefused, match=f"writable by {who}"):
            FileStore().resolve("acme-token")
        with monkeypatch.context() as mp:
            _read_only(mp, file=False, directory=True)
            assert FileStore().resolve("acme-token") == SECRET
    finally:
        secrets.directory.chmod(0o700)


def test_a_compose_secret_on_ubuntus_umask_reaches_the_deployment(secrets, monkeypatch):
    """The documented path, measured by the review: a 0664 file under `secrets:` is read."""
    secrets("OPENFACTORY_BOT_TOKEN", SECRET + "\n", mode=0o664)
    monkeypatch.setenv(STORE_VAR, "file")
    monkeypatch.setenv("OPENFACTORY_BOT_TOKEN", "fictitious-env-fallback")
    _read_only(monkeypatch)
    assert stored("OPENFACTORY_BOT_TOKEN") == SECRET


def test_a_byte_order_mark_an_editor_saved_is_not_part_of_the_secret(secrets):
    secrets("acme-token", "\ufeff" + SECRET + "\r\n")
    assert FileStore().resolve("acme-token") == SECRET


def test_a_refused_bot_token_is_red_on_the_doctor_and_names_its_repair(file_store, monkeypatch):
    """The review's measurement: a 0664 `OPENFACTORY_BOT_TOKEN` on a writable mount. The store
    line was green and the forge line asked for the variable that was set."""
    from openfactory import doctor

    path = file_store("OPENFACTORY_BOT_TOKEN", SECRET, mode=0o664)
    monkeypatch.setenv("OPENFACTORY_BOT_TOKEN", "fictitious-env-fallback")
    project = Project(name="acme", repo_path="/tmp/acme",
                      forge=ProviderRef(kind="github", repo="acme/app"))

    ok, said, remedy = doctor.credential_store_line(project)
    assert not ok and "OPENFACTORY_BOT_TOKEN" in said and f"chmod go-w {path}" in said, said
    reachable, detail = doctor.probes_for(project).forge_reachable()
    assert not reachable and doctor.REFUSED_BY_THE_STORE in detail, detail
    finding = doctor._forge(doctor.probes_for(project))
    assert "set OPENFACTORY" not in finding.remedy and finding.remedy == doctor.REFUSED_REMEDY
    assert SECRET not in said + remedy + detail + finding.message


def test_the_pull_never_returns_the_secret_or_its_login_in_what_docker_said(secrets):
    from openfactory.adapters.sandbox.pull import PullCredential, pull

    secrets("acme-registry", SECRET)
    auth = base64.b64encode(f"ci-bot:{SECRET}".encode()).decode()
    docker = _Docker(rc=1, said=f"denied for ci-bot:{SECRET} (auth {auth})")
    pulled, said = pull("registry.acme.example/ci:1",
                        PullCredential("file:acme-registry", "ci-bot"), run=docker)
    assert not pulled and "denied for ci-bot" in said
    assert SECRET not in said and auth not in said


def _a_box_whose_docker_is_recorded(monkeypatch, tmp_path, *, pulled: bool):
    import openfactory.adapters.sandbox.container as container
    import openfactory.adapters.sandbox.pull as pulling

    order: list[str] = []
    monkeypatch.setenv("OPENFACTORY_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setattr(container, "_host", lambda argv, timeout=120, env=None: (
        order.append(" ".join(argv[1:3])), (1 if argv[1:3] == ["image", "inspect"] else 0, ""))[1])
    monkeypatch.setattr(container, "_materialize_workspace",
                        lambda **kw: (order.append("clone"), "0" * 40)[1])
    monkeypatch.setattr(pulling, "pull", lambda image, cred, **kw: (
        order.append(f"PULL {cred.reference}"), (pulled, "" if pulled else "unauthorized"))[1])
    box = container.ContainerSandbox(
        image="registry.acme.example/ci:1",
        pull_credential=pulling.PullCredential("file:acme-registry", "ci-bot"))
    return box, order


def test_a_job_pulls_with_its_credential_before_anything_of_the_box_exists(
        secrets, monkeypatch, tmp_path):
    """`prepare()` is the only place a job uses the pull credential (review of #822, cut J): the
    image absent, the pull comes first — before the clone and before `docker run` — and a pull
    that fails raises, naming the reference, with nothing created."""
    secrets("acme-registry", SECRET)
    box, order = _a_box_whose_docker_is_recorded(monkeypatch, tmp_path, pulled=True)
    box.prepare(repo_path=tmp_path, base_branch="main", branch="feat/1")
    assert "PULL file:acme-registry" in order and "run --name" not in order[:1]
    pulled_at = order.index("PULL file:acme-registry")
    assert pulled_at < order.index("clone")
    assert all(not step.startswith("run") for step in order[:pulled_at])
    assert any(step.startswith("run") for step in order[pulled_at:]), order

    box, order = _a_box_whose_docker_is_recorded(monkeypatch, tmp_path, pulled=False)
    with pytest.raises(RuntimeError, match="file:acme-registry") as refused:
        box.prepare(repo_path=tmp_path, base_branch="main", branch="feat/2")
    assert "clone" not in order and not any(step.startswith("run") for step in order), order
    assert SECRET not in str(refused.value)


def _a_person_on_a_context(tmp_path, monkeypatch, name: str = "elsewhere") -> Path:
    """A docker client configuration of a person's own whose current context is `name`."""
    user = tmp_path / "user-docker"
    (user / "contexts" / "meta" / "0123").mkdir(parents=True)
    (user / "contexts" / "meta" / "0123" / "meta.json").write_text(json.dumps({"Name": name}))
    (user / "config.json").write_text(json.dumps({
        "currentContext": name, "credsStore": "desktop",
        "auths": {"registry.acme.example": {"auth": "fictitious-someone-elses-login"}}}))
    monkeypatch.setenv("DOCKER_CONFIG", str(user))
    return user


def test_the_pull_resolves_the_daemon_the_person_s_own_docker_resolves(
        secrets, tmp_path, monkeypatch):
    """`docker --config <fresh>` meant the default context, while the box's calls kept the
    person's (review of #822). The private configuration carries their `currentContext` and their
    `contexts`, and nothing of their logins."""
    from openfactory.adapters.sandbox.pull import PullCredential, pull

    secrets("acme-registry", SECRET)
    user = _a_person_on_a_context(tmp_path, monkeypatch)
    seen: dict = {}

    def docker(argv, **kw):
        directory = argv[argv.index("--config") + 1]
        seen["config"] = json.loads(Path(directory, "config.json").read_text())
        seen["contexts"] = os.path.realpath(os.path.join(directory, "contexts"))
        return subprocess.CompletedProcess(argv, 0, "sha256:ok", "")

    assert pull("registry.acme.example/ci:1", PullCredential("file:acme-registry", "ci-bot"),
                run=docker)[0]
    assert seen["config"]["currentContext"] == "elsewhere"
    assert seen["contexts"] == os.path.realpath(user / "contexts")
    assert "credsStore" not in seen["config"]
    assert seen["config"]["auths"]["registry.acme.example"]["auth"] != (
        "fictitious-someone-elses-login")
    assert (user / "contexts" / "meta" / "0123" / "meta.json").exists(), (
        "removing the private configuration removed the person's contexts")


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs the docker CLI (not a daemon)")
def test_the_real_docker_client_resolves_the_same_context_for_the_pull_and_the_box(
        secrets, tmp_path, monkeypatch):
    """Against the real client, no daemon needed: the context the pull's configuration resolves is
    the one the box's own calls resolve, for a context named in `config.json` and for one named
    by `DOCKER_CONTEXT`."""
    from openfactory.adapters.sandbox.pull import PullCredential, pull

    user = tmp_path / "user-docker"
    user.mkdir()
    monkeypatch.setenv("DOCKER_CONFIG", str(user))
    for var in ("DOCKER_HOST", "DOCKER_CONTEXT"):
        monkeypatch.delenv(var, raising=False)
    for port, name in enumerate(("elsewhere", "further"), start=1):
        # an endpoint nothing listens on: `context show` resolves a name and dials nothing
        subprocess.run(["docker", "context", "create", name, "--docker",
                        f"host=tcp://127.0.0.1:{port}"], check=True, capture_output=True)
    subprocess.run(["docker", "context", "use", "elsewhere"], check=True, capture_output=True)
    secrets("acme-registry", SECRET)

    def the_box_s(**_kw) -> str:
        return subprocess.run(["docker", "context", "show"], capture_output=True, text=True,
                              check=True).stdout.strip()

    for context, env in (("elsewhere", {}), ("further", {"DOCKER_CONTEXT": "further"})):
        for var, value in env.items():
            monkeypatch.setenv(var, value)
        shown: list[str] = []

        def docker(argv, shown=shown, **kw):
            shown.append(subprocess.run(["docker", "--config", argv[argv.index("--config") + 1],
                                         "context", "show"], capture_output=True, text=True,
                                        check=True).stdout.strip())
            return subprocess.CompletedProcess(argv, 0, "sha256:ok", "")

        pull("registry.acme.example/ci:1", PullCredential("file:acme-registry", "ci-bot"),
             run=docker)
        assert shown == [the_box_s()] == [context]


def test_the_doctor_names_a_refused_file_nobody_asked_for(file_store):
    """A planted or mis-moded file is a credential no reader names, until the day one does: the
    store line walks what the declared store holds (`listed`) as well as what the core reads."""
    from openfactory.doctor import credential_store_line

    file_store("acme-planted", SECRET, mode=0o666)
    ok, said, _ = credential_store_line(Project(name="acme", repo_path="/tmp/acme"))
    assert not ok and "acme-planted" in said and SECRET not in said, said


def test_the_board_line_says_a_refused_tracker_credential_instead_of_asking_for_it(
        file_store, monkeypatch):
    from openfactory import doctor
    from openfactory.adapters.board import factory

    file_store("ACME_JIRA_TOKEN", SECRET, mode=0o664)
    read: list[object] = []
    monkeypatch.setattr(factory, "build_board", lambda project, token_provider=None:
                        SimpleNamespace(column_names=lambda: read.append(1) or ["To Do"]))
    project = Project(name="acme", repo_path="/tmp/acme",
                      tracker=ProviderRef(kind="jira", repo="ACME",
                                          options={"token_env": "ACME_JIRA_TOKEN"}))
    finding = doctor._board(doctor.probes_for(project))
    assert not finding.ok and not read
    assert doctor.REFUSED_BY_THE_STORE in finding.remedy and "ACME_JIRA_TOKEN" in finding.remedy
    assert SECRET not in finding.message + finding.remedy


# ── the review of 493875d3 ──────────────────────────────────────────────────────────────────────

def test_the_box_is_created_with_a_file_held_name_in_dockers_environment_not_its_argv(
        file_store, monkeypatch, tmp_path):
    """`prepare()`'s `docker run` hands a `box.env` name held in a file the way `run()`'s `docker
    exec` does: the name on the command line, the value only in the client's environment."""
    import openfactory.adapters.sandbox.container as container

    file_store("ACME_SCANNER_TOKEN", SECRET)
    created: list[tuple[list[str], dict | None]] = []
    monkeypatch.setenv("OPENFACTORY_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setattr(container, "_host", lambda argv, timeout=120, env=None: (
        created.append((list(argv), env)), (0, ""))[1])
    monkeypatch.setattr(container, "_materialize_workspace", lambda **kw: "0" * 40)
    box = container.ContainerSandbox(image="img", extra_env=("ACME_SCANNER_TOKEN",))
    box.prepare(repo_path=tmp_path, base_branch="main", branch="feat/1")

    argv, env = next((a, e) for a, e in created if a[1:2] == ["run"])
    assert "ACME_SCANNER_TOKEN" in argv and not any(SECRET in part for part in argv)
    assert env is not None and env["ACME_SCANNER_TOKEN"] == SECRET


def test_the_doctor_walks_a_listing_store_by_its_listing_and_parses_nothing(
        file_store, monkeypatch):
    """The store line parsed the whole package on every run (2.8 s, review of 493875d3). A store
    that lists what it holds is walked by its listing — every refusal of an entry is of an entry
    it lists — and only a store that cannot list is asked by every name the core reads."""
    from openfactory import environ
    from openfactory.doctor import credential_store_line

    def parsed(*_a, **_kw):
        raise AssertionError("the package was parsed for a store that lists what it holds")

    file_store("OPENFACTORY_BOT_TOKEN", SECRET, mode=0o664)
    monkeypatch.setattr(environ, "names_read", parsed)
    ok, said, _ = credential_store_line(Project(name="acme", repo_path="/tmp/acme"))
    assert not ok and "OPENFACTORY_BOT_TOKEN" in said


def _the_panel_and_product_tokens_in_files(file_store):
    file_store("OPENFACTORY_PANEL_TOKEN", "fictitious-panel-0001")
    file_store("OPENFACTORY_PRODUCT_TOKEN", "fictitious-product-0002")


def test_readiness_counts_a_panel_and_a_product_token_held_in_files(file_store):
    """`product_role` read the door's variables from the environment alone, so a deployment that
    moved them into files was told its panel is open to everyone (review of 493875d3)."""
    from openfactory.onboarding import readiness

    _the_panel_and_product_tokens_in_files(file_store)
    wired = readiness.probes_for(Project(name="acme", repo_path="/tmp/acme"))
    # what `_product_role` reads, and nothing off this machine but the store the test declared
    probes = SimpleNamespace(project_name="acme", product_enabled=lambda: True,
                             product_admins=lambda: ["alice"], environ=lambda: {},
                             stored=wired.stored, refused=wired.refused)
    finding, _ = readiness._product_role(probes, "the worker")
    assert finding.ok and "open to everyone" not in finding.message, finding.message

    (file_store.directory / "OPENFACTORY_PANEL_TOKEN").chmod(0o664)  # now refused
    assert "writable by its group" in wired.refused("OPENFACTORY_PANEL_TOKEN")
    finding, _ = readiness._product_role(probes, "the worker")
    assert not finding.ok and "refuses OPENFACTORY_PANEL_TOKEN" in finding.message
    assert "fictitious-" not in finding.message


def test_certify_reads_the_panels_tokens_from_the_store_or_says_it_cannot(file_store,
                                                                          monkeypatch):
    from openfactory.certify import controls

    env = dict(os.environ)
    reading = SimpleNamespace(env=env)
    assert controls._panel(reading, None)[0] == controls.FAIL  # nothing anywhere: exposed
    _the_panel_and_product_tokens_in_files(file_store)
    result, detail, _ = controls._panel(reading, None)
    assert result == controls.PASS and "held in the `file` credential store" in detail

    (file_store.directory / "OPENFACTORY_PANEL_TOKEN").chmod(0o664)
    assert controls._panel(reading, None)[0] == controls.UNKNOWN

    # certify beside `.env.compose`, which declares a store this process cannot read
    monkeypatch.delenv(STORE_VAR)
    result, detail, _ = controls._panel(SimpleNamespace(env={**env, STORE_VAR: "file"}), None)
    assert result == controls.UNKNOWN and "not checked here" in detail


def test_certify_redacts_what_the_store_holds_and_what_a_reference_names(file_store,
                                                                        monkeypatch):
    """`_secret_values` collected the values of variables, so a token held in a file — or named by
    `token_env: file:<name>` — was a value the pack did not know to redact."""
    from openfactory.certify import pack

    _the_panel_and_product_tokens_in_files(file_store)
    file_store("acme-jira", "fictitious-jira-0003")
    row = Project(name="acme", repo_path="/tmp/acme",
                  tracker=ProviderRef(kind="jira", repo="ACME",
                                      options={"token_env": "file:acme-jira"}))
    values = pack._secret_values([row], dict(os.environ))
    assert {"fictitious-panel-0001", "fictitious-product-0002", "fictitious-jira-0003"} <= values


def test_a_stale_refused_token_file_stops_the_harness_though_the_pool_answers(file_store,
                                                                            monkeypatch):
    """The pool answered, the boxes withheld `CLAUDE_CODE_OAUTH_TOKEN` because a stale file of that
    name was refused, and `_apply_token` puts the pool's token exactly there: every job ran on
    nothing under a green agent line (review of 493875d3). Any refused credential of the harness
    now stops it, by name, and the agent line says it."""
    from openfactory import doctor
    from openfactory.adapters.agent.claude_code import POOL, ClaudeCodeAdapter

    file_store(POOL, json.dumps([{"id": "a", "token": SECRET}]))
    file_store("CLAUDE_CODE_OAUTH_TOKEN", "fictitious-stale", mode=0o664)

    adapter = ClaudeCodeAdapter()
    assert [t["id"] for t in adapter._pool] == ["a"]
    assert "CLAUDE_CODE_OAUTH_TOKEN" in adapter._refused
    ran: list[object] = []
    monkeypatch.setattr(adapter, "_invoke_once", lambda *a, **kw: ran.append(a))
    result = adapter._invoke(None, None, "say hello", "executor", tools=[], model=None,
                             context=None)
    assert not result.ok and not ran and "CLAUDE_CODE_OAUTH_TOKEN" in result.summary

    present, said, *_ = doctor.probes_for(Project(name="acme", repo_path="/tmp/acme")) \
        .agent_credential()
    assert not present and "CLAUDE_CODE_OAUTH_TOKEN" in said and SECRET not in said

    # …AND ONBOARDING DOES NOT OFFER A PASS THE HARNESS WOULD REFUSE (review of ef084ebd)
    import shutil

    from openfactory.onboarding import context as ctx
    from openfactory.onboarding import onboard as ob

    monkeypatch.setattr(shutil, "which", lambda _b: "/usr/bin/claude")
    monkeypatch.setattr("openfactory.adapters.agent.build_asker", lambda p: object())
    monkeypatch.setattr("openfactory.adapters.sandbox.registry.judging_worktree",
                        lambda p, root=None: object())
    monkeypatch.setattr(ctx, "agent_ask", lambda *a, **k: (lambda *_a, **_k: ""))
    ask_fn, mode = ob.semantic_pass_for(Project(name="acme", repo_path="/tmp/acme"), Path("/tmp"))
    assert ask_fn is None and "refused" in mode and "CLAUDE_CODE_OAUTH_TOKEN" in mode, mode


def test_the_names_a_harness_refuses_on_are_read_off_its_own_table():
    """One table (review of ef084ebd): what the doctor and onboarding ask is what the harness reads,
    walked off its own reader — for every harness that has one."""
    from openfactory.adapters.agent.claude_code import CREDENTIALS
    from openfactory.adapters.agent.registry import HARNESS_CREDENTIALS, credential_names

    assert credential_names("claude_code") == list(CREDENTIALS)
    for kind in HARNESS_CREDENTIALS:
        assert credential_names(kind), f"{kind}'s credential reader asks no setting"


# ── the review of ef084ebd ──────────────────────────────────────────────────────────────────────

def test_what_is_checked_is_the_file_that_is_read_not_the_path(secrets, monkeypatch):
    """ASKED OF THE OPEN FILE (`fstat`), not of the path: a file swapped in under the name between
    the open and the check is not the one read. Here the opened file is 0664 and a 0600 one is
    renamed over its path right after the open — a check of the path would pass and read the
    refused file's content."""
    from openfactory.adapters.credential_store.base import CredentialRefused

    path = secrets("acme-token", "fictitious-refused-content", mode=0o664)
    resolved = os.path.realpath(path)
    real_open = os.open

    def open_then_swap(target, flags, *a, **kw):
        fd = real_open(target, flags, *a, **kw)
        if os.fspath(target) == resolved:
            fresh = secrets.directory / "fresh"
            fresh.write_text(SECRET)
            fresh.chmod(0o600)
            os.rename(fresh, path)
        return fd

    monkeypatch.setattr(os, "open", open_then_swap)
    with pytest.raises(CredentialRefused, match="writable by its group"):
        FileStore().resolve("acme-token")


def test_a_link_put_under_the_name_after_it_was_resolved_is_not_followed(secrets, monkeypatch):
    """`O_NOFOLLOW`: the name is resolved first and opened second, and a link put there in between
    is refused when it is opened rather than followed. The resolution is made to miss the link."""
    from openfactory.adapters.credential_store.base import CredentialRefused

    secrets("acme-other", SECRET)
    entry = os.path.join(os.path.realpath(secrets.directory), "acme-token")
    os.symlink("acme-other", entry)
    real, other = os.lstat, os.path.join(os.path.dirname(entry), "acme-other")
    monkeypatch.setattr(os, "lstat", lambda p, *a, **kw: real(other) if os.fspath(p) == entry
                        else real(p, *a, **kw))
    with pytest.raises(CredentialRefused, match="could not be opened"):
        FileStore().resolve("acme-token")


def test_an_answer_never_shows_its_value(file_store):
    """`Answer.value` is out of the repr, so an answer printed or logged by accident says where a
    secret is and never what it is."""
    file_store("ACME_SCANNER_TOKEN", SECRET)
    found = registry.lookup("ACME_SCANNER_TOKEN")
    assert found.value == SECRET
    assert SECRET not in repr(found) and SECRET not in str(found)
    assert "file:ACME_SCANNER_TOKEN" in repr(found)


def test_jiras_anonymous_answer_says_a_refused_token_not_the_variable_to_set(secrets):
    """#749's sentence for a tokenless Jira asked to "Set JIRA_API_TOKEN" — over a reference the
    store refused, a variable that is not read in its place. The row hands the refusal over, and
    the sentence says it."""
    from openfactory.adapters.tracker.jira import _not_one_account
    from openfactory.adapters.tracker.registry import build_tracker

    secrets("acme-jira", SECRET, mode=0o664)
    project = Project(name="acme", repo_path="/tmp/acme",
                      tracker=ProviderRef(kind="jira", repo="ACME",
                                          options={"token_env": "file:acme-jira",
                                                   "site": "https://acme.example"}))
    tracker = build_tracker(project)
    assert tracker.token is None and "file:acme-jira" in tracker.refused
    said = _not_one_account("ana@acme.example", "GET", "/rest/api/3/issue/ACME-1",
                            has_token=False, refused=tracker.refused)
    assert "refused by the credential store" in said and "file:acme-jira" in said
    assert "Set JIRA_API_TOKEN" not in said and SECRET not in said
