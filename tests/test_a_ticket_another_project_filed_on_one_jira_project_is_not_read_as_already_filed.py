"""A ticket outside a project's slice of a shared Jira project is not read as already filed (#752).

THE RULE THIS HOLDS. `JiraTracker.find_ticket` is the factory's "is it already filed?" check: the
impediment filer (`ops.impediment._open`), the product role's filings and the splitter's
find-or-create each ask it before they create, and reuse whatever key it answers. Under a
`scope_jql`, several registry projects share one Jira project. Unscoped, the search answered an
open issue with that exact summary anywhere in the Jira project, so a project could read a ticket
outside its own slice as its own earlier filing, and attach its work to it instead of filing. The
issue asks for the search to be scoped like every board read (#752, against v0.6.0-rc.2).

What scoping costs is in `docs/reference/configuration.md`: a ticket the factory creates must
match the scope, or the scoped search cannot find it again (the human's answer to Q1, 2026-10-19).

MEASURED ON `main` (1be1835) WITH THIS FILE: both tests fail. The search carried no scope, and
`_open` answered `DAR-9`, the ticket outside the slice.

WHAT IS DRIVEN HERE is the real `JiraTracker`, built by `build_tracker` from a project's tracker
options as the registry holds them, against a fake at `urllib.request.urlopen`. The fake reads the
JQL by `json.loads` of the request body. It answers the open issue with the asked summary only to
a search that is not narrowed to the scope, which is what Jira does: that issue is not in the
slice.
"""

from __future__ import annotations

import json
import re

KEY = "DAR"
SITE = "https://acme-team.atlassian.net"
SCOPE = 'labels = "of-api"'
#: the open issue outside the `of-api` slice, under every summary it is asked for
OUTSIDE = "DAR-9"


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
    """A Jira site whose slice `labels = "of-api"` holds no open issue, and whose project outside
    it holds `DAR-9` under whatever summary a search asks for."""

    def __init__(self) -> None:
        #: the JQL of every search, in order, as parsed out of the request body
        self.searches: list[str] = []

    def urlopen(self, req, timeout=0):  # noqa: ARG002 — urllib's own signature
        route = req.full_url.split("/rest/api/3/", 1)[1]
        if (req.get_method(), route) != ("POST", "search/jql"):
            raise AssertionError(f"the adapter called {req.get_method()} {route}, "
                                 "a route this site never had")
        jql = json.loads(req.data)["jql"]
        self.searches.append(jql)
        if jql.startswith(f'project = "{KEY}" AND ({SCOPE}) '):
            return _Answer({"isLast": True, "issues": []})
        asked = re.search(r'summary ~ "\\"(.*)\\""', jql)
        summary = asked.group(1).replace('\\"', '"').replace("\\\\", "\\") if asked else ""
        return _Answer({"isLast": True,
                        "issues": [{"key": OUTSIDE, "fields": {"summary": summary}}]})


def _scoped_tracker(tmp_path, monkeypatch):
    from openfactory.adapters.tracker.registry import build_tracker
    from openfactory.contracts.project import Project, ProviderRef

    site = _Site()
    monkeypatch.setattr("urllib.request.urlopen", site.urlopen)
    project = Project(name="api", repo_path=str(tmp_path / "api"), tracker=ProviderRef(
        kind="jira", repo=KEY,
        options={"site": SITE, "email": "alice@acme.ai", "scope_jql": SCOPE}))
    tracker = build_tracker(project, token="t")
    assert type(tracker).__name__ == "JiraTracker"
    return tracker, site


def test_find_ticket_asks_only_within_the_projects_scope(tmp_path, monkeypatch):
    """AC3: the one search `find_ticket` makes is `project = "DAR" AND (<scope>)`, then the open
    and summary clauses, the title still escaped. On main it was `project = "DAR" AND
    statusCategory != Done AND …`, and it answered `DAR-9`."""
    tracker, site = _scoped_tracker(tmp_path, monkeypatch)

    assert tracker.find_ticket(title='Corrigir "extrato" conciliado') is None

    assert site.searches == [f'project = "{KEY}" AND ({SCOPE}) AND statusCategory != Done '
                             'AND summary ~ "\\"Corrigir \\"extrato\\" conciliado\\""']


def test_an_impediment_another_project_filed_is_not_this_projects_open_one(tmp_path, monkeypatch):
    """AC3, through its caller: the impediment filer asks `find_ticket` under every spelling of
    the title (`_open`) and reuses what it answers. Within the slice there is none, so it answers
    `None` and the project files its own. On main it answered `DAR-9`, the ticket outside."""
    from openfactory.ops import impediment

    tracker, site = _scoped_tracker(tmp_path, monkeypatch)

    assert impediment._open(tracker, "api", impediment.PRODUCT_BOARD_UNREADABLE) is None

    assert len(site.searches) == len(impediment._spellings("api", impediment.PRODUCT_BOARD_UNREADABLE))
    assert all(jql.startswith(f'project = "{KEY}" AND ({SCOPE}) ') for jql in site.searches), \
        site.searches
