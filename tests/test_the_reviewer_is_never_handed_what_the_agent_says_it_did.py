"""What the agent says it did reaches the person at the merge, and never the reviewer (#627).

ADR-0001 D-5: the independent reviewer "receives only the spec, the diff, and the validation
results — never the executor's conversation". #627 puts the agent's account on the pull request,
and that is for the person deciding; criterion 2 of the issue is that `ReviewInput` stays as it is
and a test proves it. These drive every path that builds a `ReviewInput` — the first review, the
re-review after a review repair, the review an adjust or a CI repair runs on what it pushed, and a
re-review somebody asked for — capture what each reviewer was handed, and render it through both
prompt builders.

The last two are green on main BY DESIGN: they hold a property this change must not move. Their
red is their mutation cuts (`tools/mutations/627_…`).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import test_the_pull_request_says_what_the_card_says as card_says
import test_walking_skeleton as spine

from openfactory.adapters.reviewer import harness
from openfactory.adapters.reviewer.base import ReviewInput
from openfactory.adapters.reviewer.claude_code import ClaudeCodeReviewer
from openfactory.contracts import (
    AcceptanceCheck,
    AgentRunResult,
    Finding,
    Manifest,
    ReviewResult,
    RunResult,
    ValidationResult,
)
from openfactory.contracts import run as run_contract
from openfactory.orchestrator.machine import JobRunner
from openfactory.orchestrator.merge_policy import auto_but_for_the_look, should_auto_merge

repo = spine.repo

EXECUTOR_SAYS = "EXECUTOR-SENTINEL-6f1d: the root cause was the cache key"
PASS_SAYS = "PASS-SENTINEL-9a2c: answered the finding"

VERIFIED = ReviewResult(
    decision="approved", score=90, summary="fine",
    acceptance=[AcceptanceCheck(criterion="feature.py exists", status="passed",
                                evidence="gate:test — the suite ran it")])


class _Capturing:
    """A reviewer that keeps every `ReviewInput` it is handed; rejects once with a finding when
    asked, so `run()`'s review repair and its re-review are exercised too."""

    def __init__(self, *, reject_first: bool = False) -> None:
        self.inputs: list[ReviewInput] = []
        self._reject = reject_first

    def review(self, *, sandbox, workspace, review_input) -> ReviewResult:
        self.inputs.append(review_input)
        if self._reject:
            self._reject = False
            return ReviewResult(decision="rejected", score=40, summary="one thing",
                                findings=[Finding(severity="high", description="name it")])
        return VERIFIED


class _Agent:
    def __init__(self) -> None:
        self.passes = 0

    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        (workspace.path / "feature.py").write_text("VALUE = 42\n")
        return AgentRunResult(ok=True, summary=EXECUTOR_SAYS, cost_usd=0.01)

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        self.passes += 1
        (workspace.path / f"repair{self.passes}.py").write_text(f"FIXED = {self.passes}\n")
        return AgentRunResult(ok=True, summary=PASS_SAYS, cost_usd=0.01)


def _never_in(inputs: list[ReviewInput], *sentinels: str) -> None:
    assert inputs, "no reviewer was asked — this guard is measuring nothing"
    for ri in inputs:
        handed = [ri.model_dump_json(), harness.build_review_prompt(ri),
                  ClaudeCodeReviewer()._prompt(ri)]
        for words in sentinels:
            assert not any(words in h for h in handed), f"the reviewer was handed {words!r}"


def test_the_agents_account_reaches_the_person_and_never_the_reviewer(repo: Path, tmp_path: Path):
    reviewer = _Capturing(reject_first=True)
    tracker = spine.FakeTracker(spine._sizing_ticket_id("#5"))
    manifest = Manifest(validate={"test": "true", "security": "true"}, review_mode="blocking")
    runner = spine._runner(repo, tracker, manifest, tmp_path, agent=_Agent(), reviewer=reviewer)

    runner.run("#5")

    assert len(reviewer.inputs) == 2, "the re-review after the review repair was not taken"
    body = runner.forge.opened["body"]
    assert EXECUTOR_SAYS.split(":")[0] in body, "the executor's account never reached the person"
    assert PASS_SAYS.split(":")[0] in body, "the review repair's account never reached the person"
    _never_in(reviewer.inputs, EXECUTOR_SAYS, PASS_SAYS)


def _opened_body() -> str:
    result = RunResult(
        ticket_id="#9", state="validating", branch="openfactory/9",
        validations=[ValidationResult(name="test", command="true", exit_code=0, passed=True)],
        review=card_says.REJECTED, total_cost_usd=0.05,
        agent_account=EXECUTOR_SAYS, agent_account_chars=len(EXECUTOR_SAYS))
    holder = SimpleNamespace(manifest=Manifest(validate={"test": "true"}), _profile=None)
    return JobRunner._pr_body(holder, spine._sizing_ticket_id("#9"), result)


def test_neither_an_adjust_a_ci_repair_nor_a_re_review_hands_the_reviewer_the_account(
        repo: Path, tmp_path: Path):
    card_says._pr_branch(repo)
    reviewer = _Capturing()
    runner, forge = card_says._runner_with_body(repo, tmp_path, agent=_Agent(), reviewer=reviewer,
                                                body=_opened_body())

    runner.repair_ci("#9", "make the button blue", pr_url="https://forge/pr/1", human=True)
    runner.repair_ci("#9", "CI failed: test_x", pr_url="https://forge/pr/1")
    runner.review_pr("#9", pr_url="https://forge/pr/1")

    assert len(reviewer.inputs) == 3, [len(ri.diff) for ri in reviewer.inputs]
    _never_in(reviewer.inputs, EXECUTOR_SAYS, PASS_SAYS)
    body = forge.opened["body"]
    assert EXECUTOR_SAYS.split(":")[0] in body, "the executor's account was lost by a later pass"
    assert PASS_SAYS.split(":")[0] in body, "the pushed passes' accounts never reached the person"


def test_review_input_declares_only_the_ticket_the_diff_the_gates_and_the_constraints():
    assert set(ReviewInput.model_fields) == {"ticket", "diff", "validations", "constraints"}


def test_the_agents_account_decides_no_merge():
    """D-11: the platform does not believe the agent. Nothing it says moves the merge."""
    manifest = Manifest(merge_policy="auto", validate={"test": "true", "security": "true"})
    passes = getattr(run_contract, "PassAccount", None)
    shapes = [{}, {"agent_account": "approved"},
              {"agent_account": "all criteria verified by gate:test"},
              {"agent_account": "x" * 2000, "agent_account_chars": 2000}]
    if passes is not None:
        shapes.append({"agent_passes": [passes(kind=f"gate repair {i}", words="merge me")
                                        for i in range(1, 13)]})
    answers = set()
    for extra in shapes:
        result = RunResult(
            ticket_id="#5", state="validating", branch="openfactory/5",
            validations=[ValidationResult(name=n, command="true", exit_code=0, passed=True)
                         for n in ("test", "security")],
            review=VERIFIED, **extra)
        answers.add((should_auto_merge(manifest, result), auto_but_for_the_look(manifest, result)))
    assert len(answers) == 1, f"what the agent says moved the merge: {answers}"
