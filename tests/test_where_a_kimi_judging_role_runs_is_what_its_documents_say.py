"""Where a Kimi judging role runs is what its documents say (#788, criterion 2).

#783 made Kimi Code's planner and its `ask()` read-only by instruction only, and five documents
rested that on one mitigation: the edit stays inside an ephemeral box, and "no such edit outlives
the run". Re-located on 620bb577 (2026-10-20), it is not what the code does for the judging roles.
Every `ask()` caller builds `sandbox/registry.py::judging_worktree`, which always returns a
`WorktreeSandbox`, and that box's `run` is `subprocess.Popen(command, shell=True,
cwd=workspace.path)` on the host, whatever box the project's jobs run in. The rooms it is handed
(a fresh temporary directory, the repo cache's master clone, the module's cached view, a target
checkout) are ones nothing commits from, so no `ask()` edit reaches a pull request, but nothing
confines a write to its room either.

THE FIRST TWO TESTS ARE THE MEASUREMENT the documents must agree with: a project that boxes its
jobs in a container still gets a host room for its judging roles, and the real `KimiAdapter.ask`
that disobeys its instruction leaves its file there. They are green on main by design. They turn
red the day `judging_worktree` routes into the box, which is when the wording must change back.

THE DOCUMENT ROWS READ TEXT, AND HERE THE TEXT IS THE THING. CONTRIBUTING's rule is that a guard
reads the thing rather than text about it; a release note and a docstring are read by a person, so
their sentences are what is checked. They are read as the code exports them (`__doc__`) or parsed
by heading and bullet, never grepped across a whole file, so a comment beside a fix cannot satisfy
them. ADR-0018 is history and is amended, not rewritten (#783's amendment is the precedent): a claim
in its §2 stands until a later dated amendment in the same section says where the roles run.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

import pytest

import openfactory.adapters.agent.kimi as kimi_module
import openfactory.adapters.agent.roles as roles_module
from openfactory.adapters.agent.kimi import KimiAdapter
from openfactory.adapters.sandbox import WorktreeSandbox
from openfactory.adapters.sandbox.base import Workspace
from openfactory.adapters.sandbox.registry import judging_worktree
from openfactory.contracts.project import Project

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
    "changes/362.limitation.md": lambda: (ROOT / "changes/362.limitation.md").read_text(
        encoding="utf-8"),
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

    sandbox = judging_worktree(project, root=tmp_path / "worktrees")
    result = KimiAdapter().ask(sandbox=sandbox, workspace=ws, prompt="Is this repository tidy?")

    assert result.ok, result.raw_output
    assert result.summary == "done", result.raw_output
    assert (room / "wrote.txt").read_text(encoding="utf-8") == "disobeyed\n"


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
