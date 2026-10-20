"""Readers arriving together share ONE read, on one loop, for one question (#166, #165, #754).

THIS IS THE ONE COPY. It was built in `floor/reading.py` for the schedule read (#166), the budget
read needed exactly the same thing, and the engine's job list (`runtime/temporal/view.py`, #754)
needs it a third time. A runtime module importing the floor would invert the dependency, and a
second copy beside the first is two mechanisms to keep true, so it lives here, below both.
`floor/reading.py` imports it under the names it always had (`_Flight`, `_OneAtATime`).

THE KEY IS #754's. The schedule and budget reads ask one question each, so "a read is in flight on
this loop" was enough to join it. The job list is asked several questions — another namespace,
`limit=50` from the tech-lead (`techlead/conversation.py`), a `query` — and a reader that joined a
scan of a different question would be handed somebody else's list. engineering-lessons §11: what
a cache is keyed on has to be what the work it skips would have read. The key defaults to `None`,
so a read that asks one question passes nothing and behaves exactly as before.
"""

from __future__ import annotations

import asyncio
from collections.abc import Hashable
from dataclasses import dataclass


@dataclass
class _Flight:
    """The ONE read of its kind this process has in flight, the loop it belongs to, and the
    question it answers.

    THE LOOP IS PART OF IT, for the reason `view.connect()` keys its pool by the running loop: a
    task belongs to the loop that made it. These reads are reached from more than one loop in a
    process's life — `techlead/conversation.py` opens an `asyncio.run` per question and so does the
    CLI's `poller status` — and awaiting a task from another loop raises `RuntimeError: … attached
    to a different loop`, while one whose loop has stopped never resolves at all. So a reader joins
    a flight only while the RUNNING loop is the one that made it, by identity and nothing else.

    THE KEY IS PART OF IT TOO: a reader joins only a flight asking its own question (`==`)."""

    loop: asyncio.AbstractEventLoop
    task: asyncio.Task | None = None
    key: Hashable = None


class _OneAtATime:
    """Readers arriving together share ONE read; each is handed the answer separately.

    THE MECHANISM IS #166's AND #165's. It was built for the schedule read, and the budget read
    needed exactly the same thing (a subprocess per concurrent reader — ten floor reads at the
    window's expiry spawned ten `gh` processes, measured 2026-09-19), and so did the engine's job
    list (#754: six askers together cost six scans, measured on f37aeaa). There is one mechanism,
    with one instance per read that needs it: `floor.reading._intake_read`,
    `floor.reading._budget_read` and `runtime.temporal.view._jobs_read`. Each argument below is
    `intake_cached`'s, and it holds for any read at all.

    A TASK, NOT A LOCK:

      - A LOCK IS SINGLE FLIGHT ON SUCCESS ONLY. Behind one, a reader queued on a failing read
        takes the lock, finds nothing stored — no memo here stores a failure — and reads again:
        six callers behind a 0.5 s refusal fail at 0.5 / 1.0 / … / 3.0 s, an outage turned into a
        queue. Waiting on the one task hands every waiter THAT read's failure at the instant it
        fails, and it is shared, not stored: the slot empties when the task ends, so a reader
        arriving afterwards tries again, which is what lets a recovered vendor be picked up.
      - IT BELONGS TO NO CALLER. Were the read run inside the first reader's coroutine, that
        reader's cancellation — a browser that went away — would cancel the read under everybody
        queued behind it. Every reader waits through `asyncio.shield`, so one going away takes
        only itself; the read lands, and fills the window, whoever is left to see it.

    ONE SLOT, NOT A TABLE — at most one read in flight is ever registered, so there is nothing here
    for traffic to grow. A reader on another loop, or asking another question (`key`), does not
    join it and does not queue behind it: it reads for itself and takes the slot, and the
    displaced read still lands for its own waiters (it stores nothing: `holds` says it lost).
    """

    def __init__(self) -> None:
        self.flight: _Flight | None = None

    async def shared(self, read, *, key: Hashable = None):
        """Join the read in flight for the same loop and `key`, or start it. `read(flight)` is the
        coroutine function that does the work; it is handed its own flight so it can ask `holds`
        before storing."""
        loop = asyncio.get_running_loop()
        flight = self.flight
        if flight is None or flight.loop is not loop or flight.key != key:
            flight = self.flight = _Flight(loop=loop, key=key)
            flight.task = loop.create_task(read(flight))
            # THE SLOT IS GIVEN UP BY THE TASK'S ENDING, NOT BY ITS BODY. A `finally` inside the
            # read does not run for a task cancelled before its first step — the coroutine is
            # never entered — and that would leave a finished task in the slot, handing its
            # `CancelledError` to every later reader on this loop until something forgot it. A
            # done callback runs however the task ended. Added HERE, before any waiter's `shield`
            # adds its own, because callbacks run in the order they were added: the slot is empty
            # by the time the first waiter resumes.
            flight.task.add_done_callback(lambda _task, landed=flight: self._give_up(landed))
        return await asyncio.shield(flight.task)

    def _give_up(self, flight: _Flight) -> None:
        """…unless the slot already names somebody else's read, which is not this one's to empty."""
        if self.flight is flight:
            self.flight = None

    def holds(self, flight: _Flight) -> bool:
        """Whether this read is still the registered one — `forget`, a reader on another loop and a
        reader asking another question all take the slot from under a read in flight, and a read
        that lost it stores nothing."""
        return self.flight is flight

    def forget(self) -> None:
        self.flight = None
