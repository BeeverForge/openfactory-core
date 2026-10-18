"""#690: every ADR is indexed, takes its number once, and is linked from the records it amends.

Each cut removes one of the three properties the docs guards protect for ADR-0057, the record this
pull request adds. The threshold cut is the one a tree with no duplicate cannot catch by itself;
the helper's own test, given two records with one number, catches it.
"""

TEST = "tests/test_the_docs_do_not_drift.py"

MUTATIONS = [
    ("the index loses the new record's row", "docs/adr/README.md",
     "| [0057](0057-who-may-act", "| [0057](0057-gone"),

    ("an amended record's pointer to the new one is misspelt",
     "docs/adr/0016-slack-actions-authorization.md",
     "**Amended by:** [ADR-0057](./0057-who-may-act",
     "**Amended by:** [ADR-0057](./0057-who-may-akt"),

    ("the shared-number rule stops seeing a pair", "tests/test_the_docs_do_not_drift.py",
     "if len(v) > 1}", "if len(v) > 2}"),
]
