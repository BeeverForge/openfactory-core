"""#901: a process group whose last members are unreaped zombies is not gone yet, and asking does
not raise.

`tests/test_a_rerun_after_an_interrupted_worktree_add_starts.py` (#746) waits for the process
group it interrupted with `_group_gone`, which asks `os.killpg(pgid, 0)` and read only
`ProcessLookupError` as "gone". On macOS, `killpg(pgid, 0)` on a group whose last members are
zombies awaiting reaping answers EPERM, so `PermissionError` escaped the poll and the test failed
with an error unrelated to its claim. Measured by #846's macOS reviewer on 6a87018 (Apple git
2.50.1, Python 3.13): the module was red in 6 of 10 runs, and the #746 mutation plan's baseline
was RED. On Linux a zombie group answers signal 0 with success, so CI never saw it. The same
EPERM (or the group vanishing between the check and the kill) could escape the module's
`finally` cleanup, replacing a real failure with an unrelated error.

THESE GUARDS LIVE IN THEIR OWN FILE ON PURPOSE, as #121's do
(`tests/test_the_suite_runs_where_a_maintainer_sits.py`): a guard for a file's runnability is
worth nothing inside the file it guards. The EPERM answer is driven here through a fake
`os.killpg`, because no Linux host produces it; one test runs a real `start_new_session` child to
pin the Linux behaviour the fix keeps.
"""

from __future__ import annotations

import errno
import os
import signal
import subprocess
import sys

import pytest

from tests.test_a_rerun_after_an_interrupted_worktree_add_starts import _group_gone, _wait_for


def _killpg_answering(*answers: BaseException | None):
    """A fake `os.killpg` that raises each of `answers` in turn (None: returns), and the list of
    the `(pgid, sig)` it was called with."""
    calls: list[tuple[int, int]] = []
    queue = list(answers)

    def killpg(pgid: int, sig: int) -> None:
        calls.append((pgid, sig))
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if answer is not None:
            raise answer

    return killpg, calls


def _eperm() -> PermissionError:
    return PermissionError(errno.EPERM, os.strerror(errno.EPERM))


def test_a_group_that_answers_EPERM_reads_as_not_gone_yet(monkeypatch):
    """`_group_gone` treats `PermissionError` as "not gone yet": macOS's answer to signal 0 for a
    group of unreaped zombies. On 6a87018 the fake's `PermissionError` escaped `_group_gone`."""
    fake, calls = _killpg_answering(_eperm())
    monkeypatch.setattr(os, "killpg", fake)
    assert _group_gone(12345) is False
    assert calls == [(12345, 0)]


def test_the_wait_keeps_polling_through_EPERM_until_the_group_is_gone(monkeypatch):
    """The module passes repeatedly on macOS: the poll keeps going through EPERM and stops when
    the group is gone. On 6a87018 the first `PermissionError` escaped `_wait_for`, so the poll
    was never retried (6 of 10 runs red on macOS)."""
    fake, calls = _killpg_answering(_eperm(), _eperm(), ProcessLookupError(errno.ESRCH, "gone"))
    monkeypatch.setattr(os, "killpg", fake)
    _wait_for(lambda: _group_gone(12345), "the faked group to read as gone")
    assert len(calls) == 3


def test_a_live_group_reads_as_not_gone_and_a_reaped_one_as_gone():
    """No behaviour change on Linux: a real session's group reads as not gone while it runs, and
    as gone once killed and reaped. Green on 6a87018 by design; it pins what the fix must keep."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                             start_new_session=True)
    try:
        assert _group_gone(child.pid) is False
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=60)
        _wait_for(lambda: _group_gone(child.pid), "the killed and reaped group to read as gone")
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


@pytest.mark.parametrize("answer", [_eperm(), ProcessLookupError(errno.ESRCH, "gone")],
                         ids=["EPERM", "just-gone"])
def test_the_cleanup_of_a_group_that_answers_EPERM_or_has_just_gone_does_not_raise(
        monkeypatch, answer):
    """The module's `finally` cleanup does not replace a real failure with an unrelated error:
    killing a group that answers EPERM (macOS, zombies) or that vanished since it was checked
    raises nothing. On 6a87018 the cleanup was a bare `os.killpg(…, SIGKILL)`, with no helper."""
    # imported here, so that its absence fails this test alone, not the file's collection
    from tests.test_a_rerun_after_an_interrupted_worktree_add_starts import _kill_group

    fake, calls = _killpg_answering(answer)
    monkeypatch.setattr(os, "killpg", fake)
    _kill_group(12345)
    assert calls == [(12345, signal.SIGKILL)]


def test_the_interrupt_s_cleanup_keeps_its_real_failure_when_the_group_answers_EPERM(
        monkeypatch, tmp_path):
    """`_interrupt`'s `finally` goes through `_kill_group`: a failure inside it surfaces as itself,
    not as the `PermissionError` a zombie group's SIGKILL answers on macOS. The helper alone was
    guarded on 2d5c3cd; putting the bare `os.killpg` back at the call site left the file 5 passed
    (review round 1)."""
    from types import SimpleNamespace

    from tests import test_a_rerun_after_an_interrupted_worktree_add_starts as module

    class Child:
        pid = 12345
        stdout = SimpleNamespace(close=lambda: None)
        _waited = False

        def wait(self, timeout=None):
            if not self._waited:
                self._waited = True
                raise RuntimeError("the real failure")
            return 0

        def poll(self):
            return 0

    (tmp_path / "started").touch()
    slow = SimpleNamespace(repo=tmp_path / "repo", started=tmp_path / "started",
                           release=tmp_path / "release")
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **kw: Child())
    fake, calls = _killpg_answering(_eperm())
    monkeypatch.setattr(os, "killpg", fake)
    with pytest.raises(RuntimeError, match="the real failure"):
        module._interrupt(slow, tmp_path / "root", "add_timed_out")
    assert calls == [(12345, 0), (12345, signal.SIGKILL)]
