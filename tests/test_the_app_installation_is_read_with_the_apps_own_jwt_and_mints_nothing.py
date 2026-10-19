"""The App's installation is read with the App's own JWT, and nothing is minted to ask (#743, S1).

One deployment authenticates as one GitHub App installation (`credentials.app_installation_id`),
and an installation belongs to one account. `openfactory doctor`'s `installation_scope` line asks
that installation which account it is on, through `github_app.installation_account`, and compares
it with the organisations the registry names. Before #743 nothing asked: the registry's docstring
promised a doctor check that did not exist, and `installation_permissions` — the only reader of
`GET /app/installations/{id}` — answered `None` for every failure, so a doctor built on it could
not have said whether the key, the App, the installation or the network was wrong.

The answers below are the ones GitHub gave on 2026-10-19 to an empty `HOME` with no credential:
no `Authorization` → `401 Requires authentication`; a validly signed JWT for an App GitHub does
not know → `404 Integration not found`. The fakes answer REAL `httpx.Response`s (lesson §3: a
bare mock cannot fail the reads the code makes of it). The key is generated per run.
"""

from __future__ import annotations

import dataclasses

import httpx
import jwt
import pytest

from openfactory.adapters import github_app as ga

APP_ID = "918273"
INSTALLATION = "55512345"


@pytest.fixture(scope="module")
def key():
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def pem(key) -> str:
    from cryptography.hazmat.primitives import serialization

    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


class _GitHub:
    """`httpx.get` / `httpx.post` as the adapter calls them, answering one status and body, and
    recording every call with its keyword arguments."""

    def __init__(self, status: int = 200, body=None, raises: Exception | None = None):
        self.status, self.body, self.raises = status, body, raises
        self.gets: list[tuple[str, dict]] = []
        self.posts: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if self.raises is not None:
            raise self.raises
        return httpx.Response(self.status, json=self.body, request=httpx.Request("GET", url))

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return httpx.Response(201, json={"token": "ghs_minted", "expires_at": "2099-01-01T00:00:00Z"},
                              request=httpx.Request("POST", url))


def _answering(monkeypatch, **kw) -> _GitHub:
    github = _GitHub(**kw)
    monkeypatch.setattr(ga.httpx, "get", github.get)
    monkeypatch.setattr(ga.httpx, "post", github.post)
    return github


def _ask(pem: str):
    return ga.installation_account(app_id=APP_ID, private_key=pem, installation_id=INSTALLATION)


def test_the_read_is_GET_app_installations_id_signed_with_a_jwt_the_apps_key_verifies(
        monkeypatch, key, pem):
    """S1: "asks the configured App installation which organisation it is installed on
    (`GET /app/installations/{id}`)". Before #743 there was no such function to ask."""
    github = _answering(monkeypatch, body={"id": int(INSTALLATION),
                                           "account": {"login": "acme", "type": "Organization"}})

    assert _ask(pem) == ("acme", "")

    url, kwargs = github.gets[0]
    assert url == f"https://api.github.com/app/installations/{INSTALLATION}"
    signed = kwargs["headers"]["Authorization"].removeprefix("Bearer ")
    claims = jwt.decode(signed, key.public_key(), algorithms=["RS256"])
    assert claims["iss"] == APP_ID
    assert claims["exp"] - claims["iat"] <= 600, "GitHub refuses an App JWT living over ten minutes"


def test_no_installation_token_is_minted_to_ask(monkeypatch, pem):
    """A diagnostic that mints spends (`credentials.py`'s mint comment): the account is on the
    installation's own record, which the App's JWT reads without an `access_tokens` exchange."""
    github = _answering(monkeypatch, body={"account": {"login": "acme", "type": "Organization"}})

    _ask(pem)

    assert github.posts == [], f"a token was minted to ask: {github.posts[0][0]}"
    assert len(github.gets) == 1


def test_a_read_that_times_out_is_a_reason_and_not_a_raise(monkeypatch, pem):
    """Measured 2026-10-19: an unroutable host raises `httpx.ConnectTimeout`. The doctor waits
    on this read, so it is bounded, and a firewalled box gets a sentence, not a traceback."""
    url = f"https://api.github.com/app/installations/{INSTALLATION}"
    github = _answering(monkeypatch, raises=httpx.ConnectTimeout(
        "timed out", request=httpx.Request("GET", url)))

    login, reason = _ask(pem)

    assert login is None
    assert "timed out" in reason.lower() or "timeout" in reason.lower(), reason
    timeout = github.gets[0][1]["timeout"]
    assert isinstance(timeout, (int, float)) and 0 < timeout <= 10, timeout


@pytest.mark.parametrize("status,message", [
    (401, "Requires authentication"),
    (401, "Bad credentials"),
    (404, "Integration not found"),
    (404, "Not Found"),
])
def test_github_s_own_message_is_the_reason_when_it_refuses(monkeypatch, pem, status, message):
    """A 404 alone does not say whether the App or the installation is wrong; GitHub's `message`
    does (measured 2026-10-19: `Integration not found` for an App GitHub does not know). Lesson
    §2: the reason the read failed is carried, never folded into one `None`."""
    _answering(monkeypatch, status=status, body={"message": message})

    login, reason = _ask(pem)

    assert login is None
    assert str(status) in reason and message in reason, reason


def test_the_live_probes_ask_the_installation_and_doctor_reports_it(monkeypatch, pem):
    """Lesson §1: the real probe `probes_for` builds reaches the real read, through the credential
    row, with the App trio this process was given — and the doctor's line says what it answered."""
    from openfactory import doctor
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.registry import ProjectRegistry
    from tests.pinned_probes import a_fully_pinned_probe_set

    project = Project(name="api", repo_path="/tmp/api",
                      tracker=ProviderRef(kind="github", repo="acme/api"))
    ProjectRegistry().add(project)
    monkeypatch.setenv("OPENFACTORY_GH_APP_ID", APP_ID)
    monkeypatch.setenv("OPENFACTORY_GH_APP_KEY_CONTENT", pem)
    monkeypatch.setenv("OPENFACTORY_GH_APP_INSTALLATION_ID", INSTALLATION)
    github = _answering(monkeypatch, body={"account": {"login": "othercorp",
                                                       "type": "Organization"}})

    probes = dataclasses.replace(
        a_fully_pinned_probe_set(),
        installation_scope=doctor.probes_for(project).installation_scope)
    finding = next(f for f in doctor.diagnose(probes).findings
                   if f.check == doctor.INSTALLATION_SCOPE)

    assert finding.ok is False
    assert "othercorp" in finding.message and "acme" in finding.message, finding.message
    assert github.gets and github.posts == []
