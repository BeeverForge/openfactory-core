"""A credential the store refuses opens no door, and nothing is used in its place (review of #822).

THE DEFECT. `credential_store.stored` answers None for a refusal, as for a name nothing holds, and
every reader that asks "is a credential configured?" read None as "no". So a refused panel token
opened the panel to everyone (`OPENFACTORY_PANEL_TOKEN` set, GET `/api/projects` 401 → 200), a
refused project reference was handed the deployment's own token, a refused tracker override
became the bot's, and the doctor said "set the variable" over a variable that was set.

THE RULE, FOR THE WHOLE FAMILY: a refusal is an answer, and it is final. Whatever the store refuses
— a store nobody installed, a directory it cannot trust, a file it cannot trust, an add-on that
refuses or fails — every consumer that reads a credential through it keeps its door shut and uses
nothing in the refused one's place: not the variable of the same name, not the next name of its
chain, not a mint, not a generated key, not a login.

So this is a product of two tables, and both are tied to the code:

  · `REFUSALS`, every way the store refuses a deployment credential. The file store's share is
    held to its code: every `raise CredentialRefused` in `file.py` is fired by one of them, or is
    exempt here with the reason (`test_every_refusal_the_file_store_can_give_is_a_case`);
  · `CONSUMERS`, every reader outside the store. Each names the module it reads in, and every
    module that imports the store must be one of them (`test_every_module_that_asks_the_store_is_a_
    consumer_here`), so a new reader joins this test or fails it by name. Each consumer reads its
    names from the code (`CLOSING_ENVS`, `claude_code.CREDENTIALS`, `credentials._GENERIC`, …), and
    in a chain every name AFTER the refused one answers a fallback — the value a door that folds a
    refusal into "absent" would take.
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
import os
import pathlib
import traceback
from dataclasses import dataclass

import pytest

from openfactory.adapters.credential_store import registry
from openfactory.adapters.credential_store.base import CredentialRefused
from openfactory.adapters.credential_store.file import DIR_VAR, MAX_BYTES, FileStore
from openfactory.adapters.credential_store.registry import STORE_VAR, STORES

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "openfactory"

#: What a fallback would hand over — recognisable in any answer that should not hold it.
FALLBACK = "fictitious-fallback-5c0d"
#: A `box.env` name a project declares: the deployment's, never the code's.
BOX_NAME = "ACME_SCANNER_TOKEN"
#: A project's own reference, a bare name: a deployment credential by that name.
PROJECT_NAME = "ACME_PROJECT_TOKEN"


@pytest.fixture(autouse=True)
def _no_store_declared(monkeypatch):
    monkeypatch.delenv(STORE_VAR, raising=False)
    monkeypatch.delenv(DIR_VAR, raising=False)


@dataclass
class Bench:
    """One case's world: a credential directory, declared, and the hooks to change it."""

    monkeypatch: pytest.MonkeyPatch
    tmp_path: pathlib.Path
    directory: pathlib.Path

    def file(self, name: str, value: str, mode: int = 0o600) -> pathlib.Path:
        path = self.directory / name
        path.write_text(value)
        path.chmod(mode)
        return path


def _bench(monkeypatch, tmp_path: pathlib.Path) -> Bench:
    """A credential directory of its own, declared as this deployment's `file` store."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    directory = tmp_path / "secrets"
    directory.mkdir()
    directory.chmod(0o700)
    monkeypatch.setenv(STORE_VAR, "file")
    monkeypatch.setenv(DIR_VAR, str(directory))
    return Bench(monkeypatch, tmp_path, directory)


def _tidy(b: Bench) -> None:
    """Modes a temporary directory's removal needs, put back."""
    b.directory.chmod(0o700)
    for child in b.directory.iterdir():
        if child.is_file() and not child.is_symlink():
            child.chmod(0o600)


@pytest.fixture
def bench(monkeypatch, tmp_path):
    made = _bench(monkeypatch, tmp_path)
    yield made
    _tidy(made)


def _each_refusal(tmp_path: pathlib.Path, name: str, *, skip: tuple[str, ...] = ()):
    """`(label, the Bench it was arranged on)` for each of `REFUSALS`, each in a directory and a
    monkeypatch of its own, undone after it; a case that cannot be arranged here is passed over."""
    for i, (label, arrange) in enumerate(REFUSALS.items()):
        if label in skip:
            continue
        with pytest.MonkeyPatch.context() as mp:
            b = _bench(mp, tmp_path / f"case-{i}")
            try:
                arrange(b, name)
            except pytest.skip.Exception:
                continue
            try:
                yield label, b
            finally:
                _tidy(b)


# ── every way the store refuses ─────────────────────────────────────────────────────────────────

def _unknown_kind(b: Bench, name: str) -> None:
    b.monkeypatch.setenv(STORE_VAR, "fiel")


def _no_directory(b: Bench, name: str) -> None:
    b.monkeypatch.delenv(DIR_VAR)


def _missing_directory(b: Bench, name: str) -> None:
    b.monkeypatch.setenv(DIR_VAR, str(b.tmp_path / "missing"))


def _not_a_directory(b: Bench, name: str) -> None:
    (b.tmp_path / "a-file").write_text("")
    b.monkeypatch.setenv(DIR_VAR, str(b.tmp_path / "a-file"))


def _open_directory(b: Bench, name: str) -> None:
    b.file(name, "fictitious-held-in-the-file")
    b.directory.chmod(0o777)


def _group_writable(b: Bench, name: str) -> None:
    b.file(name, "fictitious-held-in-the-file", 0o664)  # Ubuntu's umask, on a writable mount


def _world_writable(b: Bench, name: str) -> None:
    b.file(name, "fictitious-held-in-the-file", 0o646)


def _a_pipe(b: Bench, name: str) -> None:
    os.mkfifo(b.directory / name)


def _too_large(b: Bench, name: str) -> None:
    b.file(name, "x" * (MAX_BYTES + 1))


def _not_text(b: Bench, name: str) -> None:
    b.file(name, "")
    (b.directory / name).write_bytes(b"\xff\xfe\x00")


def _leads_outside(b: Bench, name: str) -> None:
    (b.tmp_path / "elsewhere").write_text("fictitious-held-outside")
    (b.directory / name).symlink_to(b.tmp_path / "elsewhere")


def _planted_in_a_shared_directory(b: Bench, name: str) -> None:
    b.directory.chmod(0o1777)
    path = b.file(name, "fictitious-planted", 0o600)
    if os.geteuid() == 0:
        os.chown(path, 54321, -1)  # root's own files are trusted; plant it as somebody else
    else:
        owner = os.geteuid()
        b.monkeypatch.setattr(os, "geteuid", lambda: owner + 1)


def _unreadable(b: Bench, name: str) -> None:
    if os.geteuid() == 0:
        pytest.skip("root opens a file whatever its mode")
    b.file(name, "fictitious-held-in-the-file", 0o000)


class _Refusing:
    def resolve(self, name):
        raise CredentialRefused(f"the acme vault will not hand `{name}` over")

    def describe(self, name):
        return f"the acme vault entry `{name}`"


class _Failing:
    def resolve(self, name):
        raise RuntimeError("the acme vault is down")

    def describe(self, name):
        return f"the acme vault entry `{name}`"


def _addon_refuses(b: Bench, name: str) -> None:
    b.monkeypatch.setitem(STORES, "acme", lambda: _Refusing())
    b.monkeypatch.setenv(STORE_VAR, "acme")


def _addon_fails(b: Bench, name: str) -> None:
    b.monkeypatch.setitem(STORES, "acme", lambda: _Failing())
    b.monkeypatch.setenv(STORE_VAR, "acme")


#: label → how the store is made to refuse the deployment credential `name`. The file store's
#: entries are held to `file.py` by the guard below; the others are the registry's own refusals.
REFUSALS = {
    "a declared store nobody installed": _unknown_kind,
    "a declared file store with no directory": _no_directory,
    "a directory that does not exist": _missing_directory,
    "a directory that is a file": _not_a_directory,
    "a directory others may write to": _open_directory,
    "a file its group may write, on a writable mount": _group_writable,
    "a file anyone may write": _world_writable,
    "a pipe named like the secret": _a_pipe,
    "a file too large to be a credential": _too_large,
    "a file that is not text": _not_text,
    "a link that leads outside the directory": _leads_outside,
    "a file another user planted in a shared directory": _planted_in_a_shared_directory,
    "a file this user cannot open": _unreadable,
    "an add-on store that refuses": _addon_refuses,
    "an add-on store that fails": _addon_fails,
}

#: The file store's refusals no deployment credential can be given, and why.
NOT_A_DEPLOYMENT_CASE = {
    "is not a file name": "a deployment credential's name is a variable name, which always is a "
                          "file name; a reference that is not one is "
                          "`test_the_file_store_refuses_by_name_what_it_should_not_trust`'s",
    "grew past": "a race between the size check and the read; the size check is the case above",
}


#: The cases that are the registry's refusals, not the file store's.
NOT_THE_FILE_STORE = ("a declared store nobody installed", "an add-on store that refuses",
                      "an add-on store that fails")


def test_every_refusal_the_file_store_can_give_is_a_case(tmp_path):
    """CASES READ FROM THE CODE: every `raise CredentialRefused` in `file.py` is fired by one of
    `REFUSALS` (traced to its line), or is exempt above with its reason. A refusal added to the
    store without a case here fails by its own line."""
    source = pathlib.Path(registry.__file__).with_name("file.py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    raises = {node.lineno: ast.unparse(node.exc) for node in ast.walk(tree)
              if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
              and getattr(node.exc.func, "id", "") == CredentialRefused.__name__}
    assert len(raises) >= 10, raises

    fired: set[int] = set()
    for _label, _b in _each_refusal(tmp_path, "ACME_CASE_TOKEN", skip=NOT_THE_FILE_STORE):
        with pytest.raises(CredentialRefused) as refused:
            FileStore().resolve("ACME_CASE_TOKEN")
        fired.add(next(f.lineno for f in reversed(traceback.extract_tb(refused.tb))
                       if f.filename == str(source)))
    if os.geteuid() == 0:  # root opens a file whatever its mode: that case skipped itself
        fired |= {line for line, text in raises.items() if "could not be opened" in text}

    exempt = {line for line, text in raises.items()
              if any(words in text for words in NOT_A_DEPLOYMENT_CASE)}
    missing = {line: raises[line] for line in set(raises) - fired - exempt}
    assert not missing, f"refusals of file.py no case here gives: {missing}"


def test_every_refusal_the_file_store_gives_names_its_cause_and_its_repair(tmp_path):
    """The house rule (CONTRIBUTING.md, "Failures speak by name"): one sentence, the cause and then
    the remedy. Each refusal says what is wrong and, after a dash, what to do — and never a
    value. The review found them naming the cause alone, so the doctor fell back to a remedy
    about reference syntax over a file that only needed `chmod`."""
    for label, _b in _each_refusal(tmp_path, "ACME_CASE_TOKEN", skip=NOT_THE_FILE_STORE):
        with pytest.raises(CredentialRefused) as refused:
            FileStore().resolve("ACME_CASE_TOKEN")
        cause, dash, repair = str(refused.value).rpartition(" — ")
        assert dash and cause and len(repair.split()) >= 3, (label, str(refused.value))
        assert "fictitious-" not in str(refused.value), label


def test_each_case_is_a_refusal_the_store_says(tmp_path):
    """The verifier of the table: each arrangement makes `lookup` say a refusal — so a case that
    stopped refusing cannot pass the product below as a door that stayed shut by accident."""
    seen = []
    for label, _b in _each_refusal(tmp_path, "ACME_CASE_TOKEN"):
        found = registry.lookup("ACME_CASE_TOKEN")
        assert found.refused and found.value is None, label
        seen.append(label)
    assert len(seen) >= len(REFUSALS) - 1, seen


# ── every consumer ───────────────────────────────────────────────────────────────────────────────

def _says_a_refusal(said: str, names: tuple[str, ...], refused: str) -> bool:
    """Whether `said` names a refusal on the walk to `refused`: that name, or one asked before it,
    which a store that refuses everything refuses first."""
    return "refused" in said and any(n in said for n in names[:names.index(refused) + 1])


def _chain(b: Bench, names: tuple[str, ...], refused: str, value=lambda n: FALLBACK) -> None:
    """In a chain of `names`, every name AFTER `refused` answers a fallback, and `refused`'s own
    variable does too — what a reader that folds a refusal into "absent" would take next."""
    for name in names[names.index(refused):]:
        b.monkeypatch.setenv(name, value(name))


def _door(b: Bench, name: str) -> None:
    from openfactory.identity import build_identity
    from openfactory.identity.local import CLOSING_ENVS, LocalIdentity

    for other in CLOSING_ENVS:
        b.monkeypatch.delenv(other, raising=False)
    b.monkeypatch.delenv("OPENFACTORY_IDENTITY", raising=False)
    rows = name.endswith("S")
    b.monkeypatch.setenv(name, f"{FALLBACK}:alice:Alice" if rows else FALLBACK)

    provider = LocalIdentity()
    assert provider.open_to_everyone() is False, "a refused closing variable opened the door"
    assert provider.identify(credential=FALLBACK) is None, "a refusal was replaced by its variable"
    assert name in provider.misconfiguration()
    with pytest.raises(ValueError, match=name):
        build_identity()

    from fastapi.testclient import TestClient

    from openfactory.api.app import app

    client = TestClient(app)
    for path in ("/api/projects", "/api/whoami"):
        assert client.get(path).status_code == 503, path
    assert client.get("/api/whoami",
                      headers={"Authorization": f"Bearer {FALLBACK}"}).status_code == 503


def _oidc(b: Bench, name: str) -> None:
    from openfactory.identity import build_identity
    from openfactory.identity.oidc import CLIENT_ID_ENV, ISSUER_ENV, OidcIdentity

    b.monkeypatch.setenv("OPENFACTORY_IDENTITY", "oidc")
    b.monkeypatch.setenv(ISSUER_ENV, "https://idp.acme.example")
    b.monkeypatch.setenv(CLIENT_ID_ENV, "acme-panel")
    b.monkeypatch.setenv(name, FALLBACK)

    provider = OidcIdentity()
    assert provider.settings.client_secret != FALLBACK
    assert name in provider.misconfiguration()
    assert provider.identify(credential="a.b.c") is None
    with pytest.raises(ValueError, match=name):
        build_identity()


def _mint_is_fallback(b: Bench) -> None:
    import openfactory.credentials as credentials

    b.monkeypatch.setattr(credentials, "_deployment_mint", lambda ref: FALLBACK)
    b.monkeypatch.setattr(credentials, "_deployment_provider", lambda ref: (lambda: FALLBACK))


def _every_resolution_of(project, axis: str) -> list[object]:
    import openfactory.credentials as c

    if axis == "tracker":
        return [c.tracker_token_for(project), c.tracker_credential_source(project),
                c.deployment_tracker_token(project), c.deployment_tracker_provider(project)]
    return [c.forge_token_for(project), c.forge_credential_source(project),
            c.deployment_forge_token(project), c.deployment_forge_provider(project)]


def _project_reference(b: Bench, name: str) -> None:
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.credentials import _GENERIC, axis_refusal

    _mint_is_fallback(b)
    b.monkeypatch.setenv(name, FALLBACK)
    for each in (*_GENERIC["tracker"], *_GENERIC["forge"], "JIRA_API_TOKEN"):
        b.monkeypatch.setenv(each, FALLBACK)
    for axis, kind, repo in (("tracker", "jira", "ACME"), ("forge", "github", "acme/app")):
        project = Project(name="acme", repo_path="/tmp/acme",
                          **{axis: ProviderRef(kind=kind, repo=repo,
                                               options={"token_env": name})})
        assert _every_resolution_of(project, axis) == [None, "", None, None], axis
        assert name in axis_refusal(project, axis)


def _vendor_default(b: Bench, name: str) -> None:
    from openfactory.adapters.credential.registry import SHIPPED_ENV
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.credentials import _GENERIC

    _mint_is_fallback(b)
    for each in _GENERIC["tracker"]:
        b.monkeypatch.setenv(each, FALLBACK)
    b.monkeypatch.setenv(name, FALLBACK)
    kind = next(k for k, variable in SHIPPED_ENV.items() if variable == name)
    project = Project(name="v", repo_path="/tmp/v", tracker=ProviderRef(kind=kind, repo="ACME"))
    assert _every_resolution_of(project, "tracker")[:3] == [None, "", None]


def _generic_pair(b: Bench, name: str) -> None:
    import openfactory.credentials as c
    from openfactory.contracts.project import Project, ProviderRef

    _mint_is_fallback(b)
    for axis in ("tracker", "forge"):
        names = c._GENERIC[axis]
        if name not in names:
            continue
        for each in names:
            b.monkeypatch.delenv(each, raising=False)
        _chain(b, names, name)
        generic = c.tracker_token if axis == "tracker" else c.forge_token
        assert generic() is None, f"a refused {name} was answered by the next of {names}"
        project = Project(name="g", repo_path="/tmp/g",
                          **{axis: ProviderRef(kind="github", repo="acme/app")})
        assert _every_resolution_of(project, axis) == [None, "", None, None], axis


def _bot_token_reader(b: Bench, name: str) -> None:
    import openfactory.adapters.github_app as github_app

    b.monkeypatch.setenv(name, FALLBACK)
    b.monkeypatch.setenv("OPENFACTORY_GH_APP_ID", "1")
    b.monkeypatch.setenv("OPENFACTORY_GH_APP_INSTALLATION_ID", "2")
    b.monkeypatch.setenv("OPENFACTORY_GH_APP_KEY_CONTENT", "-----BEGIN KEY-----")
    b.monkeypatch.setattr(github_app, "mint_installation_token", lambda **_kw: (FALLBACK, 0.0))
    assert github_app.token_from_env() is None, "a refused bot token was replaced by a mint"


def _app_key(b: Bench, name: str) -> None:
    from openfactory.credentials import app_private_key

    pem = b.tmp_path / "fallback.pem"
    pem.write_text(FALLBACK)
    names = ("OPENFACTORY_GH_APP_KEY_CONTENT", "OPENFACTORY_GH_APP_KEY")
    _chain(b, names, name, value=lambda n: FALLBACK if n.endswith("CONTENT") else str(pem))
    assert app_private_key() is None


def _token_pool(b: Bench, name: str) -> None:
    from openfactory.adapters.agent.claude_code import (
        CREDENTIALS,
        POOL,
        ClaudeCodeAdapter,
        _load_agent_token_pool,
    )

    pool = json.dumps([{"id": "a", "token": FALLBACK}])
    _chain(b, CREDENTIALS, name, value=lambda n: pool if n == POOL else FALLBACK)
    assert _load_agent_token_pool() == []
    # …and the run is refused, rather than left to a CLI that reads the next variable itself
    adapter = ClaudeCodeAdapter()
    ran: list[object] = []
    b.monkeypatch.setattr(adapter, "_invoke_once", lambda *a, **kw: ran.append(a))
    result = adapter._invoke(None, None, "say hello", "executor", tools=[], model=None,
                             context=None)
    assert not result.ok and not ran and _says_a_refusal(result.summary, CREDENTIALS, name)


def _container_box(b: Bench, name: str) -> None:
    from openfactory.adapters.sandbox.container import ContainerSandbox

    b.monkeypatch.setenv(name, FALLBACK)
    passing = ContainerSandbox(image="img", extra_env=(BOX_NAME,))._passthrough()
    assert name not in passing and FALLBACK not in passing.values()


def _worktree_box(b: Bench, name: str) -> None:
    from openfactory.adapters.sandbox.worktree import _scrubbed_env

    b.monkeypatch.setenv(name, FALLBACK)
    env = _scrubbed_env(keep=(BOX_NAME,))
    assert name not in env and FALLBACK not in env.values()


def _gate_key(b: Bench, name: str) -> None:
    from openfactory import gate_seal

    b.monkeypatch.setenv(name, FALLBACK)
    with pytest.raises(RuntimeError, match=name):
        gate_seal.seal(gate_seal.MERGE_GATE, "wf-1", "merge")
    expires, nonce = 4_102_444_800, "00"
    mac = hmac.new(FALLBACK.encode(), gate_seal._message(gate_seal.MERGE_GATE, "wf-1", expires,
                                                         nonce, ("merge",)),
                   hashlib.sha256).hexdigest()
    said = gate_seal.refusal(f"v1.{expires}.{nonce}.{mac}", gate_seal.MERGE_GATE, "wf-1", "merge",
                             now=0)
    assert name in said, "a seal made with the refused key's variable was accepted"


def _preview_key(b: Bench, name: str) -> None:
    from openfactory import preview

    b.monkeypatch.setenv(name, FALLBACK)
    b.monkeypatch.setattr(preview, "_PROCESS_SECRET", b"p" * 32)
    for secret in (FALLBACK.encode(), b"p" * 32):
        mac = hmac.new(secret, b"v1|acme|1|4102444800", hashlib.sha256).hexdigest()
        assert not preview.admits(f"v1.1.4102444800.{mac}", project="acme", token="1", now=0)
    with pytest.raises(RuntimeError, match=name):
        preview.mint("acme", "1", expires=4_102_444_800)


def _engine(b: Bench, name: str) -> None:
    from openfactory.runtime.temporal import connection

    cert, key = b.tmp_path / "client.pem", b.tmp_path / "client.key"
    cert.write_text("fictitious-cert")
    key.write_text("fictitious-key")
    b.monkeypatch.setenv("TEMPORAL_TLS_CERT", str(cert))
    names = ("TEMPORAL_API_KEY", "TEMPORAL_TLS_KEY")
    _chain(b, names, name, value=lambda n: FALLBACK if n.endswith("API_KEY") else str(key))
    with pytest.raises(RuntimeError) as refused:
        connection._auth()
    assert _says_a_refusal(str(refused.value), names, name) and FALLBACK not in str(refused.value)


def _harness_line(b: Bench, name: str) -> None:
    from openfactory import doctor
    from openfactory.adapters.agent.claude_code import CREDENTIALS, POOL
    from openfactory.contracts.project import Project

    pool = json.dumps([{"id": "a", "token": FALLBACK}])
    _chain(b, CREDENTIALS, name, value=lambda n: pool if n == POOL else FALLBACK)
    present, said, *remedy = doctor.probes_for(Project(name="acme", repo_path="/tmp/acme")) \
        .agent_credential()
    assert not present and doctor.REFUSED_BY_THE_STORE in said, said
    assert _says_a_refusal(said, CREDENTIALS, name), said
    assert FALLBACK not in said + "".join(remedy)
    assert "put the result in" not in "".join(remedy), "told to set a variable that is set"


def _readiness(b: Bench, name: str) -> None:
    from openfactory.contracts.project import BoxConfig, Project
    from openfactory.onboarding import readiness

    b.monkeypatch.setenv(name, FALLBACK)
    probes = readiness.probes_for(Project(name="acme", repo_path="/tmp/acme",
                                          box=BoxConfig(env=[name])))
    finding, _ = readiness._env_names(probes, "the worker")
    assert not finding.ok and "refuses" in finding.message and name in finding.message
    assert "not set" not in finding.message and FALLBACK not in finding.message


def _board_setup(b: Bench, name: str) -> None:
    import openfactory.adapters.tracker.github_board_setup as setup

    b.monkeypatch.setenv(name, FALLBACK)
    asked: list[object] = []
    b.monkeypatch.setattr(setup, "_gh_graphql", lambda *a, **kw: asked.append(a) or {})
    with pytest.raises(setup.BoardSetupError, match="refused") as refused:
        setup.create_board(owner="acme", title="acme board")
    assert not asked and FALLBACK not in str(refused.value)


def _onboarding(b: Bench, name: str) -> None:
    import shutil

    from openfactory.adapters.agent.claude_code import CREDENTIALS, POOL
    from openfactory.contracts.project import Project
    from openfactory.onboarding import context as ctx
    from openfactory.onboarding import onboard as ob

    pool = json.dumps([{"id": "a", "token": FALLBACK}])
    _chain(b, CREDENTIALS, name, value=lambda n: pool if n == POOL else FALLBACK)
    b.monkeypatch.setattr(shutil, "which", lambda _b: "/usr/bin/claude")
    b.monkeypatch.setattr("openfactory.adapters.agent.build_asker", lambda p: object())
    b.monkeypatch.setattr("openfactory.adapters.sandbox.registry.judging_worktree",
                          lambda p, root=None: object())
    b.monkeypatch.setattr(ctx, "agent_ask", lambda *a, **k: (lambda *_a, **_k: ""))
    ask_fn, mode = ob.semantic_pass_for(Project(name="acme", repo_path="/tmp/acme"),
                                        pathlib.Path("/tmp"))
    assert ask_fn is None and _says_a_refusal(mode, CREDENTIALS, name), mode


def _panel_label(b: Bench, name: str) -> None:
    from openfactory.api.app import _auth_credential

    _chain(b, ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"), name)
    assert _auth_credential() == ""


def _azure(b: Bench, name: str) -> None:
    from openfactory.adapters import azure_devops

    b.monkeypatch.setenv(name, FALLBACK)
    b.monkeypatch.setattr(azure_devops, "az_token", lambda: FALLBACK)
    assert azure_devops.credential_source({"token_env": name}) == ("", None)
    assert azure_devops.token_for({"token_env": name}) is None


def _pull(b: Bench, name: str) -> None:
    from openfactory.adapters.sandbox.pull import PullCredential, pull

    b.monkeypatch.setenv(name, FALLBACK)
    ran: list[object] = []
    pulled, said = pull("registry.acme.example/ci:1", PullCredential(name, "ci-bot"),
                        run=lambda argv, **kw: ran.append(argv))
    assert not pulled and not ran and FALLBACK not in said


def _doctor_store_line(b: Bench, name: str) -> None:
    from openfactory.contracts.project import Project
    from openfactory.doctor import credential_store_line

    b.monkeypatch.setenv(name, FALLBACK)
    ok, said, remedy = credential_store_line(Project(name="acme", repo_path="/tmp/acme"))
    assert not ok, said
    assert FALLBACK not in said + remedy


def _doctor_forge_line(b: Bench, name: str) -> None:
    from openfactory import doctor
    from openfactory.contracts.project import Project, ProviderRef

    _mint_is_fallback(b)
    b.monkeypatch.setenv(name, FALLBACK)
    project = Project(name="acme", repo_path="/tmp/acme",
                      forge=ProviderRef(kind="github", repo="acme/app",
                                        options={"token_env": name}))
    probes = doctor.probes_for(project)
    reachable, detail = probes.forge_reachable()
    assert not reachable and doctor.REFUSED_BY_THE_STORE in detail and name in detail, detail
    finding = doctor._forge(probes)
    assert finding.remedy == doctor.REFUSED_REMEDY and FALLBACK not in finding.message


def _names(*names: str) -> tuple[str, ...]:
    return names


def _closing() -> tuple[str, ...]:
    from openfactory.identity.local import CLOSING_ENVS

    return CLOSING_ENVS


def _oidc_names() -> tuple[str, ...]:
    from openfactory.identity.oidc import CLIENT_SECRET_ENV

    return (CLIENT_SECRET_ENV,)


def _vendor_names() -> tuple[str, ...]:
    from openfactory.adapters.credential.registry import SHIPPED_ENV

    return tuple(sorted(set(SHIPPED_ENV.values())))


def _generic_names() -> tuple[str, ...]:
    from openfactory.credentials import _GENERIC

    return tuple(dict.fromkeys((*_GENERIC["tracker"], *_GENERIC["forge"])))


def _harness_names() -> tuple[str, ...]:
    from openfactory.adapters.agent.claude_code import CREDENTIALS

    return CREDENTIALS


def _box_names() -> tuple[str, ...]:
    from openfactory.adapters.sandbox.container import _AUTH_ENV_VARS

    return (*_AUTH_ENV_VARS, BOX_NAME)


def _gate_names() -> tuple[str, ...]:
    from openfactory.gate_seal import VARIABLE

    return (VARIABLE,)


@dataclass(frozen=True)
class Consumer:
    #: the module it reads the store in, for the completeness guard
    module: str
    #: the names it asks for, read from the code
    names: object
    check: object


#: label → a reader outside the store, the names it asks for, and what "nothing opened, nothing
#: used in its place" means for it.
CONSUMERS = {
    "the panel's door": Consumer("openfactory/identity/local.py", _closing, _door),
    "the identity provider's client secret": Consumer("openfactory/identity/oidc.py",
                                                      _oidc_names, _oidc),
    "a project's own reference": Consumer("openfactory/credentials.py",
                                          lambda: (PROJECT_NAME,), _project_reference),
    "a vendor's default variable": Consumer("openfactory/credentials.py", _vendor_names,
                                            _vendor_default),
    "the deployment's pair": Consumer("openfactory/credentials.py", _generic_names, _generic_pair),
    "the App key": Consumer("openfactory/credentials.py",
                            lambda: ("OPENFACTORY_GH_APP_KEY_CONTENT", "OPENFACTORY_GH_APP_KEY"),
                            _app_key),
    "the bot token, before a mint": Consumer("openfactory/adapters/github_app.py",
                                             lambda: ("OPENFACTORY_BOT_TOKEN",),
                                             _bot_token_reader),
    "the harness's token pool": Consumer("openfactory/adapters/agent/claude_code.py",
                                         _harness_names, _token_pool),
    "the container box": Consumer("openfactory/adapters/sandbox/container.py", _box_names,
                                  _container_box),
    "the worktree box": Consumer("openfactory/adapters/sandbox/worktree.py", _box_names,
                                 _worktree_box),
    "the gate key": Consumer("openfactory/gate_seal.py", _gate_names, _gate_key),
    "the preview key": Consumer("openfactory/preview/__init__.py",
                                lambda: ("OPENFACTORY_PREVIEW_SECRET",), _preview_key),
    "the engine's credential": Consumer("openfactory/runtime/temporal/connection.py",
                                        lambda: ("TEMPORAL_API_KEY", "TEMPORAL_TLS_KEY"), _engine),
    "the doctor's harness line": Consumer("openfactory/doctor.py", _harness_names, _harness_line),
    "the doctor's forge line": Consumer("openfactory/doctor.py", lambda: (PROJECT_NAME,),
                                        _doctor_forge_line),
    "the doctor's credential store line": Consumer("openfactory/doctor.py",
                                                   lambda: ("OPENFACTORY_PANEL_TOKEN",
                                                            "OPENFACTORY_BOT_TOKEN"),
                                                   _doctor_store_line),
    "readiness's box.env line": Consumer("openfactory/onboarding/readiness.py",
                                         lambda: (BOX_NAME,), _readiness),
    "onboarding's harness check": Consumer("openfactory/onboarding/onboard.py", _harness_names,
                                           _onboarding),
    "the board's setup": Consumer("openfactory/adapters/tracker/github_board_setup.py",
                                  lambda: ("GH_TOKEN",), _board_setup),
    "the panel's harness label": Consumer("openfactory/api/app.py",
                                          lambda: ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"),
                                          _panel_label),
    "Azure's own resolution": Consumer("openfactory/adapters/azure_devops.py",
                                       lambda: ("AZURE_DEVOPS_PAT", PROJECT_NAME), _azure),
    "the image's pull credential": Consumer("openfactory/adapters/sandbox/pull.py",
                                            lambda: (PROJECT_NAME,), _pull),
}


def _cases() -> list[tuple[str, str, str]]:
    return [(refusal, consumer, name) for consumer, row in CONSUMERS.items()
            for name in row.names() for refusal in REFUSALS]


@pytest.mark.parametrize(("refusal", "consumer", "name"), _cases())
def test_a_refused_credential_opens_no_door_and_nothing_is_used_in_its_place(
        refusal, consumer, name, bench):
    REFUSALS[refusal](bench, name)
    CONSUMERS[consumer].check(bench, name)


def _importers() -> set[str]:
    """Every module outside the store that imports it — read from the code."""
    found = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("openfactory/adapters/credential_store/"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "openfactory.adapters.credential_store"):
                found.add(rel)
    return found


#: Modules that import the store and are not a consumer above, with the reason.
NOT_A_CONSUMER: dict[str, str] = {}


def test_every_module_that_asks_the_store_is_a_consumer_here():
    """A new reader of the store joins `CONSUMERS` or fails here by name — so the next door is
    held to the rule the day it is written, not the day it opens."""
    importers = _importers()
    assert len(importers) > 10, importers
    declared = {row.module for row in CONSUMERS.values()} | set(NOT_A_CONSUMER)
    assert importers <= declared, (
        f"these read a credential through the store and no case here proves a refusal opens "
        f"nothing there: {sorted(importers - declared)}")
    assert declared - set(NOT_A_CONSUMER) <= importers, sorted(declared - importers)


def test_a_consumer_that_reads_a_name_the_store_answers_is_not_shut_by_this_test(bench):
    """The twin: the same consumers, the same names, a store that answers — and the doors open as
    configured. Without it, a consumer that refused EVERYTHING would pass the product above."""
    from openfactory.identity.local import SHARED_ENV, LocalIdentity

    bench.file(SHARED_ENV, "fictitious-panel-token")
    provider = LocalIdentity()
    assert provider.misconfiguration() == "" and provider.open_to_everyone() is False
    assert provider.identify(credential="fictitious-panel-token") is not None

    from openfactory.credentials import tracker_token

    bench.file("OPENFACTORY_TRACKER_TOKEN", "fictitious-tracker-token")
    assert tracker_token() == "fictitious-tracker-token"
    bench.monkeypatch.setenv("OPENFACTORY_BOT_TOKEN", FALLBACK)
    (bench.directory / "OPENFACTORY_TRACKER_TOKEN").unlink()
    assert tracker_token() == FALLBACK, "an ABSENT name is still the chain's next"


def test_a_refused_closing_variable_admits_nobody_not_even_a_token_the_store_held(bench):
    """Nobody gets in (review of #822): the operator meant the refused credential to be a way in,
    so a provider that admitted the others would be answering a question it cannot check."""
    from openfactory.identity.local import PRODUCT_SHARED_ENV, SHARED_ENV, LocalIdentity

    bench.file(SHARED_ENV, "fictitious-panel-token", 0o664)
    bench.file(PRODUCT_SHARED_ENV, "fictitious-product-token")
    provider = LocalIdentity()
    assert provider.identify(credential="fictitious-product-token") is None
    assert provider.open_to_everyone() is False and SHARED_ENV in provider.misconfiguration()
    assert "fictitious-" not in provider.misconfiguration()
