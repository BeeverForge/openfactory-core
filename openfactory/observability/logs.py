"""One log format for every long-running process of the deployment (#675).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640). Nothing in the package configured logging,
so the worker and the panel logged through Python's last-resort handler: a warning reached the log
as its bare message, with no time, no level and no source, and every INFO line was dropped. Two of
that week's intermittent failures could be placed in time only by counting poll requests between
moments the engine's own history dated, and a context push rejected twice showed one line, because
the first rejection is an INFO. The INFO lines written as the evidence trail of a degraded path —
"the read model could not reach the engine", "coordinator … did not answer" — reached nobody.

THE FORMAT: a UTC timestamp with milliseconds, the level, the logger's name, the message. One line
per record, so `grep` and a person read it the same way; UTC, so the panel's line and the worker's
line about one moment carry one time.

THE LEVELS: the platform's own loggers (`openfactory…`) keep INFO, or what `OPENFACTORY_LOG_LEVEL`
says; uvicorn's keep INFO, so a request and the warning it caused sit side by side; everything else
— the libraries — stays at WARNING, as before.

A PROCESS THAT ALREADY HAS A CONFIGURATION KEEPS IT. When the root logger has a handler, somebody
set logging up on purpose (an embedding host, a test runner), and this does nothing at all.

JSON LINES, WHEN A DEPLOYMENT SAYS SO (#681). A log store reads fields, not sentences: with
`OPENFACTORY_LOG_FORMAT=json` every record is ONE JSON object on ONE line — `ts`, `level`,
`logger`, `message`, an `exception` when the record carries one (its newlines escaped, so a
traceback is still one line), a `stack` when it was logged with `stack_info`, `deployment` when
`OPENFACTORY_DEPLOYMENT` names one, and `project` and `product` when the record concerns one.
Unset, or any other value, keeps the readable line above unchanged.

WHICH PROJECT A RECORD CONCERNS is said where the work is about one, not at each `log.info`: the
worker's activities and the panel's routes that take a project run inside `about(...)`, and every
record logged inside it — by the platform or by a library — carries the project, and the product the
project belongs to (`product/key.py`). A record may also say it itself, with `extra={"project": …}`.

THE PRODUCT COSTS NO REQUEST ANYTHING (second review of #818, measured: with JSON on, each request
to a route that takes `{project}` read the registry on the default executor — the HTML shell too,
which the gate admits without a credential — and 300 unauthenticated `GET /p/acme` against a
registry 200 ms slow held an operator's `GET /api/whoami` for 5.1 s; a hung registry held it past
20 s). So the product is never read for a request or an activity. It is read from `_PRODUCTS`, this
process's copy of what the registry says each project belongs to:

  · FORMATTING A LINE READS MEMORY, NEVER THE REGISTRY, and never waits: a line written before the
    first read has landed says the project and leaves the product out, as it does for a project
    the registry does not know — never a guess;
  · THE REGISTRY IS READ AT MOST ONCE PER `PRODUCTS_WINDOW_S`, by one read at a time, ON A DAEMON
    THREAD OF ITS OWN and never on the default executor the gate and the activities share — so a
    registry that hangs holds that one thread, and the lines keep the products last read;
  · ONLY WORK THE GATE ADMITTED ASKS FOR THE READ (`freshen_products`): an activity, and a panel
    route behind the gate. A path the gate opens to anybody — the HTML shell — names its project
    and asks for nothing;
  · THE COPY IS BOUNDED BY THE REGISTRY: it holds the projects the registry names, never the names
    a URL carries.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import sys
import threading
import time
from collections.abc import Iterator

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

#: The variable that sets the platform's own level; INFO when unset or not a level.
LEVEL_VARIABLE = "OPENFACTORY_LOG_LEVEL"

#: The variable that makes every line a JSON object; any other value keeps the readable line.
FORMAT_VARIABLE = "OPENFACTORY_LOG_FORMAT"

#: The variable that names this deployment on every JSON line, for a log store that several
#: deployments write to. Unset → no `deployment` key.
DEPLOYMENT_VARIABLE = "OPENFACTORY_DEPLOYMENT"

#: The loggers that keep the platform's level. uvicorn's carry the panel's access lines.
OURS = ("openfactory", "uvicorn")

#: What a record concerns, for the JSON line: the keys a record may carry, in the order written.
TAGS = ("project", "product")

#: How long the products read from the registry serve the lines before work the gate admitted may
#: have the registry read again. A few seconds, as readiness keeps its answers (`health.WINDOW_S`):
#: a project registered a moment ago is named with its product within one window, and a process
#: that writes a thousand lines a second reads the registry once in it.
PRODUCTS_WINDOW_S = 5.0

#: The project and product the work running in this context concerns (`about`). A context variable,
#: so it follows a task, a thread `asyncio.to_thread` hands it to and a sync route's worker thread,
#: and never leaks from one request or one activity into the next.
_ABOUT: contextvars.ContextVar[tuple[tuple[str, str], ...]] = contextvars.ContextVar(
    "openfactory_log_about", default=())


def _utc(record: logging.LogRecord) -> str:
    """`2026-10-12T00:00:01.234Z` — the record's time in UTC, to the millisecond."""
    return (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z")


class _UTC(logging.Formatter):
    """The readable line, its time in UTC to the millisecond."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        return _utc(record)


class _JSON(logging.Formatter):
    """One record, one JSON object, one line (#681)."""

    def __init__(self, deployment: str = "") -> None:
        super().__init__()
        self._deployment = deployment

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, str] = {"ts": _utc(record), "level": record.levelname,
                                "logger": record.name, "message": record.getMessage()}
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            line["stack"] = self.formatStack(record.stack_info)
        if self._deployment:
            line["deployment"] = self._deployment
        line.update(_concerns(record))
        return json.dumps(line, ensure_ascii=False, default=str)


def _concerns(record: logging.LogRecord) -> dict[str, str]:
    """The project and product `record` concerns: what it says itself, else what the work it was
    logged in is `about` — a record that names its own project never borrows the block's product —
    and, for a project with no product said, the one `_PRODUCTS` holds. Reads memory only."""
    about = dict(_ABOUT.get())
    own = getattr(record, "project", None)
    project = str(own or about.get("project") or "")
    product = str(getattr(record, "product", None) or ("" if own else about.get("product")) or "")
    if project and not product:
        product = _PRODUCTS.of(project)
    return {tag: value for tag, value in (("project", project), ("product", product)) if value}


def structured() -> bool:
    """Whether `OPENFACTORY_LOG_FORMAT` asks for JSON lines."""
    return (os.environ.get(FORMAT_VARIABLE) or "").strip().lower() == "json"


@contextlib.contextmanager
def about(project: str = "", product: str = "") -> Iterator[None]:
    """Every record logged inside this block concerns `project` (and `product`), and says so on
    its JSON line. Empty values say nothing, so a caller passes what it has."""
    said = tuple((tag, value) for tag, value in (("project", project), ("product", product))
                 if value)
    token = _ABOUT.set(said)
    try:
        yield
    finally:
        _ABOUT.reset(token)


def _clock() -> float:
    """The clock `PRODUCTS_WINDOW_S` runs on. A function so a guard can move it, not sleep."""
    return time.monotonic()


def _products_in_the_registry() -> dict[str, str]:
    """`{project: product}` for every project of the registry that builds (`product.key`), read
    quietly: a line's tag is not where an operator learns what is wrong with the file."""
    from openfactory.product.key import product_key
    from openfactory.registry import ProjectRegistry

    return {name: product_key(project)
            for name, project in ProjectRegistry().each_that_builds().items()}


class _Products:
    """What the registry says each project belongs to, as this process last read it — read at most
    once per `PRODUCTS_WINDOW_S`, one read at a time, on a thread of its own, never waited for."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._known: dict[str, str] = {}
        #: when the last read began, and the read in flight (a token) — None when there is none
        self._began: float | None = None
        self._flight: object | None = None

    def of(self, project: str) -> str:
        """The product `project` belongs to, or `""` — from memory, whatever the registry is
        doing."""
        return self._known.get(project, "")

    def freshen(self) -> None:
        """Have the registry read again when no read is in flight and the last began a window ago
        or more. Returns at once: the read is a daemon thread's, which nobody waits for, and a
        process can exit under it."""
        with self._lock:
            if self._flight is not None or (
                    self._began is not None and _clock() - self._began < PRODUCTS_WINDOW_S):
                return
            flight = self._flight = object()
            self._began = _clock()
        threading.Thread(target=self._read, args=(flight,), name="openfactory-log-products",
                         daemon=True).start()

    def _read(self, flight: object) -> None:
        try:
            known: dict[str, str] | None = _products_in_the_registry()
        except Exception as exc:  # noqa: BLE001 — a log tag must never fail the work it describes
            logging.getLogger("openfactory.logs").debug(
                "the registry could not be read for the products on log lines (%s)", exc)
            known = None
        with self._lock:
            # KEPT ONLY WHILE THIS IS STILL THE READ IN FLIGHT: `forget` takes the slot from under
            # a read, and an answer begun before that must not land after it.
            if self._flight is not flight:
                return
            self._flight = None
            if known is not None:
                self._known = known

    def forget(self) -> None:
        with self._lock:
            self._known, self._began, self._flight = {}, None, None


#: This process's copy — one, bounded by the registry's projects.
_PRODUCTS = _Products()


def freshen_products() -> None:
    """Ask, without waiting, for the products on JSON lines to be read again if they are a window
    old (`_Products.freshen`). For work the gate admitted, as it starts: an activity, a panel
    route behind the gate. The readable line carries no tag, so without JSON it asks nothing."""
    if structured():
        _PRODUCTS.freshen()


def forget() -> None:
    """Drop the products this process read and any read in flight. A seam for the suite."""
    _PRODUCTS.forget()


def announce(logger: logging.Logger, line: str) -> None:
    """A line a process prints for a person when it starts — `panel: http://…`, `openfactory
    worker up · …` — printed on stdout as it always was, or, with JSON lines, logged at INFO: a
    container's log is stdout and stderr together, and one plain line in it is a line a log store
    cannot read (review of #818). Called once the log is configured."""
    if structured():
        logger.info(line)
    else:
        print(line, flush=True)


def exiting(logger: logging.Logger, sentence: str) -> SystemExit:
    """The `SystemExit` a process raises to end with a sentence for a person. Python prints its
    message as a plain line, so with JSON lines the sentence is logged at ERROR instead, and the
    process ends with code 1 all the same."""
    if structured():
        logger.error(sentence)
        return SystemExit(1)
    return SystemExit(sentence)


def level() -> int:
    """The level `OPENFACTORY_LOG_LEVEL` names, or INFO."""
    named = logging.getLevelName((os.environ.get(LEVEL_VARIABLE) or "INFO").strip().upper())
    return named if isinstance(named, int) else logging.INFO


def configure() -> bool:
    """Give this process the deployment's log format; `False` when it already had one."""
    root = logging.getLogger()
    if root.handlers:
        return False
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JSON((os.environ.get(DEPLOYMENT_VARIABLE) or "").strip())
                         if structured() else _UTC(FORMAT))
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    for name in OURS:
        logging.getLogger(name).setLevel(level())
    return True
