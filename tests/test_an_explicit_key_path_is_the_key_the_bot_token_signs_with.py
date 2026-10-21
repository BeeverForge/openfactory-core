"""An explicit `--key-path` is the key `openfactory bot-token` signs the App JWT with (#905).

THE DEFECT. `bot-token` declared `--key-path` and never read it: the key always came from
`app_private_key()`, i.e. `OPENFACTORY_GH_APP_KEY_CONTENT` and then `OPENFACTORY_GH_APP_KEY`.
Measured 2026-10-20 on bb929e49 (and unchanged on fa548ed4), empty `HOME`, no credential in the
environment: `openfactory bot-token --app-id 1 --installation-id 1 --key-path <a real RSA PEM>`
exits 1 with "need OPENFACTORY_GH_APP_ID, OPENFACTORY_GH_APP_INSTALLATION_ID, and the App key
...", naming as missing an app id that was passed. So a freshly downloaded `.pem` could not be
proven before it was deployed, which is what the command's docstring says it is for.

THE PRECEDENCE THESE TESTS HOLD: `--key-path` > `OPENFACTORY_GH_APP_KEY_CONTENT` >
`OPENFACTORY_GH_APP_KEY`, the most-specific-wins rule `--app-id` and `--installation-id` already
follow (#64). An explicit path that cannot be read ends the resolution with a sentence naming it;
it never falls back to the environment's key ("could not read" is not "nothing given",
engineering-lessons §2).

READING THE THING. The keys are real RSA keys made here, and the only stub is `httpx.post`, the
network edge inside `openfactory.adapters.github_app`, with the exact keyword signature
`mint_installation_token` calls it with. The JWT it is handed is verified against each key's
public half, so "which key signed" is a cryptographic answer, not a mock's say-so (lessons §3: a
`**kw` lambda in place of `mint_installation_token` could not fail an arity check, nor tell which
key was used).
"""

from __future__ import annotations

import errno
import functools
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from typer.testing import CliRunner

from openfactory.adapters import github_app as ga
from openfactory.cli import app

#: Every variable `bot-token` can be handed the App trio through. The conftest already strips
#: `OPENFACTORY_*` from the test environment; each test clears these again so it never depends on
#: that, nor on a developer's shell that exports one in its profile.
APP_VARS = ("OPENFACTORY_GH_APP_ID", "OPENFACTORY_GH_APP_INSTALLATION_ID",
            "OPENFACTORY_GH_APP_KEY", "OPENFACTORY_GH_APP_KEY_CONTENT")


@functools.cache
def _key(name: str) -> rsa.RSAPrivateKey:
    """A fictitious App key, made once per name for the module (2048-bit RSA, as GitHub issues)."""
    del name  # the name only keys the cache: "A" and "B" are two distinct keys
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _pem(name: str) -> str:
    return _key(name).private_bytes(serialization.Encoding.PEM,
                                    serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()).decode()


def _signers(app_jwt: str) -> set[str]:
    """Which of the two keys verify this JWT: `{"A"}` means A signed it and B's check raised
    `InvalidSignatureError`."""
    verified = set()
    for name in ("A", "B"):
        try:
            jwt.decode(app_jwt, _key(name).public_key(), algorithms=["RS256"],
                       options={"verify_exp": False})
        except jwt.InvalidSignatureError:
            continue
        verified.add(name)
    return verified


@pytest.fixture
def github(monkeypatch):
    """GitHub's token endpoint, answered: every call is recorded as `(url, jwt)`.

    The signature is the one `mint_installation_token` uses (`url, *, headers, timeout`), so a
    change in how it calls `httpx.post` fails here rather than passing through a `**kw`."""
    calls: list[tuple[str, str]] = []

    def post(url, *, headers, timeout):
        calls.append((url, headers["Authorization"].removeprefix("Bearer ")))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"token": "ghs_x", "expires_at": "2099-01-01T00:00:00Z"})

    monkeypatch.setattr(ga.httpx, "post", post)
    for var in APP_VARS:
        monkeypatch.delenv(var, raising=False)
    return calls


def _key_file(path: Path, name: str) -> Path:
    path.write_text(_pem(name))
    return path


@pytest.mark.parametrize("environment_form", ["content", "path"])
def test_the_jwt_is_signed_by_the_key_at_key_path_and_not_by_the_environments(
        environment_form, github, monkeypatch, tmp_path):
    """Criterion: "an explicit `--key-path` wins", and "a test shows that `--key-path <a
    fictitious PEM>` is the key used".

    The environment holds key B in either of its two shapes: the PEM itself
    (`OPENFACTORY_GH_APP_KEY_CONTENT`, a container's form) or a path (`OPENFACTORY_GH_APP_KEY`,
    what a person may have exported in a shell profile). Before the fix the JWT was signed by B in
    both cases: the flag's value was bound and dropped.
    """
    monkeypatch.setenv("OPENFACTORY_GH_APP_ID", "12345")
    monkeypatch.setenv("OPENFACTORY_GH_APP_INSTALLATION_ID", "67890")
    if environment_form == "content":
        monkeypatch.setenv("OPENFACTORY_GH_APP_KEY_CONTENT", _pem("B"))
    else:
        monkeypatch.setenv("OPENFACTORY_GH_APP_KEY", str(_key_file(tmp_path / "b.pem", "B")))
    a = _key_file(tmp_path / "a.pem", "A")

    result = CliRunner().invoke(app, ["bot-token", "--key-path", str(a)])

    assert result.exit_code == 0, result.output
    assert len(github) == 1, f"expected one mint, saw {len(github)}"
    _url, app_jwt = github[0]
    assert _signers(app_jwt) == {"A"}, (
        "the App JWT must be signed by the key at --key-path (A), not by the environment's (B)")


@pytest.mark.parametrize("spelling", ["absolute", "tilde"])
def test_key_path_alone_with_the_two_id_flags_mints_with_no_environment_at_all(
        spelling, github, monkeypatch, tmp_path):
    """Criterion: "an explicit `--key-path` wins", with nothing in the environment: the three
    flags are the whole trio, the way a new `.pem` is proven before it is deployed.

    Before the fix this exited 1 with "need OPENFACTORY_GH_APP_ID, ..." (measured 2026-10-20 with
    the real CLI). The `tilde` case is a path the shell did not expand (quoted `'~/a.pem'`): it
    resolves against `HOME`, as `OPENFACTORY_GH_APP_KEY` always did (`expanduser`).
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    a = _key_file(tmp_path / "a.pem", "A")
    flag = str(a) if spelling == "absolute" else "~/a.pem"

    result = CliRunner().invoke(
        app, ["bot-token", "--app-id", "1", "--installation-id", "2", "--key-path", flag])

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "ghs_x", (
        "stdout must carry the token alone: `$(openfactory bot-token)` captures it")
    assert len(github) == 1, f"expected one mint, saw {len(github)}"
    url, app_jwt = github[0]
    assert url == "https://api.github.com/app/installations/2/access_tokens"
    assert _signers(app_jwt) == {"A"}
    assert jwt.decode(app_jwt, _key("A").public_key(), algorithms=["RS256"],
                      options={"verify_exp": False})["iss"] == "1"


@pytest.mark.parametrize("unreadable, expected_error, expected_errno", [
    ("missing.pem", FileNotFoundError, errno.ENOENT),
    ("a-directory", IsADirectoryError, errno.EISDIR),
], ids=["missing-file", "directory"])
def test_an_unreadable_key_path_refuses_naming_the_path_and_does_not_use_the_environments_key(
        unreadable, expected_error, expected_errno, github, monkeypatch, tmp_path):
    """Criterion: "an explicit path that cannot be read refuses with a sentence naming that path
    and never falls back to a key from the environment" (lessons §2 and §6; #822's "a refusal is
    never a fallback").

    Before the fix the path was ignored and the command minted with the environment's key B,
    exit 0. The reason is checked against the error this process gets reading the same path
    (class, errno, and its `strerror` in this process's locale), not against English text. The
    reason's language is the process's, not the shell's: Python sets only LC_CTYPE at startup, so
    under `LC_ALL=pt_BR.UTF-8` the CLI still says "No such file or directory"; once anything in
    the process calls `locale.setlocale(locale.LC_ALL, "")` it says "Arquivo ou diretório
    inexistente" (both measured 2026-10-21, Ubuntu 24.04, glibc 2.39, Python 3.12.3). This test
    passes in all three (LC_ALL=C, LC_ALL=pt_BR.UTF-8, and pt_BR after that call); "No such
    file" in the assertion would fail the third.
    """
    monkeypatch.setenv("OPENFACTORY_GH_APP_ID", "12345")
    monkeypatch.setenv("OPENFACTORY_GH_APP_INSTALLATION_ID", "67890")
    monkeypatch.setenv("OPENFACTORY_GH_APP_KEY_CONTENT", _pem("B"))
    path = tmp_path / unreadable
    if expected_error is IsADirectoryError:
        path.mkdir()
    with pytest.raises(OSError) as reading:
        path.read_text()
    assert type(reading.value) is expected_error and reading.value.errno == expected_errno, (
        f"the case is not the one it names: reading {path} raised {reading.value!r}")

    result = CliRunner().invoke(app, ["bot-token", "--key-path", str(path)])

    assert github == [], "nothing may be minted when the explicit key could not be read"
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit), (
        f"the refusal must be a sentence, not an exception: {result.exception!r}")
    assert "Traceback" not in result.output
    assert str(path) in result.stderr, f"the refusal must name {path}: {result.stderr!r}"
    assert reading.value.strerror in result.stderr, (
        f"the refusal must say why ({reading.value.strerror!r}): {result.stderr!r}")


def test_an_empty_key_path_refuses_and_does_not_use_the_environments_key(github, monkeypatch):
    """`--key-path "$NEW_PEM"` with the variable unset hands the option "": a path given and
    unreadable, not "no flag" (lessons §2), so it must not prove the environment's key.

    Criterion: "an explicit path that cannot be read refuses ... and never falls back to a key from
    the environment". On efa234a2 `if key_path:` sent "" to the `else` branch: the review measured
    `--key-path "$NEW_PEM"` (unset) under `env -i` with the deployment key in
    `OPENFACTORY_GH_APP_KEY` print "✓ the App trio works", JWT signed by the environment's key,
    exit 0 (2026-10-21).
    """
    monkeypatch.setenv("OPENFACTORY_GH_APP_ID", "12345")
    monkeypatch.setenv("OPENFACTORY_GH_APP_INSTALLATION_ID", "67890")
    monkeypatch.setenv("OPENFACTORY_GH_APP_KEY_CONTENT", _pem("B"))

    result = CliRunner().invoke(app, ["bot-token", "--key-path", ""])

    assert github == [], "an empty --key-path minted with the environment's key"
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert "--key-path" in result.stderr, f"the refusal must name the flag: {result.stderr!r}"


def test_a_key_path_that_is_not_text_refuses_by_name(github, monkeypatch, tmp_path):
    """A DER key (or any binary file) cannot be read as a PEM: a sentence naming it, not a
    `UnicodeDecodeError` traceback.

    Criterion: "an explicit path that cannot be read refuses with a sentence naming that path".
    On 4adc0410 `app_private_key_at` called `read_text()`, whose `UnicodeDecodeError` is a
    `ValueError`, past the CLI's `except OSError`: the review measured `exit=1
    exc=UnicodeDecodeError` with a DER PKCS8 key, and a traceback from the real CLI on 300 random
    bytes (2026-10-21).
    """
    monkeypatch.setenv("OPENFACTORY_GH_APP_ID", "12345")
    monkeypatch.setenv("OPENFACTORY_GH_APP_INSTALLATION_ID", "67890")
    monkeypatch.setenv("OPENFACTORY_GH_APP_KEY_CONTENT", _pem("B"))
    der = tmp_path / "key.der"
    der.write_bytes(_key("A").private_bytes(serialization.Encoding.DER,
                                            serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption()))

    result = CliRunner().invoke(app, ["bot-token", "--key-path", str(der)])

    assert github == []
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert str(der) in result.stderr, result.stderr


def test_without_the_flag_the_key_the_environment_names_by_path_is_still_used(
        github, monkeypatch, tmp_path):
    """Preservation: without `--key-path`, the key is still found through `app_private_key()`,
    here by the path form `OPENFACTORY_GH_APP_KEY`.

    GREEN ON MAIN BY DESIGN: this is not a red test. It pins that dropping `envvar=` from the
    option did not drop the environment's path form (typer used to read that same variable into
    the unused flag); `test_the_bot_token_command_still_resolves_from_the_environment` in
    `tests/test_one_process_one_installation.py` covers only the `_CONTENT` form.
    """
    monkeypatch.setenv("OPENFACTORY_GH_APP_ID", "12345")
    monkeypatch.setenv("OPENFACTORY_GH_APP_INSTALLATION_ID", "67890")
    monkeypatch.setenv("OPENFACTORY_GH_APP_KEY", str(_key_file(tmp_path / "a.pem", "A")))

    result = CliRunner().invoke(app, ["bot-token"])

    assert result.exit_code == 0, result.output
    assert len(github) == 1, f"expected one mint, saw {len(github)}"
    assert _signers(github[0][1]) == {"A"}
