"""#623, proven by breaking it — a card's branch another working tree holds stops the job by name.

FOUR CLAIMS:

  1. **The box asks the porcelain who holds the branch before it writes anything**, names that
     tree and what frees it, and never removes, prunes or forces a worktree it did not create.
  2. **The machine holds the job for a person** at every door that checks a card's branch out,
     with `hold_cause` TREE and the marks that send a resume back to the pull request.
  3. **The workflow parks on it and `resume` runs the same pass again**, refunded, with no seal.
  4. **Git's own sentence reads as the person's tree**, and the park says how to free the branch.

The guards are real git (task 1's and 5's files), the real workflow in a time-skipping engine
(task 7's), and the classifier fed git's measured sentences and the real `branch_held` (task 9's).

NOT A ROW, AND WHY: "`branch_held` quotes git's output instead of the porcelain". The sentence is
built from a `WorkingTree`, and the function has no repository to ask git in, so the cut cannot be
written as a one-site change. The claim it stood for — the sentence does not depend on git's
wording or locale — is held by the first row: with the porcelain read answering `None`, git's
sentence is what reaches the person, and the locale test goes red.
"""

TEST = "tests/test_a_branch_checked_out_elsewhere_holds_the_job.py"

BOX = "openfactory/adapters/sandbox/worktree.py"
MACHINE = "openfactory/orchestrator/machine.py"
WORKFLOW = "openfactory/runtime/temporal/workflow.py"
CLASSIFY = "openfactory/techlead/classify.py"

RUNNER_TEST = "tests/test_an_adjust_on_a_branch_checked_out_elsewhere_holds_for_a_person.py"
WORKFLOW_TEST = "tests/test_a_held_branch_holds_the_adjust_and_resume_asks_again.py"
CLASSIFY_TEST = "tests/test_git_s_own_sentence_about_a_held_branch_is_read_as_the_tree.py"

MUTATIONS = [
    ("THE DEFECT ITSELF: nobody is ever read as holding the branch, and git's sentence is passed "
     "on", BOX,
     "    held = gitworktrees.holder_of(trees, branch)\n",
     "    held = None\n"),

    ("the same cut, seen from the machine: an adjust on a held branch raises out of the runner",
     BOX,
     "    held = gitworktrees.holder_of(trees, branch)\n",
     "    held = None\n", RUNNER_TEST),

    ("the check is moved after the writes: only the retry after `worktree add` asks, so the "
     "person's remote-tracking ref has already moved", BOX,
     "        held = _holder(repo_path, branch)\n"
     "        if held is not None:\n"
     "            raise _branch_held_elsewhere(branch, held, repo_path=repo_path, "
     "rebuilt=rebuilt,\n"
     "                                         ours=wt)\n"
     "        # WHEN THE REMOTE IS THIS REPOSITORY",
     "        # WHEN THE REMOTE IS THIS REPOSITORY"),

    ("the box's own leftover is not cleared first, so it is refused as somebody else's tree",
     BOX,
     "        self._clear_our_own(repo_path, wt)\n"
     "        # DECIDE BEFORE YOU WRITE",
     "        # DECIDE BEFORE YOU WRITE"),

    ("the blanket `worktree prune` is back, and a person's registration on a missing disk goes",
     BOX,
     "        self._clear_our_own(repo_path, wt)\n",
     "        self._clear_our_own(repo_path, wt)\n"
     '        _run(["git", "-C", str(repo_path), "worktree", "prune"])\n'),

    ("the porcelain is not asked again after git refuses the add, so a branch taken in the "
     "window between the read and the add fails the job with git's sentence", BOX,
     "            # passed on.\n"
     "            held = _holder(repo_path, branch)\n"
     "            if held is not None:\n"
     "                raise _branch_held_elsewhere(branch, held, repo_path=repo_path, "
     "rebuilt=rebuilt,\n"
     "                                             ours=wt)\n",
     "            # passed on.\n"),

    ("a bare `locked` line (a lock with no reason) is not read, so the person is told to remove a "
     "tree git refuses to remove",
     "openfactory/adapters/gitworktrees.py",
     '        elif line == "locked" or line.startswith("locked "):\n',
     '        elif line.startswith("locked "):\n'),

    ("the person's own checkout is told `git worktree remove`, which git refuses on a main tree",
     BOX,
     "    if main:\n",
     "    if False:\n"),

    ("a locked review tree is told to remove it, which git refuses before an unlock", BOX,
     '    unlock = f"`{git} worktree unlock {where}`, then " if locked else ""\n',
     '    unlock = ""\n'),

    # ── review of 268c726: what the person was told to keep survives ───────────────────────────
    ("the box's own tree a person locked is removed anyway, and the rmtree deletes what they kept",
     BOX,
     "                if tree.locked:\n",
     "                if False:\n"),

    ("every door is read as the one that keeps the branch, so a fresh or hosted job tells the "
     "person to commit onto a branch it then builds again", BOX,
     "        rebuilt = not (checkout_existing and _is_this_repo(remote_url, repo_path))\n",
     "        rebuilt = False\n"),

    ("the person's own checkout on a rebuild door is told to switch away, which leaves its "
     "commits on the branch the job deletes", BOX,
     "        if rebuilt:\n"
     '            return (f"{head} {again}move that checkout',
     "        if False:\n"
     '            return (f"{head} {again}move that checkout'),

    ("a tree whose directory is not there is told to commit or stash in it", BOX,
     "    gone = not tree.main and not Path(tree.path).exists()\n",
     "    gone = False\n"),

    ("the commands lose `-C <repo>`, and pasted outside the repository they answer \"is not a "
     "working tree\"", BOX,
     '    git = f"git -C {shlex.quote(repo)}" if repo else "git"\n',
     '    git = "git"\n'),

    ("an address pass a tree held leaves \"pass N carries …\" standing alone on the pull request",
     "openfactory/runtime/temporal/activities.py",
     "        if result.state == JobState.ON_HOLD and result.hold_cause == TREE:\n",
     "        if False:\n",
     "tests/test_a_reviewers_comments_reach_the_pass.py"),

    ("`run` lets the refusal escape instead of holding", MACHINE,
     "        except BranchHeldElsewhere as exc:\n"
     "            # A PERSON HAS THE BRANCH OUT (#623), and only they can free it.",
     "        except ZeroDivisionError as exc:\n"
     "            # A PERSON HAS THE BRANCH OUT (#623), and only they can free it.",
     RUNNER_TEST),

    ("`repair_ci` lets the refusal escape instead of holding", MACHINE,
     "        except BranchHeldElsewhere as exc:\n"
     "            # A PERSON HAS THE BRANCH OUT (#623): no agent ran",
     "        except ZeroDivisionError as exc:\n"
     "            # A PERSON HAS THE BRANCH OUT (#623): no agent ran",
     RUNNER_TEST),

    ("`review_pr` lets the refusal escape instead of holding", MACHINE,
     "        except BranchHeldElsewhere as exc:\n"
     "            # A PERSON HAS THE BRANCH OUT (#623): nothing was read",
     "        except ZeroDivisionError as exc:\n"
     "            # A PERSON HAS THE BRANCH OUT (#623): nothing was read",
     RUNNER_TEST),

    ("the resumed attempt's handle is dropped, so the next resume starts the session fresh",
     MACHINE,
     "                              hold_cause=TREE, resume_handle=resume_handle)\n",
     "                              hold_cause=TREE)\n",
     RUNNER_TEST),

    ("the repair's hold loses `merge_refused`, so a resume runs the whole job again instead of "
     "going back to the pull request", MACHINE,
     "                              pr_url=pr_url, merge_refused=True, code_changed=False,\n"
     "                              hold_cause=TREE)\n",
     "                              pr_url=pr_url, code_changed=False,\n"
     "                              hold_cause=TREE)\n",
     RUNNER_TEST),

    ("the workflow drops the TREE hold and reopens the gate over a pass that never ran",
     WORKFLOW,
     "            self._adjust_passes -= 1  # no agent ran: the pass is not spent\n"
     "            return passed\n",
     "            self._adjust_passes -= 1  # no agent ran: the pass is not spent\n"
     "            self._held_pass = self._refused_merge = None\n"
     "            return None\n",
     WORKFLOW_TEST),

    ("the held pass is never run again on resume, so the gate reopens without asking", WORKFLOW,
     "            if self._held_pass is not None:\n",
     "            if False:\n",
     WORKFLOW_TEST),

    ("a held re-review is charged though nothing was read", WORKFLOW,
     "                self._review_passes -= 1  # nothing was read: the pass is not spent\n",
     "",
     WORKFLOW_TEST),

    ("a held adjust is charged though no agent ran", WORKFLOW,
     "            self._adjust_passes -= 1  # no agent ran: the pass is not spent\n",
     "",
     WORKFLOW_TEST),

    ("git's own sentence about a held branch is `unknown` again", CLASSIFY,
     '    (TREE, _BRANCH_HELD, "another tree holds the branch"),\n',
     "",
     CLASSIFY_TEST),

    ("the park on a held branch says commit or stash", CLASSIFY,
     '        why = "why.tree-held" if _BRANCH_HELD.search(verdict.detail_source or "") '
     'else "why.tree"\n',
     '        why = "why.tree"\n',
     CLASSIFY_TEST),
]
