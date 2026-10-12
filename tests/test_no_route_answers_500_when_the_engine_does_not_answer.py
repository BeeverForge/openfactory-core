"""No route of the panel, and no action, answers 500 because the engine did not answer (#674).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640). In the last half hour of one sitting the
panel's log carried 103 responses `500 Internal Server Error`, each a ~200-line ASGI traceback:
73 from `GET /api/coordinator/messages` and 30 from `GET /api/inbox`. Every one ended in
`EngineUnreachable` from `view._within`, the bound #161 put on every read somebody waits for. The
routes were written before it: they turn a failed `connect()` into a 503 and call the bounded read
with nothing around it. Swept here, `/api/decisions` had the same shape, and so did the action
layer: the `diagnose` row reads the job list through the same bound, and `perform`'s catch-all read
the engine's silence as the action's own failure — FAILED, which the panel answers with a 500.

THE RULE THIS FILE HOLDS: whatever route a client calls and whatever action it asks for, an engine
that does not answer is a 503 carrying the read's own sentence, never a 500. The routes are read
from `app.routes` and the actions from the catalogue, not listed here, so one added tomorrow falls
under the rule without anyone remembering it.

WHAT IS DOUBLED, AND ONLY THAT. The engine, as a slow one behaves: `connect()` hands back a
client (the panel's cached client usually does, which is how the journey met this); every bounded
read (`_within`) raises `EngineUnreachable`; and a call made on the client directly, which nothing
bounds, gives up as the SDK's own deadline does, with an `RPCError`. What a route does with that
second one is not this file's rule. The deployment has one registered project, so the routes and actions addressed to a
project get past "no such project" to their reads. The routes, their middleware, the app's
handlers and the action layer are the real ones.

NOT SWEPT, AND WHY: the two `text/event-stream` routes and the websockets. Once a stream has
started there is no status left to answer; each carries its own degraded frame, held elsewhere.
"""

from __future__ import annotations

import logging
import re
import typing

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from openfactory import actions
from openfactory.api import app as panel
from openfactory.contracts.project import Project, ProviderRef
from openfactory.registry import ProjectRegistry
from openfactory.runtime.temporal import view as tv

temporalio_service = pytest.importorskip("temporalio.service")

SAID = "the engine did not answer the job list within 3s (OPENFACTORY_ENGINE_DEADLINE)"
PROJECT = "alpha"

#: A plausible value for every path parameter and body field, so the routes get past their own
#: validation to the reads this file is about. `action` and `answer` are words their routes check
#: before anything else.
_PLAUSIBLE = {"project": PROJECT, "issue": "7", "ref": "7", "unit": "7", "version": "1.2.0",
              "approver": "ana", "password": "a-password", "action": "resume",
              "answer": "approve", "token": "stage|7", "reason": "no longer wanted",
              "requirement": "7", "name": PROJECT}


class _SilentClient:
    """An engine client whose direct calls run out of the SDK's own time."""

    def __getattr__(self, name):
        def unanswered(*_a, **_k):
            raise temporalio_service.RPCError(
                "deadline exceeded", temporalio_service.RPCStatusCode.DEADLINE_EXCEEDED, b"")

        return unanswered


@pytest.fixture
def silent_engine(tmp_path, monkeypatch):
    """A deployment with one registered project, and an engine that does not answer."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENFACTORY_HOME", str(tmp_path / ".openfactory"))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    for name in ("OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PROD_APPROVERS", "OPENFACTORY_APPROVERS"):
        monkeypatch.delenv(name, raising=False)
    ProjectRegistry().add(Project(name=PROJECT, repo_path=str(tmp_path / "no-checkout"),
                                  tracker=ProviderRef(kind="local", repo=PROJECT)))

    async def _connect(*_a, **_k):
        return _SilentClient()

    async def _within(what, coro, *, seconds=None):
        close = getattr(coro, "close", None)
        if close:
            close()
        raise tv.EngineUnreachable(SAID)

    monkeypatch.setattr(tv, "connect", _connect)
    monkeypatch.setattr(tv, "_within", _within)
    monkeypatch.setattr(tv, "temporal_config", lambda *a, **k: ("localhost:7233", "default"))


# ── the routes ──────────────────────────────────────────────────────────────────────────────────

def _streams(route: APIRoute) -> bool:
    returned = typing.get_type_hints(route.endpoint).get("return")
    return isinstance(returned, type) and issubclass(returned, StreamingResponse)


def _routes() -> list[tuple[str, APIRoute]]:
    return [(method, route) for route in panel.app.routes
            if isinstance(route, APIRoute) and not _streams(route)
            for method in sorted(route.methods - {"HEAD", "OPTIONS"})]


def _url(route: APIRoute) -> str:
    return re.sub(r"{(\w+)(?::\w+)?}", lambda m: _PLAUSIBLE.get(m.group(1), "x"), route.path)


def _plain(annotation):
    """The plainest value of a type a body field declares."""
    kind = typing.get_origin(annotation) or annotation
    return {bool: True, int: 1, float: 1.0, list: [], dict: {}}.get(kind, "x")


def _body(route: APIRoute) -> dict | None:
    """The route's own body model, filled — so a 422 cannot stand in for an answer."""
    field = route.body_field
    if field is None:
        return None
    model = getattr(field, "type_", None) or field.field_info.annotation
    fields = getattr(model, "model_fields", None)
    if fields is None:                       # `body: dict` — free-form, the route reads what it needs
        return dict(_PLAUSIBLE)
    return {name: _PLAUSIBLE.get(name, _plain(f.annotation)) for name, f in fields.items()
            if f.is_required()}


def _escaped(exc: BaseException) -> bool:
    if isinstance(exc, tv.EngineUnreachable):
        return True
    return any(_escaped(e) for e in getattr(exc, "exceptions", ()) or ())


ROUTES = _routes()


def test_the_sweep_reaches_the_routes_that_broke():
    """An enumeration that quietly finds nothing passes every case below."""
    swept = {(method, route.path) for method, route in ROUTES}

    assert {("GET", "/api/inbox"), ("GET", "/api/coordinator/messages"), ("GET", "/api/decisions"),
            ("POST", "/api/projects/{project}/scan")} <= swept, swept
    assert len(ROUTES) > 50, f"only {len(ROUTES)} routes were read from the app"


@pytest.mark.parametrize(("method", "route"), ROUTES, ids=[f"{m} {r.path}" for m, r in ROUTES])
def test_an_engine_that_does_not_answer_is_never_a_500(silent_engine, method, route):
    client = TestClient(panel.app, raise_server_exceptions=True)
    try:
        res = client.request(method, _url(route), json=_body(route))
    except BaseException as exc:  # noqa: BLE001 — what escaped the app is the finding
        if _escaped(exc):
            pytest.fail(f"{method} {route.path}: the engine's silence escaped as {exc!r}")
        raise

    assert not (res.status_code == 500 and SAID in res.text), (
        f"{method} {_url(route)}: the engine's silence answered as a failure: {res.text[:300]}")
    assert res.status_code != 422, f"the sweep's own request was refused: {res.text[:300]}"


def test_the_503_says_what_the_engine_did_not_answer_once_in_the_log(silent_engine, caplog):
    """The sentence a client reads is the read's own, and the log says it once, not a traceback."""
    client = TestClient(panel.app, raise_server_exceptions=True)

    with caplog.at_level(logging.DEBUG):
        for url in ("/api/inbox", "/api/coordinator/messages", "/api/decisions"):
            res = client.get(url)
            assert res.status_code == 503, (url, res.status_code, res.text[:300])
            assert res.json()["detail"] == f"durable engine unreachable: {SAID}", res.json()

    said = [r for r in caplog.records if SAID in r.getMessage()]
    assert len(said) == 3, [r.getMessage() for r in said]
    assert all(r.exc_info is None and r.levelno == logging.WARNING for r in said), said


# ── the actions ─────────────────────────────────────────────────────────────────────────────────

ROWS = sorted(actions._catalog())


def test_the_action_sweep_reaches_the_row_that_broke():
    assert {"diagnose", "scan", "resume", "skip", "merge", "start"} <= set(ROWS), ROWS


@pytest.mark.parametrize("key", ROWS)
async def test_no_action_FAILS_because_the_engine_did_not_answer(silent_engine, key):
    """FAILED is the code the panel maps to 500. An engine that did not answer is UNAVAILABLE."""
    row = actions._catalog()[key]
    params = {name: _PLAUSIBLE.get(name, "x") for name in row.required}

    out = await actions.perform(key, by=actions.SYSTEM, **params)

    assert not (out.code == actions.FAILED and SAID in out.message), f"{key}: {out.message}"


async def test_an_action_the_engine_did_not_answer_says_so(silent_engine):
    out = await actions.perform("diagnose", by=actions.SYSTEM, project=PROJECT, issue="7")

    assert out.code == actions.UNAVAILABLE, out
    assert out.message == f"could not diagnose: {SAID}", out.message
