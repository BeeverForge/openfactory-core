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
        #: every search request as sent: (method, full URL, body bytes)
        self.sent: list[tuple[str, str, bytes | None]] = []

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
            self.sent.append((method, req.full_url, req.data))
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


def test_a_scope_outside_ascii_reaches_jira_unchanged(site, tmp_path):
    """Environment variance: a pt-BR deployment labels its slices in its own words
    (`labels = "fábrica-api"`). The board's GET carries the scope percent-encoded — the URL stays
    ASCII, which `urllib` requires — and it decodes back to the same characters; the tracker's
    POST body carries it intact through JSON. On main no scope was sent, and the strict site fails
    the first search."""
    accented = 'labels = "fábrica-api"'
    jira = site(accented)
    tracker, board = _built(_project(tmp_path, scope_jql=accented))

    _every_read(tracker, board)

    gets = [url for method, url, _ in jira.sent if method == "GET"]
    posts = [body for method, _, body in jira.sent if method == "POST"]
    assert gets and posts, jira.sent
    for url in gets:
        assert url.isascii(), url
        jql = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["jql"][0]
        assert jql.startswith(f'project = "{KEY}" AND ({accented})'), jql
    for body in posts:
        assert json.loads(body)["jql"].startswith(f'project = "{KEY}" AND ({accented})'), body


def test_the_documented_scope_arrives_intact_from_a_registry_file(tmp_path):
    """Environment variance: a JQL condition quotes with `"`, so the documented example is
    single-quoted YAML. The Jira example of `docs/reference/configuration.md`, written into a
    registry file and read back by `ProjectRegistry`, reaches the tracker the registry row builds
    with its double quotes intact. On main the example had no `scope_jql` and the tracker no such
    attribute."""
    import textwrap
    from pathlib import Path

    import yaml

    from openfactory.adapters.tracker.registry import build_tracker
    from openfactory.registry import ProjectRegistry

    docs = Path(__file__).resolve().parents[1] / "docs" / "reference" / "configuration.md"
    blocks = re.findall(r"```yaml\n(.*?)```", docs.read_text(), flags=re.S)
    jira = [b for b in blocks if "kind: jira" in b]
    assert len(jira) == 1, f"one Jira example in the configuration reference, found {len(jira)}"
    entry = yaml.safe_load(textwrap.dedent(jira[0]))
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump(
        {"projects": {"api": {"name": "api", "repo_path": str(tmp_path / "api"), **entry}}}))

    tracker = build_tracker(ProjectRegistry(registry).get("api"), token="t")

    assert getattr(tracker, "scope_jql", None) == 'labels = "of-api"'


def test_a_card_outside_the_slice_is_not_read_as_never_taken_up(tmp_path, monkeypatch):
    """Under a scope, the edit/close/remove gate must not read another project's running card,
    which the by-key actions still reach, as a card nobody moved."""
    import json
    import re
    import urllib.parse

    from openfactory.actions.catalog import _stage_refusal
    from openfactory.adapters.board import build_board
    from openfactory.contracts.project import Project, ProviderRef

    where = {"DAR-1": ("of-api", "A Fazer"), "DAR-2": ("of-web", "Em andamento")}

    def urlopen(req, timeout=0):
        assert "search/jql" in req.full_url, req.full_url
        jql = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)["jql"][0]
        m = re.match(r'project = "DAR" AND \(labels = "([^"]+)"\)', jql)
        keys = [k for k, (lab, _) in where.items() if m is None or lab == m.group(1)]
        return _Answer({"isLast": True, "issues": [
            {"key": k, "fields": {"status": {"name": where[k][1]}}} for k in keys]})

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    sm = {"backlog": "Backlog", "todo": "A Fazer", "in_progress": "Em andamento", "done": "Concluído"}
    api = Project(name="api", repo_path=str(tmp_path / "api"), tracker=ProviderRef(
        kind="jira", repo="DAR", options={"site": SITE, "email": "a@b.c",
                                          "status_map": json.dumps(sm), "scope_jql": API}))
    board = build_board(api, token="t")
    for act in ("edit", "close", "remove"):
        assert _stage_refusal(api, board, "DAR-2", act=act), act


def _gate(project, board, ref: str) -> dict[str, str]:
    """What the edit/close/remove gate answers for `ref`, per act."""
    from openfactory.actions.catalog import _stage_refusal

    return {act: _stage_refusal(project, board, ref, act=act)
            for act in ("edit", "close", "remove")}


def test_a_card_outside_the_slice_is_refused_by_name_naming_the_scope(site, tmp_path):
    """Review round 1, point 1 (Q6): the refusal says why — the card is not in this project's
    slice, which scope, and where to act instead — and costs the gate one search beyond
    `columns()`. At 5e70d47 the gate answered `''` to all three acts."""
    jira = site(API)
    project = _project(tmp_path, scope_jql=API)
    _, board = _built(project)

    said = _gate(project, board, "DAR-2")

    for act, sentence in said.items():
        assert "DAR-2 is not in api's slice" in sentence, (act, sentence)
        assert f"(within scope_jql {API!r})" in sentence, (act, sentence)
        assert ("if it is another project's, act on it from there; if it is api's own, put it in "
                "the scope and try again") in sentence, (act, sentence)
    assert jira.searches[:2] == [f'project = "{KEY}" AND ({API}) ORDER BY Rank ASC',
                                 f'project = "{KEY}" AND ({API}) AND key = "DAR-2"'], jira.searches
    assert len(jira.searches) == 2 * len(said), jira.searches


def test_a_slice_that_cannot_be_asked_about_a_card_refuses_as_unreadable(site, tmp_path,
                                                                         monkeypatch):
    """Lesson 2, for the gate: when the search that asks whether a card is in the slice is refused,
    the gate cannot tell, and says so as it does of an unreadable board — it never reads a search
    it could not make as "nobody moved it". At 5e70d47 the gate answered `''`."""
    jira = site(API)
    answer = jira.urlopen

    def refuse_the_key_search(req, timeout=0):
        if req.get_method() == "GET" and " AND key = " in jira._jql_of(req):
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", hdrs=None,
                                         fp=io.BytesIO(b'{"errorMessages":["x"]}'))
        return answer(req, timeout)

    monkeypatch.setattr("urllib.request.urlopen", refuse_the_key_search)
    project = _project(tmp_path, scope_jql=API)
    _, board = _built(project)

    for act, sentence in _gate(project, board, "DAR-2").items():
        assert "api's board could not be read" in sentence, (act, sentence)


def test_an_unscoped_jira_boards_gate_asks_nothing_more(site, tmp_path):
    """Lesson 10: a project that declares no scope owns every card of its Jira project, so the gate
    asks no question of a card `columns()` did not return — one search per act, as before. Green at
    5e70d47 by design; the mutation cut that makes `holds` search without a scope turns it red."""
    jira = site("")
    project = _project(tmp_path)
    _, board = _built(project)

    assert _gate(project, board, "DAR-7") == {"edit": "", "close": "", "remove": ""}
    assert jira.searches == [f'project = "{KEY}" ORDER BY Rank ASC'] * 3, jira.searches


def test_another_projects_running_card_is_not_queued_from_this_one(tmp_path, monkeypatch):
    """`ProductModule.promote` hands the door the board it read (`columns=board.columns()`), and
    under a scope that read leaves out another project's card, which the queueing move still
    reaches by key. Such a card must not read as one no board places: queueing web's running card
    from api puts it back in web's queue, and web's poller takes it a second time."""
    import json
    import re
    import urllib.parse

    from openfactory.adapters.board import build_board
    from openfactory.adapters.tracker.registry import build_tracker
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.product.config import ProductLink
    from openfactory.product.loader import ProductContext
    from openfactory.product.module import ProductModule
    from openfactory.product.voice import board_move_said
    from tests.test_card_maintenance import COMMIT, REQUIREMENTS_DIR, _corpus, _Harness

    where = {"DAR-1": ("of-api", "Backlog"), "DAR-2": ("of-web", "Em andamento")}
    moved: list[str] = []

    def urlopen(req, timeout=0):
        split = urllib.parse.urlsplit(req.full_url)
        if "search/jql" in split.path:
            jql = (urllib.parse.parse_qs(split.query)["jql"][0] if req.get_method() == "GET"
                   else json.loads(req.data)["jql"])
            label = re.search(r'labels = "([^"]+)"', jql)
            key = re.search(r'key = "([^"]+)"', jql)
            keys = [k for k, (lab, _) in where.items()
                    if (label is None or lab == label.group(1)) and (key is None or k == key.group(1))]
            return _Answer({"isLast": True, "issues": [
                {"key": k, "fields": {"status": {"name": where[k][1]}}} for k in keys]})
        issue = re.search(r"issue/(DAR-\d+)(/transitions)?$", split.path)
        if issue is None:
            return _Answer({})
        if issue.group(2) and req.get_method() == "POST":
            moved.append(issue.group(1))
            return _Answer({})
        if issue.group(2):
            return _Answer({"transitions": [{"id": "11", "name": "A Fazer",
                                             "to": {"name": "A Fazer"}}]})
        lab, status = where[issue.group(1)]
        return _Answer({"key": issue.group(1), "fields": {
            "summary": "web's card", "description": None, "labels": [lab],
            "status": {"name": status, "statusCategory": {"key": "indeterminate"}}}})

    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(tmp_path / "metrics.db"))
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    sm = {"backlog": "Backlog", "todo": "A Fazer", "in_progress": "Em andamento", "done": "Concluído"}
    api = Project(name="api", repo_path=str(tmp_path), tracker=ProviderRef(
        kind="jira", repo="DAR", options={"site": SITE, "email": "a@b.c",
                                          "status_map": json.dumps(sm), "scope_jql": API}),
        product=ProductConfig(docs_repo="acme/acme-docs", admins=["ana"], agent_name="Nina"))
    ctx = ProductContext(link=ProductLink(active=True, docs_repo="acme/acme-docs", kind="ok",
                                          reason="fine"),
                         corpus=_corpus(), docs_path=str(tmp_path), docs_commit=COMMIT,
                         requirements_dir=REQUIREMENTS_DIR)
    module = ProductModule(api, context=ctx, agent=_Harness("{}"),
                           tracker=build_tracker(api, token="t"), board=build_board(api, token="t"))

    [result] = module.promote(["DAR-2"], actor="ana")

    assert not result.ok, "another project's running card was queued from this one"
    assert "DAR-2" in result.detail and "api" in result.detail, result.detail
    assert moved == []
    assert board_move_said("outside_the_slice", ref="DAR-2", project="api", language="pt-BR").count("api") == 3


def test_a_slice_that_cannot_be_asked_about_a_card_refuses_to_queue_it(tmp_path, monkeypatch):
    """`promote` asks `holds` about a card its board read did not return, and a slice that could
    not be asked (`None`) must refuse as an unreachable board, as `_stage` does — never read as
    "inside": the door then sees a card no board places, which `PROMOTED` allows, and the move
    reaches another project's running card by key."""
    from openfactory.adapters.board import build_board
    from openfactory.adapters.tracker.registry import build_tracker
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.product.config import ProductLink
    from openfactory.product.loader import ProductContext
    from openfactory.product.module import ProductModule
    from openfactory.product.voice import board_move_said
    from tests.test_card_maintenance import COMMIT, REQUIREMENTS_DIR, _corpus, _Harness

    where = {"DAR-1": ("of-api", "Backlog"), "DAR-2": ("of-web", "Em andamento")}
    moved: list[str] = []

    def urlopen(req, timeout=0):
        split = urllib.parse.urlsplit(req.full_url)
        if "search/jql" in split.path:
            jql = (urllib.parse.parse_qs(split.query)["jql"][0] if req.get_method() == "GET"
                   else json.loads(req.data)["jql"])
            if "key = " in jql:
                raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", hdrs=None,
                                             fp=io.BytesIO(b'{"errorMessages":["x"]}'))
            label = re.search(r'labels = "([^"]+)"', jql)
            keys = [k for k, (lab, _) in where.items() if label is None or lab == label.group(1)]
            return _Answer({"isLast": True, "issues": [
                {"key": k, "fields": {"status": {"name": where[k][1]}}} for k in keys]})
        issue = re.search(r"issue/(DAR-\d+)(/transitions)?$", split.path)
        if issue is None:
            return _Answer({})
        if issue.group(2) and req.get_method() == "POST":
            moved.append(issue.group(1))
            return _Answer({})
        if issue.group(2):
            return _Answer({"transitions": [{"id": "11", "name": "A Fazer",
                                             "to": {"name": "A Fazer"}}]})
        lab, status = where[issue.group(1)]
        return _Answer({"key": issue.group(1), "fields": {
            "summary": "web's card", "description": None, "labels": [lab],
            "status": {"name": status, "statusCategory": {"key": "indeterminate"}}}})

    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(tmp_path / "metrics.db"))
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    sm = {"backlog": "Backlog", "todo": "A Fazer", "in_progress": "Em andamento", "done": "Concluído"}
    api = Project(name="api", repo_path=str(tmp_path), tracker=ProviderRef(
        kind="jira", repo="DAR", options={"site": SITE, "email": "a@b.c",
                                          "status_map": json.dumps(sm), "scope_jql": API}),
        product=ProductConfig(docs_repo="acme/acme-docs", admins=["ana"], agent_name="Nina"))
    ctx = ProductContext(link=ProductLink(active=True, docs_repo="acme/acme-docs", kind="ok",
                                          reason="fine"),
                         corpus=_corpus(), docs_path=str(tmp_path), docs_commit=COMMIT,
                         requirements_dir=REQUIREMENTS_DIR)
    module = ProductModule(api, context=ctx, agent=_Harness("{}"),
                           tracker=build_tracker(api, token="t"), board=build_board(api, token="t"))

    [result] = module.promote(["DAR-2"], actor="ana")

    assert not result.ok, "a card the slice could not be asked about was queued"
    assert result.detail == board_move_said("unreachable", ref="DAR-2"), result.detail
    assert moved == []


def test_a_board_read_refused_once_does_not_queue_another_projects_card(tmp_path, monkeypatch):
    """`promote` asks `holds` only about a card its batch read did not return. When that read is
    refused (a 429 among many pollers on one site), the door reads the board again, and if Jira
    answers then, another project's running card reads as one no board places and is queued."""
    from openfactory.adapters.board import build_board
    from openfactory.adapters.tracker.registry import build_tracker
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.product.config import ProductLink
    from openfactory.product.loader import ProductContext
    from openfactory.product.module import ProductModule
    from tests.test_card_maintenance import COMMIT, REQUIREMENTS_DIR, _corpus, _Harness

    where = {"DAR-1": ("of-api", "Backlog"), "DAR-2": ("of-web", "Em andamento")}
    moved: list[str] = []
    refused: list[str] = []

    def urlopen(req, timeout=0):
        split = urllib.parse.urlsplit(req.full_url)
        if "search/jql" in split.path:
            jql = (urllib.parse.parse_qs(split.query)["jql"][0] if req.get_method() == "GET"
                   else json.loads(req.data)["jql"])
            if jql.endswith("ORDER BY Rank ASC") and " status = " not in jql and not refused:
                refused.append(jql)
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", hdrs=None,
                                             fp=io.BytesIO(b'{"errorMessages":["x"]}'))
            label = re.search(r'labels = "([^"]+)"', jql)
            key = re.search(r'key = "([^"]+)"', jql)
            keys = [k for k, (lab, _) in where.items()
                    if (label is None or lab == label.group(1)) and (key is None or k == key.group(1))]
            return _Answer({"isLast": True, "issues": [
                {"key": k, "fields": {"status": {"name": where[k][1]}}} for k in keys]})
        issue = re.search(r"issue/(DAR-\d+)(/transitions)?$", split.path)
        if issue is None:
            return _Answer({})
        if issue.group(2) and req.get_method() == "POST":
            moved.append(issue.group(1))
            return _Answer({})
        if issue.group(2):
            return _Answer({"transitions": [{"id": "11", "name": "A Fazer",
                                             "to": {"name": "A Fazer"}}]})
        lab, status = where[issue.group(1)]
        return _Answer({"key": issue.group(1), "fields": {
            "summary": "web's card", "description": None, "labels": [lab],
            "status": {"name": status, "statusCategory": {"key": "indeterminate"}}}})

    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(tmp_path / "metrics.db"))
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    sm = {"backlog": "Backlog", "todo": "A Fazer", "in_progress": "Em andamento", "done": "Concluído"}
    api = Project(name="api", repo_path=str(tmp_path), tracker=ProviderRef(
        kind="jira", repo="DAR", options={"site": SITE, "email": "a@b.c",
                                          "status_map": json.dumps(sm), "scope_jql": API}),
        product=ProductConfig(docs_repo="acme/acme-docs", admins=["ana"], agent_name="Nina"))
    ctx = ProductContext(link=ProductLink(active=True, docs_repo="acme/acme-docs", kind="ok",
                                          reason="fine"),
                         corpus=_corpus(), docs_path=str(tmp_path), docs_commit=COMMIT,
                         requirements_dir=REQUIREMENTS_DIR)
    module = ProductModule(api, context=ctx, agent=_Harness("{}"),
                           tracker=build_tracker(api, token="t"), board=build_board(api, token="t"))

    [result] = module.promote(["DAR-2"], actor="ana")

    assert refused, "the fake never refused the batch's board read"
    assert not result.ok, "another project's running card was queued after one refused read"
    assert moved == []


def test_an_empty_slice_does_not_queue_another_projects_card(tmp_path, monkeypatch):
    """A newly scoped project starts with an empty slice: the batch's read answers `{}`, and every
    card is one it did not return, so each is asked about (`holds`) — an empty answer is a read,
    not a refused one. Green at 3c7fbcf; the cut `where is not None and …` → `where and …` (review
    of PR #884, point 6) skips the question on `{}`, and the door queues web's running card."""
    from openfactory.adapters.board import build_board
    from openfactory.adapters.tracker.registry import build_tracker
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.product.config import ProductLink
    from openfactory.product.loader import ProductContext
    from openfactory.product.module import ProductModule
    from openfactory.product.voice import board_move_said
    from tests.test_card_maintenance import COMMIT, REQUIREMENTS_DIR, _corpus, _Harness

    where = {"DAR-2": ("of-web", "Em andamento")}  # nothing on the site carries `of-api` yet
    moved: list[str] = []
    asked: list[str] = []

    def urlopen(req, timeout=0):
        split = urllib.parse.urlsplit(req.full_url)
        if "search/jql" in split.path:
            jql = (urllib.parse.parse_qs(split.query)["jql"][0] if req.get_method() == "GET"
                   else json.loads(req.data)["jql"])
            asked.append(jql)
            label = re.search(r'labels = "([^"]+)"', jql)
            key = re.search(r'key = "([^"]+)"', jql)
            keys = [k for k, (lab, _) in where.items()
                    if (label is None or lab == label.group(1)) and (key is None or k == key.group(1))]
            return _Answer({"isLast": True, "issues": [
                {"key": k, "fields": {"status": {"name": where[k][1]}}} for k in keys]})
        issue = re.search(r"issue/(DAR-\d+)(/transitions)?$", split.path)
        if issue is None:
            return _Answer({})
        if issue.group(2) and req.get_method() == "POST":
            moved.append(issue.group(1))
            return _Answer({})
        if issue.group(2):
            return _Answer({"transitions": [{"id": "11", "name": "A Fazer",
                                             "to": {"name": "A Fazer"}}]})
        lab, status = where[issue.group(1)]
        return _Answer({"key": issue.group(1), "fields": {
            "summary": "web's card", "description": None, "labels": [lab],
            "status": {"name": status, "statusCategory": {"key": "indeterminate"}}}})

    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(tmp_path / "metrics.db"))
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    sm = {"backlog": "Backlog", "todo": "A Fazer", "in_progress": "Em andamento", "done": "Concluído"}
    api = Project(name="api", repo_path=str(tmp_path), tracker=ProviderRef(
        kind="jira", repo="DAR", options={"site": SITE, "email": "a@b.c",
                                          "status_map": json.dumps(sm), "scope_jql": API}),
        product=ProductConfig(docs_repo="acme/acme-docs", admins=["ana"], agent_name="Nina"))
    ctx = ProductContext(link=ProductLink(active=True, docs_repo="acme/acme-docs", kind="ok",
                                          reason="fine"),
                         corpus=_corpus(), docs_path=str(tmp_path), docs_commit=COMMIT,
                         requirements_dir=REQUIREMENTS_DIR)
    module = ProductModule(api, context=ctx, agent=_Harness("{}"),
                           tracker=build_tracker(api, token="t"), board=build_board(api, token="t"))

    [result] = module.promote(["DAR-2"], actor="ana")

    assert f'project = "{KEY}" AND ({API}) AND key = "DAR-2"' in asked, asked
    assert not result.ok, "another project's running card was queued from an empty slice"
    assert result.detail == board_move_said("outside_the_slice", ref="DAR-2", project="api"), \
        result.detail
    assert moved == []


def _api_product_module(tmp_path, monkeypatch, urlopen, *, scope: str = API, language=None):
    """The product role of `api` on the shared Jira project `DAR`, scoped to `scope` (none when
    `""`), with `urlopen` as the only network it has."""
    from openfactory.adapters.board import build_board
    from openfactory.adapters.tracker.registry import build_tracker
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.product.config import ProductLink
    from openfactory.product.loader import ProductContext
    from openfactory.product.module import ProductModule
    from tests.test_card_maintenance import COMMIT, REQUIREMENTS_DIR, _corpus, _Harness

    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(tmp_path / "metrics.db"))
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    sm = {"backlog": "Backlog", "todo": "A Fazer", "in_progress": "Em andamento", "done": "Concluído"}
    options = {"site": SITE, "email": "a@b.c", "status_map": json.dumps(sm)}
    if scope:
        options["scope_jql"] = scope
    extra = {"language": language} if language else {}
    api = Project(name="api", repo_path=str(tmp_path), tracker=ProviderRef(
        kind="jira", repo="DAR", options=options),
        product=ProductConfig(docs_repo="acme/acme-docs", admins=["ana"], agent_name="Nina"),
        **extra)
    ctx = ProductContext(link=ProductLink(active=True, docs_repo="acme/acme-docs", kind="ok",
                                          reason="fine"),
                         corpus=_corpus(), docs_path=str(tmp_path), docs_commit=COMMIT,
                         requirements_dir=REQUIREMENTS_DIR)
    return ProductModule(api, context=ctx, agent=_Harness("{}"),
                         tracker=build_tracker(api, token="t"), board=build_board(api, token="t"))


class _RankSite:
    """`DAR-1` (`of-api`) in the backlog, `DAR-2` (`of-web`) running: the searches answer by the
    label and the key they read out of the JQL; every rank written is kept in `ranked`."""

    def __init__(self) -> None:
        self.where = {"DAR-1": ("of-api", "Backlog"), "DAR-2": ("of-web", "Em andamento")}
        self.searches: list[str] = []
        self.ranked: list[dict] = []

    def urlopen(self, req, timeout=0):
        split = urllib.parse.urlsplit(req.full_url)
        if "search/jql" in split.path:
            jql = (urllib.parse.parse_qs(split.query)["jql"][0] if req.get_method() == "GET"
                   else json.loads(req.data)["jql"])
            self.searches.append(jql)
            label = re.search(r'labels = "([^"]+)"', jql)
            key = re.search(r'key = "([^"]+)"', jql)
            status = re.search(r'status = "([^"]+)"', jql)
            keys = [k for k, (lab, st) in self.where.items()
                    if (label is None or lab == label.group(1))
                    and (key is None or k == key.group(1))
                    and (status is None or st == status.group(1))]
            return _Answer({"isLast": True, "issues": [
                {"key": k, "fields": {"status": {"name": self.where[k][1]}}} for k in keys]})
        if split.path.endswith("issue/rank"):
            self.ranked.append(json.loads(req.data))
            return _Answer(None)
        return _Answer({})


def test_another_projects_card_is_not_ranked_from_this_one(tmp_path, monkeypatch):
    """The product role's `reorder` ranks by key (`place_after` → the Agile API's `issue/rank`),
    so under a scope it reached another project's card: at 3c7fbcf `reorder(["DAR-1", "DAR-2"])`
    from `api` ranked web's running `DAR-2` after `DAR-1`, ok=True (review of PR #884, point 3).
    The card outside the slice is now refused by name, as the queueing refuses it."""
    from openfactory.product.voice import board_move_said

    site = _RankSite()
    module = _api_product_module(tmp_path, monkeypatch, site.urlopen)

    ours, theirs = module.reorder(["DAR-1", "DAR-2"], actor="ana")

    assert ours.ok, ours
    assert not theirs.ok, "another project's card was ranked from this one"
    assert theirs.detail == board_move_said("outside_the_slice", ref="DAR-2", project="api"), \
        theirs.detail
    assert [r for r in site.ranked if "DAR-2" in r["issues"]] == [], site.ranked


def test_an_unscoped_order_asks_the_slice_nothing(tmp_path, monkeypatch):
    """Lesson 10: a project that declares no scope owns every card of its Jira project, so the
    order asks no question of any card — the only search is the column's first card. Green before
    the guard by design; the cut that makes `holds` search without a scope turns it red."""
    site = _RankSite()
    module = _api_product_module(tmp_path, monkeypatch, site.urlopen, scope="")

    results = module.reorder(["DAR-1", "DAR-2"], actor="ana")

    assert [r.ok for r in results] == [True, True], results
    assert [jql for jql in site.searches if " key = " in jql] == [], site.searches


def test_a_slice_that_cannot_be_asked_about_a_card_refuses_to_rank_it(tmp_path, monkeypatch):
    """Lesson 2, for the order: a `key =` search Jira refuses is "could not see", never "inside" —
    the card is refused as an unreachable board, and nothing is ranked."""
    from openfactory.product.voice import board_move_said

    site = _RankSite()
    answer = site.urlopen

    def refuse_the_key_search(req, timeout=0):
        split = urllib.parse.urlsplit(req.full_url)
        if "search/jql" in split.path and " key = " in urllib.parse.parse_qs(split.query)["jql"][0]:
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", hdrs=None,
                                         fp=io.BytesIO(b'{"errorMessages":["x"]}'))
        return answer(req, timeout)

    module = _api_product_module(tmp_path, monkeypatch, refuse_the_key_search)

    [result] = module.reorder(["DAR-2"], actor="ana")

    assert not result.ok, "a card the slice could not be asked about was ranked"
    assert result.detail == board_move_said("unreachable", ref="DAR-2"), result.detail
    assert site.ranked == []


def _withdrawn(project, board, ref: str, monkeypatch) -> dict[str, str]:
    """What the product view's close and remove answer for `ref` (`_withdraw_refusal`, the gate
    `product_withdraw_card` asks), with the engine saying no job is on any card."""
    import asyncio

    from openfactory.actions import catalog

    async def no_job(project, issue):
        return catalog._JobOnTheCard()

    monkeypatch.setattr(catalog, "_job_on_the_card", no_job)
    return {act: asyncio.run(catalog._withdraw_refusal(project, board, ref,
                                                        remove=act == "remove"))[1]
            for act in ("close", "remove")}


def test_the_product_views_refusal_of_a_card_outside_the_slice_speaks_the_projects_language(
        site, tmp_path, monkeypatch):
    """The product view's close and remove reach the gate's refusal through `_withdraw_refusal`,
    and at 3c7fbcf a pt-BR project read it in English — "DAR-2 is not in api's slice …" — while
    the queueing's refusal of the same card was in Portuguese (review of PR #884, point 4)."""
    site(API)
    project = _project(tmp_path, scope_jql=API).model_copy(update={"language": "pt-BR"})
    _, board = _built(project)

    for act, sentence in _withdrawn(project, board, "DAR-2", monkeypatch).items():
        assert sentence.startswith("O DAR-2 não está na fatia do quadro de api"), (act, sentence)
        assert f"(within scope_jql {API!r})" in sentence, (act, sentence)
        assert sentence.count("api") == 3 + API.count("api"), (act, sentence)
