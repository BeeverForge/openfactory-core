"""A later pass adds its own line under what the agent says it did, once, and never a second
heading (#627, criterion 3 — held as idempotence, decided with the maintainer).

The executor's account is the body of the section, and it is carried over from the body as it
stands: a CI repair or an adjust is a separate activity on a fresh runner, and nothing in memory
holds the first run's result — the body is the record `_republish_review` already amends in place
(#187 for the review, #310 for the `Cost:` line). Each later pass that PUSHED adds one line: its
kind, the head it pushed, and its own words on one line cut at 200 characters. The latest ten are
listed and the rest are counted, and the count accumulates across republishes.

Before this change a pull request had no such section, so none of these could hold.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import test_the_pull_request_says_what_the_card_says as card_says
import test_walking_skeleton as spine

from openfactory.contracts import (
    AgentRunResult,
    Finding,
    Manifest,
    ReviewResult,
    RunResult,
    ValidationResult,
)
from openfactory.contracts import run as run_contract
from openfactory.orchestrator.machine import _COST_LINE, JobRunner

repo = spine.repo

HEADING = getattr(run_contract, "AGENT_ACCOUNT_HEADING", "## What the agent says it did")
LABEL = "Later passes, oldest first"
EXECUTOR = "EXEC-SENTINEL: rewrote the parser\n\nRoot cause: the last byte was dropped."
PR = "https://forge/pr/1"


def _opened_body() -> str:
    """The body as the WRITER composes it when the pull request is opened."""
    result = RunResult(
        ticket_id="#9", state="validating", branch="openfactory/9",
        validations=[ValidationResult(name="test", command="true", exit_code=0, passed=True)],
        review=card_says.REJECTED, total_cost_usd=0.05,
        agent_account=EXECUTOR, agent_account_chars=len(EXECUTOR))
    holder = SimpleNamespace(manifest=Manifest(validate={"test": "true"}), _profile=None)
    return JobRunner._pr_body(holder, spine._sizing_ticket_id("#9"), result)


class _Says:
    """A pass that rewrites the pull request and ends with `words`, a different file every pass."""

    def __init__(self, *words: str) -> None:
        self.words, self.passes = list(words), 0

    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        return AgentRunResult(ok=True)

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        self.passes += 1
        (workspace.path / f"pass{self.passes}.py").write_text(f"PASS = {self.passes}\n")
        said = self.words[min(self.passes, len(self.words)) - 1]
        if said.startswith("WRITE "):  # the pass that makes the gate green
            (workspace.path / said.split()[1]).write_text("ok\n")
        return AgentRunResult(ok=True, summary=said, cost_usd=0.01)


class _Counting(spine.FakeForge):
    def __init__(self) -> None:
        super().__init__()
        self.reads = self.writes = 0

    def pr_body(self, *, pr: str, repo: str = "") -> str | None:
        self.reads += 1
        return super().pr_body(pr=pr, repo=repo)

    def set_pr_body(self, *, pr: str, body: str, repo: str = "") -> bool:
        self.writes += 1
        return super().set_pr_body(pr=pr, body=body, repo=repo)


def _runner(repo: Path, tmp_path: Path, agent, *, validate=None, reviewer=None, body=None,
            forge=None):
    forge = forge or spine.FakeForge()
    forge.opened = {"body": body if body is not None else _opened_body()}
    runner = spine._runner(repo, spine.FakeTracker(spine._sizing_ticket_id("#9")),
                           Manifest(validate=validate or {"test": "true"}), tmp_path,
                           agent=agent, reviewer=reviewer, forge=forge)
    return runner, forge


def _pushed(tmp_path: Path) -> str:
    """The head the forge holds — what the workspace pushed."""
    return subprocess.run(["git", "--git-dir", str(tmp_path / "origin.git"), "rev-parse",
                           "openfactory/9"], capture_output=True, text=True, check=True).stdout.strip()


def _rows(body: str) -> list[str]:
    rows = body.splitlines()
    assert HEADING in rows, "the pull request carries no account of what the agent did"
    start = rows.index(HEADING)
    end = next((i for i in range(len(rows) - 1, start, -1) if rows[i].startswith(_COST_LINE)),
               len(rows))
    return rows[start:end]


def _executor_part(body: str) -> list[str]:
    rows = _rows(body)
    end = next((i for i, r in enumerate(rows) if r.startswith(LABEL)), len(rows))
    while not rows[end - 1].strip():
        end -= 1
    return rows[:end]


def _pass_rows(body: str) -> list[str]:
    return [r for r in _rows(body) if r.startswith("> - ")]


# ── one line per pushed pass, under one heading ──────────────────────────────────────────────────

def test_a_later_pass_adds_one_line_and_never_a_second_heading(repo: Path, tmp_path: Path):
    card_says._pr_branch(repo)
    runner, forge = _runner(repo, tmp_path, _Says("first fix", "second fix"))

    runner.repair_ci("#9", "CI failed", pr_url=PR)
    runner.repair_ci("#9", "CI failed again", pr_url=PR)

    assert forge.opened["body"].count(HEADING) == 1
    assert len(_pass_rows(forge.opened["body"])) == 2, _rows(forge.opened["body"])


def test_an_adjust_pass_that_pushed_adds_its_line_and_keeps_the_executors_account_byte_for_byte(
        repo: Path, tmp_path: Path):
    card_says._pr_branch(repo)
    before = _opened_body()
    runner, forge = _runner(repo, tmp_path, _Says("ADJUST-B: made the button blue"), body=before)

    runner.repair_ci("#9", "make the button blue", pr_url=PR, human=True)

    after = forge.opened["body"]
    assert _executor_part(after) == _executor_part(before), "the executor's account was rewritten"
    assert _pass_rows(after) == [f"> - adjust · `{_pushed(tmp_path)[:12]}` — "
                                 f"ADJUST-B: made the button blue"], _rows(after)


def test_a_ci_repair_that_pushed_adds_its_line(repo: Path, tmp_path: Path):
    card_says._pr_branch(repo)
    runner, forge = _runner(repo, tmp_path, _Says("made test_x pass"))

    runner.repair_ci("#9", "CI failed: test_x", pr_url=PR)

    assert _pass_rows(forge.opened["body"]) == [
        f"> - CI repair · `{_pushed(tmp_path)[:12]}` — made test_x pass"]


def test_the_same_pass_republished_twice_adds_its_line_once(repo: Path, tmp_path: Path):
    passes = getattr(run_contract, "PassAccount", None)
    assert passes is not None, "there is no pass line to add"
    holder = _holder(_opened_body())
    once = passes(kind="adjust", words="did it", head="a" * 40)

    JobRunner._republish_review(holder, PR, account_passes=[once])
    JobRunner._republish_review(holder, PR, account_passes=[once])

    assert _pass_rows(holder.forge.body) == [f"> - adjust · `{'a' * 12}` — did it"]

    # and a pass that pushed nothing after one that did adds nothing
    card_says._pr_branch(repo)
    runner, forge = _runner(repo, tmp_path, _Says("a real fix"))
    runner.repair_ci("#9", "CI failed", pr_url=PR)
    runner.agent = card_says._Idle()
    runner.repair_ci("#9", "CI failed again", pr_url=PR)
    assert len(_pass_rows(forge.opened["body"])) == 1


def test_a_pass_that_pushed_nothing_adds_no_line(repo: Path, tmp_path: Path):
    card_says._pr_branch(repo)
    original = _opened_body()
    runner, forge = _runner(repo, tmp_path, card_says._Idle(), body=original)

    runner.repair_ci("#9", "CI failed", pr_url=PR)
    runner.repair_ci("#9", "make it blue", pr_url=PR, human=True)

    assert _rows(forge.opened["body"]) == _rows(original), "a pass that changed nothing added a line"

    # an adjust held by a red gate pushed nothing either
    held, forge = _runner(repo, tmp_path / "held", _Says("tried"), validate={"test": "false"},
                          body=original)
    held.repair_ci("#9", "make it blue", pr_url=PR, human=True)
    assert _rows(forge.opened["body"]) == _rows(original), "a held adjust added a line"


def test_every_later_pass_of_the_first_run_has_its_line_in_order(repo: Path, tmp_path: Path):
    class _Stops(_Says):
        def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
            (workspace.path / "feature.py").write_text("VALUE = 1\n")
            return AgentRunResult(ok=False, summary="ran out of turns")

    class _RejectsOnce:
        def __init__(self) -> None:
            self.seen = 0

        def review(self, *, sandbox, workspace, review_input) -> ReviewResult:
            self.seen += 1
            if self.seen == 1:
                return ReviewResult(decision="rejected", score=40, summary="one thing",
                                    findings=[Finding(severity="high", description="name it")])
            return card_says.APPROVED

    agent = _Stops("RECOVERED: finished it", "WRITE gate_ok.txt — the gate is green",
                   "REVIEWED: named it")
    manifest = Manifest(validate={"test": "test -f gate_ok.txt"}, review_mode="blocking")
    runner = spine._runner(repo, spine.FakeTracker(spine._sizing_ticket_id("#9")), manifest,
                           tmp_path, agent=agent, reviewer=_RejectsOnce())
    runner.run("#9")

    assert runner.forge.opened, "no pull request was opened — this guard is measuring nothing"
    kinds = [r.split(" · ")[0].split(" — ")[0][4:] for r in _pass_rows(runner.forge.opened["body"])]
    assert kinds == ["recovery 1", "gate repair 1", "review repair 1"], kinds


def test_each_gate_repair_after_an_adjust_has_its_line(repo: Path, tmp_path: Path):
    card_says._pr_branch(repo)
    runner, forge = _runner(repo, tmp_path, _Says("A2: moved the button", "WRITE adjust_ok.txt F"),
                            validate={"test": "test -f adjust_ok.txt"})

    runner.repair_ci("#9", "move the button", pr_url=PR, human=True)

    rows = _pass_rows(forge.opened["body"])
    assert len(rows) == 2 and rows[0].startswith("> - adjust · `"), rows
    assert rows[1].startswith("> - adjust gate repair 1 · `") and rows[1].endswith(
        "WRITE adjust_ok.txt F"), rows


def test_a_pass_line_is_its_own_words_on_one_line_cut_at_200_characters(
        repo: Path, tmp_path: Path):
    words = "\n".join(f"line {i:03d} " + "w" * 80 for i in range(10))  # about 900 characters
    card_says._pr_branch(repo)
    runner, forge = _runner(repo, tmp_path, _Says(words))

    runner.repair_ci("#9", "CI failed", pr_url=PR)

    (row,) = _pass_rows(forge.opened["body"])
    said = row.split(" — ", 1)[1]
    assert said == " ".join(words.split())[:200] + "…", said


def test_only_the_latest_ten_passes_are_listed_and_the_rest_are_counted():
    passes = getattr(run_contract, "PassAccount", None)
    assert passes is not None, "there is no pass line to add"
    holder = _holder(_opened_body())
    for i in range(1, 14):
        JobRunner._republish_review(holder, PR, account_passes=[
            passes(kind="CI repair", words=f"pass {i}", head=f"{i:012x}" + "0" * 28)])

    rows = _pass_rows(holder.forge.body)
    assert [r.rsplit(" — ", 1)[1] for r in rows] == [f"pass {i}" for i in range(4, 14)]
    assert "3 earlier passes are not shown." in _rows(holder.forge.body)

    JobRunner._republish_review(holder, PR, account_passes=[
        passes(kind="CI repair", words="pass 14", head=f"{14:012x}" + "0" * 28)])
    assert "4 earlier passes are not shown." in _rows(holder.forge.body), (
        "the count of earlier passes does not accumulate across republishes")


def test_a_dated_review_does_not_stamp_the_account_as_past(repo: Path, tmp_path: Path):
    card_says._pr_branch(repo)
    runner, forge = _runner(repo, tmp_path, _Says("fixed it"))

    runner.repair_ci("#9", "CI failed", pr_url=PR)

    body = forge.opened["body"]
    assert card_says.CAVEAT in body, "the review was not dated — wrong case"
    assert not [r for r in _rows(body) if card_says.WAS in r]


def test_a_pull_request_opened_before_the_section_existed_gains_exactly_one(
        repo: Path, tmp_path: Path):
    card_says._pr_branch(repo)
    old = card_says._body_with_review() + "\n\nCost: $0.0500"
    runner, forge = _runner(repo, tmp_path, _Says("fixed it"), body=old)

    runner.repair_ci("#9", "CI failed", pr_url=PR)

    body = forge.opened["body"]
    assert body.count(HEADING) == 1
    rows = body.splitlines()
    assert rows[-1].startswith(_COST_LINE) and rows.index(HEADING) < len(rows) - 1
    section = _rows(body)
    assert any("was not recorded" in r for r in section), section
    assert not [r for r in section if r.startswith("> ") and not r.startswith("> - ")]
    assert len(_pass_rows(body)) == 1


def test_the_account_and_the_cost_line_move_in_one_write(repo: Path, tmp_path: Path):
    card_says._pr_branch(repo)
    runner, forge = _runner(repo, tmp_path, _Says("fixed it"), reviewer=card_says._Reviewer(),
                            forge=_Counting())

    runner.repair_ci("#9", "CI failed", pr_url=PR)

    assert len(_pass_rows(forge.opened["body"])) == 1, "the pass's line never landed"
    assert (forge.reads, forge.writes) == (1, 1), (forge.reads, forge.writes)


class _Forge:
    def __init__(self, body: str) -> None:
        self.body = body

    def pr_body(self, *, pr: str, repo: str = "") -> str | None:
        return self.body

    def set_pr_body(self, *, pr: str, body: str, repo: str = "") -> bool:
        self.body = body
        return True


def _holder(body: str):
    return SimpleNamespace(forge=_Forge(body), _cost_on_the_pr=0.0, _reported_cost=lambda: None)
