"""A running deployment says whether it is alive and whether it can work, without a credential (#681).

WHAT WAS MISSING. No route answered either question. The compose file had healthchecks for the
engine's database and the engine, and none for the worker or the panel, so a panel that could not
reach the engine stayed "running" and anything waiting on it waited.

THE RULES THIS FILE HOLDS:

  · `/healthz` answers 200 while the process serves — with no credential, and reading nothing: it
    answers with every dependency broken;
  · `/readyz` answers 200 when every check in `health.CHECKS` passes and 503 otherwise, naming each
    check that failed and no other — the checks are read from that table, so one added tomorrow is
    held here without anybody listing it; it needs no credential; it answers within
    `health.DEADLINE_S` whatever a check waits on; and the engine is asked at most once per
    `health.ENGINE_TTL_S`, by one caller at a time;
  · each check fails for its own dependency: the engine that does not answer (and a pooled client
    is not an answer), the registry that cannot be read, and the identity provider that cannot
    admit — which is the gate's own decision, so the two are held to the same verdicts;
  · the panel and the worker serve the same answers, and every process the compose file starts
    from this repository is health-checked by `/readyz` on the port it answers on.

WHAT IS DOUBLED, AND ONLY THAT: the engine's client (a double that answers or does not), and the
identity provider where a case needs a state the built-in rows cannot be put in. The routes, the
gate, the checks, the registry on disk, the worker's listener on a real socket and the probe a
healthcheck runs are the real ones.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from openfactory.observability import health

ROOT = Path(__file__).resolve().parents[1]


# ── the bench ───────────────────────────────────────────────────────────────────────────────────

class _Service:
    def __init__(self, engine):
        self._engine = engine

    async def check_health(self, **_kw):
        self._engine.asked += 1
        if self._engine.delay:
            await asyncio.sleep(self._engine.delay)
        if isinstance(self._engine.answer, BaseException):
            raise self._engine.answer
        return self._engine.answer


class _Engine:
    """A pooled client double: it is always handed back, whether or not the engine behind it
    answers — which is exactly what a real pooled client does after the engine went away."""

    def __init__(self):
        self.answer: object = True
        self.asked = 0
        self.delay = 0.0
        self.service_client = _Service(self)


@pytest.fixture
def engine(monkeypatch):
    from openfactory.runtime.temporal import view

    double = _Engine()

    async def _connect():
        return double

    monkeypatch.setenv("TEMPORAL_ADDRESS", "localhost:7233")
    monkeypatch.setattr(view, "connect", _connect)
    return double


@pytest.fixture
def deployment(tmp_path, monkeypatch, engine):
    """A readable registry with one fictitious project, the open `local` identity row, and an
    engine that answers."""
    for name in ("OPENFACTORY_IDENTITY", "OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PANEL_TOKENS",
                 "OPENFACTORY_PRODUCT_TOKEN", "OPENFACTORY_PRODUCT_TOKENS",
                 "OPENFACTORY_BOARD_TOKEN", "OPENFACTORY_BOARD_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "null")
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"projects": {"acme": {
        "name": "acme", "repo_path": str(tmp_path),
        "tracker": {"kind": "local", "repo": "acme"}}}}))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(registry))
    return registry


def _panel() -> TestClient:
    from openfactory.api.app import app

    return TestClient(app)


#: What breaks each check's OWN dependency, by the name `health.CHECKS` gives it. A check added to
#: the table without a way to break it here fails `test_every_check_is_broken_here`.
def _break_engine(monkeypatch, engine, _registry):
    engine.answer = ConnectionError("connection refused")


def _break_registry(monkeypatch, _engine, registry):
    registry.write_text("projects: [this is: not, valid")


def _break_identity(monkeypatch, _engine, _registry):
    monkeypatch.setenv("OPENFACTORY_IDENTITY", "no-such-provider")


BREAK = {"engine": _break_engine, "registry": _break_registry, "identity": _break_identity}


# ── liveness ────────────────────────────────────────────────────────────────────────────────────

def test_the_process_is_alive_with_every_dependency_broken_and_no_credential(deployment, engine,
                                                                            monkeypatch):
    """Nothing is read: a liveness probe that asked the engine would restart a healthy panel for
    the engine's outage. Every dependency broken, a credential configured and none presented."""
    for name in BREAK:
        BREAK[name](monkeypatch, engine, deployment)
    monkeypatch.setenv("OPENFACTORY_IDENTITY", "local")
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", "the-operator")
    asked: list[str] = []
    for name in health.CHECKS:
        monkeypatch.setitem(health.CHECKS, name, _never_asked(name, asked))

    answer = _panel().get(health.LIVE_PATH)

    assert (answer.status_code, answer.json()) == (200, {"alive": True}), answer.text
    assert asked == [] and engine.asked == 0, f"liveness asked {asked}"


def _never_asked(name, asked):
    async def check():
        asked.append(name)
    return check


# ── readiness: the table ────────────────────────────────────────────────────────────────────────

def test_every_check_is_broken_here():
    assert set(BREAK) == set(health.CHECKS) == set(health.SAID), (
        "a check with no way to break it, or no sentence to say, is a check nobody proved")


def test_ready_when_every_check_passes(deployment):
    answer = _panel().get(health.READY_PATH)

    assert answer.status_code == 200, answer.text
    assert answer.json() == {"ready": True, "failing": [],
                             "checks": {name: {"ok": True} for name in health.CHECKS}}


@pytest.mark.parametrize("broken", sorted(health.CHECKS))
def test_a_503_names_the_check_that_failed_and_no_other(deployment, engine, monkeypatch, broken):
    BREAK[broken](monkeypatch, engine, deployment)

    answer = _panel().get(health.READY_PATH)

    assert answer.status_code == 503, answer.text
    body = answer.json()
    assert body["ready"] is False and body["failing"] == [broken], body
    assert body["checks"][broken] == {"ok": False, "detail": health.SAID[broken]}, body
    assert all(body["checks"][name] == {"ok": True} for name in health.CHECKS if name != broken)


def test_every_failing_check_is_named_at_once(deployment, engine, monkeypatch):
    for name in BREAK:
        BREAK[name](monkeypatch, engine, deployment)

    body = _panel().get(health.READY_PATH).json()

    assert body["failing"] == list(health.CHECKS), body


def test_readiness_needs_no_credential(deployment, monkeypatch):
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", "the-operator")
    client = _panel()

    assert client.get("/api/projects").status_code == 401, "the gate is on for this case"
    assert client.get(health.READY_PATH).status_code == 200


def test_the_cause_reaches_the_log_once_and_never_the_body(deployment, engine, monkeypatch,
                                                           caplog):
    """The body goes to a caller nobody identified; the cause is the operator's, in the log — once
    when the check starts failing and once when it answers again, not on every poll."""
    engine.answer = ConnectionError("refused by 10.0.0.7:7233")
    monkeypatch.setattr(health, "ENGINE_TTL_S", 0.0)
    client = _panel()

    with caplog.at_level("INFO", logger="openfactory.health"):
        said = [client.get(health.READY_PATH).text for _ in range(3)]
        engine.answer = True
        client.get(health.READY_PATH)

    assert not any("10.0.0.7" in body for body in said), said
    failed = [r for r in caplog.records if "NOT_READY" in r.getMessage()]
    assert len(failed) == 1 and "10.0.0.7" in failed[0].getMessage(), caplog.text
    assert sum("answers again" in r.getMessage() for r in caplog.records) == 1, caplog.text


# ── readiness: bounded, and kind to the engine ──────────────────────────────────────────────────

@pytest.mark.parametrize("slow", sorted(health.CHECKS))
async def test_a_check_that_hangs_is_named_within_the_deadline(deployment, monkeypatch, slow):
    async def hangs():
        await asyncio.sleep(5)

    monkeypatch.setattr(health, "DEADLINE_S", 0.2)
    monkeypatch.setitem(health.CHECKS, slow, hangs)

    started = time.monotonic()
    body = await health.ready()

    assert time.monotonic() - started < 2.0, "readiness waited on a check past its deadline"
    assert body["failing"] == [slow], body
    assert body["checks"][slow]["detail"].startswith(health.SAID[slow]), body


async def test_the_engines_answer_is_kept_for_its_window(deployment, engine, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(health, "_clock", lambda: clock[0])

    for _ in range(5):
        assert (await health.ready())["ready"] is True
    assert engine.asked == 1, "asked again inside the window"

    clock[0] += health.ENGINE_TTL_S
    await health.ready()
    assert engine.asked == 2, "not asked again once the window passed"


async def test_a_kept_failure_clears_when_the_window_passes(deployment, engine, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(health, "_clock", lambda: clock[0])
    engine.answer = False

    assert (await health.ready())["failing"] == ["engine"]
    engine.answer = True
    assert (await health.ready())["failing"] == ["engine"], "the window keeps the answer"
    clock[0] += health.ENGINE_TTL_S
    assert (await health.ready())["ready"] is True


async def test_supervisors_that_ask_together_share_one_check(deployment, engine):
    engine.delay = 0.05

    answers = await asyncio.gather(*(health.ready() for _ in range(6)))

    assert all(a["ready"] for a in answers) and engine.asked == 1, engine.asked


def test_the_window_and_the_deadline_are_a_few_seconds():
    """A window long enough to hide an outage, or a deadline past a healthcheck's own timeout,
    would each be a probe that lies."""
    assert 1.0 <= health.ENGINE_TTL_S <= 10.0
    assert 1.0 <= health.DEADLINE_S <= 9.0


# ── each check, against its own dependency ──────────────────────────────────────────────────────

async def _engine_said() -> dict:
    return await health._verdict("engine")


async def test_a_pooled_client_is_not_an_answer(deployment, engine):
    """`connect()` hands the pooled client back long after the engine behind it went away."""
    engine.answer = ConnectionError("the engine went away")

    assert await _engine_said() == {"ok": False, "detail": health.SAID["engine"]}
    assert engine.asked == 1


async def test_an_engine_whose_service_is_not_serving_is_not_ready(deployment, engine):
    engine.answer = False

    assert (await _engine_said())["ok"] is False


async def test_an_engine_that_cannot_be_connected_to_is_not_ready(deployment, monkeypatch):
    from openfactory.runtime.temporal import view

    async def _refused():
        raise ConnectionError("connection refused")

    monkeypatch.setattr(view, "connect", _refused)

    assert await _engine_said() == {"ok": False, "detail": health.SAID["engine"]}


async def test_an_engine_nobody_declared_is_said_as_such(deployment, monkeypatch):
    """Not "did not answer": that sends its reader to a network, and the remedy is a variable."""
    for name in ("TEMPORAL_ADDRESS", "TEMPORAL_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)

    assert await _engine_said() == {"ok": False, "detail": health.ENGINE_UNDECLARED}


async def test_an_install_without_the_engines_client_says_what_to_install(deployment, monkeypatch):
    from openfactory.floor import reading
    from openfactory.runtime.host import CLIENT_MISSING

    async def _no_client(_client):
        return None, False, "", CLIENT_MISSING

    monkeypatch.setattr(reading, "_engine", _no_client)

    assert await _engine_said() == {"ok": False, "detail": CLIENT_MISSING}


async def test_an_engine_that_does_not_answer_in_time_is_not_ready(deployment, engine,
                                                                  monkeypatch):
    """The health check is bounded like every read of the engine (`view._within`)."""
    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "0.05")
    engine.delay = 1.0

    assert (await _engine_said())["ok"] is False


async def test_a_registry_that_cannot_be_read_is_not_ready(deployment):
    deployment.write_text("projects:\n  acme: {name: acme, tracker: 7}\n")

    assert await health._verdict("registry") == {"ok": False,
                                                 "detail": health.SAID["registry"]}


async def test_an_empty_registry_is_ready(tmp_path, monkeypatch):
    """A new install has registered nothing yet; that is a registry that reads."""
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "nothing-yet.yaml"))

    assert await health._verdict("registry") == {"ok": True}


# ── the identity provider: the gate's own decision ──────────────────────────────────────────────

class _Open:
    def open_to_everyone(self):
        return True

    def identify(self, *, credential, via=""):
        return None


class _Closed:
    def open_to_everyone(self):
        return False

    def identify(self, *, credential, via=""):
        return None


class _StoreDown(_Closed):
    def unavailable(self):
        return "the people store did not answer"


def _cannot_be_built():
    raise ValueError("an `oidc` row with no issuer")


class _UnreadableStore:
    """The people store the `local` row reads, when it cannot be read."""

    def has_people(self):
        from openfactory.observability.query import StoreUnreadable

        raise StoreUnreadable("database is locked")


def _local_over(store):
    def build():
        from openfactory.identity.local import LocalIdentity

        return LocalIdentity(env={}, store=store)
    return build


#: Every answer the gate can give a provider, before any credential is judged. The built-in rows
#: are asked as they are configured below; the states they cannot be put in without a store are
#: doubles, as `tests/test_the_gate_holds_when_the_store_cannot_be_read.py` builds them.
DOORS = {
    "open (nothing configured)": lambda: _Open(),
    "closed (credentials configured)": lambda: _Closed(),
    "the store it reads did not answer": lambda: _StoreDown(),
    "the provider cannot be built": _cannot_be_built,
    "the local row, its store unreadable": _local_over(_UnreadableStore()),
}


@pytest.mark.parametrize("door", sorted(DOORS))
async def test_the_identity_check_is_the_gates_own_decision(deployment, monkeypatch, door):
    from openfactory.api import app as api

    monkeypatch.setattr("openfactory.identity.build_identity", DOORS[door])

    gate = api._admission("")
    ready = await health._verdict("identity")

    assert ready["ok"] is (not gate.unavailable), (door, gate, ready)


def test_the_doors_cover_every_answer_the_gate_gives(monkeypatch):
    """An enumeration that quietly lost a state would agree with the gate about nothing."""
    from openfactory.api import app as api

    seen = set()
    for door in DOORS.values():
        monkeypatch.setattr("openfactory.identity.build_identity", door)
        gate = api._admission("")
        seen.add("open" if gate.open else gate.unavailable or "closed")
    assert seen == {"open", "closed", api.IDENTITY_UNAVAILABLE, api.PEOPLE_UNAVAILABLE}, seen


@pytest.mark.parametrize("kind", ["local", "oidc", "no-such-provider"])
async def test_each_identity_row_as_configured_agrees_with_the_gate(deployment, monkeypatch, kind):
    """The rows the core ships (`identity.IDENTITIES`) and a kind nobody ships, built for real."""
    from openfactory.api import app as api
    from openfactory.identity import IDENTITIES

    assert set(IDENTITIES) <= {"local", "oidc"}, "a new built-in row: add it to this case"
    monkeypatch.setenv("OPENFACTORY_IDENTITY", kind)
    for name in ("OPENFACTORY_OIDC_ISSUER", "OPENFACTORY_OIDC_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)

    gate = api._admission("")
    ready = await health._verdict("identity")

    assert ready["ok"] is (not gate.unavailable), (kind, gate, ready)


# ── the worker answers the same, on its own port ────────────────────────────────────────────────

async def _get(port: int, request: bytes) -> tuple[int, dict | str]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(request)
    await writer.drain()
    raw = await asyncio.wait_for(reader.read(), 10)
    writer.close()
    head, _, body = raw.partition(b"\r\n\r\n")
    status = int(head.split()[1])
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body.decode()


@pytest.fixture
async def worker_port(deployment):
    server = await health.listen(0, host="127.0.0.1")
    assert server is not None
    yield server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()


async def test_the_worker_answers_what_the_panel_answers(worker_port, engine, monkeypatch,
                                                         deployment):
    alive = await _get(worker_port, b"GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n")
    ready = await _get(worker_port, b"GET /readyz HTTP/1.1\r\nHost: x\r\n\r\n")
    assert alive == (200, {"alive": True})
    assert ready == (200, _panel().get(health.READY_PATH).json())

    health.forget()
    BREAK["registry"](monkeypatch, engine, deployment)
    status, body = await _get(worker_port, b"GET /readyz?verbose=1 HTTP/1.1\r\nHost: x\r\n\r\n")
    assert status == 503 and body["failing"] == ["registry"], body


@pytest.mark.parametrize(("request_", "status"), [
    (b"GET /metrics HTTP/1.1\r\nHost: x\r\n\r\n", 404),
    (b"POST /readyz HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n", 405),
    (b"not http at all\r\n\r\n", 400),
])
async def test_the_worker_answers_nothing_else(worker_port, request_, status):
    assert (await _get(worker_port, request_))[0] == status


async def test_the_worker_listens_only_when_a_port_is_asked(monkeypatch, caplog):
    monkeypatch.delenv(health.PORT_VARIABLE, raising=False)
    assert await health.listen() is None

    monkeypatch.setenv(health.PORT_VARIABLE, "eighty")
    with caplog.at_level("ERROR", logger="openfactory.health"):
        assert await health.listen() is None
    assert "is not a port" in caplog.text


async def test_a_port_that_is_taken_is_said_and_the_worker_goes_on(caplog):
    held = await asyncio.start_server(lambda r, w: None, host="127.0.0.1", port=0)
    port = held.sockets[0].getsockname()[1]
    try:
        with caplog.at_level("ERROR", logger="openfactory.health"):
            got = await health.listen(port, host="127.0.0.1")
    finally:
        held.close()
    assert got is None
    assert "nothing can ask it whether it is ready" in caplog.text


def test_the_worker_starts_its_listener_before_it_waits_for_anything():
    """Reachability, read off `main`: the listener is opened, and before the wait for the engine
    and the toolbox's first copy — exactly when a supervisor asks."""
    from openfactory.runtime.temporal import worker

    tree = ast.parse(inspect.getsource(worker.main))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]

    def first(name: str) -> int:
        lines = [n.lineno for n in calls
                 if name in (getattr(n.func, "attr", ""), getattr(n.func, "id", ""))]
        assert lines, f"`main` never calls {name}"
        return min(lines)

    assert first("listen") < first("populate_toolbox") < first("connect_at_birth")


# ── the healthcheck a container runs ────────────────────────────────────────────────────────────

def _compose_services() -> dict[str, dict]:
    """The long-running processes the compose file starts from this repository — read as the
    log guard reads them: built here, and not the build-only profile."""
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    return {name: svc for name, svc in compose["services"].items()
            if svc.get("build") and "build" not in (svc.get("profiles") or [])}


def _answers_on(svc: dict) -> int | None:
    """The port a service answers `/readyz` on: the panel's `serve --port`, or the worker's
    `OPENFACTORY_HEALTH_PORT`."""
    command = [str(c) for c in svc.get("command") or []]
    if "serve" in command and "--port" in command:
        return int(command[command.index("--port") + 1])
    port = (svc.get("environment") or {}).get(health.PORT_VARIABLE)
    return int(port) if port else None


def test_every_process_the_compose_file_starts_is_health_checked_by_readyz():
    services = _compose_services()
    assert {"worker", "panel"} <= set(services), sorted(services)

    for name, svc in services.items():
        test = (svc.get("healthcheck") or {}).get("test") or []
        assert test[:4] == ["CMD", "python", "-m", "openfactory.observability.health"], (name, test)
        asked = health.parser().parse_args(test[4:])
        assert asked.path == health.READY_PATH, (name, test)
        assert asked.port == _answers_on(svc), (
            f"{name}'s healthcheck asks port {asked.port}, and it answers on {_answers_on(svc)}")


def test_a_healthchecks_timeout_outlasts_the_readiness_deadline():
    for name, svc in _compose_services().items():
        timeout = str(svc["healthcheck"]["timeout"])
        assert timeout.endswith("s") and float(timeout[:-1]) > health.DEADLINE_S, (name, timeout)


async def test_the_probe_exits_0_when_ready_and_1_with_the_body_when_not(worker_port, engine,
                                                                        monkeypatch, deployment,
                                                                        capfd):
    args = ["--port", str(worker_port)]

    assert await asyncio.to_thread(health.main, args) == 0
    health.forget()
    BREAK["engine"](monkeypatch, engine, deployment)
    assert await asyncio.to_thread(health.main, args) == 1
    assert '"failing": ["engine"]' in capfd.readouterr().err


def test_the_probe_exits_1_when_nothing_answers(capfd):
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free = sock.getsockname()[1]

    assert health.main(["--port", str(free), "--path", health.LIVE_PATH]) == 1
    assert "did not answer" in capfd.readouterr().err


def test_the_contract_lists_the_probes_the_panel_serves():
    """`docs/reference/the-front-end-api.md` is the API's contract; its routes table holds what is
    under `/api/`, and the probes table what a supervisor asks outside it."""
    from fastapi.routing import APIRoute

    from openfactory.api.app import app

    text = (ROOT / "docs" / "reference" / "the-front-end-api.md").read_text(encoding="utf-8")
    table = text.split("<!-- probes:start -->")[1].split("<!-- probes:end -->")[0]
    rows = {tuple(cell.strip().strip("`") for cell in line.strip().strip("|").split("|")[:2])
            for line in table.splitlines() if line.strip().startswith("| GET")}
    served = {("GET", r.path) for r in app.routes
              if isinstance(r, APIRoute) and r.path in health.PATHS and "GET" in r.methods}

    assert rows == served == {("GET", path) for path in health.PATHS}, (rows, served)
