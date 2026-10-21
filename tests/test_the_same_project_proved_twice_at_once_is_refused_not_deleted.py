"""#745: a second proof of a project that is already being proven removed the first one's box.

Every proof of one key asks its box for the same branch, so the same tree and the same container
name. On the worktree box the second `prepare` takes the first proof's tree for its own and
removes it (`A tree alive: False`, git 2.43.0, 2026-10-18, and again on 43b8ff7b, 2026-10-21); on
the container box `prepare` `docker rm -f`s the container wearing that name as debris. The doors
that meet it are `box prove`, `box answer` and onboarding, of one project, at once — from one
process or from two (the CLI beside the worker).

What must be true (AC2, AC3): a second proof of a key already being proven is refused with
`ProveBusy` before the box, the repository cache or the checkout is touched, and the first proof's
tree survives; the refusal holds when the holder is another process, ends when the proof ends or
raises, and a holder killed with SIGKILL leaves nothing behind; two different keys never block
each other.

`ProveBusy` and `proof_lock_path` are read off the module inside each test body (or by the
holder process), never imported at module level, so that on a tree without them each test FAILS
for that reason instead of the module erroring at collection.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from openfactory import box_prove
from openfactory.adapters.sandbox import registry as sandboxes

_MANIFEST = SimpleNamespace(base_branch="main", setup=[], validation={})
_WAIT = 30  # seconds any step may take before the test calls it a hang, not a pass


def _proofs_here(tmp_path: Path, monkeypatch) -> None:
    """Every proof's state, the lock included, under the test's own directory."""
    monkeypatch.setattr(box_prove, "PROOF_DIR", tmp_path / "proofs")


def _prove(key: str, repo: Path | None, **kw):
    return box_prove.box_probes(SimpleNamespace(name=key, box=None), "img", repo_path=repo,
                                manifest=_MANIFEST, key=key, **kw)


def _recording_box(monkeypatch, tmp_path: Path) -> list[str]:
    """A box that writes down `build_sandbox`, `prepare` and `resolve_repo_path` as they happen."""
    from openfactory import factory

    touched: list[str] = []

    class _Box:
        def prepare(self, **_kw):
            touched.append("prepare")
            return SimpleNamespace(path=str(tmp_path))

        def cleanup(self, **_kw):
            pass

        def harness_path(self, name):
            return name

    def build(*_a, **_kw):
        touched.append("build_sandbox")
        return _Box()

    def resolve(*_a, **_kw):
        touched.append("resolve_repo_path")
        return tmp_path

    monkeypatch.setattr(sandboxes, "installed_box_traits",
                        lambda _kind: SimpleNamespace(honours_image=True))
    monkeypatch.setattr(sandboxes, "build_sandbox", build)
    monkeypatch.setattr(factory, "resolve_repo_path", resolve)
    return touched


class _Holder(threading.Thread):
    """A proof of `key` on its own thread, held open until `release` is set.

    A SECOND THREAD, NOT A NESTED `with`: the lock a proof takes is re-entrant for the thread that
    holds it (`util/filelock.py`), so a nested entry on one thread would pass any such guard and
    measure nothing."""

    def __init__(self, key: str, repo: Path | None, *, on_entry=None, **kw) -> None:
        super().__init__(daemon=True)
        self.key, self.repo, self.kw, self.on_entry = key, repo, kw, on_entry
        self.entered, self.release = threading.Event(), threading.Event()
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            with _prove(self.key, self.repo, **self.kw) as probes:
                if self.on_entry is not None:
                    self.on_entry(probes)
                self.entered.set()
                self.release.wait(_WAIT)
        except BaseException as exc:  # noqa: BLE001 — handed to the test, which re-raises it
            self.error = exc
            self.entered.set()

    def __enter__(self):
        self.start()
        assert self.entered.wait(_WAIT), f"the proof of {self.key} never started"
        if self.error is not None:
            raise self.error
        return self

    def __exit__(self, *_exc):
        self.release.set()
        self.join(_WAIT)
        return False


def _try_to_prove(key: str, repo: Path | None, **kw) -> BaseException | None:
    """Enter and leave a proof of `key`; answer what refused it, or `None` when it ran."""
    try:
        with _prove(key, repo, **kw):
            pass
    except Exception as exc:  # noqa: BLE001 — the test reads which refusal it was
        return exc
    return None


def _on_another_thread(key: str, repo: Path | None, **kw) -> BaseException | None:
    seen: list[BaseException | None] = []
    worker = threading.Thread(target=lambda: seen.append(_try_to_prove(key, repo, **kw)),
                              daemon=True)
    worker.start()
    worker.join(_WAIT)
    assert seen, f"the proof of {key} on another thread never ended"
    return seen[0]


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


#: Another process proving `key`: it asks `box_prove` for the key's lock path ITSELF, as the CLI
#: beside the worker does, takes the exclusive `flock` on it, says so, and keeps it until killed. A
#: path the test computed and handed over would agree with this process whatever the path is made
#: of, so a lock path that varied by process (a pid in its name) would go unseen.
_HOLD = """
import fcntl, sys, time
from openfactory import box_prove
path = box_prove.proof_lock_path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
handle = open(path, "a")
fcntl.flock(handle, fcntl.LOCK_EX)
print("held", flush=True)
time.sleep(120)
"""


def _another_process_holding(key: str, proofs: Path) -> subprocess.Popen:
    holder = subprocess.Popen([sys.executable, "-c", _HOLD, key], stdout=subprocess.PIPE,
                              text=True, env={**os.environ, "OPENFACTORY_PROOFS": str(proofs)})
    assert holder.stdout is not None and holder.stdout.readline().strip() == "held", (
        "the holder process never took the lock")
    return holder


def test_a_second_proof_of_a_running_key_is_refused_and_the_first_tree_survives(
        tmp_path, monkeypatch):
    """AC2 on the real worktree box. Before: no refusal, and the second proof's `prepare` removed
    the tree the first proof was running in."""
    _proofs_here(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    repo = _repository(tmp_path / "acme")
    marked: list[Path] = []

    def mark(probes) -> None:
        rc, out = probes.run_in_box("pwd", None, _WAIT)
        assert rc == 0, f"the first proof's box could not run `pwd`: {out}"
        marker = Path(out.strip().splitlines()[-1]) / "acme-is-proving-here"
        marker.write_text("acme\n")
        marked.append(marker)

    with _Holder("acme", repo, sandbox="worktree", on_entry=mark):
        refused = _try_to_prove("acme", repo, sandbox="worktree")
        assert marked[0].exists(), (
            "the second proof of acme removed the working tree the first one is proving in")

    busy = box_prove.ProveBusy
    assert isinstance(refused, busy), f"the second proof of acme was not refused: {refused!r}"
    assert "acme" in str(refused), str(refused)


@pytest.mark.parametrize("kind", ["container", "worktree"])
def test_the_refusal_comes_before_the_box_is_touched(tmp_path, monkeypatch, kind):
    """AC2, decide before you write (engineering lessons §12): the refused proof neither syncs the
    checkout (`resolve_repo_path`), nor builds a box, nor prepares one. Before: all three ran, and
    `prepare` is where the first proof's tree or container is removed."""
    _proofs_here(tmp_path, monkeypatch)
    touched = _recording_box(monkeypatch, tmp_path)

    with _Holder("acme", None, sandbox=kind):
        touched.clear()
        refused = _try_to_prove("acme", None, sandbox=kind)
        assert touched == [], f"the refused proof of acme touched {touched}"

    busy = box_prove.ProveBusy
    assert isinstance(refused, busy), f"the second proof of acme was not refused: {refused!r}"


def test_a_proof_that_ended_or_raised_leaves_its_key_free(tmp_path, monkeypatch):
    """AC2: the key is free again once its proof ends, however it ends. Asked from ANOTHER thread
    each time, because the holder's own thread would re-enter a lock it never let go."""
    _proofs_here(tmp_path, monkeypatch)
    _recording_box(monkeypatch, tmp_path)
    busy = box_prove.ProveBusy

    assert _try_to_prove("acme", tmp_path, sandbox="container") is None
    after_an_end = _on_another_thread("acme", tmp_path, sandbox="container")
    assert not isinstance(after_an_end, busy), f"a proof that ended kept acme: {after_an_end}"
    assert after_an_end is None, repr(after_an_end)

    with pytest.raises(ValueError, match="the proof raised"):
        with _prove("acme", tmp_path, sandbox="container"):
            raise ValueError("the proof raised")
    after_a_raise = _on_another_thread("acme", tmp_path, sandbox="container")
    assert not isinstance(after_a_raise, busy), f"a proof that raised kept acme: {after_a_raise}"
    assert after_a_raise is None, repr(after_a_raise)


def test_a_proof_whose_checkout_could_not_be_resolved_leaves_its_key_free(tmp_path, monkeypatch):
    """AC2: the lock is taken before the checkout is synced, so a sync that raises (an unreachable
    remote, a full disk) happens while the key is held. It must let the key go, or every later
    proof of it in this process is refused until a restart."""
    from openfactory import factory

    _proofs_here(tmp_path, monkeypatch)
    _recording_box(monkeypatch, tmp_path)
    busy = box_prove.ProveBusy

    def unreachable(*_a, **_kw):
        raise RuntimeError("the remote could not be reached")

    monkeypatch.setattr(factory, "resolve_repo_path", unreachable)
    with pytest.raises(RuntimeError, match="could not be reached"):
        with _prove("acme", None, sandbox="container"):
            pass

    after = _on_another_thread("acme", tmp_path, sandbox="container")
    assert not isinstance(after, busy), f"a proof whose checkout failed kept acme: {after}"
    assert after is None, repr(after)


def test_two_keys_hold_their_locks_side_by_side(tmp_path, monkeypatch):
    """AC1/AC2: the refusal is per key — a proof of `b` runs while `a` is being proven."""
    _proofs_here(tmp_path, monkeypatch)
    _recording_box(monkeypatch, tmp_path)
    busy = box_prove.ProveBusy

    with _Holder("a", tmp_path, sandbox="container"):
        beside = _try_to_prove("b", tmp_path, sandbox="container")

    assert not isinstance(beside, busy), f"proving a refused b: {beside}"
    assert beside is None, repr(beside)


def test_a_proof_held_by_another_process_refuses_this_one(tmp_path, monkeypatch):
    """AC3: the CLI and the worker are two processes, so the lock is the kernel's, on the path
    `proof_lock_path` gives each of them for the key. Before: no such path, and nothing refused."""
    _proofs_here(tmp_path, monkeypatch)
    touched = _recording_box(monkeypatch, tmp_path)
    holder = _another_process_holding("acme", tmp_path / "proofs")
    try:
        refused = _try_to_prove("acme", tmp_path, sandbox="container")
    finally:
        holder.kill()
        holder.wait(_WAIT)

    busy = box_prove.ProveBusy
    assert isinstance(refused, busy), (
        f"a proof of acme ran while another process held it: {refused!r}")
    assert "prepare" not in touched, "the refused proof prepared a box"


def test_a_holder_killed_mid_proof_leaves_no_lock(tmp_path, monkeypatch):
    """AC3: a proof killed with SIGKILL runs no `finally`, so a lock that is a file's existence
    would hold its key for good. The kernel's `flock` dies with its holder."""
    _proofs_here(tmp_path, monkeypatch)
    touched = _recording_box(monkeypatch, tmp_path)
    holder = _another_process_holding("acme", tmp_path / "proofs")
    os.kill(holder.pid, signal.SIGKILL)
    holder.wait(_WAIT)

    after = _try_to_prove("acme", tmp_path, sandbox="container")

    assert after is None, f"the proof of acme was refused after its holder was killed: {after!r}"
    assert "prepare" in touched
