"""No git maintenance runs behind a test's back, and a failed clone logs git's whole sentence
(#592), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/592_the_suite_runs_no_git_maintenance.py

A commit or a push ends with `git maintenance run --auto`, detached; newer git repacks the suite's
small fixture repositories while a test clones them by path, and about one CI run in ten failed.
The claims, each a row:

  1. the suite's git config turns off automatic maintenance, gc and receive's gc;
  2. the repo cache logs git's whole answer, not its last 160 characters;
  3. every git the suite starts sees that config: no fixture builds git's environment from
     nothing (review of #595).
"""

TEST = "tests/test_the_suite_runs_no_git_maintenance.py"
CONFTEST = "tests/conftest.py"
CACHE = "openfactory/runtime/repo_cache.py"
ATTACHED = "tests/test_a_file_is_attached_in_the_conversation.py"

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
    # ADDED 2026-10-10 (review of #595)
    ("the context fixture builds git's environment from nothing again", ATTACHED,
     '    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",\n',
     '    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",\n'),
    ("the guard reads dict literals and never a name assigned one", TEST,
     "isinstance(kw.value, ast.Name) and kw.value.id in built)",
     "False)"),
]
