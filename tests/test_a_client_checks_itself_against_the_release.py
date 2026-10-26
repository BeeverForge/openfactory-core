"""A front end checks itself against a release: what the routes ANSWER, not only that they exist.

`tests/test_the_front_end_api_is_a_contract.py` pins the route TABLE to the code. It never asked a
route for its answer, it held one client, read as text, and it lived in `tests/`, which the
package does not ship. `openfactory.conformance.client` is the suite a client runs — the default
front end and a screen of one's own alike — and this file holds it two-sided, the way the adapter
suite is held: our own client runs GREEN through the same function the command runs, and a client
or an API that breaks a rule runs RED, naming it.

WHAT IS PROVEN HERE:

  · the default front end's manifest, read from the page, holds against the app — populated, and
    holding nothing, where every read answers its refusal — and so does a credentialed run;
  · that manifest is what the page calls: every address the page writes is one of its routes, a
    call the page adds is in it with its method, and the explanation of a call is not a call;
  · a manifest naming what the API does not have — a route, a field, an event kind or its field —
    fails, naming it, and one naming only what it has passes;
  · an API answering outside what it promises — an unnamed status, a body outside its model, a
    refusal without a sentence, another release, the wrong 401 — fails, naming it;
  · a call whose method or route the page's text cannot say is named, never guessed;
  · the suite only reads, a manifest it cannot read is refused in one sentence, and the command
    says CONFORMANT or NOT CONFORMANT with the exit code a CI job branches on — 2 for a credential
    it cannot use, 1 for a dependency that cannot answer or an API that stops answering mid-run, never a traceback, and never a run
    that waits without bound;
  · the guide's manifest, its command and the line it shows are ones the suite and the command
    take and print.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from openfactory.conformance.client import (
           SCHEMA,
           ManifestError,
           check_client,
           parse_manifest,
)
from openfactory.conformance.front_end import PAGE, calls, declared
from openfactory.conformance.front_end import manifest as front_end
from tests.test_the_front_end_api_is_a_contract import _called_by_the_page, _reaches
from tests.test_the_read_routes_declare_their_model import bench  # noqa: F401 — the fixture

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "reference" / "the-client-contract-suite.md"

#: What fills the bench's routes: its one project, a job with a journal, an address to read.
BENCH = {"project": "acme", "issue": "12", "repo_path": "/srv/acme"}


def _manifest(*routes: tuple[str, str, list[str]], events: tuple = ()) -> object:
    return parse_manifest({"schema": SCHEMA, "client": "a screen of one's own",
                           "routes": [{"method": m, "path": p, "fields": f} for m, p, f in routes],
                           "events": [{"kind": k, "fields": f} for k, f in events]})


def _rules(report) -> list[str]:
    return [f.rule for f in report.findings]


def _said(report) -> str:
    return "\n".join(f"{f.rule}: {f.detail}" for f in report.findings)


@pytest.fixture
def empty(monkeypatch, tmp_path):
    """A deployment that holds nothing: no project, no engine, no credential."""
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_BOARD_DB", str(tmp_path / "board.db"))
    for var in ("OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_IDENTITY",
                "OPENFACTORY_PRODUCT_TOKEN", "OPENFACTORY_PRODUCT_TOKENS"):
        monkeypatch.delenv(var, raising=False)
    from openfactory.api.app import app

    return TestClient(app)


# ── the default front end is the first green run ────────────────────────────────────────────────

def test_the_default_front_end_holds_against_a_populated_release(bench):  # noqa: F811
    asked, answered = [], {}
    bench.event_hooks = {
        "request": [lambda request: asked.append(request.method)],
        "response": [lambda answer: answered.update({str(answer.request.url): answer.status_code})]}
    ours = declared()

    report = check_client(bench, ours, params=BENCH)

    assert report.findings == [], _said(report)
    # populated, so every read said yes and its BODY was held to its model, not only its refusal
    reads = {url: status for url, status in answered.items()
             if "/whoami" not in url and "/version" not in url and "/openapi" not in url}
    assert reads and set(reads.values()) == {200}, reads
    assert "http://testserver/api/board/acme" in reads, sorted(reads)
    assert "http://testserver/api/address?repo_path=%2Fsrv%2Facme" in reads, sorted(reads)
    from openfactory.conformance.client import _release_reads

    typed = [r for r in ours.routes if r.method == "GET" and r.path in _release_reads()]
    assert report.asked >= len(typed) >= 18, (report.asked, len(typed))
    assert set(asked) == {"GET"}, f"the suite sent {sorted(set(asked))} — it may only read"


def test_against_a_release_that_holds_nothing_every_read_answers_a_refusal_it_names(empty):
    """Every `{project}` is the probe no deployment holds, so each read that takes one answers
    its refusal — and each refusal is one the description names for that read."""
    report = check_client(empty, declared())

    assert report.findings == [], _said(report)
    assert any("not checked" in n for n in report.notes), report.notes


@pytest.fixture
def gated(empty, monkeypatch):
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", "the-operator")
    return empty


def test_a_credentialed_run_checks_the_401_and_holds(gated):
    report = check_client(gated, declared(), credential="the-operator")

    assert report.findings == [], _said(report)
    assert not any("not checked" in n for n in report.notes), report.notes


def test_a_run_without_the_credential_a_gated_release_asks_for_says_so(gated):
    report = check_client(gated, _manifest(("GET", "/api/v1/projects", [])))

    assert "client.credential" in _rules(report), _said(report)
    assert "--token-env" in _said(report)


def test_a_credential_the_release_refuses_is_named(gated):
    report = check_client(gated, _manifest(("GET", "/api/v1/projects", [])), credential="nobody")

    assert "client.credential" in _rules(report), _said(report)


def _through(app, answer_for) -> httpx.Client:
    """The app's own answers, but where `answer_for(request)` answers one instead."""
    def handler(request: httpx.Request) -> httpx.Response:
        mine = answer_for(request)
        if mine is not None:
            return mine
        real = app.request(request.method, str(request.url), headers=dict(request.headers))
        return httpx.Response(real.status_code, content=real.content,
                              headers={"content-type": real.headers.get("content-type", "")})

    return httpx.Client(base_url="http://api.test", transport=httpx.MockTransport(handler))


def test_a_credentialed_run_holds_the_401_of_no_credential_on_its_own(gated):
    """The deployment refuses the credential nobody issued as it should, and answers a request
    with NO credential as if it were open: that alone is the finding."""
    def open_without_one(request):
        if request.url.path == "/api/v1/whoami" and "authorization" not in request.headers:
            return httpx.Response(200, json={"display": "anyone", "scopes": []})
        return None

    report = check_client(_through(gated, open_without_one),
                          _manifest(("GET", "/api/v1/projects", [])), credential="the-operator")

    assert _rules(report) == ["client.refusal-401"], _said(report)
    assert "with no credential answered 200" in _said(report)


# ── the default front end's manifest is what the page calls ─────────────────────────────────────

def test_every_address_the_page_calls_is_a_route_of_its_manifest():
    routes = {(r["method"], r["path"]) for r in front_end()["routes"]}
    paths = {p for _m, p in routes}

    for called in sorted(_called_by_the_page()):
        if called.endswith("/"):
            assert any(p.startswith(called) for p in paths), called
        else:
            assert any(_reaches(called, p) for p in paths), called
    from openfactory.conformance.front_end import _release_routes

    assert routes <= _release_routes(), sorted(routes - _release_routes())
    assert ("WS", "/api/stream") in routes and ("WS", "/api/product/stream") in routes
    assert ("POST", "/api/act/{name}") in routes and ("GET", "/api/floor/{project}") in routes


def test_the_page_branches_on_event_kinds_its_manifest_names():
    kinds = {e["kind"] for e in front_end()["events"]}

    assert {"update", "bye", "said", "reply", "refused"} <= kinds, sorted(kinds)


def _page(extra: str) -> str:
    return PAGE.read_text(encoding="utf-8").replace("</script>", extra + "\n</script>", 1)


def test_a_call_the_page_adds_is_in_its_manifest_with_its_method():
    page = _page('async function added(p){await mfetch("/api/jobs",{method:"POST",body:"{}"});'
                 'await mfetch(`/api/promote/${p}/${p}`,{headers:{},method:"POST"})}')

    added = calls(page) - calls(PAGE.read_text(encoding="utf-8"))

    assert added == {("POST", "/api/jobs"), ("POST", "/api/promote/{project}/{issue}")}, added


def test_the_explanation_of_a_call_is_not_a_call():
    page = _page('/* mfetch("/api/temporal/jobs",{method:"POST"}) */\n'
                 '  // mfetch("/api/v1/version")')

    assert calls(page) == calls(PAGE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("call", [
    'const o={method:"DELETE"};mfetch("/api/whoami",o)',
    'mfetch("/api/whoami",{method:m?"DELETE":"PUT"})',
    'mfetch("/api/whoami",{...o})',
], ids=["options in a variable", "method not a literal", "options spread"])
def test_a_call_whose_method_the_page_does_not_write_is_named_never_read_as_a_get(empty, call):
    page = _page(f"async function unread(m,o){{{call}}}")

    added = calls(page) - calls(PAGE.read_text(encoding="utf-8"))
    assert added == {("?", "/api/whoami")}, added
    report = check_client(empty, declared(page))

    assert _rules(report) == ["client.route"], _said(report)
    assert "? /api/whoami is a call whose method cannot be read off the page" in _said(report)


def test_a_method_the_options_write_is_read_past_what_they_nest():
    page = _page('async function nested(){await mfetch("/api/jobs",'
                 '{headers:{method:"GET"},method:"POST"})}')

    assert calls(page) - calls(PAGE.read_text(encoding="utf-8")) == {("POST", "/api/jobs")}


@pytest.mark.parametrize(("call", "method"), [
    ('mfetch("/api/jobs",{"method":"DELETE"})', "DELETE"),
    ("mfetch(\"/api/jobs\",{'method':'DELETE'})", "DELETE"),
    ('mfetch("/api/jobs",{headers:{},"method":"POST"})', "POST"),
    ('mfetch("/api/jobs",{"method":m})', "?"),
    ("mfetch(\"/api/jobs\",{'method':m?\"DELETE\":\"PUT\"})", "?"),
], ids=["double quotes", "single quotes", "after another key", "quoted, not a literal",
        "single quotes, a ternary"])
def test_a_quoted_method_key_is_read_as_the_bare_one(call, method):
    """`{"method":"DELETE"}` is the same options as `{method:"DELETE"}`: it is never the GET."""
    page = _page(f"async function quoted(m){{await {call}}}")

    assert calls(page) - calls(PAGE.read_text(encoding="utf-8")) == {(method, "/api/jobs")}


@pytest.mark.parametrize("address", ["`/api/${x}`", '"/api/"+x', "`/api/v1/${x}`"])
def test_an_address_whose_route_is_a_runtime_value_is_named_not_every_route(empty, address):
    page = _page(f"async function any(x){{await api({address})}}")

    added = calls(page) - calls(PAGE.read_text(encoding="utf-8"))
    assert len(added) == 1 and {m for m, _p in added} == {"GET"}, added
    ((_m, written),) = added
    assert written.endswith("/${…}"), added
    report = check_client(empty, declared(page))

    assert _rules(report) == ["client.route"], _said(report)
    assert "whose route cannot be read off the page" in _said(report)


def test_a_call_to_a_route_the_release_does_not_have_is_named_by_the_suite(empty):
    page = _page('async function gone(){await api("/api/no-such-read")}')
    assert ("GET", "/api/no-such-read") in calls(page)

    report = check_client(empty, declared(page))

    assert _rules(report) == ["client.route"], _said(report)
    assert "GET /api/no-such-read" in _said(report)


# ── a client that names what the API does not have ──────────────────────────────────────────────

def test_a_manifest_of_what_the_api_has_passes(empty):
    report = check_client(empty, _manifest(
        ("GET", "/api/v1/whoami", ["display", "scopes"]),
        ("GET", "/api/v1/budget", ["rows.state", "summary"]),
        ("POST", "/api/act/{name}", []), ("WS", "/api/product/stream", []),
        events=(("said", ["text"]), ("ended", []))))

    assert report.findings == [], _said(report)


@pytest.mark.parametrize(("routes", "events", "rule", "named"), [
    ([("GET", "/api/v1/gone", [])], (), "client.route", "GET /api/v1/gone"),
    ([("POST", "/api/v1/whoami", [])], (), "client.route", "POST /api/v1/whoami"),
    ([("WS", "/api/v1/gone", [])], (), "client.route", "WS /api/v1/gone"),
    ([("WS", "/api/product/stream", ["text"])], (), "client.route", "names fields"),
    ([("GET", "/api/v1/whoami", ["no_such_field"])], (), "client.field", "no_such_field"),
    ([("GET", "/api/v1/budget", ["rows.no_such_field"])], (), "client.field",
     "rows.no_such_field"),
    ([], (("no_such_kind", []),), "client.event", "no_such_kind"),
    ([], (("said", ["no_such_field"]),), "client.event-field", "no_such_field"),
], ids=["route", "method", "socket", "socket's fields", "field", "nested field", "event", "event field"])
def test_what_the_manifest_names_and_the_api_lacks_fails_naming_it(empty, routes, events, rule,
                                                                   named):
    report = check_client(empty, _manifest(*routes, events=events))

    assert _rules(report) == [rule], _said(report)
    assert named in report.findings[0].detail, _said(report)


# ── an API that answers outside what it promises ────────────────────────────────────────────────

def _lying(empty, path: str, answer: httpx.Response | None = None, *, version: str = "") -> object:
    """The app's own answers, but for `path`, which answers `answer` — and the version route,
    which answers `version` when one is given."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == path and answer is not None:
            return answer
        if version and request.url.path == "/api/v1/version":
            return httpx.Response(200, json={"version": version})
        real = empty.request(request.method, str(request.url), headers=dict(request.headers))
        return httpx.Response(real.status_code, content=real.content,
                              headers={"content-type": real.headers.get("content-type", "")})

    return httpx.Client(base_url="http://api.test", transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(("answer", "rule"), [
    (httpx.Response(418, json={"detail": "a teapot"}), "client.answer-status"),
    (httpx.Response(200, json={"display": ["not", "a", "string"]}), "client.answer-model"),
    (httpx.Response(404, text="not found"), "client.refusal-by-name"),
], ids=["unnamed status", "body outside its model", "refusal without a sentence"])
def test_an_answer_outside_the_promise_fails_naming_it(empty, answer, rule):
    report = check_client(_lying(empty, "/api/v1/whoami", answer),
                          _manifest(("GET", "/api/v1/whoami", [])))

    assert rule in _rules(report), _said(report)
    assert "GET /api/v1/whoami" in _said(report)


def test_a_422_listing_what_it_could_not_read_is_a_refusal_by_name(empty):
    unread = httpx.Response(422, json={"detail": [{"loc": ["query", "x"], "msg": "not a number"}]})
    report = check_client(_lying(empty, "/api/v1/floor", unread),
                          _manifest(("GET", "/api/v1/floor", [])))

    assert report.findings == [], _said(report)


def test_an_api_of_another_release_is_named_with_both_versions(empty):
    report = check_client(_lying(empty, "", version="0.0.1"),
                          _manifest(("GET", "/api/v1/whoami", [])))

    assert _rules(report) == ["client.release"], _said(report)
    assert "0.0.1" in _said(report) and "pip install openfactory==0.0.1" in _said(report)


def test_a_deprecated_alias_passes_with_a_note_naming_its_v1_address(empty):
    report = check_client(empty, _manifest(("GET", "/api/budget", [])))

    assert report.findings == [], _said(report)
    assert "GET /api/budget is a deprecated alias: build on its /api/v1/ address" in report.notes


@pytest.mark.parametrize("answer", [
    httpx.Response(500, json={"detail": "the version could not be read"}),
    httpx.Response(200, json=["0.8.0"]),
], ids=["not 200", "not an object"])
def test_a_version_route_that_does_not_say_the_release_is_named(empty, answer):
    report = check_client(_lying(empty, "/api/v1/version", answer),
                          _manifest(("GET", "/api/v1/whoami", [])))

    assert _rules(report) == ["client.release"], _said(report)
    assert f"answered {answer.status_code}, so the release the API runs is unknown" in _said(
        report)


def test_a_401_the_contract_does_not_name_is_named(gated):
    wrong = httpx.Response(401, json={"detail": "go away"})
    report = check_client(_lying(gated, "/api/v1/whoami", wrong),
                          _manifest(("GET", "/api/v1/projects", [])), credential="the-operator")

    assert "client.refusal-401" in _rules(report), _said(report)


def test_an_address_that_does_not_answer_is_named():
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    http = httpx.Client(base_url="http://nowhere.test", transport=httpx.MockTransport(refuse))
    report = check_client(http, _manifest(("GET", "/api/v1/whoami", [])))

    assert _rules(report) == ["client.reachable"], _said(report)
    assert "nowhere.test" in _said(report)


# ── the manifest, and the command ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("route", "said"), [
    ({"method": "?", "path": "/api/v1/whoami"}, "`method` is '?', and must be one of GET, POST"),
    ({"method": "GET", "path": "/api/v1/${x}"}, "has a runtime value"),
    ({"method": "GET", "path": "/api/v1/${…}"}, "has a runtime value"),
], ids=["?", "${x}", "${…}"])
def test_what_only_the_page_reader_writes_is_refused_from_a_written_manifest(empty, monkeypatch,
                                                                             tmp_path, route,
                                                                             said):
    """`?` and `${…}` are the default front end's reader naming what a page's text cannot say. A
    manifest someone wrote names its methods and paths: either is the exit-2 refusal, in one
    sentence, never a run that fails `client.route`."""
    mine = tmp_path / "mine.json"
    mine.write_text(json.dumps({"schema": SCHEMA, "client": "acme dashboard", "routes": [route]}))

    with pytest.raises(ManifestError) as refused:
        parse_manifest(json.loads(mine.read_text()))
    assert said in str(refused.value) and "\n" not in str(refused.value)

    got = _cli(monkeypatch, empty, "--manifest", str(mine))

    assert got.exit_code == 2, got.output
    assert said in got.output and len(got.output.strip().splitlines()) == 1, got.output
    assert "client.route" not in got.output and "Traceback" not in got.output


def test_the_page_reader_alone_may_write_what_it_cannot_read():
    """The same rows the reader writes: through `declared` they hold, and the page's own rows read
    the same through either door."""
    page = _page('async function unread(o,x){mfetch("/api/whoami",o);await api(`/api/${x}`)}')
    data = front_end(page)

    assert {("?", "/api/whoami"), ("GET", "/api/${…}")} <= {(r.method, r.path)
                                                            for r in declared(page).routes}
    with pytest.raises(ManifestError):
        parse_manifest(data)
    today = front_end()
    assert declared().routes == parse_manifest(today).routes
    assert len(today["routes"]) == 41, len(today["routes"])


@pytest.mark.parametrize(("data", "said"), [
    ([], "not a JSON object"),
    ({"schema": SCHEMA, "client": "x", "routes": [], "event": []}, "keys the suite does not read"),
    ({"schema": "openfactory.client/0", "client": "x", "routes": []}, "this release reads"),
    ({"schema": SCHEMA, "client": "", "routes": [{"method": "GET", "path": "/x"}]}, "`client`"),
    ({"schema": SCHEMA, "client": "x", "routes": [{"method": "FETCH", "path": "/x"}]},
     "`method`"),
    ({"schema": SCHEMA, "client": "x", "routes": [{"method": "GET", "path": "/x",
                                                   "fields": "a"}]}, "`fields`"),
    ({"schema": SCHEMA, "client": "x", "routes": [], "events": []}, "nothing to check"),
], ids=["not an object", "unknown key", "schema", "client", "method", "fields", "empty"])
def test_a_manifest_the_suite_cannot_read_is_refused_in_one_sentence(data, said):
    with pytest.raises(ManifestError) as refused:
        parse_manifest(data, source="my.json")

    assert said in str(refused.value) and str(refused.value).startswith("my.json: ")
    assert "\n" not in str(refused.value)


def _cli(monkeypatch, http, *args):
    from openfactory import cli

    monkeypatch.setattr(cli, "_client_http", lambda _address: http)
    return CliRunner().invoke(cli.app, ["conformance-client", "http://api.test", *args])


def test_the_command_says_conformant_for_the_default_front_end(bench, monkeypatch):  # noqa: F811
    got = _cli(monkeypatch, bench, *[a for k, v in BENCH.items() for a in ("--param", f"{k}={v}")])

    assert got.exit_code == 0, got.output
    assert "CONFORMANT — the default front end" in got.output and "FAIL" not in got.output


def test_the_command_fails_a_client_naming_what_it_uses_and_the_api_lacks(empty, monkeypatch,
                                                                          tmp_path):
    mine = tmp_path / "mine.json"
    mine.write_text(json.dumps({"schema": SCHEMA, "client": "acme dashboard",
                                "routes": [{"method": "GET", "path": "/api/v1/gone"}]}))

    got = _cli(monkeypatch, empty, "--manifest", str(mine))

    assert got.exit_code == 1, got.output
    assert "FAIL  client.route" in got.output and "GET /api/v1/gone" in got.output
    assert "NOT CONFORMANT — 1 rule(s) broken for acme dashboard" in got.output


@pytest.mark.parametrize(("args", "said"), [
    (["--manifest", "/nonexistent/mine.json"], "could not be read"),
    (["--token-env", "NO_SUCH_VARIABLE_HERE"], "NO_SUCH_VARIABLE_HERE, and it is not set"),
    (["--param", "project"], "must be name=value"),
], ids=["manifest", "credential", "param"])
def test_the_command_refuses_what_it_cannot_use_in_one_sentence(empty, monkeypatch, args, said):
    got = _cli(monkeypatch, empty, *args)

    assert got.exit_code == 2 and said in got.output, got.output
    assert "Traceback" not in got.output


@pytest.mark.parametrize("args", [[], ["--token-env", "MY_CLIENT_TOKEN"]],
                         ids=["none given", "one the API refuses"])
def test_a_credential_the_command_cannot_use_exits_2_naming_it(gated, monkeypatch, args):
    """Exit 2, as for an option the suite cannot use: a CI job reads a misconfigured secret as
    that, not as a client that broke the contract."""
    monkeypatch.setenv("MY_CLIENT_TOKEN", "nobody-issued-this")

    got = _cli(monkeypatch, gated, *args)

    assert got.exit_code == 2, got.output
    assert "FAIL  client.credential" in got.output and "NOT CHECKED" in got.output, got.output
    assert "NOT CONFORMANT" not in got.output and "nobody-issued-this" not in got.output


@pytest.mark.parametrize("args", [[], ["--token-env", "MY_CLIENT_TOKEN"]],
                         ids=["no credential", "a credential"])
def test_a_whoami_that_answers_503_is_the_dependency_not_the_credential(monkeypatch, args):
    """The identity provider is down: every `whoami` answers the contract's 503. That is the
    deployment's state, exit 1, never a misconfigured secret (exit 2)."""
    def provider_down(request):
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json={"paths": {}})
        return httpx.Response(503, json={"detail": "the identity provider cannot answer right now"})

    monkeypatch.setenv("MY_CLIENT_TOKEN", "the-operator")
    got = _cli(monkeypatch, httpx.Client(base_url="http://api.test",
                                         transport=httpx.MockTransport(provider_down)), *args)

    assert got.exit_code == 1, got.output
    assert "FAIL  client.dependency" in got.output, got.output
    assert "the identity provider cannot answer right now" in got.output
    assert "client.credential" not in got.output and "NOT CHECKED" not in got.output
    assert "client.refusal-401" not in got.output and "NOTE" not in got.output, got.output
    assert "client.release" not in got.output, "nothing past whoami is judged"


def test_a_whoami_that_answers_neither_200_nor_401_to_the_credential_is_the_apis(gated):
    """`whoami` is the read every credential may make, so it has no 403 for one: a 403 is the API's
    answer, never a refused credential."""
    def forbidden(request):
        if request.url.path == "/api/v1/whoami" and request.headers.get(
                "authorization") == "Bearer the-operator":
            return httpx.Response(403, json={"detail": "not allowed"})
        return None

    report = check_client(_through(gated, forbidden), _manifest(("GET", "/api/v1/projects", [])),
                          credential="the-operator")

    assert _rules(report) == ["client.answer-status"], _said(report)
    assert "answered 403" in _said(report)


def test_an_api_that_stops_answering_mid_run_is_one_sentence_and_exit_1(empty, monkeypatch):
    """The description and `whoami` answer; every request after them times out."""
    def then_silence(request):
        if request.url.path in ("/openapi.json", "/api/v1/whoami"):
            return None
        raise httpx.ReadTimeout("timed out", request=request)

    got = _cli(monkeypatch, _through(empty, then_silence))

    assert got.exit_code == 1, got.output
    assert "the API at http://api.test stopped answering during the run: timed out" in got.output
    assert "Traceback" not in got.output and not isinstance(got.exception, httpx.HTTPError)


def test_the_command_asks_with_a_bounded_timeout():
    """A read the API cannot answer is a finding of its own, never a run that hangs."""
    from openfactory import cli

    with cli._client_http("http://api.test") as http:
        bounds = (http.timeout.connect, http.timeout.read, http.timeout.write, http.timeout.pool)

    assert all(b is not None and 0 < b <= 60 for b in bounds), bounds


def test_the_command_presents_the_credential_its_variable_holds(gated, monkeypatch):
    monkeypatch.setenv("MY_CLIENT_TOKEN", "the-operator")

    got = _cli(monkeypatch, gated, "--token-env", "MY_CLIENT_TOKEN")

    assert got.exit_code == 0, got.output
    assert "the-operator" not in got.output, "the credential is never printed"


# ── the guide ───────────────────────────────────────────────────────────────────────────────────

def _blocks(language: str) -> list[str]:
    return re.findall(rf"```{language}\n(.*?)```", GUIDE.read_text(encoding="utf-8"), flags=re.S)


def test_the_guides_manifest_holds_against_the_release(gated, monkeypatch, tmp_path):
    """Run as the guide's first command runs it — its manifest, a credential — and the line the
    command prints is the one the guide shows, counts and all."""
    (example,) = [b for b in _blocks("json") if SCHEMA in b]
    (shown,) = [line for line in GUIDE.read_text(encoding="utf-8").splitlines()
                if line.startswith("CONFORMANT — ")]
    mine = tmp_path / "my-client.json"
    mine.write_text(example)
    monkeypatch.setenv("MY_TOKEN", "the-operator")

    got = _cli(monkeypatch, gated, "--manifest", str(mine), "--token-env", "MY_TOKEN")

    assert got.exit_code == 0, got.output
    (printed,) = [line for line in got.output.splitlines() if line.startswith("CONFORMANT — ")]
    assert printed.replace("http://api.test", "http://localhost:8787") == shown, (printed, shown)


def test_the_guides_commands_are_ones_the_command_takes():
    import typer

    from openfactory.cli import app

    command = typer.main.get_command(app).commands["conformance-client"]
    lines = [line for block in _blocks("bash") + _blocks("yaml")
             for line in block.replace("\\\n", " ").splitlines()
             if "openfactory conformance-client" in line]
    assert len(lines) >= 3, lines
    for line in lines:
        argv = shlex.split(line.split("openfactory conformance-client", 1)[1])
        command.make_context("conformance-client", argv)  # raises on an option it does not have


def test_the_guides_ci_job_is_yaml_a_runner_reads():
    (job,) = _blocks("yaml")

    assert yaml.safe_load(job)
