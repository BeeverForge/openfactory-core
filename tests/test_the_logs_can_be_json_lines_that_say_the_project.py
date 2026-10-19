"""The worker's and the panel's logs can be JSON lines, each saying the project it concerns (#681).

#675 gave every process the deployment starts one readable line with a time, a level and a name. A
log store reads fields, not sentences, and the line could not say which project or product it was
about: a warning a job wrote and the same warning from another project's job read alike.

THE RULES THIS FILE HOLDS:

  · with `OPENFACTORY_LOG_FORMAT=json`, every process the deployment starts — read from what
    starts them, by the #675 guard this file borrows its drivers from — writes one JSON object per
    line, on stderr AND on stdout (a container's log is both), with `ts` (UTC, to the millisecond),
    `level`, `logger` and `message`, keeps the platform's INFO and drops the libraries'; a traceback
    stays one line; `deployment` is there exactly when `OPENFACTORY_DEPLOYMENT` names one; the
    lines a process prints for a person, and the sentence it ends with, follow the format;
  · without it — unset, or any other value — the line is #675's, unchanged;
  · a record concerns a project when it is logged inside work about one, and then its line says the
    project and the product the project belongs to: EVERY worker activity whose input names a
    project, read from the activities the worker registers, and EVERY panel route whose path takes
    one, read from the app's routes — the body of the stream it answers with included. Work that
    names no project says none;
  · THE PRODUCT COSTS NOBODY ANYTHING (second review of #818): a line takes it from memory and
    never waits; the registry is read at most once per window, one read at a time, on a daemon
    thread of its own and never on the default executor; only work the gate admitted asks for that
    read, so EVERY route the gate leaves open — read from the app's routes and the gate's own rule —
    takes no thread and reads no registry, with the executor held and the registry hung; and the
    copy holds the registry's projects, never the names a URL carries;
  · with JSON lines, the durable engine client's own core writes through the same format.
"""

from __future__ import annotations

import ast
import asyncio
import concurrent.futures
import inspect
import io
import json
import logging
import re
import threading
import time
import types
import typing

import pytest
import yaml
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from temporalio import activity
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

    written = capsys.readouterr()
    plain = [line for line in written.out.splitlines() if line.strip()]
    assert all(line.startswith("{") and json.loads(line) for line in plain), (
        f"{process} wrote a plain line on stdout: {plain}")
    lines = _json_lines(written.err)
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


def test_the_panel_says_where_it_serves_in_the_format_it_was_asked_for(monkeypatch, capsys):
    """`serve`'s first line, for a person: printed as ever, or a JSON line among the others."""
    with _a_fresh_process():
        DRIVEN["panel"](monkeypatch)
    assert "panel: http://127.0.0.1:8787" in capsys.readouterr().out.splitlines()

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    with _a_fresh_process():
        DRIVEN["panel"](monkeypatch)
    written = capsys.readouterr()
    assert not written.out.strip(), written.out
    assert {"level": "INFO", "message": "panel: http://127.0.0.1:8787"}.items() <= next(
        line for line in _json_lines(written.err) if "panel:" in line["message"]).items()


#: The functions a process runs to start, whose every line goes through `logs.announce` — the
#: worker's `main` and the panel's `serve`, the two entry points #675's guard drives.
def _entry_points():
    from openfactory import cli
    from openfactory.runtime.temporal import worker

    return {"worker.main": worker.main, "cli.serve": cli.serve}


@pytest.mark.parametrize("name", sorted(_entry_points()))
def test_no_entry_point_prints_past_the_format(name):
    """Read off each entry point's syntax tree: nothing in it writes to stdout by itself."""
    tree = ast.parse(inspect.getsource(_entry_points()[name]).lstrip())
    printed = [ast.unparse(n)[:80] for n in ast.walk(tree) if isinstance(n, ast.Call)
               and (getattr(n.func, "id", "") == "print"
                    or (getattr(n.func, "attr", "") == "echo"
                        and getattr(n.func.value, "id", "") == "typer"))]

    assert not printed, f"{name} prints past the log format: {printed}"


@pytest.mark.parametrize("asked", ["json", None])
def test_a_worker_that_cannot_start_ends_with_its_sentence_in_the_format(monkeypatch, capsys,
                                                                         asked):
    from openfactory.runtime.temporal import worker
    from openfactory.runtime.temporal.connection import EngineNotListening

    sentence = "the durable engine at 127.0.0.1:7233 accepted no connection in 30s"

    async def _never_listens():
        raise EngineNotListening(sentence)

    if asked:
        monkeypatch.setenv(logs.FORMAT_VARIABLE, asked)
    monkeypatch.setattr(worker, "main", _never_listens)
    with _a_fresh_process(), pytest.raises(SystemExit) as ended:
        asyncio.run(worker.born())

    if asked:
        assert ended.value.code == 1
        (line,) = _json_lines(capsys.readouterr().err)
        assert (line["level"], line["message"]) == ("ERROR", f"worker: {sentence}"), line
    else:
        assert ended.value.code == f"worker: {sentence}"


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


def test_a_stack_asked_for_is_kept_on_its_one_line(monkeypatch, capsys):
    """`stack_info=True` is kept by the readable format; the JSON line keeps it too."""
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    with _a_fresh_process():
        logs.configure()
        logging.getLogger("openfactory.knowledge").warning("where was this asked", stack_info=True)

    (line,) = _json_lines(capsys.readouterr().err)
    assert line["stack"].startswith("Stack (most recent call last)"), line
    assert "test_a_stack_asked_for_is_kept_on_its_one_line" in line["stack"], line


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


def test_a_record_that_names_its_own_project_never_borrows_the_blocks_product(captured):
    with logs.about(project="acme", product="repo:acme/docs"):
        logging.getLogger("openfactory.test.about").info("its own", extra={"project": "initech"})

    (line,) = captured()
    assert (line.get("project"), line.get("product")) == ("initech", None), line


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """`acme` belongs to the product of its context repository; `globex` is a product of one;
    `broken` does not build, and is left out without a word."""
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"projects": {
        "acme": {"name": "acme", "repo_path": str(tmp_path),
                 "tracker": {"kind": "local", "repo": "acme"},
                 "product": {"docs_repo": "Acme/Docs"}},
        "globex": {"name": "globex", "repo_path": str(tmp_path),
                   "tracker": {"kind": "local", "repo": "globex"}},
        "broken": {"name": "broken", "tracker": "not a tracker"}}}))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(path))
    return path


#: What `registry` says each of its projects that builds belongs to.
PRODUCTS = {"acme": "repo:acme/docs", "globex": "project:globex"}

#: The name of the thread a read of the products runs on.
READER = "openfactory-log-products"


def _readers() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == READER]


def _landed(within: float = 5.0) -> None:
    """Wait for the read in flight, if there is one, to land — this process's, not a thread an
    earlier case left finishing."""
    deadline = time.monotonic() + within
    while logs._PRODUCTS._flight is not None:
        assert time.monotonic() < deadline, "the products' read did not land"
        time.sleep(0.005)


def _asked() -> bool:
    """Whether anything asked for the products to be read since the copy was last forgotten."""
    return logs._PRODUCTS._began is not None


class _Hung:
    """The registry's file read, counted, and hung until released — a mount that stopped."""

    def __init__(self, monkeypatch):
        from openfactory.registry import ProjectRegistry

        self.reads = 0
        self.gate = threading.Event()
        real = ProjectRegistry._load_raw

        def hangs(registry):
            self.reads += 1
            self.gate.wait(10)  # bounded, so a case that waits on it ends rather than hangs
            return real(registry)

        monkeypatch.setattr(ProjectRegistry, "_load_raw", hangs)


class _HeldExecutor(concurrent.futures.ThreadPoolExecutor):
    """The default executor the gate's verdict hops to, given ONE thread and that thread held: a
    caller that needs it waits until `release`. Counts what was handed to it besides the hold."""

    def __init__(self):
        super().__init__(max_workers=1)
        self.held = threading.Event()
        self.handed = 0
        super().submit(self.held.wait, 10)

    def submit(self, fn, /, *args, **kwargs):
        self.handed += 1
        return super().submit(fn, *args, **kwargs)

    def release(self):
        self.held.set()
        self.shutdown(wait=False)


@pytest.fixture
async def held_executor():
    loop = asyncio.get_running_loop()
    executor = _HeldExecutor()
    loop.set_default_executor(executor)
    yield executor
    executor.release()


def test_the_product_is_the_one_the_registry_says_and_only_for_json(registry, monkeypatch):
    logs.freshen_products()
    assert not _asked(), "the readable line carries no tag, so it must not pay for the registry"

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    logs.freshen_products()
    _landed()

    assert {name: logs._PRODUCTS.of(name) for name in (*PRODUCTS, "broken", "nobody")} == {
        **PRODUCTS, "broken": "", "nobody": ""}


async def test_a_line_takes_its_product_from_memory_and_never_waits_for_the_registry(
        registry, monkeypatch, captured, held_executor):
    """THE RULE OF THE COPY, under a registry that hangs and an executor that is full: three
    hundred lines about the registry's projects and about names nobody registered, each with the
    read asked for again, are written at once from the event loop; the registry is read ONCE, on a
    daemon thread of the log's own and not on the executor; the lines written before the read
    landed leave the product out; and once it lands, the copy holds the registry's projects and
    nothing a line named."""
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    hung = _Hung(monkeypatch)
    names = [*PRODUCTS, *(f"stranger-{n}" for n in range(98))] * 3

    started = time.monotonic()
    for name in names:
        logs.freshen_products()
        with logs.about(project=name):
            _say(f"about {name}")
    held = time.monotonic() - started
    readers = _readers()
    hung.gate.set()
    _landed()
    with logs.about(project="acme"):
        _say("after the read")
    with logs.about(project="stranger-after"):
        _say("a stranger after the read")

    *lines, stranger = captured()
    assert held < 2.0, f"{len(names)} lines held the loop {held:.1f}s"
    assert hung.reads == 1, f"the registry was read {hung.reads} times"
    assert readers and all(thread.daemon for thread in readers), readers
    assert held_executor.handed == 0, "a line took a thread of the default executor"
    assert all("product" not in line for line in lines[:-1]), lines[:3]
    assert (lines[-1]["project"], lines[-1]["product"]) == ("acme", PRODUCTS["acme"])
    assert "product" not in stranger, stranger
    assert logs._PRODUCTS._known == PRODUCTS, "the copy kept a name a line asked about"


def test_the_registry_is_read_once_per_window(registry, monkeypatch):
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    now = [1000.0]
    monkeypatch.setattr(logs, "_clock", lambda: now[0])
    hung = _Hung(monkeypatch)
    hung.gate.set()

    logs.freshen_products()
    _landed()
    now[0] += logs.PRODUCTS_WINDOW_S - 0.01
    logs.freshen_products()
    _landed()
    assert hung.reads == 1

    now[0] += 0.01
    logs.freshen_products()
    _landed()
    assert hung.reads == 2


def test_a_read_that_fails_keeps_the_products_last_read(registry, monkeypatch):
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    now = [1000.0]
    monkeypatch.setattr(logs, "_clock", lambda: now[0])
    logs.freshen_products()
    _landed()

    registry.write_text("projects: [this is: not, valid")
    now[0] += logs.PRODUCTS_WINDOW_S
    logs.freshen_products()
    _landed()

    assert logs._PRODUCTS.of("acme") == PRODUCTS["acme"]


def test_a_read_begun_before_forget_lands_nowhere(registry, monkeypatch):
    """Waited for by its own thread: after `forget` no read is in flight, so the slot cannot say
    when the one begun before it has finished."""
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    hung = _Hung(monkeypatch)
    before = set(_readers())
    logs.freshen_products()
    (begun,) = set(_readers()) - before
    logs.forget()
    hung.gate.set()
    begun.join(5)

    assert not begun.is_alive() and hung.reads == 1
    assert logs._PRODUCTS._known == {}


# ── the panel: every route that takes a project ─────────────────────────────────────────────────

def _routes_about_a_project():
    from fastapi.routing import APIRoute

    from openfactory.api.app import app

    return [r for r in app.routes if isinstance(r, APIRoute) and "project" in r.param_convertors]


def test_every_route_of_the_panel_is_built_to_say_its_project():
    from fastapi.routing import APIRoute

    from openfactory.api.app import app
    from openfactory.api.project_route import AboutItsProject

    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    about = [r for r in routes if "{project}" in r.path]

    assert len(about) > 20, [r.path for r in about]
    assert all(isinstance(r, AboutItsProject) for r in routes), [
        r.path for r in routes if not isinstance(r, AboutItsProject)]


def test_every_route_asks_the_gates_own_rule():
    """The rule the class asks is the gate's: a route it calls guarded is one the gate guards."""
    from openfactory.api.app import _gated

    routes = _routes_about_a_project()
    said = {r.path: type(r).gated(r.path) for r in routes}

    assert said == {r.path: _gated(r.path) for r in routes}
    assert set(said.values()) == {True, False}, "the sweep found only one side of the gate"


def _open_routes() -> list[str]:
    """Every GET route about a project that the gate leaves open, its parameters filled."""
    from openfactory.api.app import _gated

    return [re.sub(r"\{[^}]+\}", "acme", r.path) for r in _routes_about_a_project()
            if not _gated(r.path) and "GET" in (r.methods or set())]


def test_the_sweep_finds_the_shell():
    assert {"/p/acme", "/p/acme/board", "/logs/acme", "/product/acme"} <= set(_open_routes())


async def test_no_route_the_gate_leaves_open_takes_a_thread_or_reads_the_registry(
        registry, monkeypatch, held_executor):
    """THE GATE'S RULE, "AN UNGATED PATH NEVER TAKES A THREAD" (`app.py::_ask_the_gate`), WITH JSON
    ON. The second review's probe, made deterministic: the gate on, the registry hung, the default
    executor given one thread and that one held — and ten unauthenticated requests to every open
    route about a project, at once. Each answers; none was handed to the executor; the registry was
    not read. Before the fix each of them read the registry on that executor, so they queued behind
    it and so did every request the gate checks."""
    import httpx

    from openfactory.api.app import app

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", "the-operator")
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "null")
    hung = _Hung(monkeypatch)
    paths = _open_routes()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://panel", timeout=10) as client:
            answers = await asyncio.wait_for(
                asyncio.gather(*(client.get(path) for path in paths for _ in range(10))), 8.0)
    finally:
        hung.gate.set()

    assert {a.request.url.path: a.status_code for a in answers}.keys() == set(paths)
    assert all(a.status_code < 500 for a in answers), [(a.request.url.path, a.status_code)
                                                       for a in answers if a.status_code >= 500]
    assert held_executor.handed == 0, f"{held_executor.handed} requests took a thread"
    assert hung.reads == 0, f"the registry was read {hung.reads} times for nobody"


def _a_panel_of_the_same_class() -> FastAPI:
    """The routes the panel's class builds, with the panel's gate rule, and a handler of each kind:
    on the loop, on a worker thread, a stream, one the gate leaves open, and one whose path names
    no project."""
    from openfactory.api.app import _gated
    from openfactory.api.project_route import AboutItsProject

    app = FastAPI()
    app.router.route_class = AboutItsProject.gated_by(_gated)

    @app.get("/api/board/{project}")
    async def on_the_loop(project: str) -> dict:
        _say("on the loop")
        return {}

    @app.get("/api/loops/{project}")
    def on_a_thread(project: str) -> dict:
        _say("on a thread")
        return {}

    @app.get("/api/jobs/{project}/{issue}/stream")
    async def a_stream(project: str, issue: str) -> StreamingResponse:
        _say("in the handler")

        async def body():
            _say("in the stream's body")
            yield b"data: x\n\n"
            _say("at the stream's end")

        return StreamingResponse(body(), media_type="text/event-stream")

    @app.get("/p/{project}")
    def the_shell(project: str) -> dict:
        _say("the shell")
        return {}

    @app.get("/api/budget")
    def about_no_project() -> dict:
        _say("about no project")
        return {}

    return app


def test_a_panel_route_about_a_project_says_it_and_its_product(registry, monkeypatch, captured):
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    client = TestClient(_a_panel_of_the_same_class())
    assert client.get("/api/budget").status_code == 200
    assert not _asked(), "a route about no project asked for the registry"
    assert client.get("/p/globex").status_code == 200
    assert not _asked(), "a route the gate leaves open asked for the registry"
    assert client.get("/api/board/acme").status_code == 200
    assert _asked(), "a route behind the gate never asked for the products"
    _landed()
    before = len(captured())

    for path in ("/api/board/acme", "/api/loops/globex", "/api/jobs/acme/7/stream", "/p/globex",
                 "/api/budget"):
        assert client.get(path).status_code == 200, path

    said = {line["message"]: (line.get("project"), line.get("product"))
            for line in captured()[before:]}
    assert said == {"on the loop": ("acme", PRODUCTS["acme"]),
                    "on a thread": ("globex", PRODUCTS["globex"]),
                    "in the handler": ("acme", PRODUCTS["acme"]),
                    "in the stream's body": ("acme", PRODUCTS["acme"]),
                    "at the stream's end": ("acme", PRODUCTS["acme"]),
                    "the shell": ("globex", PRODUCTS["globex"]),
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
    assert not _asked(), "an activity that carries its product asked for the registry"
    hung = _Hung(monkeypatch)
    globex = [_model_about(typing.get_type_hints(run_job)["inp"], "globex")[0]]
    await _run(run_job, globex)
    hung.gate.set()
    _landed()
    await _run(run_job, globex)

    first, before, after = captured()
    assert (first["project"], first["product"]) == ("acme", "carried")
    assert (before["project"], before.get("product")) == ("globex", None), before
    assert (after["project"], after["product"]) == ("globex", PRODUCTS["globex"])


@pytest.mark.parametrize("fn", _activities(), ids=lambda fn: fn.__name__)
async def test_every_activity_runs_at_once_with_the_registry_hung_and_the_executor_full(
        captured, registry, monkeypatch, held_executor, fn):
    """THE INTERCEPTOR WAITS FOR NOTHING: with JSON on, the registry hung and the default executor
    the activities' own `to_thread` shares held, every activity still starts at once and says its
    project — it used to read the product on that executor first, once per activity."""
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    hung = _Hung(monkeypatch)
    args, names = _arguments_about(fn, "acme")
    try:
        assert await asyncio.wait_for(_run(fn, args), 2.0) == "done"
    finally:
        hung.gate.set()

    (line,) = captured()
    assert line.get("project") == ("acme" if names else None), (fn.__name__, line)
    assert held_executor.handed == 0, fn.__name__


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


# ── the durable engine client's own core ────────────────────────────────────────────────────────

class _Runtimes:
    """`temporalio.runtime.Runtime` and `Client.connect`, recorded: the telemetry each runtime was
    built with, and the runtime each client was made on — so a case reads the configuration, and
    no core is started."""

    def __init__(self, monkeypatch):
        from openfactory.runtime.temporal import connection

        self.built: list = []
        self.clients: list = []
        recorder = self

        class _Runtime:
            def __init__(self, *, telemetry):
                self.telemetry = telemetry
                recorder.built.append(self)

        async def _connect(*_a, **kwargs):
            recorder.clients.append(kwargs.get("runtime"))
            return object()

        monkeypatch.setattr(connection, "Runtime", _Runtime)
        monkeypatch.setattr(connection.Client, "connect", _connect)
        monkeypatch.setenv("TEMPORAL_ADDRESS", "localhost:7233")


def _a_line_of_the_core(level: int, message: str):
    """A log entry as the client's core hands it over (`temporalio.bridge.runtime`)."""
    return types.SimpleNamespace(level=level, target="temporalio_client::retry", message=message,
                                 fields={"code": "Unavailable"}, time=time.time())


async def test_with_json_lines_every_engine_client_has_a_runtime_whose_core_writes_through_the_log(
        monkeypatch, capsys):
    """Read off what `connection.connect()` — the one door every engine client of the worker, the
    panel and the CLI is made through — hands each client: a runtime of its own (one shared would
    stop forwarding for all the moment one client is dropped: the bridge's `Drop` aborts their
    one forwarder), whose core forwards its lines to `CORE_LOGGER` at the library's own default
    filter; and a line forwarded that way is a JSON line on stderr."""
    from temporalio.runtime import LoggingConfig

    from openfactory.runtime.temporal import connection

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    runtimes = _Runtimes(monkeypatch)

    await connection.connect()
    await connection.connect()

    assert len(runtimes.built) == 2 and runtimes.clients == runtimes.built, (
        "every client is made on a runtime of its own", runtimes.clients, runtimes.built)
    for runtime in runtimes.built:
        said = runtime.telemetry.logging
        assert said.forwarding is not None, "the core still writes its own lines"
        assert said.forwarding.logger.name == connection.CORE_LOGGER
        assert said.filter == LoggingConfig.default.filter, (
            "the core is asked for more than it says by default", said.filter)

    with _a_fresh_process():
        logs.configure()
        runtimes.built[0].telemetry.logging.forwarding._on_logs([
            _a_line_of_the_core(logging.WARNING, "gRPC call poll_activity_task_queue retried"),
            _a_line_of_the_core(logging.INFO, "a core's chatter")])
    written = capsys.readouterr()
    assert not written.out.strip(), written.out
    (line,) = _json_lines(written.err)
    assert line["level"] == "WARNING" and line["logger"].startswith(connection.CORE_LOGGER), line
    assert "poll_activity_task_queue retried" in line["message"], line


@pytest.mark.parametrize("asked", [None, "text"])
async def test_without_json_the_engines_runtime_is_left_as_it_was(monkeypatch, asked):
    from openfactory.runtime.temporal import connection

    if asked:
        monkeypatch.setenv(logs.FORMAT_VARIABLE, asked)
    runtimes = _Runtimes(monkeypatch)

    await connection.connect()

    assert runtimes.built == [] and runtimes.clients == [None]


@activity.defn(name="nothing_at_all")
async def _nothing_at_all() -> None:
    return None


@pytest.mark.owns_its_engine
async def test_a_core_warning_arrives_as_a_json_line_after_another_client_is_gone(
        monkeypatch, capsys):
    """THE THIRD REVIEW'S MEASUREMENT, ON A REAL ENGINE. The worker drops one-shot clients at boot
    (`schedule.ensure_all`), and with one shared runtime that silenced its core for good: the
    bridge aborts a runtime's one forwarder when any client of it is dropped. So: a client made
    through `connect()` is dropped, then a worker polls on another — and the core's own warning
    must still reach the log, as a JSON line, and no line may be anything else. The time-skipping
    engine makes the core warn as the worker starts; if it ever stops, the engine goes away under
    the worker, whose polls then retry and warn.

    THE WORKER IS STOPPED HERE ON EVERY PATH, AND WAITED FOR WITHIN A BOUND: a case that failed
    with its worker still polling a dead engine left it to the loop's teardown, and one mutation
    run of this file hung for hours there."""
    import gc
    import uuid

    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    from openfactory.runtime.temporal import connection

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    for name in ("TEMPORAL_API_KEY", "TEMPORAL_TLS_CERT", "TEMPORAL_TLS_KEY", "TEMPORAL_NAMESPACE"):
        monkeypatch.delenv(name, raising=False)
    seen: list[dict] = []
    strays: list[str] = []
    core: list[dict] = []
    stopped = False
    env = await WorkflowEnvironment.start_time_skipping()
    engine_up = True
    try:
        with _a_fresh_process():
            logs.configure()
            monkeypatch.setenv("TEMPORAL_ADDRESS", env.client.service_client.config.target_host)
            gone = await connection.connect()
            del gone
            gc.collect()
            client = await connection.connect()
            worker = Worker(client, task_queue=f"q-{uuid.uuid4().hex}",
                            activities=[_nothing_at_all])
            polling = asyncio.create_task(worker.run())
            try:
                core = await _the_cores_lines(capsys, seen, strays, within=5.0)
                if not core and not strays:
                    await env.shutdown()
                    engine_up = False
                    core = await _the_cores_lines(capsys, seen, strays, within=30.0)
            finally:
                polling.cancel()
                finished, _pending = await asyncio.wait({polling}, timeout=15.0)
                stopped = polling in finished
    finally:
        if engine_up:
            await env.shutdown()

    assert stopped, "the worker did not stop within 15 s of being cancelled"
    assert not strays, f"lines that are not one JSON object: {strays[:3]}"
    assert core, "no line from the engine client's core reached the log"
    assert core[0]["level"] == "WARNING", core[0]


async def _the_cores_lines(capsys, seen: list[dict], strays: list[str], *,
                           within: float) -> list[dict]:
    """Read what was written until a line from the engine client's core is among the JSON lines,
    a line that is not JSON is (`strays`), or `within` seconds pass; `seen` keeps every JSON line
    across reads. Never raises, so its caller always stops its worker."""
    from openfactory.runtime.temporal import connection

    deadline = time.monotonic() + within
    while True:
        written = capsys.readouterr()
        for line in (*written.out.splitlines(), *written.err.splitlines()):
            if not line.strip():
                continue
            try:
                said = json.loads(line)
            except ValueError:
                said = None
            if isinstance(said, dict) and list(said)[:4] == list(FIELDS):
                seen.append(said)
            else:
                strays.append(line[:300])
        core = [line for line in seen if line["logger"].startswith(connection.CORE_LOGGER)]
        if core or strays or time.monotonic() >= deadline:
            return core
        await asyncio.sleep(0.1)
