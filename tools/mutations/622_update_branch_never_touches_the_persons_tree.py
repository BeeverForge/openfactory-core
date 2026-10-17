"""#622, proven by breaking it — bringing a job branch up to date never touches the person's tree.

THREE CLAIMS:

  1. **`update_branch` rebases in a scratch tree in every repository, bare or not.** The person
     stays on their branch, and an uncommitted change is no reason to stay `behind`.
  2. **Their `rebase.updateRefs` moves none of their branches.**
  3. **The cleanup removes the scratch tree's own registration and nothing else** — never
     `worktree prune`, which would drop a linked worktree of theirs whose directory is missing.

The guard is `tests/test_the_pull_request_lives_in_the_file.py`: real git, a person's repository
with a working tree.
"""

TEST = "tests/test_the_pull_request_lives_in_the_file.py"

FORGE = "openfactory/adapters/forge/local.py"

MUTATIONS = [
    ("THE DEFECT ITSELF: a repository with a tree is rebased in that tree again, which checks the "
     "head out over the person's branch", FORGE,
     "        if refused := self._rebase_in_a_scratch_tree(base, head, where):\n"
     '            log.warning("could not rebase %s onto %s — %s", head, base, refused)\n'
     "            return False\n",
     "        if not self._bare(where):\n"
     '            p = self._git("rebase", "--onto", base, merge_base, head, cwd=where)\n'
     "            if p.returncode != 0:\n"
     '                self._git("rebase", "--abort", cwd=where)\n'
     "                return False\n"
     "        elif refused := self._rebase_in_a_scratch_tree(base, head, where):\n"
     "            return False\n"),

    ("the person's `rebase.updateRefs` applies, and a branch of theirs inside the range moves",
     FORGE,
     '"rebase", "--no-update-refs", "--no-autosquash", base, cwd=tree)',
     '"rebase", "--no-autosquash", base, cwd=tree)'),

    ("the cleanup prunes, and a stale registration of the person's own goes with the scratch's",
     FORGE,
     '            self._git("worktree", "remove", "--force", tree, cwd=where)\n'
     "            shutil.rmtree(scratch, ignore_errors=True)\n",
     "            shutil.rmtree(scratch, ignore_errors=True)\n"
     '            self._git("worktree", "prune", cwd=where)\n'),

    ("a head checked out in a LINKED worktree is rebased under whoever has it", FORGE,
     "        if self._checked_out(head, where):\n"
     '            log.warning("%s is checked out — it will not be rebased under whoever has it", '
     "head)\n",
     "        if _same(self._worktree_of(head, where), where):\n"
     '            log.warning("%s is checked out — it will not be rebased under whoever has it", '
     "head)\n"),
]
