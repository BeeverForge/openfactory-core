"""#623 — a branch another working tree holds is the person's tree, and the park says how to free it.

Two doors still carry git's own sentence rather than the box's: the race window (somebody checks
the branch out between the box's read of the porcelain and its `worktree add`), and a box caller
that does not catch `BranchHeldElsewhere`. That sentence reached the park as `job errored after
retries: worktree add failed: …` and was classified `unknown` ("I could not identify the cause").

MEASURED 2026-10-17: git 2.34.1 (ubuntu:22.04) says `is already checked out at '<path>'`, git
2.43.0 says `is already used by worktree at '<path>'`. Both are fed verbatim here. The box's own
sentence is built with the real `branch_held`, never a copy of its text.
"""

from __future__ import annotations

import pytest

from openfactory.adapters.sandbox.worktree import branch_held
from openfactory.techlead.classify import TREE, classify, remedy_for
from openfactory.techlead.voice import REMEDY

GIT_2_34 = "fatal: 'openfactory/28' is already checked out at '/x/review'"
GIT_2_43 = "fatal: 'openfactory/28' is already used by worktree at '/x/review'"


@pytest.mark.parametrize("git_said", [GIT_2_34, GIT_2_43])
def test_git_2_34_and_2_43_sentences_are_the_tree(git_said):
    note = f"job errored after retries: worktree add failed: Preparing worktree\n{git_said}"

    assert classify(note, state="on_hold").cause == TREE


@pytest.mark.parametrize("language", ["en", "pt-BR"])
@pytest.mark.parametrize("main", [False, True])
def test_the_park_says_free_the_branch_not_commit_or_stash(language, main):
    note = branch_held("openfactory/28", "/x/review tree", main=main, locked=False)

    remedy = remedy_for(classify(note, cause=TREE), language=language)

    assert REMEDY["why.tree-held"][language] in remedy.say
    assert REMEDY["why.tree"][language] not in remedy.say


@pytest.mark.parametrize("git_said", [GIT_2_34, GIT_2_43])
def test_git_s_own_sentence_gets_the_held_branch_remedy_too(git_said):
    remedy = remedy_for(classify(f"worktree add failed: {git_said}"), language="en")

    assert REMEDY["why.tree-held"]["en"] in remedy.say


def test_an_edit_in_the_way_still_says_commit_or_stash():
    note = ("error: Your local changes to the following files would be overwritten by merge:\n"
            "\tapp.py\nPlease commit your changes or stash them before you merge.")

    remedy = remedy_for(classify(note), language="en")

    assert REMEDY["why.tree"]["en"] in remedy.say
    assert REMEDY.get("why.tree-held", {}).get("en", "\0") not in remedy.say
