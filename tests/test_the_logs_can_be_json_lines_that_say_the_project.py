"""The worker's and the panel's logs can be JSON lines, each saying the project it concerns (#681).

#675 gave every process the deployment starts one readable line with a time, a level and a name. A
log store reads fields, not sentences, and the line could not say which project or product it was
about: a warning a job wrote and the same warning from another project's job read alike.

THE RULES THIS FILE HOLDS:

  · with `OPENFACTORY_LOG_FORMAT=json`, every process the deployment starts — read from what
    starts them, by the #675 guard this file borrows its drivers from — writes one JSON object per
    line, with `ts` (UTC, to the millisecond), `level`, `logger` and `message`, keeps the platform's
    INFO and drops the libraries'; a traceback stays one line; `deployment` is there exactly when
    `OPENFACTORY_DEPLOYMENT` names one;
  · without it — unset, or any other value — the line is #675's, unchanged;
  · a record concerns a project when it is logged inside work about one, and then its line says the
    project and the product the project belongs to: EVERY worker activity whose input names a
    project, read from the activities the worker registers, and EVERY panel route whose path takes
    one, read from the app's routes. Work that names no project says none.
"""

from __future__ import annotations

import ast
import inspect
import io
import json
import logging
import re
import typing

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from temporalio.worker import ActivityInboundInterceptor, ExecuteActivityInput

from openfactory.observability import logs
from tests.test_every_process_the_deployment_starts_logs_with_a_time_a_level_and_a_name import (
    DRIVEN,
    LINE,
    REJECTED,
    UNLISTED,
    _a_fresh_process,
)

TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
FIELDS = ("ts", "level", "logger", "message")


@pytest.fixture(autouse=True)
def _nothing_said(monkeypatch):
    for name in (logs.LEVEL_VARIABLE, logs.FORMAT_VARIABLE, logs.DEPLOYMENT_VARIABLE):
        monkeypatch.delenv(name, raising=False)


def _json_lines(err: str) -> list[dict]:
    lines = [line for line in err.splitlines() if line.strip()]
    assert lines, "nothing was written"
    parsed = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except ValueError:
            pytest.fail(f"a line that is not one JSON object: {line!r}")
    return parsed


# ── every process the deployment starts ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("process", sorted(DRIVEN))
def test_every_line_is_one_json_object_with_the_four_fields(monkeypatch, capsys, process):
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    with _a_fresh_process():
        DRIVEN[process](monkeypatch)

    lines = _json_lines(capsys.readouterr().err)
    for line in lines:
        assert list(line)[:4] == list(FIELDS), line
        assert TS.match(line["ts"]) and line["level"] in ("INFO", "WARNING", "ERROR"), line
        assert "deployment" not in line, line
    said = {(line["level"], line["logger"], line["message"]) for line in lines}
    assert ("INFO", "openfactory.knowledge.pipeline", REJECTED) in said, said
    assert ("WARNING", "openfactory.panel", UNLISTED) in said, said
    assert not any("a library's chatter" in line["message"] for line in lines), lines


@pytest.mark.parametrize("asked", ["json", " JSON "])
def test_json_is_asked_in_any_case(monkeypatch, capsys, asked):
    monkeypatch.setenv(logs.FORMAT_VARIABLE, asked)
    with _a_fresh_process():
        DRIVEN["worker"](monkeypatch)

    assert _json_lines(capsys.readouterr().err)


@pytest.mark.parametrize("asked", [None, "", "text", "jsonl", "yaml"])
def test_anything_else_keeps_the_readable_line_unchanged(monkeypatch, capsys, asked):
    if asked is not None:
        monkeypatch.setenv(logs.FORMAT_VARIABLE, asked)
    with _a_fresh_process():
        DRIVEN["worker"](monkeypatch)

    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert lines and all(LINE.match(line) for line in lines), lines


def test_the_deployment_is_named_on_every_line_when_it_is_set(monkeypatch, capsys):
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    monkeypatch.setenv(logs.DEPLOYMENT_VARIABLE, " factory-eu-1 ")
    with _a_fresh_process():
        DRIVEN["panel"](monkeypatch)

    assert {line.get("deployment") for line in _json_lines(capsys.readouterr().err)} == {
        "factory-eu-1"}


def test_a_traceback_stays_one_line_and_a_message_keeps_its_letters(monkeypatch, capsys):
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    with _a_fresh_process():
        logs.configure()
        try:
            raise RuntimeError("o repositório não respondeu")
        except RuntimeError:
            logging.getLogger("openfactory.knowledge").exception("a push was refused — ação")

    err = capsys.readouterr().err
    (line,) = _json_lines(err)
    assert "ação" in err, "the letters were escaped rather than written"
    assert line["message"] == "a push was refused — ação", line
    assert line["exception"].startswith("Traceback") and "não respondeu" in line["exception"]


# ── what a record concerns ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def captured():
    """The JSON lines one logger writes, formatted as they are emitted — inside the context the
    record was logged in, which is where a stream handler formats it."""
    out = io.StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(logs._JSON())
    logger = logging.getLogger("openfactory.test.about")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    yield lambda: [json.loads(line) for line in out.getvalue().splitlines()]
    logger.removeHandler(handler)
    logger.propagate = True


def _say(what: str) -> None:
    logging.getLogger("openfactory.test.about").info(what)


def test_a_record_inside_work_about_a_project_says_it_and_outside_says_none(captured):
    _say("before")
    with logs.about(project="acme", product="repo:acme/docs"):
        _say("inside")
        with logs.about(project="globex"):
            _say("nested")
        _say("back")
    logging.getLogger("openfactory.test.about").info("its own", extra={"project": "initech"})
    _say("after")

    said = {line["message"]: (line.get("project"), line.get("product")) for line in captured()}
    assert said == {"before": (None, None), "inside": ("acme", "repo:acme/docs"),
                    "nested": ("globex", None), "back": ("acme", "repo:acme/docs"),
                    "its own": ("initech", None), "after": (None, None)}


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """`acme` belongs to the product of its context repository; `globex` is a product of one."""
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"projects": {
        "acme": {"name": "acme", "repo_path": str(tmp_path),
                 "tracker": {"kind": "local", "repo": "acme"},
                 "product": {"docs_repo": "Acme/Docs"}},
        "globex": {"name": "globex", "repo_path": str(tmp_path),
                   "tracker": {"kind": "local", "repo": "globex"}}}}))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(path))
    return path


def test_the_product_is_the_one_the_registry_says_and_only_for_json(registry, monkeypatch):
    assert logs.concerning("acme") == {"project": "acme", "product": ""}, (
        "the readable line carries no tag, so it must not pay for the registry")

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    assert logs.concerning("acme") == {"project": "acme", "product": "repo:acme/docs"}
    assert logs.concerning("globex") == {"project": "globex", "product": "project:globex"}
    assert logs.concerning("acme", "carried") == {"project": "acme", "product": "carried"}
    assert logs.concerning("nobody-registered") == {"project": "nobody-registered", "product": ""}


# ── the panel: every route that takes a project ─────────────────────────────────────────────────

def test_every_route_of_the_panel_is_built_to_say_its_project():
    from fastapi.routing import APIRoute

    from openfactory.api.app import app
    from openfactory.api.project_route import AboutItsProject

    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    about = [r for r in routes if "{project}" in r.path]

    assert len(about) > 20, [r.path for r in about]
    assert all(isinstance(r, AboutItsProject) for r in routes), [
        r.path for r in routes if not isinstance(r, AboutItsProject)]


def _a_panel_of_the_same_class() -> FastAPI:
    """The routes the panel's class builds, with a handler of each kind: on the loop, on a worker
    thread, and one whose path names no project."""
    from openfactory.api.project_route import AboutItsProject

    app = FastAPI()
    app.router.route_class = AboutItsProject

    @app.get("/api/board/{project}")
    async def on_the_loop(project: str) -> dict:
        _say("on the loop")
        return {}

    @app.get("/api/loops/{project}")
    def on_a_thread(project: str) -> dict:
        _say("on a thread")
        return {}

    @app.get("/api/budget")
    def about_no_project() -> dict:
        _say("about no project")
        return {}

    return app


def test_a_panel_route_about_a_project_says_it_and_its_product(registry, monkeypatch, captured):
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    client = TestClient(_a_panel_of_the_same_class())

    for path in ("/api/board/acme", "/api/loops/globex", "/api/budget"):
        assert client.get(path).status_code == 200, path

    said = {line["message"]: (line.get("project"), line.get("product")) for line in captured()}
    assert said == {"on the loop": ("acme", "repo:acme/docs"),
                    "on a thread": ("globex", "project:globex"),
                    "about no project": (None, None)}


# ── the worker: every activity whose input names a project ──────────────────────────────────────

def _is_model(kind) -> bool:
    return isinstance(kind, type) and issubclass(kind, BaseModel)


def _model_about(model: type[BaseModel], project: str, depth: int = 2):
    """An instance of `model` naming `project` where the model declares one — its own field, or a
    model one field down — and whether it could."""
    fields = model.model_fields
    if "project" in fields:
        return model.model_construct(project=project), True
    if depth > 1:
        for name, field in fields.items():
            if _is_model(field.annotation):
                inner, found = _model_about(field.annotation, project, depth - 1)
                if found:
                    return model.model_construct(**{name: inner}), True
    return model.model_construct(), False


def _arguments_about(fn, project: str) -> tuple[list, bool]:
    """The arguments `fn` is called with, naming `project` wherever its signature lets them."""
    from openfactory.runtime.temporal.interceptors import PROJECT_PARAMETERS

    hints = typing.get_type_hints(fn)
    args, names = [], False
    for name in inspect.signature(fn).parameters:
        kind = hints.get(name)
        if name in PROJECT_PARAMETERS and kind is str:
            args.append(project)
            names = True
        elif _is_model(kind):
            built, found = _model_about(kind, project)
            args.append(built)
            names = names or found
        else:
            args.append(None)
    return args, names


class _TheActivity:
    """What runs below the interceptor: the activity, saying one line."""

    async def execute_activity(self, input: ExecuteActivityInput):
        _say(f"inside {input.fn.__name__}")
        return "done"


async def _run(fn, args) -> str:
    from openfactory.runtime.temporal.interceptors import AboutItsProject

    inbound = AboutItsProject().intercept_activity(_TheActivity())
    assert isinstance(inbound, ActivityInboundInterceptor)
    return await inbound.execute_activity(
        ExecuteActivityInput(fn=fn, args=args, executor=None, headers={}))


def _activities():
    from openfactory.runtime.temporal import worker

    return list(worker.WORKER_ACTIVITIES)


@pytest.mark.parametrize("fn", _activities(), ids=lambda fn: fn.__name__)
async def test_every_activity_whose_input_names_a_project_says_it(captured, fn):
    args, names = _arguments_about(fn, "acme")

    assert await _run(fn, args) == "done"

    (line,) = captured()
    assert line.get("project") == ("acme" if names else None), (fn.__name__, line)


def test_the_sweep_reaches_the_activities_that_name_a_project_and_those_that_do_not():
    """An enumeration that quietly found nothing would pass every case above."""
    named = {fn.__name__ for fn in _activities() if _arguments_about(fn, "acme")[1]}

    assert {"run_job", "product_sweep", "preview_plan", "conversation_turn"} <= named, named
    assert {"scan_projects", "verify_gate_seal"} <= {fn.__name__ for fn in _activities()} - named


async def test_an_activity_that_carries_its_product_says_that_product(captured, registry,
                                                                     monkeypatch):
    from openfactory.runtime.temporal.activities import conversation_turn, run_job
    from openfactory.runtime.temporal.io import TurnInput

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    await _run(conversation_turn, [TurnInput.model_construct(project="acme", product="carried")])
    await _run(run_job, [_model_about(typing.get_type_hints(run_job)["inp"], "globex")[0]])

    first, second = captured()
    assert (first["project"], first["product"]) == ("acme", "carried")
    assert (second["project"], second["product"]) == ("globex", "project:globex")


def test_the_worker_registers_the_interceptor():
    """Reachability, read off `main`: the worker is built with it — a class nobody registers would
    pass every case above and tag nothing."""
    from openfactory.runtime.temporal import worker

    tree = ast.parse(inspect.getsource(worker.main))
    built = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "Worker"]
    assert len(built) == 1
    given = {k.arg: k.value for k in built[0].keywords}
    assert "interceptors" in given, "the worker is built without its interceptors"
    named = {n.func.id for n in ast.walk(given["interceptors"])
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "AboutItsProject" in named, ast.dump(given["interceptors"])
