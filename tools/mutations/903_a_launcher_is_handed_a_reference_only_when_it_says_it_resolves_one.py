"""A remote launcher is handed a stored secret's reference only when it says it resolves one (#903).

Run:
    .venv/bin/python tools/mutate.py \
      tools/mutations/903_a_launcher_is_handed_a_reference_only_when_it_says_it_resolves_one.py

The claims, one cut each:

- THE DECLARATION (`adapters/sandbox/registry.py`). Only a literal `True` declares, and a runner
  that declares but whose `launch` cannot take `references=` is refused by name when it is built.
  A runner the deployment lacks is "not installed", never "values".
- THE HAND-OVER (`credentials.box_launch_credentials`, `box_options`). A declaring launcher gets
  the reference and never the value, and the box reads that axis from the variable the launcher
  fills. A launcher that declares nothing is refused, in a sentence that names its box kind,
  whichever step reached the secret: the vendor's default variable and the deployment's generic
  pair included.
- THE LAUNCH (`activities._remote_launch`). A launcher that declares nothing is called with
  exactly the keywords it always was, and the refusal comes before `launch`. Every site that
  launches a remote box (a promotion phase, a re-review, a CI repair) comes through it and builds
  its box with the references.
- THE DOCTOR (`doctor.launcher_credentials_line`). It says what each remote row is handed, says a
  row whose runner is not installed, and fails the refusal the first job would meet. It asks only
  the axes `box_launch_credentials` asks.

- THE DOCS (`configuration.md`'s "A remote box", `07-extensibility.md` §10.1). They name the
  declaration, the doctor's words, the doctor's line and the refusal as the code exports them, so
  renaming any one of the four in the code turns the docs test red until the docs follow. A docs
  test that compared against a literal of its own would stay green under each of these cuts.
"""

DECLARES = "tests/test_a_launcher_declares_whether_it_resolves_credential_references.py"
NOTHING = "tests/test_a_launcher_that_declares_nothing_is_never_handed_a_stored_secret.py"
RESOLVES = "tests/test_a_launcher_that_resolves_references_is_handed_the_reference.py"
DOCTOR_TEST = "tests/test_the_doctor_says_what_each_launcher_is_handed.py"
DOCS_TEST = "tests/test_the_docs_say_what_each_launcher_is_handed.py"
SITES_TEST = "tests/test_every_remote_launch_site_hands_the_reference.py"

TEST = NOTHING

REGISTRY = "openfactory/adapters/sandbox/registry.py"
CREDENTIALS = "openfactory/credentials.py"
ACTIVITIES = "openfactory/runtime/temporal/activities.py"
DOCTOR = "openfactory/doctor.py"

MUTATIONS = [
    # ── the declaration ────────────────────────────────────────────────────────────────────────
    ("a truthy value is read as a declaration", REGISTRY,
     "    return getattr(runner, RESOLVES_REFERENCES_ATTR, None) is True",
     "    return bool(getattr(runner, RESOLVES_REFERENCES_ATTR, None))", DECLARES),
    ("a runner that declares and cannot take `references` is admitted", REGISTRY,
     "    if resolves_references(runner):\n        try:",
     "    if False:\n        try:", DECLARES),
    ("a runner the deployment lacks is not said as not installed", REGISTRY,
     "    except RunnerNotInstalled:\n        return \"not installed\"",
     "    except LookupError:\n        return \"not installed\"", DECLARES),

    # ── the hand-over ──────────────────────────────────────────────────────────────────────────
    ("the declaration is ignored: a declaring launcher is refused like any other", CREDENTIALS,
     "    declares = resolves_references(runner)",
     "    declares = False", RESOLVES),
    ("the declaration is ignored the other way: a declaring launcher is handed the value in "
     "`extra_env`", CREDENTIALS,
     "                    references[BOX_TOKEN_ENV[axis]] = held",
     "                    out[BOX_TOKEN_ENV[axis]] = credential_store.look(held).value", RESOLVES),
    ("the box keeps the project's `token_env` for an axis handed as a reference", CREDENTIALS,
     "        if BOX_TOKEN_ENV[axis] in (references or {}):\n"
     "            options[\"token_env\"] = BOX_TOKEN_ENV[axis]\n",
     "", RESOLVES),
    ("the refusal no longer names the launcher's box kind", CREDENTIALS,
     "f\"credential store, and the `{kind}` box's launcher does not declare that \"",
     "f\"credential store, and the box's launcher does not declare that \"", NOTHING),
    ("a secret reached through the deployment's generic pair is not seen as held in a store",
     CREDENTIALS,
     "    if found.startswith(\"generic:\"):\n        found = _generic_reference(axis)",
     "    if found.startswith(\"generic:\"):\n        return \"\"", NOTHING),
    # Measured 2026-10-21: 12 cases red, the 8 vendor-default ones (jira, acme) and the 4 own-source
    # ones of azure_devops, whose secret is read under its vendor's default variable too.
    ("a secret reached through the vendor's default variable is not seen as held in a store",
     CREDENTIALS,
     "    if found.startswith(\"env:\") or not _stored_secret(found):\n        return \"\"\n"
     "    return found",
     "    if found.startswith(\"env:\") or not _stored_secret(found):\n        return \"\"\n"
     "    default = vendor_default_env(getattr(project, axis, None))\n"
     "    if default and found.endswith(\":\" + default):\n        return \"\"\n"
     "    return found", NOTHING),

    # ── the launch ─────────────────────────────────────────────────────────────────────────────
    ("`references` is passed to a launcher that declares nothing", ACTIVITIES,
     "    if references:\n        launch[\"references\"] = references",
     "    if True:\n        launch[\"references\"] = references", NOTHING),
    ("the credentials are asked after `launch`, so a refused job has already launched", ACTIVITIES,
     "    env, references = box_launch_credentials(project, kind, runner)\n"
     "    if references:\n        launch[\"references\"] = references\n"
     "    return runner.launch(build_box(references), extra_env={**extra_env, **env} or None, "
     "**launch)",
     "    result = runner.launch(build_box({}), extra_env=extra_env or None, **launch)\n"
     "    box_launch_credentials(project, kind, runner)\n"
     "    return result", NOTHING),

    # Measured 2026-10-22 (review of 17b05b8f): each of these three survived all 671 tests that
    # name the sites, until the sites module drove them; each is now `1 failed, 2 passed`.
    ("a promotion phase builds its box without the references, so the box reads the project's "
     "`token_env` the launcher does not fill", ACTIVITIES,
     "            tracker_options=box_options(project, \"tracker\", references=references),\n"
     "            forge_options=box_options(project, \"forge\", references=references),\n"
     "        )\n\n    return _remote_launch(\n        project, sandbox, box,",
     "            tracker_options=box_options(project, \"tracker\"),\n"
     "            forge_options=box_options(project, \"forge\"),\n"
     "        )\n\n    return _remote_launch(\n        project, sandbox, box,", SITES_TEST),
    ("a re-review launches past `_remote_launch`, so no credential is asked or handed",
     ACTIVITIES,
     "    return _remote_launch(\n        project, inp.sandbox, box, variant=\"-review\",\n"
     "        extra_env=",
     "    return remote_box(inp.sandbox).launch(\n        box({}), variant=\"-review\",\n"
     "        extra_env=", SITES_TEST),
    ("a CI repair or adjustment launches past `_remote_launch`, so no credential is asked or "
     "handed", ACTIVITIES,
     "    passed = _remote_launch(\n        project, inp.sandbox, box, "
     "variant=\"-adjust\" if human else \"-ci-repair\",",
     "    passed = remote_box(inp.sandbox).launch(\n        box({}), "
     "variant=\"-adjust\" if human else \"-ci-repair\",", SITES_TEST),

    # ── the doctor ─────────────────────────────────────────────────────────────────────────────
    ("the doctor's line never fails a stored secret the first job would refuse", DOCTOR,
     "        if held:\n            return (False,",
     "        if False:\n            return (False,", DOCTOR_TEST),
    ("the doctor says every remote row is handed references", DOCTOR,
     "            said.append(f\"`{kind}` {LAUNCHER_SAID[answer]}\")",
     "            said.append(f\"`{kind}` {LAUNCHER_SAID['references']}\")", DOCTOR_TEST),
    ("the doctor drops a row whose runner is not installed", DOCTOR,
     "        if answer != \"local\":\n            answers[kind] = answer",
     "        if answer not in (\"local\", \"not installed\"):\n            answers[kind] = answer",
     DOCTOR_TEST),
    ("the doctor asks the store only of the axes that declare an identity", DOCTOR,
     "            if not (declared or problem) and (reference := credentials._held_in_a_store(",
     "            if (declared or problem) and (reference := credentials._held_in_a_store(",
     DOCTOR_TEST),

    # ── the docs ───────────────────────────────────────────────────────────────────────────────
    ("the docs test compares against a literal rather than the export: the declaration's "
     "attribute", REGISTRY,
     "RESOLVES_REFERENCES_ATTR = \"resolves_references\"",
     "RESOLVES_REFERENCES_ATTR = \"resolves_refs\"", DOCS_TEST),
    ("the docs test compares against a literal rather than the export: the doctor's words for "
     "values", DOCTOR,
     "    \"values\": \"is handed values: short-lived minted tokens only\",",
     "    \"values\": \"is handed values: minted tokens only\",", DOCS_TEST),
    ("the docs test compares against a literal rather than the export: the doctor's line name",
     DOCTOR,
     "lambda: Finding(\"launcher_credentials\", *probes.launcher_credentials())",
     "lambda: Finding(\"launcher_creds\", *probes.launcher_credentials())", DOCS_TEST),
    ("the docs test compares against a literal rather than the export: the refusal sentence",
     CREDENTIALS,
     "f\"{RESOLVES_REFERENCES}, so it is handed only short-lived minted tokens and \"",
     "f\"{RESOLVES_REFERENCES}, so it is handed only minted tokens and \"", DOCS_TEST),
]
