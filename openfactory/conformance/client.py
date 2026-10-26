"""The client contract suite — a front end checks, against a release, that it and the API agree.

WHY THIS IS A DELIVERABLE AND NOT A TEST FOLDER, for the reason the adapter suite beside it is one.
The core's API is the contract a screen of one's own builds on
(`docs/reference/the-front-end-api.md`), and the default front end is only its first client.
Until this module, the one check of that contract lived in `tests/`, which the package does not
ship, and it read the route TABLE: that each route exists, never what it answers. A front end built
on the API had no way to learn, before its users did, that an upgrade had taken away a route, a
field or an event kind it reads.

A CLIENT DECLARES WHAT IT USES, AND THE SUITE ASKS THE API. The declaration is a small JSON
manifest — the routes, the fields of their answers and the event kinds the client relies on — and
the suite holds each against a live API at an address: the route is in the description the API
serves, the field is in the model it answers in, the kind is one the release's event models name.
Then it ASKS: every typed read the manifest names is called, and its status must be one the
description names for it (or one the contract names for every route), a body that says yes must
be the release's own model, and a refusal must say why in a `detail` sentence. A removal of
something the manifest names fails the run and names what is missing.

WHAT A CHECK MAY DO: read, and nothing else. Only GET routes that declare a model are called; a
route that writes, a stream and a file are checked against the description and never called, so a
run against a production deployment changes nothing in it. The credential is read from an
environment variable the caller names, and it is never printed.

ONE RELEASE ON BOTH SIDES. The models a body is held to, and the event kinds, are the ones of the
package this suite ships in, so the API at the address must run the same release: the first check
asks `/api/v1/version`, and a deployment of another version is a finding naming both, since a run
across two releases answers for neither.

THE RULES ARE FUNCTIONS, NOT PYTEST — a client lives in its own repository with its own runner.
`openfactory conformance-client` renders the report; the core's own suite drives the same function
over the default front end's manifest (`openfactory.conformance.front_end`), against the app.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from openfactory.conformance.adapters import Finding

#: What a manifest says it is, so a later shape can be told from this one.
SCHEMA = "openfactory.client/1"

#: The methods a manifest row may name: HTTP's, and `WS` for a socket, as the contract's table
#: writes them.
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "WS")

#: What the default front end's reader writes for what it cannot read off a call — a method that is
#: not a string literal in the call's own options, or an address whose route is a runtime value —
#: so the run names that call instead of taking it for the GET, or every route, it might be.
UNREAD = "?"
UNREAD_SEGMENT = "${…}"

#: The statuses the contract (section 2) names for EVERY route, which the description therefore does
#: not repeat on each: no credential or one nobody issued, a credential outside the path's area, and
#: a dependency that cannot answer right now — the identity provider, or the durable engine, which
#: every route answers as a 503 by one handler (`app._the_engine_did_not_answer`).
EVERY_ROUTE = (401, 403, 503)

#: What a path parameter is filled with when the caller gives none: a name no deployment holds, so a
#: read that takes a project answers its refusal, and the refusal is what is checked.
PROBE = "conformance-probe"

#: A credential nobody issued, for the check that one is refused like no credential at all.
NOT_ISSUED = "conformance-probe-credential-nobody-issued"

_PARAMETER = re.compile(r"\{([^}:]+)(?::[^}]*)?\}")


class ManifestError(ValueError):
    """A manifest the suite cannot read, said in one sentence that names the file and the fix."""


@dataclass(frozen=True)
class Route:
    """One route a client calls, and the fields of its answer it reads."""

    method: str
    path: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class EventUse:
    """One event kind a client branches on, and the fields of its data it reads."""

    kind: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manifest:
    client: str
    routes: tuple[Route, ...]
    events: tuple[EventUse, ...] = ()


@dataclass
class Report:
    """What a run found: the broken rules, the notes a client should read anyway (a deprecated
    alias, an open deployment), and how many answers were asked, so a run that asked nothing is
    seen as one."""

    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    asked: int = 0


def _finding(rule: str, detail: str, why: str) -> Finding:
    return Finding(rule=rule, detail=detail, taught_by=why)


# ── the manifest ────────────────────────────────────────────────────────────────────────────────

def parse_manifest(data: object, *, source: str = "the manifest") -> Manifest:
    """`data` as a manifest, or a `ManifestError` naming what is wrong with it. Nothing unknown is
    ignored: a key the suite does not read is a client believing it declared something it did
    not."""
    def refuse(what: str) -> ManifestError:
        return ManifestError(f"{source}: {what} — see docs/reference/the-client-contract-suite.md "
                             f"for the shape")

    if not isinstance(data, dict):
        raise refuse("it is not a JSON object")
    unknown = sorted(set(data) - {"schema", "client", "routes", "events"})
    if unknown:
        raise refuse(f"it has keys the suite does not read: {', '.join(unknown)}")
    if data.get("schema") != SCHEMA:
        raise refuse(f"`schema` is {data.get('schema')!r}, and this release reads {SCHEMA!r}")
    client = data.get("client")
    if not isinstance(client, str) or not client.strip():
        raise refuse("`client` must name the client, as a non-empty string")
    routes, events = data.get("routes", []), data.get("events", [])
    if not isinstance(routes, list) or not isinstance(events, list):
        raise refuse("`routes` and `events` must each be a list")
    if not routes and not events:
        raise refuse("it names no route and no event kind, so there is nothing to check")

    def fields_of(row: dict, where: str) -> tuple[str, ...]:
        got = row.get("fields", [])
        if not isinstance(got, list) or not all(isinstance(f, str) and f for f in got):
            raise refuse(f"{where}: `fields` must be a list of field names")
        return tuple(got)

    parsed_routes = []
    for n, row in enumerate(routes):
        where = f"routes[{n}]"
        if not isinstance(row, dict) or set(row) - {"method", "path", "fields"}:
            raise refuse(f"{where} must be an object of `method`, `path` and `fields`")
        method, path = row.get("method"), row.get("path")
        if method not in METHODS and method != UNREAD:
            raise refuse(f"{where}: `method` is {method!r}, and must be one of "
                         f"{', '.join(METHODS)}")
        if not isinstance(path, str) or not path.startswith("/"):
            raise refuse(f"{where}: `path` must be the route's path, as the contract writes it")
        parsed_routes.append(Route(method, path, fields_of(row, where)))
    parsed_events = []
    for n, row in enumerate(events):
        where = f"events[{n}]"
        if not isinstance(row, dict) or set(row) - {"kind", "fields"} or not isinstance(
                row.get("kind"), str):
            raise refuse(f"{where} must be an object of `kind` and `fields`")
        parsed_events.append(EventUse(row["kind"], fields_of(row, where)))
    return Manifest(client=client.strip(), routes=tuple(parsed_routes),
                    events=tuple(parsed_events))


def read_manifest(path: str | Path) -> Manifest:
    """The manifest in the file at `path`, or a `ManifestError` naming it."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestError(f"{path}: could not be read ({exc.strerror or exc})") from None
    except ValueError as exc:
        raise ManifestError(f"{path}: is not JSON ({exc})") from None
    return parse_manifest(data, source=str(path))


# ── the schema a field is looked up in ──────────────────────────────────────────────────────────

def _resolve(schema: dict, document: dict) -> dict:
    while isinstance(schema, dict) and "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        schema = (document.get("components", {}).get("schemas", {}).get(name)
                  or document.get("$defs", {}).get(name) or {})
    return schema if isinstance(schema, dict) else {}


def _has_field(schema: dict, dotted: str, document: dict) -> bool:
    """Whether `dotted` names a field the schema DECLARES, a list's items read through: `rows.state`
    is the `state` of each row. A key a model would only tolerate (`additionalProperties`) is not
    declared, and a client reading it reads something no release promised."""
    here = [schema]
    for name in dotted.split("."):
        found = []
        while here:
            node = _resolve(here.pop(), document)
            branches = node.get("anyOf") or node.get("oneOf") or node.get("allOf")
            if branches:
                here.extend(branches)
            elif node.get("type") == "array" or "items" in node:
                here.append(node.get("items", {}))
            elif name in node.get("properties", {}):
                found.append(node["properties"][name])
        if not found:
            return False
        here = found
    return True


# ── the release this suite ships in ─────────────────────────────────────────────────────────────

def _release_reads() -> dict[str, type[BaseModel]]:
    """The model each typed GET of this release answers in, by path."""
    from fastapi.routing import APIRoute

    from openfactory.api.app import app

    return {r.path: r.response_model for r in app.routes
            if isinstance(r, APIRoute) and "GET" in (r.methods or set())
            and isinstance(r.response_model, type) and issubclass(r.response_model, BaseModel)}


def _release_sockets() -> set[str]:
    """The socket routes of this release. The description the API serves names HTTP routes only."""
    from fastapi.routing import APIWebSocketRoute

    from openfactory.api.app import app

    return {r.path for r in app.routes if isinstance(r, APIWebSocketRoute)}


def _release_version() -> str:
    from openfactory import __version__

    return __version__


# ── the checks ──────────────────────────────────────────────────────────────────────────────────

def _headers(credential: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}"} if credential else {}


def _json(answer: httpx.Response) -> object:
    try:
        return answer.json()
    except ValueError:
        return None


def _says_why(status: int, body: object) -> bool:
    """A refusal is JSON with a `detail` sentence; the framework's 422 lists what it could not
    read instead."""
    if not isinstance(body, dict):
        return False
    detail = body.get("detail")
    return isinstance(detail, list) if status == 422 else isinstance(detail, str) and bool(detail)


def _check_release(http: httpx.Client, credential: str | None, report: Report) -> bool:
    answer = http.get("/api/v1/version", headers=_headers(credential))
    body = _json(answer)
    if answer.status_code != 200 or not isinstance(body, dict):
        report.findings.append(_finding(
            "client.release", f"GET /api/v1/version answered {answer.status_code}, so the release "
                              f"the API runs is unknown",
            "the models a body is held to are this release's; a run cannot say which release it "
            "checked against without it"))
        return False
    ours = _release_version()
    if body.get("version") != ours:
        report.findings.append(_finding(
            "client.release", f"the API runs {body.get('version')!r} and this suite is {ours!r}'s: "
                              f"install the release the API runs (pip install "
                              f"openfactory=={body.get('version')}) and run its suite",
            "a run that holds one release's answers to another's models answers for neither"))
        return False
    return True


def _check_refusals(http: httpx.Client, credential: str | None, report: Report) -> None:
    """No credential, and one nobody issued, are both the contract's 401 — asked of `whoami`, the
    read every credential may make. Without a credential to present the deployment must be open.

    A 503 is none of these: the contract gives it to every route for a dependency that cannot
    answer right now (the gate raises it before any 401 when the identity provider cannot be
    read), so it is filed as `client.dependency` — the deployment's state, never a bad secret."""
    bare = http.get("/api/v1/whoami")
    report.asked += 1
    if _unavailable(bare, report):
        return
    if credential is None:
        if bare.status_code == 401:
            report.findings.append(_finding(
                "client.credential", "the API asks for a credential and none was given: name the "
                                     "environment variable that holds one with --token-env",
                "a run without a credential against a gated deployment checks nothing"))
        else:
            report.notes.append("the deployment answers without a credential, so its 401 was not "
                                "checked: run against a deployment with a credential configured "
                                "for that")
        return
    stranger = http.get("/api/v1/whoami", headers=_headers(NOT_ISSUED))
    report.asked += 1
    for what, answer in (("no credential", bare), ("a credential nobody issued", stranger)):
        body = _json(answer)
        if answer.status_code != 401 or not isinstance(body, dict) or body.get(
                "detail") != "unauthorized":
            report.findings.append(_finding(
                "client.refusal-401", f"GET /api/v1/whoami with {what} answered "
                                      f"{answer.status_code} {answer.text[:200]!r}, not 401 "
                                      f"{{\"detail\": \"unauthorized\"}}",
                "a client signs a person out on the 401 the contract names; another answer leaves "
                "it showing a screen it may not read"))
    me = http.get("/api/v1/whoami", headers=_headers(credential))
    report.asked += 1
    if _unavailable(me, report):
        return
    # ONLY A 401 REFUSES THE CREDENTIAL ITSELF: `whoami` is the one read every credential may make
    # whatever it is scoped to (`app._UNSCOPED_ROUTES`), so it has no 403 to give a credential, and
    # any other answer is the API's, not the run's configuration
    if me.status_code == 401:
        report.findings.append(_finding(
            "client.credential", f"the credential given was refused by GET /api/v1/whoami "
                                 f"({me.status_code}): check the variable --token-env names",
            "every read below would be judged by a refusal of the caller, not of the API"))
    elif me.status_code != 200:
        report.findings.append(_finding(
            "client.answer-status", f"GET /api/v1/whoami, the read every credential may make, "
                                    f"answered {me.status_code} {me.text[:200]!r} to the "
                                    f"credential given, neither 200 nor its refusal (401)",
            "a client asks whoami which screen to draw; an answer that is neither leaves it "
            "guessing"))


def _unavailable(answer: httpx.Response, report: Report) -> bool:
    """Whether `whoami` answered the contract's 503, filed as the dependency it names."""
    if answer.status_code != 503:
        return False
    body = _json(answer)
    why = body.get("detail") if isinstance(body, dict) else None
    report.findings.append(_finding(
        "client.dependency", f"GET /api/v1/whoami answered 503"
                             f"{f' ({why})' if isinstance(why, str) and why else ''}: a dependency "
                             f"the API needs cannot answer right now, so nothing was held; run "
                             f"again when it does",
        "a 503 is the deployment's state, not the credential's; nothing it answers until then "
        "says whether the client conforms"))
    return True


def _fill(path: str, params: dict[str, str]) -> str:
    """`path` with each parameter filled from `params`, or with `PROBE`, each one quoted."""
    return _PARAMETER.sub(lambda m: quote(params.get(m.group(1), PROBE), safe=""), path)


def _ask(http: httpx.Client, route: Route, operation: dict, model: type[BaseModel],
         credential: str | None, params: dict[str, str], report: Report) -> None:
    """Call one typed read and hold its answer to what the description and the release promise."""
    query = {p["name"]: params[p["name"]] for p in operation.get("parameters", [])
             if p.get("in") == "query" and p.get("name") in params}
    at = _fill(route.path, params)
    answer = http.get(at, params=query, headers=_headers(credential))
    report.asked += 1
    status, body = answer.status_code, _json(answer)
    named = {int(s) for s in operation.get("responses", {}) if s.isdigit()}
    where = f"GET {at}"
    if status not in named | set(EVERY_ROUTE):
        report.findings.append(_finding(
            "client.answer-status", f"{where} answered {status}, and the description names "
                                    f"{sorted(named)} for it (and {list(EVERY_ROUTE)} for every "
                                    f"route)",
            "a client branches on the statuses the description names; an unnamed one reaches its "
            "users as a broken screen"))
    if 200 <= status < 300:
        try:
            model.model_validate(body)
        except ValidationError as exc:
            said = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or '(body)'}: {e['msg']}"
                             for e in exc.errors()[:3])
            report.findings.append(_finding(
                "client.answer-model", f"{where} answered a body that is not {model.__name__}: "
                                       f"{said}",
                "the model is what a client reads the body as; a body outside it is a field the "
                "client finds missing or of another type"))
    elif not _says_why(status, body):
        report.findings.append(_finding(
            "client.refusal-by-name", f"{where} refused with {status} and no `detail` sentence: "
                                      f"{answer.text[:200]!r}",
            "every refusal says why in `detail`, so a client can show it instead of a status code"))


def check_client(http: httpx.Client, manifest: Manifest, *, credential: str | None = None,
                 params: dict[str, str] | None = None) -> Report:
    """Hold `manifest` against the API `http` reaches. `http` carries the address as its
    `base_url`; `params` fills a route's path parameters and the query parameters its description
    declares, by name — a path parameter with none is `PROBE`, so the read answers its refusal."""
    params = dict(params or {})
    report = Report()
    try:
        described = http.get("/openapi.json")
    except httpx.HTTPError as exc:
        report.findings.append(_finding(
            "client.reachable", f"could not reach the API at {http.base_url}: {exc}",
            "the suite asks a running API; start one, or name the address it serves on"))
        return report
    document = _json(described)
    if described.status_code != 200 or not isinstance(document, dict) or "paths" not in document:
        report.findings.append(_finding(
            "client.reachable", f"{http.base_url} answered GET /openapi.json with "
                                f"{described.status_code}, not the API's description",
            "the description is served whether or not the default front end is on; an address "
            "that does not serve it is not the core's API"))
        return report
    # THE CREDENTIAL FIRST: every answer after it, the version's included, is judged with it, and a
    # caller the API refuses would be reported as an API that refuses everything
    _check_refusals(http, credential, report)
    if any(f.rule in ("client.credential", "client.dependency") for f in report.findings):
        return report
    if not _check_release(http, credential, report):
        return report

    reads, sockets = _release_reads(), _release_sockets()
    paths = document["paths"]
    for route in manifest.routes:
        name = f"{route.method} {route.path}"
        if route.method == UNREAD or UNREAD_SEGMENT in route.path:
            what = "method" if route.method == UNREAD else "route"
            report.findings.append(_finding(
                "client.route", f"{name} is a call whose {what} cannot be read off the page: "
                                f"write the method as a string literal in the call's options, "
                                f"and the address with its route's segments as literals",
                "a call the suite cannot read is one it cannot hold to a route, so it is named "
                "instead of taken for the route it might be"))
            continue
        if route.method == "WS":
            if route.path not in sockets:
                report.findings.append(_finding(
                    "client.route", f"{name} is not a socket of this release",
                    "a client that opens a socket the API no longer has falls back to polling, "
                    "or to nothing"))
            elif route.fields:
                report.findings.append(_finding(
                    "client.route", f"{name} names fields, and a socket's are its event kinds' — "
                                    f"name them under `events`",
                    "a field the suite cannot look up is a field it cannot hold"))
            continue
        operation = paths.get(route.path.replace(":path}", "}"), {}).get(route.method.lower())
        if operation is None:
            report.findings.append(_finding(
                "client.route", f"{name} is not a route of the API at {http.base_url}",
                "a route a client calls that the API does not serve is a screen that breaks on "
                "upgrade"))
            continue
        if operation.get("deprecated"):
            report.notes.append(f"{name} is a deprecated alias: build on its /api/v1/ address")
        success = (operation.get("responses", {}).get("200", {}).get("content", {})
                   .get("application/json", {}).get("schema"))
        for dotted in route.fields:
            if not success or not _has_field(success, dotted, document):
                report.findings.append(_finding(
                    "client.field", f"{name} answers no field `{dotted}`",
                    "a field a client reads and the API no longer declares is read as missing, "
                    "silently"))
        model = reads.get(route.path)
        if route.method == "GET" and model is not None:
            _ask(http, route, operation, model, credential, params, report)

    from openfactory.api import events

    for use in manifest.events:
        if use.kind not in events.KINDS:
            report.findings.append(_finding(
                "client.event", f"no stream of this release sends the event kind `{use.kind}`",
                "a client that waits for a kind no stream sends waits for ever"))
            continue
        data = events.DATA_MODELS[use.kind].model_json_schema()
        for dotted in use.fields:
            if not _has_field(data, dotted, data):
                report.findings.append(_finding(
                    "client.event-field", f"the event kind `{use.kind}` carries no field "
                                          f"`{dotted}`",
                    "a field a client reads and the event no longer declares is read as missing, "
                    "silently"))
    return report
