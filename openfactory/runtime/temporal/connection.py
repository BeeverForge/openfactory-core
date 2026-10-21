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
from typing import NamedTuple
from urllib.parse import urlsplit

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.runtime import LogForwardingConfig, LoggingConfig, Runtime, TelemetryConfig
from temporalio.service import TLSConfig

from openfactory.listeners import ENGINE
from openfactory.observability import logs
from openfactory.runtime.temporal.deadlines import read_deadline, unreachable_window
from openfactory.runtime.temporal.vocabulary import EngineUnreachable

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


class _Rest(NamedTuple):
    """A target whose last attempt was made on a runtime of its own and did not land: when it ended,
    until when nothing is attempted for it, the wait that is, and what the attempt said."""

    at: float
    until: float
    wait: float
    said: str


#: The target RESTING after an attempt that built a runtime and failed, and ONE ENTRY IN TOTAL, as
#: `_HELD` is: a target that changes is a new key, and the old one's rest is let go of with it.
_RESTING: dict[tuple[str, str, str], _Rest] = {}
#: The longest a target rests between two attempts that fail, in seconds. The first rest is
#: `OPENFACTORY_ENGINE_UNREACHABLE_FOR` (`deadlines.unreachable_window`, 3 s unset), and each
#: attempt that fails after one doubles it, up to this: so an engine that stays away costs the
#: process one runtime a minute, and one that comes back is asked again within a minute at worst.
RESTS_AT_MOST_S = 60.0


def _rest_after(key: tuple[str, str, str], failure: BaseException) -> None:
    """Remember that `key`'s attempt failed after its runtime was built. Called under `_HOLDING`."""
    first = unreachable_window()
    before = _RESTING.get(key)
    wait = first if before is None else min(2 * before.wait, max(RESTS_AT_MOST_S, first))
    now = time.monotonic()
    _RESTING.clear()
    _RESTING[key] = _Rest(at=now, until=now + wait, wait=wait,
                          said=f"{type(failure).__name__}: {failure}"[:200])


def _resting(key: tuple[str, str, str]) -> EngineUnreachable | None:
    """The refusal for a caller that arrives while `key` rests, or None. Called under `_HOLDING`."""
    rest = _RESTING.get(key)
    now = time.monotonic()
    if rest is None or rest.until <= now:
        return None
    return EngineUnreachable(
        f"the durable engine at {key[0]} did not take a connection {now - rest.at:.1f}s ago "
        f"({rest.said}), so it is not asked again for {rest.until - now:.1f}s: the wait starts "
        f"at OPENFACTORY_ENGINE_UNREACHABLE_FOR and doubles after each attempt that fails, up "
        f"to {max(RESTS_AT_MOST_S, unreachable_window()):g}s")


class _Abandoned(Exception):  # noqa: N818 — not an error of the engine's: nobody waited for it
    """The connect a caller queued behind was cancelled. That says nothing about the engine, so
    the caller tries for itself."""


async def connect(*, within: float | None = None) -> Client:
    """The durable engine's client for this process: the one it holds, made the first time it is
    asked for and handed to every caller after that, on any loop and any thread. An attempt to
    make it is bounded by `within`, else by the engine's read deadline.

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

    A CLIENT IS NOT BOUND TO THE LOOP THAT MADE IT — FROM temporalio 1.29.0, WHICH THE PACKAGE
    REQUIRES FOR THIS. Up to 1.28.0 every call took an `asyncio.Lock` bound to the first loop that
    contended for it; 1.29.0 skips it once the client is connected (sdk-python #1606, which still
    calls other loops "more likely to work", not guaranteed). Measured on 1.32.0 against a dev
    server: a client made under one `asyncio.run` answered health checks, system-info reads and
    workflow listings from two later `asyncio.run`s after the first loop had closed, and from three
    other threads' loops at the same time as three calls on the main one; and 1500 concurrent calls
    from four threads' loops and the main one all answered (seventh review of #818). The SDK runs
    each call on its own core and hands the answer to whichever loop is running the caller.

    A FAILED CONNECT IS SHARED, NOT CACHED, as `view.connect()` has it: the callers queued behind a
    failing attempt take its failure, and a caller arriving afterwards tries again — with JSON
    lines, once its target's rest has ended (below) — which is how a recovered engine is picked up
    without a restart. A cancelled attempt is nobody's failure; the
    callers behind it try for themselves. A runtime that cannot be built is a failed attempt like
    any other (seventh review: built before the attempt was settled, it wedged every later
    connect for the life of the process).

    EVERY ATTEMPT IS BOUNDED, whoever starts it: by `within`, else by `OPENFACTORY_ENGINE_DEADLINE`
    (`deadlines.read_deadline`), the bound every read already waits by. A caller with a bound of
    its own queues behind the attempt in flight, so an unbounded attempt would hold it: measured,
    one with no bound against a listener that never answered ran 30.1 s, and three bounded reads
    during it each gave up without trying.

    WITH JSON LINES, AN ENGINE THAT IS NOT THERE COSTS NOTHING, AND ONE THAT FAILS COSTS LITTLE
    (review requesting changes on 3cd816ac, measured on temporalio 1.34.0: a process that started
    while its engine was down built a runtime for every connect, each leaking about 65 KB of
    native memory that no collection frees, and ran a full collection on the caller's loop for
    each — 1,200 refused connects grew it from 77 to 151 MB through this door and from 66 to
    146 MB through `view.connect()`, and a collection took 20 ms on a small heap and 300 ms on
    3M objects; a panel pays that on every healthcheck and every read until the engine answers).
    So, only where an attempt would build a runtime of its own (`core_runtime`):

      · THE SOCKET IS ASKED FIRST, as `connect_at_birth` asks it (`_listening`): a port nobody
        listens on — the engine stopped, its container gone, its name not resolving — is said
        as `EngineNotListening`, and nothing is built and nothing collected for it;
      · AN ATTEMPT THAT BUILT ITS RUNTIME AND FAILED — the socket taken and then a refusal, a key
        the engine does not accept, no answer within the bound — LEAVES ITS TARGET RESTING
        (`_RESTING`): until the rest ends, a caller is refused at once with `EngineUnreachable`,
        saying what the attempt said, and builds nothing. The first rest is
        `OPENFACTORY_ENGINE_UNREACHABLE_FOR`, and each attempt that fails after one doubles it,
        up to `RESTS_AT_MOST_S`; a client that lands ends it. A cancelled attempt is still
        nobody's failure, and leaves no rest."""
    while True:
        key = fingerprint()  # raises for an engine nobody declared, before anything is built
        with _HOLDING:
            held = _HELD.get(key)
            if held is not None:
                return held
            refusal = _resting(key)
            if refusal is not None:
                raise refusal
            flight = _IN_FLIGHT.get(key)
            mine = flight is None
            if flight is None:
                flight = _IN_FLIGHT[key] = concurrent.futures.Future()
                # RUNNING, so a waiter that is cancelled cannot cancel the attempt under the others.
                flight.set_running_or_notify_cancel()
        if mine:
            return await _connect_for(key, flight, read_deadline() if within is None else within)
        try:
            return await asyncio.wrap_future(flight)
        except _Abandoned:
            continue


async def _connect_for(key: tuple[str, str, str], flight: concurrent.futures.Future,
                      bound: float) -> Client:
    """The one attempt for `key`, within `bound`, on a runtime made for it — its outcome, whatever
    it is, handed to `flight`."""
    where, space, _digest = key
    runtime = None
    try:
        # ONE BOUND OVER THE PROBE AND THE CONNECT, so the attempt ends within `bound` whatever
        # part of it waits.
        async with asyncio.timeout(bound):
            # ASKED ONLY WHERE A RUNTIME WOULD BE BUILT: without JSON lines the client is made on
            # the library's default runtime, and a refused connect there costs nothing (measured
            # flat, review on 3cd816ac), so its refusal is left as the library says it.
            if logs.structured() and not await _listening(*_host_and_port(where)):
                raise EngineNotListening(
                    f"nothing accepted a connection at {where}, where the durable engine is "
                    f"declared, so no client was made for it")
            # INSIDE THE `try`, because building it can fail like the connect can (the bridge's
            # "Failed initializing runtime", for one, when a thread cannot start under a pid
            # limit): outside, the attempt stayed in flight unsettled and every later connect
            # waited on it.
            runtime = core_runtime()
            client = await Client.connect(
                where, namespace=space, data_converter=pydantic_data_converter,
                **({"runtime": runtime} if runtime is not None else {}), **_auth())
    except BaseException as exc:
        failure: BaseException = exc
        if isinstance(exc, TimeoutError):
            failure = TimeoutError(
                f"the durable engine at {where} did not take a connection within {bound:g}s "
                f"(OPENFACTORY_ENGINE_DEADLINE)")
        with _HOLDING:
            _IN_FLIGHT.pop(key, None)
            if runtime is not None and isinstance(exc, Exception):
                _rest_after(key, failure)
        flight.set_exception(failure if isinstance(failure, Exception) else _Abandoned())
        # A FAILED CONNECT KEEPS ITS RUNTIME — a thread per CPU — in a reference cycle only a full
        # collection frees (review on d2ef6149, measured: a panel whose engine was down at its
        # first connect gained twelve threads per healthcheck on 12 CPUs, 146 after twelve, and a
        # steady heap almost never runs that collection). So it is run here, on the caller's loop:
        # 20 ms on a small heap, 300 ms on 3M objects (review on 3cd816ac). AT MOST ONCE PER REST:
        # a port nobody listens on builds no runtime, and a target that rests builds none until
        # its rest ends. NOT ON A THREAD: a collection holds the interpreter's lock for its whole
        # length, so the loop waits for it there all the same (measured on 3M objects: 181 ms on
        # the loop, its longest gap 182 ms; 170 ms on a thread, 170 ms). While this failure is
        # handled its traceback still holds this attempt's runtime, so what this frees is the
        # attempt before it, and the last one is freed when a client lands (below). NOT REUSED
        # INSTEAD: a runtime a failed attempt touched forwards nothing afterwards (the bridge's
        # `Drop`, `core_runtime`).
        if runtime is not None:
            del runtime
            gc.collect()
        if failure is not exc:
            raise failure from None
        raise
    with _HOLDING:
        _IN_FLIGHT.pop(key, None)
        let_go = [other for target, other in _HELD.items() if target != key]
        _HELD.clear()
        _HELD[key] = client
        failed_before = bool(_RESTING)
        _RESTING.clear()
    flight.set_result(client)
    if let_go or failed_before:
        # A TARGET THAT CHANGED lets its old client go — collected at once, so its connection
        # and its runtime go with it, rather than at whatever collection comes next. A caller
        # still using it keeps its own reference, and the collection then frees nothing early.
        # AND A CLIENT THAT LANDS AFTER FAILED ATTEMPTS frees the last of their runtimes, which
        # the collection run while that failure was handled could not (re-review on 3cd816ac,
        # measured on the real panel: 26 threads while the engine was silent, 38 for good once it
        # answered, 14 after one collection).
        del let_go
        gc.collect()
    return client


def forget() -> None:
    """Let go of the client this process holds. A seam for the suite, which must not hand one
    test's engine to the next."""
    with _HOLDING:
        _HELD.clear()
        _IN_FLIGHT.clear()
        _RESTING.clear()


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


def _host_and_port(where: str) -> tuple[str, int]:
    """The host and port an engine address names, its port the engine's default when it names
    none."""
    parts = urlsplit(f"//{where}")
    return parts.hostname or where, parts.port or ENGINE.default_port


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
    host, port = _host_and_port(where)
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
    # ITS OWN WAIT IS THE CONNECT'S BOUND, not the read deadline: a process being born may give
    # its engine longer to answer than a read gives it (`OPENFACTORY_ENGINE_STARTS_IN`). Until
    # #681 the connect after the socket accepted had no bound at all; now it has what is left of
    # the wait, and at least the read deadline.
    within = max(deadline - time.monotonic(), read_deadline())
    try:
        return await connect(within=within)
    except TimeoutError:
        # SAID AS THE OTHER TIMING FAILURE IS, naming the setting that bounded it — the read
        # deadline's sentence would send its reader to the wrong variable (delta review of #818).
        raise EngineNotListening(
            f"the durable engine at {where} took the connection but did not answer it in "
            f"{within:.0f}s — this process dials it as it starts. Is the engine still starting, "
            f"or is something else listening at `{_ADDRESS_VARS[0]}`? An engine that is only "
            f"slow to start is given longer with `{_STARTS_IN_VAR}`.") from None
