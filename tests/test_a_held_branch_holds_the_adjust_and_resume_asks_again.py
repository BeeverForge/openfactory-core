"""#623 — a pass a working tree held parks, and `resume` runs that pass again.

FIELD REPORT (`docs/field-reports/2026-10-some2dgame-run.md` §A2, card 28, 2026-10-09): the adjust
pass failed because the card's branch was checked out in the operator's review tree, and `act
resume` only reopened the gate. The pass was not run again, and nothing asked about the branch
again.

WHAT IS PROVEN HERE, on the real `JobWorkflow` in a time-skipping engine with the merge gate's own
harness (`test_the_merge_gate_is_heard_on_every_path`), with `adjust_pr` / `review_pr` /
`repair_ci` answering the machine's TREE hold (`hold_cause == "tree"`):

  · the job PARKS on it, naming the tree, instead of reopening the gate over a pass that never ran;
  · a resume runs the SAME pass again, without asking the person's seal again (seals are
    single-use) and without running the agent's first pass again; still held, it parks again;
  · freed, the pass runs and the gate reopens with one pass spent, not two;
  · the new return is behind `workflow.patched`: a history recorded without it replays.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import test_the_merge_gate_is_heard_on_every_path as gate
from gate_answers import answer_merge_gate
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from openfactory.contracts import JobState, ReviewResult, RunResult
from openfactory.contracts.checks import WAIT, CiDecision
from openfactory.runtime.temporal.io import AdjustInput, CiRepairInput, ReviewPassInput, RunJobInput
from openfactory.runtime.temporal.workflow import JobWorkflow

pytestmark = pytest.mark.owns_its_engine

MARKER = "a-tree-in-the-way-holds-the-pass"
REVIEW = "/home/ana/review tree"
HELD = (f"openfactory/12 is checked out in another working tree, at {REVIEW}, and git lets a "
        f"branch be checked out in only one place, so this job did not start, and nothing in "
        f"that tree was touched. Free it with `git worktree remove '{REVIEW}'`, then resume.")
QUIET = CiDecision(verdict="pending", action=WAIT)


@pytest.fixture
async def env():
    e = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    try:
        yield e
    finally:
        await e.shutdown()


_RUNS: list[RunJobInput] = []
_ADJUSTS: list[AdjustInput] = []
_READS: list[ReviewPassInput] = []
_REPAIRS: list[CiRepairInput] = []
#: how many of the next passes find the branch held; the one after runs
_HELD_FOR = [0]


def _held(issue: str, pr_url: str) -> RunResult:
    # the machine's own marks (`JobRunner.repair_ci` / `review_pr`)
    return RunResult(ticket_id=issue, state=JobState.ON_HOLD, pr_url=pr_url, note=HELD,
                     hold_cause="tree", merge_refused=True, code_changed=False)


def _still_held() -> bool:
    if _HELD_FOR[0] > 0:
        _HELD_FOR[0] -= 1
        return True
    return False


@activity.defn(name="run_job")
async def mock_run_job(inp: RunJobInput) -> RunResult:
    _RUNS.append(inp)
    return RunResult(ticket_id=inp.issue, state=JobState.PR_OPEN, pr_url="https://x/pr/1",
                     branch="openfactory/12",
                     review=ReviewResult(decision="rejected", score=40, summary="not yet"))


@activity.defn(name="adjust_pr")
async def mock_adjust(inp: AdjustInput) -> RunResult:
    _ADJUSTS.append(inp)
    if _still_held():
        return _held(inp.issue, inp.pr_url)
    return RunResult(ticket_id=inp.issue, state=JobState.PR_OPEN, pr_url=inp.pr_url,
                     code_changed=True)


@activity.defn(name="review_pr")
async def mock_review(inp: ReviewPassInput) -> RunResult:
    _READS.append(inp)
    if _still_held():
        return _held(inp.issue, inp.pr_url)
    return RunResult(ticket_id=inp.issue, state=JobState.PR_OPEN, pr_url=inp.pr_url,
                     code_changed=False,
                     review=ReviewResult(decision="approved", score=90, summary="good"))


@activity.defn(name="repair_ci")
async def mock_repair(inp: CiRepairInput) -> RunResult:
    _REPAIRS.append(inp)
    if _still_held():
        return _held(inp.issue, inp.pr_url)
    gate._CI[0] = QUIET  # the repair turned the checks green
    return RunResult(ticket_id=inp.issue, state=JobState.PR_OPEN, pr_url=inp.pr_url,
                     code_changed=True)


@activity.defn(name="card_adjusted")
async def mock_adjusted(inp) -> str:
    return "told"


@activity.defn(name="tell_the_requester")
async def mock_tell(inp) -> None:
    return None


_OURS = {"run_job", "repair_ci"}
MOCKS = [*(m for m in gate.MOCKS if getattr(m, "__temporal_activity_definition").name not in _OURS),
         mock_run_job, mock_adjust, mock_review, mock_repair, mock_adjusted, mock_tell]


@pytest.fixture(autouse=True)
def _fresh():
    gate._REPAIRS.clear(), gate._CLOSED.clear(), gate._MERGED.clear()
    gate._HOLD_REPAIR.clear(), gate._HOLD_READ.clear()
    gate._READS[0] = 0
    gate._CI[0], gate._MSTATE[0] = QUIET, "blocked"
    gate._UPDATES.clear(), gate._AT.clear(), gate._FORCED.clear()
    gate._AUTO[0] = False
    _RUNS.clear(), _ADJUSTS.clear(), _READS.clear(), _REPAIRS.clear()
    _HELD_FOR[0] = 0


async def _at_the_gate(h, *, after: int = 0, of: list | None = None) -> dict:
    """The gate open and answerable, after `after` calls to `of` were made."""
    async def look():
        g = await h.query(JobWorkflow.awaiting_merge)
        return g if (g and g.get("gate_live") and not g.get("working")
                     and await h.query(JobWorkflow.awaiting_action) is None
                     and len(of if of is not None else []) >= after) else None
    return await gate._until("the gate open", look)


async def _parked(h, env, *, calls: list, n: int) -> dict:
    for _ in range(200):
        parked = await h.query(JobWorkflow.awaiting_action)
        if parked and len(calls) >= n:
            return parked
        await env.sleep(timedelta(seconds=1))
    raise AssertionError(f"never parked after {n} call(s); {len(calls)} made")


async def _resume(h) -> None:
    await h.signal(JobWorkflow.act_on_impediment, args=["resume", ""])


async def _discard(h) -> None:
    await answer_merge_gate(h, "discard", "", "ana")
    await h.result()


# ── the adjust ──────────────────────────────────────────────────────────────────────────────────

async def test_an_adjust_on_a_held_branch_parks_instead_of_reopening_the_gate(env):
    _HELD_FOR[0] = 1
    async with Worker(env.client, task_queue=gate.TQ, workflows=[JobWorkflow], activities=MOCKS):
        h = await gate._start(env.client)
        before = await _at_the_gate(h)
        await answer_merge_gate(h, "adjust", "the button on the right", "ana")

        parked = await _parked(h, env, calls=_ADJUSTS, n=1)
        assert parked.get("kind") == "impediment", parked
        assert REVIEW in (parked.get("note") or ""), parked
        assert await h.query(JobWorkflow.awaiting_merge) is None, (
            "the gate is still offered over a pass that never ran")
        await _resume(h)
        after = await _at_the_gate(h, after=2, of=_ADJUSTS)
        assert after["adjusts_left"] == before["adjusts_left"] - 1, (before, after)
        await _discard(h)


async def test_resumed_while_still_held_the_same_hold_stands_and_the_gate_stays_shut(env):
    _HELD_FOR[0] = 2
    async with Worker(env.client, task_queue=gate.TQ, workflows=[JobWorkflow], activities=MOCKS):
        h = await gate._start(env.client)
        await _at_the_gate(h)
        await answer_merge_gate(h, "adjust", "the button on the right", "ana")
        first = await _parked(h, env, calls=_ADJUSTS, n=1)

        await _resume(h)
        again = await _parked(h, env, calls=_ADJUSTS, n=2)

        assert again.get("note") == first.get("note")
        assert [a.instruction for a in _ADJUSTS] == ["the button on the right"] * 2
        assert len(_RUNS) == 1, "the resume ran the agent's first pass again"
        assert await h.query(JobWorkflow.gate_refused) == "", (
            "the resumed pass asked for the person's seal again, which is spent")
        assert await h.query(JobWorkflow.awaiting_merge) is None
        await _resume(h)
        await _at_the_gate(h, after=3, of=_ADJUSTS)
        await _discard(h)


async def test_resumed_once_freed_the_pass_runs_and_the_gate_reopens_with_one_pass_spent(env):
    _HELD_FOR[0] = 2
    async with Worker(env.client, task_queue=gate.TQ, workflows=[JobWorkflow], activities=MOCKS):
        h = await gate._start(env.client)
        before = await _at_the_gate(h)
        await answer_merge_gate(h, "adjust", "the button on the right", "ana")
        await _parked(h, env, calls=_ADJUSTS, n=1)
        await _resume(h)
        await _parked(h, env, calls=_ADJUSTS, n=2)
        await _resume(h)

        after = await _at_the_gate(h, after=3, of=_ADJUSTS)
        assert len(_ADJUSTS) == 3 and len(_RUNS) == 1
        assert after["adjusts_left"] == before["adjusts_left"] - 1, (
            f"held passes were charged: {before['adjusts_left']} → {after['adjusts_left']}")
        await _discard(h)


# ── a check's repair, and a re-review ───────────────────────────────────────────────────────────

async def test_a_ci_repair_held_by_a_tree_is_repaired_again_after_resume(env):
    gate._CI[0] = gate.RED
    _HELD_FOR[0] = 1
    async with Worker(env.client, task_queue=gate.TQ, workflows=[JobWorkflow], activities=MOCKS):
        h = await gate._start(env.client)
        parked = await _parked(h, env, calls=_REPAIRS, n=1)
        assert REVIEW in (parked.get("note") or "")

        await _resume(h)
        for _ in range(200):  # the watch rests after a repair: let the engine's clock run
            g = await h.query(JobWorkflow.awaiting_merge)
            if g and g.get("gate_live") and len(_REPAIRS) >= 2:
                break
            await env.sleep(timedelta(seconds=30))
        assert len(_REPAIRS) == 2 and len(_RUNS) == 1, (
            "the resume did not go back into the watch to repair again")
        await _discard(h)


async def test_a_re_review_held_by_a_tree_parks_and_resume_reads_again(env):
    _HELD_FOR[0] = 1
    async with Worker(env.client, task_queue=gate.TQ, workflows=[JobWorkflow], activities=MOCKS):
        h = await gate._start(env.client)
        await _at_the_gate(h)
        await answer_merge_gate(h, "review", "", "ana")
        parked = await _parked(h, env, calls=_READS, n=1)
        assert REVIEW in (parked.get("note") or "")

        await _resume(h)
        await _at_the_gate(h, after=2, of=_READS)
        assert len(_READS) == 2 and len(_RUNS) == 1
        assert (await h.query(JobWorkflow.verdict) or {}).get("decision") == "approved", (
            "the second reading did not replace the verdict")
        await _discard(h)


async def test_a_held_re_review_is_not_charged(env):
    """Nothing was read, so the re-review is not spent: three held ones would otherwise answer
    "3 re-reviews already spent" about a pull request nobody re-read (review of 24e59fe)."""
    _HELD_FOR[0] = 1
    async with Worker(env.client, task_queue=gate.TQ, workflows=[JobWorkflow], activities=MOCKS):
        h = await gate._start(env.client)
        await _at_the_gate(h)
        await answer_merge_gate(h, "review", "", "ana")
        await _parked(h, env, calls=_READS, n=1)
        await _resume(h)
        await _at_the_gate(h, after=2, of=_READS)
        assert [r.attempt for r in _READS] == [1, 1], [r.attempt for r in _READS]
        await _discard(h)


# ── replay ──────────────────────────────────────────────────────────────────────────────────────

async def test_a_held_pass_whose_hold_lacks_the_mark_still_resumes_into_the_watch(env, monkeypatch):
    """`_a_tree_holds_the_pass` marks the hold `merge_refused` itself, so a TREE hold that arrives
    without the machine's mark still resumes into the watch, not into a fresh job (review of
    83973c2: the mark's line survived its cut)."""
    def unmarked(issue: str, pr_url: str) -> RunResult:
        return RunResult(ticket_id=issue, state=JobState.ON_HOLD, pr_url=pr_url, note=HELD,
                         hold_cause="tree", merge_refused=False, code_changed=False)
    monkeypatch.setitem(globals(), "_held", unmarked)
    _HELD_FOR[0] = 1
    async with Worker(env.client, task_queue=gate.TQ, workflows=[JobWorkflow], activities=MOCKS):
        h = await gate._start(env.client)
        await _at_the_gate(h)
        await answer_merge_gate(h, "adjust", "the button on the right", "ana")
        await _parked(h, env, calls=_ADJUSTS, n=1)
        await _resume(h)
        await _at_the_gate(h, after=2, of=_ADJUSTS)
        assert len(_ADJUSTS) == 2 and len(_RUNS) == 1, (len(_ADJUSTS), len(_RUNS))
        await _discard(h)


async def test_a_job_recorded_before_the_marker_replays(env, monkeypatch):
    """Recorded with `patched` answering False for this marker — the arm a job in flight before
    this change selects: the held adjust reopens the gate as it used to. Replayed through the real
    `patched()`, it must replay; through the marker's arm it must diverge, or the replay proved
    nothing."""
    from temporalio import workflow as tw

    _HELD_FOR[0] = 1
    real = tw.patched
    with monkeypatch.context() as m:
        m.setattr(tw, "patched", lambda name: False if name == MARKER else real(name))
        async with Worker(env.client, task_queue=gate.TQ, workflows=[JobWorkflow],
                          activities=MOCKS):
            h = await gate._start(env.client)
            await _at_the_gate(h)
            await answer_merge_gate(h, "adjust", "the button on the right", "ana")
            await _at_the_gate(h, after=1, of=_ADJUSTS)
            await _discard(h)
        history = await h.fetch_history()

    await Replayer(workflows=[JobWorkflow],
                   data_converter=pydantic_data_converter).replay_workflow(history)

    monkeypatch.setattr(tw, "patched", lambda name: True if name == MARKER else real(name))
    with pytest.raises(Exception) as caught:
        await Replayer(workflows=[JobWorkflow],
                       data_converter=pydantic_data_converter).replay_workflow(history)
    said = str(caught.value)
    assert "determinis" in said.lower() or "TMPRL1100" in said or "Nondeterminism" in said, (
        f"the marker's arm failed the replay for another reason: {said[:400]}")
