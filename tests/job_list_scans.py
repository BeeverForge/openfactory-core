"""An engine that counts the job lists it is asked for (#754, criteria 4 and 5).

`list_jobs` paid one whole scan per reader: `list_workflows`, then a describe and up to three worker
queries per running row. Readers arriving together (the floor, the inbox, each browser's stream
tick) and readers right after one another (the panel's re-read 600-800 ms after a click) each paid
it again. What the sharing tests count is the number of times the engine was asked to LIST, because
that is the cost being shared: every `list_workflows` call is one scan, whatever it then asks.

The engine's shape is the one `list_jobs` uses and nothing more (`tests/test_temporal_view.py`'s
fakes): `list_workflows(query)` returning an async iterator, `get_workflow_handle(wf_id,
run_id=None)`. The listing waits `DELAY` before its first row, so askers started together are
provably in flight at the same time; that is the only sleep, and it is never what an assertion
measures.

Every row's memo title says which scan built it, so an answer handed to a reader it was not built
for is visible in the rows themselves, not only in a count.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from temporalio.client import WorkflowExecutionStatus

from openfactory.runtime.temporal import view as tv
from openfactory.runtime.temporal.workflow import JobWorkflow

PROJECT = "books"
#: The job the writes answer: never one of the listed rows, so a write leaves the list as it was
#: and the only reason a later list can differ is that it was read again.
WRITTEN = "42"
#: How long a listing takes before its first row: long enough that askers started together are
#: all waiting while it runs, short enough to cost nothing.
DELAY = 0.05
#: What a listing filtered by start time answers: a different question, a different list.
RECENT = 'StartTime > "2026-10-19T00:00:00Z"'


class _Wf:
    """A RUNNING `JobWorkflow` as `list_workflows` yields it, stamped with the scan that listed it."""

    def __init__(self, issue: str, scan: int) -> None:
        self.id = tv.job_id(PROJECT, issue)
        self.run_id = f"run-{issue}"
        self.status = WorkflowExecutionStatus.RUNNING
        self.start_time = datetime.now(UTC) - timedelta(minutes=int(issue))
        self.close_time = None
        self.scan = scan

    async def memo(self):
        return {"title": f"ticket {self.id} (scan {self.scan})"}


class _Page:
    """`WorkflowExecutionAsyncIterator`'s shape (temporalio 1.34.0): `__aiter__`/`__anext__`."""

    def __init__(self, wfs: list[_Wf], *, fail: bool) -> None:
        self._left = iter(wfs)
        self._fail = fail
        self._started = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._started:
            self._started = True
            await asyncio.sleep(DELAY)
            if self._fail:
                raise RuntimeError("the engine refused the listing")
        try:
            return next(self._left)
        except StopIteration:
            raise StopAsyncIteration from None


class _Desc:
    def __init__(self, run_id: str) -> None:
        self.status = WorkflowExecutionStatus.RUNNING
        self.run_id = run_id


class _Handle:
    """A live job. The listed ones are at no gate; `WRITTEN` is at every gate a write asks
    about first, so each write in `view.py` gets as far as the write itself."""

    def __init__(self, engine: CountedEngine, wf_id: str) -> None:
        self._engine = engine
        self.id = wf_id

    async def describe(self):
        return _Desc("run")

    async def query(self, q, *_a, **_kw):
        if self.id != tv.job_id(PROJECT, WRITTEN):
            return None
        return {
            JobWorkflow.awaiting_action: {"kind": "impediment", "state": "on_hold"},
            JobWorkflow.awaiting_merge: {"pr_url": "https://forge.example/books/pull/42",
                                         "auto": False, "adjusts_left": 1},
            JobWorkflow.awaiting_approval: True,
            JobWorkflow.release_wait: {"hears": True, "adjusts_left": 1},
        }.get(q)

    async def signal(self, signal, *args, **kwargs):
        self._engine.writes.append(("signal", self.id))


class CountedEngine:
    """Counts its listings (`scans`) and records each one's query (`seen_query`) and each write."""

    def __init__(self, issues: int = 8, *, failing: int = 0) -> None:
        self._issues = [str(i) for i in range(1, issues + 1)]
        self._failing = failing
        self.scans = 0
        self.seen_query: list[str] = []
        self.writes: list[tuple[str, str]] = []

    def list_workflows(self, query):
        self.scans += 1
        self.seen_query.append(query)
        fail = self._failing > 0
        self._failing -= fail
        issues = self._issues[:2] if RECENT in query else self._issues
        return _Page([_Wf(issue, self.scans) for issue in issues], fail=fail)

    def get_workflow_handle(self, wf_id, run_id=None):
        return _Handle(self, wf_id)

    async def start_workflow(self, run, params, *, id, task_queue, **_kw):
        self.writes.append(("start", id))
        return _Handle(self, id)

    async def execute_workflow(self, run, arg, *, id, task_queue, **_kw):
        # The gate-key probe: a workflow started and waited for, answering "" (the key agrees).
        self.writes.append(("start", id))
        return ""


def forget() -> None:
    """Everything a previous `list_jobs` left: the closed states, the deploy outcomes and, once it
    exists, the shared answer (asked with `getattr`, so these files also run against a tree that
    has none — the red-first run points them at one)."""
    tv._state_cache.clear()
    tv._deploy_cache.clear()
    forget_jobs = getattr(tv, "forget_jobs", None)
    if forget_jobs is not None:
        forget_jobs()


def scans_of(rows: list[dict]) -> set[str]:
    """Which scans built these rows, read off their titles."""
    return {r["title"].rsplit("(scan ", 1)[1].rstrip(")") for r in rows}
