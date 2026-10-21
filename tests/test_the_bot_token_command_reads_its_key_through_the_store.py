"""`openfactory bot-token` reads the App key through the credential store, and has no flag for it.

THE DEFECT (#905). `--key-path` was bound to `envvar="OPENFACTORY_GH_APP_KEY"`, and the command
minted with `app_private_key()`, which never looked at the flag. So `--key-path <a PEM>` was
accepted and ignored, and typer read a credential's locator from the environment beside the
credential store (#742), where a file store declared by the deployment never reached it.

THE RULE, FOR THE WHOLE CLI: no option of any command takes its default from the environment
itself. The composition root reads a setting (#64), and a credential comes through the store
(#742); typer resolving an `envvar=` before any of our code runs is a reader neither can reach.
The commands and their options are read from the CLI as it is built, so a command added tomorrow
is held to the rule the day it is written.
"""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from openfactory.adapters.credential_store.file import DIR_VAR
from openfactory.adapters.credential_store.registry import STORE_VAR
from openfactory.cli import app

#: Fictitious PEMs, recognisable in what the minter is handed.
STORED_PEM = "-----BEGIN RSA PRIVATE KEY-----\nfictitious-stored-5b1e\n-----END RSA PRIVATE KEY-----"
FLAGGED_PEM = "-----BEGIN RSA PRIVATE KEY-----\nfictitious-flag-0c7d\n-----END RSA PRIVATE KEY-----"


@pytest.fixture(autouse=True)
def _a_deployment_with_an_app(monkeypatch):
    for name in ("OPENFACTORY_GH_APP_KEY", "OPENFACTORY_GH_APP_KEY_CONTENT", STORE_VAR, DIR_VAR):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENFACTORY_GH_APP_ID", "12345")
    monkeypatch.setenv("OPENFACTORY_GH_APP_INSTALLATION_ID", "67890")


@pytest.fixture
def minted(monkeypatch) -> dict:
    """What the minter is handed — the key the command actually used."""
    import openfactory.adapters.github_app as ga

    seen: dict = {}

    def mint(*, app_id, private_key, installation_id):
        seen.update(app_id=app_id, private_key=private_key, installation_id=installation_id)
        return "ghs_MINTED", "2026-01-01T00:00:00Z"

    monkeypatch.setattr(ga, "mint_installation_token", mint)
    return seen


def _commands(command, path: str = "openfactory"):
    """`(path, command)` for `command` and every command under it. A group is whatever has
    `commands`: typer builds its own click classes, so `isinstance(…, click.Group)` sees none."""
    yield path, command
    for name, sub in (getattr(command, "commands", None) or {}).items():
        yield from _commands(sub, f"{path} {name}")


def test_no_option_of_any_command_is_read_from_the_environment():
    """READ FROM THE CLI AS IT IS BUILT — every command, every group, every option."""
    commands = dict(_commands(typer.main.get_command(app)))
    assert len(commands) > 20 and "openfactory bot-token" in commands, sorted(commands)
    options = [(path, param) for path, command in commands.items() for param in command.params]

    read = sorted(f"{path} {param.opts or param.name}: {param.envvar}"
                  for path, param in options if param.envvar)
    assert read == [], (
        f"these options take their default from the environment, before any code of ours runs — "
        f"outside the composition root, and for a credential outside the store: {read}")


def test_the_key_path_flag_is_gone_and_help_names_the_store():
    refused = CliRunner().invoke(app, ["bot-token", "--key-path", "/tmp/acme.pem"])
    assert refused.exit_code == 2, refused.output
    assert "No such option" in refused.output and "--key-path" in refused.output

    said = CliRunner().invoke(app, ["bot-token", "--help"], terminal_width=200)
    assert said.exit_code == 0, said.output
    assert "--key-path" not in said.output
    for words in ("credential store", STORE_VAR, "OPENFACTORY_GH_APP_KEY_CONTENT",
                  "OPENFACTORY_GH_APP_KEY "):
        assert words in " ".join(said.output.split()) + " ", (words, said.output)


def test_the_key_the_command_mints_with_is_the_one_the_store_holds(tmp_path, monkeypatch, minted):
    """A file store holds the PEM; a path in the environment names another. The store's is used —
    the variable the flag was bound to is a deployment credential like any other, asked of the
    declared store first."""
    directory = tmp_path / "secrets"
    directory.mkdir()
    directory.chmod(0o700)
    held = directory / "OPENFACTORY_GH_APP_KEY_CONTENT"
    held.write_text(STORED_PEM)
    held.chmod(0o600)
    other = tmp_path / "other.pem"
    other.write_text(FLAGGED_PEM)
    monkeypatch.setenv(STORE_VAR, "file")
    monkeypatch.setenv(DIR_VAR, str(directory))
    monkeypatch.setenv("OPENFACTORY_GH_APP_KEY", str(other))

    result = CliRunner().invoke(app, ["bot-token"])

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "ghs_MINTED"
    assert minted["private_key"].strip() == STORED_PEM


def test_with_no_key_anywhere_the_refusal_names_the_store(minted):
    result = CliRunner().invoke(app, ["bot-token"])

    assert result.exit_code == 1 and not minted
    said = " ".join(result.stderr.split())
    assert "credential store" in said and STORE_VAR in said, said
