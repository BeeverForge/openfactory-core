"""An empty slice of a Jira project is an empty board, and a missing project is still unreadable (#752).

THE RULE THIS HOLDS. `JiraTracker.list_tickets` tells "there is nothing" from "I could not see"
by asking the project itself when a search comes back empty (`_project_exists`, a `GET
project/<KEY>`): Jira answers `200, []` for a project key that does not exist, so an empty page
alone proves nothing. Under a `scope_jql` (a project's slice of a Jira project it shares with
other registry projects) an empty page is the ordinary case: a slice nobody has filed into yet.
So the SEARCH carries the scope and the EXISTENCE PROBE does not. A probe narrowed to the slice
would turn an empty slice into a missing project, and every caller of `product/board.py` would be
told UNREADABLE about a board that is merely empty. The review of the closed PR #258 named this:
"an empty slice is not a missing project".

The other half is engineering lesson 2. A project that does not exist is unreadable whatever the
scope: a scope must not turn the `None` of a missing project into the `[]` of an empty slice.
Since #749 (6a87018) that 404 costs one more request: `_call` asks `GET myself` once after any
404, to tell a missing project from a credential Jira took as nobody's. The fake answers `myself`
200 (a pair Jira accepts), so the 404 stays a missing project, and the test holds the whole
sequence: search, `project/DAR`, `myself`. Without the route the fake raised AssertionError,
which `_who_is_asking` does not catch (it catches OSError and HTTPException): it passed through
`_call` and was caught by `_project_exists`'s `except Exception`, whose warning named it ("cannot
show the project itself (the adapter called GET myself …)", measured 2026-10-19). The `None`
held, but the last request was `myself`, not the probe the assertion named (red in both orders
after the rebase onto 52025ee, 2026-10-19).

MEASURED ON `main` (1be1835) WITH THIS FILE: both tests fail, because the registry dropped
`scope_jql` and the search carried no scope (`'project = "DAR" ORDER BY updated DESC'`).

WHAT IS DRIVEN HERE is the real `JiraTracker`, built by `build_tracker` from a project's tracker
options as the registry holds them, against a fake at `urllib.request.urlopen`. The fake reads
the JQL by `json.loads` of the request body and the probe by its URL, never by searching bytes.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.parse

KEY = "DAR"
SITE = "https://acme-team.atlassian.net"
SCOPE = 'labels = "of-api"'


class _Answer:
    def __init__(self, payload) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


class _Site:
    """A Jira site whose every search is an empty page. `project_exists`: whether `GET
    project/DAR` answers the project (200) or Jira's 404 for a missing or invisible one. `GET
    myself` answers 200, the account the pair signs in as, so a 404 is never #749's refusal."""

    def __init__(self, *, project_exists: bool) -> None:
        self.project_exists = project_exists
        #: `(method, route, the query string's jql or None, the body's jql or None)`, in order
        self.requests: list[tuple[str, str, str | None, str | None]] = []

    def urlopen(self, req, timeout=0):  # noqa: ARG002 — urllib's own signature
        method = req.get_method()
        split = urllib.parse.urlsplit(req.full_url)
        route = split.path.split("/rest/api/3/", 1)[1]
        in_query = urllib.parse.parse_qs(split.query).get("jql", [None])[0]
        in_body = json.loads(req.data).get("jql") if req.data else None
        self.requests.append((method, route, in_query, in_body))
        if (method, route) == ("POST", "search/jql"):
            return _Answer({"isLast": True, "issues": []})
        if (method, route) == ("GET", f"project/{KEY}"):
            if self.project_exists:
                return _Answer({"key": KEY, "name": "Dar"})
            raise urllib.error.HTTPError(
                req.full_url, 404, "Not Found", hdrs=None,
                fp=io.BytesIO(b'{"errorMessages":["No project could be found with key \'DAR\'."]}'))
        if (method, route) == ("GET", "myself"):
            return _Answer({"accountId": "557058:alice", "emailAddress": "alice@acme.ai"})
        raise AssertionError(f"the adapter called {method} {route}, a route this site never had")


def _scoped_tracker(tmp_path, monkeypatch, *, project_exists: bool):
    from openfactory.adapters.tracker.registry import build_tracker
    from openfactory.contracts.project import Project, ProviderRef

    site = _Site(project_exists=project_exists)
    monkeypatch.setattr("urllib.request.urlopen", site.urlopen)
    project = Project(name="api", repo_path=str(tmp_path / "api"), tracker=ProviderRef(
        kind="jira", repo=KEY,
        options={"site": SITE, "email": "alice@acme.ai", "scope_jql": SCOPE}))
    tracker = build_tracker(project, token="t")
    assert type(tracker).__name__ == "JiraTracker"
    return tracker, site


def test_an_empty_slice_is_read_as_empty_and_the_project_is_asked_unscoped(tmp_path, monkeypatch):
    """AC4: a project whose slice holds no ticket reads `[]`, an empty board, not `None`. The search
    that came back empty carried the scope, and the one existence probe that followed is the bare
    `GET project/DAR`, with no JQL anywhere in it. On main the search had no scope."""
    tracker, site = _scoped_tracker(tmp_path, monkeypatch, project_exists=True)

    assert tracker.list_tickets() == []

    search, *probes = site.requests
    assert search == ("POST", "search/jql", None,
                      f'project = "{KEY}" AND ({SCOPE}) ORDER BY updated DESC')
    assert probes == [("GET", f"project/{KEY}", None, None)]


def test_a_missing_project_is_unreadable_whatever_the_scope(tmp_path, monkeypatch):
    """AC4, lesson 2: when the project itself answers 404, the empty slice is not an empty board:
    `list_tickets` answers `None`, unreadable, even though a scope was declared and its search
    carried it, and the probe and #749's `myself` that follow it carry none. On main the search
    had no scope."""
    tracker, site = _scoped_tracker(tmp_path, monkeypatch, project_exists=False)

    assert tracker.list_tickets() is None

    assert site.requests == [
        ("POST", "search/jql", None, f'project = "{KEY}" AND ({SCOPE}) ORDER BY updated DESC'),
        ("GET", f"project/{KEY}", None, None),
        ("GET", "myself", None, None),
    ]
