"""No test and no mutation plan reads a release-note fragment, proven by adding a reader back
(review of #1151).

Run:  .venv/bin/python tools/mutate.py tools/mutations/1149_no_test_reads_a_release_note_fragment.py

The final's commit removes every fragment it assembles, so a reader turned red on 0.7.0's final
pull request and nowhere before it (#1149). Each row puts back one of the two readers #1151 retired:

  1. The Kimi documents' guard reads `changes/362.limitation.md` again, as a `DOCUMENTS` row.
     Held by `test_no_test_or_plan_names_a_fragment_in_its_code`, while the fragment is in the
     tree; right after a final `changes/` is empty and this row survives, which the guard's
     docstring says.
  2. Plan 788 cuts the fragment again. Held by `test_no_plan_cuts_a_fragment`, which applies
     whether the fragment is in the tree or not.
"""

TEST = "tests/test_no_test_reads_a_release_note_fragment.py"
NAMES = TEST + "::test_no_test_or_plan_names_a_fragment_in_its_code"
CUTS = TEST + "::test_no_plan_cuts_a_fragment"

KIMI_GUARD = "tests/test_where_a_kimi_judging_role_runs_is_what_its_documents_say.py"
PLAN_788 = "tools/mutations/788_the_kimi_documents_say_where_its_roles_run.py"

GUARD_RETIRED = ("    # RETIRED 2026-10-27 (#1149): `changes/362.limitation.md` was read here until "
                 "0.7.0's notes were\n")
PLAN_RETIRED = ("    # RETIRED 2026-10-27 (#1149): the C3 cut of `changes/362.limitation.md`. "
                "Assembling\n")

MUTATIONS = [
    ("the Kimi documents' guard reads the 0.7.0 note again", KIMI_GUARD, GUARD_RETIRED,
     '    "changes/362.limitation.md": lambda: (ROOT / "changes/362.limitation.md").read_text(\n'
     '        encoding="utf-8"),\n' + GUARD_RETIRED,
     NAMES),

    ("plan 788 cuts the 0.7.0 note again", PLAN_788, PLAN_RETIRED,
     '    ("C3 the 0.7.0 limitation note says again that no such edit outlives the run",\n'
     '     "changes/362.limitation.md", "nothing confines a write to any of them.",\n'
     '     "no such edit outlives the run.", NO_BOX.format("changes/362.limitation.md")),\n'
     + PLAN_RETIRED,
     CUTS),
]
