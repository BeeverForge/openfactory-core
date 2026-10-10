"""No git maintenance runs behind a test's back, and a failed clone logs git's whole sentence
(#592), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/592_the_suite_runs_no_git_maintenance.py

A commit or a push ends with `git maintenance run --auto`, detached; newer git repacks the suite's
small fixture repositories while a test clones them by path, and about one CI run in ten failed.
The claims, each a row:

  1. the suite's git config turns off automatic maintenance, gc and receive's gc;
  2. the repo cache logs git's whole answer, not its last 160 characters.
"""

TEST = "tests/test_the_suite_runs_no_git_maintenance.py"
CONFTEST = "tests/conftest.py"
CACHE = "openfactory/runtime/repo_cache.py"

MUTATIONS = [
    ("TODAY'S DEFECT: the runner's git repacks the suite's repositories behind its back", CONFTEST,
     '        "[maintenance]\\n\\tauto = false\\n"\n'
     '        "[gc]\\n\\tauto = 0\\n"\n'
     '        "[receive]\\n\\tautogc = false\\n"\n',
     ""),
    ("a push still runs gc in the repository it lands in", CONFTEST,
     '        "[receive]\\n\\tautogc = false\\n"\n',
     ""),
    ("the log keeps the last 160 characters again", CACHE,
     "project, _scrub(out).strip()[-2000:])",
     "project, _scrub(out)[-160:])"),
]
