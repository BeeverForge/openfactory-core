"""The installation is changed through its rows, and only by its administrator (#741, slice 1),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/741a_the_installation_is_changed_through_its_rows.py

The claims, each a group of rows:

  1. a row that writes the installation is declared one, and a declared one writes it — read
     through an instance built inline, one bound to a name, and the poller's hold called by name
     two functions down;
  2. `perform` refuses an installation row to a scoped credential — the shared board and
     product tokens too, whose scope is their own whether or not they send a label — says so
     in its own reason, and still refuses an unscoped caller who is no admin;
  3. no front end writes what a row owns;
  4. a person revoked is gone, their old session too, and the last one stays while nothing else
     closes the door;
  5. a pause says what is still running, and an unread list is not a drained floor;
  6. the doctor's document is the row's, stamped with whose opinion it is, `ok` is about the
     doctor having run, and it answers a caller who is no admin;
  7. `product name` reads when no name is given, and `product declare` says when it cannot read
     and names the command's remedy for an empty repository;
  9. the doctor's probes and a declaration's read leave the loop the panel serves from.
  8. the front end's contract lists every installation row.
"""

TEST = "tests/test_the_installation_is_changed_through_its_rows.py"
LAYER = "tests/test_the_action_layer.py"
PEOPLE_TEST = "tests/test_a_person_is_invited_not_signed_up.py"
DOCTOR_TEST = "tests/test_doctor_json_is_a_versioned_contract.py"
NINA = "tests/test_the_product_role_is_called_nina.py"
DECLARE = "tests/test_a_preexisting_context_repo_is_declarable.py"
SHARED = "tests/test_a_shared_credential_is_who_it_is.py"

ACTIONS = "openfactory/actions/__init__.py"
CATALOG = "openfactory/actions/catalog.py"
PEOPLE = "openfactory/identity/people.py"
CLI = "openfactory/cli.py"
CONTRACT = "docs/reference/the-front-end-api.md"

MUTATIONS = [
    # ── 1. what writes the installation says so ────────────────────────────────────────────────
    ("a row that writes the registry inline forgets its declaration, so a board or a product "
     "credential reaches it", CATALOG,
     '            required=("project", "docs_repo"),\n            installation=True,\n',
     '            required=("project", "docs_repo"),\n'),
    ("a row that writes the people store through a name it bound forgets its declaration",
     CATALOG,
     '            required=("person",),\n            installation=True,\n'
     '            params={"person": "the person\'s id',
     '            required=("person",),\n'
     '            params={"person": "the person\'s id'),
    # RE-PINNED 2026-10-20: the row declares its refusal reasons (`refuses=`, #837) between its
    # runner and its parameters now; the claim is unchanged.
    ("a row that holds the poller two functions down forgets its declaration", CATALOG,
     '            run=_poller_pause,\n            refuses=(UNAVAILABLE,),\n'
     '            optional=("note",),\n            installation=True,\n',
     '            run=_poller_pause,\n            refuses=(UNAVAILABLE,),\n'
     '            optional=("note",),\n'),
    # RE-PINNED 2026-10-20: `refuses=` (#837) sits between the doctor's runner and its parameters.
    ("a row that changes nothing is declared an installation row, so the declaration stops "
     "meaning anything", CATALOG,
     '            run=_doctor,\n            refuses=(NOT_FOUND,),\n            required=("project",),\n',
     '            run=_doctor,\n            refuses=(NOT_FOUND,),\n            required=("project",),\n'
     '            installation=True,\n'),
    # RE-PINNED 2026-10-20: the doctor's probes run on a thread of their own now (claim 9).
    ("a read row starts writing the registry and nothing says it is the administrator's",
     CATALOG,
     "    report = await asyncio.to_thread(lambda: doc.diagnose(doc.probes_for(found)))\n",
     "    from openfactory.registry import ProjectRegistry\n\n"
     '    ProjectRegistry().set_language(project, "en")\n'
     "    report = await asyncio.to_thread(lambda: doc.diagnose(doc.probes_for(found)))\n"),

    # ── 2. the administrator's ─────────────────────────────────────────────────────────────────
    ("`perform` stops asking the installation, so a scoped credential changes the deployment",
     ACTIONS,
     "    if found.installation and by.scopes is not None:",
     "    if False:"),
    ("`perform` stops asking the installation, so the shared board token, the floor's, pauses "
     "pickup and revokes people with or without a label", ACTIONS,
     "    if found.installation and by.scopes is not None:",
     "    if False:", SHARED),
    ("the installation's refusal says the credential was scoped away from an area, so a front "
     "end sends it to a credential of another area that will not do either", ACTIONS,
     "            reason=NOT_THE_INSTALLATIONS,\n", "            reason=OUT_OF_SCOPE,\n", SHARED),
    ("revoking a person needs no admin, so a chat user outside `admins` takes people off the "
     "deployment", CATALOG,
     '            required=("person",),\n            installation=True,\n'
     '            params={"person": "the person\'s id',
     '            required=("person",),\n            installation=True,\n'
     '            needs_admin=False,\n'
     '            params={"person": "the person\'s id'),

    # ── 3. no front end writes what a row owns ─────────────────────────────────────────────────
    ("the command line writes the product role's name itself again", CLI,
     "    # A MAPPING ONTO THE `product_name` ROW (#741)",
     "    ProjectRegistry().set_agent_name\n    # A MAPPING ONTO THE `product_name` ROW (#741)",
     LAYER),

    # ── 4. a person revoked ────────────────────────────────────────────────────────────────────
    ("the fold ignores a withdrawal, so a revoked person signs in", PEOPLE,
     '        elif event == "withdrawn":', '        elif event == "withdrawn-never":'),
    ("a withdrawal leaves the sessions it should end, so an old one comes back the day the id "
     "registers again", PEOPLE,
     "            for h, s in list(snap.sessions.items()):\n"
     "                if s.person_id == ident:\n"
     "                    del snap.sessions[h]",
     "            pass"),
    ("an account's withdrawal expires, so the account comes back when it does", PEOPLE,
     "        }, expires_at=None if ident in snap.people else max(invited))",
     "        }, expires_at=int(self._now()) + INVITE_TTL_SECONDS)", PEOPLE_TEST),
    ("a revocation nobody signed reads the people store before it is refused", CATALOG,
     "    if not who:\n        return refused(INVALID, _people.UNSIGNED_WITHDRAWAL, person=ident)\n",
     ""),
    ("the last person is revoked and the panel opens to whoever arrives", CATALOG,
     "    if (registered and set(snap.people) == {ident}",
     "    if (False and registered and set(snap.people) == {ident}"),
    ("the last person is kept even when a credential keeps the door shut", CATALOG,
     "            and not refusals(CLOSING_ENVS)\n"
     "            and not any(value.strip() for value in held(CLOSING_ENVS).values())):",
     "            and True):"),

    # ── 5. a pause says what is still running ──────────────────────────────────────────────────
    ("a pause from the panel stops saying a job is still running", CATALOG,
     "    elif running:\n        said += (f\". The pause holds new pickups only",
     "    elif False:\n        said += (f\". The pause holds new pickups only"),
    ("an unread job list reads as a drained floor again", CATALOG,
     '    running = None if jobs is None else [j for j in jobs if j.get("status") == "running"]',
     '    running = [j for j in (jobs or []) if j.get("status") == "running"]'),

    # ── 6. one doctor ──────────────────────────────────────────────────────────────────────────
    ("the doctor row stops stamping whose opinion it is", CATALOG,
     "    document = doc.as_document(report, project=project, build=namespace.build_stamp())",
     '    document = doc.as_document(report, project=project, build=("", ""))', DOCTOR_TEST),
    ("the doctor needs an admin, so the floor's viewers cannot ask whether a project can run",
     CATALOG,
     '            required=("project",),\n            needs_admin=False,\n'
     '            # A PROJECT BEFORE ITS CODE IS DIAGNOSED',
     '            required=("project",),\n            # A PROJECT BEFORE ITS CODE IS DIAGNOSED'),
    ("a project that is not ready is a failure of the doctor rather than its answer", CATALOG,
     "    return done(said, **document)",
     '    return (done(said, **document) if document["ok"] else refused(FAILED, said))'),

    # ── 7. the product's own two ───────────────────────────────────────────────────────────────
    ("`product name` with no name writes one instead of reading it", CATALOG,
     "    if agent_name is None:\n        current = ",
     "    if False:\n        current = ", NINA),
    ("`product declare` says reachable over a repository it could not read", CATALOG,
     "    if ok:\n        return done(f\"{project}'s context repository is {repo} — recorded, "
     "and reachable\",",
     "    if True:\n        return done(f\"{project}'s context repository is {repo} — recorded, "
     "and reachable\",", DECLARE),

    ("`product declare` with an empty repository names a parameter instead of the command",
     CLI,
     '    if not (docs_repo or "").strip().strip("/"):\n',
     "    if False:\n"),

    # ── 8. the contract ────────────────────────────────────────────────────────────────────────
    ("the front end's contract stops listing a row a screen of one's own needs", CONTRACT,
     "| `people_revoke` | `person` | takes a person off the deployment",
     "| people revoke | `person` | takes a person off the deployment"),

    # ── 9. the panel's loop keeps serving ──────────────────────────────────────────────────────
    ("the doctor's probes run on the loop the panel serves from again", CATALOG,
     "    report = await asyncio.to_thread(lambda: doc.diagnose(doc.probes_for(found)))\n",
     "    report = doc.diagnose(doc.probes_for(found))\n"),
    ("a declaration's read runs on the loop the panel serves from again", CATALOG,
     "    ok, why = await asyncio.to_thread(context_reachability, found, repo)\n",
     "    ok, why = context_reachability(found, repo)\n"),
]
