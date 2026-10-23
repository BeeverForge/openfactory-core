"""A value that reaches git as a positional argument is behind `--`, so it can never be read as
an option (#741).

A repository name, a clone URL or a refspec comes from the registry, a request or a product's
record, and several of those reach `git` on a command line. Git reads a leading `-` as an option
wherever the end-of-options marker `--` has not been given, so a value like
`--upload-pack=<something>` passed to `git ls-remote <url>` is run as the `--upload-pack` option
rather than read as a repository. `product_declare` met this exactly: on a `local` forge the
declared name became the clone URL unchanged, and `context_reachability` ran `git ls-remote
--heads <url>` with no `--`.

TWO HALVES, HELD HERE:
  1. every git argv in the package for a subcommand that takes a remote, a URL or a path
     positionally carries `--` before those arguments — read from the source, so a call added
     later is held too;
  2. the row that takes a repository refuses a value that begins with `-` with a sentence, before
     anything reaches git, and `git ... -- <value>` refuses such a value itself.
"""

from __future__ import annotations

import ast
import asyncio
import subprocess
from pathlib import Path

import pytest

from openfactory import actions

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "openfactory"

#: The subcommands that take a remote, a URL or a path as a positional argument — exactly the
#: shapes a hostile value can turn into an option. `remote set-url`/`add` take a URL too.
REMOTE = frozenset({"clone", "fetch", "ls-remote", "push", "pull"})


def _s(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _git_argv(elts: list[ast.AST]) -> tuple[str, bool] | None:
    """`(subcommand, has_marker)` if `elts` is a git argv for a remote-taking subcommand, else
    None. A leading `git`, the global `-C <path>`/`-c <k=v>` pairs and any `-flag` are skipped to
    find the subcommand; `--` anywhere in the argv is the marker."""
    toks = [_s(e) for e in elts]
    if not toks or all(t is None for t in toks):
        return None
    i = 1 if toks[0] == "git" else 0
    while i < len(toks):
        t = toks[i]
        if t in ("-C", "-c"):
            i += 2
            continue
        if t is None:  # an expression where the subcommand would be — not a literal argv
            return None
        if t.startswith("-"):
            i += 1
            continue
        break
    if i >= len(toks):
        return None
    sub, marker = toks[i], "--" in toks
    if sub == "remote":
        rest = toks[i + 1:]
        if "set-url" in rest or "add" in rest:
            return (f"remote {'set-url' if 'set-url' in rest else 'add'}", marker)
        return None
    return (sub, marker) if sub in REMOTE else None


def _callee(node: ast.Call) -> str:
    """The name a call is made by — `_git`, `self._git`, `git` — or "" for anything else."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _violations(text: str) -> list[tuple[int, str]]:
    """Every remote-taking git argv in `text` without `--`. Two shapes carry one: a list or tuple
    literal — passed straight to `subprocess.run`, built in a variable, iterated in a loop, or
    handed to a `_git([...])` wrapper — and the argument list of a wrapper called with git's words
    one by one, `_git("clone", url, dest)`, which no literal holds."""
    out = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
            got = _git_argv(node.elts)
        elif isinstance(node, ast.Call) and "git" in _callee(node) and node.args:
            got = _git_argv(node.args)
        else:
            continue
        if got and not got[1]:
            out.append((node.lineno, got[0]))
    return out


def test_every_git_argv_for_a_remote_puts_its_values_behind_the_marker():
    offenders = {}
    for path in sorted(PKG.rglob("*.py")):
        bad = _violations(path.read_text(encoding="utf-8"))
        if bad:
            offenders[path.relative_to(ROOT).as_posix()] = bad
    assert not offenders, (
        "a git argv reaches a remote/URL/path value with no `--` before it, so git could read a "
        f"value beginning with '-' as an option: {offenders}")


def test_the_reader_sees_a_missing_marker_and_a_present_one():
    """The guard above is worth nothing if it cannot tell the two apart, so it is shown both."""
    assert _violations('subprocess.run(["git", "ls-remote", "--heads", url])') == [(1, "ls-remote")]
    assert _violations('subprocess.run(["git", "ls-remote", "--heads", "--", url])') == []
    # a non-remote subcommand is not this rule's business, marker or no marker
    assert _violations('_run(["git", "-C", p, "rev-parse", "HEAD"])') == []
    assert _violations('_git(["remote", "set-url", "origin", url])') == [(1, "remote set-url")]
    # a wrapper handed git's words one by one is read too, with or without `self.`
    assert _violations('_git("clone", url, dest)') == [(1, "clone")]
    assert _violations('self._git("fetch", ".", spec, cwd=where)') == [(1, "fetch")]
    assert _violations('_git("clone", "--", url, dest)') == []
    assert _violations('_git("-C", path, "rev-parse", "HEAD")') == []


ADMIN = actions.Actor(id="rob", via="panel", admin=True)
#: A value shaped like a git option, carrying a harmless marker: if git ran it as `--upload-pack`
#: the probe in the test below would create the file, which the test then asserts never happens.
def _option_shaped(marker: Path) -> str:
    return f"--upload-pack=touch {marker};://x"


@pytest.fixture
def one_local_project(tmp_path, monkeypatch):
    """`acme` on a real local forge, so `product_declare` would reach `git ls-remote` if it got
    that far."""
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.identity.local import CLOSING_ENVS
    from openfactory.registry import ProjectRegistry

    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "registry.yaml"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(path))
    repo = tmp_path / "acme"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    ProjectRegistry().add(Project(name="acme", repo_path=str(repo),
                                  tracker=ProviderRef(kind="local", repo="acme", options={}),
                                  forge=ProviderRef(kind="local", repo="acme", options={})))
    return path


def test_the_row_refuses_a_repository_that_begins_like_an_option(one_local_project, tmp_path):
    """The option-shaped value is refused by `product_declare` before anything reaches git: the
    answer is a sentence, the registry is untouched, and nothing was run."""
    marker = tmp_path / "MARKER"
    before = one_local_project.read_bytes()

    out = asyncio.run(actions.perform("product_declare", by=ADMIN, project="acme",
                                      docs_repo=_option_shaped(marker)))

    assert out.code == actions.INVALID and "begins with '-'" in out.message, out
    assert one_local_project.read_bytes() == before, "the registry was written for a refused name"
    assert not marker.exists(), "the value reached a shell"


def test_git_itself_refuses_an_option_shaped_value_behind_the_marker(tmp_path):
    """The other half: even a value that reached git is read as a repository, not an option,
    because the `--` is there. git refuses it ('strange pathname … blocked') and runs nothing."""
    marker = tmp_path / "MARKER"
    done = subprocess.run(["git", "ls-remote", "--heads", "--", _option_shaped(marker)],
                          capture_output=True, text=True, timeout=20, check=False,
                          cwd=str(tmp_path))

    assert done.returncode != 0, "git accepted an option-shaped repository"
    assert not marker.exists(), "git ran the value as an option despite the marker"
