"""#747, proven by breaking it — a cache sync never pulls the git directory out from under a job.

Run:  .venv/bin/python tools/mutate.py tools/mutations/747_a_running_jobs_worktree_holds_the_cache.py

THE CLAIMS, each held by a row:
  1. **The worktree box marks the worktree it adds**, in that worktree's own admin directory and
     in no other, on every door of `prepare`; a refused write is said and the job still starts.
  2. **`_needs_publish` holds the served tree while a marked worktree stands on it**, for both
     cache classes, and says so with `OPENFACTORY_CACHE_HELD`; a `.git/worktrees` it cannot read
     holds too ("could not see" is not "nothing").
  3. **A mark holds only while its worktree is on disk and younger than a day**; a stale one is
     passed over and said with `OPENFACTORY_CACHE_HOLD_EXPIRED`.
  4. **The unmoved sync reads no mark**: the marks are read only when a publish would happen.
  5. **The hold ends when git removes the worktree**: the box's `cleanup` and `prune` take the
     marker, and the next sync publishes the moved base.

The guards are real git: the real `RepoCache`/`SparseRepoCache` over a local origin and the real
`WorktreeSandbox.prepare` over the served checkout.
"""

TEST = "tests/test_a_cache_sync_never_pulls_the_git_directory_out_from_under_a_running_job.py"

BOX = "openfactory/adapters/sandbox/worktree.py"
CACHE = "openfactory/runtime/repo_cache.py"
MARKS = "openfactory/adapters/gitworktrees.py"

MARK_TEST = "tests/test_the_worktree_box_marks_the_worktree_it_adds_as_a_job.py"
RELEASE_TEST = "tests/test_a_job_releases_the_cache_when_git_removes_its_worktree.py"
DAY_TEST = "tests/test_a_crashed_jobs_marker_stops_holding_the_cache_after_a_day.py"

MUTATIONS = [
    # M1 — the box never marks
    ("M1 THE DEFECT ITSELF: prepare no longer marks the worktree it added, and the sync swaps the "
     "tree under the job", BOX,
     "            gitworktrees.mark_as_job(wt)\n",
     "            pass\n"),
    ("M1, seen from the box: no door of prepare leaves a marker", BOX,
     "            gitworktrees.mark_as_job(wt)\n",
     "            pass\n", MARK_TEST),
    ("M1, seen from git's cleanup: there is no marker for remove or prune to take, and nothing "
     "holds", BOX,
     "            gitworktrees.mark_as_job(wt)\n",
     "            pass\n", RELEASE_TEST),

    # M2 — the cache ignores the marks
    ("M2 _needs_publish ignores the marks and publishes on the old three reasons", CACHE,
     "        return not RepoCache._held_by_a_job(served, why)\n",
     "        return True\n"),
    ("M2, seen from the release: the first sync already swaps the tree the job stands on", CACHE,
     "        return not RepoCache._held_by_a_job(served, why)\n",
     "        return True\n", RELEASE_TEST),

    # M3 — the "still on disk" test
    ("M3 a marked worktree whose directory is gone still holds the tree", MARKS,
     "            if not where.exists():\n                continue\n",
     ""
     ),

    # M4, M5 — the day
    ("M4 the day is gone: a marker holds for ever", MARKS,
     "JOB_MARKER_MAX_AGE = 24 * 60 * 60\n",
     "JOB_MARKER_MAX_AGE = 10 ** 12\n", DAY_TEST),
    ("M5 the day compared the wrong way: a young marker is stale and an old one holds", MARKS,
     "(live if mark.age < JOB_MARKER_MAX_AGE else stale)",
     "(live if mark.age > JOB_MARKER_MAX_AGE else stale)", DAY_TEST),

    # M6 — the lines that say so
    ("M6a the hold is kept but not said", CACHE,
     "        log.warning(\"OPENFACTORY_CACHE_HELD %s would be replaced (%s), but a running job's \"\n"
     "                    \"worktree stands on it: %s. It is kept as it is until that worktree is \"\n"
     "                    \"removed, for at most %d h after it was marked.\",\n"
     "                    served, why, holders, gitworktrees.JOB_MARKER_MAX_AGE // 3600)\n",
     "        pass\n"),
    ("M6b a stale marker is passed over without a word", CACHE,
     "        for stale in marks.stale:\n            log.warning(",
     "        for stale in marks.stale:\n            continue\n            log.warning(",
     DAY_TEST),

    # M7 — the unmoved sync
    ("M7 the marks are read on every sync, before the head and dirty comparison", CACHE,
     "        head = _head(served)\n        if not head:\n",
     "        gitworktrees.live_job_marks(served)\n"
     "        head = _head(served)\n        if not head:\n"),

    # M8 — only the box's own admin directory
    ("M8 the marker is written into the repository's own .git instead of the worktree's admin "
     "directory", MARKS,
     '"rev-parse", "--absolute-git-dir"',
     '"rev-parse", "--git-common-dir"', MARK_TEST),

    # M9 — could not see
    ("M9 a .git/worktrees that cannot be read is read as no marks", MARKS,
     "    except OSError:\n        return None\n    return JobMarks(live, stale)\n",
     "    except OSError:\n        return JobMarks([], [])\n    return JobMarks(live, stale)\n"),

    # M10 — every cache class
    ("M10 the sparse cache publishes without asking _needs_publish", CACHE,
     '                                env).stdout.strip() == "true"\n'
     "        if self._needs_publish(served, master):\n",
     '                                env).stdout.strip() == "true"\n'
     '        if not (served / ".git").exists() or _head(served) != _head(master):\n'),

    # M11 — a refused write is said
    ("M11 a marker the disk refused is swallowed without a WARNING", BOX,
     "            log.warning(\"could not mark %s as a running job's worktree (%s) — a repository \"",
     "            pass\n            if False: log.warning(\"could not mark %s as a running job's "
     "worktree (%s) — a repository \"",
     MARK_TEST),
]
