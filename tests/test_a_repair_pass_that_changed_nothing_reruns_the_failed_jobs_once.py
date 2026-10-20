"""#756 (criterion B) — a repair pass that changed nothing re-runs the failed jobs once.

WHAT IT COST. An agent handed a red check its change does not explain finds nothing to change,
and says so by pushing nothing (`RunResult.code_changed is False`, measured on the checkout by
`machine.repair_ci`'s `as_left`). The watch then rested `_CI_POLL` and read the same red result off
the same run: nothing had asked the forge to run the checks again, so the next attempt was a
second paid pass on an unchanged head, and `_CI_REPAIR_MAX` parked the card. After such a pass the
failed jobs are re-run once, through the forge's seam (`base.rerun_failed_of`), and the pull
request is told which (PO answer Q4), besides the result's note and the worker log. A re-run the
forge refuses is said on the pull request too (PO answer Q3).

    B  a pass that answered `PR_OPEN` with `code_changed is False` — on either door, the inline
       runner and a remote box, whose result carries the field across (`boxed_job._emit` dumps the
       whole `RunResult`) — re-runs the failed jobs exactly once, and says so on the pull request
       and in the note. Nothing else re-runs: a pass that changed the code (the push re-runs the
       checks), one whose change could not be measured (lesson §2: "could not see" is not
       "nothing changed"), one that held, paused or failed, a person's adjust pass (#68: its
       words are not a red build), and a forge that cannot re-run, which says nothing.

ON MAIN (9a421ae, the tests alone) the rows that expect a re-run, a comment, a warning or a note
are red: `_run_ci_repair` returns the pass's result as it came. The rows that expect nothing are
green there BY DESIGN, and each names the cut in
`tools/mutations/756_an_unrelated_red_check_is_rerun_not_repaired.py` that turns it red.

Every input passes `attempt=2`, so the pre-launch re-run (criterion A, once per head) never stands
in for the pass: the agent runs and the post-pass move is the only one in play.
"""

from __future__ import annotations

import logging

import pytest

from openfactory.adapters.forge import base
from openfactory.contracts import JobState, RunResult
from openfactory.runtime.temporal import activities as acts
from tests import test_a_red_check_the_diff_does_not_touch_is_rerun_before_an_agent_is_paid as pre

#: the worker's seams and the typed red forge, borrowed rather than rebuilt (function-scoped)
on_the_worker = pre.on_the_worker
SECOND = pre.SECOND
PR = pre.PR
DOORS = pre.DOORS
#: what the comment says about why: the repair pass changed nothing
WHY = "changed nothing"
REFUSAL = "HTTP 403: Resource not accessible by integration"


class _Forge(pre._Forge):  # noqa: SLF001
    """The typed red forge, which also notes how many agent passes had run when it was asked to
    re-run: a post-pass re-run is asked AFTER the pass, never instead of it."""

    agents: list | None = None
    passes_before_rerun: list[int]

    def rerun_failed(self, *, pr):
        self.passes_before_rerun = [*getattr(self, "passes_before_rerun", []),
                                    len(self.agents or [])]
        return super().rerun_failed(pr=pr)




# ═══ B: a pass that changed nothing re-runs once, and says so ═══════════════════════════════════

@pytest.mark.parametrize("door", DOORS)
def test_a_pass_that_changed_nothing_reruns_the_failed_jobs_once(on_the_worker, door):
    """Criterion B, the issue itself, on both doors: the agent ran and pushed nothing, so the
    failed jobs are re-run exactly once, after the pass. The pass's own result goes back to the
    watch (`PR_OPEN`, `code_changed=False`, the reviewer's verdict still standing), its note
    naming what was re-run.

    Red on main: the pass's result is returned as it came, and `rerun_failed` is never called."""
    forge = _Forge()
    forge.agents = on_the_worker(forge, door=door, changed=False)
    got = acts._run_ci_repair(SECOND, "run-r2")  # noqa: SLF001 — the activity's own body
    assert forge.reruns == 1, f"a pass that changed nothing re-ran {forge.reruns} time(s)"
    assert forge.passes_before_rerun == [1], (
        f"the re-run was not asked after the pass: {forge.passes_before_rerun}")
    assert got.state is JobState.PR_OPEN and got.pr_url == PR
    assert got.code_changed is False, "the re-run was reported as a change to the reviewed code"
    assert "build" in (got.note or ""), f"the note does not say what was re-run: {got.note!r}"


def test_the_pull_request_is_told_which_jobs_were_rerun_after_a_pass_that_changed_nothing(
        on_the_worker):
    """PO answer Q4: the post-pass re-run is said on the pull request, after the forge answered and
    from its answer (lesson §9): it names `build`, which the forge re-ran, not `lint`, which it did
    not; says the repair pass changed nothing; carries no card id.

    Red on main: no comment is made."""
    forge = _Forge(checks=pre.RED_BUILD + [{"name": "lint", "bucket": "fail", "blocking": True,
                                            "kind": "code"}], reran=["build"])
    forge.agents = on_the_worker(forge, changed=False)
    acts._run_ci_repair(SECOND, "run-r2")  # noqa: SLF001
    assert len(forge.comments) == 1, f"the pull request was told {len(forge.comments)} time(s)"
    said = forge.comments[0]
    assert forge.events.index("rerun") < forge.events.index("comment"), (
        "the comment was posted before the forge answered the re-run")
    assert "build" in said, f"the comment does not name the re-run check: {said}"
    assert "lint" not in said, f"the comment names a check the forge did not re-run: {said}"
    assert WHY in said.lower(), f"the comment does not say why it re-ran: {said}"
    assert "#12" not in said, "a card id reached the pull request"


def test_a_refused_rerun_after_a_pass_is_said_and_the_pass_stands(on_the_worker, caplog):
    """PO answer Q3, after the pass: a re-run the forge refuses is a warning in the worker log, a
    comment on the pull request in the forge's words, and a line in the note. The pass's result is
    otherwise the one it answered: nothing is retried, nothing else is launched.

    Red on main: no warning, no comment."""
    forge = _Forge(reran=base.RerunRefused(REFUSAL))
    forge.agents = on_the_worker(forge, changed=False)
    with caplog.at_level(logging.WARNING):
        got = acts._run_ci_repair(SECOND, "run-r2")  # noqa: SLF001
    warned = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(REFUSAL in w for w in warned), f"no warning names the refusal: {warned}"
    assert len(forge.comments) == 1 and REFUSAL in forge.comments[0], (
        f"the pull request was not told the re-run was refused: {forge.comments}")
    assert "#12" not in forge.comments[0], "a card id reached the pull request"
    assert REFUSAL in (got.note or ""), f"the note does not say why nothing was re-run: {got.note!r}"
    assert got.state is JobState.PR_OPEN and got.code_changed is False
    assert len(forge.agents) == 1, "a refused re-run launched another pass"


def test_nothing_to_rerun_after_a_pass_is_said_in_the_note(on_the_worker):
    """The forge was asked and found no failed job of this pull request to re-run (`[]`: the check
    finished green since, or its run lives where the forge cannot reach it). Nothing was refused
    and nothing was re-run, so the pull request is not told; the note says why not.

    Red on main: the note is the pass's own."""
    forge = _Forge(reran=[])
    forge.agents = on_the_worker(forge, changed=False)
    got = acts._run_ci_repair(SECOND, "run-r2")  # noqa: SLF001
    assert forge.reruns == 1 and forge.comments == []
    assert "re-run" in (got.note or ""), f"the note does not say why nothing was re-run: {got.note!r}"


# ═══ B, the reverse guards: nothing else re-runs ════════════════════════════════════════════════

@pytest.mark.parametrize("door", DOORS)
def test_a_pass_that_changed_the_code_reruns_nothing(on_the_worker, door):
    """A pass that pushed: the forge runs the checks on the new head by itself, and a re-run of the
    old head's failed jobs would be a red reading of code that is no longer there.

    Green on main by design. The cut "the post-pass condition dropped (any `PR_OPEN` re-runs)"
    turns it red."""
    forge = _Forge()
    forge.agents = on_the_worker(forge, door=door, changed=True)
    got = acts._run_ci_repair(SECOND, "run-r2")  # noqa: SLF001
    assert forge.reruns == 0 and forge.comments == [], forge.events
    assert got.note in (None, ""), f"the pass's note was rewritten: {got.note!r}"


@pytest.mark.parametrize("door", DOORS)
def test_a_pass_whose_change_could_not_be_measured_reruns_nothing(on_the_worker, door):
    """Lesson §2: `code_changed is None` is "could not see whether the pass changed the pull
    request", not "it changed nothing". It may have pushed; nothing is re-run.

    Green on main by design. The cut "`code_changed is not True`" turns it red."""
    forge = _Forge()
    forge.agents = on_the_worker(forge, door=door, changed=None)
    acts._run_ci_repair(SECOND, "run-r2")  # noqa: SLF001
    assert forge.reruns == 0 and forge.comments == [], forge.events


@pytest.mark.parametrize("door", DOORS)
@pytest.mark.parametrize("state", [JobState.ON_HOLD, JobState.PAUSED, JobState.FAILED])
def test_a_pass_that_held_or_paused_reruns_nothing(on_the_worker, door, state):
    """A pass that held for a person, paused on a usage limit, or failed did not answer "I looked
    and there was nothing to change": it is the watch's to settle, with the checks as they are.

    Green on main by design. The cut "the `PR_OPEN` condition dropped" turns it red."""
    forge = _Forge()
    forge.agents = on_the_worker(forge, door=door, changed=False, state=state)
    got = acts._run_ci_repair(SECOND, "run-r2")  # noqa: SLF001
    assert forge.reruns == 0 and forge.comments == [], forge.events
    assert got.state is state


@pytest.mark.parametrize("door", DOORS)
def test_a_persons_adjust_pass_never_reruns_ci(on_the_worker, door):
    """#68: an adjust pass carries a person's words (`ci_log=`), not a red build. It may change
    nothing because the person asked for nothing the code lacked; that says nothing about the
    checks, which may be green.

    Green on main by design. The cut "the post-pass condition drops `not human`" turns it red."""
    forge = _Forge()
    forge.agents = on_the_worker(forge, door=door, changed=False)
    acts._run_ci_repair(SECOND, "run-r2", ci_log="please rename the helper")  # noqa: SLF001
    assert len(forge.agents) == 1, "the adjust pass did not run"
    assert forge.reruns == 0 and forge.comments == [], forge.events


def test_a_forge_that_cannot_rerun_says_nothing_after_a_pass(on_the_worker):
    """Criterion D after the pass: Azure Repos, the local forge, every add-on declare no
    `rerun_failed`. The pass's result goes back exactly as it came — no comment, no note.

    Green on main by design. The cut "`rerun_failed_of` accepts any truthy answer" is held by
    `test_rerunning_failed_jobs_is_a_capability_a_forge_declares.py`; here the cut "a missing
    capability is written in the note" turns it red."""

    class _Plain(_Forge):
        rerun_failed = None

    forge = _Plain()
    forge.agents = on_the_worker(forge, changed=False)
    got = acts._run_ci_repair(SECOND, "run-r2")  # noqa: SLF001
    assert forge.comments == [], forge.comments
    assert got.note in (None, ""), f"the pass's note was rewritten: {got.note!r}"


def test_a_forge_that_cannot_be_built_after_a_pass_returns_the_pass():
    """The pass is done when the forge is built for its re-run. A forge that cannot be built (an
    App token that failed to mint) is caught there, and the pass's result goes back as it came:
    a missing re-run is not the pass's price, and it never escapes the repair activity.

    Added in review round 1: the cut "the forge built after a pass is not caught" survived the
    first 59 rows, because every row's forge could be built."""
    passed = RunResult(ticket_id="12", state=JobState.PR_OPEN, pr_url=PR, code_changed=False)

    def no_forge():
        raise RuntimeError("the App token could not be minted")

    got = acts._rerun_after_a_pass_that_changed_nothing(  # noqa: SLF001
        no_forge, SECOND, passed, human=False)
    assert got is passed
