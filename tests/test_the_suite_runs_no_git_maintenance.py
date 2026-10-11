"""No git maintenance runs behind a test's back, and a clone that fails says git's whole sentence
(#592).

About one CI run in ten failed a test that clones a repository the suite had just built, a
different test each time: `hardlink different from source at …/objects/pack/tmp_idx_…`, or
`failed to copy file to …/objects/5b/908c…: No such file or directory`. A commit, and a push into a
bare repository, end with `git maintenance run --auto` DETACHED — it repacks after the command has
returned — and the runner's git (2.55) repacks small repositories that the old `gc --auto`
thresholds left alone. A clone of a local path copies the objects directory file by file, so it
met a pack being written, or a loose object just packed away. Measured on git 2.56 in a container,
a bare repository pushed four times and cloned by path after each push: two runs of 600 clones
failed 1 and 6 times with maintenance on (`hardlink different from source at
…/objects/pack/tmp_rev_…`), and 0 and 0 with it off.

The suite's own git config (`tests/conftest.py`) turns automatic maintenance off, so which git a
machine runs is not part of what the suite measures. The repo cache logged the last 160
characters of git's answer, which cut inside the object's path: the words before it were lost.
"""

from __future__ import annotations

import ast
import logging
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("key, value", [("maintenance.auto", "false"), ("gc.auto", "0"),
                                        ("receive.autogc", "false")])
def test_a_repository_the_suite_builds_runs_no_maintenance_after_a_commit_or_a_push(
        tmp_path, key, value):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    said = subprocess.run(["git", "-C", str(tmp_path), "config", "--get", key],
                          capture_output=True, text=True)

    assert said.stdout.strip() == value, (
        f"{key} is {said.stdout.strip() or 'unset'} in a repository the suite builds: git's "
        f"automatic maintenance may repack it while a test clones it")


def test_a_clone_that_failed_logs_gits_whole_sentence(tmp_path, caplog):
    """The words before the path are what git was doing when it failed; a cut at the last 160
    characters kept the path and lost them."""
    from openfactory.runtime.repo_cache import RepoCache

    nowhere = tmp_path / ("a-directory-with-a-long-name-" * 8) / "docs.git"

    with caplog.at_level(logging.WARNING, logger="openfactory.repo_cache"):
        assert RepoCache(root=tmp_path / "cache").sync("p", str(nowhere), "main") is None

    failed = [r.getMessage() for r in caplog.records
              if "OPENFACTORY_CACHE: clone failed for p" in r.getMessage()]
    assert failed and "fatal:" in failed[0] and str(nowhere) in failed[0], failed


# ── the guard: every git the suite starts sees the suite's config ───────────────────────────────

ROOT = Path(__file__).resolve().parents[1]


def _replaces_the_environment(node: ast.AST) -> bool:
    """A dict literal with no `**` unpacking: an environment built from nothing."""
    return isinstance(node, ast.Dict) and None not in node.keys


def _gits_on_their_own_environment(source: str) -> list[str]:
    """`<line>` for every `git` argv started with an `env=` that does not carry the process's own
    — a dict literal, or a name assigned one in the same function — so `GIT_CONFIG_GLOBAL` is
    lost and git's automatic maintenance runs."""
    found = []
    for scope in ast.walk(ast.parse(source)):
        if not isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef | ast.Module):
            continue
        built = {t.id for n in ast.walk(scope) if isinstance(n, ast.Assign)
                 and _replaces_the_environment(n.value) for t in n.targets
                 if isinstance(t, ast.Name)}
        for call in (n for n in ast.walk(scope) if isinstance(n, ast.Call)):
            argv = call.args[0] if call.args else None
            first = argv.elts[0] if isinstance(argv, ast.List) and argv.elts else None
            if not (isinstance(first, ast.Constant) and first.value == "git"):
                continue
            for kw in call.keywords:
                if kw.arg == "env" and (_replaces_the_environment(kw.value) or (
                        isinstance(kw.value, ast.Name) and kw.value.id in built)):
                    found.append(call.lineno)
    return [str(n) for n in sorted(set(found))]


def test_no_git_the_suite_starts_loses_the_suites_config():
    """A GUARD ON THE CLASS (review of #595): the fixture above reaches only a git that inherits
    the environment, and a fixture that built its own committed, pushed and was cloned by path."""
    lost = [f"{path.relative_to(ROOT)}:{line}"
            for path in sorted((ROOT / "tests").rglob("*.py"))
            for line in _gits_on_their_own_environment(path.read_text(encoding="utf-8"))]
    assert lost == [], f"a git runs without the suite's config, maintenance on: {lost}"


def test_the_guard_sees_the_fixture_it_was_written_for():
    """THE GUARD CALLS ITS OWN RULE on the shape that escaped, and passes the shape that merges."""
    before = (
        "def context_repo():\n"
        "    env = {'GIT_AUTHOR_NAME': 't', 'PATH': os.environ['PATH']}\n"
        "    subprocess.run(['git', *args], cwd=seed, env=env)\n"
        "    subprocess.run(['git', 'push'], env={'HOME': '/x'})\n"
        "    subprocess.run(['git', 'push'], env={**os.environ, 'HOME': '/x'})\n")
    assert _gits_on_their_own_environment(before) == ["3", "4"]
