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
    ADR-0018 §2 and the Kimi bullet of `docs/configuration.md`. One
    cut per document puts a false clause back (three of them the very text main carried on
    620bb577). The ADR's original sentences under the table stay as history, so its cut puts the
    false clause INSIDE the 2026-10-20 amendment, where no later amendment answers it.
  - C4. Each of those documents says where the judging roles run (`judging_worktree` or "on the
    host") and that nothing commits from that room. One cut per document drops "nothing commits
    from"; one more drops the configuration bullet's only "on the host", the other arm of the check.
  - C5. `env context --ask` asks in the person's own checkout, and each document says so wherever
    it says "nothing commits from" (review of e2b57dd1, 2026-10-20, point 2). The fact is held by
    `test_a_kimi_question_asked_as_env_context_asks_leaves_its_file_in_the_persons_checkout`
    (`judging_worktree(None, root=<a git checkout>)`, the real `KimiAdapter.ask`, the disobeying
    stub, `?? wrote.txt`); the wording by
    `test_each_document_names_env_context_ask_wherever_it_says_nothing_commits_from`. One cut
    moves the room, one cut per document drops the exception clause.
  - C6. The independent review is an `ask()` NOT handed `judging_worktree`: `JobRunner._review`
    passes the job's own box and workspace to `HarnessReviewer.review`, so a Kimi reviewer's
    committed write is in the pushed branch (review of dc0efac4, 2026-10-20, point 1). The fact is
    held by `test_a_kimi_review_that_writes_reaches_the_pushed_branch` (the real `KimiAdapter`
    behind `HarnessReviewer`, the worktree box, a bare origin, `planner_stage` off, review at its
    advisory default); its cut hands the reviewer a fresh temporary room instead, the day the
    review moves into a judging room. The wording by
    `test_each_document_names_the_review_wherever_it_says_where_the_questions_run`: no document
    says every `ask()` goes through `judging_worktree`, and each paragraph that says "nothing
    commits from" names the review, where it runs and that its write can reach the pull request.
    One cut per document drops the review clause; one puts "every `ask()` runs" back.

RETIRED 2026-10-27 (#1149): the four cuts of `changes/362.limitation.md`, one each for C3 to C6.
Assembling 0.7.0's notes removes the fragment, and its text is now 0.7.0's frozen section of
`CHANGELOG.md`, so the guard no longer reads it and these rows would point at no file.

RE-PINNED (#788, review round 2, R2.1): the C3 and C5 anchors in `kimi.py`, `roles.py`, the 0.7.0
note and the configuration bullet moved when each gained the review clause; each cut still makes
the same claim false.

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
CHECKOUT = (TEST + "::test_a_kimi_question_asked_as_env_context_asks_leaves_its_file_in_the_"
            "persons_checkout")
EXCEPT = TEST + "::test_each_document_names_env_context_ask_wherever_it_says_nothing_commits_from[{}]"
REVIEW_FACT = TEST + "::test_a_kimi_review_that_writes_reaches_the_pushed_branch"
REVIEW = (TEST + "::test_each_document_names_the_review_wherever_it_says_where_the_questions_"
          "run[{}]")

KIMI = "openfactory/adapters/agent/kimi.py"
ROLES = "openfactory/adapters/agent/roles.py"
ADR = "docs/adr/0018-harness-roles.md"
CONF = "docs/configuration.md"
WORKTREE = "openfactory/adapters/sandbox/worktree.py"
REGISTRY = "openfactory/adapters/sandbox/registry.py"
MACHINE = "openfactory/orchestrator/machine.py"

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

    ("C5 the host box runs a command somewhere other than the room: the question asked as "
     "`env context --ask` asks leaves nothing in the person's checkout", WORKTREE,
     _RUN_CWD, "                command, shell=True, cwd=self.root.parent,\n",
     CHECKOUT),

    ("C1 judging_worktree routes the judging roles into the project's container box", REGISTRY,
     _JUDGING_RETURN,
     "    return _container(image=getattr(box, \"image\", None))\n",
     FACT),

    # ── C3: a false clause back in each document ───────────────────────────────────────────────
    ("C3 kimi.__doc__ says again that no such edit outlives the run", KIMI,
     "   and its edit reaches no pull request but stays where it was written, except `env context\n",
     "   and no such edit outlives the run, except `env context\n",
     NO_BOX.format("kimi.__doc__")),

    ("C3 KimiAdapter.__doc__ is main's again: 'through the sandbox (never on the host)'", KIMI,
     '    """Kimi Code, driven non-interactively through whatever box the caller hands it.\n',
     '    """Kimi Code, driven non-interactively through the sandbox (never on the host).\n',
     NO_BOX.format("KimiAdapter.__doc__")),

    ("C3 KimiAdapter.ask.__doc__ says again it cannot escape the platform's own ephemeral box",
     KIMI,
     '        its room either."""\n',
     '        its room either. It cannot escape the platform\'s own ephemeral box."""\n',
     NO_BOX.format("KimiAdapter.ask.__doc__")),

    ("C3 roles.__doc__ says a disobedient kimi question writes inside their ephemeral box", ROLES,
     "writes where it is asked: on the host, or in the job's workspace for the review.\n",
     "writes inside their ephemeral box.\n",
     NO_BOX.format("roles.__doc__")),

    # RETIRED 2026-10-27 (#1149): the C3 cut of `changes/362.limitation.md`. Assembling
    # 0.7.0's notes removes the fragment; its text is 0.7.0's frozen CHANGELOG.md section.

    # RE-PINNED (#788, task 21): the amendment's planner sentences grew the hold, so the cut now
    # anchors on the amendment's last line, still inside the dated paragraph.
    ("C3 the ADR-0018 amendment itself says a judging role cannot escape the box", ADR,
     "a project turned `planner_stage` on (ADR-0014).\n",
     "a project turned `planner_stage` on (ADR-0014). A judging role cannot escape the box it is "
     "handed.\n",
     NO_BOX.format("ADR-0018 section 2")),

    ("C3 the configuration bullet is main's again: 'a mode, not an enforced policy'", CONF,
     "  weaker: instruction only, with no mode and no policy.",
     "  weaker (a mode, not an enforced policy).",
     NO_BOX.format("docs/configuration.md Kimi bullet")),

    # ── C4: each document stops saying where the roles run ─────────────────────────────────────
    ("C4 kimi.__doc__ no longer says nothing commits from the room", KIMI,
     "in a room nothing\n   commits from (a temporary directory",
     "in a room of its\n   own (a temporary directory",
     NAMES.format("kimi.__doc__")),

    ("C4 KimiAdapter.__doc__ no longer says nothing commits from the room", KIMI,
     "project's box, in a room nothing commits from, except",
     "project's box, in a room of its own, except",
     NAMES.format("KimiAdapter.__doc__")),

    ("C4 KimiAdapter.ask.__doc__ no longer says nothing commits from the room", KIMI,
     "in a room\n        nothing commits from, except",
     "in a room\n        of its own, except",
     NAMES.format("KimiAdapter.ask.__doc__")),

    ("C4 roles.__doc__ no longer says nothing commits from the room", ROLES,
     "is one nothing commits from (a temporary directory",
     "is one of its own (a temporary directory",
     NAMES.format("roles.__doc__")),

    # RETIRED 2026-10-27 (#1149): the C4 cut of `changes/362.limitation.md`. Assembling
    # 0.7.0's notes removes the fragment; its text is 0.7.0's frozen CHANGELOG.md section.

    ("C4 the ADR-0018 amendment no longer says nothing commits from the rooms", ADR,
     "Each is a room\nnothing commits from, so",
     "Each is a room\nof its own, so",
     NAMES.format("ADR-0018 section 2")),

    ("C4 the configuration bullet no longer says nothing commits from the directory", CONF,
     "in a directory\n  nothing commits from, except",
     "in a directory\n  of their own, except",
     NAMES.format("docs/configuration.md Kimi bullet")),

    ("C4 the configuration bullet no longer says the questions run on the host", CONF,
     "the questions run on the host, in a directory",
     "the questions run elsewhere, in a directory",
     NAMES.format("docs/configuration.md Kimi bullet")),

    # ── C5: each document drops the `env context --ask` exception beside "nothing commits from" ──
    ("C5 kimi.__doc__ drops the env context --ask exception", KIMI,
     "except `env context\n   --ask`, which asks in the checkout it is pointed at (the person's own "
     "repository on a local\n   deployment), where a write is left in that working tree, and the "
     "independent review",
     "except the independent review",
     EXCEPT.format("kimi.__doc__")),

    ("C5 KimiAdapter.__doc__ drops the env context --ask exception", KIMI,
     "except `env context --ask`,\n    which asks in the checkout it is pointed at, and the "
     "independent review",
     "except the independent review",
     EXCEPT.format("KimiAdapter.__doc__")),

    ("C5 KimiAdapter.ask.__doc__ drops the env context --ask exception", KIMI,
     "except `env context --ask`, which asks in the checkout it is pointed\n        at, where a "
     "write is left in that working tree, and the independent review",
     "except the independent review",
     EXCEPT.format("KimiAdapter.ask.__doc__")),

    ("C5 roles.__doc__ drops the env context --ask exception", ROLES,
     "except `env context --ask`, which asks in\nthe checkout it is pointed at, where a write is "
     "left in that working tree, and the independent\nreview",
     "except the independent\nreview",
     EXCEPT.format("roles.__doc__")),

    # RETIRED 2026-10-27 (#1149): the C5 cut of `changes/362.limitation.md`. Assembling
    # 0.7.0's notes removes the fragment; its text is 0.7.0's frozen CHANGELOG.md section.

    ("C5 the ADR-0018 amendment lists the target checkout among the rooms nothing commits from "
     "again", ADR,
     "pull request, except\n`env context --ask`, which asks in the target checkout it is "
     "pointed at",
     "pull request, and that includes\n`env context --ask`, which asks in the target checkout it "
     "is pointed at",
     EXCEPT.format("ADR-0018 section 2")),

    ("C5 the configuration bullet drops the env context --ask exception", CONF,
     "except `env context --ask`, which asks in the checkout it is pointed at\n"
     "  and leaves a write in that working tree, and the independent review",
     "except the independent review",
     EXCEPT.format("docs/configuration.md Kimi bullet")),

    # ── C6: the review, the `ask()` that is not handed `judging_worktree` ──────────────────────────
    ("C6 the job's review asks in a fresh temporary room, not the job's workspace", MACHINE,
     "        review = self.reviewer.review(sandbox=sandbox, workspace=workspace,\n",
     "        review = self.reviewer.review(sandbox=sandbox, workspace=workspace.model_copy("
     "update={\"path\": __import__(\"tempfile\").mkdtemp()}),\n",
     REVIEW_FACT),

    ("C6 kimi.__doc__ says again that every ask() runs on the host", KIMI,
     "   Where an `ask()` runs is its caller's choice. A judging role's caller builds\n",
     "   Every `ask()` runs on the host, because each caller builds\n",
     REVIEW.format("kimi.__doc__")),

    ("C6 kimi.__doc__ drops the review exception", KIMI,
     ", and the independent review, which\n"
     "   runs in the job's box on the job's workspace before the push (`JobRunner._review` hands\n"
     "   `HarnessReviewer.review` both), where a write it commits, or one a review-repair pass then\n"
     "   sweeps in, can reach the pull request (measured in the review of dc0efac4, 2026-10-20).\n",
     ".\n",
     REVIEW.format("kimi.__doc__")),

    ("C6 KimiAdapter.__doc__ drops the review exception", KIMI,
     ", and the independent review, which runs in the\n"
     "    job's box on the job's workspace before the push, where its write can reach the pull "
     "request\n    (see",
     "\n    (see",
     REVIEW.format("KimiAdapter.__doc__")),

    ("C6 KimiAdapter.ask.__doc__ drops the review exception", KIMI,
     ", and the independent review, which runs in\n"
     "        the job's box on the job's workspace before the push (`HarnessReviewer.review`), "
     "where a\n        write it commits, or one a review-repair pass then sweeps in, can reach "
     "the pull request.\n",
     ".\n",
     REVIEW.format("KimiAdapter.ask.__doc__")),

    ("C6 roles.__doc__ drops the review exception", ROLES,
     ", and the independent\nreview, which runs in the job's box on the job's workspace before "
     "the push, where a write it\ncommits, or one a review-repair pass then sweeps in, can reach "
     "the pull request (the same test\nfile holds it);",
     ";",
     REVIEW.format("roles.__doc__")),

    # RETIRED 2026-10-27 (#1149): the C6 cut of `changes/362.limitation.md`. Assembling
    # 0.7.0's notes removes the fragment; its text is 0.7.0's frozen CHANGELOG.md section.

    ("C6 the ADR-0018 amendment drops the review exception", ADR,
     ",\nand the independent review, which runs in the job's box on the job's workspace before "
     "the push:\n",
     ".\nThe review runs before the push:\n",
     REVIEW.format("ADR-0018 section 2")),

    ("C6 the configuration bullet drops the review exception", CONF,
     ", and the independent review, which runs in the job's\n"
     "  box on the job's workspace before the push, where its write can reach the pull request "
     "(review\n  is on by default).",
     ".",
     REVIEW.format("docs/configuration.md Kimi bullet")),
]
