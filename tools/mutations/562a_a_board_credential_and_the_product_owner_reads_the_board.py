"""A credential for the board and nothing else, and the product owner reads the board (#562, the
API's half), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/562a_a_board_credential_and_the_product_owner_reads_the_board.py

The claims, each a row:

  1. a board row and the shared board token are scoped to the floor, and close the door;
  2. the product owner reads the board of a project with a product role, and no other, and never a
     pull request's diff through it;
  3. `people invite --board` invites to the board, and an invitation to both areas is refused;
  4. the readiness report counts a board credential as a closed door;
  5. a worktree workload never holds a board credential.
"""

TEST = "tests/test_a_board_credential_and_the_product_owner_reads_the_board.py"
LOCAL = "openfactory/identity/local.py"
APP = "openfactory/api/app.py"
CATALOG = "openfactory/actions/catalog.py"
ACTIONS = "openfactory/actions/__init__.py"
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
     "CLOSING_ENVS = (PEOPLE_ENV, SHARED_ENV, PRODUCT_PEOPLE_ENV, PRODUCT_SHARED_ENV, "
     "BOARD_PEOPLE_ENV,\n                BOARD_SHARED_ENV)",
     "CLOSING_ENVS = (PEOPLE_ENV, SHARED_ENV, PRODUCT_PEOPLE_ENV, PRODUCT_SHARED_ENV)"),
    ("a panel row outranks the board's shared token, as it did", LOCAL,
     "            if board_shared and hmac.compare_digest(token, board_shared):",
     "            if board_shared and hmac.compare_digest(token, board_shared) and not any(\n"
     "                    hmac.compare_digest(token, x.token)\n"
     '                    for x in _people(self._env.get(PEOPLE_ENV, ""))):'),
    ("a board row outranks the product's shared token", LOCAL,
     "            if product_shared and hmac.compare_digest(token, product_shared):",
     "            if product_shared and hmac.compare_digest(token, product_shared) and not any(\n"
     "                    hmac.compare_digest(token, x.token)\n"
     '                    for x in _people(self._env.get(BOARD_PEOPLE_ENV, ""))):'),

    # 2. the product owner's read
    ("TODAY'S RULE: the product owner is refused the board", APP,
     "        if _the_product_owners_board(path, scopes, query):\n            return None",
     "        if False:\n            return None"),
    ("the product owner reads the board of a project with no product role", APP,
     "    return _has_product_role(project)\n", "    return True\n"),
    ("the product owner reaches a name nobody registered", APP,
     "    except KeyError:\n        return False   # a project nobody registered",
     "    except KeyError:\n        return True   # a project nobody registered"),
    ("TODAY'S REVIEW: the product owner reads a pull request's diff through the board", APP,
     '    if not found or any(key == "pr" and value for key, value in parse_qsl(query)):',
     "    if not found:"),
    ("the middleware does not hand the gate the query", APP,
     "_ask_the_gate(request.url.path, _credential_of(request), request.url.query)",
     "_ask_the_gate(request.url.path, _credential_of(request))"),
    ("the gate's thread is not handed the query", APP,
     "    return await asyncio.to_thread(_gate_verdict, path, credential, query)",
     "    return await asyncio.to_thread(_gate_verdict, path, credential)"),
    ("the product owner reads every route under the board's prefix", APP,
     '_PRODUCT_BOARD_READ = re.compile(r"^/api/board/([^/]+)$")',
     '_PRODUCT_BOARD_READ = re.compile(r"^/api/board/([^/]+)(?:/.*)?$")'),

    # 3. the invitation
    # RE-PINNED (#741): the refusal moved out of `_people_invite`'s body and became the row's
    # declaration, `installation=True`, which `perform` asks for every row that changes the
    # installation. The claim is the same one — a scoped credential does not invite.
    ("a scoped credential invites an administrator", ACTIONS,
     "    if found.installation and by.scopes is not None:",
     "    if False:"),
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
     "    door_is_closed = sso or has_product or _set(*CLOSING_ENVS)",
     "    door_is_closed = sso or has_product or _set(*CLOSING_ENVS[:4])"),

    # 5. the workload
    # re-pinned 2026-10-18 (#742): the credential directory follows the board's credentials
    ("a worktree workload holds the board's credentials", WORKTREE,
     '                      "OPENFACTORY_BOARD_TOKEN", "OPENFACTORY_BOARD_TOKENS",\n',
     ""),
]
