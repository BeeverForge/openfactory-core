"""The API a front end needs is described and pinned as an API (#561, slice 1).

Decided on 2026-10-08 for 0.6.0: the core's API does not depend on any front end, and the panel is
the DEFAULT front end, using "the same documented API any other front end would. Nothing in it is
private to the core." The API was not documented anywhere a screen of one's own could start from:
FastAPI's own description named the HTTP routes, and not the credentials, the areas, the refusals
or the streams.

`docs/reference/the-front-end-api.md` is the contract, and this file pins it to the code:

  - every route under `/api/` is a row of its table, in its area, and every row is a route;
  - every address the default front end calls is a route of the contract;
  - the three ways to present a credential, and the 401 and 403 the table promises, are exercised
    without the page;
  - the streams' frames and endings are the ones the code sends.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "reference" / "the-front-end-api.md"
PAGE = ROOT / "openfactory" / "api" / "panel.html"
AREA = {"floor": "floor", "product": "product", None: "every credential"}


def _contract_text() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def _rows() -> dict[tuple[str, str], str]:
    """`(method, path) → area` as the contract's table states them."""
    table = _contract_text().split("<!-- routes:start -->")[1].split("<!-- routes:end -->")[0]
    rows = {}
    for line in table.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[1].startswith("`/api/"):
            rows[(cells[0], cells[1].strip("`"))] = cells[2]
    return rows


def _routes() -> dict[tuple[str, str], str]:
    """`(method, path) → area` as the app serves them, the area read by the gate's own rule."""
    from openfactory.api.app import _scope_of_path, app

    routes = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/"):
            continue
        methods = (["WS"] if isinstance(route, APIWebSocketRoute)
                   else sorted(route.methods or []) if isinstance(route, APIRoute) else [])
        for method in methods:
            routes[(method, path)] = AREA[_scope_of_path(re.sub(r"\{[^}]+\}", "x", path))]
    return routes


def _reaches(called: str, route: str) -> bool:
    """Whether an address the page writes can be `route`, segment by segment: a `${…}` the page
    fills (`x`) may be any segment — `/api/preview/x/x/x` is the start, stop and rebuild of one
    preview — and a route's `{parameter}` any segment the page writes; `{…:path}` takes the rest."""
    mine, theirs = called.strip("/").split("/"), route.strip("/").split("/")
    for n, segment in enumerate(theirs):
        if segment.endswith(":path}"):
            return len(mine) > n
        if n >= len(mine) or not (mine[n] == "x" or segment.startswith("{")
                                  or mine[n] == segment):
            return False
    return len(mine) == len(theirs)


def _called_by_the_page() -> set[str]:
    """Every `/api/...` address the default front end writes in its code — comments left out, a
    `${…}` read as one segment, the query dropped."""
    code = re.sub(r"/\*.*?\*/|<!--.*?-->", "", PAGE.read_text(encoding="utf-8"), flags=re.S)
    code = "\n".join(line for line in code.splitlines() if not line.strip().startswith("//"))
    called = set()
    for found in re.finditer(r"(['\"`])(/api/(?:(?!\1).)*?)\1", code):
        called.add(re.sub(r"\$\{[^}]*\}", "x", found.group(2)).split("?")[0])
    return called


# ── the table ───────────────────────────────────────────────────────────────────────────────────

def test_every_route_is_a_row_of_the_contract_and_every_row_is_a_route():
    rows, routes = _rows(), _routes()

    assert set(routes) - set(rows) == set(), "routes the contract does not list"
    assert set(rows) - set(routes) == set(), "rows of the contract that are no route"


def test_every_row_states_the_area_the_gate_reads():
    rows = _rows()
    for key, area in _routes().items():
        assert rows[key].startswith(area), (key, rows[key], area)


def test_the_default_front_end_calls_only_the_contract():
    """NOTHING IN IT IS PRIVATE TO THE CORE. An address the page calls that the contract does not
    list is either a route the contract forgot or one the page reaches past it. An address that
    ends in `/` is the start of one the page concatenates, and must start a route."""
    paths = {path for _method, path in _rows()}
    for called in sorted(_called_by_the_page()):
        if called.endswith("/"):
            assert any(p.startswith(called) for p in paths), called
        else:
            assert any(_reaches(called, p) for p in paths), called


# ── credentials and refusals ────────────────────────────────────────────────────────────────────

@pytest.fixture
def gated(monkeypatch):
    for var in ("OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_PRODUCT_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", "the-operator")
    monkeypatch.setenv("OPENFACTORY_PRODUCT_TOKENS", "the-analyst:bia")
    from openfactory.api.app import app

    return TestClient(app)


def test_a_credential_is_read_from_the_header_the_cookie_and_the_query(gated):
    assert gated.get("/api/whoami",
                     headers={"Authorization": "Bearer the-operator"}).status_code == 200
    gated.cookies.set("openfactory_token", "the-operator")
    assert gated.get("/api/whoami").status_code == 200
    gated.cookies.clear()
    assert gated.get("/api/whoami?token=the-operator").status_code == 200


def test_no_credential_is_the_401_the_contract_names(gated):
    answer = gated.get("/api/projects")

    assert answer.status_code == 401 and answer.json()["detail"] == "unauthorized"


def test_a_credential_outside_its_area_is_the_403_the_contract_names(gated):
    floor = gated.get("/api/projects", headers={"Authorization": "Bearer the-analyst"})
    whoami = gated.get("/api/whoami", headers={"Authorization": "Bearer the-analyst"})

    assert floor.status_code == 403
    assert floor.json()["detail"].startswith("this credential is scoped to product"), floor.json()
    assert whoami.status_code == 200, "whoami is every credential's"


# ── the streams ─────────────────────────────────────────────────────────────────────────────────

def test_the_streams_frames_and_endings_are_the_ones_the_code_sends():
    from openfactory.api import app as api

    said = _contract_text().split("## 4. Streams")[1].split("## 5.")[0]
    chat = (ROOT / "openfactory" / "api" / "product_chat.py").read_text(encoding="utf-8")
    for kind in sorted(set(re.findall(r'"kind": "(\w+)"', chat))):
        assert f"`{kind}`" in said, f"the product chat sends `{kind}` and the contract omits it"
    for kind in ("hello", "update", "bye"):
        assert f'"kind": "{kind}"' in Path(api.__file__).read_text(encoding="utf-8"), kind
        assert f"`{kind}`" in said, kind
    for why in (*api._ENDED_WHY.values(), api._ENDED_UNAVAILABLE, api.STREAM_ENDED_EVENT):
        assert f"`{why}`" in said, why
    assert "1008" in said and "1011" in said


def test_the_api_describes_its_own_http_routes(monkeypatch):
    monkeypatch.delenv("OPENFACTORY_PANEL_TOKEN", raising=False)
    from openfactory.api.app import app

    described = TestClient(app).get("/openapi.json").json()["paths"]
    for method, path in _rows():
        if method != "WS":
            # the description writes a path parameter without its converter
            assert path.replace(":path}", "}") in described, path
