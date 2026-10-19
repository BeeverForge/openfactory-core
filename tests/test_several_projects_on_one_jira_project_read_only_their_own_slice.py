"""Several platform projects on one Jira project each read only their own slice of it (#752).

THE INCIDENT. A deployment registered about nineteen repositories against one Jira project, each
its own registry project with `tracker: {kind: jira, repo: <KEY>}`. Every JQL the Jira row built
was `project = "<KEY>"` and nothing else, so every project's poller read the whole Jira project as
its pickup queue: in one night one ticket was picked up by three projects (issue #752, against
v0.6.0-rc.2). Nothing a project declared could narrow the read.

WHAT IS NOW TRUE. A Jira tracker option `scope_jql` — a JQL condition such as `labels = "of-api"` —
is ANDed, inside parentheses, onto every read the Jira board makes (`columns`, `items_in_status`,
and `place_after` through it) and onto `JiraTracker.list_tickets`. The board reads it off its
tracker with `getattr`, so the port does not change. Unset, or only whitespace, every query is
byte for byte what it was. A scope Jira refuses is named in the warning, and the read stays
UNREADABLE, never empty.

MEASURED ON `main` (1be1835) WITH THIS FILE: every test but the no-scope one fails. The registry
dropped the option and no read carried a clause, so both pollers below answered `["DAR-1", "DAR-2"]`.

WHAT IS DRIVEN HERE is the real `JiraTracker` and the real `JiraProjectBoard`, built by
`build_tracker` / `build_board` from a project's tracker options as the registry holds them,
against a fake at the one place the adapter touches the network (`urllib.request.urlopen`). The
board sends its JQL URL-encoded in a GET query and the tracker in a POST body, and only `urlopen`
sees both. The fake reads the JQL by parsing the request (`parse_qs`, `json.loads`), never by
searching its bytes, and the strict one fails the test (`pytest.fail`, which the adapters'
`except Exception` cannot swallow) on any search that is not narrowed to the declared scope.
"""

from __future__ import annotations

import io
import json
import logging
import re
import urllib.error
import urllib.parse
from datetime import UTC, datetime, timedelta

import pytest

KEY = "DAR"
SITE = "https://acme-team.atlassian.net"
TODO = "A Fazer"
API, WEB = 'labels = "of-api"', 'labels = "of-web"'
#: which tickets carry which label on the shared project — the slice each scope selects
LABELS = {"DAR-1": "of-api", "DAR-2": "of-web"}


class _Answer:
    def __init__(self, payload) -> None:
        self._body = json.dumps(payload).encode() if payload is not None else b""

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _board_issue(key: str) -> dict:
    return {"key": key, "fields": {"status": {"name": TODO}}}


def _list_issue(key: str) -> dict:
    """One `search/jql` row in the shape the live endpoint returned (see
    `tests/test_the_tracker_has_a_read_side.py::_jira_issue`)."""
    return {"id": "10071", "key": key, "fields": {
        "summary": key, "labels": [LABELS.get(key, "")], "assignee": None,
        "updated": "2026-08-05T15:07:22.794+0100", "resolution": None, "description": None,
        "status": {"name": TODO, "statusCategory": {"key": "new"}}}}


class _Site:
    """A Jira site holding `DAR-1` (labelled `of-api`) and `DAR-2` (labelled `of-web`).

    `scope`: the condition every search must be narrowed to — `""` for a project that declared
    none. `strict`: a search that is not narrowed to `scope` fails the test there and then; not
    strict, the site answers by the label it reads out of the JQL, and every ticket without one
    (which is what Jira does with `project = "DAR"`). `refuse`: every search answers 400."""

    def __init__(self, scope: str = "", *, strict: bool = True, refuse: bool = False) -> None:
        self.scope = scope
        self.strict = strict
        self.refuse = refuse
        #: the JQL of every search, in order, as parsed out of the request
        self.searches: list[str] = []
        self.requests: list[tuple[str, str]] = []

    def _jql_of(self, req) -> str:
        if req.get_method() == "GET":
            query = urllib.parse.urlsplit(req.full_url).query
            return urllib.parse.parse_qs(query)["jql"][0]
        return json.loads(req.data)["jql"]

    def _check(self, jql: str) -> None:
        if not self.strict:
            return
        if self.scope:
            narrowed = f'project = "{KEY}" AND ({self.scope})'
            if not (jql == narrowed or jql.startswith(narrowed + " ")):
                pytest.fail(f"a search was not narrowed to the project's scope: {jql!r}")
        elif jql != f'project = "{KEY}"' and not jql.startswith(f'project = "{KEY}" '):
            pytest.fail(f"a search does not start with the bare project clause: {jql!r}")

    def _slice(self, jql: str) -> list[str]:
        label = re.match(rf'project = "{KEY}" AND \(labels = "([^"]+)"\)', jql)
        return [k for k, lab in LABELS.items() if label is None or lab == label.group(1)]

    def urlopen(self, req, timeout=0):  # noqa: ARG002 — urllib's own signature
        method = req.get_method()
        # `/rest/api/3/<route>` or `/rest/agile/1.0/<route>`, the query string apart
        name, version, path = req.full_url.split("/rest/", 1)[1].split("/", 2)
        family, route = f"{name}/{version}", path.split("?", 1)[0]
        self.requests.append((method, route))
        if route == "search/jql":
            jql = self._jql_of(req)
            self.searches.append(jql)
            self._check(jql)
            if self.refuse:
                raise urllib.error.HTTPError(
                    req.full_url, 400, "Bad Request", hdrs=None,
                    fp=io.BytesIO(b'{"errorMessages":["Error in the JQL Query"]}'))
            keys = self._slice(jql)
            if method == "GET":                                   # the board
                return _Answer({"isLast": True, "issues": [_board_issue(k) for k in keys]})
            body = json.loads(req.data)
            if not body.get("nextPageToken"):                     # the tracker: two pages
                return _Answer({"isLast": False, "nextPageToken": "page-2",
                                "issues": [_list_issue(k) for k in keys[:1]]})
            return _Answer({"isLast": True, "issues": [_list_issue(k) for k in keys[1:]]})
        if (method, route) == ("GET", f"project/{KEY}"):
            return _Answer({"key": KEY, "name": "Dar"})
        if (method, family, route) == ("PUT", "agile/1.0", "issue/rank"):
            return _Answer(None)
        raise AssertionError(f"the adapter called {method} {route}, a route this site never had")


def _project(tmp_path, name: str = "api", **scope):
    """A Jira project as the registry holds one: `scope_jql` only when given."""
    from openfactory.contracts.project import Project, ProviderRef

    options = {"site": SITE, "email": "alice@acme.ai",
               "status_map": json.dumps({"todo": TODO}), **scope}
    return Project(name=name, repo_path=str(tmp_path / name),
                   tracker=ProviderRef(kind="jira", repo=KEY, options=options))


def _built(project):
    """The tracker and the board, built by the registry rows from the project's options."""
    from openfactory.adapters.board import build_board
    from openfactory.adapters.tracker.registry import build_tracker

    tracker, board = build_tracker(project, token="t"), build_board(project, token="t")
    assert type(tracker).__name__ == "JiraTracker" and type(board).__name__ == "JiraProjectBoard"
    return tracker, board


def _every_read(tracker, board) -> None:
    """Every read the Jira row makes of the project's issues, each kind once."""
    board.columns()
    board.items_in_status(TODO)
    board.place_after(issue="DAR-3", issue_url="", after=None, column=TODO)
    since = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    for state in ("all", "open", "closed"):
        tracker.list_tickets(state=state)
    tracker.list_tickets(updated_since=since)


@pytest.fixture
def site(monkeypatch):
    def install(scope: str = "", **how) -> _Site:
        jira = _Site(scope, **how)
        monkeypatch.setattr("urllib.request.urlopen", jira.urlopen)
        return jira
    return install


def test_the_scope_a_project_declares_reaches_its_jira_board_from_the_registry(site, tmp_path):
    """AC1: the option is read off the project's tracker options by the registry row and reaches
    the board the poller is handed. On main the registry dropped it: `project = "DAR" AND status =
    "A Fazer" ORDER BY Rank ASC`, the whole project."""
    jira = site(API)
    _tracker, board = _built(_project(tmp_path, scope_jql=API))

    board.items_in_status(TODO)

    assert jira.searches == [f'project = "{KEY}" AND ({API}) AND status = "{TODO}" '
                             f'ORDER BY Rank ASC']


@pytest.mark.parametrize("declared", [{}, {"scope_jql": "  "}], ids=["absent", "whitespace"])
def test_a_project_that_declares_no_scope_reads_its_jira_project_exactly_as_before(
        site, tmp_path, declared):
    """AC1, unset: the capability is optional, and a project that declares no scope — or only
    whitespace — sends today's JQL byte for byte (`board/jira.py` `columns` and `items_in_status`,
    `tracker/jira.py::list_tickets`'s join). Green on main by design: it pins those strings so the
    new code cannot change them (an empty scope emitting `AND ()` is the cut that turns it red)."""
    jira = site("")
    tracker, board = _built(_project(tmp_path, **declared))

    _every_read(tracker, board)

    bare = f'project = "{KEY}"'
    assert jira.searches[:3] == [f"{bare} ORDER BY Rank ASC",
                                 f'{bare} AND status = "{TODO}" ORDER BY Rank ASC',
                                 f'{bare} AND status = "{TODO}" ORDER BY Rank ASC']
    listed = jira.searches[3:]
    assert listed[0::2] == listed[1::2], "each page of one listing asks the same JQL"
    assert listed[0::2][:3] == [f"{bare} ORDER BY updated DESC",
                                f"{bare} AND statusCategory != Done ORDER BY updated DESC",
                                f"{bare} AND statusCategory = Done ORDER BY updated DESC"]
    assert re.fullmatch(rf'{re.escape(bare)} AND updated >= "-\d+m" ORDER BY updated DESC',
                        listed[6]), listed[6]


def test_every_read_the_jira_board_makes_carries_the_projects_scope(site, tmp_path):
    """AC2 and the issue's Test line: `columns`, `items_in_status`, `place_after` and
    `list_tickets` (all, open, closed, with `updated_since`, and on its second page) each send
    `project = "DAR" AND (<scope>)`. The strict site fails the test on the first search that does
    not. On main every one of them sent `project = "DAR"` alone."""
    jira = site(API)
    tracker, board = _built(_project(tmp_path, scope_jql=API))

    _every_read(tracker, board)

    # 3 board searches (place_after reads the column first) and 4 listings of two pages each: a
    # read that silently stopped searching must not be reported as scoped
    assert len(jira.searches) >= 11, jira.searches
    assert ("PUT", "issue/rank") in jira.requests, "place_after reached the rank it was asked for"


def test_a_project_polls_only_the_tickets_in_its_own_scope(site, tmp_path):
    """AC2, the effect the issue reports: two projects, `api` and `web`, on one Jira project. Each
    poller's pickup queue is its own slice. On main both read `["DAR-1", "DAR-2"]`, and each could
    claim the other's ticket — the one ticket three projects picked up in one night."""
    site(strict=False)
    _api_tracker, api = _built(_project(tmp_path, "api", scope_jql=API))
    _web_tracker, web = _built(_project(tmp_path, "web", scope_jql=WEB))

    assert (api.items_in_status(TODO), web.items_in_status(TODO)) == (["DAR-1"], ["DAR-2"])


def test_a_scope_with_an_OR_cannot_widen_the_read_past_the_project(site, tmp_path):
    """AC2, "ANDed" (Q2): the scope is wrapped in parentheses, so an OR inside it narrows within the
    project instead of escaping it — without them the read would be `project = "DAR" AND labels =
    "of-api" OR labels = "of-web"`, every `of-web` ticket on the whole site. `ORDER BY` stays last.
    On main no scope was sent at all."""
    either = f"{API} OR {WEB}"
    jira = site(either)
    tracker, board = _built(_project(tmp_path, scope_jql=either))

    _every_read(tracker, board)

    for jql in jira.searches:
        where, order, ordering = jql.rpartition(" ORDER BY ")
        assert order and "ORDER BY" not in where, jql
        assert ordering in ("Rank ASC", "updated DESC"), jql
        assert where.startswith(f'project = "{KEY}" AND ({API} OR {WEB})'), jql


def test_narrowing_the_board_read_costs_no_extra_request(site, tmp_path):
    """AC2, its cost (lesson 10): the scope rides inside the query the board already makes, so a
    scoped project asks the site exactly as many times as an unscoped one. On main the scope is
    missing from the counted requests, and the strict site fails the first of them."""
    bare = site("")
    _every_read(*_built(_project(tmp_path / "bare")))
    scoped = site(API)
    _every_read(*_built(_project(tmp_path / "scoped", scope_jql=API)))

    assert len(scoped.requests) == len(bare.requests), (scoped.requests, bare.requests)
    assert len(scoped.searches) == len(bare.searches) >= 11


def test_a_scope_jira_refuses_is_named_and_the_read_stays_unreadable(site, tmp_path, caplog):
    """Q3: a scope Jira cannot parse answers 400 (the existing "unreadable" branch). The warning
    names `scope_jql` and the condition, so the person reading it sees the cause, and the read is
    still unreadable — `None` from `columns` and `list_tickets` — never an empty board. On main the
    warnings said only "could not search DAR"."""
    broken = 'labels = "of-api'
    site(broken, strict=False, refuse=True)
    tracker, board = _built(_project(tmp_path, scope_jql=broken))

    with caplog.at_level(logging.WARNING):
        assert board.columns() is None
        assert tracker.list_tickets() is None

    said = [r.getMessage() for r in caplog.records
            if r.name in ("openfactory.board.jira", "openfactory.tracker.jira")]
    assert len([m for m in said if "scope_jql" in m and broken in m]) == 2, said
