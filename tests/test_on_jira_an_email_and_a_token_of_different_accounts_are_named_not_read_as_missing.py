"""#749: on Jira, an email and an API token of two different accounts made every card read as missing.

JIRA CLOUD DOES NOT REFUSE A BASIC-AUTH PAIR WHOSE TOKEN IS ANOTHER ACCOUNT'S. It answers the request
as if nobody had signed in: `GET issue/<KEY>` is 404 "does not exist or you do not have permission
to see it", `GET project/<KEY>` is 404, and `search/jql` is 200 with an empty page. `_call` turned
the 404 into `JiraRefused("jira GET issue/DAR-7 failed: 404 …", code=404)`, and every reader a
person sees repeated it — the card's door (`Ports.seen`, `str(exc)[:120]`), the job's preflight
(`degrade(f"ticket: {str(exc)[:120]}")`), the board (`_project_exists` → None) — so every card that
exists read as not found, and jobs parked on it. Reported 2026-10-14 by a downstream deployment
against v0.6.0-rc.2; reported, not re-measured here.

THE ONE REQUEST THAT DOES SAY IT is `GET /rest/api/3/myself`: anonymous, it answers 401 (Atlassian's
REST v3 documentation of "Get current user"; the issue's report). So a 404 asks it ONCE, with the
same credential, under `api/3` whatever family 404'd — `myself` exists nowhere else. A 401 there
is the refusal that names the pair; anything else, or no answer at all, keeps the 404 exactly as it
was, so a card that is really missing, or a site that could not be asked, is never misreported the
other way.

A SECOND INSTANCE OF THE SAME DEFECT, found in the code: with no token at all `_headers` sends
`email:` with an empty password, which Jira reads the same anonymous way. Calling that "different
accounts" would be false, so it has a sentence of its own.

WHAT IS DRIVEN IS THE REAL `JiraTracker`, THROUGH ITS REAL `_call`, against a fake at the one place
the adapter touches the network (`urllib.request.urlopen`), as
`test_a_withdrawn_card_is_not_delivered_on_jira.py` does. The fake records every request with its
`Authorization` header and refuses any route it does not have. Its 404 bodies are pt-BR on the issue
and English on the project, because a pt-BR site answers in Portuguese: the rule reads the status
code, never the body.
"""

from __future__ import annotations

import io
import json
import logging
import urllib.error
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from openfactory.adapters.tracker.jira import JiraRefused, JiraTracker
from openfactory.lifecycle.ports import Ports
from openfactory.techlead import CREDENTIAL, classify

SITE = "https://acme-team.atlassian.net"
EMAIL = "alice@acme.ai"
TOKEN = "ATATT3xFfGF0-not-a-real-token-0123456789"
REF = "DAR-7"
ISSUE = f"/rest/api/3/issue/{REF}"
PROJECT = "/rest/api/3/project/DAR"
SEARCH = "/rest/api/3/search/jql"
MYSELF = "/rest/api/3/myself"

#: What a pt-BR site answers on an issue an anonymous request cannot see (the issue's report).
_ISSUE_404 = {"errorMessages": ["O item não existe ou você não tem permissão para vê-lo."],
              "errors": {}}
#: …and an English one on a project.
_PROJECT_404 = {"errorMessages": ["No project could be found with key 'DAR'."], "errors": {}}
#: `GET myself` without a signed-in user.
_MYSELF_401 = {"errorMessages": ["You are not authenticated. Authentication required to perform "
                                 "this operation."]}
_MYSELF_200 = {"accountId": "5b10a2844c20165700ede21g", "emailAddress": EMAIL,
               "displayName": "Alice", "active": True}
_ISSUE_200 = {"id": "10071", "key": REF,
              "fields": {"summary": "exportar o relatório", "description": None,
                         "status": {"name": "A Fazer", "statusCategory": {"key": "new"}}}}


class _Answer:
    def __init__(self, payload: dict | None) -> None:
        self._body = json.dumps(payload).encode() if payload is not None else b""

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


class _Site:
    """One Jira Cloud site: the routes a case gives it, and what `GET myself` answers.

    A route's answer is a payload (200), an HTTP status (an `HTTPError` with that code), or an
    exception `urlopen` raises (the network). `myself` is answered the same way."""

    def __init__(self, *, routes: dict | None = None, myself=401) -> None:
        self.routes = routes or {}
        self.myself = myself
        self.requests: list[tuple[str, str, str | None]] = []   # method, path?query, Authorization

    def asked(self, path: str) -> int:
        return sum(1 for _method, asked, _auth in self.requests if asked == path)

    def _refuse(self, req, code: int):
        payload = {MYSELF: _MYSELF_401, PROJECT: _PROJECT_404}.get(
            urlsplit(req.full_url).path, _ISSUE_404)
        raise urllib.error.HTTPError(req.full_url, code, "refused", hdrs=None,
                                     fp=io.BytesIO(json.dumps(payload, ensure_ascii=False).encode()))

    def urlopen(self, req, timeout=0):  # noqa: ARG002 — urllib's own signature
        method = req.get_method()
        parts = urlsplit(req.full_url)
        assert f"{parts.scheme}://{parts.netloc}" == SITE, req.full_url
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        self.requests.append((method, path, req.get_header("Authorization")))
        if path == MYSELF and method == "GET":
            if self.asked(MYSELF) > 3:
                raise AssertionError("GET myself asked again and again: the probe recursed")
            answer = self.myself
        elif (method, path) in self.routes:
            answer = self.routes[(method, path)]
        else:
            raise AssertionError(f"the adapter called {method} {path}, a route this site never had")
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, int):
            if answer >= 400:
                self._refuse(req, answer)
            return _Answer(None)
        return _Answer(answer)


@pytest.fixture
def site(monkeypatch):
    def _open(**kw) -> _Site:
        jira = _Site(**kw)
        monkeypatch.setattr("urllib.request.urlopen", jira.urlopen)
        return jira
    return _open


def _tracker(*, email: str = EMAIL, token: str | None = TOKEN) -> JiraTracker:
    return JiraTracker(site=SITE, project_key="DAR", email=email, token=token)


def _main_says(code: int) -> str:
    """The sentence `_call` raised on 82500f9 for a refused `GET issue/DAR-7`."""
    return f"jira GET issue/{REF} failed: {code} {json.dumps(_ISSUE_404, ensure_ascii=False)}"


# ── C1: a 404 whose `myself` answers 401 is the mismatch, named ──────────────────────────────────

def test_a_404_whose_myself_answers_401_is_refused_with_code_401_naming_the_email_and_the_remedy(
        site):
    """C1. On 82500f9 this raised `code=404` "…does not exist…", and nothing asked `myself`."""
    site(routes={("GET", ISSUE): 404}, myself=401)

    with pytest.raises(JiraRefused) as raised:
        _tracker().get_ticket(REF)

    exc = raised.value
    assert exc.code == 401, str(exc)
    assert isinstance(exc, RuntimeError), "every catch-all caller parks on a RuntimeError"
    text = str(exc)
    assert EMAIL in text
    assert "different accounts" in text
    assert "pair" in text.lower()
    assert isinstance(exc.__cause__, urllib.error.HTTPError) and exc.__cause__.code == 404


def test_the_refusal_never_carries_the_token(site, caplog):
    """C1. The sentence names the email a person typed, never the secret beside it."""
    site(routes={("GET", ISSUE): 404}, myself=401)

    with caplog.at_level(logging.DEBUG, logger="openfactory.tracker.jira"):
        with pytest.raises(JiraRefused) as raised:
            _tracker().get_ticket(REF)

    assert raised.value.code == 401, str(raised.value)
    assert TOKEN not in str(raised.value)
    assert TOKEN not in repr(raised.value.args)
    assert all(TOKEN not in r.getMessage() for r in caplog.records)


def test_myself_is_asked_with_the_same_credential_as_the_call_that_404d(site):
    """C1. The probe is the same person asking: a `myself` asked by nobody would always be 401."""
    jira = site(routes={("GET", ISSUE): 404}, myself=401)

    with pytest.raises(JiraRefused):
        _tracker().get_ticket(REF)

    assert [path for _m, path, _a in jira.requests] == [ISSUE, MYSELF]
    (issue_auth, myself_auth) = [auth for _m, _p, auth in jira.requests]
    assert issue_auth and issue_auth.startswith("Basic ")
    assert myself_auth == issue_auth


def test_a_404_on_the_agile_api_asks_myself_of_the_core_api(site):
    """C1. `_call` serves `agile/1.0` too (the board's rank), and `myself` lives only under `api/3`:
    a probe that followed the call's family would ask a route Jira does not have."""
    jira = site(routes={("PUT", "/rest/agile/1.0/issue/rank"): 404}, myself=401)

    with pytest.raises(JiraRefused) as raised:
        _tracker()._call("PUT", "issue/rank", {"issues": [REF], "rankBeforeIssue": "DAR-3"},
                         api="agile/1.0")

    assert jira.asked(MYSELF) == 1
    assert jira.asked("/rest/agile/1.0/myself") == 0
    assert raised.value.code == 401, str(raised.value)


# ── C2: a probe that says anything else, or nothing, keeps the 404 ───────────────────────────────

def test_a_404_whose_myself_answers_200_is_the_original_404_unchanged(site):
    """C2. A signed-in user who cannot see the card, or a card that is gone: the 404 as it was."""
    jira = site(routes={("GET", ISSUE): 404}, myself=_MYSELF_200)

    with pytest.raises(JiraRefused) as raised:
        _tracker().get_ticket(REF)

    assert str(raised.value) == _main_says(404)
    assert raised.value.code == 404
    assert jira.asked(MYSELF) == 1


@pytest.mark.parametrize("myself", [
    urllib.error.URLError("[Errno -3] Temporary failure in name resolution"),
    TimeoutError(),
    ConnectionResetError(),
    500, 502, 503,
    403, 404,
], ids=["dns", "timeout", "reset", "500", "502", "503", "403", "404"])
def test_a_myself_that_cannot_answer_keeps_the_original_404(site, myself):
    """C2. A probe that cannot answer (network, 5xx), or answers something that is not 401, keeps
    the original 404, so nothing is misreported the other way."""
    jira = site(routes={("GET", ISSUE): 404}, myself=myself)

    with pytest.raises(JiraRefused) as raised:
        _tracker().get_ticket(REF)

    assert jira.asked(MYSELF) == 1
    assert raised.value.code == 404
    assert str(raised.value) == _main_says(404)
    assert isinstance(raised.value.__cause__, urllib.error.HTTPError)


# ── C3: once per 404, and never for any other answer ─────────────────────────────────────────────

def test_myself_is_asked_once_per_404_and_never_for_any_other_answer(site):
    """C3. On 82500f9 no row asked it, so the 404 rows asked it 0 times, not 1."""
    jira = site(routes={("GET", ISSUE): _ISSUE_200})
    _tracker().get_ticket(REF)
    assert jira.asked(MYSELF) == 0, "a card that reads costs no extra request"

    for code in (400, 401, 403, 500):
        jira = site(routes={("GET", ISSUE): code})
        with pytest.raises(JiraRefused) as raised:
            _tracker().get_ticket(REF)
        assert raised.value.code == code
        assert jira.asked(MYSELF) == 0, f"a {code} is not a 404 and asks nothing"

    jira = site(routes={("GET", ISSUE): 404}, myself=_MYSELF_200)
    with pytest.raises(JiraRefused):
        _tracker().get_ticket(REF)
    assert jira.asked(MYSELF) == 1, "one 404 asks once"

    jira = site(routes={("GET", ISSUE): 404}, myself=_MYSELF_200)
    tracker = _tracker()
    for _ in range(2):
        with pytest.raises(JiraRefused):
            tracker.get_ticket(REF)
    assert jira.asked(MYSELF) == 2, "two 404s ask twice: nothing is cached"

    jira = site(routes={("GET", ISSUE): 404}, myself=404)
    with pytest.raises(JiraRefused) as raised:
        _tracker().get_ticket(REF)
    assert jira.asked(MYSELF) == 1, "a myself that 404s is not itself probed"
    assert raised.value.code == 404


# ── C4: what a person reads names the mismatch ───────────────────────────────────────────────────

def test_a_card_read_through_the_door_says_the_account_is_mismatched_not_that_it_is_missing(site):
    """C4. `Ports.seen` cuts the exception at 120 characters; on 82500f9 what was left said
    "…failed: 404 …não existe…", for a card that exists."""
    site(routes={("GET", ISSUE): 404}, myself=401)

    seen = Ports(SimpleNamespace(name="dar"), tracker=_tracker()).seen(REF)

    assert seen.cannot_tell
    assert "different accounts" in seen.cannot_tell, seen.cannot_tell


def test_the_cause_comes_first_in_the_sentence_so_a_park_line_keeps_it(site):
    """C4. The job's preflight parks on `str(exc)[:120]` (`activities.py`), so the cause must sit
    before the longest path this adapter 404s on, with a long email."""
    email = "first.middle.lastname@acme-team-group.ai"
    assert len(email) == 40
    path = f"issue/{REF}/comment?startAt=0&maxResults=100"
    site(routes={("GET", f"/rest/api/3/{path}"): 404}, myself=401)

    with pytest.raises(JiraRefused) as raised:
        _tracker(email=email)._all_comments(REF)

    assert "different accounts" in str(raised.value)[:120], str(raised.value)


def test_a_board_read_with_a_mismatched_pair_is_unreadable_and_the_log_names_the_pair(
        site, caplog):
    """C4. An anonymous `search/jql` is 200 and empty, `project/DAR` is 404: the board is None
    (unreadable, never `[]`), and on 82500f9 the warning carried the 404 text only."""
    site(routes={("POST", SEARCH): {"isLast": True, "issues": []}, ("GET", PROJECT): 404},
         myself=401)

    with caplog.at_level(logging.WARNING, logger="openfactory.tracker.jira"):
        board = _tracker().list_tickets()

    assert board is None
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "different accounts" in said, said


@pytest.mark.parametrize("token", [TOKEN, None], ids=["another-accounts-token", "no-token"])
def test_a_job_parked_on_the_refusal_is_classified_as_a_credential(site, token):
    """C4, the job's park: the preflight parks on `f"ticket: {str(exc)[:120]}"` (`activities.py`),
    and the tech-lead classifies that line. On 82500f9 both refusals' first 120 characters read
    `unknown` (measured 2026-10-19), so a parked job named no cause; the pair is a credential."""
    site(routes={("GET", ISSUE): 404}, myself=401)

    with pytest.raises(JiraRefused) as raised:
        _tracker(token=token).get_ticket(REF)

    park = f"ticket: {str(raised.value)[:120]}"
    assert classify(park).cause == CREDENTIAL, park

# ── C5: no token at all is not "different accounts" ─────────────────────────────────────────────

@pytest.mark.parametrize("token", [None, ""], ids=["none", "empty"])
def test_with_no_token_the_refusal_says_no_token_reached_the_tracker(site, token):
    """C5. `_headers` sends `email:` with an empty password, the same anonymous request; the
    registry promises the adapter names the variable to set, and on 82500f9 it said 404."""
    site(routes={("GET", ISSUE): 404}, myself=401)

    with pytest.raises(JiraRefused) as raised:
        _tracker(token=token).get_ticket(REF)

    assert raised.value.code == 401, str(raised.value)
    assert "no API token" in str(raised.value)
    assert "different accounts" not in str(raised.value)
    assert "token_env" in str(raised.value)


# ── the cost: a read that answers asks nothing more ──────────────────────────────────────────────

def test_a_card_that_reads_costs_no_extra_request(site):
    """Lesson 10, the cost measured: the probe is paid only by a 404. A card that reads is one
    request, a board with issues one, an empty board whose project answers two, as on 82500f9;
    what the probe adds is one request per 404 (`get_ticket` 1 → 2, an empty board whose project
    404s 2 → 3, whatever `myself` answers).

    Green on 82500f9, which had no probe: it holds the new path against a probe on every answer
    (the 749 plan's "the probe runs on a call that succeeded" cut turns it red)."""
    row = {"key": REF, "fields": _ISSUE_200["fields"]}

    jira = site(routes={("GET", ISSUE): _ISSUE_200}, myself=_MYSELF_200)
    _tracker().get_ticket(REF)
    assert [path for _m, path, _a in jira.requests] == [ISSUE]

    jira = site(routes={("POST", SEARCH): {"isLast": True, "issues": [row]}}, myself=_MYSELF_200)
    assert _tracker().list_tickets()
    assert [path for _m, path, _a in jira.requests] == [SEARCH]

    jira = site(routes={("POST", SEARCH): {"isLast": True, "issues": []},
                        ("GET", PROJECT): {"key": "DAR"}}, myself=_MYSELF_200)
    assert _tracker().list_tickets() == []
    assert [path for _m, path, _a in jira.requests] == [SEARCH, PROJECT]
