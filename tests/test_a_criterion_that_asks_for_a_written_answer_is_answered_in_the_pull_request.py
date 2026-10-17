"""A card criterion that asks the agent to report something is answered in the pull request (#627).

THE FIELD REPORT'S CARD 82 (docs/field-reports/2026-10-some2dgame-run.md, C4): "Say in the card
result which root causes you found". The executor found them and said so in its final message —
which reached the 200-character journal note and nothing else. The reviewer, handed only the
ticket, the diff and the gates (ADR-0001 D-5), could not find the answer in the diff and marked
the criterion failed. The criterion could never be satisfied.

Decided with the maintainer, on #447's precedent: the answer is published under
`AGENT_ACCOUNT_HEADING`, which the reviewer is not shown; every reviewer is told so
(`WRITTEN_ANSWER_RULE`), marks such a criterion `unknown` rather than `failed`, and the card reads
NOT VERIFIED — a person reads the answer at the merge. Every agent pass is told where its final
message is published.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import test_walking_skeleton as spine
from test_agent_harness import _ctx, _FakeSandbox, _ws

from openfactory.adapters.agent import roles
from openfactory.adapters.agent.codex import CodexAdapter
from openfactory.adapters.reviewer import base as reviewer_base
from openfactory.adapters.reviewer import harness
from openfactory.adapters.reviewer.base import ReviewInput
from openfactory.adapters.reviewer.claude_code import ClaudeCodeReviewer
from openfactory.contracts import (
    AcceptanceCheck,
    AcceptanceCriterion,
    AgentRunResult,
    Manifest,
    ReviewResult,
    RunResult,
    Ticket,
    ValidationResult,
)
from openfactory.contracts import run as run_contract
from openfactory.orchestrator.machine import JobRunner
from openfactory.review.evidence import settle

repo = spine.repo

HEADING = getattr(run_contract, "AGENT_ACCOUNT_HEADING", "## What the agent says it did")
CRITERION = "Say in the card result which root causes you found"
ROOT_CAUSES = ("Root cause 1: the sprite atlas was loaded twice on resize.\n"
               "Root cause 2: the collision grid kept stale cells after a level reload.")


def _card82() -> Ticket:
    return Ticket(id="#82", title="fix the flicker", objective="stop the flicker", repo="o/game",
                  acceptance_criteria=[AcceptanceCriterion(text="the flicker is gone"),
                                       AcceptanceCriterion(text=CRITERION)])


class _FindsRootCauses:
    def __init__(self) -> None:
        self.repairs = 0

    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        (workspace.path / "atlas.py").write_text("LOADED_ONCE = True\n")
        return AgentRunResult(ok=True, summary=f"Fixed the flicker.\n\n{ROOT_CAUSES}",
                              cost_usd=0.01)

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        self.repairs += 1
        (workspace.path / "lint_ok.txt").write_text("ok\n")
        return AgentRunResult(ok=True, summary="fixed the lint error", cost_usd=0.01)


def _section(body: str) -> str:
    assert HEADING in body, "the pull request carries no account of what the agent did"
    return body[body.index(HEADING):]


def _run(repo: Path, tmp_path: Path, validate: dict) -> tuple[str, _FindsRootCauses]:
    agent = _FindsRootCauses()
    runner = spine._runner(repo, spine.FakeTracker(_card82()), Manifest(validate=validate),
                           tmp_path, agent=agent)
    runner.run("#82")
    assert runner.forge.opened, "no pull request was opened — this guard is measuring nothing"
    return runner.forge.opened["body"], agent


def test_the_card_82_root_causes_reach_the_pull_request_under_the_agents_heading(
        repo: Path, tmp_path: Path):
    body, _ = _run(repo, tmp_path, {"test": "true", "security": "true"})

    section = _section(body)
    for line in ROOT_CAUSES.splitlines():
        assert f"> {line}" in section, f"{line!r} is not under {HEADING!r}"


def test_the_root_causes_survive_a_repair_pass_after_the_executor(repo: Path, tmp_path: Path):
    body, agent = _run(repo, tmp_path, {"test": "true", "lint": "test -f lint_ok.txt"})

    assert agent.repairs == 1, "no gate repair ran — this guard is measuring one pass"
    section = _section(body)
    for line in ROOT_CAUSES.splitlines():
        assert f"> {line}" in section, "a later pass replaced the executor's answer"
    rows = [r for r in section.splitlines() if "fixed the lint error" in r]
    assert len(rows) == 1 and rows[0].startswith("> - gate repair 1 · `"), rows


def _ri() -> ReviewInput:
    return ReviewInput(ticket=_card82(), diff="+LOADED_ONCE = True",
                       validations=[ValidationResult(name="test", command="true", exit_code=0,
                                                     passed=True)])


def test_every_reviewer_is_told_a_written_answer_is_in_that_section_and_is_not_a_failure():
    rule = getattr(reviewer_base, "WRITTEN_ANSWER_RULE", None)
    assert rule, "no reviewer is told where a written answer is"
    assert HEADING in rule and "`unknown`" in rule and "never `failed`" in rule, rule
    assert rule in harness.build_review_prompt(_ri()), "the harness reviewer is not told"
    assert rule in ClaudeCodeReviewer()._prompt(_ri()), "Claude Code's reviewer is not told"


def test_every_pass_is_told_its_final_message_is_published_under_that_heading():
    for role in ("executor", "recovery"):
        assert HEADING in roles.role_prompt(role), f"the {role} is not told where it is published"
    sb = _FakeSandbox(last_message="fixed")
    CodexAdapter(model="gpt-5").repair(sandbox=sb, workspace=_ws(), context=_ctx(),
                                       failure_log="pytest: 2 failed")
    assert HEADING in sb.commands[0], "a repair pass is not told where its message is published"


def test_a_written_answer_left_for_the_person_is_never_reported_as_a_criterion_not_met():
    validations = [ValidationResult(name="test", command="true", exit_code=0, passed=True)]
    review = settle(ReviewResult(
        decision="approved", score=88, summary="the flicker fix is right",
        acceptance=[
            AcceptanceCheck(criterion="the flicker is gone", status="passed",
                            evidence="gate:test — tests/test_atlas.py covers it"),
            AcceptanceCheck(criterion=CRITERION, status="unknown",
                            evidence=f"answered in the pull request under `{HEADING}`, which "
                                     f"the reviewer is not shown — a person reads it there")]),
        validations)
    result = RunResult(ticket_id="#82", state="validating", branch="openfactory/82",
                       validations=validations, review=review, total_cost_usd=0.02,
                       agent_account=ROOT_CAUSES, agent_account_chars=len(ROOT_CAUSES))
    holder = SimpleNamespace(manifest=Manifest(validate={"test": "true"}), _profile=None)
    body = JobRunner._pr_body(holder, _card82(), result)

    assert "NOT VERIFIED" in body, "an answer no gate ran was presented as verified"
    assert "criterion NOT met" not in body
    assert not [r for r in body.splitlines() if r.startswith("> - wire `")], (
        "the person is told to wire a written answer into a gate")
    for line in ROOT_CAUSES.splitlines():
        assert f"> {line}" in _section(body)
