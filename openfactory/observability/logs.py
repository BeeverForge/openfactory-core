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
traceback is still one line), `deployment` when `OPENFACTORY_DEPLOYMENT` names one, and `project`
and `product` when the record concerns one. Unset, or any other value, keeps the readable line
above unchanged.

WHICH PROJECT A RECORD CONCERNS is said where the work is about one, not at each `log.info`: the
worker's activities and the panel's routes that take a project run inside `about(...)`, and every
record logged inside it — by the platform or by a library — carries the project, and the product the
project belongs to (`product/key.py`). A record may also say it itself, with `extra={"project": …}`.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import logging
import os
import sys
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
        if self._deployment:
            line["deployment"] = self._deployment
        about = dict(_ABOUT.get())
        for tag in TAGS:
            said = getattr(record, tag, None) or about.get(tag)
            if said:
                line[tag] = str(said)
        return json.dumps(line, ensure_ascii=False, default=str)


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


def concerning(project: str, product: str = "") -> dict[str, str]:
    """`about`'s arguments for work on the registry project `project`: the product the work
    carries, else the one the registry says the project belongs to (`product.key.product_key`).

    THE REGISTRY IS READ ONLY FOR JSON LINES. The readable line carries no tag, so a deployment
    that did not ask for JSON pays nothing; one that did pays one registry read per activity or
    request about a project. A project the registry cannot answer for is still the project: the
    product is left out, never guessed."""
    if not project:
        return {}
    if product or not structured():
        return {"project": project, "product": product}
    try:
        from openfactory.product.key import product_key
        from openfactory.registry import ProjectRegistry

        product = product_key(ProjectRegistry().get(project))
    except Exception as exc:  # noqa: BLE001 — a log tag must never fail the work it describes
        logging.getLogger("openfactory.logs").debug(
            "the product of %r could not be read for its log lines (%s)", project, exc)
    return {"project": project, "product": product}


async def concerning_from_a_loop(project: str, product: str = "") -> dict[str, str]:
    """`concerning`, for a caller on an event loop: when it has the registry to read, it reads it
    on a thread, so a request or an activity about a project never holds the loop for a file."""
    if not project or product or not structured():
        return concerning(project, product)
    return await asyncio.to_thread(concerning, project, product)


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
