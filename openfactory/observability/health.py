"""What a supervisor asks a running process (#681): is it alive, can it work right now, and —
with a credential — which version it runs and what is installed into it.

WHAT WAS MISSING. No route answered any of the three. `docker-compose.yml` had a healthcheck for
the engine's database and for the engine, and none for the worker or the panel, so a panel that was
up but could not reach the engine stayed "running", and anything waiting on it waited. The facts
readiness needs were already computed, but only inside other answers: the engine in the floor's
reading, the registry inline in the routes, the identity provider in the gate's admission.

THREE ANSWERS, AND WHAT EACH MAY COST:

  · `alive()` — the process serves. NO I/O AND NO CREDENTIAL: a liveness probe that reads a disk or
    asks an engine restarts a healthy process for somebody else's outage.
  · `ready()` — the engine answers, the registry reads and the identity provider can admit. Each
    failing check is named, and only a check that failed; a supervisor reads 503.
  · `version()` — the package, the image, the kind of address the engine is reached at, and every
    add-on installed with its distribution, version, axis and kind. Behind the credential like the
    rest of `/api/`, because which add-ons a deployment carries is a fact about the deployment.

WHAT READINESS MAY COST, AND THE ANSWER IS "LITTLE, AND NEVER SOMEBODY ELSE'S". It is asked by
anybody, with no credential, as often as they like, so (review of #818, measured: 300 requests at
once against a registry 200 ms slow held an authenticated request for 5 s, and a registry read that
hung filled the default executor until nothing that hops to a thread — the gate included — ran):

  · EVERY CHECK IS ASKED BY ONE CALLER AT A TIME AND KEPT FOR `WINDOW_S`. Callers that arrive
    while a check is in flight share it (`_OneAtATime`, the floor's single flight), and its answer
    serves every caller for the window. A burst costs each dependency one question per window, and
    a check that hangs holds one question, not one per poll.
  · NO CHECK TAKES A THREAD OF THE DEFAULT EXECUTOR. The gate's verdict hops to that executor
    (`api/app.py::_ask_the_gate`), and so do the worker's activities. A blocking check runs on a
    daemon thread of its own (`_off_the_loop`) — at most one per check, by the rule above — so a
    hung registry can stall nothing but the registry check, and a process can still exit.
  · BOUNDED. Every check runs at once, each within `deadline()`, so the answer never waits on a
    dependency longer than that, and a check that is late is named — never the check beside it.

WHAT A CALLER WITH NO CREDENTIAL IS TOLD. Readiness names the check that failed and says one fixed
sentence about it; the cause — an address, a variable's name, a file's path — goes to the log, ONCE
when the check starts failing and once when it answers again, never on every poll. It is the gate's
rule for a caller nobody has identified (`api/app.py::IDENTITY_UNAVAILABLE`). That is READINESS'S
OWN line. A dependency that reports its own failure each time it is read still does so when
readiness reads it — the people store and the metrics sink under it, two lines a window while the
store cannot be read, as for every request the gate checks in that outage (review of #818,
measured: four windows, nine warnings, one readiness's). Silencing another module's line from
here would mean owning every handler's filters, an add-on sink's included; the cause is in
readiness's own line either way. The one cause said in
the body is an install without the engine's client library: what to install is a fact about the
product, not about the deployment, and every other surface says it the same way
(`runtime/host.py::CLIENT_MISSING`).

WHO SERVES THEM. The panel serves `/healthz`, `/readyz` and `/api/v1/version`. The worker serves no
HTTP, so when `OPENFACTORY_HEALTH_PORT` names a port it answers `/healthz` and `/readyz` there
(`listen`), on `OPENFACTORY_HEALTH_HOST` (this machine's loopback unless the deployment says
otherwise, as `openfactory serve` does) — ON ITS OWN EVENT LOOP, so a worker whose loop is stuck
does not answer, which is what a liveness probe is for. The compose file's healthchecks ask both
through `probe`, inside each container:

    python -m openfactory.observability.health --port 8787
"""

from __future__ import annotations

import argparse
import asyncio
import http.client
import json
import logging
import os
import sys
import threading
import time
from collections.abc import Awaitable, Callable
from http import HTTPStatus

from openfactory.floor.reading import _OneAtATime

log = logging.getLogger("openfactory.health")

#: The two routes a supervisor asks without a credential, wherever this process serves them.
LIVE_PATH = "/healthz"
READY_PATH = "/readyz"
PATHS = (LIVE_PATH, READY_PATH)

#: Where the panel answers `version()`, behind the credential (the versioned reads, #678).
VERSION_PATH = "/api/v1/version"

#: The variable that makes a process with no HTTP server of its own — the worker — answer
#: `/healthz` and `/readyz` on a port. Unset, it answers nothing and opens nothing.
PORT_VARIABLE = "OPENFACTORY_HEALTH_PORT"

#: …and the address it answers on. Unset → `LOOPBACK`, the default `openfactory serve` binds the
#: panel to: an orchestrator that probes from outside the process's network says so (`0.0.0.0`).
HOST_VARIABLE = "OPENFACTORY_HEALTH_HOST"
LOOPBACK = "127.0.0.1"

#: The image's digest, as the deployment that pulled it by digest names it. NOT A BUILD ARGUMENT,
#: AND IT CANNOT BE ONE: a digest is the hash of the image, so writing it into the image changes
#: it. The image knows what it was built from (`namespace.build_stamp`); only whoever deployed it
#: knows which digest that became.
IMAGE_DIGEST_VARIABLE = "OPENFACTORY_IMAGE_DIGEST"

#: How long a check's answer is kept. A few seconds: a supervisor learns of a dependency that went
#: away within one of its own polls, and a dozen supervisors polling every second cost each
#: dependency one question per window, not a dozen per second.
WINDOW_S = 5.0

#: What a supervisor reads for each check that failed. One sentence each, never the cause.
SAID = {
    "engine": "the durable engine did not answer",
    "registry": "the project registry could not be read",
    "identity": "the identity provider cannot check credentials",
}

#: …and for an engine nobody declared, which is not an engine that did not answer: that sentence
#: sends its reader to a network, and the remedy is a variable (#163).
ENGINE_UNDECLARED = "this deployment does not say where its durable engine is"


class NotReady(Exception):  # noqa: N818 — a verdict, not an error: the check ran and said no
    """A check that ran and found its dependency not ready: `cause` for the log, and the
    sentence for the caller when it is not the check's own (`SAID`)."""

    def __init__(self, cause: str, *, said: str = "") -> None:
        super().__init__(cause)
        self.cause = cause
        self.said = said


def deadline() -> float:
    """How long `ready()` waits for any one check: room for the engine check's two bounded steps
    — a connect and a health check, each within `OPENFACTORY_ENGINE_DEADLINE` (`read_deadline`,
    three seconds unless the deployment says otherwise) — and a second more. It FOLLOWS that
    setting (review of #818): a fixed five seconds read a slow engine, answering within a deadline
    the deployment raised, as one that "did not answer within 5s" on every poll.

    READ FROM `deadlines`, NOT `view` (review on f48b79fd): the probe below asks this every
    fifteen seconds in each container, and `view` imports the engine's client to answer it."""
    from openfactory.runtime.temporal.deadlines import read_deadline

    return 2 * read_deadline() + 1.0


def probe_timeout() -> float:
    """How long the probe a healthcheck runs waits for its answer: `deadline()` and two seconds
    more, so a check that hangs reaches the supervisor as its 503 — never as "did not answer"."""
    return deadline() + 2.0


# ── liveness ────────────────────────────────────────────────────────────────────────────────────

def alive() -> dict:
    """The process serves. Nothing is read: see the module's first rule."""
    return {"alive": True}


# ── readiness ───────────────────────────────────────────────────────────────────────────────────

def _clock() -> float:
    """The clock the window runs on. A function so a guard can move it, not sleep."""
    return time.monotonic()


async def _off_the_loop(read: Callable[[], None]) -> None:
    """`read()` on a daemon thread of its own, awaited without holding the loop.

    NOT `asyncio.to_thread`: that is the default executor, which the gate and the worker's
    activities share, and a read that hangs would hold one of its threads for as long as it hangs
    (review of #818). A thread of its own costs nobody else anything; single flight keeps it to
    one per check; and a daemon thread never holds a process that is exiting."""
    loop = asyncio.get_running_loop()
    done: asyncio.Future[None] = loop.create_future()

    def settle(error: BaseException | None) -> None:
        if done.done():
            return
        if error is None:
            done.set_result(None)
        else:
            done.set_exception(error)

    def run() -> None:
        error: BaseException | None = None
        try:
            read()
        except BaseException as exc:  # noqa: BLE001 — handed to the waiter, which reports it
            error = exc
        try:
            loop.call_soon_threadsafe(settle, error)
        except RuntimeError:
            log.debug("a readiness check finished after its loop had closed; nobody waits for it")

    threading.Thread(target=run, name=f"openfactory-ready-{getattr(read, '__name__', 'check')}",
                     daemon=True).start()
    await done


async def _engine() -> None:
    """The engine answers its health check. The steps are the floor's probe's (`reading._engine`):
    the client library, the declaration, the pooled and bounded connect — and then the engine's own
    health check, because a pooled client is handed back long after the engine behind it went
    away, and "connected" would then be a memory, not an answer.

    NOT `reading._engine` ITSELF: it warns on every connect that fails, which is right for a floor
    a person reads and wrong here, where the cause is said once per change (review of #818: four
    polls of a stopped engine logged four warnings)."""
    from openfactory.listeners import ENGINE
    from openfactory.runtime.host import CLIENT_MISSING, why_the_engine_cannot_be_read

    try:
        from openfactory.runtime.temporal import view
    except ImportError as exc:
        why = why_the_engine_cannot_be_read(exc)
        raise NotReady(why, said=CLIENT_MISSING if why == CLIENT_MISSING else "") from exc
    if not ENGINE.declared():
        raise NotReady("no engine address is declared", said=ENGINE_UNDECLARED)
    try:
        answered = await view.check_health(await view.connect())
    except Exception as exc:  # noqa: BLE001 — every failure is the same verdict, its cause logged
        raise NotReady(f"{type(exc).__name__}: {str(exc)[:200]}") from exc
    if not answered:
        raise NotReady("the engine answers, but says its workflow service is not serving")


def _registry_reads() -> None:
    """The registry reads: every project in it builds, as every reader of it needs. What it
    raises when it does not is the cause `_verdict` logs."""
    from openfactory.registry import ProjectRegistry

    ProjectRegistry().list()


async def _registry() -> None:
    """`_registry_reads`, off the event loop: a registry is a file, and a file can hang."""
    await _off_the_loop(_registry_reads)


def _identity_admits() -> None:
    """THE GATE'S OWN DECISION, before any credential (`api/app.py::_admission`): a provider that
    cannot be built, or one that answers without the store it depends on, can admit nobody; one
    that is open admits everybody; any other can admit whoever it was configured for. A
    deployment that configured no provider is the open `local` row, and ready. A provider that
    cannot be built raises here, and what it raises is the cause `_verdict` logs.

    `open_to_everyone` IS ASKED FIRST, AS THE GATE ASKS IT, AND NOT ONLY FOR ITS ANSWER: it is the
    read of the store that tells the `local` row whether anybody is registered, and a row says it
    is `unavailable` only once a read has failed."""
    from openfactory.identity import build_identity

    provider = build_identity()
    if getattr(provider, "open_to_everyone", lambda: False)():
        return
    ask = getattr(provider, "unavailable", None)
    why = ask() if callable(ask) else ""
    if isinstance(why, str) and why.strip():
        raise NotReady(why.strip()[:200])


async def _identity() -> None:
    """`_identity_admits`, off the event loop: a provider's store may sit across a network."""
    await _off_the_loop(_identity_admits)


#: Every check `ready()` runs, by the name a 503 says. A check is an async callable that returns
#: when its dependency is ready and raises `NotReady` when it is not; `ready()` asks each through
#: its own `_Slot`, so every check is single-flighted, kept for the window and bounded alike.
CHECKS: dict[str, Callable[[], Awaitable[None]]] = {
    "engine": _engine,
    "registry": _registry,
    "identity": _identity,
}


class _Slot:
    """One check's question in flight and its last answer, `(when, said, cause)` — `said` is
    `""` when the dependency answered."""

    def __init__(self) -> None:
        self.read = _OneAtATime()
        self.kept: tuple[float, str, str] | None = None

    async def kept_or_asked(self, name: str) -> tuple[float, str, str]:
        kept = self.kept
        if kept is not None and _clock() - kept[0] < WINDOW_S:
            return kept
        return await self.read.shared(lambda flight: self._ask(name, flight))

    async def _ask(self, name: str, flight) -> tuple[float, str, str]:
        try:
            await CHECKS[name]()
            said, cause = "", ""
        except NotReady as exc:
            said, cause = exc.said or SAID[name], exc.cause
        except Exception as exc:  # noqa: BLE001 — a check that broke is a check that did not pass
            said, cause = SAID[name], f"{type(exc).__name__}: {str(exc)[:200]}"
        answer = (_clock(), said, cause)
        # KEPT ONLY WHILE THE SLOT IS STILL THIS QUESTION'S: `forget` takes it from under a
        # question in flight, and an answer begun before that must not serve the window after.
        if self.read.holds(flight):
            self.kept = answer
        return answer

    def forget(self) -> None:
        self.kept = None
        self.read.forget()


#: One slot per check — bounded by `CHECKS`, never by traffic.
_SLOTS = {name: _Slot() for name in CHECKS}

#: Each check's last verdict in this process, so the log says a change once, not every poll.
_LAST: dict[str, bool] = {}


def _said_once(name: str, ok: bool, cause: str = "") -> None:
    before = _LAST.get(name)
    _LAST[name] = ok
    if ok and before is False:
        log.info("ready: the %s answers again", name)
    elif not ok and before is not False:
        log.warning("NOT_READY the %s check failed: %s", name, cause or "no cause was given")


async def _verdict(name: str) -> dict:
    """One check, bounded, as the body says it: `{"ok": true}` or `{"ok": false, "detail": …}`.
    A caller that runs out of time leaves the question in flight; it still lands in the window."""
    bound = deadline()
    try:
        _when, said, cause = await asyncio.wait_for(_SLOTS[name].kept_or_asked(name), bound)
    except TimeoutError:
        said, cause = f"{SAID[name]} within {bound:g}s", f"no answer within {bound:g}s"
    if not said:
        _said_once(name, True)
        return {"ok": True}
    _said_once(name, False, cause)
    return {"ok": False, "detail": said}


async def ready() -> dict:
    """`{"ready": …, "checks": {name: verdict}, "failing": [names]}` — every check at once."""
    names = list(CHECKS)
    verdicts = await asyncio.gather(*(_verdict(name) for name in names))
    checks = dict(zip(names, verdicts, strict=True))
    failing = [name for name, verdict in checks.items() if not verdict["ok"]]
    return {"ready": not failing, "checks": checks, "failing": failing}


def forget() -> None:
    """Drop every check's kept answer and question in flight, and the verdicts the log said. A
    seam for the suite."""
    for slot in _SLOTS.values():
        slot.forget()
    _LAST.clear()


async def answer(path: str) -> tuple[int, dict]:
    """The status and body for a GET of `path`, for every server of these routes — the panel's
    and the worker's say the same thing because they ask this."""
    if path == LIVE_PATH:
        return 200, alive()
    if path == READY_PATH:
        said = await ready()
        return (200 if said["ready"] else 503), said
    return 404, {"detail": f"only {' and '.join(PATHS)} are answered here"}


# ── the version ─────────────────────────────────────────────────────────────────────────────────

def _image() -> dict | None:
    """What this process's image is: the digest its deployment names, and the stamp the image
    wrote when it was built. None outside an image, where the code on disk is what runs."""
    from openfactory.namespace import build_stamp

    code, built_at = build_stamp()
    digest = (os.environ.get(IMAGE_DIGEST_VARIABLE) or "").strip()
    if not (code or digest):
        return None
    return {"digest": digest or None, "code": code or None, "built_at": built_at or None}


def _address_kind() -> str | None:
    """`view.address_kind()`, or None on an install with no engine client to reach one with."""
    try:
        from openfactory.runtime.temporal import view
    except ImportError:
        return None
    return view.address_kind()


def version() -> dict:
    """Which version this process runs, and what is installed into it."""
    from openfactory import __version__, plugins

    return {"version": __version__, "image": _image(),
            "engine": {"address_kind": _address_kind()}, "addons": plugins.installed()}


# ── for a process with no HTTP server of its own ────────────────────────────────────────────────

#: How long a connection may take to say what it asks, and how many header lines it may send.
_READ_S = 5.0
_MOST_HEADERS = 100


def port_asked() -> int | None:
    """The port `OPENFACTORY_HEALTH_PORT` names, or None — unset, or not a port, said once."""
    raw = (os.environ.get(PORT_VARIABLE) or "").strip()
    if not raw:
        return None
    try:
        port = int(raw)
    except ValueError:
        port = 0
    if not 0 < port < 65536:
        log.error("%s=%r is not a port — nothing will answer %s and %s on this process",
                  PORT_VARIABLE, raw, LIVE_PATH, READY_PATH)
        return None
    return port


def host_asked() -> str:
    """The address `OPENFACTORY_HEALTH_HOST` names, or `LOOPBACK` — what `openfactory serve`
    binds the panel to unless told otherwise. Readiness is asked without a credential, so it is
    answered beyond this machine only where the deployment says so."""
    return (os.environ.get(HOST_VARIABLE) or "").strip() or LOOPBACK


async def listen(port: int | None = None, host: str | None = None) -> asyncio.Server | None:
    """Answer `/healthz` and `/readyz` on `host`:`port` (defaults: `OPENFACTORY_HEALTH_HOST`,
    `OPENFACTORY_HEALTH_PORT`) and on the RUNNING loop. None when no port was asked for, or when
    it cannot be bound: the process still works, and the log says that nothing can ask it whether
    it does."""
    port = port if port is not None else port_asked()
    if port is None:
        return None
    host = host or host_asked()
    try:
        server = await asyncio.start_server(_serve_one, host=host, port=port)
    except OSError as exc:
        log.error("could not answer %s and %s on %s:%s (%s) — this process runs, and nothing "
                  "can ask it whether it is ready", LIVE_PATH, READY_PATH, host, port, exc)
        return None
    log.info("answering %s and %s on %s:%s", LIVE_PATH, READY_PATH, host, port)
    return server


async def _serve_one(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """One request, one answer, the connection closed. The headers are read to their end before
    answering: closing a socket with unread bytes in it resets the connection, and a client can
    lose the answer to the reset."""
    try:
        status, body = await asyncio.wait_for(_read_and_answer(reader), _READ_S + deadline())
    except (TimeoutError, ValueError, UnicodeDecodeError, ConnectionError) as exc:
        log.debug("a health request could not be read (%s)", exc)
        status, body = 400, {"detail": "a request is `GET /healthz` or `GET /readyz`"}
    payload = json.dumps(body).encode("utf-8")
    head = (f"HTTP/1.1 {status} {HTTPStatus(status).phrase}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(payload)}\r\n"
            f"Cache-Control: no-store\r\nConnection: close\r\n\r\n")
    try:
        writer.write(head.encode("latin-1") + payload)
        await writer.drain()
    except ConnectionError as exc:
        log.debug("a health request went away before its answer (%s)", exc)
    finally:
        writer.close()


async def _read_and_answer(reader: asyncio.StreamReader) -> tuple[int, dict]:
    line = await asyncio.wait_for(reader.readline(), _READ_S)
    method, target, _version = line.decode("latin-1").split()
    for _ in range(_MOST_HEADERS):
        header = await asyncio.wait_for(reader.readline(), _READ_S)
        if header in (b"\r\n", b"\n", b""):
            break
    else:
        raise ValueError("too many header lines")
    if method != "GET":
        return 405, {"detail": "only GET is answered here"}
    return await answer(target.split("?", 1)[0])


# ── the probe a healthcheck runs ────────────────────────────────────────────────────────────────

def probe(port: int, path: str = READY_PATH, *, host: str = LOOPBACK,
          timeout: float | None = None) -> int:
    """GET `path` on this machine's `port`: 0 when it answers 200, else 1 — with what it said on
    stderr, so `docker inspect` shows a supervisor which check failed. It waits `probe_timeout()`
    unless told otherwise."""
    connection = http.client.HTTPConnection(host, port,
                                            timeout=probe_timeout() if timeout is None else timeout)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read().decode("utf-8", "replace")
    except OSError as exc:
        print(f"{path} on port {port} did not answer: {exc}", file=sys.stderr)
        return 1
    finally:
        connection.close()
    if response.status == 200:
        return 0
    print(f"{path} on port {port} answered {response.status}: {body[:500]}", file=sys.stderr)
    return 1


def parser() -> argparse.ArgumentParser:
    asked = argparse.ArgumentParser(
        prog="python -m openfactory.observability.health",
        description="Ask a process of this deployment whether it is ready (or alive); exit 0 when "
                    "it is. What a container's healthcheck runs.")
    asked.add_argument("--port", type=int, required=True,
                       help="the port the process answers on: the panel's, or the worker's "
                            f"{PORT_VARIABLE}")
    asked.add_argument("--path", default=READY_PATH, choices=PATHS,
                       help=f"what to ask (default {READY_PATH})")
    return asked


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return probe(args.port, args.path)


if __name__ == "__main__":
    raise SystemExit(main())
