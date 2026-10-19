"""#901, proven by breaking it — a process group whose last members are unreaped zombies is not
gone yet, and the cleanup of an interrupted add's group never raises.

TWO CLAIMS, both about the helpers of
`tests/test_a_rerun_after_an_interrupted_worktree_add_starts.py` (#746's module), which on macOS
(Apple git 2.50.1, Python 3.13) was red in 6 of 10 runs on 6a87018:

  1. **`_group_gone` reads EPERM as "not gone yet"**: macOS answers `killpg(pgid, 0)` with EPERM
     while a killed group's last members are zombies awaiting reaping, so the wait keeps polling
     instead of raising, and never stops while the group still holds processes.
  2. **`_kill_group`, the module's `finally` cleanup, raises nothing** for a group that answers
     EPERM or vanished since it was checked, so a cleanup never replaces a test's real failure.

The guard is `tests/test_a_process_group_whose_last_members_are_zombies_is_not_yet_gone.py`, in a
file of its own (as #121's): a fake `os.killpg` drives the EPERM answer no Linux host gives, and a
real `start_new_session` child pins the Linux behaviour.
"""

TEST = "tests/test_a_process_group_whose_last_members_are_zombies_is_not_yet_gone.py"

INTERRUPTED = "tests/test_a_rerun_after_an_interrupted_worktree_add_starts.py"

_EPERM_CLAUSE = (
    "    except PermissionError:\n"
    "        # macOS answers EPERM while the killed group's last members are zombies awaiting reaping\n"
    "        # (#846's run, Apple git 2.50.1, Python 3.13: 6/10 red): not gone yet, never \"gone\".\n"
    "        return False\n"
)

MUTATIONS = [
    # ── claim 1: EPERM is not gone yet ──────────────────────────────────────────────────────────
    ("THE DEFECT: EPERM escapes `_group_gone`", INTERRUPTED,
     _EPERM_CLAUSE,
     ""),

    ("EPERM reads as gone, so the wait stops while the group still holds processes", INTERRUPTED,
     _EPERM_CLAUSE,
     _EPERM_CLAUSE.replace("        return False\n", "        return True\n")),

    # ── claim 2: the cleanup's kill raises nothing ──────────────────────────────────────────────
    ("the cleanup's kill lets EPERM escape", INTERRUPTED,
     "    with contextlib.suppress(ProcessLookupError, PermissionError):\n",
     "    with contextlib.suppress(ProcessLookupError):\n"),

    ("the cleanup's kill lets a just-vanished group escape", INTERRUPTED,
     "    with contextlib.suppress(ProcessLookupError, PermissionError):\n",
     "    with contextlib.suppress(PermissionError):\n"),
]
