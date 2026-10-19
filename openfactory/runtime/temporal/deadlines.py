"""How long this deployment waits for its durable engine — read without the engine's client.

ITS OWN MODULE, AND A SMALL ONE (#681, review of #818 on f48b79fd): the healthcheck a container runs
every fifteen seconds asks `health.deadline()`, which follows `OPENFACTORY_ENGINE_DEADLINE`, and
read through `view` it imported the engine's client, the workflows and the activities to read one
variable — measured, 158 ms of the probe's start and most of its 62 MB, in each of two containers.
`view` names the same two functions from here, so the probe and the reads it waits for never
disagree about them.
"""

from __future__ import annotations

import logging
import os

#: The logger `view` says a malformed number through, as it did when these lived there.
log = logging.getLogger("openfactory.panel.temporal")


#: What a READ somebody is waiting for may spend on an engine that is not answering (#159).
#:
#: MEASURED, ON THE REAL STACK. With the engine killed under a running panel — `main` at `98dc177`,
#: so with the pooled client — `/api/floor` took **38.8 s**, `/api/inbox` 8.9 s (and then a 500),
#: `/api/temporal/jobs` 6.3 s: the client retries an unreachable engine (`gRPC call
#: describe_schedule retried 7 times`) before anything gives up. The board's own route stayed at
#: 8 ms and the board still crawled — a tab gets six connections to a host, the page asks for the
#: floor on every engine frame and holds the stream open, so those six fill with requests waiting
#: on retries and every other read queues behind them.
#:
#: WHAT A HEALTHY READ COSTS, so the headroom is a measurement and not a hope (review of #161).
#: On a dev server with the worker running, timed through these functions:
#:
#:     list_jobs, 8 jobs      51 ms median, 80 ms max
#:     list_jobs, 50 jobs     317 ms median, 352 ms max   ← 50 is the panel's own limit
#:     job_detail             8 ms
#:     intake                 5 ms
#:
#: So three seconds was roughly ten times what the panel's largest list cost, asked one job after
#: another as it was then. Each RUNNING row is a describe plus up to three queries a worker answers,
#: and that sum is what overran this bound on a busy floor (#754). The listed jobs are now asked
#: about in batches of `view.list_concurrency()` (8 unset), so a list costs about one slowest row
#: per batch of the listing instead of every running row's round trips added up. Readers asking
#: together, or within `LIST_TTL_S`, share one scan (`view.list_jobs`). Measured 2026-10-19 on
#: `temporal server start-dev` 1.9.1 (Server 1.32.0), temporalio 1.34.0, a stand-in registered as
#: `JobWorkflow` answering its real queries: 98 listed, the 50 read being 48 running (8 at a merge
#: gate) and 2 closed, 10 scans each:
#:
#:     one after another (f37aeaa)        558 ms median, 583 ms max   185 describes and queries
#:     8 at a time (unset)                357 ms median, 364 ms max   188 (the last batch's extra)
#:     OPENFACTORY_LIST_CONCURRENCY=1     564 ms median, 594 ms max
#:     six readers at once                6 scans in ~2.0-2.2 s on f37aeaa; 1 scan in ~350 ms
#:
#: The compose stack's `temporalio/auto-setup:1.25.2` on Postgres 16 gave the same: 557 against
#: 345 ms, 6 scans against 1. On loopback a scan is bound by THIS process's CPU (a 354 ms scan
#: at eight spent 327 ms of it; one at a time, 307 ms of 576), which is why eight at once buys a
#: third here and not eightfold: what it overlaps is the round trips, and those are what a
#: namespace across a network pays.
#:
#: The bound also catches a second real case: a workflow whose worker is gone cannot answer a
#: query at all, and `list_jobs` did not return in 120 s against eight such jobs. It now degrades
#: in three (measured again 2026-10-19 on the dev server above, f37aeaa and now alike: 3.00 s,
#: the same sentence, and no task still running 1 s later). The deadline sits on the shared scan
#: (`view._scan`), so running out of time cancels every question the scan still has out.
#:
#: A NUMBER A DEPLOYMENT CAN CHANGE, because "slow" is a property of somebody's network: a Temporal
#: Cloud namespace across a region answers in tenths of a second, and this must not call that
#: unreachable. Read per call, so an operator changes it without a rebuild.
def read_deadline() -> float:
    return _seconds("OPENFACTORY_ENGINE_DEADLINE", 3.0)


#: How long an engine that did not answer is remembered as unreachable, so the NEXT read does not
#: pay the same wait again. Short on purpose: an engine that came back must be picked up without a
#: restart, which is the rule `connect()` already holds for a failed connect.
def unreachable_window() -> float:
    return _seconds("OPENFACTORY_ENGINE_UNREACHABLE_FOR", 3.0)


def _seconds(name: str, fallback: float) -> float:
    try:
        wanted = float(os.environ.get(name, "") or fallback)
    except ValueError:
        log.warning("%s is not a number (%r) — using %ss", name, os.environ.get(name), fallback)
        return fallback
    return wanted if wanted > 0 else fallback
