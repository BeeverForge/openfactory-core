"""#746, proven by breaking it — a re-run on the worktree box starts over its own tree that git has
forgotten or that its own interrupted `worktree add` left, and nothing else at its path is touched.

FOUR CLAIMS:

  1. **This repository's forgotten tree is removed, and only it** (`_a_tree_this_repository_forgot`):
     its `.git` file names this repository's `<common>/worktrees/`, relative or absolute, and the
     working-tree list, read, does not list it. Never when the list could not be read.
  2. **Anything else at the path is refused by name before anything is written** (`path_taken`):
     the branch is not deleted and no ref is fetched; the sentence names whose it is and a
     command that works as written, shell-quoted; an empty directory is used.
  3. **The box's own interrupted add is unlocked and removed only when git's lock bytes AND the
     box's mark prove it** (option A, the human's choice of 2026-10-18); a person's lock, another
     repository's mark, and an unread list leave it as it is. The mark lives exactly while the
     add runs, and the add runs under `LC_ALL=C`.
  4. **A lock the box cannot prove is named for what it may be**, a person's or an interrupted
     add's.

The guards are real git with real linked worktrees, the real `RepoCache`, and real child processes
killed while a smudge filter holds git's checkout open (tasks 2, 3 and 4's files).
"""

TEST = "tests/test_a_rerun_over_a_tree_git_has_forgotten_starts.py"

BOX = "openfactory/adapters/sandbox/worktree.py"
NOT_OURS = "tests/test_a_directory_at_the_box_s_path_that_is_not_this_repository_s_is_left_as_it_was.py"
INTERRUPTED = "tests/test_a_rerun_after_an_interrupted_worktree_add_starts.py"

MUTATIONS = [
    # ── claim 1: this repository's forgotten tree, and only it ──────────────────────────────────
    ("THE DEFECT ITSELF: no leftover is ever this repository's forgotten tree", BOX,
     "    if any(_same_dir(tree.path, wt) for tree in trees):\n"
     "        return False\n"
     "    return _admin_dir_of(repo_path, wt) is not None\n",
     "    return False\n"),

    ("any `.git` file naming a `worktrees/` admin dir counts, another repository's included", BOX,
     '    return named if _same_dir(named.parent, common / "worktrees") else None\n',
     "    return named\n",
     NOT_OURS),

    ("a forgotten-looking leftover is removed when the list could not be read", BOX,
     '            _run(["git", "-C", str(repo_path), "worktree", "remove", "--force", str(wt)])\n'
     "            return None\n",
     '            _run(["git", "-C", str(repo_path), "worktree", "remove", "--force", str(wt)])\n'
     "            if _admin_dir_of(repo_path, wt) is not None:\n"
     "                shutil.rmtree(wt, ignore_errors=True)\n"
     "            return None\n"),

    ("a relative gitdir is resolved against the process's cwd, not the tree", BOX,
     "        return (wt / target).resolve()\n",
     "        return Path(target).resolve()\n"),

    ("`--git-common-dir` is not joined to the repository path", BOX,
     "        return (Path(repo_path) / out.strip()).resolve()\n",
     "        return Path(out.strip()).resolve()\n"),

    ("THE ISSUE'S OWN FIX: whatever is at the path is removed, a clone, a person's directory or "
     "another repository's tree included", BOX,
     "        if _a_tree_this_repository_forgot(repo_path, wt, trees):\n",
     "        if os.path.lexists(wt):\n",
     NOT_OURS),

    # RETIRED 2026-10-18: "`.is_file()` on `wt/.git` becomes `.exists()`, so a clone counts". An
    # EQUIVALENT MUTANT, measured: it survived (task 3's file, 110 passed). A clone's `.git` is a
    # directory, and `open()` on it raises IsADirectoryError, which `_gitdir_named_by` already
    # answers as "names nothing"; no `.git` that exists and is not a regular file reads as a gitdir
    # line. The claim it stood for, a clone at the path is left byte for byte, is held by the
    # `a-clone` cases of task 3's file against rows 2 and 7.

    # ── claim 2: anything else is refused by name, before anything is written ──────────────────
    ("the pre-write refusal of a taken path is removed", BOX,
     "        taken = _what_is_at(wt) if trees is not None else None\n",
     "        taken = None\n",
     NOT_OURS),

    ("the refusal comes after `branch -D`", BOX,
     "        taken = _what_is_at(wt) if trees is not None else None\n",
     "        if not (checkout_existing and _is_this_repo(remote_url, repo_path)):\n"
     '            _run(["git", "-C", str(repo_path), "branch", "-D", branch])\n'
     "        taken = _what_is_at(wt) if trees is not None else None\n",
     NOT_OURS),

    ("another repository's live tree is told to `mv`, which breaks its registration", BOX,
     '    if what == "tree":\n'
     '        git = f"git -C {shlex.quote(owner)} worktree"\n',
     "    if False:\n"
     '        git = f"git -C {shlex.quote(owner)} worktree"\n',
     NOT_OURS),

    ("the paths in the sentence are not shell-quoted", BOX,
     '    where, mine = shlex.quote(path), "<a path of yours>"\n',
     '    where, mine = path, "<a path of yours>"\n',
     NOT_OURS),

    ("a symlink at the path is followed, and the job checks out into what it names", BOX,
     '        if wt.is_symlink():\n            return "symlink", "", False\n', "",
     NOT_OURS),  # review of 35ac306, point 1

    ("an empty directory at the path is refused too", BOX,
     "            if next(entries, None) is None:\n"
     "                return None\n",
     "            if False:\n"
     "                return None\n",
     NOT_OURS),

    # ── claim 3: the box's own interrupted add, proven by git's bytes AND its own mark ──────────
    ("any lock with the box's mark counts, a person's relock included", BOX,
     "    return locked == _GITS_OWN_LOCK and _a_mark_of(repo_path, wt)\n",
     "    return _a_mark_of(repo_path, wt)\n",
     INTERRUPTED),

    ("git's lock bytes alone count, a person's `--reason initializing` included", BOX,
     "    return locked == _GITS_OWN_LOCK and _a_mark_of(repo_path, wt)\n",
     "    return locked == _GITS_OWN_LOCK\n",
     INTERRUPTED),

    ("a bare lock (an empty `locked`) counts as git's own", BOX,
     "    return locked == _GITS_OWN_LOCK and _a_mark_of(repo_path, wt)\n",
     '    return locked.strip() in (b"initializing", b"") and _a_mark_of(repo_path, wt)\n',
     INTERRUPTED),

    ("the mark's repository is not compared: any mark at the path counts", BOX,
     "    return common is not None and held == _mark_bytes(common, wt)\n",
     "    return common is not None\n",
     INTERRUPTED),

    ("the interrupted add is unlocked and removed when the list could not be read", BOX,
     '            _run(["git", "-C", str(repo_path), "worktree", "remove", "--force", str(wt)])\n'
     "            return None\n",
     '            _run(["git", "-C", str(repo_path), "worktree", "unlock", str(wt)])\n'
     '            _run(["git", "-C", str(repo_path), "worktree", "remove", "--force", str(wt)])\n'
     "            return None\n",
     INTERRUPTED),

    ("the mark is unlinked in a `finally`, also when the add timed out", BOX,
     "        mark = _write_mark(repo_path, wt)\n"
     '        rc, out = _run(["git", "-C", str(repo_path), *add], env=_in_gits_own_words())\n'
     "        _unlink_mark(mark)\n",
     "        mark = _write_mark(repo_path, wt)\n"
     "        try:\n"
     '            rc, out = _run(["git", "-C", str(repo_path), *add], env=_in_gits_own_words())\n'
     "        finally:\n"
     "            _unlink_mark(mark)\n",
     INTERRUPTED),

    ("the mark is not unlinked after the add returned", BOX,
     "        _unlink_mark(mark)\n",
     "        pass\n",
     INTERRUPTED),

    ("the add inherits the deployment's locale", BOX,
     '*add], env=_in_gits_own_words())\n',
     "*add])\n",
     INTERRUPTED),

    ("the `worktree unlock` before `remove --force` is skipped", BOX,
     '                    rc, out = _run(["git", "-C", str(repo_path), "worktree", "unlock",\n'
     "                                    tree.path])\n",
     '                    rc, out = 0, ""\n',
     INTERRUPTED),

    ("a later add writes over an earlier interrupted add's mark, and unlinks it", BOX,
     "        if os.path.lexists(mark):\n",
     "        if False:\n",
     INTERRUPTED),

    # ── claim 4: an unproven lock is named for what it may be ────────────────────────────────────
    ("the unproven lock is said to be somebody's again", BOX,
     "    whose = (\", the job's own from an earlier pass, which is locked, by a person or by a \"\n"
     '             "git worktree add that was interrupted, and the box could not tell which, so it "\n'
     '             "was left as it is" if ours and locked else\n',
     "    whose = (\", the job's own from an earlier pass, which somebody locked, so it was left \"\n"
     '             "as it is" if ours and locked else\n',
     INTERRUPTED),
]
