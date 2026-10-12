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
"""

from __future__ import annotations

import logging
import os
import sys
import time

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

#: The variable that sets the platform's own level; INFO when unset or not a level.
LEVEL_VARIABLE = "OPENFACTORY_LOG_LEVEL"

#: The loggers that keep the platform's level. uvicorn's carry the panel's access lines.
OURS = ("openfactory", "uvicorn")


class _UTC(logging.Formatter):
    """`2026-10-12T00:00:01.234Z` — the record's time in UTC, to the millisecond."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        return (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                + f".{int(record.msecs):03d}Z")


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
    handler.setFormatter(_UTC(FORMAT))
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    for name in OURS:
        logging.getLogger(name).setLevel(level())
    return True
