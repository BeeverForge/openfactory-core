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
  · the suite only reads, a manifest it cannot read is refused in one sentence, and the command
    says CONFORMANT or NOT CONFORMANT with the exit code a CI job branches on;
  · the guide's manifest and command are ones the suite and the command take.
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
from openfactory.conformance.front_end import PAGE, calls
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
    declared = parse_manifest(front_end())

    report = check_client(bench, declared, params=BENCH)

    assert report.findings == [], _said(report)
    # populated, so every read said yes and its BODY was held to its model, not only its refusal
    reads = {url: status for url, status in answered.items()
             if "/whoami" not in url and "/version" not in url and "/openapi" not in url}
    assert reads and set(reads.values()) == {200}, reads
    assert "http://testserver/api/board/acme" in reads, sorted(reads)
    assert "http://testserver/api/address?repo_path=%2Fsrv%2Facme" in reads, sorted(reads)
    from openfactory.conformance.client import _release_reads

    typed = [r for r in declared.routes if r.method == "GET" and r.path in _release_reads()]
    assert report.asked >= len(typed) >= 18, (report.asked, len(typed))
    assert set(asked) == {"GET"}, f"the suite sent {sorted(set(asked))} — it may only read"


def test_against_a_release_that_holds_nothing_every_read_answers_a_refusal_it_names(empty):
    """Every `{project}` is the probe no deployment holds, so each read that takes one answers
    its refusal — and each refusal is one the description names for that read."""
    report = check_client(empty, parse_manifest(front_end()))

    assert report.findings == [], _said(report)
    assert any("not checked" in n for n in report.notes), report.notes


@pytest.fixture
def gated(empty, monkeypatch):
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", "the-operator")
    return empty


def test_a_credentialed_run_checks_the_401_and_holds(gated):
    report = check_client(gated, parse_manifest(front_end()), credential="the-operator")

    assert report.findings == [], _said(report)
    assert not any("not checked" in n for n in report.notes), report.notes


def test_a_run_without_the_credential_a_gated_release_asks_for_says_so(gated):
    report = check_client(gated, _manifest(("GET", "/api/v1/projects", [])))

    assert "client.credential" in _rules(report), _said(report)
    assert "--token-env" in _said(report)


def test_a_credential_the_release_refuses_is_named(gated):
    report = check_client(gated, _manifest(("GET", "/api/v1/projects", [])), credential="nobody")

    assert "client.credential" in _rules(report), _said(report)


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


def test_a_call_to_a_route_the_release_does_not_have_is_named_by_the_suite(empty):
    page = _page('async function gone(){await api("/api/no-such-read")}')
    assert ("GET", "/api/no-such-read") in calls(page)

    report = check_client(empty, parse_manifest(front_end(page)))

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
    ([("GET", "/api/v1/whoami", ["no_such_field"])], (), "client.field", "no_such_field"),
    ([("GET", "/api/v1/budget", ["rows.no_such_field"])], (), "client.field",
     "rows.no_such_field"),
    ([], (("no_such_kind", []),), "client.event", "no_such_kind"),
    ([], (("said", ["no_such_field"]),), "client.event-field", "no_such_field"),
], ids=["route", "method", "socket", "field", "nested field", "event", "event field"])
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
