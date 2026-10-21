"""Every process the deployment starts logs with a time, a level and a name, and keeps INFO (#675).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640). The worker and the panel configured no
logging. A warning reached their logs as a bare message — `floor: could not list the jobs (…)` —
with no time, no level and no source, and every INFO line was dropped: a context push rejected
twice showed one line, because the first rejection is an INFO. Two of the week's intermittent
failures could be placed in time only by counting poll requests between moments the engine's own
history dated.

THE RULE THIS FILE HOLDS: every long-running process the deployment starts writes one format —
`<UTC time to the ms> <LEVEL> <logger name>: <message>` — and keeps the platform's INFO. The
processes are read from what starts them, not listed here: the compose file's services built from
this repository (the build-only profile aside) and the plan `openfactory up` runs. A process added
to either has to be driven below, or the first test fails.

WHAT IS DOUBLED, AND ONLY THAT. What each process does once it is up: the worker's `main()`, and
uvicorn's server. Each double logs the lines a real one would, through the real loggers; the entry
point, the log setup and the handler are the real ones. The root logger is emptied for each case,
as a fresh process's is, and put back afterwards.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import shlex
import sys
import threading
import warnings
from pathlib import Path

import pytest
import yaml

from openfactory.observability import logs

ROOT = Path(__file__).resolve().parents[1]
LINE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z (DEBUG|INFO|WARNING|ERROR|CRITICAL) "
                  r"[\w.]+: .+$")
REJECTED = "knowledge: push to main rejected — re-basing on the new tip and trying once more"
UNLISTED = "floor: could not list the jobs (the engine did not answer the job list within 3s)"
ACCESS = '127.0.0.1:64387 - "POST /api/act/merge HTTP/1.1" 404'


# ── what starts a process ───────────────────────────────────────────────────────────────────────

def _cmd(dockerfile: Path) -> list[str]:
    cmds = [line for line in dockerfile.read_text().splitlines() if line.startswith("CMD ")]
    return json.loads(cmds[-1][4:])


def _compose_processes() -> dict[str, list[str]]:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    out = {}
    for name, svc in compose["services"].items():
        build = svc.get("build")
        if not build or "build" in (svc.get("profiles") or []):
            continue
        dockerfile = build.get("dockerfile") if isinstance(build, dict) else "Dockerfile"
        command = svc.get("command") or _cmd(ROOT / dockerfile)
        out[f"compose:{name}"] = [str(c) for c in command]
    return out


def _up_processes(tmp_path) -> dict[str, list[str]]:
    from openfactory.runtime import host

    plan = host.processes(panel_port=8787, state=tmp_path, engine="temporal")
    return {f"up:{name}": argv[1:] for name, argv in plan if name != "engine"}


def _which(argv: list[str]) -> str:
    joined = shlex.join(argv)
    if "-m openfactory.runtime.temporal.worker" in joined:
        return "worker"
    if "-m openfactory.cli serve" in joined:
        return "panel"
    return joined


def test_every_process_the_deployment_starts_is_driven_here(tmp_path, monkeypatch):
    monkeypatch.setattr("openfactory.runtime.host.the_client", lambda: True)
    started = {**_compose_processes(), **_up_processes(tmp_path)}

    assert {"compose:worker", "compose:panel", "up:worker", "up:panel"} <= set(started), started
    assert {_which(argv) for argv in started.values()} == set(DRIVEN), started


# ── each one, driven ────────────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _a_fresh_process():
    """The root logger as a process starts with it: no handler, WARNING; put back on the way out.

    INSIDE THE TEST, NOT IN A FIXTURE: pytest hangs its own capture handler on the root logger at
    the start of each phase, so one emptied during setup is no longer empty when the test runs.

    PYTHON'S OWN HOOKS ARE PUT BACK TOO: with JSON lines `configure` hands the warnings, the
    exception nobody caught and the unraisable one to the log (#681), and a case must not leave
    the next one's warnings and threads reporting to a handler that is gone."""
    root = logging.getLogger()
    kept = (root.handlers[:], root.level,
            {name: logging.getLogger(name).level for name in (*logs.OURS, "temporalio")})
    hooks = (sys.excepthook, threading.excepthook, sys.unraisablehook, warnings.showwarning)
    root.handlers.clear()
    root.setLevel(logging.WARNING)
    for name in kept[2]:
        logging.getLogger(name).setLevel(logging.NOTSET)
    try:
        yield
    finally:
        logging.captureWarnings(False)
        sys.excepthook, threading.excepthook, sys.unraisablehook, warnings.showwarning = hooks
        root.handlers[:] = kept[0]
        root.setLevel(kept[1])
        for name, level in kept[2].items():
            logging.getLogger(name).setLevel(level)


@pytest.fixture(autouse=True)
def _no_level_set(monkeypatch):
    monkeypatch.delenv(logs.LEVEL_VARIABLE, raising=False)


def _the_lines_a_process_writes():
    logging.getLogger("openfactory.knowledge.pipeline").info(REJECTED)
    logging.getLogger("openfactory.panel").warning(UNLISTED)
    logging.getLogger("temporalio.worker").info("a library's chatter")


def _drive_worker(monkeypatch):
    from openfactory.runtime.temporal import worker

    async def _up():
        _the_lines_a_process_writes()

    monkeypatch.setattr(worker, "main", _up)
    asyncio.run(worker.born())
    return {}


def _drive_panel(monkeypatch):
    import uvicorn

    from openfactory import cli

    ran: dict = {}

    def _serve(app, **kwargs):
        ran.update(kwargs)
        logging.getLogger("uvicorn.access").info(ACCESS)
        _the_lines_a_process_writes()

    monkeypatch.setattr(uvicorn, "run", _serve)
    monkeypatch.setattr("openfactory.namespace.announce_build", lambda *_a, **_k: None)
    cli.serve(host="127.0.0.1", port=8787)
    return ran


DRIVEN = {"worker": _drive_worker, "panel": _drive_panel}


@pytest.mark.parametrize("process", sorted(DRIVEN))
def test_every_line_carries_a_time_a_level_and_a_name(monkeypatch, capsys, process):
    with _a_fresh_process():
        DRIVEN[process](monkeypatch)

    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert lines, f"{process} wrote no log line"
    assert all(LINE.match(line) for line in lines), lines
    assert any(line.endswith(f" INFO openfactory.knowledge.pipeline: {REJECTED}")
               for line in lines), f"{process} dropped the platform's INFO: {lines}"
    assert any(line.endswith(f" WARNING openfactory.panel: {UNLISTED}") for line in lines), lines
    assert not any("a library's chatter" in line for line in lines), (
        f"{process} let a library's INFO through: {lines}")


def test_the_panels_requests_are_in_the_same_format(monkeypatch, capsys):
    """uvicorn is told not to set up its own format, so its access lines come through this one."""
    with _a_fresh_process():
        ran = _drive_panel(monkeypatch)

    assert ran.get("log_config", "unset") is None, ran
    lines = capsys.readouterr().err.splitlines()
    assert any(LINE.match(line) and line.endswith(f" INFO uvicorn.access: {ACCESS}")
               for line in lines), lines


def test_the_level_is_a_setting(monkeypatch, capsys):
    monkeypatch.setenv(logs.LEVEL_VARIABLE, "warning")
    with _a_fresh_process():
        _drive_worker(monkeypatch)

    err = capsys.readouterr().err
    assert UNLISTED in err and REJECTED not in err, err


def test_a_level_that_is_no_level_keeps_INFO(monkeypatch, capsys):
    monkeypatch.setenv(logs.LEVEL_VARIABLE, "loud")
    with _a_fresh_process():
        _drive_worker(monkeypatch)

    assert REJECTED in capsys.readouterr().err


def test_a_process_that_already_set_up_its_log_keeps_it():
    """An embedding host, or a test runner, configured logging on purpose; nothing is added."""
    mine = logging.StreamHandler()
    with _a_fresh_process():
        logging.getLogger().addHandler(mine)

        assert logs.configure() is False
        assert logging.getLogger().handlers == [mine]
        assert logging.getLogger("openfactory").level == logging.NOTSET


def test_the_time_is_UTC_whatever_the_machines_zone(monkeypatch):
    """The panel's line and the worker's about one moment carry one time, wherever each runs."""
    import time

    monkeypatch.setenv("TZ", "America/Sao_Paulo")
    time.tzset()
    try:
        record = logging.LogRecord("openfactory.panel", logging.WARNING, __file__, 1, UNLISTED,
                                   None, None)
        record.created, record.msecs = 0.25, 250.0
        with _a_fresh_process():
            logs.configure()
            said = logging.getLogger().handlers[0].format(record)
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()

    assert said == f"1970-01-01T00:00:00.250Z WARNING openfactory.panel: {UNLISTED}", said
