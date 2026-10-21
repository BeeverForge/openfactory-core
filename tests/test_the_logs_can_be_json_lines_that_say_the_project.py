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
  · NOTHING THE PACKAGE RUNS WRITES PAST THE FORMAT (fourth review of #818): every write to a
    process's own stdout or stderr in `openfactory/` — read off each module's syntax tree — goes
    through `logs.announce`, or sits where only a box's own program, a command run from a terminal
    or a process of its own reaches it, each with its reason; and Python's own lines — a warning,
    an exception nobody caught, in any thread, and one nobody could raise — are JSON lines too, a
    start that fails included;
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
import gc
import inspect
import io
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import types
import typing
import weakref
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[1]
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


# ── nothing the package runs writes past the format (fourth review of #818) ─────────────────────

#: Where the package writes to its process's own stdout or stderr by itself, by file and by the
#: function the write is in (`*`: the whole module), each with the reason that code is never the
#: worker's or the panel's. Every other such write is a plain line among the JSON ones: the fourth
#: review of #818 measured seven in the code a worker's jobs run, the pre-flight that could not size
#: among them, which a log store that drops what it cannot parse drops first. A module's
#: `if __name__ == "__main__":` block runs only as a process of its own, and needs no row.
OUTSIDE_THE_LOG = {
    "openfactory/cli.py": {
        "*": "the CLI, which answers a person at a terminal — save the commands that become the "
             "deployment's own processes (`BECOME_A_PROCESS`)"},
    "openfactory/cli_refusals.py": {"*": "the CLI's refusals, which only the CLI imports"},
    "openfactory/observability/logs.py": {
        "announce": "the one door for a line for a person: it prints only where the process's "
                    "lines are not JSON",
        "configure": "hands stderr to the log's own handler"},
    "openfactory/observability/health.py": {
        "probe": "the probe a healthcheck runs, a process of its own (`python -m "
                 "openfactory.observability.health`) whose stderr `docker inspect` shows"},
    "openfactory/runtime/boxed_job.py": dict.fromkeys(
        ("_options", "_no_identity", "_a_count", "run_boxed", "run_ci_repair", "run_review_pass",
         "_emit"),
        "the program a remote box runs (`python -m openfactory.runtime.boxed_job`), reached from "
        "its `main` only: its stdout is the box's log, whose result line the host parses"),
    "openfactory/runtime/temporal/schedule.py": {
        "main": "`python -m openfactory.runtime.temporal.schedule`, an operator's command"},
    "openfactory/runtime/temporal/starter.py": {
        "main": "`python -m openfactory.runtime.temporal.starter`, an operator's command"},
    "openfactory/api/openapi.py": {
        "main": "`python -m openfactory.api.openapi`, which writes the contract's document"},
    "openfactory/adapters/extract/pdf.py": {
        "main": "the extraction's child process, whose stdout is the pipe its parent reads"},
    "openfactory/product/evaluation/__main__.py": {
        "*": "`make eval-product`, a battery run from a terminal"},
    "openfactory/testing/local_flow.py": {
        "FlowRun.print_trace": "the local flow's trace, printed for a person at a terminal"},
    "openfactory/policy/test_work.py": {
        "admissible": "the Core, which may not import the log (`test_the_core_boundary.py`) — "
                      "and nothing in the package calls it: the orchestrator asks `refusal_for` "
                      "and logs the refusal itself (`orchestrator/machine.py`)"},
}

#: The commands of a module allowed whole above that become the deployment's own long-running
#: processes — the panel's `serve` and `openfactory worker` — where nothing may write past it.
BECOME_A_PROCESS = {"openfactory/cli.py": ("serve", "worker_cmd")}

_STREAMS = {"stdout", "stderr", "__stdout__", "__stderr__"}
_ECHOES = {"typer", "click"}


def _is_main_block(node: ast.AST) -> bool:
    return (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__"
            and any(isinstance(c, ast.Constant) and c.value == "__main__"
                    for c in node.test.comparators))


def _what_writes(node: ast.AST) -> str:
    """What `node` writes to its process's own stdout or stderr, or `""`."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "sys" and node.attr in _STREAMS:
            return f"sys.{node.attr}"
    if isinstance(node, ast.ImportFrom) and node.module == "sys":
        named = [alias.name for alias in node.names if alias.name in _STREAMS]
        return f"from sys import {', '.join(named)}" if named else ""
    if not isinstance(node, ast.Call):
        return ""
    func = node.func
    if isinstance(func, ast.Name) and func.id == "print":
        return "print(…)"
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        owner, name = func.value.id, func.attr
        if owner in _ECHOES and name in ("echo", "secho"):
            return f"{owner}.{name}(…)"
        if owner == "traceback" and name.startswith("print_"):
            return f"traceback.{name}(…)"
        if (owner, name) == ("os", "write") and node.args and isinstance(
                node.args[0], ast.Constant) and node.args[0].value in (1, 2):
            return f"os.write({node.args[0].value}, …)"
    return ""


def _writes(tree: ast.AST) -> list[tuple[str, int, str]]:
    """Every write `tree` makes to its process's stdout or stderr by itself, as `(where, line,
    what)` — `where` is the function it sits in (`Class.method`, `outer.inner`), `__main__` for
    the module's main block, `""` for the module's own top level."""
    found: list[tuple[str, int, str]] = []

    def visit(node: ast.AST, where: str) -> None:
        for child in ast.iter_child_nodes(node):
            what = _what_writes(child)
            if what:
                found.append((where, child.lineno, what))
            inner = where
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = f"{where}.{child.name}" if where else child.name
            elif not where and _is_main_block(child):
                inner = "__main__"
            visit(child, inner)

    visit(tree, "")
    return found


def _the_package_writes() -> list[tuple[str, str, int, str]]:
    return [(path.relative_to(ROOT).as_posix(), where, line, what)
            for path in sorted((ROOT / "openfactory").rglob("*.py"))
            for where, line, what in _writes(ast.parse(path.read_text(encoding="utf-8")))]


def _allowed(path: str, where: str) -> bool:
    outermost = where.split(".", 1)[0]
    if outermost in BECOME_A_PROCESS.get(path, ()):
        return False
    if outermost == "__main__":
        return True
    rows = OUTSIDE_THE_LOG.get(path, {})
    return "*" in rows or any(where == row or where.startswith(f"{row}.") for row in rows)


def test_nothing_the_worker_or_the_panel_runs_writes_past_the_log():
    """Read off every module's syntax tree: each write to the process's own stdout or stderr goes
    through `logs.announce`, which prints or logs as the process's lines are — or it sits where
    the worker and the panel never run it, said in `OUTSIDE_THE_LOG`. A `print` added to an
    activity tomorrow is named here before it is a plain line in a deployment's log."""
    past = [f"{path}:{line} in {where or 'the module'}: {what}"
            for path, where, line, what in _the_package_writes() if not _allowed(path, where)]

    assert not past, ("these write past the log format — send each through `logs.announce` at "
                      "its level, or say in OUTSIDE_THE_LOG why no deployment process runs it:\n"
                      + "\n".join(past))


#: Every way of writing to the process's own streams the sweep must see, as a statement. A sweep
#: blind to one of them would pass the package above with that one in it.
WAYS_OF_WRITING = {
    "print": "print('a line')",
    "print to stderr": "print('a line', file=sys.stderr)",
    "a stream written": "sys.stdout.write('a line')",
    "Python's own stream": "sys.__stderr__.write('a line')",
    "a stream imported": "from sys import stderr",
    "typer": "typer.echo('a line')",
    "click": "click.secho('a line')",
    "a traceback": "traceback.print_exc()",
    "a descriptor": "os.write(2, b'a line')",
}


@pytest.mark.parametrize("way", sorted(WAYS_OF_WRITING))
def test_the_sweep_sees_every_way_of_writing_and_where_it_is(way):
    said = WAYS_OF_WRITING[way]
    placed = {
        "f": f"def f():\n    {said}\n",
        "C.m": f"class C:\n    def m(self):\n        {said}\n",
        "f.inner": f"async def f():\n    def inner():\n        {said}\n",
        "__main__": f"if __name__ == '__main__':\n    {said}\n",
        "": f"{said}\n",
    }
    for where, module in placed.items():
        found = {w for w, _line, _what in _writes(ast.parse(
            "import click, os, sys, traceback, typer\n" + module))}
        assert found == {where}, (way, where, found)


def test_every_place_the_sweep_lets_write_still_writes():
    """A row with no write left under it is a door left open for whatever comes next; a process's
    command that no longer exists guards nothing."""
    found: dict[str, set[str]] = {}
    for path, where, _line, _what in _the_package_writes():
        found.setdefault(path, set()).add(where)
    stale = [f"{path} :: {row}" for path, rows in OUTSIDE_THE_LOG.items() for row in rows
             if not any(row == "*" or where == row or where.startswith(f"{row}.")
                        for where in found.get(path, ()))]
    commands = {path: {node.name for node in ast.parse((ROOT / path).read_text()).body
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
                for path in BECOME_A_PROCESS}

    assert not stale, f"rows that allow a write nothing makes any more: {stale}"
    assert all(set(names) <= commands[path] for path, names in BECOME_A_PROCESS.items()), (
        BECOME_A_PROCESS, commands)


@pytest.mark.parametrize("level", [logging.INFO, logging.WARNING])
def test_a_line_for_a_person_is_printed_or_is_a_json_line_at_its_level(monkeypatch, capsys,
                                                                       level):
    said = "OPENFACTORY_PREFLIGHT: DEGRADED for acme#7 — sizer: the harness token is not set"
    logger = logging.getLogger("openfactory.test.announce")
    with _a_fresh_process():
        logs.configure()
        logs.announce(logger, said, level)
    written = capsys.readouterr()
    assert written.out.splitlines() == [said] and not written.err.strip(), written

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    with _a_fresh_process():
        logs.configure()
        logs.announce(logger, said, level)
    written = capsys.readouterr()
    assert not written.out.strip(), written.out
    (line,) = _json_lines(written.err)
    assert (line["level"], line["logger"], line["message"]) == (
        logging.getLevelName(level), logger.name, said), line


def test_a_process_that_never_set_up_its_log_prints_whatever_the_variable_says(monkeypatch,
                                                                              capsys):
    """A box's own program never calls `configure`, and its stdout is the box's log, whose last
    line the host parses: the variable reaching it changes nothing there."""
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    said = "OPENFACTORY_RESUME: continuing build session 7f0c"
    with _a_fresh_process():
        logs.announce(logging.getLogger("openfactory.test.announce"), said, logging.WARNING)

    written = capsys.readouterr()
    assert written.out.splitlines() == [said] and not written.err.strip(), written


class _RunsItsBody:
    """Below the worker's interceptor: the activity's body, run as the activity runs it."""

    async def execute_activity(self, input: ExecuteActivityInput):
        return await input.fn(*input.args)


async def test_what_a_job_says_for_a_person_is_a_json_line_about_its_project(monkeypatch,
                                                                             capsys):
    """THE FOURTH REVIEW'S MEASUREMENT. The worker's real `_do_coordinate` — what
    `coordinator_advise` runs on its thread — through the worker's own interceptor, with the judge
    failing: the path where a parked decision gets no advice. It printed a plain line on stdout,
    saying no project, beside the warning a JSON line said with one."""
    from openfactory.runtime.temporal import activities
    from openfactory.runtime.temporal.interceptors import AboutItsProject
    from openfactory.runtime.temporal.io import CoordinatorItem

    def _no_judge(_project):
        raise RuntimeError("no judge is configured on this bench")

    async def _coordinator(item):
        return await asyncio.to_thread(activities._do_coordinate, item)

    monkeypatch.setattr(activities, "_judge_for", _no_judge)
    item = CoordinatorItem(project="acme", issue="7", job_id="of-acme-7")
    inbound = AboutItsProject().intercept_activity(_RunsItsBody())
    for asked in (None, "json"):
        if asked:
            monkeypatch.setenv(logs.FORMAT_VARIABLE, asked)
        with _a_fresh_process():
            logs.configure()
            assert await inbound.execute_activity(ExecuteActivityInput(
                fn=_coordinator, args=[item], executor=None, headers={})) == {}
        written = capsys.readouterr()
        if not asked:
            assert "OPENFACTORY_COORDINATOR: no parseable advice for acme#7" in (
                written.out.splitlines()), written.out
            continue
        assert not written.out.strip(), f"a plain line beside the JSON: {written.out!r}"
        lines = _json_lines(written.err)
        said = [line for line in lines if "OPENFACTORY_COORDINATOR" in line["message"]]
        assert len(said) == 1 and said[0]["level"] == "WARNING", lines
        assert all(line.get("project") == "acme" for line in lines), lines


def test_what_the_panel_says_before_it_serves_is_a_json_line(monkeypatch, capsys, tmp_path):
    """`serve`'s own start, before uvicorn takes the process (fifth review of #818, measured: a
    build the panel could not record — a state directory that is not one — warned before the log
    was set up, through Python's last-resort handler, a bare line with no time, level or name)."""
    import uvicorn

    from openfactory import cli, namespace

    not_a_directory = tmp_path / "state"
    not_a_directory.write_text("a file where the state directory should be\n")
    monkeypatch.setenv("OPENFACTORY_STATE_DIR", str(not_a_directory / "deployment"))
    monkeypatch.setattr(namespace, "build_stamp", lambda: ("3f9a1c0e2b7d", "2026-10-19T00:00Z"))
    monkeypatch.setattr(uvicorn, "run", lambda *_a, **_k: None)
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    with _a_fresh_process():
        cli.serve(host="127.0.0.1", port=8787)

    written = capsys.readouterr()
    assert not written.out.strip(), written.out
    lines = _json_lines(written.err)
    assert any(line["logger"] == namespace.log.name and "could not record" in line["message"]
               for line in lines), lines


def test_the_live_feed_keeps_its_envelope_inside_a_json_line(monkeypatch, capsys):
    """The pre-flight's live feed has no box: the worker streams it through the stdout sink
    (`activities._pf_emit`). With JSON lines the envelope is the message of one, prefix and all,
    so a reader of the feed finds it whole; a box's program prints it as it always did."""
    from openfactory.observability.events import JobEvent, StdoutEventSink, now_iso

    event = JobEvent(ts=now_iso(), job_id="openfactory-acme-7", ticket_id="7", kind="state",
                     message="sizing")
    envelope = "OPENFACTORY_EVENT:" + event.model_dump_json()
    with _a_fresh_process():
        StdoutEventSink().emit(event)
    assert capsys.readouterr().out.splitlines() == [envelope]

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    with _a_fresh_process():
        logs.configure()
        StdoutEventSink().emit(event)
    written = capsys.readouterr()
    assert not written.out.strip(), written.out
    (line,) = _json_lines(written.err)
    assert (line["level"], line["logger"], line["message"]) == (
        "INFO", "openfactory.journal", envelope), line


#: The level each line for a person is said at with JSON lines, by where it is said — its file, the
#: function it sits in, and the first words of the line. A line that says a degraded or failed
#: path must never be silent, so it is a WARNING: with `OPENFACTORY_LOG_LEVEL=WARNING` an INFO line
#: is dropped (fifth review of #818: the degraded pre-flight put back at INFO survived every test).
#: The call sites are read off the package; one that is not here fails the case below, so a line
#: added tomorrow is classed by whoever adds it.
NEVER_SILENT, SAID_FOR_THE_RECORD = "WARNING", "INFO"
LINE_LEVELS = {
    ("openfactory/runtime/temporal/activities.py", "_do_preflight.degrade",
     "OPENFACTORY_PREFLIGHT: DEGRADED for "): NEVER_SILENT,
    ("openfactory/runtime/temporal/activities.py", "_do_preflight",
     "OPENFACTORY_PREFLIGHT: unparseable verdict ("): NEVER_SILENT,
    ("openfactory/runtime/temporal/activities.py", "_do_coordinate",
     "OPENFACTORY_COORDINATOR: no parseable advice for "): NEVER_SILENT,
    ("openfactory/runtime/temporal/activities.py", "_do_diagnose",
     "OPENFACTORY_TECHLEAD: no parseable handoff for "): NEVER_SILENT,
    ("openfactory/adapters/sandbox/container.py", "ContainerSandbox.prepare",
     "OPENFACTORY: removing the leftover box "): NEVER_SILENT,
    ("openfactory/adapters/sandbox/container.py", "ContainerSandbox.prepare",
     "OPENFACTORY: could not remove the leftover box "): NEVER_SILENT,
    ("openfactory/adapters/agent/claude_code.py", "_snapshot_session",
     "OPENFACTORY_RESUME: the session snapshot is "): NEVER_SILENT,
    ("openfactory/adapters/agent/claude_code.py", "_snapshot_session",
     "OPENFACTORY_RESUME: "): NEVER_SILENT,
    ("openfactory/adapters/agent/claude_code.py", "_snapshot_session",
     "OPENFACTORY_RESUME: session snapshot failed ("): NEVER_SILENT,
    ("openfactory/adapters/agent/claude_code.py", "_restore_session",
     "OPENFACTORY_RESUME: session restore failed ("): NEVER_SILENT,
    ("openfactory/adapters/agent/claude_code.py", "ClaudeCodeAdapter._invoke",
     "OPENFACTORY_TOKEN: token '"): NEVER_SILENT,
    ("openfactory/adapters/agent/claude_code.py", "ClaudeCodeAdapter._resume_session_for",
     "OPENFACTORY_RESUME: restored state lacks session "): NEVER_SILENT,
    ("openfactory/adapters/agent/claude_code.py", "ClaudeCodeAdapter._resume_session_for",
     "OPENFACTORY_RESUME: continuing "): SAID_FOR_THE_RECORD,
    ("openfactory/observability/events.py", "StdoutEventSink.emit", ""): SAID_FOR_THE_RECORD,
    ("openfactory/runtime/temporal/worker.py", "main",
     "openfactory worker up · "): SAID_FOR_THE_RECORD,
    ("openfactory/cli.py", "serve", "panel: http://"): SAID_FOR_THE_RECORD,
}


def _first_words(node: ast.AST) -> str:
    """The first literal text of a line as its call site writes it: an f-string's first part, or
    `""` when the line is built from names alone."""
    for inner in ast.walk(node):
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            return inner.value
    return ""


def _the_lines_said_for_a_person() -> dict[tuple[str, str, str], list[str]]:
    """`{(file, function, first words): [level, …]}` for every `logs.announce(…)` in the package,
    the level as its call site hands it (INFO when it hands none)."""
    found: dict[tuple[str, str, str], list[str]] = {}

    def visit(node: ast.AST, path: str, where: str) -> None:
        for child in ast.iter_child_nodes(node):
            if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "announce" and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == "logs" and len(child.args) >= 2):
                given = child.args[2] if len(child.args) > 2 else next(
                    (k.value for k in child.keywords if k.arg == "level"), None)
                level = "INFO" if given is None else ast.unparse(given).rsplit(".", 1)[-1]
                found.setdefault((path, where, _first_words(child.args[1])), []).append(level)
            inner = where
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = f"{where}.{child.name}" if where else child.name
            visit(child, path, inner)

    for module in sorted((ROOT / "openfactory").rglob("*.py")):
        rel = module.relative_to(ROOT).as_posix()
        visit(ast.parse(module.read_text(encoding="utf-8")), rel, "")
    return found


def test_a_line_that_must_never_be_silent_is_said_at_warning():
    """Read off every call site of `logs.announce`: each is classed in `LINE_LEVELS`, once, and
    hands the level its class says — so a degraded or failed path is a WARNING with JSON lines, and
    survives `OPENFACTORY_LOG_LEVEL=WARNING`."""
    said = _the_lines_said_for_a_person()

    assert set(said) == set(LINE_LEVELS), (
        "lines for a person nobody classed:", sorted(set(said) - set(LINE_LEVELS)),
        "classes with no line left:", sorted(set(LINE_LEVELS) - set(said)))
    wrong = {where: levels for where, levels in said.items()
             if levels != [LINE_LEVELS[where]]}
    assert not wrong, f"said at another level than its class, or twice from one place: {wrong}"
    assert {NEVER_SILENT, SAID_FOR_THE_RECORD} == set(LINE_LEVELS.values())


# ── Python's own lines (fourth review of #818) ──────────────────────────────────────────────────

#: What Python writes on stderr by itself, by what causes it: the code, and the logger, level and
#: exception its JSON line says. Each runs in a process of its own, after `logs.configure()`, as a
#: process of the deployment would.
PYTHONS_OWN = {
    "a warning": ("import warnings\nwarnings.warn('a library warned')\n",
                  "py.warnings", "WARNING", "UserWarning"),
    "an exception nobody caught": ("raise RuntimeError('nobody caught this')\n",
                                   logs.UNCAUGHT_LOGGER, "ERROR", "RuntimeError"),
    "one that ends a thread": (
        "import threading\n"
        "sweep = threading.Thread(target=lambda: 1 / 0, name='a-sweep')\n"
        "sweep.start()\nsweep.join()\n", logs.UNCAUGHT_LOGGER, "ERROR", "ZeroDivisionError"),
    "one nobody could raise": (
        "class _Gone:\n    def __del__(self):\n        raise ValueError('raised in a finaliser')\n"
        "_Gone()\n", logs.UNCAUGHT_LOGGER, "WARNING", "ValueError"),
}

#: Every level `OPENFACTORY_LOG_LEVEL` can name, read off the `logging` module `logs.level()` asks
#: (one name for each, an alias such as `WARN` naming the same one), and the variable unset.
LEVELS = ["unset", *sorted({value: name for name, value
                            in logging.getLevelNamesMapping().items()}.values())]


def _a_process_of_its_own(script: str, *, asked: str | None,
                          level: str = "unset") -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in (logs.FORMAT_VARIABLE, logs.LEVEL_VARIABLE, logs.DEPLOYMENT_VARIABLE)}
    if asked:
        env[logs.FORMAT_VARIABLE] = asked
    if level != "unset":
        env[logs.LEVEL_VARIABLE] = level
    return subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)


def _every_line_is_json(ran: subprocess.CompletedProcess) -> list[dict]:
    """Every line the process wrote, on either stream, parsed: one JSON object with the four
    fields first, or the case fails naming the line."""
    lines = []
    for line in (*ran.stdout.splitlines(), *ran.stderr.splitlines()):
        if not line.strip():
            continue
        try:
            said = json.loads(line)
        except ValueError:
            said = None
        assert isinstance(said, dict) and list(said)[:4] == list(FIELDS), (
            f"a line that is not one JSON object: {line!r}")
        lines.append(said)
    return lines


@pytest.mark.parametrize("level_set", LEVELS)
@pytest.mark.parametrize("cause", sorted(PYTHONS_OWN))
def test_what_python_writes_by_itself_is_a_json_line(cause, level_set):
    """Each of Python's own reports is one JSON line — WHATEVER `OPENFACTORY_LOG_LEVEL` SAYS, as
    Python's own hooks write whatever any level is (review requesting changes on 3cd816ac: with the
    level at CRITICAL, an exception that ended the process, or a thread, wrote nothing at all)."""
    code, logger, level, kind = PYTHONS_OWN[cause]
    ran = _a_process_of_its_own(
        "from openfactory.observability import logs\nlogs.configure()\n" + code, asked="json",
        level=level_set)

    lines = _every_line_is_json(ran)
    said = [line for line in lines if line["logger"] == logger]
    assert len(said) == 1 and said[0]["level"] == level, (cause, lines)
    assert kind in said[0]["message"] + said[0].get("exception", ""), said[0]
    assert ran.returncode == (1 if cause == "an exception nobody caught" else 0), ran.returncode


def test_a_thread_that_exits_says_nothing():
    """A thread ended by `SystemExit` is a thread that chose to stop: Python's own hook says
    nothing for it, and neither does the log's."""
    ran = _a_process_of_its_own(
        "from openfactory.observability import logs\nlogs.configure()\nimport threading\n"
        "def _done():\n    raise SystemExit(3)\n"
        "ended = threading.Thread(target=_done, name='a-sweep')\nended.start()\nended.join()\n",
        asked="json")

    assert not (ran.stdout + ran.stderr).strip(), (ran.stdout, ran.stderr)
    assert ran.returncode == 0


#: An object's address in what Python writes, which differs from one process to the next.
_AN_ADDRESS = re.compile(r"0x[0-9a-fA-F]+")


@pytest.mark.parametrize("level_set", LEVELS)
def test_without_json_python_writes_as_it_always_did(level_set):
    """`configure` hands Python's hooks to the log only for JSON lines; the readable format leaves
    every one of them as Python has it, at every level: the process writes what the same code
    writes in a process whose log nobody configured. Asked of THIS Python, not spelled here — its
    words change between releases (3.14 says "Exception ignored while calling deallocator" where
    3.13 says "Exception ignored in"), and the package runs on every Python from 3.12."""
    causes = ("".join(code for cause, (code, *_said) in sorted(PYTHONS_OWN.items())
                      if cause != "an exception nobody caught")
              + PYTHONS_OWN["an exception nobody caught"][0])
    ran = _a_process_of_its_own(
        "from openfactory.observability import logs\nlogs.configure()\n" + causes, asked=None,
        level=level_set)
    # The same lines above the causes, so a traceback names the same line numbers.
    bare = _a_process_of_its_own(
        "from openfactory.observability import logs\nlogs.__name__\n" + causes, asked=None,
        level=level_set)

    logged = [line for line in ran.stderr.splitlines() if LINE.match(line) or line.startswith("{")]
    assert not logged, f"Python's own lines went through the log: {logged}"
    assert _AN_ADDRESS.sub("0x", ran.stderr) == _AN_ADDRESS.sub("0x", bare.stderr), (
        ran.stderr, bare.stderr)
    for cause, (*_how, kind) in PYTHONS_OWN.items():
        assert kind in ran.stderr, (cause, ran.stderr)
    assert ran.returncode == bare.returncode == 1


#: The two doors a worker is started through, and the line that starts it there: the module's
#: own `-m` block, run as compose and `openfactory up` run it, and the CLI's command.
WORKER_DOORS = {
    "python -m openfactory.runtime.temporal.worker": (
        "import runpy\n"
        "runpy.run_module('openfactory.runtime.temporal.worker', run_name='__main__')\n"),
    "openfactory worker": (
        "from openfactory import cli\ncli.app(['worker'], prog_name='openfactory')\n"),
}


@pytest.mark.parametrize("door", sorted(WORKER_DOORS))
def test_a_start_that_fails_for_any_other_reason_ends_as_one_json_line(door):
    """`born` says an engine that never listened as a sentence; any other failure of the start —
    here the app key the boot writes first — escapes it. With JSON lines it must still end as
    one line, its traceback inside it, and exit 1, through either door."""
    ran = _a_process_of_its_own(
        "import dotenv\n"
        "dotenv.load_dotenv = lambda *_a, **_k: False\n"
        "from openfactory.runtime import boxed_job\n"
        "def _cannot(*_a, **_k):\n"
        "    raise RuntimeError('the app key could not be written')\n"
        "boxed_job.materialize_app_key = _cannot\n" + WORKER_DOORS[door], asked="json")

    lines = _every_line_is_json(ran)
    ended = [line for line in lines if line["level"] in ("ERROR", "CRITICAL")]
    assert len(ended) == 1 and ended[0]["logger"] == logs.UNCAUGHT_LOGGER, lines
    assert "RuntimeError: the app key could not be written" in ended[0]["exception"], ended[0]
    assert ran.returncode == 1, ran.returncode


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


#: Every character Python's own `str.splitlines()` ends a line on, read from Python itself — the
#: strictest reader a JSON line has, and the one this file's helpers use.
LINE_BOUNDARIES = "".join(chr(c) for c in range(0x10000)
                          if len(f"a{chr(c)}b".splitlines()) > 1)


def test_one_record_is_one_line_whatever_line_boundary_its_message_carries(monkeypatch, capsys):
    """A message may carry any character a reader splits lines on — a U+2028 pasted from a web
    page, a NEL from a legacy encoding. Each is escaped, so the record is still one line for every
    reader, and the message reads back as it was written (sixth review of #818)."""
    said = "the card's title read " + "|".join(LINE_BOUNDARIES)
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    with _a_fresh_process():
        logs.configure()
        logging.getLogger("openfactory.knowledge").warning(said)

    err = capsys.readouterr().err
    assert len(err.splitlines()) == 1, err.splitlines()
    (line,) = _json_lines(err)
    assert line["message"] == said
    assert {"\n", "\r", "\x85", "\u2028", "\u2029"} <= set(LINE_BOUNDARIES)


def _the_documented_fields() -> set[str]:
    """The fields `configuration.md`'s `OPENFACTORY_LOG_FORMAT` row says a JSON line carries: the
    backticked names after "The fields:"."""
    text = (ROOT / "docs" / "reference" / "configuration.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith(f"| `{logs.FORMAT_VARIABLE}`"))
    listed = row.split("The fields:", 1)[1].split("Unset", 1)[0]
    return set(re.findall(r"`([a-z]+)`", listed))


def test_a_line_carries_the_documented_fields_and_nothing_else(monkeypatch, capsys):
    """A record that carries everything the format can say — a traceback, a stack, a deployment, a
    project and a product — and an `extra` of its own: its line has exactly the fields the
    configuration reference documents. An `extra` a caller passes for its own reasons (an email, a
    token) never rides out on a line (sixth review of #818: writing every `extra` survived)."""
    documented = _the_documented_fields()
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    monkeypatch.setenv(logs.DEPLOYMENT_VARIABLE, "factory-eu-1")
    with _a_fresh_process():
        logs.configure()
        try:
            raise RuntimeError("the push was refused")
        except RuntimeError:
            logging.getLogger("openfactory.knowledge").exception(
                "a push was refused", stack_info=True,
                extra={"project": "acme", "product": "repo:acme/docs",
                       "requester_email": "someone@example.invalid", "token": "not-a-real-one"})

    (line,) = _json_lines(capsys.readouterr().err)
    assert set(line) == documented, (sorted(set(line) - documented),
                                     sorted(documented - set(line)))
    assert {"ts", "level", "logger", "message", "project", "product"} <= documented


def test_a_stack_asked_for_is_kept_on_its_one_line(monkeypatch, capsys):
    """`stack_info=True` is kept by the readable format; the JSON line keeps it too."""
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    with _a_fresh_process():
        logs.configure()
        logging.getLogger("openfactory.knowledge").warning("where was this asked", stack_info=True)

    (line,) = _json_lines(capsys.readouterr().err)
    assert line["stack"].startswith("Stack (most recent call last)"), line
    assert "test_a_stack_asked_for_is_kept_on_its_one_line" in line["stack"], line


def _documented_variables() -> set[str]:
    """Every variable `docs/reference/configuration.md`'s tables name in a row's first cell."""
    named: set[str] = set()
    text = (ROOT / "docs" / "reference" / "configuration.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("| `"):
            named.update(re.findall(r"`([A-Z][A-Z0-9_]+)`", line.split("|")[1]))
    return named


def test_every_variable_the_logs_and_the_probes_read_has_its_row():
    """Read off the modules: every `*_VARIABLE` the log format and the probes read is a row of the
    configuration reference, under its own name — a row renamed is a setting nobody can find."""
    from openfactory.observability import health

    read = {value for module in (logs, health) for name, value in vars(module).items()
            if name.endswith("_VARIABLE") and isinstance(value, str)}

    assert len(read) >= 6, read
    assert not read - _documented_variables(), sorted(read - _documented_variables())


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

    def __init__(self, monkeypatch, *, at: str = "localhost:7233"):
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
        monkeypatch.setenv("TEMPORAL_ADDRESS", at)


@pytest.fixture
def listening():
    """Addresses where a socket listens and never reads what it is sent — so the probe a connect
    asks first, with JSON lines, finds something there, and a connect is never answered — each
    closed when the case ends."""
    opened: list[socket.socket] = []

    def _one() -> str:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(64)
        opened.append(sock)
        return f"127.0.0.1:{sock.getsockname()[1]}"

    yield _one
    for sock in opened:
        sock.close()


@pytest.fixture
def refusing() -> str:
    """An address nobody listens on: a port bound and let go of, so a connection there is
    refused — an engine stopped, its container gone."""
    with socket.socket() as nobody:
        nobody.bind(("127.0.0.1", 0))
        return f"127.0.0.1:{nobody.getsockname()[1]}"


@pytest.fixture
def closing():
    """An address whose socket takes each connection and closes it at once, so the library's
    connect is refused after the socket took it — as a port a container publishes is taken while
    the engine behind it is not up, or an engine refuses the key it is given."""
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(64)

    def _close_each():
        while True:
            try:
                taken, _peer = sock.accept()
            except OSError:
                return                      # the socket was closed: the case is over
            taken.close()

    threading.Thread(target=_close_each, daemon=True).start()
    yield f"127.0.0.1:{sock.getsockname()[1]}"
    sock.close()


def _a_line_of_the_core(level: int, message: str):
    """A log entry as the client's core hands it over (`temporalio.bridge.runtime`)."""
    return types.SimpleNamespace(level=level, target="temporalio_client::retry", message=message,
                                 fields={"code": "Unavailable"}, time=time.time())


async def test_with_json_lines_the_one_engine_client_has_a_runtime_whose_core_writes_through_the_log(
        monkeypatch, capsys, listening):
    """Read off what `connection.connect()` — the one door every engine client of the worker, the
    panel and the CLI is made through — does: the process's client is made ONCE, on a runtime of
    its own whose core forwards its lines to `CORE_LOGGER` at the library's own default filter,
    and handed back to every later caller, from this loop or another; a target that changes gets
    a client and a runtime of its own. A line forwarded that way is a JSON line on stderr."""
    from temporalio.runtime import LoggingConfig

    from openfactory.runtime.temporal import connection

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    runtimes = _Runtimes(monkeypatch, at=listening())

    first = await connection.connect()
    again = await connection.connect()
    elsewhere = await asyncio.to_thread(lambda: asyncio.run(connection.connect()))
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "another-namespace")
    moved = await connection.connect()

    assert again is first and elsewhere is first, "a second caller was given a client of its own"
    assert moved is not first, "a target that changed was served the old target's client"
    assert len(runtimes.built) == 2 and runtimes.clients == runtimes.built, (
        "the held client and the moved target's each on a runtime of their own",
        runtimes.clients, runtimes.built)
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


async def test_a_client_a_changed_target_lets_go_of_keeps_no_runtime(monkeypatch, listening):
    """The SDK's client sits in a reference cycle, so a client let go of keeps its runtime — a
    thread per CPU with JSON lines — until a full collection. The one client a process lets go of
    is the one whose target changed (a moved address, a rotated key), and its runtime is gone the
    moment the new client is held, not at whatever collection comes next."""
    import weakref

    from openfactory.runtime.temporal import connection

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    runtimes = _Runtimes(monkeypatch, at=listening())

    class _InACycle:                       # as the SDK's client is: it refers to itself
        def __init__(self, runtime):
            self.runtime, self.itself = runtime, self

    async def _connect(*_a, **kwargs):
        runtimes.clients.append(kwargs.get("runtime"))
        return _InACycle(kwargs.get("runtime"))

    monkeypatch.setattr(connection.Client, "connect", _connect)
    await connection.connect()
    first = weakref.ref(runtimes.built[0])
    runtimes.built.clear()
    runtimes.clients.clear()
    monkeypatch.setenv("TEMPORAL_ADDRESS", listening())
    await connection.connect()

    assert first() is None, "the client a changed target let go of still holds its runtime"


async def test_a_runtime_that_cannot_be_built_is_a_failed_attempt_and_the_next_one_tries(
        monkeypatch, listening):
    """Building a runtime can fail like a connect can — the bridge's "Failed initializing runtime",
    for one, when a thread cannot start under a pid limit. That attempt fails, is let go of, and the
    next connect to a healthy engine tries for itself (seventh review of #818: built before the
    attempt was settled, it stayed in flight, and every later connect waited on it for good)."""
    from openfactory.runtime.temporal import connection

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    _Runtimes(monkeypatch, at=listening())
    making, failed = connection.core_runtime, []

    def _fails_once():
        if not failed:
            failed.append(True)
            raise RuntimeError("Failed initializing runtime: a thread could not start")
        return making()

    monkeypatch.setattr(connection, "core_runtime", _fails_once)
    with pytest.raises(RuntimeError, match="Failed initializing runtime"):
        await asyncio.wait_for(connection.connect(), 5.0)

    client = await asyncio.wait_for(connection.connect(), 5.0)
    assert client is await asyncio.wait_for(connection.connect(), 5.0)


class _Arrivals:
    """How many callers are waiting on the attempt in flight — counted where each one's wait
    begins, when `asyncio.wrap_future` hangs its callback on the flight — so a case releases the
    engine once they all hold it, not after a guess (delta review of #818: counted earlier, at the
    door, a caller could still be on its way to the flight when the engine was released)."""

    def __init__(self, monkeypatch):
        from openfactory.runtime.temporal import connection

        self._seen = 0
        self._changed = threading.Condition()
        arrivals = self

        class _Flight(concurrent.futures.Future):
            def add_done_callback(self, fn):
                super().add_done_callback(fn)
                with arrivals._changed:
                    arrivals._seen += 1
                    arrivals._changed.notify_all()

        monkeypatch.setattr(connection, "concurrent", types.SimpleNamespace(
            futures=types.SimpleNamespace(Future=_Flight)))

    def wait_for(self, waiting: int) -> None:
        with self._changed:
            assert self._changed.wait_for(lambda: self._seen >= waiting, timeout=10.0), (
                f"{self._seen} of {waiting} callers are waiting on the attempt")


class _HeldEngine:
    """The library's connect, the FIRST attempt held until the case releases it — then answering, or
    failing with `fails` — and every later attempt answering at once. Counts the attempts."""

    def __init__(self, monkeypatch, *, at: str = "localhost:7233"):
        from openfactory.runtime.temporal import connection

        monkeypatch.setenv("TEMPORAL_ADDRESS", at)
        self.client, self.attempts, self.fails = object(), 0, None
        self.entered, self.release = threading.Event(), threading.Event()
        counting = threading.Lock()

        async def _connect(*_args, **_kwargs):
            with counting:
                self.attempts += 1
                first = self.attempts == 1
            self.entered.set()
            if first:
                await asyncio.get_running_loop().run_in_executor(None, self.release.wait, 10.0)
                if self.fails is not None:
                    raise self.fails
            return self.client

        monkeypatch.setattr(connection.Client, "connect", _connect)

    async def is_asked(self) -> None:
        """Until the first attempt has reached the library, without holding this loop."""
        entered = await asyncio.get_running_loop().run_in_executor(None, self.entered.wait, 10.0)
        assert entered, "no attempt reached the library within 10 s"


def _on_a_loop_of_its_own(said: list) -> threading.Thread:
    """A caller of `connection.connect()` on a thread and a loop of its own, its answer — or what it
    raised — appended to `said`."""
    from openfactory.runtime.temporal import connection

    def _ask():
        try:
            said.append(asyncio.run(connection.connect()))
        except BaseException as exc:  # noqa: BLE001 — the case reads what each caller was told
            said.append(exc)

    caller = threading.Thread(target=_ask, daemon=True)
    caller.start()
    return caller


@pytest.mark.parametrize("outcome", ["answers", "fails"])
async def test_callers_who_arrive_together_share_one_attempt_and_its_outcome(monkeypatch,
                                                                             outcome):
    """THE SINGLE FLIGHT, ACROSS LOOPS AND THREADS (seventh review of #818: each rule survived
    every test that reached the door). Callers on three loops arrive while one attempt is in
    flight: the library is asked once, and each of them is told what that one attempt said — its
    client, or its failure, which nobody behind it repeats. A caller arriving after a failure
    tries again, which is how a recovered engine is picked up."""
    from openfactory.runtime.temporal import connection

    engine, arrivals = _HeldEngine(monkeypatch), _Arrivals(monkeypatch)
    if outcome == "fails":
        engine.fails = RuntimeError("the engine refused the handshake")
    said: list = []
    callers = [_on_a_loop_of_its_own(said)]
    try:
        await engine.is_asked()
        callers += [_on_a_loop_of_its_own(said), _on_a_loop_of_its_own(said)]
        here = asyncio.create_task(connection.connect())
        await asyncio.get_running_loop().run_in_executor(None, arrivals.wait_for, 3)
    finally:
        engine.release.set()
    try:
        said.append(await here)
    except RuntimeError as exc:
        said.append(exc)
    for caller in callers:
        await asyncio.get_running_loop().run_in_executor(None, caller.join, 10.0)

    assert engine.attempts == 1, f"{engine.attempts} attempts for four callers who came together"
    expected = engine.client if outcome == "answers" else engine.fails
    assert len(said) == 4 and all(answer is expected for answer in said), said
    if outcome == "fails":
        assert await connection.connect() is engine.client and engine.attempts == 2


@pytest.mark.parametrize("asked", ["json", None])
async def test_a_cancelled_attempt_is_nobodys_failure_and_those_behind_it_try(monkeypatch,
                                                                              listening, asked):
    """The caller whose attempt is in flight goes away — a bounded read that gave up, a request a
    browser closed. That says nothing about the engine, so the callers queued behind it try for
    themselves and are given a client, never the cancellation as if the engine had failed — and,
    with JSON lines, never a rest, though the attempt had built its runtime."""
    from openfactory.runtime.temporal import connection

    if asked:
        monkeypatch.setenv(logs.FORMAT_VARIABLE, asked)
        monkeypatch.setattr(connection, "Runtime", lambda **_kwargs: types.SimpleNamespace())
    engine = _HeldEngine(monkeypatch, at=listening())
    arrivals = _Arrivals(monkeypatch)
    said: list = []
    owner = asyncio.create_task(connection.connect())
    try:
        await engine.is_asked()
        callers = [_on_a_loop_of_its_own(said), _on_a_loop_of_its_own(said)]
        await asyncio.get_running_loop().run_in_executor(None, arrivals.wait_for, 2)
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner
        for caller in callers:
            await asyncio.get_running_loop().run_in_executor(None, caller.join, 10.0)
    finally:
        engine.release.set()

    assert said == [engine.client, engine.client], said


async def test_callers_who_arrive_at_the_same_instant_on_many_threads_make_one_attempt(monkeypatch):
    """The lock around the held client and the flight is what makes the single flight hold across
    THREADS (re-review on 3cd816ac, measured: with `_HOLDING` a no-op, 32 threads released by one
    barrier made 2 or 3 library attempts in 4 trials of 20; with the lock, 1 in 20 of 20)."""
    from openfactory.runtime.temporal import connection

    monkeypatch.setenv("TEMPORAL_ADDRESS", "localhost:7233")
    attempts, counting = [], threading.Lock()

    async def _connect(*_args, **_kwargs):
        with counting:
            attempts.append(1)
        await asyncio.sleep(0.2)
        return object()

    monkeypatch.setattr(connection.Client, "connect", _connect)
    before = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for trial in range(30):
            connection.forget()
            attempts.clear()
            together = threading.Barrier(32)

            def _ask(together: threading.Barrier = together) -> None:
                together.wait()
                asyncio.run(connection.connect())

            callers = [threading.Thread(target=_ask, daemon=True) for _ in range(32)]
            for caller in callers:
                caller.start()
            for caller in callers:
                await asyncio.get_running_loop().run_in_executor(None, caller.join, 10.0)
            assert len(attempts) == 1, f"trial {trial}: {len(attempts)} attempts for 32 callers"
    finally:
        sys.setswitchinterval(before)


async def test_a_waiter_that_gives_up_cancels_nobody_elses_attempt(monkeypatch):
    """A caller queued behind an attempt is cancelled. Only its own wait ends: the attempt goes on,
    its owner is handed the client it made, and the callers still waiting are given it too."""
    from openfactory.runtime.temporal import connection

    engine, arrivals = _HeldEngine(monkeypatch), _Arrivals(monkeypatch)
    owner_said: list = []
    others_said: list = []
    callers = [_on_a_loop_of_its_own(owner_said)]
    try:
        await engine.is_asked()
        callers.append(_on_a_loop_of_its_own(others_said))
        await asyncio.get_running_loop().run_in_executor(None, arrivals.wait_for, 1)
        gives_up = asyncio.create_task(connection.connect())
        await asyncio.get_running_loop().run_in_executor(None, arrivals.wait_for, 2)
        gives_up.cancel()
        with pytest.raises(asyncio.CancelledError):
            await gives_up
    finally:
        engine.release.set()
    for caller in callers:
        await asyncio.get_running_loop().run_in_executor(None, caller.join, 10.0)

    assert owner_said == [engine.client], owner_said
    assert others_said == [engine.client], others_said
    assert engine.attempts == 1


async def test_an_attempt_nobody_bounded_is_bounded_and_the_reads_behind_it_get_its_end(
        monkeypatch):
    """A caller with no bound of its own (a release, a preview stop, a schedule command) starts the
    first connect, and a bounded read queues behind it. The attempt is bounded all the same — by
    `OPENFACTORY_ENGINE_DEADLINE` — so neither waits on an engine that never answers for longer
    than the deployment said (seventh review of #818, measured: unbounded, it ran 30.1 s against a
    listener that never answered, and the reads behind it gave up without trying)."""
    from openfactory.runtime.temporal import connection

    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "0.5")
    engine = _HeldEngine(monkeypatch)
    try:
        unbounded = asyncio.create_task(connection.connect())
        await engine.is_asked()
        behind = asyncio.create_task(connection.connect())
        done, _ = await asyncio.wait({unbounded, behind}, timeout=5.0)
    finally:
        engine.release.set()

    assert done == {unbounded, behind}, "an attempt nobody bounded is still waiting on the engine"
    for ended in (unbounded, behind):
        assert isinstance(ended.exception(), TimeoutError), ended.exception()
        assert "did not take a connection within 0.5s" in str(ended.exception())
    assert await connection.connect() is engine.client


@pytest.mark.parametrize("asked", [None, "text"])
async def test_without_json_the_engines_runtime_is_left_as_it_was(monkeypatch, asked):
    from openfactory.runtime.temporal import connection

    if asked:
        monkeypatch.setenv(logs.FORMAT_VARIABLE, asked)
    runtimes = _Runtimes(monkeypatch)

    await connection.connect()

    assert runtimes.built == [] and runtimes.clients == [None]


def _threads_of_this_process() -> int | None:
    """This process's threads as the system counts them — the engine client's core's included,
    which `threading` cannot see — or None where the system does not say."""
    task = Path("/proc/self/task")
    if task.is_dir():
        return len(os.listdir(task))
    if sys.platform == "darwin":
        listed = subprocess.run(["ps", "-M", "-p", str(os.getpid())], capture_output=True,
                                text=True, timeout=30)
        return len(listed.stdout.splitlines()) - 1 if listed.returncode == 0 else None
    return None


#: How many connects each case below makes in a row, after the first.
REFUSED_CONNECTS = 10

#: The doors a process connects to its engine through, each asked as its callers ask it: the one
#: client's own (`connection.connect` — the worker's tools, a release, a preview's stop), a worker's
#: birth, bounded short here, and the read side's (`view.connect` — every panel read, and
#: readiness). `test_every_door_to_the_engine_is_a_case` reads the set off the code.
CONNECT_DOORS = ("connection.connect", "connection.connect_at_birth", "view.connect")


def _door(name: str):
    """The door `name`, ready to be awaited."""
    from openfactory.runtime.temporal import connection, view

    return {"connection.connect": connection.connect,
            "connection.connect_at_birth": lambda: connection.connect_at_birth(within=0.1,
                                                                               every=0.02),
            "view.connect": view.connect}[name]()


def test_every_door_to_the_engine_is_a_case():
    """Read off `connection.py` and `view.py`: every coroutine a caller connects through — those
    named `connect…` — is a case of the rules below, and the one attempt that builds a runtime
    (`_connect_for`) is made from `connection.connect` alone, so every door's cost is that one's."""
    doors, attempts = set(), set()
    for module in ("connection", "view"):
        tree = ast.parse((ROOT / "openfactory" / "runtime" / "temporal" / f"{module}.py")
                         .read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if node.name.startswith("connect"):
                doors.add(f"{module}.{node.name}")
            if any(isinstance(call, ast.Call) and getattr(call.func, "id", "") == "_connect_for"
                   for call in ast.walk(node)):
                attempts.add(f"{module}.{node.name}")

    assert doors == set(CONNECT_DOORS), sorted(doors ^ set(CONNECT_DOORS))
    assert attempts == {"connection.connect"}, attempts


class _Costs:
    """What connecting costs, counted: the runtimes `core_runtime` built (the library's default,
    None, is not one), by weak reference, and the full collections `connection` ran."""

    def __init__(self, monkeypatch):
        from openfactory.runtime.temporal import connection

        self.built: list[weakref.ref] = []
        self.collections = 0
        making = connection.core_runtime

        def _recorded():
            runtime = making()
            if runtime is not None:
                self.built.append(weakref.ref(runtime))
            return runtime

        def _collect(*args):
            self.collections += 1
            return gc.collect(*args)

        monkeypatch.setattr(connection, "core_runtime", _recorded)
        monkeypatch.setattr(connection, "gc", types.SimpleNamespace(collect=_collect))


def _no_engine_credentials(monkeypatch) -> None:
    for name in ("TEMPORAL_API_KEY", "TEMPORAL_TLS_CERT", "TEMPORAL_TLS_KEY", "TEMPORAL_NAMESPACE"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("asked", ["json", None])
@pytest.mark.parametrize("door", CONNECT_DOORS)
async def test_a_port_nobody_listens_on_costs_no_runtime_and_no_collection(monkeypatch, refusing,
                                                                          door, asked):
    """REVIEW REQUESTING CHANGES ON 3cd816ac, measured on temporalio 1.34.0: a process started while
    its engine was down built a runtime for every connect — about 65 KB of native memory each,
    which no collection frees — and ran a full collection on the caller's loop for each, 20 ms on a
    small heap and 300 ms on 3M objects: 1,200 refused connects grew it from 77 to 151 MB through
    `connection.connect` and from 66 to 146 MB through `view.connect`, and a panel pays one on
    every healthcheck and every read. So, through every door and in either format: however many
    connects find nobody listening, each caller is told, and no runtime is built and no collection
    runs for any of them."""
    if asked:
        monkeypatch.setenv(logs.FORMAT_VARIABLE, asked)
    _no_engine_credentials(monkeypatch)
    monkeypatch.setenv("TEMPORAL_ADDRESS", refusing)
    costs = _Costs(monkeypatch)

    for _ in range(1 + REFUSED_CONNECTS):
        with pytest.raises(RuntimeError):
            await _door(door)

    assert costs.built == [], f"{len(costs.built)} runtimes built for a port nobody listens on"
    assert costs.collections == 0, f"{costs.collections} collections for a port nobody listens on"


#: How an attempt fails once the socket has taken it — with the library's own connect: refused at
#: once (`closing`: a socket that closes what it takes), or never answered within the attempt's
#: bound (`listening`: one that never reads).
AFTER_THE_SOCKET_TAKES_IT = ("refused at once", "never answered")


@pytest.mark.owns_its_engine  # the library's own connect, against sockets this case opens
@pytest.mark.parametrize("fails", AFTER_THE_SOCKET_TAKES_IT)
@pytest.mark.parametrize("door", CONNECT_DOORS)
async def test_an_attempt_that_fails_once_its_runtime_is_built_rests_its_target_at_every_door(
        monkeypatch, listening, closing, door, fails):
    """A socket that takes the connection is not an engine that answers: a port a container
    publishes is taken while the engine behind it is down, an engine refuses a key, a wedged one
    never answers. With JSON lines that attempt has built its runtime by then, so it leaves its
    target RESTING: until the rest ends, a connect through any door is refused at once with
    `EngineUnreachable`, and nothing is built, collected or asked of the library for it (review
    requesting changes on 3cd816ac: without the rest, each read built a runtime again)."""
    from openfactory.runtime.temporal import connection
    from openfactory.runtime.temporal.vocabulary import EngineUnreachable

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    monkeypatch.setenv("OPENFACTORY_ENGINE_UNREACHABLE_FOR", "60")
    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "0.3")
    _no_engine_credentials(monkeypatch)
    monkeypatch.setenv("TEMPORAL_ADDRESS", closing if fails == "refused at once" else listening())
    costs = _Costs(monkeypatch)
    asked: list[object] = []
    opening = connection.Client.connect

    async def _counted(*args, **kwargs):
        asked.append(kwargs.get("runtime"))
        return await opening(*args, **kwargs)

    monkeypatch.setattr(connection.Client, "connect", _counted)

    with pytest.raises((RuntimeError, TimeoutError)):
        await _door(door)
    for other in (*CONNECT_DOORS, *CONNECT_DOORS):
        with pytest.raises(EngineUnreachable):
            await _door(other)

    assert len(costs.built) == 1 and len(asked) == 1, (
        f"{len(costs.built)} runtimes built and the library asked {len(asked)} times; one each")
    assert costs.collections == 1, f"{costs.collections} collections for one failed attempt"


@pytest.mark.parametrize("first", ["unset", "0.5", "90"])
def test_a_rest_doubles_after_each_attempt_that_fails_again_up_to_a_minute(monkeypatch, first):
    """The first rest is `OPENFACTORY_ENGINE_UNREACHABLE_FOR`, each attempt that fails after one
    doubles it, up to `RESTS_AT_MOST_S` (or the first rest, when the deployment set it longer):
    an engine that stays away costs a runtime a minute, and one that comes back is asked again
    within a minute at worst. One target rests at a time, and the refusal says where, what the
    attempt said, and the setting the wait starts at."""
    from openfactory.runtime.temporal import connection

    if first != "unset":
        monkeypatch.setenv("OPENFACTORY_ENGINE_UNREACHABLE_FOR", first)
    starts = connection.unreachable_window()
    target = ("engine.example:7233", "default", "a-digest")
    waits = []
    for _ in range(10):
        connection._rest_after(target, RuntimeError("Unauthenticated: the key is not accepted"))
        (rest,) = connection._RESTING.values()
        waits.append(rest.wait)
    said = str(connection._resting(target))
    another = ("engine.example:7233", "another-namespace", "a-digest")
    connection._rest_after(another, RuntimeError("Unauthenticated"))

    most = max(connection.RESTS_AT_MOST_S, starts)
    assert waits == [min(starts * 2 ** n, most) for n in range(10)], waits
    for named in ("engine.example:7233", "Unauthenticated: the key is not accepted",
                  "OPENFACTORY_ENGINE_UNREACHABLE_FOR"):
        assert named in said, (named, said)
    assert list(connection._RESTING) == [another], "a target that changed kept the old one's rest"
    assert connection._RESTING[another].wait == starts, "a new target's first rest was doubled"


async def _until_no_target_rests() -> None:
    from openfactory.runtime.temporal import connection

    for rest in list(connection._RESTING.values()):
        await asyncio.sleep(max(0.0, rest.until - time.monotonic()) + 0.01)


@pytest.mark.parametrize("door", CONNECT_DOORS)
async def test_once_its_rest_ends_a_target_is_asked_again_and_a_client_that_lands_leaves_no_failed_runtime(
        monkeypatch, listening, door):
    """A failed attempt's runtime sits in a cycle with the failure's traceback, so the collection run
    while that failure is handled frees the attempt before it, never its own, and the read side kept
    the last failure until a client landed (re-review on 3cd816ac, measured on the real panel: 26
    threads while the engine was silent, 38 for good once it answered, 14 after one collection).
    So, through every door: each rest ends and the engine is asked again, and when a client lands
    no failed attempt's runtime is left."""
    from openfactory.runtime.temporal import connection

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    monkeypatch.setenv("OPENFACTORY_ENGINE_UNREACHABLE_FOR", "0.05")
    monkeypatch.setattr(connection, "RESTS_AT_MOST_S", 0.05)
    runtimes = _Runtimes(monkeypatch, at=listening())
    refusing, asked = [True], []

    async def _connect(*_args, **kwargs):
        asked.append(1)
        if refusing[0]:
            in_a_cycle = [kwargs.get("runtime")]
            in_a_cycle.append(in_a_cycle)
            raise RuntimeError("Connection refused")
        return object()

    monkeypatch.setattr(connection.Client, "connect", _connect)
    for _ in range(3):
        await _until_no_target_rests()
        with pytest.raises(RuntimeError):
            await _door(door)
    failed = [weakref.ref(runtime) for runtime in runtimes.built]
    runtimes.built.clear()
    refusing[0] = False
    await _until_no_target_rests()
    client = await _door(door)

    assert len(failed) == 3 and len(asked) == 4, (len(failed), len(asked))
    assert client is await connection.connect(), "the client that landed is not the one held"
    assert [ref for ref in failed if ref() is not None] == [], "a failed attempt's runtime is left"


@pytest.mark.owns_its_engine  # the library's own connect, refused by a socket this case opens
async def test_a_connect_refused_once_the_socket_took_it_keeps_no_runtime_alive(monkeypatch,
                                                                                 closing):
    """With JSON lines every attempt has a runtime of its own, about a thread per CPU, and a failed
    attempt's must not stay until a full collection (review on d2ef6149, measured: a panel whose
    engine was down at its first connect gained twelve threads per healthcheck on 12 CPUs, 146
    after twelve; on 8 CPUs ten refused connects left 91 threads, and one `gc.collect()` brought
    them back to 10). A port nobody listens on builds no runtime now, so the attempts here are
    the library's own, refused after the socket took them, each once its target's rest has ended:
    however many fail, at most the last one's runtime is alive, and the process's threads stay
    within one runtime of what they were after the first."""
    from openfactory.runtime.temporal import connection

    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    monkeypatch.setenv("OPENFACTORY_ENGINE_UNREACHABLE_FOR", "0.01")
    monkeypatch.setattr(connection, "RESTS_AT_MOST_S", 0.01)
    _no_engine_credentials(monkeypatch)
    monkeypatch.setenv("TEMPORAL_ADDRESS", closing)
    costs = _Costs(monkeypatch)

    async def _refused() -> None:
        await _until_no_target_rests()
        with pytest.raises(RuntimeError):
            await connection.connect()

    await _refused()
    after_one = _threads_of_this_process()
    for _ in range(REFUSED_CONNECTS):
        await _refused()
    alive = sum(ref() is not None for ref in costs.built)
    after_all = _threads_of_this_process()

    assert len(costs.built) == REFUSED_CONNECTS + 1, "every attempt is made on a runtime of its own"
    assert alive <= 1, f"{alive} of {len(costs.built)} refused connects still hold their runtime"
    if after_one is not None and after_all is not None:
        assert after_all <= after_one + (os.cpu_count() or 1) + 2, (after_one, after_all)


#: How many reads each shape below makes, after its first.
READS = 6


@pytest.mark.owns_its_engine
@pytest.mark.parametrize("asked", ["json", None])
async def test_a_process_holds_one_engine_client_whoever_reads_and_from_whichever_loop(
        monkeypatch, asked):
    """THE SIXTH REVIEW'S TWO SHAPES, ON A REAL ENGINE, in both formats. A process held one client
    per loop and dropped one each time a read arrived from another, and a dropped client kept its
    connection — and, with JSON lines, its runtime's thread per CPU — until a full collection:

      · the worker's readiness on its own loop taking turns with a product turn's read on the
        standing loop: connections 2 → 12 in both formats, threads 21 → 111 with JSON, in six;
      · a read under an `asyncio.run` of its own, as the product door makes one per message, and
        a one-shot `connection.connect()`: threads 10 → 55 in six.

    So: the worker's client is made once, readiness asks that very client, and after every shape
    the library has been asked for one connection in all, at most that client's runtime is alive,
    and the process's threads are where they were after the first round. Every step is awaited; no
    case waits on a clock."""
    import weakref

    from temporalio.api.workflowservice.v1 import GetSystemInfoRequest
    from temporalio.client import Client
    from temporalio.testing import WorkflowEnvironment

    from openfactory.observability import health
    from openfactory.runtime.temporal import connection, view
    from openfactory.runtime.temporal.standing import from_a_thread

    if asked:
        monkeypatch.setenv(logs.FORMAT_VARIABLE, asked)
    for name in ("TEMPORAL_API_KEY", "TEMPORAL_TLS_CERT", "TEMPORAL_TLS_KEY", "TEMPORAL_NAMESPACE"):
        monkeypatch.delenv(name, raising=False)
    opened: list[object] = []
    opening = Client.connect

    async def _counted(*args, **kwargs):
        opened.append(kwargs.get("runtime"))
        return await opening(*args, **kwargs)

    runtimes: list[weakref.ref] = []
    making = connection.core_runtime

    def _recorded():
        runtime = making()
        if runtime is not None:
            runtimes.append(weakref.ref(runtime))
        return runtime

    monkeypatch.setattr(connection, "core_runtime", _recorded)
    asked_by_readiness: list[object] = []
    checking = view.check_health

    async def _readiness_asks(client):
        asked_by_readiness.append(client)
        return await checking(client)

    monkeypatch.setattr(view, "check_health", _readiness_asks)

    async def a_turns_read() -> None:          # `product/model.py::_engine_reads`'s shape
        await (await view.connect()).workflow_service.get_system_info(GetSystemInfoRequest())

    def a_door_read() -> None:                # `product/door.py`: a loop per message
        asyncio.run(a_turns_read())

    env = await WorkflowEnvironment.start_time_skipping()
    try:
        monkeypatch.setattr(Client, "connect", _counted)  # after the engine's own client
        monkeypatch.setenv("TEMPORAL_ADDRESS", env.client.service_client.config.target_host)
        the_workers = await connection.connect()        # what `connect_at_birth` makes
        seen = []
        for _ in range(1 + READS):
            health.forget()                             # a new window, as each poll 15 s apart is
            await health.ready()                        # the worker's own loop
            await asyncio.to_thread(from_a_thread, a_turns_read)   # the standing loop
            seen.append(_threads_of_this_process())
        for _ in range(READS):
            await asyncio.to_thread(a_door_read)
            one_shot = await connection.connect()
            await one_shot.workflow_service.get_system_info(GetSystemInfoRequest())
            del one_shot
        seen.append(_threads_of_this_process())
    finally:
        await env.shutdown()

    assert len(opened) == 1, f"the library was asked for {len(opened)} connections, not one"
    assert asked_by_readiness and all(c is the_workers for c in asked_by_readiness), (
        "readiness asked a client other than the worker's")
    assert sum(ref() is not None for ref in runtimes) <= 1, "a dropped client kept its runtime"
    if seen[0] is not None:
        assert max(seen) <= seen[0] + 2, f"threads after each round: {seen}"


@activity.defn(name="nothing_at_all")
async def _nothing_at_all() -> None:
    return None


@pytest.mark.owns_its_engine
async def test_a_core_warning_arrives_as_a_json_line_after_another_client_is_gone(
        monkeypatch, capfd):
    """THE THIRD REVIEW'S MEASUREMENT, ON A REAL ENGINE. The worker dropped one-shot clients at
    boot (`schedule.ensure_all`), and with one shared runtime that silenced its core for good: the
    bridge aborts a runtime's one forwarder when any client of it is dropped (temporalio's #1988).
    The process now holds one client per target, so the client dropped here is the one a target
    that changed let go of. Then a worker polls on the process's client — and the core's own warning
    must still reach the log, as a JSON line, and no line may be anything else. The time-skipping
    engine makes the core warn as the worker starts; if it ever stops, the engine goes away under
    the worker, whose polls then retry and warn.

    THE WORKER IS STOPPED HERE ON EVERY PATH, AND WAITED FOR WITHIN A BOUND: a case that failed
    with its worker still polling a dead engine left it to the loop's teardown, and one mutation
    run of this file hung for hours there.

    WHAT IS READ IS FILE DESCRIPTORS 1 AND 2, NOT PYTHON'S STREAMS (fourth review of #818): the
    core is native code, and a core that wrote its own lines would write them to the descriptors,
    where `capsys` sees nothing. The time-skipping engine is started with the capture off, so its
    own process writes where it always did, and only this process's lines are read."""
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
    with capfd.disabled():
        env = await WorkflowEnvironment.start_time_skipping()
    engine_up = True
    try:
        with _a_fresh_process():
            logs.configure()
            monkeypatch.setenv("TEMPORAL_ADDRESS", env.client.service_client.config.target_host)
            # A CLIENT THAT IS GONE: the process holds one client per target, so the one let go
            # of is the client of a target that changed — made, dropped and collected.
            monkeypatch.setenv("TEMPORAL_NAMESPACE", "a-target-that-changed")
            gone = await connection.connect()
            monkeypatch.delenv("TEMPORAL_NAMESPACE")
            client = await connection.connect()
            assert client is not gone
            del gone
            gc.collect()
            worker = Worker(client, task_queue=f"q-{uuid.uuid4().hex}",
                            activities=[_nothing_at_all])
            polling = asyncio.create_task(worker.run())
            try:
                core = await _the_cores_lines(capfd, seen, strays, within=5.0)
                if not core and not strays:
                    await env.shutdown()
                    engine_up = False
                    core = await _the_cores_lines(capfd, seen, strays, within=30.0)
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


async def _the_cores_lines(capfd, seen: list[dict], strays: list[str], *,
                           within: float) -> list[dict]:
    """Read what was written until a line from the engine client's core is among the JSON lines,
    a line that is not JSON is (`strays`), or `within` seconds pass; `seen` keeps every JSON line
    across reads. Never raises, so its caller always stops its worker."""
    from openfactory.runtime.temporal import connection

    deadline = time.monotonic() + within
    while True:
        written = capfd.readouterr()
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
