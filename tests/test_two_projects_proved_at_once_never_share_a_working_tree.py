"""#745: two projects proved at the same time deleted each other's working tree.

`box_probes` prepared every proof's workspace on ONE branch, `openfactory/box-prove`, and the
worktree box names its directory after the branch under a root every project the process serves
shares (`Path.cwd() / ".openfactory-worktrees"`). So two proofs taken at once met at one path.
Measured on git 2.43.0 with a real `WorktreeSandbox`, two keys and one root (2026-10-18, and again
on 43b8ff7b, 2026-10-21):

- ONE REPOSITORY (two registry projects on one local checkout, where `resolve_repo_path` returns
  the path itself): the second `prepare` takes the first proof's tree for its own and removes it.
  The first proof was still running in it: `A tree alive: False`.
- TWO REPOSITORIES: the second proof does not start. On c0a50f3 git refused it (`worktree add
  failed: … already exists`); since #746 the box refuses it first, by name, because a working tree
  of the other repository is at its path. Either way B's `box_start_error()` is not empty.

What must be true (AC1, read off the issue's "What happens" and "Fix"): two proofs with different
keys get different branches and different working trees, and neither disturbs the other — keys a
branch name cannot spell included.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from openfactory import box_prove, namespace
from openfactory.adapters.sandbox import registry as sandboxes

_MANIFEST = SimpleNamespace(base_branch="main", setup=[], validation={})


def _project(key: str) -> SimpleNamespace:
    return SimpleNamespace(name=key, box=None)


def _proofs_here(tmp_path: Path, monkeypatch) -> None:
    """Every proof's state under the test's own directory, never `/var/lib/openfactory/proofs`."""
    monkeypatch.setattr(box_prove, "PROOF_DIR", tmp_path / "proofs")


def _recording_box(monkeypatch, tmp_path: Path) -> list[str]:
    """A box that records the branch each proof asked it to prepare, and nothing else."""
    branches: list[str] = []

    class _Box:
        def prepare(self, *, branch, **_kw):
            branches.append(branch)
            return SimpleNamespace(path=str(tmp_path))

        def cleanup(self, **_kw):
            pass

        def harness_path(self, name):
            return name

    monkeypatch.setattr(sandboxes, "installed_box_traits",
                        lambda _kind: SimpleNamespace(honours_image=True))
    monkeypatch.setattr(sandboxes, "build_sandbox", lambda *_a, **_kw: _Box())
    return branches


def _prove(key: str, repo: Path, **kw):
    return box_prove.box_probes(_project(key), "img", repo_path=repo, manifest=_MANIFEST,
                                key=key, **kw)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgSign=false", *args],
                   check=True, capture_output=True, text=True)


def _repository(where: Path) -> Path:
    where.mkdir(parents=True)
    _git(where, "init", "-q", "-b", "main")
    (where / "README").write_text("hello\n")
    _git(where, "add", "README")
    _git(where, "commit", "-q", "-m", "first")
    return where


def _workspace_of(probes) -> Path:
    """Where the proof's box is, asked of the box itself: the worktree box runs in its tree."""
    rc, out = probes.run_in_box("pwd", None, 30)
    assert rc == 0, f"the proof's box could not run `pwd`: {out}"
    return Path(out.strip().splitlines()[-1])


def test_two_keys_are_proven_on_two_branches(tmp_path, monkeypatch):
    """AC1. Before: both keys called `prepare(branch="openfactory/box-prove")`."""
    _proofs_here(tmp_path, monkeypatch)
    branches = _recording_box(monkeypatch, tmp_path)

    for key in ("acme", "globex"):
        with _prove(key, tmp_path, sandbox="container"):
            pass

    acme, globex = branches
    assert acme != globex, f"two projects were proven on one branch, {acme!r}"
    for branch in branches:
        assert branch.startswith(f"{namespace.BRANCH_PREFIX}/box-prove-"), branch


def test_two_repositories_of_one_project_are_proven_on_two_branches(tmp_path, monkeypatch):
    """AC1, for one product that spans repositories: each is proven under its own `key`
    (`box prove --repo`, onboarding), so the branch and the lock are the key's, not the project's
    name. Before review round 1 of #745 every test passed `key == name`, and `subject =
    project.name` left them all green while two repositories of acme shared one branch again."""
    _proofs_here(tmp_path, monkeypatch)
    branches = _recording_box(monkeypatch, tmp_path)

    for key in ("acme", "acme--org--web"):
        with box_prove.box_probes(_project("acme"), "img", repo_path=tmp_path,
                                  manifest=_MANIFEST, key=key, sandbox="container"):
            pass

    assert len(set(branches)) == 2, f"two repositories of acme shared a branch: {branches}"


def test_keys_a_branch_name_cannot_spell_still_get_a_branch_each_and_git_accepts_it(
        tmp_path, monkeypatch):
    """AC1, for registry names that are free text: a space, a slash, the `_checkout_key` shape
    (`owner--org--name`), a letter outside ASCII, and `..`, the one run of kept characters a ref
    refuses. Slugged alike, `acme web` and `acme/web`
    would share a branch again; unslugged, git would refuse the name. Git itself is asked."""
    _proofs_here(tmp_path, monkeypatch)
    branches = _recording_box(monkeypatch, tmp_path)
    keys = ("acme web", "acme/web", "acme-web", "acme--org--web", "ação", "acme..web")

    for key in keys:
        with _prove(key, tmp_path, sandbox="container"):
            pass

    for key, branch in zip(keys, branches, strict=True):
        checked = subprocess.run(["git", "check-ref-format", "--branch", branch],
                                 capture_output=True, text=True)
        assert checked.returncode == 0, (
            f"git refuses the branch {branch!r} the proof of {key!r} asked for: {checked.stderr}")
    assert len(set(branches)) == len(keys), (
        f"keys a branch name cannot spell shared a branch: {dict(zip(keys, branches, strict=True))}")


def test_two_projects_on_one_repository_both_start_and_keep_their_trees(tmp_path, monkeypatch):
    """AC1 on the real worktree box. Before: B's `prepare` took A's tree for its own and removed
    it while A was proving in it (`A tree alive: False`, git 2.43.0, 2026-10-18)."""
    _proofs_here(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    repo = _repository(tmp_path / "shared")

    with _prove("a", repo, sandbox="worktree") as a:
        assert a.box_start_error() == "", a.box_start_error()
        marker = _workspace_of(a) / "a-is-proving-here"
        marker.write_text("a\n")
        with _prove("b", repo, sandbox="worktree") as b:
            assert b.box_start_error() == "", b.box_start_error()
            assert marker.exists(), "proving b removed the working tree a is proving in"


def test_two_projects_on_two_repositories_both_start(tmp_path, monkeypatch):
    """AC1 on the real worktree box, two repositories and the one root every project shares.
    Before: B did not start, refused over A's tree at the one path both proofs took."""
    _proofs_here(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    repo_a = _repository(tmp_path / "acme")
    repo_b = _repository(tmp_path / "globex")

    with _prove("a", repo_a, sandbox="worktree") as a:
        assert a.box_start_error() == "", a.box_start_error()
        marker = _workspace_of(a) / "a-is-proving-here"
        marker.write_text("a\n")
        with _prove("b", repo_b, sandbox="worktree") as b:
            assert b.box_start_error() == "", (
                f"the second project's proof did not start: {b.box_start_error()}")
            assert marker.exists(), "proving b removed the working tree a is proving in"
