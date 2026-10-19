"""The job list is the same list however many jobs are asked about at once (#754, criterion 3:
"keeping the existing newest-first sort" and "both keep the per-row body unchanged").

`list_jobs` asked about each workflow one after another, so the rows it kept were the first `limit`
that were not `gone`, in the order `list_workflows` gave them, before the newest-first sort. The fix
asks `OPENFACTORY_LIST_CONCURRENCY` of them at once (8 when unset), and the two ways that can change
the answer without failing anything else are both here:

- KEPT IN THE ORDER THEY FINISHED. The sort is by `start_time` and is stable, so only rows that tie
  on it keep list order — and they keep it only if they were appended in list order. Every stand-in
  RPC here costs LESS the later its workflow is in the list, so the completion order is the list
  order reversed, and the fixture has two pairs of ties whose order would flip.
- THE LIMIT COUNTED ON WHAT WAS ASKED, NOT ON WHAT IS SHOWN. `gone` rows (aged out of retention,
  still in visibility) are dropped before they count, so `limit=5` is five cards a person sees.

THESE PASS ON THE SEQUENTIAL LIST, and that is their claim: `main` ignores the variable, so all
three settings give the one list it always gave. What turns them red is a concurrent list that
differs from it (`tools/mutations/754_the_job_list_is_asked_side_by_side_and_shared.py`, the
"completion order" and "limit before the gone filter" cuts).

The fixture is one of each kind of row `list_jobs` builds, read through the module's own vocabulary
(`JobState`, `MERGE_WAIT`, `ATTENTION_STATES`, `WorkflowExecutionStatus`, `JobWorkflow`'s queries),
so a row that is the same in all three runs is the same for a reason and not because every row came
back `gone`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from temporalio.client import WorkflowExecutionStatus

from openfactory.contracts.state import JobState
from openfactory.runtime.temporal import view as tv
from openfactory.runtime.temporal.workflow import JobWorkflow

VARIABLE = "OPENFACTORY_LIST_CONCURRENCY"
PROJECT = "books"
#: Each stand-in RPC of the workflow at list position `i` (of `n`) waits `(n - i) * STEP` seconds.
STEP = 0.002
NOW = datetime.now(UTC)


@pytest.fixture(autouse=True)
def _nothing_remembered_between_runs(monkeypatch):
    """A clean engine memory and no registry: the project is the one the fixture names."""
    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "10")
    monkeypatch.setattr(tv, "_registered_projects", lambda: [PROJECT])
    # #330: whether `address` is offered at a merge gate is the forge's answer, read from the
    # registry; the stand-in says yes, so the field is present and the same in every run.
    monkeypatch.setattr(tv, "_lists_review_comments", lambda project: project == PROJECT)
    tv.reset_clients()
    _forget()
    yield
    _forget()
    tv.reset_clients()


def _forget() -> None:
    """Everything a previous `list_jobs` left that would make the next one ask less: the closed
    states, the deploy outcomes and, once it exists, the shared answer (asked with `getattr`, so
    this file also runs against a tree that has none)."""
    tv._state_cache.clear()
    tv._deploy_cache.clear()
    forget_jobs = getattr(tv, "forget_jobs", None)
    if forget_jobs is not None:
        forget_jobs()


class _Wf:
    """A `JobWorkflow` as `list_workflows` yields it, and what the engine answers about it."""

    def __init__(self, issue: str, *, minutes_ago: int, status=WorkflowExecutionStatus.RUNNING,
                 true_status=None, queries=None, result=None, gone=False) -> None:
        self.id = tv.job_id(PROJECT, issue)
        self.run_id = f"run-{issue}"
        self.status = status
        self.start_time = NOW - timedelta(minutes=minutes_ago)
        self.close_time = None if status == WorkflowExecutionStatus.RUNNING else NOW
        self.true_status = true_status or status
        self.queries = queries or {}
        self.result = result
        self.gone = gone
        self.title = f"ticket {issue}"
        self.latency = 0.0

    async def memo(self):
        return {"title": self.title}


class _Desc:
    def __init__(self, status, run_id) -> None:
        self.status = status
        self.run_id = run_id


class _Handle:
    def __init__(self, wf: _Wf | None, deploy: str | None = None) -> None:
        self._wf = wf
        self._deploy = deploy

    async def _wait(self) -> None:
        await asyncio.sleep(self._wf.latency if self._wf else 0)

    async def describe(self):
        await self._wait()
        if self._deploy is not None:
            return _Desc(WorkflowExecutionStatus.COMPLETED, "deploy-run")
        if self._wf is None or self._wf.gone:
            raise RuntimeError("workflow not found")  # aged out of retention
        return _Desc(self._wf.true_status, self._wf.run_id)

    async def query(self, q, *_a, **_kw):
        await self._wait()
        return self._wf.queries.get(q)

    async def result(self):
        await self._wait()
        return self._deploy if self._deploy is not None else self._wf.result


class _Page:
    """`WorkflowExecutionAsyncIterator`'s shape (temporalio 1.34.0): `__aiter__`/`__anext__`."""

    def __init__(self, wfs) -> None:
        self._left = iter(wfs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._left)
        except StopIteration:
            raise StopAsyncIteration from None


class _Engine:
    def __init__(self, wfs: list[_Wf], *, deployed: dict[str, str] | None = None) -> None:
        self._wfs = wfs
        # The later in the list, the faster it answers: completion order is list order reversed.
        for i, wf in enumerate(wfs):
            wf.latency = (len(wfs) - i) * STEP
        self._deploys = {f"openfactory-deploy-{PROJECT}-{issue}": outcome
                         for issue, outcome in (deployed or {}).items()}

    def list_workflows(self, query):
        return _Page(self._wfs)

    def get_workflow_handle(self, wf_id, run_id=None):
        if wf_id in self._deploys:
            return _Handle(None, deploy=self._deploys[wf_id])
        return _Handle(next((w for w in self._wfs if w.id == wf_id), None))


def _floor() -> tuple[_Engine, dict[str, dict]]:
    """One of each row, in list order, with what each must read as. Two pairs tie on start time
    (20 and 40 minutes ago), each pair's later member answering first."""
    merge = {"pr_url": "https://forge.example/books/pull/7"}
    wfs = [
        _Wf("1", minutes_ago=20, queries={JobWorkflow.awaiting_action: {
            "kind": "impediment", "state": JobState.ON_HOLD.value, "note": "the spec is unclear"}}),
        _Wf("2", minutes_ago=5, queries={JobWorkflow.awaiting_merge: {**merge, "working": True}}),
        _Wf("3", minutes_ago=20, queries={JobWorkflow.awaiting_merge: {**merge, "auto": True}}),
        _Wf("4", minutes_ago=30, queries={JobWorkflow.awaiting_merge: {**merge, "auto": False}}),
        _Wf("5", minutes_ago=1, queries={JobWorkflow.awaiting_approval: True,
                                         JobWorkflow.gate_refused: "the seal did not verify"}),
        _Wf("6", minutes_ago=40, true_status=WorkflowExecutionStatus.TERMINATED),
        _Wf("7", minutes_ago=60, status=WorkflowExecutionStatus.COMPLETED,
            result={"state": JobState.MERGED.value}),
        _Wf("8", minutes_ago=40, status=WorkflowExecutionStatus.COMPLETED,
            result={"state": JobState.ON_HOLD.value}),
        _Wf("9", minutes_ago=2, gone=True),
        _Wf("10", minutes_ago=3, gone=True),
        _Wf("11", minutes_ago=10),
    ]
    expected = {
        "1": {"state": JobState.ON_HOLD.value, "attention": True},
        "2": {"state": JobState.REPAIRING.value, "attention": False},
        "3": {"state": "merging", "attention": False},
        "4": {"state": "awaiting_your_merge", "attention": True},
        "5": {"state": JobState.AWAITING_PROD_APPROVAL.value, "attention": True,
              "refused": "the seal did not verify"},
        "6": {"state": JobState.FAILED.value, "status": "closed", "attention": False},
        "7": {"state": JobState.MERGED.value, "deploy": "deployed", "attention": False},
        "8": {"state": JobState.ON_HOLD.value, "attention": False},
        "11": {"state": "running", "attention": False},
    }
    return _Engine(wfs, deployed={"7": "success"}), expected


async def _list(monkeypatch, setting: str | None, engine: _Engine, **kw) -> list[dict]:
    if setting is None:
        monkeypatch.delenv(VARIABLE, raising=False)
    else:
        monkeypatch.setenv(VARIABLE, setting)
    _forget()
    return await tv.list_jobs(engine, "default", **kw)


async def test_the_same_rows_in_the_same_order_one_at_a_time_and_eight_at_a_time(monkeypatch):
    """Criterion 3. One at a time, eight at a time and unset give one list, row for row and field
    for field, newest first with ties in the order the engine listed them."""
    engine, expected = _floor()

    one = await _list(monkeypatch, "1", engine)
    eight = await _list(monkeypatch, "8", engine)
    unset = await _list(monkeypatch, None, engine)

    assert eight == one
    assert unset == one

    # THE FIXTURE REACHED EVERY KIND OF ROW: equal lists of `gone` rows would prove nothing.
    by_issue = {r["issue"]: r for r in one}
    assert set(by_issue) == set(expected)
    for issue, fields in expected.items():
        assert {k: by_issue[issue].get(k) for k in fields} == fields, issue
        # A person is asked only about a live job in a state that needs one.
        assert fields["attention"] == (fields["state"] in tv.ATTENTION_STATES
                                       and by_issue[issue]["status"] == "running"), issue
    assert by_issue["4"]["action"]["kind"] == tv.MERGE_WAIT
    assert by_issue["4"]["action"]["can_address"] is True
    assert by_issue["1"]["title"] == "ticket 1"

    # NEWEST FIRST, TIES IN LIST ORDER: 5 (1 min), 2, 11, then 1 before 3 (both 20 min, 1 listed
    # first and answering last), 4, then 6 before 8 (both 40 min), then 7.
    assert [r["issue"] for r in one] == ["5", "2", "11", "1", "3", "4", "6", "8", "7"]
    starts = [r["start_time"] for r in one]
    assert starts == sorted(starts, reverse=True)


@pytest.mark.parametrize("setting", ["1", "8", None])
async def test_the_limit_counts_the_jobs_shown_not_the_jobs_asked_about(monkeypatch, setting):
    """Criterion 3. `limit=5` over twelve jobs, two of the first five aged out: the five cards are
    the first five that are not `gone`, in list order, whatever the setting."""
    wfs = [_Wf(str(i), minutes_ago=i, gone=i in (1, 3)) for i in range(12)]
    engine = _Engine(wfs)

    rows = await _list(monkeypatch, setting, engine, limit=5)

    assert [r["issue"] for r in rows] == ["0", "2", "4", "5", "6"]
