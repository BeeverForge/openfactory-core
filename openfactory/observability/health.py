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
    failing check is named; a supervisor reads 503. BOUNDED: every check runs at once, each within
    `DEADLINE_S`, so the answer never waits on a dependency longer than that. THE ENGINE'S ANSWER IS
    KEPT FOR `ENGINE_TTL_S`: readiness asked every few seconds by every supervisor must not become
    load on an engine that is already struggling — the floor's own rule for its schedule read.
  · `version()` — the package, the image, the kind of address the engine is reached at, and every
    add-on installed with its distribution, version, axis and kind. Behind the credential like the
    rest of `/api/`, because which add-ons a deployment carries is a fact about the deployment.

WHAT A CALLER WITH NO CREDENTIAL IS TOLD. Readiness names the check that failed and says one fixed
sentence about it; the cause — an address, a variable's name, a file's path — goes to the log, once
when the check starts failing and once when it answers again. It is the gate's rule for a caller
nobody has identified (`api/app.py::IDENTITY_UNAVAILABLE`). The one cause said in the body is an
install without the engine's client library: what to install is a fact about the product, not about
the deployment, and every other surface says it the same way (`runtime/host.py::CLIENT_MISSING`).

WHO SERVES THEM. The panel serves `/healthz`, `/readyz` and `/api/v1/version`. The worker serves no
HTTP, so when `OPENFACTORY_HEALTH_PORT` names a port it answers `/healthz` and `/readyz` there
(`listen`) — ON ITS OWN EVENT LOOP, so a worker whose loop is stuck does not answer, which is what
a liveness probe is for. The compose file's healthchecks ask both through `probe`:

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

#: The image's digest, as the deployment that pulled it by digest names it. NOT A BUILD ARGUMENT,
#: AND IT CANNOT BE ONE: a digest is the hash of the image, so writing it into the image changes
#: it. The image knows what it was built from (`namespace.build_stamp`); only whoever deployed it
#: knows which digest that became.
IMAGE_DIGEST_VARIABLE = "OPENFACTORY_IMAGE_DIGEST"

#: How long `ready()` waits for any one check. The engine's own reads are bounded at three seconds
#: (`view.read_deadline`); five leaves a connect and a health check room to answer, and a compose
#: healthcheck's `timeout` above it.
DEADLINE_S = 5.0

#: How long the engine's answer is kept. A few seconds: a supervisor learns of an engine that went
#: away within one of its own polls, and a dozen supervisors polling every second cost the engine
#: one health check per window, not a dozen per second.
ENGINE_TTL_S = 5.0

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


# ── liveness ────────────────────────────────────────────────────────────────────────────────────

def alive() -> dict:
    """The process serves. Nothing is read: see the module's first rule."""
    return {"alive": True}


# ── readiness ───────────────────────────────────────────────────────────────────────────────────

#: `(when, said, cause)` of the engine's last answer; `said` is `""` when it answered.
_engine_memo: tuple[float, str, str] | None = None
_engine_read = _OneAtATime()


def _clock() -> float:
    """The clock the engine's window runs on. A function so a guard can move it, not sleep."""
    return time.monotonic()


async def _engine() -> None:
    """The engine answers its health check — asked at most once per `ENGINE_TTL_S`, and by one
    caller at a time: readers that arrive while a check is in flight share it (`_OneAtATime`, the
    floor's single flight), and a check that outlives `DEADLINE_S` still lands in the window."""
    memo = _engine_memo
    if memo is None or _clock() - memo[0] >= ENGINE_TTL_S:
        memo = await _engine_read.shared(_ask_the_engine)
    if memo[1]:
        raise NotReady(memo[2], said=memo[1])


async def _ask_the_engine(flight) -> tuple[float, str, str]:
    global _engine_memo

    said, cause = await _engine_answers()
    answer = (_clock(), said, cause)
    if _engine_read.holds(flight):
        _engine_memo = answer
    return answer


async def _engine_answers() -> tuple[str, str]:
    """`(said, cause)`, both `""` when the engine answered. THE FLOOR'S OWN PROBE first
    (`reading._engine`: the declaration, the client library, the pooled and bounded connect), and
    then the engine's health check — because a pooled client is handed back long after the engine
    behind it went away, and "connected" would then be a memory, not an answer."""
    from openfactory.floor import reading
    from openfactory.listeners import ENGINE
    from openfactory.runtime.host import CLIENT_MISSING

    client, connected, _address, error = await reading._engine(None)
    if not connected:
        if error == CLIENT_MISSING:
            return CLIENT_MISSING, error
        return (SAID["engine"] if ENGINE.declared() else ENGINE_UNDECLARED), error
    try:
        from openfactory.runtime.temporal import view

        if await view.check_health(client):
            return "", ""
        cause = "the engine answers, but says its workflow service is not serving"
    except Exception as exc:  # noqa: BLE001 — every failure is the same verdict, its cause logged
        cause = f"{type(exc).__name__}: {str(exc)[:200]}"
    return SAID["engine"], cause


def _registry_reads() -> None:
    """The registry reads: every project in it builds, as every reader of it needs. What it
    raises when it does not is the cause `_verdict` logs."""
    from openfactory.registry import ProjectRegistry

    ProjectRegistry().list()


async def _registry() -> None:
    """`_registry_reads`, off the event loop: a registry is a file, and a file can hang."""
    await asyncio.to_thread(_registry_reads)


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
    await asyncio.to_thread(_identity_admits)


#: Every check `ready()` runs, by the name a 503 says. A check is an async callable that returns
#: when its dependency is ready and raises `NotReady` when it is not.
CHECKS: dict[str, Callable[[], Awaitable[None]]] = {
    "engine": _engine,
    "registry": _registry,
    "identity": _identity,
}

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
    """One check, bounded, as the body says it: `{"ok": true}` or `{"ok": false, "detail": …}`."""
    try:
        await asyncio.wait_for(CHECKS[name](), DEADLINE_S)
    except NotReady as exc:
        said, cause = exc.said or SAID[name], exc.cause
    except TimeoutError:
        said = f"{SAID[name]} within {DEADLINE_S:g}s"
        cause = f"no answer within {DEADLINE_S:g}s"
    except Exception as exc:  # noqa: BLE001 — a check that broke is a check that did not pass
        said, cause = SAID[name], f"{type(exc).__name__}: {str(exc)[:200]}"
    else:
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
    """Drop the engine's kept answer and the verdicts the log said. A seam for the suite."""
    global _engine_memo

    _engine_memo = None
    _engine_read.forget()
    _LAST.clear()


async def answer(path: str) -> tuple[int, dict]:
    """The status and body for a GET of `path`, for every server of these routes — the panel's
    and the worker's say the same thing because they ask this."""
    if path == LIVE_PATH:
        return 200, alive()
    if path == READY_PATH:
        said = await ready()
        return (200 if said["ready"] else 503), said
    return 404, {"detail": f"nothing is served at {path}; ask {' or '.join(PATHS)}"}


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


async def listen(port: int | None = None, host: str | None = None) -> asyncio.Server | None:
    """Answer `/healthz` and `/readyz` on `port` (default: `OPENFACTORY_HEALTH_PORT`) and on the
    RUNNING loop — by default on every interface (`host=None`), because an orchestrator's probe
    comes from outside the container, and only these two routes are served there. None when no
    port was asked for, or when it cannot be bound: the process still works, and the log says
    that nothing can ask it whether it does."""
    port = port if port is not None else port_asked()
    if port is None:
        return None
    try:
        server = await asyncio.start_server(_serve_one, host=host, port=port)
    except OSError as exc:
        log.error("could not answer %s and %s on port %s (%s) — this process runs, and nothing "
                  "can ask it whether it is ready", LIVE_PATH, READY_PATH, port, exc)
        return None
    log.info("answering %s and %s on port %s", LIVE_PATH, READY_PATH, port)
    return server


async def _serve_one(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """One request, one answer, the connection closed. The headers are read to their end before
    answering: closing a socket with unread bytes in it resets the connection, and a client can
    lose the answer to the reset."""
    try:
        status, body = await asyncio.wait_for(_read_and_answer(reader), _READ_S + DEADLINE_S)
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

def probe(port: int, path: str = READY_PATH, *, host: str = "127.0.0.1",
          timeout: float = DEADLINE_S + 2) -> int:
    """GET `path` on this machine's `port`: 0 when it answers 200, else 1 — with what it said on
    stderr, so `docker inspect` shows a supervisor which check failed."""
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
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
