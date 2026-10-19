"""One place to connect to Temporal — dev-server or Temporal Cloud, env-driven.

The SAME code runs everywhere (ADR-0001 D-16); only the connection target changes:

    dev:    TEMPORAL_ADDRESS=localhost:7233                        (default, no auth)
    cloud:  TEMPORAL_ADDRESS=<region>.<cloud>.api.temporal.io:7233
            TEMPORAL_NAMESPACE=<namespace>.<account>
            TEMPORAL_API_KEY=<key>                                 (API-key auth + TLS)
      or    TEMPORAL_TLS_CERT=/path/client.pem
            TEMPORAL_TLS_KEY=/path/client.key                      (classic mTLS)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import gc
import hashlib
import logging
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.runtime import LogForwardingConfig, LoggingConfig, Runtime, TelemetryConfig
from temporalio.service import TLSConfig

from openfactory.listeners import ENGINE
from openfactory.observability import logs

#: The one local target, spelled once. Named so a deployment can DECLARE it — which is the whole
#: difference between "I meant the dev server" and "nobody told me anything" (#163). ASKED OF THE
#: ONE DEFINITION (#183), so it is the port `openfactory up` starts the engine on by construction.
LOCAL_DEV_ADDRESS = ENGINE.local()

#: Every name this deployment could have used to say where its engine is. Read at call time, in
#: order; `TEMPORAL_ENDPOINT` is what Temporal Cloud's console calls the gRPC endpoint, and the
#: terraform in this repository sets that one while the compose stack sets the other.
_ADDRESS_VARS = ENGINE.reach_vars


class EngineNotDeclared(RuntimeError):
    """Nobody said where the durable engine is.

    ITS OWN TYPE, because every caller of `address()` already has an except-branch that degrades
    honestly, and this must land there rather than in a generic handler that reports "the engine
    did not answer" — which is the sentence a silent localhost produced for a year.
    """


def address() -> str:
    """Where this deployment's durable engine is. RAISES when nobody said (#163).

    IT DEFAULTED TO `localhost:7233`, and the house memory records what that cost: a worker with a
    misconfigured environment connects to something real-looking on the machine it happens to be
    running on and does nothing visible — no error, no workflows, a green process. Measured worse
    than that once: with the OSS compose stack up, a test run started a REAL workflow on a
    developer's engine (#107), and the suite stayed green throughout.

    A DEV SERVER IS STILL ONE LINE: `TEMPORAL_ADDRESS=localhost:7233`, which is what the compose
    stack, the terraform and `docs/configuration.md` all already do. What changed is that saying
    it is now required — an unset environment is a fact about the deployment, not a preference for
    the developer's laptop.
    """
    if found := ENGINE.declared():
        return found
    raise EngineNotDeclared(
        "this deployment does not say where its durable engine is: set "
        + " or ".join(f"`{v}`" for v in _ADDRESS_VARS)
        + f" (a local dev server is `{_ADDRESS_VARS[0]}={LOCAL_DEV_ADDRESS}`). Nothing is "
        "assumed, because a silent fall back to a local engine is a worker that connects "
        "somewhere real-looking and does nothing visible.")


def namespace() -> str:
    return os.environ.get("TEMPORAL_NAMESPACE", "default")


def _auth() -> dict:
    api_key = os.environ.get("TEMPORAL_API_KEY")
    if api_key:  # Temporal Cloud API-key auth (TLS required)
        return {"api_key": api_key, "tls": True}
    cert, key = os.environ.get("TEMPORAL_TLS_CERT"), os.environ.get("TEMPORAL_TLS_KEY")
    if cert and key:  # classic mTLS client cert
        return {
            "tls": TLSConfig(
                client_cert=Path(cert).read_bytes(),
                client_private_key=Path(key).read_bytes(),
            )
        }
    return {}  # plain dev-server


#: How much of the auth digest travels in a pool key. Twelve hex characters is 48 bits — far more
#: than the handful of targets one process ever holds, and short enough to sit in a log line
#: without wrapping.
_DIGEST_CHARS = 12


def _contents(path: str) -> str:
    """The bytes at `path`, digested — or a marker naming it, when they cannot be read.

    NEVER RAISES. A key computation that refuses has no sentence to say about the file; `_auth()`
    does, one line later, inside the connect attempt where the caller is already holding a
    degraded read. The marker still CHANGES when a path appears or disappears, which is the only
    question this value is asked.
    """
    if not path:
        return ""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return "unreadable\x00" + path


def fingerprint() -> tuple[str, str, str]:
    """`(address, namespace, auth-digest)` — what this process would connect to, and as whom.

    ASKED OF THIS MODULE FOR THE SAME REASON `view.temporal_config()` is (#163): two answers to
    "where is the engine" is the defect this file was fixed for, and a caller that wants to know
    whether two connections would land in the same place must not re-read the environment with its
    own precedence to find out. It raises `EngineNotDeclared` exactly as `address()` does — which
    is the refusal `connect()` would produce one line later anyway.

    Its callers are `connect()`, which holds one client per target for the process (#681), and
    `view.connect()`, which reuses one client per target (GitHub issue #134): the
    panel opened a fresh gRPC client on every `/api/floor` request, and the reporter measured 20 →
    32 open connections over six requests on 2026-09-15. "Same target" has to include the AUTH
    material, because a redeployment that swaps an API key while keeping the address must not be
    served by a client holding the old credential.

    THE SECRET NEVER ENTERS THE KEY — a truncated SHA-256 goes in instead. A pool key reaches a log
    line, a `repr` and a test failure message, and this repository already carries guards against
    credentials travelling that way (`tests/conftest.py`'s strip exists because `.env` once reached
    the whole suite). The digest answers the only question the key asks — *did this change?* —
    and answers nothing else.

    IT DIGESTS THE TLS FILES' CONTENTS, NOT THEIR PATHS, and that costs two file reads per
    `connect()` call on an mTLS deployment. IT DIGESTED THE PATHS, and the reviewer of #145 drove
    the difference on 2026-09-15: rewrite the file at `TEMPORAL_TLS_CERT` in place, with
    `Client.connect` faked to record the bytes it is handed, and

        da669de: first request used b'CERT-BEFORE' | second request used b'CERT-ROTATED-IN-PLACE'
        the pool, on paths:  first b'CERT-BEFORE' | second b'CERT-BEFORE'

    — because before the pool the panel connected on every request, so `_auth()` re-read both files
    every time. Reuse silently dropped that re-read. TWO READS PER CALL IS STRICTLY CHEAPER THAN
    WHAT IT REPLACES: `da669de` read both files on every read-side request too, and then opened a
    gRPC client as well. This reads them and hands back the client it already holds. A deployment
    on API-key auth or a plain dev server has no files here and pays nothing.

    AN UNREADABLE FILE DOES NOT RAISE OUT OF HERE. It digests to a marker, so the honest error
    still comes from `_auth()` inside the connect attempt — where `view.connect()`'s
    failure-sharing path reports it once to every caller queued behind it, rather than from a key
    computation that has no sentence to say about it.
    """
    cert = os.environ.get("TEMPORAL_TLS_CERT") or ""
    key = os.environ.get("TEMPORAL_TLS_KEY") or ""
    material = "\x00".join((
        "api_key", os.environ.get("TEMPORAL_API_KEY") or "",
        "tls_cert", cert, _contents(cert),
        "tls_key", key, _contents(key),
    ))
    digest = hashlib.sha256(material.encode()).hexdigest()[:_DIGEST_CHARS]
    return address(), namespace(), digest


#: The logger the engine client's core writes through when the deployment asked for JSON lines.
CORE_LOGGER = "temporalio.core"


def core_telemetry() -> TelemetryConfig:
    """The client core's telemetry, its lines handed to `CORE_LOGGER` at the levels it writes by
    default (its own warnings, the libraries' errors) — and so to the deployment's one format."""
    return TelemetryConfig(logging=LoggingConfig(
        filter=LoggingConfig.default.filter,
        forwarding=LogForwardingConfig(logger=logging.getLogger(CORE_LOGGER))))


def core_runtime() -> Runtime | None:
    """The runtime a new client is made on. With JSON log lines, ONE OF ITS OWN, whose core hands
    its lines to `CORE_LOGGER` (`core_telemetry`), and so to the deployment's one format; without,
    None — the library's shared default, whose core writes its own lines, as it always did.

    WHY THE CORE IS TOLD AT ALL (second review of #818, measured): the client's core is not Python,
    and left to itself it writes its own lines — `WARN temporalio_client::retry: gRPC call
    poll_activity_task_queue retried 6 times …`, compact, coloured, on stdout — exactly when the
    engine goes away, which is when somebody reads the log.

    WHY ONE PER CLIENT, AND NOT ONE SHARED DEFAULT (third review, measured on the real worker): the
    library's bridge stops a runtime's forwarding for EVERY client of it the moment ANY one of them
    is dropped. `temporalio/bridge/src/runtime.rs` (1.34.0, and `main` the same day): `Runtime` is
    `Clone`, each client holds a clone, and `impl Drop for Runtime` aborts the one
    `log_forwarder_handle` they all share. The worker drops a dozen one-shot clients at boot
    (`schedule.ensure_all`), so on one shared runtime its core went silent — no plain line and no
    JSON one: 0 lines in 60 s of an engine outage, where the readable format printed 86. A
    runtime of its own lives and dies with its client: about 5 ms and one thread per CPU to
    build, about 3 ms to drop (measured on 8 CPUs). And the process holds ONE client (`connect`),
    so it pays that once: the real worker kept 12 threads through an engine outage with JSON lines
    and 12 in the readable format, on 8 CPUs."""
    if not logs.structured():
        return None
    return Runtime(telemetry=core_telemetry())


#: The ONE client this process holds for its engine target, by `fingerprint()` — and ONE ENTRY IN
#: TOTAL: a target that changes (a moved address, a rotated key) is a new key, and the old client
#: is let go of rather than kept beside it (`view._CLIENTS` keeps the same rule, for the same
#: reason: #134's leak on a deployment's clock).
_HELD: dict[tuple[str, str, str], Client] = {}
#: The connect in flight for a target, shared by every caller that arrives while it runs — on this
#: loop, another loop or another thread. At most one per key, and gone once it lands or fails.
_IN_FLIGHT: dict[tuple[str, str, str], concurrent.futures.Future] = {}
_HOLDING = threading.Lock()


class _Abandoned(Exception):  # noqa: N818 — not an error of the engine's: nobody waited for it
    """The connect a caller queued behind was cancelled. That says nothing about the engine, so
    the caller tries for itself."""


async def connect() -> Client:
    """The durable engine's client for this process: the one it holds, made the first time it is
    asked for and handed to every caller after that, on any loop and any thread.

    ONE CLIENT PER PROCESS AND TARGET, NEVER DROPPED (fifth and sixth reviews of #818, measured).
    With JSON lines every client is made on a runtime of its own (`core_runtime`), about one thread
    per CPU, and a client that is dropped keeps that runtime — and, in either format, its gRPC
    connection — in a reference cycle only a full collection frees. Callers dropped clients in
    steady operation: the read side's pool emptied its one entry each time the worker's readiness
    (its own loop) and a product turn's read (the standing loop) took turns — 2 → 12 connections in
    both formats and 21 → 111 threads with JSON over six rounds — and a door-shaped read under an
    `asyncio.run` of its own took 10 → 55 threads in six. Holding the one client removes the drop
    instead of paying for it: every one of those reads now gets the client the process already
    has, so the worker's readiness asks the very client the worker serves on, and #1988's forwarder
    is never aborted, because no runtime with a live client loses a clone.

    A CLIENT IS NOT BOUND TO THE LOOP THAT MADE IT. Measured on temporalio 1.32.0 against a dev
    server: a client made under one `asyncio.run` answered health checks, system-info reads and
    workflow listings from two later `asyncio.run`s after the first loop had closed, and from three
    other threads' loops at the same time as three calls on the main one. The SDK runs each call on
    its own core and hands the answer to whichever loop is running the caller.

    A FAILED CONNECT IS SHARED, NOT CACHED, as `view.connect()` has it: the callers queued behind a
    failing attempt take its failure, and a caller arriving afterwards tries again, which is how a
    recovered engine is picked up without a restart. A cancelled attempt is nobody's failure; the
    callers behind it try for themselves."""
    while True:
        key = fingerprint()  # raises for an engine nobody declared, before anything is built
        with _HOLDING:
            held = _HELD.get(key)
            if held is not None:
                return held
            flight = _IN_FLIGHT.get(key)
            mine = flight is None
            if flight is None:
                flight = _IN_FLIGHT[key] = concurrent.futures.Future()
                # RUNNING, so a waiter that is cancelled cannot cancel the attempt under the others.
                flight.set_running_or_notify_cancel()
        if mine:
            return await _connect_for(key, flight)
        try:
            return await asyncio.wrap_future(flight)
        except _Abandoned:
            continue


async def _connect_for(key: tuple[str, str, str], flight: concurrent.futures.Future) -> Client:
    """The one attempt for `key`, on a runtime made for it, its outcome handed to `flight`."""
    where, space, _digest = key
    runtime = core_runtime()
    try:
        client = await Client.connect(
            where, namespace=space, data_converter=pydantic_data_converter,
            **({"runtime": runtime} if runtime is not None else {}), **_auth()
        )
    except BaseException as exc:
        with _HOLDING:
            _IN_FLIGHT.pop(key, None)
        flight.set_exception(exc if isinstance(exc, Exception) else _Abandoned())
        # A FAILED CONNECT KEEPS ITS RUNTIME — a thread per CPU — in a reference cycle only a full
        # collection frees (review on d2ef6149, measured: a panel whose engine was down at its
        # first connect gained twelve threads per healthcheck on 12 CPUs, 146 after twelve, and a
        # steady heap almost never runs that collection). So it is run here, once per failed
        # connect and only with JSON lines: 31–45 ms median, 80–110 ms at worst, on the caller's
        # loop. Only a process that has not connected yet pays it: once a client is held, an
        # engine that goes away is reconnected underneath it and nothing here runs again. NOT
        # REUSED INSTEAD: a runtime a failed attempt touched forwards nothing afterwards (the
        # bridge's `Drop`, `core_runtime`).
        if runtime is not None:
            del runtime
            gc.collect()
        raise
    with _HOLDING:
        _IN_FLIGHT.pop(key, None)
        let_go = [other for target, other in _HELD.items() if target != key]
        _HELD.clear()
        _HELD[key] = client
    flight.set_result(client)
    if let_go:
        # A TARGET THAT CHANGED lets its old client go — collected at once, so its connection
        # and its runtime go with it, rather than at whatever collection comes next. A caller
        # still using it keeps its own reference, and the collection then frees nothing early.
        del let_go
        gc.collect()
    return client


def forget() -> None:
    """Let go of the client this process holds. A seam for the suite, which must not hand one
    test's engine to the next."""
    with _HOLDING:
        _HELD.clear()
        _IN_FLIGHT.clear()


class EngineNotListening(RuntimeError):
    """Nothing accepted a connection where the engine was declared, for as long as was allowed.

    ITS OWN TYPE, as `EngineNotDeclared` is: it is the one failure at a worker's birth that is
    about TIMING rather than configuration, and the entry point turns it into a sentence and an
    exit code instead of the traceback #135 was filed with."""


#: How long a process being born waits for its engine to start listening, in seconds.
_STARTS_IN_VAR = "OPENFACTORY_ENGINE_STARTS_IN"
_STARTS_IN_S = 30.0


def engine_starts_in() -> float:
    """The bound on the wait below. A DEPLOYMENT'S NUMBER, read per call: how long an engine takes
    to bind is a property of somebody's disk — the dev server recovers its local database before
    it listens, and #135 was likelier exactly after a hard kill, when that recovery is longest."""
    try:
        wanted = float(os.environ.get(_STARTS_IN_VAR, "") or _STARTS_IN_S)
    except ValueError:
        return _STARTS_IN_S
    return wanted if wanted > 0 else _STARTS_IN_S


async def _listening(host: str, port: int) -> bool:
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.0)
    except (OSError, TimeoutError):
        return False
    writer.close()
    with contextlib.suppress(OSError):
        await writer.wait_closed()
    return True


async def connect_at_birth(*, within: float | None = None, every: float = 0.25) -> Client:
    """`connect()`, for a process that may have been started BESIDE its engine (#135).

    THE RACE. `openfactory up` starts the engine, the worker and the panel together, and on some
    restarts the worker dialled before the engine's dev server had bound its port: `connect()`
    raised, the worker exited, and because one dying process ends the set the panel went down with
    it. Same command, nothing changed between runs.

    IT IS THE WORKER'S WAIT, NOT `up`'s. The worker is the process with the dependency, and the
    client already rides out an engine that goes away while the worker RUNS; the one outage it did
    not survive was the one at its own first connect. Every starter has that race — `up`, a worker
    started by hand beside `temporal server start-dev`, compose whenever the engine container
    restarts (`depends_on` orders the first start only) — so waiting in `up` would have fixed one
    starter of three, and left `host.run` holding a second job besides ending the set together.

    THE SOCKET IS ASKED, NOT THE ERROR MESSAGE. The client raises an untyped `RuntimeError` for a
    refused connection, so telling "nothing is listening yet" from "something said no" by its text
    would be parsing a string another project owns. So: wait, bounded, until the declared address
    ACCEPTS a connection — then connect exactly once, and let whatever that raises (a bad key, a
    namespace that does not exist) raise as it always did. A refusal that is an answer is never
    retried, by construction: `connect()` is never retried at all.

    An engine nobody declared still raises `EngineNotDeclared` at once (#163) — there is no
    address to wait on, and none is assumed.
    """
    where = address()
    bound = engine_starts_in() if within is None else within
    parts = urlsplit(f"//{where}")
    host, port = parts.hostname or where, parts.port or ENGINE.default_port
    deadline = time.monotonic() + bound
    while not await _listening(host, port):
        if time.monotonic() >= deadline:
            raise EngineNotListening(
                f"the durable engine at {where} accepted no connection in {bound:.0f}s — this "
                f"process dials it as it starts, and nothing was listening. Is the engine "
                f"running (`openfactory up` starts it beside the worker; `temporal server "
                f"start-dev` starts it alone)? Is `{_ADDRESS_VARS[0]}` where it listens "
                f"(`openfactory doctor` checks)? An engine that is only slow to start is given "
                f"longer with `{_STARTS_IN_VAR}`.")
        await asyncio.sleep(every)
    return await connect()
