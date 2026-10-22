"""The stack preflight sends a missing agent credential to the credential store the deployment
declares, not to `.env.compose` (#904), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/904_the_preflight_sends_the_credential_to_the_declared_store.py

Under `OPENFACTORY_CREDENTIAL_STORE=file` the worker reads the token from a file in
`OPENFACTORY_CREDENTIAL_DIR`, and the preflight, which runs before the stack and cannot see that
directory, still told the person to put it "— in .env.compose" (measured on cf7ec0f5). The claims,
each a row:

  1. a declared store other than `env` replaces the `.env.compose` location with the store's
     sentence, read over the deployment's settings (the file under the environment, #560);
  2. `env`, in any case, padded or empty, is the environment and keeps today's remedy (Q1);
  3. the store's sentence says this check does not read the store, being made to run before the
     stack, and names `openfactory doctor` as the check once it is up; it does not say the stack
     is down, which is false where the installer's last line runs it, inside the worker;
  4. the preflight names the store and never builds it: the CLI image may lack its add-on (#822);
  5. under `file` the sentence says which directory the file goes in, and which file: the one
     named after the setting the harness's repair asks for (the pool's own for a pool repair);
  6. `openfactory doctor`, which that sentence sends the person to, names the same store in its
     own remedy and not `.env.compose`, and keeps today's line under `env`;
  7. under a declared store a `.env.compose` that cannot be read is still said (#583).
  8. a refusal reaches the doctor's line too, with the store's own remedy as the repair, and
     its suffix names the declared store, not `.env.compose` (#822).
"""

TEST = "tests/test_preflight_sends_a_missing_agent_credential_to_the_store_the_deployment_declares.py"
PREFLIGHT = "openfactory/preflight.py"
DOCTOR = "openfactory/doctor.py"
REGISTRY = "openfactory/adapters/credential_store/registry.py"

MUTATIONS = [
    # 1. the declared store is where the remedy goes, read where the deployment keeps it
    ("TODAY'S DEFECT, BACK: every miss is sent to .env.compose", PREFLIGHT,
     '        if store == ENV:\n'
     '            return False, said + _unread(), f"{repair} — in .env.compose"\n'
     '        return False, said + _unread(), f"{repair} — {_in_the_store(store, kind, repair)}"\n',
     '        return False, said + _unread(), f"{repair} — in .env.compose"\n'),
    ("the preflight reads the declared store from the environment alone (#560 again)", PREFLIGHT,
     "        store = deployment_store(settings)\n",
     "        store = deployment_store()\n"),

    # 2. `env` is the environment
    ("`env` is taken for a declared store", PREFLIGHT,
     "        if store == ENV:\n",
     "        if False:\n"),
    ("the declared kind is compared as written, not normalised", REGISTRY,
     '            or "").strip().lower() or ENV',
     '            or "") or ENV'),

    # 3. the sentence's two halves
    # Re-pinned on the review's wording (review of #904): the check is "made to run before the
    # stack", true inside the worker as well, where the installer's last line runs it.
    ("the sentence drops `openfactory doctor`", PREFLIGHT,
     '"exists, so `openfactory doctor` checks it once the stack is up")',
     '"exists")'),
    ("the sentence drops that this check does not read the store and is made to run before the "
     "stack", PREFLIGHT,
     '"this check does not read that store, because it is made to run before the stack "\n'
     '            "exists, so `openfactory doctor` checks it once the stack is up")',
     '"so `openfactory doctor` checks it once the stack is up")'),
    ("the sentence says the doctor checks it, not when", PREFLIGHT,
     '"exists, so `openfactory doctor` checks it once the stack is up")',
     '"exists, so `openfactory doctor` checks it")'),
    ("the sentence says the stack is not up, false inside the running worker", PREFLIGHT,
     '"this check does not read that store, because it is made to run before the stack "\n'
     '            "exists, so',
     '"this check runs before the stack and cannot read that store, so'),

    # 4. named, never built
    ("the preflight builds the declared store to name it", PREFLIGHT,
     '    where = ""\n    if store == FILE:\n',
     "    from openfactory.adapters.credential_store import registry as _built\n"
     "    _built.build_store(store)\n"
     '    where = ""\n    if store == FILE:\n'),

    # 5. the file store's directory
    ("the file store's sentence names no directory", PREFLIGHT,
     '        where = (f"a file named after the setting ({named}) in the directory {DIR_VAR} names, "\n'
     '                 if named else f"a file named after the setting in the directory {DIR_VAR} names, ")',
     '        where = (f"a file named after the setting ({named}), "\n'
     '                 if named else "a file named after the setting, ")'),
    # 5b. the file store's file is the one the repair asks for (review of #904: both survived
    # while the test read `TOKEN in remedy`, which the harness's own repair text satisfies)
    ("the file store's sentence names no file", PREFLIGHT,
     '        named = next((n for n in credential_names(harness) if n in repair), "")\n',
     '        named = ""\n'),
    ("the file store's sentence always names the pool's file, for a single token too", PREFLIGHT,
     '        named = next((n for n in credential_names(harness) if n in repair), "")\n',
     '        named = credential_names(harness)[0]\n'),

    # 6. the doctor the sentence sends the person to (review of #904)
    ("THE DOCTOR'S DEFECT, BACK: its remedy says .env.compose under every store", DOCTOR,
     "    declared = deployment_store()\n    if declared == ENV:\n",
     "    declared = deployment_store()\n    if True:\n"),
    ("the doctor takes `env` for a declared store", DOCTOR,
     "    declared = deployment_store()\n    if declared == ENV:\n",
     "    declared = deployment_store()\n    if False:\n"),
    ("the doctor's remedy does not name the declared store's kind", DOCTOR,
     'where = f" — in the `{declared}` credential store this deployment declares ({STORE_VAR})"',
     'where = f" — in the credential store this deployment declares ({STORE_VAR})"'),
    ("the doctor's remedy does not say where the file store's file goes", DOCTOR,
     "        if declared == FILE:\n            where +=",
     "        if False:\n            where +="),
    ("the doctor's remedy borrows the preflight's \"cannot read\" half", DOCTOR,
     '            where += f", as a file named after the setting in the directory {DIR_VAR} names"',
     '            where += (f", as a file named after the setting in the directory {DIR_VAR} names"\n'
     '                      "; this check cannot read that store")'),

    # 7. the unreadable file is still said in the store branch (review of #904)
    ("the store branch drops that .env.compose could not be read", PREFLIGHT,
     '        return False, said + _unread(), f"{repair} — {_in_the_store(store, kind, repair)}"\n',
     '        return False, said, f"{repair} — {_in_the_store(store, kind, repair)}"\n'),

    # 8. a refusal reaches the doctor's line too, with the store's remedy as the repair (review of
    # #904, round 2: this cut survived the 72 covering modules)
    ("the doctor sends a refused credential back to .env.compose", DOCTOR,
     "    declared = deployment_store()\n",
     "    declared = ENV if repair and 'refusal' in repair[0] else deployment_store()\n"),
]
