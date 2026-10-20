"""#756 (criteria A, C, E, F) — a red check the diff does not touch is re-run before an agent is paid.

WHAT IT COST. A blocking check that failed for a reason no changed file touches — a flaky
integration test, a busy shared environment — was handed to a paid agent pass. The agent changed
nothing (there was nothing in the change to fix), the next attempt failed the same way, and
`_CI_REPAIR_MAX` parked the card `CI still failing after 2 repair attempt(s)`: two agent passes
spent on a rerun's worth of trouble. The cheaper move is to re-run the failed jobs, through the
forge's own seam (`base.rerun_failed_of`, criterion D, in
`test_rerunning_failed_jobs_is_a_capability_a_forge_declares.py`), and let the watch read the
checks again.

    A  the first attempt on a head whose failing log names no file the pull request changes
       (no full path, no basename with its extension) re-runs the failed jobs, says so on the
       pull request naming what the forge re-ran, and launches no agent, on either door (the
       inline runner and a remote box). A log that names a changed file, a diff that could not be
       read, a diff that was cut, and any later attempt (PO answer Q1: once per head) launch the
       agent as before
    C  the re-run is counted against the watch's existing repair cap, and one attempt never
       re-runs twice
    E  the re-run waits on no clock of its own
    F  #184's property holds: an empty log is held for a person before any re-run is weighed,
       and the agent is handed the very log the decision was made from, read once

ON MAIN (9a421ae, the tests alone) every row that expects a re-run is red: `_run_ci_repair` has
two outcomes, the #184 hold or the agent, so the fake forge's `rerun_failed` is never called and
the agent is launched. The rows that expect the agent are green there BY DESIGN — they guard the
paths the new move must not take — and each names the cut in
`tools/mutations/756_an_unrelated_red_check_is_rerun_not_repaired.py` that turns it red.

Every repair input here passes `attempt=1` (or 2) explicitly: `CiRepairInput.attempt` defaults to
0, and the workflow increments before it calls, so its first repair arrives as attempt 1.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from temporalio import activity
from temporalio.client import Client, WorkflowHandle
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from openfactory.adapters.forge import base
from openfactory.contracts import JobState, RunResult
from openfactory.contracts.checks import Check, decide
from openfactory.runtime.temporal import activities as acts
from openfactory.runtime.temporal import workflow as wf
from openfactory.runtime.temporal.io import CiRepairInput, JobParams
from openfactory.runtime.temporal.workflow import JobWorkflow
from openfactory.techlead import CODE as CAUSE_CODE
from tests import test_a_failing_check_is_read_for_what_it_is as watch

PR = "https://github.com/acme/x/pull/2"
CHANGED = "src/billing/invoice.py"
DIFF = (f"diff --git a/{CHANGED} b/{CHANGED}\n"
        f"--- a/{CHANGED}\n+++ b/{CHANGED}\n@@ -1 +1 @@\n-a\n+b\n")
#: The issue's shape: the failing test lives in a file the pull request does not change.
UNRELATED = "FAILED tests/integration/test_queue.py::test_it - TimeoutError: broker did not answer"
RED_BUILD = [{"name": "build", "bucket": "fail", "blocking": True, "kind": "code",
              "url": "https://github.com/acme/x/actions/runs/1/job/7"}]
PENDING_BUILD = [{"name": "build", "bucket": "pending", "blocking": True, "kind": "code",
                  "url": "https://github.com/acme/x/actions/runs/1/job/9"}]
#: What the comment says about why: no file the pull request changes appears in the log.
WHY = "no file this pull request changes appears in"


def _diff_of(*paths: str) -> str:
    return "".join(f"diff --git a/{p} b/{p}\n--- a/{p}\n+++ b/{p}\n@@ -1 +1 @@\n-a\n+b\n"
                   for p in paths)


class _Forge:
    """A typed forge with a red blocking build, which can re-run its failed jobs.

    `reran` is what `rerun_failed` answers (a list of names, or an exception to raise); `logs`
    answers `failed_ci_logs` in turn, the last one repeating, so a second read of the log is
    visible as a different text. `events` is the order things happened in."""

    checks_are_typed = True

    def __init__(self, *, log=UNRELATED, diff=DIFF, checks=None, reran=("build",),
                 after_rerun=None):
        self.logs = [log] if isinstance(log, str) else list(log)
        self.diff = diff
        self.checks = list(checks if checks is not None else RED_BUILD)
        self.reran = reran
        self.after_rerun = after_rerun  # the rows the checks read once a re-run was asked
        self.log_reads = 0
        self.events: list[str] = []
        self.comments: list[str] = []

    def pr_checks(self, *, pr):
        return self.checks

    def failed_ci_logs(self, *, pr):
        self.log_reads += 1
        return self.logs[min(self.log_reads, len(self.logs)) - 1]

    def pr_diff(self, *, pr, **_kw):
        self.events.append("diff")
        return self.diff

    def rerun_failed(self, *, pr):
        self.events.append("rerun")
        if self.after_rerun is not None:
            self.checks = list(self.after_rerun)
        if isinstance(self.reran, BaseException):
            raise self.reran
        return list(self.reran)

    def review_pr(self, *, pr, event, body):
        assert event == "comment"
        self.events.append("comment")
        self.comments.append(body)

    @property
    def reruns(self) -> int:
        return self.events.count("rerun")


@pytest.fixture
def on_the_worker(monkeypatch):
    """The worker's seams, shaped as in `test_the_repair_brief_states_the_failure_it_was_given`:
    a project, its forge, and the two doors an agent pass goes through — the inline runner
    (`build_runner(...).repair_ci`) and a remote box (`remote_box(...).launch`) — each recorded.

    `use(forge, door=..., changed=...)` installs the forge and the door; `changed` is the
    `code_changed` the agent's pass answers. It returns the list of passes launched: the log each
    inline pass was handed, or the variant each remote box was launched with."""
    agents: list[str] = []
    project = SimpleNamespace(name="p", tracker=SimpleNamespace(options={}, kind="github"),
                              forge=None)
    monkeypatch.setattr(acts, "ProjectRegistry", lambda: SimpleNamespace(get=lambda _n: project))
    monkeypatch.setattr(acts, "_ref_repo", lambda _p, _i: ("acme/x", ""))
    monkeypatch.setattr(acts, "_runner_view", lambda _p, _i: (project, ""))
    monkeypatch.setattr(acts, "_resolved_image", lambda _p, sandbox: "")
    monkeypatch.setattr(acts, "box_options", lambda _p, _axis: {})
    monkeypatch.setattr(acts, "box_credential_env", lambda _p: {})
    monkeypatch.setattr("openfactory.paths.events_file", lambda _p, _i: None)
    monkeypatch.setattr("openfactory.observability.registry.journal_for",
                        lambda *_a, **_k: None)

    def use(forge, *, door="inline", changed=True):
        monkeypatch.setattr(acts, "_forge_for", lambda _p: forge)
        monkeypatch.setattr(acts, "installed_box_traits",
                            lambda _s: SimpleNamespace(remote=door == "remote"))

        def runner(*a, **kw):
            def repair_ci(issue, ci_log, pr_url="", human=False):
                agents.append(ci_log)
                return RunResult(ticket_id=issue, state=JobState.PR_OPEN, pr_url=pr_url,
                                 code_changed=changed)
            return SimpleNamespace(repair_ci=repair_ci)

        def launch(box, *, variant, extra_env, journal, timeout, run_id):
            agents.append(variant)
            return RunResult(ticket_id=box.issue, state=JobState.PR_OPEN,
                             pr_url=extra_env["OPENFACTORY_PR"], code_changed=changed)

        monkeypatch.setattr(acts, "build_runner", runner)
        monkeypatch.setattr(acts, "remote_box", lambda _s: SimpleNamespace(launch=launch))
        return agents
    return use


FIRST = CiRepairInput(project="p", issue="12", pr_url=PR, sandbox="worktree", attempt=1)
SECOND = CiRepairInput(project="p", issue="12", pr_url=PR, sandbox="worktree", attempt=2)

DOORS = [pytest.param("inline", id="the inline runner"),
         pytest.param("remote", id="a remote box")]


# ═══ A: an unrelated red check is re-run, and no agent is paid ══════════════════════════════════

@pytest.mark.parametrize("door", DOORS)
def test_a_failing_log_that_names_no_changed_file_reruns_the_failed_jobs_and_launches_no_agent(
        on_the_worker, door):
    """Criterion A, the issue itself. The log names `tests/integration/test_queue.py`, the pull
    request changes `src/billing/invoice.py`: the failed jobs are re-run and no agent is launched,
    whichever door the agent would have gone through. The result keeps the reviewer's verdict
    standing (`code_changed=False`, #179) and sends the watch back to reading the checks.

    Red on main: the fake's `rerun_failed` is never called and an agent is launched."""
    forge = _Forge()
    agents = on_the_worker(forge, door=door)
    got = acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001 — the activity's own body
    assert forge.reruns == 1, f"the failed jobs were not re-run: {forge.events}"
    assert agents == [], f"an agent was paid for a check the change does not touch: {agents}"
    assert got.state is JobState.PR_OPEN and got.pr_url == PR
    assert got.code_changed is False, "a re-run was reported as a change to the reviewed code"


def test_the_pull_request_is_told_which_jobs_were_rerun_and_why(on_the_worker):
    """Criterion A's comment, after the re-run and from its answer (lesson §9): it names the
    checks the forge SAID it re-ran — here `build`, not `lint`, whose run the forge did not
    re-run — says no changed file appears in their failing log, and carries no card id.

    Red on main: no comment is made."""
    forge = _Forge(checks=RED_BUILD + [{"name": "lint", "bucket": "fail", "blocking": True,
                                        "kind": "code"}], reran=["build"])
    on_the_worker(forge)
    acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001
    assert len(forge.comments) == 1, f"the pull request was told {len(forge.comments)} time(s)"
    said = forge.comments[0]
    assert forge.events.index("rerun") < forge.events.index("comment"), (
        "the comment was posted before the forge answered the re-run")
    assert "build" in said, f"the comment does not name the re-run check: {said}"
    assert "lint" not in said, f"the comment names a check the forge did not re-run: {said}"
    assert WHY in said.lower(), f"the comment does not say why it re-ran: {said}"
    assert "#12" not in said, "a card id reached the pull request"


@pytest.mark.parametrize("door", DOORS)
@pytest.mark.parametrize("log", [
    pytest.param(f"FAILED {CHANGED}::test_total - AssertionError", id="the full relative path"),
    pytest.param(f"  File \"/home/runner/work/x/x/{CHANGED}\", line 12, in total",
                 id="the path inside an absolute runner path"),
    pytest.param("D:\\a\\x\\x\\src\\billing\\invoice.py(12): error", id="a Windows runner path"),
    pytest.param("invoice.py:12: AssertionError: 3 != 4", id="the basename with its extension"),
])
def test_a_failing_log_that_names_a_changed_file_launches_the_agent(on_the_worker, door, log):
    """A REVERSE GUARD for criterion A: a log that names what the pull request changed is the
    change's own failure, and the agent is launched as before, with no re-run and no comment.

    Green on main by design (main always launches). The cut "every log reads as unrelated"
    (`log_names_the_change` answers False) turns it red."""
    forge = _Forge(log=log)
    agents = on_the_worker(forge, door=door)
    acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001
    assert len(agents) == 1, f"no agent was launched on the change's own failure: {forge.events}"
    assert forge.reruns == 0 and forge.comments == []


@pytest.mark.parametrize("changed,log,related", [
    pytest.param("a.py", "FAILED tests/data.py::test_load - KeyError", False,
                 id="a.py is not data.py"),
    pytest.param("a.py", "./a.py:3: SyntaxError", True, id="./a.py:3 names a.py"),
    pytest.param(CHANGED, "AssertionError: the invoice total was 3, not 4", False,
                 id="the stem alone is not the file"),
])
def test_a_short_basename_is_matched_as_a_file_not_as_a_substring(on_the_worker, changed, log,
                                                                 related):
    """Criterion A, how a file is recognised in a log: a basename with its extension, preceded by
    a character that cannot be part of a path. `a.py` is a suffix of `data.py` and is not that
    file; `invoice` is the stem of `invoice.py` and is any word in a sentence.

    Red on main for the two unrelated cases (no re-run; main launches the agent). The cut "the
    stem is matched instead of the basename" turns the third red."""
    forge = _Forge(log=log, diff=_diff_of(changed))
    agents = on_the_worker(forge)
    acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001
    if related:
        assert len(agents) == 1 and forge.reruns == 0, f"{log!r} was not read as naming {changed}"
    else:
        assert agents == [] and forge.reruns == 1, f"{log!r} was read as naming {changed}"


def test_a_diff_that_could_not_be_read_is_not_read_as_unrelated(on_the_worker):
    """Lesson §2: `pr_diff` answers `None` when it could not read the diff. "Could not see the
    change" is not "the change touches nothing in the log"; the agent is launched as before.

    Green on main by design. The cut "`changed_paths` answers `[]` for `None`" turns it red."""
    forge = _Forge(diff=None)
    agents = on_the_worker(forge)
    acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001
    assert agents == [UNRELATED] and forge.reruns == 0


def test_a_cut_diff_is_not_read_as_unrelated(on_the_worker):
    """Lesson §2: a diff cut by `base.truncated` names only the files before the cut; the file the
    log names may be past it. A cut diff is "could not see all of it", and the agent is launched.

    Green on main by design. The cut "the marker check removed" turns it red."""
    whole = _diff_of(CHANGED, *(f"src/generated/part_{n}.py" for n in range(40)))
    cut = base.truncated(whole, len(DIFF))
    assert cut != whole, "the diff was not cut: the premise is not set up"
    forge = _Forge(diff=cut)
    agents = on_the_worker(forge)
    acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001
    assert agents == [UNRELATED] and forge.reruns == 0


def test_a_second_attempt_on_the_same_head_launches_the_agent(on_the_worker):
    """PO answer Q1(b): the re-run stands in for the agent once per head, on the first attempt.
    A wrong "unrelated" (the commonest real regression: changed `invoice_totals.ts`, failing
    `checkout.spec.ts`) then costs one CI re-run, not the whole repair budget (#258 review item 5).

    Green on main by design. The cut "the once-per-head bound removed" turns it red."""
    forge = _Forge()
    agents = on_the_worker(forge)
    acts._run_ci_repair(SECOND, "run-r2")  # noqa: SLF001
    assert agents == [UNRELATED], "the second attempt did not reach an agent"
    assert forge.reruns == 0, "a re-run stood in for the agent a second time on the same head"


def test_a_retried_attempt_after_a_rerun_launches_nothing_while_the_checks_run_again(
        on_the_worker):
    """The engine may retry `repair_ci` (`_RETRY_REATTACHING`) after the re-run went through. The
    checks then read pending, so the #184 gate answers "nothing to repair": no second re-run and
    no agent on the same attempt.

    Red on main for its first half: the first call launches the agent and re-runs nothing."""
    forge = _Forge(after_rerun=PENDING_BUILD)
    agents = on_the_worker(forge)
    acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001
    again = acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001 — the engine's retry
    assert forge.reruns == 1 and agents == [], f"{forge.events}, agents {agents}"
    assert again.state is JobState.PR_OPEN and again.code_changed is False


# ═══ C: bounded by the watch's existing cap ═════════════════════════════════════════════════════

def test_one_attempt_never_reruns_twice(on_the_worker):
    """The pre-launch re-run returns before any agent, so a pass that changed nothing — and with
    it the post-pass re-run of criterion B — cannot follow it in the same attempt.

    Red on main: no re-run at all (and the agent runs)."""
    forge = _Forge()
    agents = on_the_worker(forge, changed=False)
    acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001
    assert forge.reruns == 1, f"one attempt re-ran {forge.reruns} time(s): {forge.events}"
    assert agents == []


TQ = "test-an-unrelated-red-check-is-rerun"


@pytest.fixture
async def env():
    e = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    try:
        yield e
    finally:
        await e.shutdown()


async def _start(client: Client) -> WorkflowHandle:
    return await client.start_workflow(
        JobWorkflow.run,
        JobParams(project="p", issue="12", promote=False, merge_deadline_days=3650),
        id=f"wf-{uuid.uuid4()}", task_queue=TQ)


async def _wait_for_park(h: WorkflowHandle, env: WorkflowEnvironment) -> dict:
    """The park, waited for on the engine's clock: the watch rests `_CI_POLL` (two minutes)
    after each attempt, so the clock is moved a minute at a time, never past an hour."""
    for _ in range(60):
        parked = await h.query(JobWorkflow.awaiting_action)
        if parked:
            return parked
        await env.sleep(timedelta(minutes=1))
    raise AssertionError("the job never parked after its repair attempts")


@pytest.mark.owns_its_engine
async def test_reruns_are_counted_against_the_repair_cap_and_the_card_still_parks(
        env, on_the_worker):
    """Criterion C and PO answer Q2, on the real `JobWorkflow` and a real (time-skipping) engine:
    the watch reads a red build every time, and its `repair_ci` is the activity's own body
    (`_run_ci_repair`) over a forge that stays red. Attempt 1 re-runs (no agent), attempt 2
    launches the agent, and the card parks after `_CI_REPAIR_MAX` attempts with the same sentence
    and the same cause as before: the re-run spent an attempt, the cap did not grow.

    Red on main: no re-run ever happens, both attempts launch an agent."""
    forge = _Forge()
    agents = on_the_worker(forge)
    attempts: list[int] = []

    @activity.defn(name="repair_ci")
    async def repair_ci(inp: CiRepairInput) -> RunResult:
        attempts.append(inp.attempt)
        return acts._run_ci_repair(inp, f"run-r{inp.attempt}")  # noqa: SLF001

    red = decide([Check(name="build", bucket="fail", blocking=True, kind="code",
                        evidence=UNRELATED)])
    watch._reset(red, open_for=99)  # noqa: SLF001 — the watch's own recorders
    mocks = [m for m in watch.MOCKS if m is not watch.mock_repair] + [repair_ci]
    async with Worker(env.client, task_queue=TQ, workflows=[JobWorkflow], activities=mocks):
        h = await _start(env.client)
        parked = await _wait_for_park(h, env)

    assert attempts == list(range(1, wf._CI_REPAIR_MAX + 1)), attempts  # noqa: SLF001
    assert forge.reruns == 1, f"{forge.reruns} re-run(s) over {len(attempts)} attempts"
    assert len(agents) == 1, f"{len(agents)} agent pass(es) over {len(attempts)} attempts"
    assert forge.reruns + len(agents) <= wf._CI_REPAIR_MAX  # noqa: SLF001
    assert f"CI still failing after {wf._CI_REPAIR_MAX} repair attempt(s)" in parked["note"]  # noqa: SLF001
    assert parked["cause"] == CAUSE_CODE, f"the park lost its cause: {parked}"


# ═══ E: no clock of its own ═════════════════════════════════════════════════════════════════════

def test_the_rerun_waits_on_no_clock_of_its_own(on_the_worker, monkeypatch):
    """Criterion E. Any wait for re-runs to settle belongs to `adapters/sandbox/timeouts.py`, and
    the watch already rests `_CI_POLL` before it reads the checks again. The re-run path is driven
    with both sleeps raising: it must re-run and return without touching either.

    Red on main: the re-run path does not exist, so "the re-run happened" fails."""
    def no_clock(*_a, **_k):
        raise AssertionError("the re-run path waited on a clock of its own")

    monkeypatch.setattr(time, "sleep", no_clock)
    monkeypatch.setattr(asyncio, "sleep", no_clock)
    forge = _Forge()
    on_the_worker(forge)
    got = acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001
    assert forge.reruns == 1 and got.state is JobState.PR_OPEN


# ═══ F: #184's property holds ═══════════════════════════════════════════════════════════════════

def test_an_empty_log_is_held_for_a_person_and_never_read_as_unrelated(on_the_worker):
    """Criterion F, a PRESERVATION GUARD. An empty failing log names no changed file — and is not
    evidence that the failure is unrelated: it is no evidence at all. The #184 gate decides
    first, holds the pull request for a person, and nothing is re-run or launched.

    Green on main by design (the gate holds). The cut "the rule is asked before the gate" turns
    it red."""
    forge = _Forge(log="")
    agents = on_the_worker(forge)
    got = acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001
    assert got.state is JobState.ON_HOLD and got.merge_refused is True
    assert forge.reruns == 0 and agents == [] and forge.comments == []


@pytest.mark.parametrize("why", [
    pytest.param("related", id="the log names a changed file"),
    pytest.param("refused", id="the re-run was refused"),
])
def test_the_agent_is_handed_the_log_the_decision_was_made_from(on_the_worker, why):
    """Criterion F: whichever way the agent is reached, it is handed the gate's own evidence, and
    the forge's log is read exactly once. A second read could come back different, or empty,
    after the decision to launch was taken (#184).

    Green on main by design (main reads once and hands the evidence on). The cut "the agent is
    handed `forge.failed_ci_logs(...)` after a refused re-run" turns the refused case red."""
    first = f"FAILED {CHANGED}::test_total" if why == "related" else UNRELATED
    forge = _Forge(log=[first, "a second read, after the decision"],
                   reran=RuntimeError("HTTP 403: Resource not accessible by integration"))
    agents = on_the_worker(forge)
    acts._run_ci_repair(FIRST, "run-r1")  # noqa: SLF001
    assert agents == [first], f"the agent was handed {agents}, not the gate's log"
    assert forge.log_reads == 1, f"the failing log was read {forge.log_reads} times"
