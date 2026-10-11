"""A credential for the board and nothing else, and the product owner reads the board (#562, the
API's half), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/562a_a_board_credential_and_the_product_owner_reads_the_board.py

The claims, each a row:

  1. a board row and the shared board token are scoped to the floor, and close the door;
  2. the product owner reads the board of a project with a product role, and no other;
  3. `people invite --board` invites to the board, and an invitation to both areas is refused;
  4. the readiness report counts a board credential as a closed door;
  5. a worktree workload never holds a board credential.
"""

TEST = "tests/test_a_board_credential_and_the_product_owner_reads_the_board.py"
LOCAL = "openfactory/identity/local.py"
APP = "openfactory/api/app.py"
CATALOG = "openfactory/actions/catalog.py"
CLI = "openfactory/cli.py"
READINESS = "openfactory/onboarding/readiness.py"
WORKTREE = "openfactory/adapters/sandbox/worktree.py"

MUTATIONS = [
    # 1. the credential
    ("a board row is read by nobody", LOCAL,
     '            for person in _people(self._env.get(BOARD_PEOPLE_ENV, "")):',
     "            for person in []:"),
    ("a board row is an administrator", LOCAL,
     '                                   via="local", groups=(BOARD_GROUP,))',
     '                                   via="local")'),
    ("the shared board token is an administrator", LOCAL,
     '                return Subject(id="", display="somebody with the board token",\n'
     "                               via=UNKNOWN.via, groups=(BOARD_GROUP,))",
     "                return UNKNOWN"),
    ("the board variables leave the door open", LOCAL,
     "               (PEOPLE_ENV, SHARED_ENV, PRODUCT_PEOPLE_ENV, PRODUCT_SHARED_ENV,\n"
     "                BOARD_PEOPLE_ENV, BOARD_SHARED_ENV)):",
     "               (PEOPLE_ENV, SHARED_ENV, PRODUCT_PEOPLE_ENV, PRODUCT_SHARED_ENV)):"),

    # 2. the product owner's read
    ("TODAY'S RULE: the product owner is refused the board", APP,
     '_EVERY_AREA_PREFIXES = ("/api/preview/", "/api/board/")',
     '_EVERY_AREA_PREFIXES = ("/api/preview/",)'),
    ("the product owner reads every client's board", APP,
     "    if scopes is not None and actions.FLOOR not in scopes and not _has_product_role(proj):",
     "    if False:"),

    # 3. the invitation
    ("an invitation to the board is an administrator's", CATALOG,
     "                                                   (BOARD_GROUP,) if boarded else ()),",
     "                                                   ()),"),
    ("an invitation to both areas is issued", CATALOG,
     "    if scoped and boarded:\n        return refused(",
     "    if False:\n        return refused("),
    ("the shell drops `--board`", CLI,
     '        board="yes" if board else ""))',
     '        board=""))'),

    # 4. the readiness report
    ("a deployment with only board credentials is reported open", READINESS,
     "    door_is_closed = sso or has_product or _set(PEOPLE_ENV, SHARED_ENV, BOARD_PEOPLE_ENV,\n"
     "                                                BOARD_SHARED_ENV)",
     "    door_is_closed = sso or has_product or _set(PEOPLE_ENV, SHARED_ENV)"),

    # 5. the workload
    ("a worktree workload holds the board's credentials", WORKTREE,
     '                      "OPENFACTORY_BOARD_TOKEN", "OPENFACTORY_BOARD_TOKENS")',
     "                      )"),
]
