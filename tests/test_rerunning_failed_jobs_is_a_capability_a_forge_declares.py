"""#756 (criterion D) — re-running a pull request's failed jobs is a capability a forge DECLARES.

WHAT IT COST. A blocking check red for a reason no changed file touches (a flaky integration
test, a busy shared environment) was handed to a paid agent pass. The agent changed nothing, the
next attempt failed the same way, and `_CI_REPAIR_MAX` parked the card. The cheaper move is to
re-run the failed jobs. #258's first attempt did that by calling the GitHub CLI from the repair
activity, and its review set the constraint these cases hold: the move goes through an optional
forge seam, `base.rerun_failed_of(forge, pr)`, which generic code calls and only a row that can
re-run answers. Every other forge, add-on and test double is repaired as it always was.

    the seam      `rerun_failed_of`: no capability → None; an answer → the names re-run; a
                  refusal → `RerunRefused`, as a value; a test double is never a success
    the activity  no capability → the agent, as before, with the gate's own log; a refusal → the
                  agent, a warning naming why, and the pull request told (PO answer Q3)
    GitHub        `gh run rerun <id> --failed --repo <own repository>`, once per run that a red
                  blocking `code` row links to: the runs `failed_ci_logs` reads, and no other
    the core      `openfactory/runtime/**` never reaches `gh` itself, and the registered
                  `repair_ci` activity reaches the seam through both of its moves

ON MAIN (9a421ae) 15 of these 17 cases are red: the seam does not exist (`AttributeError` on
`base.rerun_failed_of` / `base.RerunRefused`), `GitHubForge` has no `rerun_failed`, and
`repair_ci` reaches no re-run. The AST guard and its self-check are green there by design (nothing calls a forge CLI from the core yet); the mutation plan
`tools/mutations/756_an_unrelated_red_check_is_rerun_not_repaired.py` writes
`forge._gh(["run", "rerun", ...])` into `activities.py` to turn it red.
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from openfactory.adapters.forge import base
from openfactory.adapters.forge.azure_devops import AzureReposForge
from openfactory.adapters.forge.github import GitHubForge
from openfactory.adapters.forge.local import LocalForge
from openfactory.contracts import JobState, RunResult
from openfactory.runtime.temporal import activities as acts
from openfactory.runtime.temporal.io import CiRepairInput

ROOT = Path(__file__).resolve().parents[1]

PR = "https://github.com/acme/x/pull/2"
#: A failing log that names no file the diff below changes: the shape the issue describes.
LOG = "FAILED tests/integration/test_queue.py::test_it - TimeoutError: broker did not answer"
DIFF = ("diff --git a/src/billing/invoice.py b/src/billing/invoice.py\n"
        "--- a/src/billing/invoice.py\n+++ b/src/billing/invoice.py\n@@ -1 +1 @@\n-a\n+b\n")
RED_BUILD = [{"name": "build", "bucket": "fail", "blocking": True, "kind": "code",
              "url": "https://github.com/acme/x/actions/runs/1/job/7"}]
#: What `gh` answers when the App lacks `Actions: write`, as the refusal a row hands on.
REFUSAL = "HTTP 403: Resource not accessible by integration"


# ═══ the seam ═══════════════════════════════════════════════════════════════════════════════════

def test_a_forge_without_the_capability_is_answered_none():
    """No `rerun_failed` on the row: the honest answer is an absence, not "re-ran nothing"."""
    assert base.rerun_failed_of(SimpleNamespace(), PR) is None
    assert base.rerun_failed_of(SimpleNamespace(rerun_failed="yes"), PR) is None


def test_a_row_that_reran_answers_the_names_of_the_checks_it_reran():
    asked: list[str] = []

    def rerun_failed(*, pr):
        asked.append(pr)
        return ["build"]

    assert base.rerun_failed_of(SimpleNamespace(rerun_failed=rerun_failed), PR) == ["build"]
    assert asked == [PR]


@pytest.mark.parametrize("answer", [
    pytest.param(lambda: MagicMock(), id="a mock"),
    pytest.param(lambda: "build", id="a string"),
    pytest.param(lambda: [MagicMock()], id="a list of mocks"),
    pytest.param(lambda: [1], id="a list of numbers"),
])
def test_a_test_double_is_not_a_declaration(answer):
    """A `MagicMock` answers every attribute with a callable mock. If the seam took a truthy answer
    for success, every double in the suite would claim a re-run that never happened, and the
    repair would comment on it and launch no agent. Only a list of check names is a success."""
    assert not isinstance(base.rerun_failed_of(MagicMock(), PR), list)
    got = base.rerun_failed_of(SimpleNamespace(rerun_failed=lambda *, pr: answer()), PR)
    assert not isinstance(got, list), f"{got!r} was read as the names of re-run checks"


@pytest.mark.parametrize("raised", [
    pytest.param(lambda: base.RerunRefused(REFUSAL), id="a refusal the row names"),
    pytest.param(lambda: RuntimeError(REFUSAL), id="any other exception"),
])
def test_a_rerun_the_forge_refuses_is_handed_on_as_a_value_naming_why(raised):
    """A refusal (a 403, a run still in progress) is "could not", never "nothing to re-run"
    (lesson §2). It comes back as a value that carries the forge's words, so the caller can say
    them to a person without a `try` of its own."""
    def rerun_failed(*, pr):
        raise raised()

    got = base.rerun_failed_of(SimpleNamespace(rerun_failed=rerun_failed), PR)
    assert isinstance(got, base.RerunRefused) and REFUSAL in str(got)


# ═══ the activity: without the capability, or refused, the agent runs as before ════════════════

class _Forge:
    """A typed forge with a red blocking build and a log that names no changed file."""

    checks_are_typed = True

    def __init__(self):
        self.diff_reads = 0
        self.comments: list[str] = []

    def pr_checks(self, *, pr):
        return RED_BUILD

    def failed_ci_logs(self, *, pr):
        return LOG

    def pr_diff(self, *, pr, **_kw):
        self.diff_reads += 1
        return DIFF

    def review_pr(self, *, pr, event, body):
        assert event == "comment"
        self.comments.append(body)


class _Refusing(_Forge):
    def rerun_failed(self, *, pr):
        raise RuntimeError(REFUSAL)


@pytest.fixture
def on_the_worker(monkeypatch):
    """The worker's seams, shaped as in `test_the_repair_brief_states_the_failure_it_was_given`:
    a project, its forge, and an inline runner that records the log each agent pass is given."""
    ran: list[str] = []
    project = SimpleNamespace(name="p")
    monkeypatch.setattr(acts, "ProjectRegistry", lambda: SimpleNamespace(get=lambda _n: project))
    monkeypatch.setattr(acts, "_ref_repo", lambda _p, _i: ("acme/x", ""))
    monkeypatch.setattr(acts, "_runner_view", lambda _p, _i: (project, ""))
    monkeypatch.setattr(acts, "_resolved_image", lambda _p, sandbox: "")
    monkeypatch.setattr(acts, "installed_box_traits", lambda _s: SimpleNamespace(remote=False))

    def runner(*a, **kw):
        def repair_ci(issue, ci_log, pr_url="", human=False):
            ran.append(ci_log)
            return RunResult(ticket_id=issue, state=JobState.PR_OPEN, pr_url=pr_url,
                             code_changed=True)
        return SimpleNamespace(repair_ci=repair_ci)

    monkeypatch.setattr(acts, "build_runner", runner)

    def use(forge):
        monkeypatch.setattr(acts, "_forge_for", lambda _p: forge)
        return ran
    return use


#: The first repair attempt on this head (the workflow counts from 1): the one attempt where the
#: PO's answer to Q1 lets a re-run stand in for the agent.
FIRST = CiRepairInput(project="p", issue="12", pr_url=PR, sandbox="worktree", attempt=1)


def test_a_forge_without_the_capability_gets_the_agent_as_before(on_the_worker):
    """Azure DevOps, the local forge and every add-on today: the repair is the one it was — the
    agent, handed the log the decision was made from (#184), no comment, and the diff never read
    (the capability is asked first, so no forge pays a read for a move it cannot make).

    Green on main apart from its premise: the seam the premise asks does not exist there. The
    mutation that reads `pr_diff` before the capability turns the `diff_reads` line red."""
    forge = _Forge()
    assert base.rerun_failed_of(forge, PR) is None
    ran = on_the_worker(forge)
    got = acts._run_ci_repair(FIRST)  # noqa: SLF001 — the activity's own body
    assert ran == [LOG], "the agent was not handed the gate's own log"
    assert got.state is JobState.PR_OPEN
    assert forge.comments == [], "a forge with no re-run was told about one"
    assert forge.diff_reads == 0, "the diff was read for a move this forge cannot make"


def test_a_refused_rerun_falls_through_to_the_agent_and_says_why(on_the_worker, caplog):
    """The rule says "unrelated" (the log names `tests/integration/test_queue.py`, the diff
    changes `src/billing/invoice.py`) and it is the first attempt, so a re-run is asked — and the
    forge refuses. The repair must not stop there: the agent runs with the gate's log, the worker
    log carries the forge's words, and (PO answer Q3) the pull request is told that the re-run was
    refused and that an agent was launched instead.

    Red on main: there is no re-run, so nothing names the refusal."""
    forge = _Refusing()
    ran = on_the_worker(forge)
    with caplog.at_level(logging.WARNING):
        got = acts._run_ci_repair(FIRST)  # noqa: SLF001
    assert ran == [LOG], "a refused re-run did not fall through to the agent with the gate's log"
    assert got.state is JobState.PR_OPEN
    warned = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(REFUSAL in w for w in warned), f"no warning names the refusal: {warned}"
    told = [c for c in forge.comments if REFUSAL in c]
    assert told, f"the pull request was not told the re-run was refused: {forge.comments}"
    assert "agent" in told[0].lower(), f"the comment does not say an agent ran instead: {told[0]}"
    assert "#12" not in told[0], "a card id reached the pull request"


# ═══ GitHub: the runs its red required checks link to, and only those ══════════════════════════

def _github(monkeypatch, all_checks, required, *, rerun_exit=0, rerun_stderr=""):
    """A real `GitHubForge` whose `gh` answers from these rows and records every argv
    (the shape of `test_a_failing_check_is_read_for_what_it_is.py::_github`)."""
    f = GitHubForge("acme/x")
    calls: list[list[str]] = []

    def gh(args, timeout=120):
        calls.append(list(args))
        out = SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:2] == ["pr", "checks"]:
            if "--required" in args:
                out.stdout = json.dumps([{"name": n, "bucket": "fail"} for n in required])
            else:
                out.stdout = json.dumps(all_checks)
        elif args[:2] == ["run", "rerun"]:
            out.returncode, out.stderr = rerun_exit, rerun_stderr
        elif args[:2] == ["run", "view"]:
            # Every run's failing log reads, as on a real red run; the rows below that need an
            # unreadable or empty log override this one call.
            out.stdout = f"FAIL in run {args[2]}\n"
        return out

    monkeypatch.setattr(f, "_gh", gh)
    f.calls = calls
    return f


def _row(name, bucket, *, workflow="ci", link=""):
    return {"name": name, "bucket": bucket, "state": bucket.upper(), "workflow": workflow,
            "link": link}


def _reruns(f) -> list[list[str]]:
    return [c for c in f.calls if c[:2] == ["run", "rerun"]]


def test_github_reruns_the_failed_jobs_of_the_runs_its_red_required_checks_link_to(monkeypatch):
    """The rows `failed_ci_logs` reads its log from — blocking, about the code, failed or
    cancelled — and no other: an advisory workflow, a status another app posted, a passing run.
    Two red jobs of one run are one re-run of that run's failed jobs. A status whose link is a run
    of this repository is still not a check about the code, and is not re-run."""
    runs = "https://github.com/acme/x/actions/runs"
    f = _github(monkeypatch, [
        _row("pytest", "fail", link=f"{runs}/1/job/7"),
        _row("lint", "fail", link=f"{runs}/1/job/8"),              # same run as pytest
        # A commit status (no workflow, so not about the code) whose link is a run of this
        # repository, as a status-posting action leaves it: only `kind` tells it from a build.
        # It stands before `unit` so that, were it chosen, it would be one of the two runs read.
        _row("deploy/preview", "fail", workflow="", link=f"{runs}/6/job/1"),
        _row("unit", "cancel", link=f"{runs}/5/job/2"),
        _row("e2e", "fail", link=f"{runs}/3/job/1"),               # advisory
        _row("license/cla", "fail", workflow="", link="https://cla.example/2"),  # another app
        _row("build", "pass", link=f"{runs}/4/job/1"),
    ], ["pytest", "lint", "unit", "license/cla", "deploy/preview", "build"])
    got = f.rerun_failed(pr=PR)
    assert sorted(_reruns(f)) == [["run", "rerun", "1", "--failed", "--repo", "acme/x"],
                                  ["run", "rerun", "5", "--failed", "--repo", "acme/x"]]
    assert sorted(got) == ["lint", "pytest", "unit"]


def test_github_a_run_of_another_repository_is_not_rerun(monkeypatch):
    """C-18, as `failed_ci_logs` reads its runs: `gh run` does not resolve a URL, so the runs are
    asked of the repository the pull request names, and a link to another repository's run —
    here the forge's own default one — is not this pull request's check."""
    f = _github(monkeypatch, [
        _row("pytest", "fail", link="https://github.com/acme/api/actions/runs/1/job/7"),
        _row("build", "fail", link="https://github.com/acme/x/actions/runs/2/job/3"),
    ], ["pytest", "build"])
    got = f.rerun_failed(pr="https://github.com/acme/api/pull/9")
    assert _reruns(f) == [["run", "rerun", "1", "--failed", "--repo", "acme/api"]]
    assert got == ["pytest"]


def test_github_a_rerun_gh_refuses_is_a_refusal_naming_why(monkeypatch):
    """`gh run rerun` exits non-zero (no `Actions: write`, a run still in progress): that is a
    refusal carrying gh's own words, never `[]` ("asked, and nothing was re-runnable")."""
    f = _github(monkeypatch, [_row("pytest", "fail",
                                   link="https://github.com/acme/x/actions/runs/1/job/7")],
                ["pytest"], rerun_exit=1, rerun_stderr=REFUSAL)
    got = base.rerun_failed_of(f, PR)
    assert isinstance(got, base.RerunRefused) and REFUSAL in str(got)


def test_github_checks_it_could_not_read_are_a_refusal_not_nothing(monkeypatch):
    """Lesson §2: `pr_checks` that raises is "could not see which runs failed", not "no run
    failed". It is a refusal naming why, so the pull request is told (PO answer Q3) and the agent
    runs; `[]` would launch the agent in silence.

    Added in review round 1: the cut "unreadable checks answer `[]`" survived the first 59 rows."""
    f = _github(monkeypatch, [], [])

    def unreadable(*, pr):
        raise RuntimeError("gh pr checks failed: HTTP 502")

    monkeypatch.setattr(f, "pr_checks", unreadable)
    got = base.rerun_failed_of(f, PR)
    assert isinstance(got, base.RerunRefused), f"unreadable checks answered {got!r}"
    assert "could not be read" in str(got) and "HTTP 502" in str(got)


def test_github_one_run_refused_of_two_is_a_refusal_naming_both(monkeypatch):
    """Two red runs, the first re-run, the second refused with gh's measured words for a run
    still in progress: the answer is a refusal (not every failed job re-ran) that names the run
    gh refused AND the check that did re-run, so neither half is lost (lesson §9).

    Added in review round 1: the cut "a partial refusal is answered as a success" survived."""
    runs = "https://github.com/acme/x/actions/runs"
    f = _github(monkeypatch, [_row("pytest", "fail", link=f"{runs}/1/job/7"),
                              _row("e2e", "fail", link=f"{runs}/2/job/1")], ["pytest", "e2e"])
    real = f._gh  # noqa: SLF001

    def gh(args, timeout=120):
        out = real(args, timeout)
        if args[:3] == ["run", "rerun", "2"]:
            out.returncode, out.stderr = 1, "run 2 cannot be rerun; This workflow is already running"
        return out

    monkeypatch.setattr(f, "_gh", gh)
    got = base.rerun_failed_of(f, PR)
    assert isinstance(got, base.RerunRefused), f"a partial refusal answered {got!r}"
    assert "run 2" in str(got) and "already running" in str(got) and "pytest" in str(got)
    assert sorted(c[2] for c in _reruns(f)) == ["1", "2"], "a run was not asked"


def test_github_reruns_only_the_runs_whose_logs_the_decision_read(monkeypatch):
    """Three red required runs: the repair decides from the log `failed_ci_logs` reads, so the
    re-run asks exactly the runs that log was read from, and a third run whose log nobody read
    stays red for the next attempt's agent (one selection, `_failing_runs`, for both).

    Added in the human round, 2026-10-20: on d33f056 the log read runs 1 and 2 and the re-run
    asked runs 1, 2 and 3 (measured with three red code runs and `gh` stubbed)."""
    runs = "https://github.com/acme/x/actions/runs"
    f = _github(monkeypatch, [_row(f"c{i}", "fail", link=f"{runs}/{i}/job/9") for i in (1, 2, 3)],
                ["c1", "c2", "c3"])
    f.failed_ci_logs(pr=PR)
    read = [c[2] for c in f.calls if c[:2] == ["run", "view"]]
    got = f.rerun_failed(pr=PR)
    assert [c[2] for c in _reruns(f)] == read == ["1", "2"], (
        f"logs read of runs {read}, re-ran runs {[c[2] for c in _reruns(f)]}")
    assert got == ["c1", "c2"]


def test_github_names_the_red_checks_it_left_past_the_runs_read(monkeypatch):
    """Three red required runs: `c1` and `c2` are re-run, and the answer also names `c3`, whose run
    is past the two whose logs were read, as left red. It is not a refusal: refusing would launch
    the agent at once on `c1` and `c2`'s logs, which name no changed file.

    Added in the human round, 2026-10-20 (re-review on c4f591b): `c3` was dropped in silence, so
    neither the pull request nor the note could name it."""
    runs = "https://github.com/acme/x/actions/runs"
    f = _github(monkeypatch, [_row(f"c{i}", "fail", link=f"{runs}/{i}/job/9") for i in (1, 2, 3)],
                ["c1", "c2", "c3"])
    got = base.rerun_failed_of(f, PR)
    assert got == ["c1", "c2"], f"answered {got!r}"
    assert getattr(got, "left", None) == ["c3"], (
        f"the check left past the runs read is not named: {getattr(got, 'left', None)!r}")


def test_a_row_answering_a_plain_list_leaves_no_check_unnamed():
    """A row that answers only the names it re-ran (a test double, an add-on) is read as having
    left nothing past a bound, so the caller reads `left` off every success alike."""
    got = base.rerun_failed_of(SimpleNamespace(rerun_failed=lambda *, pr: ["build"]), PR)
    assert got == ["build"] and getattr(got, "left", None) == [], f"answered {got!r}"


def test_github_logs_none_of_which_read_are_no_log(monkeypatch):
    """No selected run's failing log reads: the log is empty (the #184 gate holds for a person),
    never a placeholder standing in for a log nobody read.

    Added in the human round, 2026-10-20: the re-review on c4f591b found the cut "an unread run
    adds `LOG`" survived every row."""
    runs = "https://github.com/acme/x/actions/runs"
    f = _github(monkeypatch, [_row("pytest", "fail", link=f"{runs}/1/job/7"),
                              _row("e2e", "fail", link=f"{runs}/2/job/1")], ["pytest", "e2e"])
    real = f._gh  # noqa: SLF001

    def gh(args, timeout=120):
        out = real(args, timeout)
        if args[:2] == ["run", "view"]:
            out.returncode, out.stdout, out.stderr = 1, "", "HTTP 404: Not Found"
        return out

    monkeypatch.setattr(f, "_gh", gh)
    assert f.failed_ci_logs(pr=PR) == ""
    assert sorted(c[2] for c in f.calls if c[:2] == ["run", "view"]) == ["1", "2"], f.calls


#: The two ways `gh run view <id> --log-failed` gives the repair no log of a run: it exits
#: non-zero (the run's logs expired or are not yet archived, a 404, a rate limit), or exits zero
#: with nothing on stdout. `failed_ci_logs` skips the run either way.
_NO_LOG = [pytest.param(1, "HTTP 404: Not Found", id="the read fails"),
           pytest.param(0, "", id="the read comes back empty")]


def _second_log_unread(monkeypatch, exit_code, stderr):
    """Two red required runs, run 1's failing log read and run 2's not."""
    runs = "https://github.com/acme/x/actions/runs"
    f = _github(monkeypatch, [_row("pytest", "fail", link=f"{runs}/1/job/7"),
                              _row("e2e", "fail", link=f"{runs}/2/job/1")], ["pytest", "e2e"])
    real = f._gh  # noqa: SLF001

    def gh(args, timeout=120):
        out = real(args, timeout)
        if args[:3] == ["run", "view", "2"]:
            out.returncode, out.stdout, out.stderr = exit_code, "", stderr
        return out

    monkeypatch.setattr(f, "_gh", gh)
    return f


@pytest.mark.parametrize(("exit_code", "stderr"), _NO_LOG)
def test_github_never_reruns_a_run_whose_failing_log_was_not_read(monkeypatch, exit_code, stderr):
    """The repair decides from the failing log `failed_ci_logs` reads, and that read skips a run
    whose `gh run view --log-failed` fails or comes back empty. Such a run was never judged
    unrelated, so it is not re-run: it stays red for the agent.

    Added in the human round, 2026-10-20: on 28e9226 run 2's log was not read (gh exit 1, or exit
    0 with nothing) and `rerun_failed` still asked `gh run rerun 2 --failed`."""
    f = _second_log_unread(monkeypatch, exit_code, stderr)
    assert "FAIL in run 1" in f.failed_ci_logs(pr=PR) and "run 2" not in f.failed_ci_logs(pr=PR)
    base.rerun_failed_of(f, PR)
    assert [c[2] for c in _reruns(f)] == ["1"], (
        f"re-ran runs {[c[2] for c in _reruns(f)]}; the log was read of run 1 only")


@pytest.mark.parametrize(("exit_code", "stderr"), _NO_LOG)
def test_github_a_run_left_unread_is_a_refusal_naming_it(monkeypatch, exit_code, stderr):
    """Not every failed job was re-run, so the answer is a refusal (PO answer Q3: said on the
    pull request, and the agent runs), naming the run left out and why, and the check that did
    re-run (lesson §9), never a success that hides run 2 or `[]`.

    Added in the human round, 2026-10-20: on 28e9226 the answer was `['pytest', 'e2e']`."""
    f = _second_log_unread(monkeypatch, exit_code, stderr)
    got = base.rerun_failed_of(f, PR)
    assert isinstance(got, base.RerunRefused), f"a run whose log was not read answered {got!r}"
    why = "could not be read (HTTP 404: Not Found)" if exit_code else "was empty"
    assert "run 2" in str(got) and why in str(got) and "re-ran pytest" in str(got), str(got)


def test_only_rows_that_can_rerun_declare_it():
    """GitHub Actions re-runs a run's failed jobs; Azure DevOps (until a real organisation proves
    its retry, a follow-up) and the local forge declare nothing, and are repaired as before."""
    assert callable(getattr(GitHubForge, "rerun_failed", None))
    assert getattr(AzureReposForge, "rerun_failed", None) is None
    assert getattr(LocalForge, "rerun_failed", None) is None


# ═══ the core never reaches a forge's CLI ═══════════════════════════════════════════════════════

_CLI_SEAMS = {"_gh", "_gh_read"}


def _reaches_a_forge_cli(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _CLI_SEAMS:
            found.append(f"line {node.lineno}: .{node.attr}")
        elif isinstance(node, ast.Call):
            for arg in node.args[:1]:
                if (isinstance(arg, (ast.List, ast.Tuple)) and arg.elts
                        and isinstance(arg.elts[0], ast.Constant) and arg.elts[0].value == "gh"):
                    found.append(f"line {node.lineno}: an argv beginning \"gh\"")
    return found


def test_the_guard_sees_a_forge_cli_call():
    """The guard below reads the parsed code, so it is asked here that it can see what it bans."""
    assert _reaches_a_forge_cli(ast.parse('forge._gh(["run", "rerun", "1"])'))
    assert _reaches_a_forge_cli(ast.parse('subprocess.run(["gh", "run", "rerun", "1"])'))
    assert not _reaches_a_forge_cli(ast.parse('rerun_failed_of(forge, pr)'))


def test_generic_code_never_reaches_a_forge_cli():
    """#258 review items 3 and 8: the re-run goes through the forge's row, never `gh` from the
    core. Green on main by design (no caller yet); the mutation plan writes `forge._gh([...])`
    into the repair activity to turn it red."""
    offenders = {}
    for path in sorted((ROOT / "openfactory" / "runtime").rglob("*.py")):
        hits = _reaches_a_forge_cli(ast.parse(path.read_text(encoding="utf-8")))
        if hits:
            offenders[str(path.relative_to(ROOT))] = hits
    assert offenders == {}, f"the core reaches a forge CLI itself: {offenders}"


# ═══ the seam is reached from the activity the worker runs ══════════════════════════════════════

_BOTH_MOVES = ("_rerun_what_the_change_does_not_touch", "_rerun_after_a_pass_that_changed_nothing")


def test_the_rerun_is_reached_from_the_repair_activity():
    """Lesson §1: a capability every test calls and nothing in production reaches is the defect
    this repository has met twelve times (`tests/test_loops_are_reachable.py`). The re-run must be
    reached from `repair_ci`, the activity the workflow's CI loop calls, through EACH of its two
    moves (before an agent is launched, and after a pass that changed nothing), and that activity
    must be registered on the worker. On main (9a421ae) `rerun_failed_of` and both moves do not
    exist, so nothing reaches them.

    The graph is name-based and stops at the seam: `rerun_failed_of` asks the row with
    `getattr(forge, "rerun_failed")`, which no call edge shows. That last link is held by
    `tests/test_auto_merge_is_judged_from_the_gates_that_were_read.py::
    test_no_capability_is_asked_of_a_forge_row_that_no_shipped_row_declares` and by
    `test_only_rows_that_can_rerun_declare_it` above."""
    from openfactory.runtime.temporal.worker import WORKER_ACTIVITIES
    from tests.test_loops_are_reachable import _call_graph, _reachable_from

    assert acts.repair_ci in WORKER_ACTIVITIES, "repair_ci is not registered on the worker"
    edges, _ = _call_graph()
    from_the_activity = _reachable_from(edges, {"repair_ci"})
    unreached = [move for move in _BOTH_MOVES if move not in from_the_activity]
    assert unreached == [], f"repair_ci never reaches {unreached}"
    stops_short = [move for move in _BOTH_MOVES
                   if "rerun_failed_of" not in _reachable_from(edges, {move})]
    assert stops_short == [], f"{stops_short} never ask the forge to re-run anything"
