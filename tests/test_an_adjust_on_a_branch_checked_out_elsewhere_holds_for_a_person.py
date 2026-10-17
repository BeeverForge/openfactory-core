"""#623 — a pass that continues a pull request holds for a person when its branch is out elsewhere.

FIELD REPORT (`docs/field-reports/2026-10-some2dgame-run.md` §A2, card 28, 2026-10-09): the
operator reviewed the pull request in a scratch `git worktree` of `openfactory/28`, pressed
*adjust*, and the pass failed with git's "already used by worktree" sentence, which left
`JobRunner.repair_ci` as a `RuntimeError` and came back as `job errored after retries`.

WHAT IS PROVEN HERE, on a real repository with a bare origin, the worktree box, and a person's
review tree of the pull request's branch in the same clone: every door of the machine that
checks out a card's branch (`repair_ci` for a person's adjust and for a check's repair, `run`
resuming a paused attempt, `review_pr`) returns a hold for a person whose note names that tree, with
`hold_cause == TREE`, and launches no agent. Once the tree is removed, the same adjust runs and
pushes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from openfactory.contracts import AgentRunResult, JobState, Manifest
from openfactory.contracts.bot import BotIdentity
from openfactory.techlead.classify import TREE
from tests.test_walking_skeleton import (
    FakeForge,
    FakeReviewer,
    FakeTracker,
    _git,
    _runner,
    _sizing_ticket_id,
    repo,  # noqa: F401 — the fixture: a real repository with a bare origin to push to
)

PR = "https://forge/pr/1"
ASKED = "put the button on the right"
BRANCH = "openfactory/9"
OWNER = "ana"


class _Agent:
    """Writes the change it was asked for, and records that it was asked at all."""

    def __init__(self):
        self.calls = 0

    def repair(self, *, sandbox, workspace, context, failure_log):
        self.calls += 1
        (Path(workspace.path) / "button.py").write_text("SIDE = 'right'\n")
        return AgentRunResult(ok=True, summary="moved it", cost_usd=0.01, actions=[])

    def execute(self, *, sandbox, workspace, context):  # pragma: no cover — must not run
        self.calls += 1
        raise AssertionError("no agent may run on a branch another tree holds")


class _CountingReviewer(FakeReviewer):
    def __init__(self):
        self.calls = 0

    def review(self, *, sandbox, workspace, review_input):
        self.calls += 1
        return super().review(sandbox=sandbox, workspace=workspace, review_input=review_input)


def _on_the_forge(repo: Path) -> str:  # noqa: F811
    return subprocess.run(
        ["git", "--git-dir", str(repo.parent / "origin.git"), "rev-parse", BRANCH],
        check=True, capture_output=True, text=True).stdout.strip()


def _an_open_pull_request_a_person_reviews(repo: Path) -> Path:  # noqa: F811
    """The pull request's branch on the forge, and the person's review tree of it in their clone.
    The path holds a space, as a person's may."""
    _git(["checkout", "-b", BRANCH], repo)
    (repo / "feature.py").write_text("x = 1\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "the first pass"], repo)
    _git(["push", "-u", "origin", BRANCH], repo)
    _git(["checkout", "main"], repo)
    review = repo.parent / "review tree"
    _git(["worktree", "add", str(review), BRANCH], repo)
    return review.resolve()


def _machine(repo: Path, tmp_path: Path, agent, reviewer=None):  # noqa: F811
    tracker = FakeTracker(_sizing_ticket_id("#9"), assignees=[OWNER, "openfactory-bot"])
    runner = _runner(repo, tracker, Manifest(validate={"test": "true"}), tmp_path, agent=agent,
                     forge=FakeForge(), reviewer=reviewer,
                     bot=BotIdentity(login="openfactory-bot"))
    return runner, tracker


def _held_for_a_person(got, tracker, review: Path) -> None:
    assert got.state is JobState.ON_HOLD
    assert got.hold_cause == TREE
    assert str(review) in got.note
    assert any(str(review) in c for c in tracker.comments)
    assert tracker.assign_history[-1] == [OWNER]


def test_an_adjust_pass_on_a_held_branch_holds_and_launches_no_agent(repo, tmp_path):  # noqa: F811
    review = _an_open_pull_request_a_person_reviews(repo)
    first = _on_the_forge(repo)
    agent = _Agent()
    runner, tracker = _machine(repo, tmp_path, agent)

    got = runner.repair_ci("#9", ASKED, pr_url=PR, human=True)

    _held_for_a_person(got, tracker, review)
    assert got.merge_refused is True and got.code_changed is False
    assert agent.calls == 0
    assert _on_the_forge(repo) == first


def test_a_ci_repair_on_a_held_branch_holds_too(repo, tmp_path):  # noqa: F811
    review = _an_open_pull_request_a_person_reviews(repo)
    agent = _Agent()
    runner, tracker = _machine(repo, tmp_path, agent)

    got = runner.repair_ci("#9", "test_button FAILED", pr_url=PR, human=False)

    _held_for_a_person(got, tracker, review)
    assert got.merge_refused is True and got.code_changed is False
    assert agent.calls == 0


def test_a_resumed_attempt_on_a_held_branch_holds_and_keeps_its_handle(repo, tmp_path):  # noqa: F811
    review = _an_open_pull_request_a_person_reviews(repo)
    agent = _Agent()
    runner, tracker = _machine(repo, tmp_path, agent)

    got = runner.run("#9", resume_handle="h1")

    _held_for_a_person(got, tracker, review)
    # the next resume still continues the paused attempt (ADR-0012/0013 D1)
    assert got.resume_handle == "h1"
    assert agent.calls == 0


def test_a_re_review_on_a_held_branch_holds(repo, tmp_path):  # noqa: F811
    review = _an_open_pull_request_a_person_reviews(repo)
    reviewer = _CountingReviewer()
    runner, tracker = _machine(repo, tmp_path, _Agent(), reviewer=reviewer)

    got = runner.review_pr("#9", pr_url=PR)

    _held_for_a_person(got, tracker, review)
    assert got.merge_refused is True and got.code_changed is False
    assert reviewer.calls == 0


def test_once_freed_the_same_adjust_runs_and_pushes(repo, tmp_path):  # noqa: F811
    review = _an_open_pull_request_a_person_reviews(repo)
    first = _on_the_forge(repo)
    agent = _Agent()
    runner, _ = _machine(repo, tmp_path, agent)
    assert runner.repair_ci("#9", ASKED, pr_url=PR, human=True).state is JobState.ON_HOLD

    _git(["worktree", "remove", str(review)], repo)
    got = runner.repair_ci("#9", ASKED, pr_url=PR, human=True)

    assert got.state is JobState.PR_OPEN and got.code_changed is True
    assert agent.calls == 1
    assert _on_the_forge(repo) != first
