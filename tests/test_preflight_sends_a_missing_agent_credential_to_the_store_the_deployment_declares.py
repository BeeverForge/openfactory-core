"""A missing agent credential is sent to the credential store the deployment declares (#904).

A deployment that declares `OPENFACTORY_CREDENTIAL_STORE` keeps its credentials in that store: the
worker asks it first and the environment second, and a `file` store reads the file
`CLAUDE_CODE_OAUTH_TOKEN` in `OPENFACTORY_CREDENTIAL_DIR`, where a refusal is final (#822). The
stack preflight runs in the CLI container before the stack exists (`install.sh`, `in_the_cli
preflight`) and cannot see that directory. With no credential in `.env.compose`, it still told the
person to put the token "— in .env.compose": the harness's repair with that location appended on
every miss (`preflight._probe_agent_credential`, measured on cf7ec0f5). #822's own reference says
the preflight "runs before the stack and its store exist, reads `.env.compose` alone"; the remedy
did not say what that means for the person.

THE REMEDY UNDER A DECLARED STORE says three things: the credential is expected in that store; this
check cannot read it before the stack runs; `openfactory doctor` checks it once the stack is up. It
says no `.env.compose`. `env`, in any case, padded or empty, IS the environment and not a declared
store (Q1): its remedy stays the `.env.compose` one, and those cases are the control.

THE INSTALLER'S CASE, HERE (#560): a working directory holding `.env.compose`, and an environment
holding none of it. The real probe is driven, `preflight.check(preflight.probes_for_this_machine())`,
and the `agent_credential` finding's remedy is read.
"""

from __future__ import annotations

import pytest

from openfactory import preflight
from openfactory.adapters.agent import claude_code
from openfactory.adapters.agent.claude_code import CREDENTIALS, POOL
from openfactory.adapters.credential_store import registry
from openfactory.adapters.credential_store.file import DIR_VAR
from openfactory.adapters.credential_store.registry import STORE_VAR

#: The single-token name a `file` store reads its file by: the harness's own, never retyped here.
TOKEN = CREDENTIALS[1]
DOCTOR = "openfactory doctor"


@pytest.fixture
def installation(tmp_path, monkeypatch):
    """The installer's run: `/out` with its `.env.compose`, and a bare environment.

    conftest strips `OPENFACTORY_*` already; the store's two settings are deleted here anyway, so
    the test says what it depends on."""
    for name in (*CREDENTIALS, STORE_VAR, DIR_VAR, "OPENFACTORY_HARNESS_EXECUTOR",
                 *(variable for _w, variable, _d in preflight.PUBLISHED_PORTS)):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)

    def write(**rows: str) -> None:
        (tmp_path / ".env.compose").write_text(
            "# written by openfactory init\n" + "".join(f"{k}={v}\n" for k, v in rows.items()))
    return write


def _credential_line() -> preflight.Finding:
    report = preflight.check(preflight.probes_for_this_machine())
    [line] = [f for f in report.findings if f.check == "agent_credential"]
    return line


def _assert_sent_to_the_store(remedy: str, kind: str) -> None:
    """The three parts of the store's remedy, and no `.env.compose`."""
    assert ".env.compose" not in remedy, remedy
    assert f"`{kind}`" in remedy, f"the declared store is not named: {remedy}"
    assert STORE_VAR in remedy, f"the setting that declared it is not named: {remedy}"
    assert "before the stack" in remedy, f"it does not say it cannot be checked yet: {remedy}"
    assert DOCTOR in remedy, f"the check once the stack is up is not named: {remedy}"


def test_a_declared_file_store_is_where_the_remedy_sends_the_credential(installation):
    installation(**{STORE_VAR: registry.FILE})

    line = _credential_line()

    assert not line.ok, line
    _assert_sent_to_the_store(line.remedy, registry.FILE)
    assert TOKEN in line.remedy and DIR_VAR in line.remedy, (
        f"the file store's remedy does not say which file goes where: {line.remedy}")
    assert claude_code._REPAIR["none"] in line.remedy, "how to get the token stays"


def test_a_store_kind_this_image_cannot_name_is_still_named_and_left_to_the_doctor(
        installation, monkeypatch):
    """The CLI image may lack the add-on the worker has, and an unknown kind is final in the
    worker (#822): the preflight names the kind and defers to doctor, and never builds a store."""
    def no_store_is_built(kind: str):
        raise AssertionError(f"the preflight built the {kind!r} credential store")

    monkeypatch.setattr(registry, "build_store", no_store_is_built)
    installation(**{STORE_VAR: "vault"})

    line = _credential_line()

    assert not line.ok, line
    _assert_sent_to_the_store(line.remedy, "vault")
    assert DIR_VAR not in line.remedy, f"the file store's directory is not vault's: {line.remedy}"


def test_a_broken_pool_under_a_declared_store_is_not_sent_to_env_compose(installation):
    """The harness's pool repair stays (#584); the location is the store's sentence (Q3)."""
    installation(**{STORE_VAR: registry.FILE, POOL: "[{oops"})

    line = _credential_line()

    assert not line.ok, line
    assert line.remedy.startswith(f"fix {POOL}:"), line.remedy
    _assert_sent_to_the_store(line.remedy, registry.FILE)


@pytest.mark.parametrize("declared", [registry.ENV, registry.ENV.upper(), f" {registry.ENV} ", ""])
def test_a_declared_env_store_is_the_environment_and_keeps_the_env_compose_remedy(
        installation, declared):
    """THE CONTROL (Q1): `env` is the environment, which this check has just read. Green before
    #904 by design; it pins what must not change."""
    installation(**{STORE_VAR: declared})

    line = _credential_line()

    assert not line.ok, line
    assert f"{claude_code._REPAIR['none']} — in .env.compose" in line.remedy, line.remedy
    assert DOCTOR not in line.remedy, line.remedy


def test_a_store_declared_in_the_environment_and_not_the_file_is_still_seen(
        installation, monkeypatch):
    """The environment wins over the file, as it does for compose (#560)."""
    installation()
    monkeypatch.setenv(STORE_VAR, registry.FILE)

    line = _credential_line()

    assert not line.ok, line
    _assert_sent_to_the_store(line.remedy, registry.FILE)
