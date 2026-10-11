"""Every clone the platform runs reads its source through the pack protocol, never by copying the
source's objects directory file by file (#594).

A clone of a local path, git's default, links or copies each file under the source's
`.git/objects`. A commit, a push and a fetch end with `git maintenance run --auto`, detached, and
newer git repacks small repositories: a clone that lists a pack being written, or a loose object
about to be packed away, fails — `hardlink different from source at …/objects/pack/tmp_rev_…`,
`failed to copy file to …/objects/5b/908c…: No such file or directory`. On git 2.56, two runs of
600 clones of a freshly pushed repository failed 1 and 6 times. Every clone of a path the platform
makes is one of these: the local forge's repositories are paths (`LocalForge.clone_url`), and the
box and the preview clone the worker's cache directory.

`--no-local` reads the source through upload-pack, which reads the object store as git does and
survives a concurrent repack. For a URL git ignores it. The proof that a clone does not copy the
objects directory is what it does with a file only a repack in progress leaves there.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRAY = "tmp_idx_left_by_a_repack"


def _source(tmp_path: Path) -> Path:
    """A repository with a pack, and beside it a file a repack in progress writes."""
    src = tmp_path / "src"
    subprocess.run(["git", "init", "-q", "-b", "main", str(src)], check=True)
    (src / "a.txt").write_text("a\n")
    subprocess.run(["git", "-C", str(src), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(src), "commit", "-qm", "a"], check=True)
    subprocess.run(["git", "-C", str(src), "gc", "-q"], check=True)
    (src / ".git" / "objects" / "pack" / STRAY).write_text("half written")
    return src


def test_a_clone_by_path_copies_what_a_repack_is_writing_and_the_pack_protocol_does_not(tmp_path):
    """The mechanism, on git's own command: the default local clone copies the stray file, which
    is the race; `--no-local` never sees it."""
    src = _source(tmp_path)

    subprocess.run(["git", "clone", "-q", str(src), str(tmp_path / "local")], check=True)
    subprocess.run(["git", "clone", "-q", "--no-local", str(src), str(tmp_path / "pack")],
                   check=True)

    assert (tmp_path / "local" / ".git" / "objects" / "pack" / STRAY).exists()
    assert not (tmp_path / "pack" / ".git" / "objects" / "pack" / STRAY).exists()


def test_the_repo_cache_clones_a_path_through_the_pack_protocol(tmp_path):
    """The clone every read of a local-forge repository goes through."""
    from openfactory.runtime.repo_cache import RepoCache

    src = _source(tmp_path)

    served = RepoCache(root=tmp_path / "cache").sync("p", str(src), "main")

    assert served is not None and (served / "a.txt").read_text() == "a\n"
    master = tmp_path / "cache" / ".masters" / "p"
    assert not list(master.rglob(STRAY)), "the cache copied the source's objects directory"


def test_the_box_clones_the_cache_through_the_pack_protocol(tmp_path):
    """The box's workspace is a clone of the worker's cache DIRECTORY — a path on every forge."""
    from openfactory.adapters.sandbox.container import _materialize_workspace

    src = _source(tmp_path)
    clone = tmp_path / "workspace"

    _materialize_workspace(repo_path=src, host_clone=clone, base_branch="main",
                           branch="feat/a-change", checkout_existing=False)

    assert (clone / "a.txt").read_text() == "a\n"
    assert not list(clone.rglob(STRAY)), "the box copied the cache's objects directory"


# ── the guard ───────────────────────────────────────────────────────────────────────────────────

def _clones(source: str) -> list[str]:
    """`<line>` for every `git clone` argv in `source` that does not pass `--no-local`: a list,
    tuple or call whose strings start `clone`, or `git`, `clone`."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.List | ast.Tuple):
            items = node.elts
        elif isinstance(node, ast.Call):
            items = node.args
        else:
            continue
        words = [e.value if isinstance(e, ast.Constant) else None for e in items]
        starts = words[:1] == ["clone"] or words[:2] == ["git", "clone"]
        if starts and "--no-local" not in words:
            found.append(node.lineno)
    return [str(n) for n in sorted(found)]


def test_every_clone_the_platform_runs_passes_no_local():
    """A GUARD ON THE CLASS: the next clone written into the platform reads a path the same way."""
    missing = [f"{path.relative_to(ROOT)}:{line}"
               for path in sorted((ROOT / "openfactory").rglob("*.py"))
               for line in _clones(path.read_text(encoding="utf-8"))]
    assert missing == [], f"a clone copies its source's objects directory file by file: {missing}"


def test_the_guard_sees_each_shape_of_a_clone_it_replaced():
    """THE GUARD CALLS ITS OWN RULE on the shapes the platform clones in."""
    before = ('_git(["clone", "--depth", "1", url, str(tmp)])\n'
              'subprocess.run(["git", "clone", "-q", where, tmp])\n'
              '_git("clone", "--depth", "1", remote_url, str(pub))\n'
              'shallow = ["clone", "--depth", "1", url, str(tmp)]\n'
              '_git(["clone", "--no-local", url, str(tmp)])\n')
    assert _clones(before) == ["1", "2", "3", "4"]
