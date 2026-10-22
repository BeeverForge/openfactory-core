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
import stat
import traceback
from dataclasses import dataclass

import pytest

from openfactory.adapters.credential_store import registry
from openfactory.adapters.credential_store.base import CredentialRefused
from openfactory.adapters.credential_store.file import DIR_VAR, MAX_BYTES, FileStore
from openfactory.adapters.credential_store.registry import STORE_VAR, STORES
from tests.the_tree_read_once import parsed

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
    for child in b.directory.rglob("*"):
        if child.is_symlink():
            continue
        child.chmod(0o700 if child.is_dir() else 0o600)


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


def _read_only_mount(b: Bench) -> None:
    """The directory's mount refuses writes — a cluster's secret volume, a compose `secrets:` bind."""
    import openfactory.adapters.credential_store.file as store_file

    b.monkeypatch.setattr(store_file, "_mount_refuses_writes", lambda fd=None, path="": True)


def _another_users(b: Bench, path: pathlib.Path) -> None:
    """`path` — and, without root, everything this process made — belongs to a user who is
    neither root nor this process's."""
    if os.geteuid() == 0:
        os.chown(path, 54321, -1)  # root's own files are trusted; make it somebody else's
    else:
        owner = os.geteuid()
        b.monkeypatch.setattr(os, "geteuid", lambda: owner + 1)


def _another_users_file(b: Bench, path: pathlib.Path) -> None:
    """`path` belongs to another user, and the credential directory to this process's."""
    _another_users(b, path)
    if os.geteuid() == 0:
        return
    me, real = os.geteuid(), os.stat
    root = os.path.realpath(b.directory)

    def stat_(p, *a, **kw):
        found = real(p, *a, **kw)
        if os.fspath(p) == root:
            fields = list(found)
            fields[stat.ST_UID] = me
            return os.stat_result(fields)
        return found

    b.monkeypatch.setattr(os, "stat", stat_)


def _planted_in_a_shared_directory(b: Bench, name: str) -> None:
    """In a shared directory on a read-only mount — the one layout a shared directory is read in —
    a file whose owner is somebody else."""
    _read_only_mount(b)
    b.directory.chmod(0o1777)
    _another_users_file(b, b.file(name, "fictitious-planted", 0o600))


def _shared_by_its_bits(mode: int):
    def arrange(b: Bench, name: str) -> None:
        """A directory others may write to by its bits alone, sticky or not, on a read-only mount:
        a file in it another user's is no more the deployment's than in a sticky one."""
        _read_only_mount(b)
        b.directory.chmod(mode)
        _another_users_file(b, b.file(name, "fictitious-planted", 0o600))
    return arrange


def _a_shared_directory_of_another_users(b: Bench, name: str) -> None:
    _read_only_mount(b)
    b.directory.chmod(0o777)
    _another_users(b, b.directory)
    b.file(name, "fictitious-held-in-the-file", 0o600)


def _a_link_into_a_subdirectory_others_may_write_to(b: Bench, name: str) -> None:
    """The credential directory is the owner's alone; the directory its link leads into is not."""
    data = b.directory / "data"
    data.mkdir()
    (data / name).write_text("fictitious-held-in-the-file")
    (data / name).chmod(0o600)
    data.chmod(0o777)
    (b.directory / name).symlink_to(f"data/{name}")


def _a_hard_link_in_the_deployments_own_directory(b: Bench, name: str) -> None:
    os.link(_the_deployments_other_secret(b), b.directory / name)


def _the_deployments_other_secret(b: Bench) -> pathlib.Path:
    return b.file("ACME_OTHER_SECRET", "fictitious-other-secret", 0o600)


def _a_link_in_a_shared_writable_directory(b: Bench, name: str) -> None:
    b.directory.chmod(0o1777)
    (b.directory / name).symlink_to(_the_deployments_other_secret(b).name)


def _a_hard_link_in_a_shared_writable_directory(b: Bench, name: str) -> None:
    b.directory.chmod(0o1777)
    os.link(_the_deployments_other_secret(b), b.directory / name)


def _made_by_another_user(b: Bench, link: pathlib.Path) -> None:
    """`link`'s own owner (its `lstat`) is somebody else."""
    real = os.lstat

    def lstat(path, *a, **kw):
        found = real(path, *a, **kw)
        if os.fspath(path) == os.fspath(link):
            fields = list(found)
            fields[stat.ST_UID] = 54321
            return os.stat_result(fields)
        return found

    b.monkeypatch.setattr(os, "lstat", lstat)


def _a_link_another_user_made(b: Bench, name: str) -> None:
    """On a read-only mount, a link under the name whose own owner (its `lstat`) is somebody else:
    what it leads to is the deployment's, and says nothing of who put the link there."""
    _read_only_mount(b)
    entry = b.directory / name
    entry.symlink_to(_the_deployments_other_secret(b).name)
    _made_by_another_user(b, entry)


def _a_link_on_the_way_another_user_made(b: Bench, name: str) -> None:
    """…and further along: the link under the name is this user's, the one it leads to is not."""
    _read_only_mount(b)
    hop = b.directory / "hop"
    hop.symlink_to(_the_deployments_other_secret(b).name)
    (b.directory / name).symlink_to("hop")
    _made_by_another_user(b, hop)


def _a_link_through_a_subdirectory_others_may_write_to(b: Bench, name: str) -> None:
    """The credential directory and the file are the owner's alone; a link on the way is in a
    subdirectory others may write to, where it can be swapped for one to any other file."""
    real = b.directory / "real"
    real.mkdir()
    (real / "ACME_OTHER_SECRET").write_text("fictitious-other-secret")
    (real / "ACME_OTHER_SECRET").chmod(0o600)
    real.chmod(0o700)
    via = b.directory / "via"
    via.mkdir()
    (via / "hop").symlink_to("../real/ACME_OTHER_SECRET")
    via.chmod(0o777)
    (b.directory / name).symlink_to("via/hop")


def _a_link_that_leads_to_itself(b: Bench, name: str) -> None:
    (b.directory / name).symlink_to(name)


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


def _addon_cannot_be_built(b: Bench, name: str) -> None:
    """An add-on whose builder raises, as one does on a deployment that installed it and never
    set it up (review of bd178211): a store that cannot be built is a refusal, by name."""
    def cannot_be_built():
        raise RuntimeError("acme vault: VAULT_ADDR is not set")

    b.monkeypatch.setitem(STORES, "acme", cannot_be_built)
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
    "a link in a shared directory anyone may write to": _a_link_in_a_shared_writable_directory,
    "a hard link in a shared directory anyone may write to":
        _a_hard_link_in_a_shared_writable_directory,
    "a link another user made, on a read-only mount": _a_link_another_user_made,
    "a link on the way another user made, on a read-only mount":
        _a_link_on_the_way_another_user_made,
    "a link through a subdirectory others may write to":
        _a_link_through_a_subdirectory_others_may_write_to,
    "a link that leads to itself": _a_link_that_leads_to_itself,
    "a directory others may write to by its bits (0777), on a read-only mount":
        _shared_by_its_bits(0o777),
    "a directory its group may write to (0770), on a read-only mount": _shared_by_its_bits(0o770),
    "a shared directory of another user's, on a read-only mount":
        _a_shared_directory_of_another_users,
    "a link into a subdirectory others may write to": _a_link_into_a_subdirectory_others_may_write_to,
    "a hard link in the deployment's own directory": _a_hard_link_in_the_deployments_own_directory,
    "a file this user cannot open": _unreadable,
    "an add-on store that refuses": _addon_refuses,
    "an add-on store that fails": _addon_fails,
    "an add-on store that cannot be built": _addon_cannot_be_built,
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
                      "an add-on store that fails", "an add-on store that cannot be built")


def test_every_refusal_the_file_store_can_give_is_a_case(tmp_path):
    """CASES READ FROM THE CODE: every `raise CredentialRefused` in `file.py` is fired by one of
    `REFUSALS` (traced to its line), or is exempt above with its reason. A refusal added to the
    store without a case here fails by its own line."""
    source = pathlib.Path(registry.__file__).with_name("file.py")
    tree = parsed(source)
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
    with pytest.raises(gate_seal.KeyRefused, match=name):
        gate_seal.seal(gate_seal.MERGE_GATE, "wf-1", "merge")
    assert not issubclass(gate_seal.KeyRefused, RuntimeError), (
        "a refused key would read as 'the job is not at the gate' to every caller of the engine")
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


def _the_minter_is_fallback(b: Bench) -> None:
    """The deployment's App minter, the provider a construction point hands an adapter when the
    project holds no token, answers a fallback — what a refused reference would be replaced by."""
    import openfactory.factory as factory

    b.monkeypatch.setattr(factory, "_bot_token_provider", lambda: (lambda: FALLBACK))


def _built_with_nothing(built) -> bool:
    """Whether an adapter was built with no token and no provider, and — for one that runs `gh`
    — would not run it on the machine's own login either: its `_env()` refuses by name (the
    ambient `GH_TOKEN` the consumers plant is a fallback like any other)."""
    from openfactory.adapters.github_cli import LoginRefused

    if getattr(built, "_static_token", None) == FALLBACK \
            or getattr(built, "_token_provider", None) is not None:
        return False
    env_of = getattr(built, "_env", None)
    if callable(env_of):
        try:
            env = env_of()
        except LoginRefused:
            return True
        return FALLBACK not in (env.get("GH_TOKEN"), env.get("GITHUB_TOKEN"))
    return getattr(built, "token", None) != FALLBACK


def _ambient_login(b: Bench) -> None:
    """A login the machine has of its own — what `gh` runs on when it is handed no token."""
    b.monkeypatch.setenv("GH_TOKEN", FALLBACK)
    b.monkeypatch.setenv("GITHUB_TOKEN", FALLBACK)


def _gh_trapped(b: Bench) -> list[object]:
    """Every subprocess started from here on, recorded and never run — the package's `gh` calls
    all go through the `subprocess` module (`gh_starts` reads them)."""
    import subprocess

    started: list[object] = []
    for start in ("run", "Popen"):
        b.monkeypatch.setattr(subprocess, start,
                              lambda argv, *a, **kw: started.append((argv, kw.get("env"))))
    return started


def _no_gh_started(b: Bench, forge, tracker) -> None:
    """EVERY SUBPROCESS THE ADAPTERS START (review of ef084ebd): a `gh` call is refused before it
    runs, by the forge as a failed call and by the tracker as a `LoginRefused`."""
    from openfactory.adapters.github_cli import LoginRefused

    started = _gh_trapped(b)
    said = forge._gh(["api", "repos/acme/app"])
    assert said.returncode != 0 and "refused" in (said.stderr or ""), said
    with pytest.raises(LoginRefused):
        tracker._gh(["api", "repos/acme/app"])
    with pytest.raises(LoginRefused):
        tracker.update_body("#1", "a fictitious body")
    assert not started, started


def _worker_builds(b: Bench, name: str) -> None:
    """THE WORKER'S CONSTRUCTION POINTS (review of #822): every activity builds its tracker and
    its forge through these two, and they handed the App minter to a project whose own reference
    was refused."""
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.credentials import _GENERIC
    from openfactory.runtime.temporal import activities

    _mint_is_fallback(b)
    _the_minter_is_fallback(b)
    _ambient_login(b)
    b.monkeypatch.setenv(name, FALLBACK)
    for each in (*_GENERIC["tracker"], *_GENERIC["forge"]):
        b.monkeypatch.setenv(each, FALLBACK)
    named = {"token_env": name}
    project = Project(name="acme", repo_path="/tmp/acme",
                      tracker=ProviderRef(kind="github", repo="acme/app", options=named),
                      forge=ProviderRef(kind="github", repo="acme/app", options=named))
    tracker, forge = activities._tracker_for(project), activities._forge_for(project)
    assert _built_with_nothing(tracker), "the tracker took the minter, or the machine's login"
    assert _built_with_nothing(forge), "the forge took the minter, or the machine's login"
    _no_gh_started(b, forge, tracker)


def _github_board(b: Bench, name: str) -> None:
    """The GitHub board a tracker reads its columns from refuses as the tracker does."""
    from openfactory.adapters.board import build_board
    from openfactory.adapters.github_cli import LoginRefused
    from openfactory.contracts.project import Project, ProviderRef

    _ambient_login(b)
    b.monkeypatch.setenv(name, FALLBACK)
    project = Project(name="acme", repo_path="/tmp/acme",
                      tracker=ProviderRef(kind="github", repo="acme/app",
                                          options={"token_env": name, "board_owner": "acme",
                                                   "board_number": "7"}))
    board = build_board(project, token=None)
    with pytest.raises(LoginRefused):
        board.token  # noqa: B018 — every `gh` call of the board reads it first
    # …and the two that start `gh`: a read answers "unreadable", and the link is not typed on the
    # machine's own login (review of 1b5ec71d)
    import openfactory.adapters.tracker.github_project as github_project

    b.monkeypatch.setattr(github_project, "_OWNER_KIND", {})
    started = _gh_trapped(b)
    assert board.columns() is None
    assert board.url() == "https://github.com/users/acme/projects/7"
    assert not started and not github_project._OWNER_KIND, started


def _ci_observer(b: Bench, name: str) -> None:
    """The CI observer, built as the production approval and the promotion runner build it, with
    the forge's credential (review of 1b5ec71d): after a refusal it starts no `gh` on the
    machine's own login."""
    from openfactory.adapters.environment.registry import build_observer
    from openfactory.adapters.github_cli import LoginRefused
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.credentials import _GENERIC, deployment_forge_token, forge_token_for

    _mint_is_fallback(b)
    _ambient_login(b)
    b.monkeypatch.setenv(name, FALLBACK)
    for each in _GENERIC["forge"]:
        b.monkeypatch.setenv(each, FALLBACK)
    project = Project(name="acme", repo_path="/tmp/acme",
                      forge=ProviderRef(kind="github", repo="acme/app",
                                        options={"token_env": name}))
    observer = build_observer(project,
                              token=forge_token_for(project) or deployment_forge_token(project))
    started = _gh_trapped(b)
    with pytest.raises(LoginRefused):
        observer.ci_status(repo="", ref="main")
    assert not started, started


def _board_creation(b: Bench, name: str) -> None:
    """`openfactory project init`'s board, created with what the project resolves (review of
    1b5ec71d): after a refusal it is not created on `GH_TOKEN` or the machine's own login."""
    from openfactory.adapters.board_setup.base import BoardSetupError
    from openfactory.adapters.board_setup.registry import board_creator
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.credentials import _GENERIC, deployment_tracker_token, tracker_token_for

    _mint_is_fallback(b)
    _ambient_login(b)
    b.monkeypatch.setenv(name, FALLBACK)
    for each in _GENERIC["tracker"]:
        b.monkeypatch.setenv(each, FALLBACK)
    project = Project(name="acme", repo_path="/tmp/acme",
                      tracker=ProviderRef(kind="github", repo="acme/app",
                                          options={"token_env": name}))
    creator = board_creator("github")
    assert creator is not None
    started = _gh_trapped(b)
    with pytest.raises(BoardSetupError, match="refused") as refused:
        creator.create(project=project, owner="acme", title="acme board",
                       token=tracker_token_for(project) or deployment_tracker_token(project))
    assert not started and FALLBACK not in str(refused.value), started


def _a_refused_app_key(b: Bench, name: str) -> None:
    """With the App configured and its key refused, the forge has no token: it must not run `gh`
    on the machine's own login either (review of ef084ebd)."""
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.runtime.temporal import activities

    _ambient_login(b)
    b.monkeypatch.setenv(name, "-----BEGIN FICTITIOUS KEY-----")
    b.monkeypatch.setenv("OPENFACTORY_GH_APP_ID", "1")
    b.monkeypatch.setenv("OPENFACTORY_GH_APP_INSTALLATION_ID", "2")
    project = Project(name="acme", repo_path="/tmp/acme",
                      forge=ProviderRef(kind="github", repo="acme/app"))
    assert _built_with_nothing(activities._forge_for(project))


def _jira_row(b: Bench, name: str) -> None:
    """Jira's row falls back to `JIRA_API_TOKEN` by itself, for every caller of `build_tracker`."""
    from openfactory.adapters.tracker.registry import build_tracker
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.runtime.temporal import activities

    b.monkeypatch.setenv(name, FALLBACK)
    b.monkeypatch.setenv("JIRA_API_TOKEN", FALLBACK)
    project = Project(name="acme", repo_path="/tmp/acme",
                      tracker=ProviderRef(kind="jira", repo="ACME",
                                          options={"token_env": name,
                                                   "site": "https://acme.example"}))
    assert build_tracker(project).token != FALLBACK
    assert activities._tracker_for(project).token != FALLBACK


def _impediment_board(b: Bench, name: str) -> None:
    """The factory's own board, where impediments are filed, resolves its tracker's credential like
    any tracker's."""
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.credentials import _GENERIC
    from openfactory.ops import impediment

    _mint_is_fallback(b)
    _the_minter_is_fallback(b)
    b.monkeypatch.setenv(name, FALLBACK)
    for each in _GENERIC["tracker"]:
        b.monkeypatch.setenv(each, FALLBACK)  # the deployment's pair, which it used to take
    board = ProviderRef(kind="github", repo="acme/factory", options={"token_env": name})
    b.monkeypatch.setattr(impediment, "_board",
                          lambda project: __import__("types").SimpleNamespace(tracker=board))
    built = impediment._tracker_for(Project(name="acme", repo_path="/tmp/acme"), None)
    assert _built_with_nothing(built)


def _product_board(b: Bench, name: str) -> None:
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.credentials import tracker_token_for
    from openfactory.product import board

    _mint_is_fallback(b)
    _the_minter_is_fallback(b)
    b.monkeypatch.setenv(name, FALLBACK)
    project = Project(name="acme", repo_path="/tmp/acme",
                      tracker=ProviderRef(kind="github", repo="acme/app",
                                          options={"token_env": name}))
    assert _built_with_nothing(board._tracker(project, tracker_token_for(project)))


class _AtTheGates:
    """An engine whose job waits at every gate, recording what it is signalled."""

    def __init__(self) -> None:
        self.signals: list = []

    def get_workflow_handle(self, _wf):
        return self

    async def query(self, q, *_a):
        return {"awaiting_merge": {"pr": 7, "adjusts_left": 2}, "awaiting_approval": True,
                "release_wait": {"hears": True, "adjusts_left": 2}}.get(getattr(q, "__name__", q))

    async def signal(self, *a, **_k):
        self.signals.append(a)


def _merge_gate(b: Bench, name: str) -> None:
    """The panel's merge gate: a refused gate key is said as itself, never "not waiting"."""
    import asyncio

    from openfactory.actions import catalog

    b.monkeypatch.setenv(name, FALLBACK)
    engine = _AtTheGates()

    async def connected():
        return engine, None

    b.monkeypatch.setattr(catalog, "_project", lambda p: (type("P", (), {"name": "acme"})(),
                                                          None))
    b.monkeypatch.setattr(catalog, "_connected", connected)
    _gate, bad = asyncio.run(catalog._answer_gate(project="acme", issue="12", by="ana",
                                                  answer="merge"))
    said = str(getattr(bad, "message", bad))
    assert not engine.signals and "not waiting on a merge" not in said, said
    assert "gate key" in said and FALLBACK not in said


def _another_pass(b: Bench, name: str) -> None:
    """Both "another pass" paths: the reason is the key's own, not `NOT_WAITING`."""
    import openfactory.product.release as release
    from openfactory.product import adjust

    b.monkeypatch.setenv(name, FALLBACK)
    engine = _AtTheGates()

    async def client():
        return engine

    b.monkeypatch.setattr(release, "_client", client)
    project = type("P", (), {"name": "acme"})()
    assert adjust._not_yet(project, "12", instruction="again", by="ana") == adjust.KEY_REFUSED
    assert adjust.answer_gate(project, "12", answer="adjust", instruction="x",
                              by="ana") == adjust.KEY_REFUSED
    assert not engine.signals


def _certify_panel(b: Bench, name: str) -> None:
    """Certify's exposure control: a refused panel token closes the panel to everybody, so it is
    never reported as a panel that answers anybody, nor passed on a value nobody can present."""
    from types import SimpleNamespace

    from openfactory.certify import controls

    for each in controls._PANEL_TOKENS:
        b.monkeypatch.delenv(each, raising=False)
    result, detail, _ = controls._panel(SimpleNamespace(env=dict(os.environ)), None)
    assert result == controls.UNKNOWN, (result, detail)


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
    "the worker's tracker and forge": Consumer("openfactory/runtime/temporal/activities.py",
                                               lambda: (PROJECT_NAME,), _worker_builds),
    "Jira's row": Consumer("openfactory/adapters/tracker/registry.py", lambda: (PROJECT_NAME,),
                           _jira_row),
    "the GitHub board": Consumer("openfactory/adapters/board/factory.py", lambda: (PROJECT_NAME,),
                                 _github_board),
    "the CI observer": Consumer("openfactory/adapters/environment/registry.py",
                                lambda: (PROJECT_NAME,), _ci_observer),
    "the board's creation at init": Consumer("openfactory/adapters/tracker/github_board_setup.py",
                                             lambda: (PROJECT_NAME,), _board_creation),
    "the GitHub forge after a refused App key": Consumer(
        "openfactory/adapters/forge/registry.py", lambda: ("OPENFACTORY_GH_APP_KEY_CONTENT",),
        _a_refused_app_key),
    "the factory board's tracker": Consumer("openfactory/ops/impediment.py",
                                            lambda: (PROJECT_NAME,), _impediment_board),
    "the product board's tracker": Consumer("openfactory/product/board.py",
                                            lambda: (PROJECT_NAME,), _product_board),
    "the merge gate's answer": Consumer("openfactory/actions/catalog.py", _gate_names,
                                        _merge_gate),
    "another pass, at either gate": Consumer("openfactory/product/adjust.py", _gate_names,
                                             _another_pass),
    "certify's panel control": Consumer("openfactory/certify/controls.py",
                                        lambda: __import__("openfactory.certify.controls",
                                                           fromlist=["x"])._PANEL_TOKENS,
                                        _certify_panel),
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
        for node in ast.walk(parsed(path)):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "openfactory.adapters.credential_store"):
                found.add(rel)
    return found


# ── every construction point: it falls back to the deployment's own only after asking ─────────

#: What a construction point falls back to when a project holds no credential: the deployment's
#: App minter and mint, its vendor default, its pair. Each is the LAST step of a resolution, and a
#: refusal ends the resolution (review of #822), so a call to one asks the refusal first.
DEPLOYMENT_WIDE = frozenset({"_bot_token_provider", "github_app_token_from_env", "vendor_default",
                             "tracker_token", "forge_token"})
#: …and the questions that ask it: the project's axis, or the deployment's own pair.
ASKS_THE_REFUSAL = frozenset({"axis_refusal", "pair_refusal"})
#: What builds an adapter or the provider it is handed.
BUILDS = frozenset({"build_tracker", "build_forge", "build_board", "bot_token_provider_for",
                    "deployment_tracker_provider", "deployment_forge_provider",
                    "deployment_tracker_token", "deployment_forge_token"})
#: The resolution itself, where those steps are composed — `credentials` and the vendors' rows.
THE_RESOLUTION = frozenset({"openfactory/credentials.py",
                            "openfactory/adapters/credential/registry.py"})


def _calls(tree: ast.AST, names: frozenset) -> list[ast.Call]:
    """The calls in `tree` of one of `names` — a bare name, or an attribute of an imported module
    (`credentials.forge_token()`), never a method of something else (`probes.forge_token()`)."""
    imported = {alias.asname or alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in names:
            out.append(node)
        elif isinstance(func, ast.Attribute) and func.attr in names \
                and isinstance(func.value, ast.Name) and func.value.id in imported:
            out.append(node)
    return out


def construction_points(root: pathlib.Path = PACKAGE) -> dict[str, list[tuple[int, str]]]:
    """`{module: [(line, what)]}` of every call that builds an adapter or falls back to the
    deployment's own, outside the resolution — read from the code."""
    found: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root.parent).as_posix()
        if rel in THE_RESOLUTION:
            continue
        tree = parsed(path)
        for call in _calls(tree, BUILDS | DEPLOYMENT_WIDE):
            found.setdefault(rel, []).append((call.lineno, ast.unparse(call.func)))
    return found


def falls_back_without_asking(root: pathlib.Path = PACKAGE) -> list[tuple[str, int, str]]:
    """`(module, line, what)` for every fall-back to the deployment's own whose function does not
    ask the refusal first — outside the resolution and the deployment-wide readers themselves."""
    out = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root.parent).as_posix()
        if rel in THE_RESOLUTION:
            continue
        tree = parsed(path)
        parent = {id(c): n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        for call in _calls(tree, DEPLOYMENT_WIDE):
            fn = parent.get(id(call))
            while fn is not None and not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = parent.get(id(fn))
            if fn is not None and fn.name in DEPLOYMENT_WIDE:
                continue  # one deployment-wide reader composing another
            if fn is None or not any(isinstance(n, ast.Call) and ASKS_THE_REFUSAL & {
                    getattr(n.func, "id", ""), getattr(n.func, "attr", "")} for n in ast.walk(fn)):
                out.append((rel, call.lineno, ast.unparse(call.func)))
    return out


def test_every_construction_point_asks_the_refusal_before_it_falls_back():
    """THE RULE AT EVERY CONSTRUCTION POINT (review of #822): the worker built its tracker and
    forge with the App minter, and Jira's row with `JIRA_API_TOKEN`, after the project's own
    reference was refused, because `credentials` was the only place a refusal was final. Every
    call that falls back to the deployment's own now asks `axis_refusal` (or, with no project,
    `pair_refusal`) in the same function — the minter through `factory.bot_token_provider_for`."""
    offenders = falls_back_without_asking()
    assert not offenders, (
        "these fall back to the deployment's own credential without asking whether the store "
        "refused the project's — a refusal is answered by the next credential there:\n  "
        + "\n  ".join(f"{path}:{line}: {what}()" for path, line, what in offenders))


def test_the_construction_rule_sees_the_worker_and_every_builder(tmp_path):
    """Its verifiers: the points the review named are among those it reads, and a fall-back planted
    without the question is seen while one that asks is not."""
    points = construction_points()
    for module in ("openfactory/runtime/temporal/activities.py",
                   "openfactory/runtime/temporal/view.py", "openfactory/product/board.py",
                   "openfactory/product/module.py", "openfactory/ops/impediment.py",
                   "openfactory/factory.py", "openfactory/adapters/tracker/registry.py"):
        assert module in points, module
    assert len(points) > 20, sorted(points)

    pkg = tmp_path / "openfactory"
    pkg.mkdir()
    (pkg / "planted.py").write_text(
        "from openfactory.factory import _bot_token_provider\n"
        "from openfactory import credentials\n"
        "def unasked(project):\n"
        "    return _bot_token_provider()\n"
        "def asked(project):\n"
        "    return None if credentials.axis_refusal(project, 'forge') else _bot_token_provider()\n"
        "def a_probe(p):\n"
        "    return p.forge_token()\n"
        "def the_pair():\n"
        "    return credentials.forge_token()\n")
    assert [(line, what) for _, line, what in falls_back_without_asking(pkg)] == [
        (4, "_bot_token_provider"), (10, "credentials.forge_token")]


#: Modules that read a credential through the store, or build an adapter's credential, and are no
#: consumer above — each with the reason a refusal is final there anyway.
NOT_A_CONSUMER: dict[str, str] = {
    module: "held by `test_every_construction_point_asks_the_refusal_before_it_falls_back`: its "
            "fall-back to the deployment's own asks `axis_refusal` first"
    for module in ("openfactory/runtime/temporal/view.py", "openfactory/product/module.py",
                   "openfactory/runtime/boxed_job.py", "openfactory/factory.py")
} | {
    "openfactory/certify/pack.py": "it REDACTS what the store holds, and hiding a value opens no "
                                   "door: a refusal there is one value fewer to hide, never a "
                                   "credential used",
    "openfactory/product/model.py": "it REDACTS what the store holds from the product's facts and "
                                    "briefings, as the certify pack does: a refusal there is one "
                                    "value fewer to hide, never a credential used",
    "openfactory/adapters/github_cli.py": "it raises `LoginRefused` for every GitHub adapter, and "
                                          "asks the App key's refusal again when a mint answers "
                                          "nothing: the worker's tracker and forge, the GitHub "
                                          "board and the CI observer above hold it",
    "openfactory/runtime/temporal/view.py": "it seals the answers the merge gate, the approval "
                                            "and another pass deliver, and raises the key's "
                                            "refusal to them: their consumers above hold it",
    "openfactory/adapters/agent/registry.py": "it asks the store which of a harness's names it "
                                              "refuses, for the doctor's agent line and "
                                              "onboarding — consumers above — and opens nothing",
    "openfactory/runtime/temporal/activities.py": "it verifies a seal through "
                                                  "`gate_seal.refusal`, which says a refused key "
                                                  "as the reason an answer is refused",
    "openfactory/preflight.py": "it reads which store the deployment declares, a selector, and "
                                "names that store in a missing credential's remedy (#904): it "
                                "is made to run before the stack, builds, lists and asks no store, and "
                                "reads no credential through one",
}


def test_every_module_that_asks_the_store_is_a_consumer_here():
    """A new reader of the store — or a new place that hands an adapter the deployment's own when
    the project holds nothing — joins `CONSUMERS` or fails here by name, so the next door is held
    to the rule the day it is written, not the day it opens."""
    importers = _importers()
    assert len(importers) > 10, importers
    falling_back = {path.relative_to(ROOT).as_posix() for path in sorted(PACKAGE.rglob("*.py"))
                    if _calls(parsed(path),
                              DEPLOYMENT_WIDE | {"bot_token_provider_for"})} - THE_RESOLUTION
    # …AND EVERYTHING THAT SEALS OR VERIFIES WITH THE GATE KEY, which reads the store through
    # `gate_seal` without importing it — how the gate's callers escaped this guard (#822)
    sealing = {path.relative_to(ROOT).as_posix() for path in sorted(PACKAGE.rglob("*.py"))
               if "gate_seal" in {alias.name for node in ast.walk(ast.parse(
                   path.read_text(encoding="utf-8"))) if isinstance(node, ast.ImportFrom)
                   for alias in node.names} | {
                   node.module for node in ast.walk(parsed(path))
                   if isinstance(node, ast.ImportFrom) and node.module == "openfactory.gate_seal"}}
    # …and everything that ASKS the refusal itself, the GitHub rows deciding whether an adapter may
    # fall back to the machine's own login among them
    deciding = {path.relative_to(ROOT).as_posix() for path in sorted(PACKAGE.rglob("*.py"))
                if _calls(parsed(path),
                          ASKS_THE_REFUSAL | {"github_refusal", "app_key_refusal"})
                } - THE_RESOLUTION
    asking = importers | falling_back | sealing | deciding
    declared = {row.module for row in CONSUMERS.values()} | set(NOT_A_CONSUMER)
    assert asking <= declared, (
        f"these read a credential through the store, or fall back to the deployment's own, and no "
        f"case here proves a refusal opens nothing there: {sorted(asking - declared)}")
    assert declared <= asking, sorted(declared - asking)


# ── every `gh` the package starts: a case above reaches it after a refusal ────────────────────

#: Every `gh` the package starts, read from the code by `gh_starts`, → the consumer above whose
#: case reaches it from adapters built after a refusal, with a login on the machine to fall back
#: to, and sees it start nothing (review of 1b5ec71d: the CI observer and board creation did).
GH_STARTS = {
    ("openfactory/adapters/forge/github.py", "GitHubForge._gh"): "the worker's tracker and forge",
    ("openfactory/adapters/tracker/github.py", "GitHubIssuesTracker._gh"):
        "the worker's tracker and forge",
    ("openfactory/adapters/tracker/github.py", "GitHubIssuesTracker.update_body"):
        "the worker's tracker and forge",
    ("openfactory/adapters/tracker/github_project.py", "_run_gh"): "the GitHub board",
    ("openfactory/adapters/tracker/github_project.py", "_owner_kind"): "the GitHub board",
    ("openfactory/adapters/environment/github_actions.py", "GitHubActionsObserver._api"):
        "the CI observer",
    ("openfactory/adapters/tracker/github_board_setup.py", "_gh_graphql"):
        "the board's creation at init",
}
#: …and the one no stored credential reaches, with the reason.
GH_WITH_NO_STORED_CREDENTIAL = {
    ("openfactory/adapters/forge/github.py", "discover_token"):
        "`openfactory init` asks whether the PERSON at the terminal is logged in to `gh`, to offer "
        "their own login while it writes the configuration: it resolves no stored credential, so "
        "there is no refusal for it to answer",
}

#: The `subprocess` calls that start a program.
_STARTS = frozenset({"run", "Popen", "call", "check_call", "check_output"})


def gh_starts(root: pathlib.Path = PACKAGE) -> set[tuple[str, str]]:
    """`(module, function)` of every `gh` the package starts — a `subprocess` call whose argv is a
    list beginning with `"gh"`, written in the call or bound to a name in the same function —
    read from the code."""
    found: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root.parent).as_posix()
        tree = parsed(path)
        parent = {id(c): n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call) and call.args and (
                    getattr(call.func, "attr", "") in _STARTS
                    or getattr(call.func, "id", "") in _STARTS)):
                continue
            scope, here = [], parent.get(id(call))
            while here is not None:
                if isinstance(here, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    scope.insert(0, here)
                here = parent.get(id(here))
            argv = call.args[0]
            function = next((s for s in reversed(scope) if not isinstance(s, ast.ClassDef)), None)
            if isinstance(argv, ast.Name) and function is not None:
                argv = next((n.value for n in ast.walk(function) if isinstance(n, ast.Assign)
                             and any(isinstance(t, ast.Name) and t.id == argv.id
                                     for t in n.targets)), argv)
            if isinstance(argv, (ast.List, ast.Tuple)) and argv.elts \
                    and isinstance(argv.elts[0], ast.Constant) and argv.elts[0].value == "gh":
                found.add((rel, ".".join(s.name for s in scope) or "<module>"))
    return found


def test_every_gh_the_package_starts_is_reached_by_a_case_after_a_refusal():
    """A NEW `gh` CALL JOINS A CASE (review of 1b5ec71d): the CI observer and board creation still
    ran `gh` on the machine's own login after a refusal because no case reached them. Each `gh`
    the package starts is now named, with the consumer whose case proves it starts nothing."""
    read = gh_starts()
    declared = set(GH_STARTS) | set(GH_WITH_NO_STORED_CREDENTIAL)
    assert read <= declared, (
        f"these start `gh`, and no case here proves they start nothing after a refusal — add the "
        f"call to a consumer's case and name it in GH_STARTS: {sorted(read - declared)}")
    assert declared <= read, sorted(declared - read)
    assert set(GH_STARTS.values()) <= set(CONSUMERS), sorted(set(GH_STARTS.values()) - set(CONSUMERS))


def test_the_gh_reading_sees_a_call_written_or_bound_and_nothing_else(tmp_path):
    pkg = tmp_path / "openfactory"
    pkg.mkdir()
    (pkg / "planted.py").write_text(
        "import subprocess\n"
        "def written():\n"
        "    return subprocess.run(['gh', 'api', 'user'])\n"
        "class Adapter:\n"
        "    def bound(self):\n"
        "        cmd = ['gh', 'api', 'graphql']\n"
        "        return subprocess.run(cmd, env={})\n"
        "def another_program():\n"
        "    return subprocess.run(['git', 'status'])\n"
        "def answered_unrun():\n"
        "    return subprocess.CompletedProcess(['gh'], 2, '', 'refused')\n")
    assert gh_starts(pkg) == {("openfactory/planted.py", "written"),
                              ("openfactory/planted.py", "Adapter.bound")}


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
