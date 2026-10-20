"""#788: the Kimi documents say where its read-only roles run, and that is where they run.

The claims, each held by a row of `TEST` (named per cut below):

  - C1. THE FACT. `sandbox/registry.py::judging_worktree` hands every judging role a host
    `WorktreeSandbox`, even for a project whose jobs run in a container, and that box runs a
    command in the room it is handed (`cwd=workspace.path`). Held by
    `test_a_judging_role_runs_on_the_host_even_where_the_project_boxes_its_jobs`.
  - C2. A Kimi question that disobeys its read-only instruction leaves its file in that host room.
    Held by `test_a_kimi_question_that_writes_leaves_its_file_in_the_host_room`, through the real
    `KimiAdapter.ask`.
  - C3. No document says a Kimi judging role is kept in a box or that its edit cannot outlive the
    run: the module, class and `ask()` docstrings of `kimi.py`, the `roles.py` module docstring,
    `changes/362.limitation.md`, ADR-0018 §2 and the Kimi bullet of `docs/configuration.md`. One
    cut per document puts a false clause back (three of them the very text main carried on
    620bb577). The ADR's original sentences under the table stay as history, so its cut puts the
    false clause INSIDE the 2026-10-20 amendment, where no later amendment answers it.
  - C4. Each of those documents says where the judging roles run (`judging_worktree` or "on the
    host") and that nothing commits from that room. One cut per document drops "nothing commits
    from"; one more drops the configuration bullet's only "on the host", the other arm of the check.

The fact cut points `run`'s `cwd` at `self.root.parent` rather than the plan's `self.root`:
`self.root` (the `worktrees` directory) does not exist in the test, so Popen would raise
`FileNotFoundError` and the row would be red for a crash; `self.root.parent` exists, and the row is
red for the reason it holds (`pwd -P` answers another directory; `wrote.txt` lands elsewhere).
"""

TEST = "tests/test_where_a_kimi_judging_role_runs_is_what_its_documents_say.py"
NO_BOX = TEST + "::test_no_document_says_the_kimi_roles_are_kept_in_a_box[{}]"
NAMES = TEST + "::test_each_document_names_where_the_kimi_judging_roles_run[{}]"
FACT = TEST + "::test_a_judging_role_runs_on_the_host_even_where_the_project_boxes_its_jobs"
WRITES = TEST + "::test_a_kimi_question_that_writes_leaves_its_file_in_the_host_room"

KIMI = "openfactory/adapters/agent/kimi.py"
ROLES = "openfactory/adapters/agent/roles.py"
NOTE = "changes/362.limitation.md"
ADR = "docs/adr/0018-harness-roles.md"
CONF = "docs/configuration.md"
WORKTREE = "openfactory/adapters/sandbox/worktree.py"
REGISTRY = "openfactory/adapters/sandbox/registry.py"

_RUN_CWD = "                command, shell=True, cwd=workspace.path,\n"
_JUDGING_RETURN = ("    return WorktreeSandbox(root=root, "
                   "extra_env=tuple(getattr(box, \"env\", None) or ()))\n")

MUTATIONS = [
    # ── C1 / C2: the fact the wording rests on ────────────────────────────────────────────────
    ("C1 the host box runs a command somewhere other than the room it is handed", WORKTREE,
     _RUN_CWD, "                command, shell=True, cwd=self.root.parent,\n",
     FACT),

    ("C2 the host box runs a command somewhere other than the room: the disobedient question's "
     "file is not in its room", WORKTREE,
     _RUN_CWD, "                command, shell=True, cwd=self.root.parent,\n",
     WRITES),

    ("C1 judging_worktree routes the judging roles into the project's container box", REGISTRY,
     _JUDGING_RETURN,
     "    return _container(image=getattr(box, \"image\", None))\n",
     FACT),

    # ── C3: a false clause back in each document ───────────────────────────────────────────────
    ("C3 kimi.__doc__ says again that no such edit outlives the run", KIMI,
     "   but stays where it was written.\n",
     "   but stays where it was written. No such edit outlives the run.\n",
     NO_BOX.format("kimi.__doc__")),

    ("C3 KimiAdapter.__doc__ is main's again: 'through the sandbox (never on the host)'", KIMI,
     '    """Kimi Code, driven non-interactively through whatever box the caller hands it.\n',
     '    """Kimi Code, driven non-interactively through the sandbox (never on the host).\n',
     NO_BOX.format("KimiAdapter.__doc__")),

    ("C3 KimiAdapter.ask.__doc__ says again it cannot escape the platform's own ephemeral box",
     KIMI,
     '        confines it to that room either."""\n',
     '        confines it to that room either. '
     'It cannot escape the platform\'s own ephemeral box."""\n',
     NO_BOX.format("KimiAdapter.ask.__doc__")),

    ("C3 roles.__doc__ says a disobedient kimi question writes inside their ephemeral box", ROLES,
     "kimi nothing does, and a question that disobeys its instruction writes on the host.\n",
     "kimi nothing does, and a question that disobeys its instruction writes inside their "
     "ephemeral box.\n",
     NO_BOX.format("roles.__doc__")),

    ("C3 the 0.7.0 limitation note says again that no such edit outlives the run", NOTE,
     "in a directory nothing commits from, and nothing confines a write to it.",
     "in a directory nothing commits from, and no such edit outlives the run.",
     NO_BOX.format("changes/362.limitation.md")),

    ("C3 the ADR-0018 amendment itself says a judging role cannot escape the box", ADR,
     "planner's edit reaches the pull request. With `--sandbox worktree` that workspace is itself "
     "on the\nhost.\n",
     "planner's edit reaches the pull request. With `--sandbox worktree` that workspace is itself "
     "on the\nhost. A judging role cannot escape the box it is handed.\n",
     NO_BOX.format("ADR-0018 section 2")),

    ("C3 the configuration bullet is main's again: 'a mode, not an enforced policy'", CONF,
     "  weaker: instruction only, with no mode and no policy.",
     "  weaker (a mode, not an enforced policy).",
     NO_BOX.format("docs/configuration.md Kimi bullet")),

    # ── C4: each document stops saying where the roles run ─────────────────────────────────────
    ("C4 kimi.__doc__ no longer says nothing commits from the room", KIMI,
     "it runs in a room nothing commits from (a temporary directory",
     "it runs in a room of its own (a temporary directory",
     NAMES.format("kimi.__doc__")),

    ("C4 KimiAdapter.__doc__ no longer says nothing commits from the room", KIMI,
     "in a room nothing commits from (see the module docstring",
     "in a room of its own (see the module docstring",
     NAMES.format("KimiAdapter.__doc__")),

    ("C4 KimiAdapter.ask.__doc__ no longer says nothing commits from the room", KIMI,
     "in a room\n        nothing commits from: an edit made while judging",
     "in a room\n        of its own: an edit made while judging",
     NAMES.format("KimiAdapter.ask.__doc__")),

    ("C4 roles.__doc__ no longer says nothing commits from the room", ROLES,
     "is one nothing commits from (a temporary directory",
     "is one of its own (a temporary directory",
     NAMES.format("roles.__doc__")),

    ("C4 the 0.7.0 limitation note no longer says nothing commits from the directory", NOTE,
     "in a directory nothing commits from,",
     "in a directory of their own,",
     NAMES.format("changes/362.limitation.md")),

    ("C4 the ADR-0018 amendment no longer says nothing commits from the rooms", ADR,
     "Each is a room nothing commits from, so",
     "Each is a room of its own, so",
     NAMES.format("ADR-0018 section 2")),

    ("C4 the configuration bullet no longer says nothing commits from the directory", CONF,
     "in a directory\n  nothing commits from. Don't put",
     "in a directory\n  of their own. Don't put",
     NAMES.format("docs/configuration.md Kimi bullet")),

    ("C4 the configuration bullet no longer says the questions run on the host", CONF,
     "the questions run on the host, in a directory",
     "the questions run elsewhere, in a directory",
     NAMES.format("docs/configuration.md Kimi bullet")),
]
