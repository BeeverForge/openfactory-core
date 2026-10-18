"""GitHub App auth — mint short-lived installation tokens, with auto-refresh.

GitHub-specific *token acquisition*, deliberately kept out of the core: the
framework only ever holds the opaque token (BotIdentity). App installation tokens
last ~1h, so a long-running server stores the durable **private key** and mints
fresh tokens on demand — never a stored token. Other providers differ (GitLab
tokens are long-lived; Jira uses API tokens), each in their own adapter.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx
import jwt

log = logging.getLogger("openfactory.github_app")


def token_from_env() -> str | None:
    """Resolve a bot token: an explicit OPENFACTORY_BOT_TOKEN, else mint from GitHub App env
    (OPENFACTORY_GH_APP_ID/KEY/INSTALLATION_ID). None if neither is configured. The token is a
    deployment credential, read through the credential store (#742)."""
    from openfactory.adapters.credential_store.registry import stored

    if token := stored("OPENFACTORY_BOT_TOKEN"):
        return token
    from openfactory.credentials import app_id, app_installation_id, app_private_key

    aid, key, inst = app_id(), app_private_key(), app_installation_id()
    if not (aid and key and inst):
        return None
    return mint_installation_token(app_id=aid, private_key=key, installation_id=inst)[0]


def _app_jwt(app_id: str, private_key: str) -> str:
    """The App's own JWT (RS256), the credential every App-level endpoint takes.

    `iat` sixty seconds back absorbs a clock that runs a little fast; `exp` nine minutes ahead
    stays inside GitHub's ten-minute ceiling for an App JWT."""
    now = int(time.time())
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": app_id}, private_key,
                      algorithm="RS256")


def mint_installation_token(
    *, app_id: str, private_key: str, installation_id: str
) -> tuple[str, float]:
    """Sign an App JWT (RS256), exchange it for an installation token. Returns
    (token, expires_at_epoch)."""
    app_jwt = _app_jwt(app_id, private_key)
    r = httpx.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
    return data["token"], expires


def installation_permissions(
    *, app_id: str, private_key: str, installation_id: str
) -> dict[str, str] | None:
    """What the installation is GRANTED — `{"contents": "write", "workflows": "write", ...}` — or
    None when it could not be read (#356).

    `GET /app/installations/{id}`, SIGNED WITH THE APP'S JWT, the way the mint above is: the
    installation's own record, read without minting a token to ask. An installation token cannot
    answer this about itself — GitHub sends it no list of its permissions — and minting one only
    to look would spend for a read. The token a job is minted carries exactly these: the mint
    above asks for no narrower set.

    NEVER RAISES. A key that does not sign, a refused JWT, an unreachable API and an answer
    without `permissions` are all "could not read", which a certificate says as `unknown`."""
    try:
        app_jwt = _app_jwt(app_id, private_key)
        r = httpx.get(
            f"https://api.github.com/app/installations/{installation_id}",
            headers={"Authorization": f"Bearer {app_jwt}",
                     "Accept": "application/vnd.github+json"},
            timeout=30,
        )
        data = r.json() if r.status_code == 200 else None
    except Exception:  # noqa: BLE001 — every failure here is the same answer: not read
        log.info("the App installation's permissions could not be read", exc_info=True)
        return None
    granted = data.get("permissions") if isinstance(data, dict) else None
    if not isinstance(granted, dict):
        return None
    return {str(k): str(v) for k, v in granted.items()}


def installation_account(
    *, app_id: str, private_key: str, installation_id: str, timeout: float = 10.0
) -> tuple[str | None, str]:
    """`(login, "")` of the account the installation is on, or `(None, why it could not be read)`.

    `GET /app/installations/{id}`, signed with the App's JWT, as `installation_permissions` reads
    it: the installation's own record, so nothing is minted to ask (a diagnostic that mints
    spends). `openfactory doctor`'s `installation_scope` line compares the login with the
    organisations the registry names (#743).

    THE REASON IS CARRIED, unlike `installation_permissions`'s `None`. Measured 2026-10-19 against
    api.github.com: no `Authorization` answers `401 Requires authentication`, a validly signed JWT
    for an App GitHub does not know answers `404 Integration not found`, and an unroutable host
    raises `httpx.ConnectTimeout`. A bare 404 does not say whether the App or the installation is
    wrong; GitHub's `message` does, so the reason is `"<status> <message>"`.

    TEN SECONDS, not the mint's thirty: the doctor waits on this read, once per run, and ten is the
    bound it already gives `docker info`. A firewalled box gets a sentence within it.

    NEVER RAISES. "Could not be read" and "read, and on another account" are different answers,
    and the doctor says each in its own words."""
    try:
        app_jwt = _app_jwt(app_id, private_key)
    except Exception as exc:  # noqa: BLE001 — a key that does not sign is a reason, not a crash
        log.info("the App's JWT could not be signed", exc_info=True)
        return None, f"the App's private key does not sign a JWT ({type(exc).__name__})"
    url = f"https://api.github.com/app/installations/{installation_id}"
    try:
        r = httpx.get(url, headers={"Authorization": f"Bearer {app_jwt}",
                                    "Accept": "application/vnd.github+json"},
                      timeout=timeout)
    except httpx.TimeoutException:
        return None, f"{url} did not answer within {timeout:g} s (timed out)"
    except Exception as exc:  # noqa: BLE001 — every transport failure is a reason the doctor says
        log.info("the App installation could not be read", exc_info=True)
        return None, f"{url} could not be reached ({type(exc).__name__}: {str(exc)[:120]})"
    try:
        data = r.json()
    except ValueError:
        data = None
    if r.status_code == 200:
        account = data.get("account") if isinstance(data, dict) else None
        login = account.get("login") if isinstance(account, dict) else None
        if isinstance(login, str) and login:
            return login, ""
        return None, "200, but the answer names no account login"
    message = data.get("message") if isinstance(data, dict) else None
    return None, f"{r.status_code} {message or r.reason_phrase}".strip()


class GitHubAppTokenProvider:
    """Caches an installation token and re-mints ~5 min before it expires. This is
    what an always-on worker holds; a single short `openfactory run` needs only one token."""

    def __init__(self, *, app_id: str, private_key: str, installation_id: str) -> None:
        self.app_id = app_id
        self.private_key = private_key
        self.installation_id = installation_id
        self._token: str | None = None
        self._expires: float = 0.0

    def token(self) -> str:
        if self._token and time.time() < self._expires - 300:
            return self._token
        self._token, self._expires = mint_installation_token(
            app_id=self.app_id, private_key=self.private_key, installation_id=self.installation_id
        )
        return self._token

    def permissions(self) -> dict[str, str] | None:
        """What THIS installation is granted (`installation_permissions`), or None."""
        return installation_permissions(app_id=self.app_id, private_key=self.private_key,
                                        installation_id=self.installation_id)
