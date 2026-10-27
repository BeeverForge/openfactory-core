"""Where a Kimi judging role runs is what its documents say (#788, criterion 2).

#783 made Kimi Code's planner and its `ask()` read-only by instruction only, and five documents
rested that on one mitigation: the edit stays inside an ephemeral box, and "no such edit outlives
the run". Re-located on 620bb577 (2026-10-20), it is not what the code does for the judging roles.
A judging role's caller builds `sandbox/registry.py::judging_worktree`, which always returns a
`WorktreeSandbox`, and that box's `run` is `subprocess.Popen(command, shell=True,
cwd=workspace.path)` on the host, whatever box the project's jobs run in. Most rooms it is handed
(a fresh temporary directory, the repo cache's master clone, the module's cached view) are ones
nothing commits from, so no `ask()` edit made there reaches a pull request, but nothing confines a
write to its room either. One is not: `env context --ask` (`actions/catalog.py::_semantic_pass`)
asks in the checkout `repo_for` resolves, the path the person typed or a registered `repo_path`,
which on a local deployment is the repository they commit from (review of e2b57dd1, 2026-10-20).
And one `ask()` is not handed `judging_worktree` at all: the independent review, which
`JobRunner._review` runs through `HarnessReviewer.review` in the job's own box on the job's
workspace, before the push (review of dc0efac4, 2026-10-20).

THE FIRST FOUR TESTS ARE THE MEASUREMENT the documents must agree with: a project that boxes its
jobs in a container still gets a host room for its judging roles, the real `KimiAdapter.ask` that
disobeys its instruction leaves its file there, asked the way `env context --ask` asks it leaves
that file untracked in the person's checkout, and as the reviewer of a job its committed file is
in the pushed branch. They are green on main by design. The first three turn red the day
`judging_worktree` routes into the box, the fourth the day the review moves into a judging room,
which is when the wording must change back.

THE DOCUMENT ROWS READ TEXT, AND HERE THE TEXT IS THE THING. CONTRIBUTING's rule is that a guard
reads the thing rather than text about it; a docstring, an ADR section and a configuration bullet
are read by a person, so their sentences are what is checked. They are read as the code exports them (`__doc__`) or parsed
by heading and bullet, never grepped across a whole file, so a comment beside a fix cannot satisfy
them. ADR-0018 is history and is amended, not rewritten (#783's amendment is the precedent): a claim
in its §2 stands until a later dated amendment in the same section says where the roles run.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import openfactory.adapters.agent.kimi as kimi_module
import openfactory.adapters.agent.roles as roles_module
from openfactory.adapters.agent.kimi import KimiAdapter
from openfactory.adapters.reviewer.harness import HarnessReviewer
from openfactory.adapters.sandbox import WorktreeSandbox
from openfactory.adapters.sandbox.base import Workspace
from openfactory.adapters.sandbox.registry import judging_worktree
from openfactory.contracts import AcceptanceCriterion, AgentRunResult, JobState, Manifest, Ticket
from openfactory.contracts.project import Project
from openfactory.observability import InMemoryEventSink
from openfactory.orchestrator import JobRunner
from tests.test_walking_skeleton import FakeForge, FakeTracker

ROOT = Path(__file__).resolve().parent.parent

#: Claims no document may make about the Kimi judging roles: each says they are kept in a box, or
#: that an edit cannot outlive the run. Matched on whitespace-collapsed text, so a docstring that
#: wraps the claim across two lines is still caught.
FORBIDDEN_CLAIMS = (
    "outlives the run",
    "ephemeral box",
    "inside their ephemeral box",
    "inside it while judging",
    "cannot escape the",
    "never on the host",
    "a mode, not",
)

#: Where the judging roles run: either the function that builds their room, or the plain words.
#: "on the host" preceded by "never " is the false claim above, not this one.
WHERE_THEY_RUN = re.compile(r"judging_worktree|(?<!never )\bon the host\b")

#: What keeps an `ask()` edit out of a pull request, in the one phrasing every document reuses.
NOTHING_COMMITS = "nothing commits from"

#: The one judging room the phrase above is not true of, named as the exception beside it.
ENV_CONTEXT_ASK_EXCEPTION = "except `env context --ask`"

#: The `ask()` that is not handed `judging_worktree` at all: `JobRunner._review` passes the job's
#: own box and workspace to `HarnessReviewer.review`, which asks there (the review of dc0efac4,
#: 2026-10-20, point 1). Named, with where its write goes, wherever a document says where the
#: questions run.
REVIEW_EXCEPTION = "the independent review, which runs in the job's box on the job's workspace"
REVIEW_REACHES = "can reach the pull request"

#: The universal claim that review found false: every `ask()` goes through `judging_worktree`.
#: Matched case-insensitively on whitespace-collapsed text.
EVERY_ASK_CLAIMS = (
    "every `ask()` runs",
    "every `ask()` caller",
    "every caller hands it",
    "where `ask()` runs is the same for every harness",
)


def _collapsed(text: str) -> str:
    return " ".join((text or "").split())


def _adr_0018_section_2() -> str:
    """ADR-0018 from its `### 2.` heading to the next `### ` heading, the heading excluded."""
    lines = (ROOT / "docs/adr/0018-harness-roles.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("### 2."))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("### "))
    return "\n".join(lines[start + 1:end])


def _configuration_kimi_bullet() -> str:
    """`docs/configuration.md`'s one bullet that starts `- **Kimi`, with its indented lines."""
    lines = (ROOT / "docs/configuration.md").read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("- **Kimi")]
    assert len(starts) == 1, f"expected one `- **Kimi` bullet in docs/configuration.md: {starts}"
    bullet = [lines[starts[0]]]
    for line in lines[starts[0] + 1:]:
        if not line.startswith("  ") or not line.strip():
            break
        bullet.append(line)
    return "\n".join(bullet)


#: Each document a person reads about where the Kimi roles run, read as it reaches them.
DOCUMENTS = {
    "kimi.__doc__": lambda: kimi_module.__doc__,
    "KimiAdapter.__doc__": lambda: KimiAdapter.__doc__,
    "KimiAdapter.ask.__doc__": lambda: KimiAdapter.ask.__doc__,
    "roles.__doc__": lambda: roles_module.__doc__,
    # RETIRED 2026-10-27 (#1149): `changes/362.limitation.md` was read here until 0.7.0's notes were
    # assembled, which removes every fragment it uses; its text is now 0.7.0's frozen section of
    # `CHANGELOG.md`, which no later change may edit, so nothing is left here to guard.
    "ADR-0018 section 2": _adr_0018_section_2,
    "docs/configuration.md Kimi bullet": _configuration_kimi_bullet,
}

ADR = "ADR-0018 section 2"


def _paragraphs(text: str) -> list[str]:
    return [_collapsed(p) for p in re.split(r"\n\s*\n", text) if p.strip()]


def _answers_where(paragraph: str) -> bool:
    return bool(WHERE_THEY_RUN.search(paragraph)) and NOTHING_COMMITS in paragraph


def _project_whose_jobs_run_in_a_container(monkeypatch) -> Project:
    """The box KIND is the deployment's (`OPENFACTORY_SANDBOX`, `factory.py`), the image and the
    names it passes are the project's (`Project.box`): both say container here."""
    monkeypatch.setenv("OPENFACTORY_SANDBOX", "container")
    return Project(name="boxed", repo_path="/tmp/boxed",
                   box={"image": "ghcr.io/example/client-ci:1", "network": "bridge",
                        "env": ["MODEL_GATEWAY_KEY"]})


def _disobeying_kimi_on_path(monkeypatch, tmp_path: Path) -> None:
    """A `kimi` that writes `wrote.txt` in its working directory and answers `done`. It stands
    where kimi-code 0.31.1 would and prints the one `role: assistant` line the adapter reads;
    `HOME` is empty, so `BEFORE_THE_HARNESS` finds no account MCP file and lets it start."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "kimi"
    stub.write_text("#!/bin/sh\n"
                    "echo disobeyed > wrote.txt\n"
                    "echo '{\"role\":\"assistant\",\"content\":\"done\"}'\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("KIMI_CODE_HOME", raising=False)


def _reviewing_kimi_on_path(monkeypatch, tmp_path: Path) -> None:
    """A `kimi` that, asked to review, writes `reviewed.txt` in its working directory, commits it
    with the factory's own `-c` overrides, and answers an approval in the one `role: assistant`
    line the adapter reads: the advisory review the review of dc0efac4 drove by hand. The git
    calls do not check their exit, so a room that is no repository still gets the same answer and
    the row is red at the pushed branch, not at the stub. `HOME` is empty, as for the stub above."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    verdict = json.dumps({"decision": "approved", "score": 90, "summary": "fine"})
    stub = bin_dir / "kimi"
    stub.write_text(
        f"#!{sys.executable}\n"
        "import json, subprocess\n"
        "open('reviewed.txt', 'w').write('the reviewer wrote this\\n')\n"
        "git = ['git', '-c', 'commit.gpgSign=false', '-c', 'user.name=r',\n"
        "       '-c', 'user.email=r@example.invalid']\n"
        "subprocess.run([*git, 'add', 'reviewed.txt'])\n"
        "subprocess.run([*git, 'commit', '-q', '-m', 'reviewed'])\n"
        f"print(json.dumps({{'role': 'assistant', 'content': {verdict!r}}}))\n",
        encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("KIMI_CODE_HOME", raising=False)


class _Executor:
    """An executor that writes `feature.py` through the box's own `run`, as a harness CLI does."""

    name = "codex"

    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        sandbox.run(workspace=workspace, command="echo 'VALUE = 42' > feature.py", timeout=60)
        return AgentRunResult(ok=True, summary="added feature.py", cost_usd=0.01)

    def repair(self, *, sandbox, workspace, context, failure_log, **kw) -> AgentRunResult:
        return AgentRunResult(ok=True)


def _repository_with_a_bare_origin(tmp_path: Path) -> tuple[Path, Path]:
    """A repository with one tracked `README.md`, pushed to a bare origin `publish_branch` pushes
    to for real (the walking skeleton's shape)."""
    env = {**os.environ, "LC_ALL": "C"}
    git = ["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgSign=false",
           "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    subprocess.run([*git, "init", "-q", "--bare", str(origin)], check=True, env=env)
    repo.mkdir()
    for args in (["init", "-q"], ["config", "user.name", "t"],
                 ["config", "user.email", "t@example.invalid"],
                 ["remote", "add", "origin", str(origin)]):
        subprocess.run([*git, "-C", str(repo), *args], check=True, env=env)
    (repo / "README.md").write_text("# app\n", encoding="utf-8")
    for args in (["add", "README.md"], ["commit", "-q", "-m", "init"],
                 ["push", "-q", "-u", "origin", "main"]):
        subprocess.run([*git, "-C", str(repo), *args], check=True, env=env,
                       capture_output=True)
    return repo, origin


def _room(tmp_path: Path) -> tuple[Path, Workspace]:
    room = tmp_path / "room"
    room.mkdir()
    return room, Workspace(path=room, branch="main", base_branch="main")


# ── the measurement the documents must agree with ─────────────────────────────────────────────────

def test_a_judging_role_runs_on_the_host_even_where_the_project_boxes_its_jobs(
        monkeypatch, tmp_path):
    """Criterion 2's basis: `judging_worktree` builds a host `WorktreeSandbox` for a project
    whose jobs run in a container, and a command it runs answers from the host room's own path,
    not from the container's `/workspace`. Green on main (620bb577); it goes red when the judging
    roles move into the box, which is when the documents must change back."""
    project = _project_whose_jobs_run_in_a_container(monkeypatch)
    room, ws = _room(tmp_path)

    sandbox = judging_worktree(project, root=tmp_path / "worktrees")
    assert isinstance(sandbox, WorktreeSandbox), type(sandbox)

    code, out = sandbox.run(workspace=ws, command="pwd -P", timeout=30)
    assert code == 0, out
    assert out.strip() == str(room.resolve())


def test_a_kimi_question_that_writes_leaves_its_file_in_the_host_room(monkeypatch, tmp_path):
    """Criterion 2's basis for "nothing confines a write to its room": the real `KimiAdapter.ask`,
    through `judging_worktree`, starts a `kimi` that disobeys the read-only instruction, and its
    file is on the host afterwards. The stub stands where kimi-code 0.31.1 would and prints the
    one `role: assistant` line the adapter reads; `HOME` is empty, so `BEFORE_THE_HARNESS` finds
    no account MCP file and lets it start. Green on main (620bb577)."""
    project = _project_whose_jobs_run_in_a_container(monkeypatch)
    room, ws = _room(tmp_path)
    _disobeying_kimi_on_path(monkeypatch, tmp_path)

    sandbox = judging_worktree(project, root=tmp_path / "worktrees")
    result = KimiAdapter().ask(sandbox=sandbox, workspace=ws, prompt="Is this repository tidy?")

    assert result.ok, result.raw_output
    assert result.summary == "done", result.raw_output
    assert (room / "wrote.txt").read_text(encoding="utf-8") == "disobeyed\n"


def test_a_kimi_question_asked_as_env_context_asks_leaves_its_file_in_the_persons_checkout(
        monkeypatch, tmp_path):
    """Criterion 2's basis for the `env context --ask` exception: `_semantic_pass`
    (`actions/catalog.py`) asks with `judging_worktree(project, root=checkout)` and
    `Workspace(path=checkout)`, where `checkout` is what `repo_for` resolved, the person's own
    repository on a local deployment. Driven the same way with no project (`env context` on a bare
    path) and the disobeying stub, the file is left untracked in that checkout. The review of
    e2b57dd1 (2026-10-20) measured `?? wrote.txt` there while four documents called every judging
    room one nothing commits from. Green on main by design; it is the fact the wording names."""
    checkout = tmp_path / "persons-repo"
    checkout.mkdir()
    git = ["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgSign=false",
           "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-C", str(checkout)]
    env = {**os.environ, "LC_ALL": "C"}
    subprocess.run([*git, "init", "-q"], check=True, env=env)
    (checkout / "README.md").write_text("mine\n", encoding="utf-8")
    subprocess.run([*git, "add", "README.md"], check=True, env=env)
    subprocess.run([*git, "commit", "-q", "-m", "mine"], check=True, env=env)
    _disobeying_kimi_on_path(monkeypatch, tmp_path)

    result = KimiAdapter().ask(
        sandbox=judging_worktree(None, root=checkout),
        workspace=Workspace(path=str(checkout), branch="main", base_branch="main"),
        prompt="What does this repository build?")

    assert result.ok, result.raw_output
    status = subprocess.run([*git, "status", "--porcelain"], check=True, env=env,
                            capture_output=True, text=True).stdout
    assert status.splitlines() == ["?? wrote.txt"], status


def test_a_kimi_review_that_writes_reaches_the_pushed_branch(monkeypatch, tmp_path):
    """Criterion 2's basis for the review exception (review of dc0efac4, 2026-10-20, point 1): the
    independent review is an `ask()` that is NOT handed `judging_worktree`. `JobRunner._review`
    passes the job's own box and workspace, and `HarnessReviewer.review` asks there, so the real
    `KimiAdapter` as reviewer, through the worktree box, with `planner_stage` off (the #788 check
    never runs) and review at its default (advisory), starts a `kimi` that writes and commits
    `reviewed.txt` in the job's workspace, and the job pushes it. The reviewer measured
    `README.md, feature.py, reviewed.txt` in `refs/heads/openfactory/1` on a scratch merge onto
    bb929e49 while six documents said every `ask()` ran in a room nothing commits from. Green by
    design; it turns red the day the review moves into a judging room, which is when the
    documents must change back."""
    repo, origin = _repository_with_a_bare_origin(tmp_path)
    _reviewing_kimi_on_path(monkeypatch, tmp_path)
    ticket = Ticket(id="#1", title="add feature", objective="add a feature", repo="o/app",
                    acceptance_criteria=[AcceptanceCriterion(text="feature.py exists")])
    runner = JobRunner(
        tracker=FakeTracker(ticket), forge=FakeForge(), agent=_Executor(),
        sandbox=WorktreeSandbox(root=tmp_path / "wt"),
        manifest=Manifest(validate={"test": "true"}, planner_stage=False),
        repo_path=repo, events=InMemoryEventSink(),
        reviewer=HarnessReviewer(KimiAdapter()),
    )
    assert runner.manifest.review_mode == "advisory", runner.manifest.review_mode

    result = runner.run("#1")

    assert result.state is JobState.PR_OPEN, f"{result.state.value}: {result.note}"
    assert result.review is not None and result.review.decision == "approved", result.review
    env = {**os.environ, "LC_ALL": "C"}
    heads = subprocess.run(["git", "-C", str(origin), "for-each-ref", "--format=%(refname)",
                            "refs/heads/"], check=True, env=env, capture_output=True,
                           text=True).stdout.split()
    pushed = [h for h in heads if h != "refs/heads/main"]
    assert len(pushed) == 1, heads
    files = subprocess.run(["git", "-C", str(origin), "ls-tree", "-r", "--name-only", pushed[0]],
                           check=True, env=env, capture_output=True, text=True).stdout.split()
    assert "reviewed.txt" in files, (
        f"the review's write did not reach the pushed branch {pushed[0]}: {files}")


# ── the documents ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", DOCUMENTS)
def test_no_document_says_the_kimi_roles_are_kept_in_a_box(name):
    """Criterion 2: no document says a Kimi judging role is kept in a box, or that its edit cannot
    outlive the run. On main (620bb577) the `ask()` docstring said it "cannot escape the
    platform's own ephemeral box", the module docstring that "no such edit outlives the run", the
    class docstring "never on the host", the 0.7.0 limitation note "inside their ephemeral box; no
    such edit outlives the run", ADR-0018 §2 "it could edit inside it while judging", and
    `docs/configuration.md` "a mode, not an enforced policy". For the ADR, a claim may stay as
    history only when a later dated amendment in §2 says where the roles run."""
    text = DOCUMENTS[name]()
    assert text, f"{name} is empty: there is nothing to read"
    if name == ADR:
        paragraphs = _paragraphs(text)
        claiming = [i for i, p in enumerate(paragraphs)
                    if any(claim in p for claim in FORBIDDEN_CLAIMS)]
        if not claiming:
            return
        answered_after = [p for p in paragraphs[claiming[-1] + 1:]
                          if p.startswith("**Amended (") and _answers_where(p)]
        assert answered_after, (
            f"{name} still says {[c for c in FORBIDDEN_CLAIMS if c in paragraphs[claiming[-1]]]} "
            f"and no later dated amendment in the section says where the judging roles run")
        return
    collapsed = _collapsed(text)
    made = [claim for claim in FORBIDDEN_CLAIMS if claim in collapsed]
    assert not made, f"{name} says {made}"


@pytest.mark.parametrize("name", DOCUMENTS)
def test_each_document_names_where_the_kimi_judging_roles_run(name):
    """Criterion 2: each document says where the judging roles run (`judging_worktree`, or "on
    the host") and that nothing commits from that room. On main (620bb577) none of them did."""
    text = DOCUMENTS[name]()
    assert text, f"{name} is empty: there is nothing to read"
    collapsed = _collapsed(text)
    assert WHERE_THEY_RUN.search(collapsed), (
        f"{name} does not say where the judging roles run (`judging_worktree` or 'on the host')")
    assert NOTHING_COMMITS in collapsed, (
        f"{name} does not say {NOTHING_COMMITS!r} the room the judging roles run in")


@pytest.mark.parametrize("name", DOCUMENTS)
def test_each_document_names_env_context_ask_wherever_it_says_nothing_commits_from(name):
    """Criterion 2, as the review of e2b57dd1 (2026-10-20) found it: `env context --ask` asks in
    the person's own checkout (the row above), so a paragraph that calls the judging rooms ones
    "nothing commits from" names that verb as the exception in the same paragraph. On a72dffe6
    none did: `kimi.py` and `roles.py` listed "a target checkout" among those rooms, ADR-0018's
    amendment said of the target checkout for `env context --ask` "Each is a room nothing commits
    from", and the 0.7.0 note and the configuration bullet said it of every read-only question."""
    text = DOCUMENTS[name]()
    assert text, f"{name} is empty: there is nothing to read"
    saying = [p for p in _paragraphs(text) if NOTHING_COMMITS in p]
    assert saying, f"{name} does not say {NOTHING_COMMITS!r}: the row above holds that"
    silent = [p for p in saying if ENV_CONTEXT_ASK_EXCEPTION not in p]
    assert not silent, (
        f"{name} says {NOTHING_COMMITS!r} without {ENV_CONTEXT_ASK_EXCEPTION!r} in: {silent}")


@pytest.mark.parametrize("name", DOCUMENTS)
def test_each_document_names_the_review_wherever_it_says_where_the_questions_run(name):
    """Criterion 2, as the review of dc0efac4 (2026-10-20, point 1) found it: the independent
    review is an `ask()` in the job's box on the job's workspace (the row above), so no document
    says every `ask()` goes through `judging_worktree`, and a paragraph that calls the judging
    rooms ones "nothing commits from" names the review as an exception there, and that its write
    can reach the pull request. On dc0efac4 six documents said "every `ask()`" (or "every caller
    hands it", or "the same for every harness, and it is not the job's box") and none named the
    review beside the rooms; `changes/362.limitation.md` listed the read-only questions without
    it."""
    text = DOCUMENTS[name]()
    assert text, f"{name} is empty: there is nothing to read"
    lowered = _collapsed(text).lower()
    made = [claim for claim in EVERY_ASK_CLAIMS if claim in lowered]
    assert not made, f"{name} still says {made}, and the independent review is an `ask()` too"
    saying = [p for p in _paragraphs(text) if NOTHING_COMMITS in p]
    assert saying, f"{name} does not say {NOTHING_COMMITS!r}: the row above holds that"
    silent = [p for p in saying if REVIEW_EXCEPTION not in p or REVIEW_REACHES not in p]
    assert not silent, (
        f"{name} says {NOTHING_COMMITS!r} without {REVIEW_EXCEPTION!r} and {REVIEW_REACHES!r} "
        f"in: {silent}")
