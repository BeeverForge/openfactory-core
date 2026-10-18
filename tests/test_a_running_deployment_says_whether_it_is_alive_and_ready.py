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
    `health.deadline()` whatever a check waits on, and that deadline follows the engine's own;
    every check is asked at most once per `health.WINDOW_S`, by one caller at a time; and the cause
    of a failure is logged once per change, by any logger, and never sent;
  · READINESS COSTS NOBODY ELSE ANYTHING (review of #818): a check that is slow or hangs holds no
    thread the gate needs, never blocks the event loop, and is never reported as another check;
  · each check fails for its own dependency: the engine that does not answer (and a pooled client
    is not an answer), the registry that cannot be read, and the identity provider that cannot
    admit — which is the gate's own decision, so the two are held to the same verdicts;
  · the panel and the worker serve the same answers — the worker on this machine's loopback
    unless the deployment says otherwise, once its boot's own steps are done — and every process
    the compose file starts from this repository is health-checked by `/readyz` on the port it
    answers on.

WHAT IS DOUBLED, AND ONLY THAT: the engine's client (a double that answers or does not), and the
identity provider where a case needs a state the built-in rows cannot be put in. The routes, the
gate, the checks, the registry on disk, the worker's listener on a real socket and the probe a
healthcheck runs are the real ones.
"""

from __future__ import annotations

import ast
import asyncio
import concurrent.futures
import inspect
import json
import logging
import threading
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
        if self._engine.held is not None:
            await self._engine.held.wait()
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
        self.connect_delay = 0.0
        #: what a connect raises — a stopped engine refuses it
        self.refused: BaseException | None = None
        #: an `asyncio.Event` the health check waits on — an engine that never answers
        self.held: asyncio.Event | None = None
        self.service_client = _Service(self)


@pytest.fixture
def engine(monkeypatch):
    from openfactory.runtime.temporal import view

    double = _Engine()

    async def _connect():
        if double.connect_delay:
            await asyncio.sleep(double.connect_delay)
        if double.refused is not None:
            raise double.refused
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
    engine.refused = ConnectionError("connection refused by 10.0.0.7:7233")


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


@pytest.mark.parametrize("broken", sorted(health.CHECKS))
async def test_a_failure_is_logged_once_by_anybody_and_never_sent(deployment, engine,
                                                                  monkeypatch, caplog, broken):
    """The body goes to a caller nobody identified; the cause is the operator's, in the log — ONE
    warning when the check starts failing, from ANY logger, however many supervisors' polls fall
    in new windows (review of #818: four polls of a stopped engine logged four warnings, from the
    floor's probe the engine check reused)."""
    clock = [1000.0]
    monkeypatch.setattr(health, "_clock", lambda: clock[0])
    BREAK[broken](monkeypatch, engine, deployment)

    with caplog.at_level(logging.INFO):
        said = []
        for _ in range(4):
            said.append(json.dumps(await health.ready()))
            clock[0] += health.WINDOW_S

    warned = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warned) == 1 and "NOT_READY" in warned[0].getMessage(), [
        (r.name, r.getMessage()) for r in warned]
    assert not any("10.0.0.7" in body for body in said), said


async def test_a_check_that_answers_again_is_said_once(deployment, engine, monkeypatch, caplog):
    clock = [1000.0]
    monkeypatch.setattr(health, "_clock", lambda: clock[0])
    BREAK["engine"](monkeypatch, engine, deployment)
    await health.ready()

    engine.refused = None
    with caplog.at_level(logging.INFO, logger="openfactory.health"):
        for _ in range(3):
            clock[0] += health.WINDOW_S
            assert (await health.ready())["ready"] is True

    assert sum("answers again" in r.getMessage() for r in caplog.records) == 1, caplog.text


# ── readiness: bounded, and kind to the engine ──────────────────────────────────────────────────

@pytest.mark.parametrize("slow", sorted(health.CHECKS))
async def test_a_check_that_hangs_is_named_within_the_deadline(deployment, monkeypatch, slow):
    async def hangs():
        await asyncio.sleep(10)

    monkeypatch.setattr(health, "deadline", lambda: 1.5)
    monkeypatch.setitem(health.CHECKS, slow, hangs)

    started = time.monotonic()
    body = await health.ready()

    assert time.monotonic() - started < 6.0, "readiness waited on a check past its deadline"
    assert body["failing"] == [slow], body
    assert body["checks"][slow]["detail"].startswith(health.SAID[slow]), body


def _counted(monkeypatch, *, delay: float = 0.0) -> dict[str, int]:
    """Every check in `CHECKS`, wrapped to count the questions its dependency is asked."""
    asked = dict.fromkeys(health.CHECKS, 0)
    for name, check in list(health.CHECKS.items()):
        async def counted(name=name, check=check):
            asked[name] += 1
            if delay:
                await asyncio.sleep(delay)
            await check()
        monkeypatch.setitem(health.CHECKS, name, counted)
    return asked


async def test_every_checks_answer_is_kept_for_its_window(deployment, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(health, "_clock", lambda: clock[0])
    asked = _counted(monkeypatch)

    for _ in range(5):
        assert (await health.ready())["ready"] is True
    assert asked == dict.fromkeys(health.CHECKS, 1), f"asked again inside the window: {asked}"

    clock[0] += health.WINDOW_S
    await health.ready()
    assert asked == dict.fromkeys(health.CHECKS, 2), f"not asked once the window passed: {asked}"


async def test_a_kept_failure_clears_when_the_window_passes(deployment, engine, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(health, "_clock", lambda: clock[0])
    engine.answer = False

    assert (await health.ready())["failing"] == ["engine"]
    engine.answer = True
    assert (await health.ready())["failing"] == ["engine"], "the window keeps the answer"
    clock[0] += health.WINDOW_S
    assert (await health.ready())["ready"] is True


async def test_supervisors_that_ask_together_share_one_question_per_check(deployment,
                                                                          monkeypatch):
    asked = _counted(monkeypatch, delay=0.05)

    answers = await asyncio.gather(*(health.ready() for _ in range(6)))

    assert all(a["ready"] for a in answers)
    assert asked == dict.fromkeys(health.CHECKS, 1), asked


async def test_an_answer_whose_question_lost_its_slot_is_not_kept(deployment, engine,
                                                                  monkeypatch):
    """`forget` takes the slot from under a question in flight; an answer begun before it must not
    serve the window after it."""
    clock = [1000.0]
    monkeypatch.setattr(health, "_clock", lambda: clock[0])
    engine.delay = 0.1

    first = asyncio.create_task(health.ready())
    await asyncio.sleep(0.02)
    health.forget()
    await first
    engine.delay = 0.0
    await health.ready()

    assert engine.asked == 2, "the answer of a question that lost its slot was kept"


def test_the_window_is_a_few_seconds_and_the_deadline_makes_room_for_the_engine(monkeypatch):
    """A window long enough to hide an outage is a probe that lies; so is a deadline shorter than
    the engine's own two bounded steps, a connect and a health check (review of #818)."""
    from openfactory.runtime.temporal import view

    assert 1.0 <= health.WINDOW_S <= 10.0
    for said in (None, "0.5", "3", "10"):
        if said is None:
            monkeypatch.delenv("OPENFACTORY_ENGINE_DEADLINE", raising=False)
        else:
            monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", said)
        assert health.deadline() > 2 * view.read_deadline(), (said, health.deadline())


async def test_a_slow_engine_inside_its_own_deadline_is_ready(deployment, engine, monkeypatch):
    """Whatever the fallback, the deployment's engine deadline is what readiness waits for."""
    monkeypatch.setattr(health, "DEADLINE_S", 0.4)
    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "1.5")
    engine.connect_delay = engine.delay = 0.3

    assert (await health.ready())["ready"] is True


# ── readiness costs nobody else anything (review of #818) ───────────────────────────────────────

#: What makes each check's OWN dependency stop answering until it is released, by the name
#: `health.CHECKS` gives it — a registry on a mount that stopped, a people store that does not
#: answer, an engine that never answers. Each returns `(entered, release)`. A check added without
#: a way to hang it here fails `test_every_check_can_be_hung_here`.
def _hang_engine(monkeypatch, engine):
    engine.held = asyncio.Event()
    return (lambda: engine.asked), engine.held.set


def _hanging(monkeypatch, attribute):
    entered, gate = [], threading.Event()

    def hangs():
        entered.append(threading.current_thread().name)
        gate.wait(10)   # bounded, so a check that blocks the loop ends the case rather than it

    monkeypatch.setattr(health, attribute, hangs)
    return (lambda: len(entered)), gate.set


HANG = {
    "engine": _hang_engine,
    "registry": lambda monkeypatch, _engine: _hanging(monkeypatch, "_registry_reads"),
    "identity": lambda monkeypatch, _engine: _hanging(monkeypatch, "_identity_admits"),
}


def test_every_check_can_be_hung_here():
    assert set(HANG) == set(health.CHECKS)


@pytest.mark.parametrize("hung", sorted(health.CHECKS))
async def test_a_hung_check_starves_no_request_and_blames_no_other_check(deployment, engine,
                                                                         monkeypatch, hung):
    """The review's probe, made deterministic. The executor the gate's verdict hops to is given ONE
    thread; twenty unauthenticated `/readyz` arrive while one check's dependency hangs; an
    operator's request must still be answered at once, each `/readyz` must name the hung check and
    no other, within the deadline, and the dependency must have been asked once — by one question,
    on a thread that is not the gate's. A check that blocked the event loop instead would hold
    every one of those answers for as long as it hangs."""
    import httpx

    from openfactory.api.app import app

    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", "the-operator")
    monkeypatch.setattr(health, "deadline", lambda: 1.5)
    loop = asyncio.get_running_loop()
    loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=1))
    entered, release = HANG[hung](monkeypatch, engine)
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://panel", timeout=10) as client:
            polls = [asyncio.create_task(client.get(health.READY_PATH)) for _ in range(20)]
            await asyncio.sleep(0.05)
            operator = await asyncio.wait_for(
                client.get("/api/whoami", headers={"Authorization": "Bearer the-operator"}), 3.0)
            answers = await asyncio.wait_for(asyncio.gather(*polls), 6.0)
    finally:
        release()

    assert operator.status_code == 200, operator.text
    assert time.monotonic() - started < 8.0, "the loop was held while a dependency hung"
    for answer in answers:
        assert answer.status_code == 503 and answer.json()["failing"] == [hung], answer.json()
    assert entered() == 1, f"the hung dependency was asked {entered()} times"


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


async def test_an_engine_that_cannot_be_connected_to_is_not_ready(deployment, engine):
    engine.refused = ConnectionError("connection refused")

    assert await _engine_said() == {"ok": False, "detail": health.SAID["engine"]}


async def test_an_engine_nobody_declared_is_said_as_such(deployment, monkeypatch):
    """Not "did not answer": that sends its reader to a network, and the remedy is a variable."""
    for name in ("TEMPORAL_ADDRESS", "TEMPORAL_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)

    assert await _engine_said() == {"ok": False, "detail": health.ENGINE_UNDECLARED}


@pytest.mark.parametrize(("missing", "said"), [("temporalio", "install"),
                                                ("openfactory.something_else", "engine")])
async def test_an_install_without_the_engines_client_says_what_to_install(deployment, monkeypatch,
                                                                         missing, said):
    """The install sentence only when the client library is what is missing (`host`'s rule): the
    engine's reader is made unimportable for want of `missing`, as an install without the
    `runtime` extra makes it."""
    import builtins

    from openfactory.runtime.host import CLIENT_MISSING

    real = builtins.__import__

    def _without(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "openfactory.runtime.temporal" and "view" in (fromlist or ()):
            raise ModuleNotFoundError(f"No module named {missing!r}", name=missing)
        return real(name, globals, locals, fromlist, level)

    with monkeypatch.context() as patched:
        patched.setattr(builtins, "__import__", _without)
        said_now = await _engine_said()

    expected = CLIENT_MISSING if said == "install" else health.SAID["engine"]
    assert said_now == {"ok": False, "detail": expected}


async def test_an_engine_that_does_not_answer_in_time_is_not_ready(deployment, engine,
                                                                  monkeypatch):
    """The health check is bounded like every read of the engine (`view._within`)."""
    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "0.05")
    engine.delay = 0.5   # inside readiness's own deadline (1.1 s here), past the engine's

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
    (b"GET /metrics-of-acme HTTP/1.1\r\nHost: x\r\n\r\n", 404),
    (b"POST /readyz HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n", 405),
    (b"not http at all\r\n\r\n", 400),
])
async def test_the_worker_answers_nothing_else_and_echoes_nothing(worker_port, request_, status):
    got, body = await _get(worker_port, request_)

    assert got == status
    assert "acme" not in json.dumps(body), body


async def test_the_worker_answers_on_loopback_unless_the_deployment_says_otherwise(monkeypatch):
    """Readiness is asked without a credential, so it is answered beyond this machine only where
    the deployment says so — `openfactory serve`'s own default (review of #818)."""
    monkeypatch.delenv(health.HOST_VARIABLE, raising=False)
    server = await health.listen(0)
    try:
        bound = {sock.getsockname()[0] for sock in server.sockets}
    finally:
        server.close()
    assert bound == {health.LOOPBACK}, bound

    monkeypatch.setenv(health.HOST_VARIABLE, "0.0.0.0")
    server = await health.listen(0)
    try:
        bound = {sock.getsockname()[0] for sock in server.sockets}
    finally:
        server.close()
    assert bound == {"0.0.0.0"}, bound


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


#: The steps of the worker's boot that run on its loop and hold it — the app key, the registry's
#: seed, the toolbox's first copy (~800 MB), the registry read and the channels' start.
BLOCKING_BOOT = ("materialize_app_key", "seed_registry", "populate_toolbox", "list",
                 "start_channel_listeners")


def test_the_worker_opens_its_listener_once_its_loop_is_free_and_before_it_waits():
    """Reachability, read off `main`: the listener is opened AFTER every step that holds the loop
    — a listener opened before them accepted connections and answered nothing (review of #818) —
    and BEFORE the wait for the engine, which only awaits, so a supervisor is answered then."""
    from openfactory.runtime.temporal import worker

    tree = ast.parse(inspect.getsource(worker.main))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]

    def first(name: str) -> int:
        lines = [n.lineno for n in calls
                 if name in (getattr(n.func, "attr", ""), getattr(n.func, "id", ""))]
        assert lines, f"`main` never calls {name}"
        return min(lines)

    assert max(first(step) for step in BLOCKING_BOOT) < first("listen") < first("connect_at_birth")


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


def test_a_healthchecks_timeout_outlasts_the_readiness_deadline(monkeypatch):
    """Under the compose file's own environment, which leaves the engine's deadline at its
    default."""
    for name, svc in _compose_services().items():
        environment = svc.get("environment") or {}
        if "OPENFACTORY_ENGINE_DEADLINE" in environment:
            monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE",
                               str(environment["OPENFACTORY_ENGINE_DEADLINE"]))
        else:
            monkeypatch.delenv("OPENFACTORY_ENGINE_DEADLINE", raising=False)
        timeout = str(svc["healthcheck"]["timeout"])
        assert timeout.endswith("s") and float(timeout[:-1]) > health.deadline(), (name, timeout)


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
