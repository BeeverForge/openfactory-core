"""A project's settings and its removal are changed through their rows (#741, slice 2), proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/741b_a_projects_settings_are_changed_through_its_rows.py

The claims, each a group of rows:

  1. every installation row that takes a project refuses one nobody registered, by name and with
     the roster, and writes nothing;
  2. the shell's flags and a front end's words set one preview policy, and a yes or no that is
     neither is refused before anything is written;
  3. the rows are the administrator's and the contract lists them;
  4. the command line maps onto the rows and writes nothing itself;
  5. the model is saved verbatim, before the shell asks the harness, and a front end is told the
     row did not ask;
  6. a preview's policy says what it refused, and a front end's words that are not a number of
     hours or a yes or no are refused.
"""

TEST = "tests/test_the_installation_is_changed_through_its_rows.py"
LAYER = "tests/test_the_action_layer.py"
MODEL = "tests/test_the_model_is_set_from_the_cli.py"
RECOGNISED = "tests/test_a_model_nobody_can_run_is_not_a_setting.py"

CATALOG = "openfactory/actions/catalog.py"
CLI = "openfactory/cli.py"
CONTRACT = "docs/reference/the-front-end-api.md"

MUTATIONS = [
    # ── 1. a project nobody registered ─────────────────────────────────────────────────────────
    ("a removal of a name nobody registered reports success", CATALOG,
     "    except KeyError:\n        return _no_such_project(project, so=\"nothing was removed\")\n",
     "    except KeyError:\n        pass\n"),
    ("the refusal of a ghost loses its roster, so the name that was meant is not on it", CATALOG,
     "    known = \", \".join(sorted(p.name for p in ProjectRegistry().list())) or \"none\"",
     "    known = \"none\""),
    # NOT A ROW: the preview row's own `_project` check could be cut, and the registry's writer
    # would still refuse the ghost before writing — the same answer reached one step later, which
    # no case can tell apart. The claim is held by the two rows above and the registry's own.

    # ── 2. one preview policy ──────────────────────────────────────────────────────────────────
    ("a front end's \"false\" is read as a yes, so a body lifts nothing it asks to", CATALOG,
     "    if _said_yes(value):\n        return True\n",
     "    if value:\n        return True\n"),
    ("a yes or no that is neither is read as no, so a form field lifts a look a person must take",
     CATALOG,
     "    raise ValueError(f\"{value!r} is neither yes nor no\")",
     "    return False"),
    ("a comma-separated list from a front end is one name", CATALOG,
     "    envs, args = _listed(env), _listed(build_arg)",
     "    envs, args = [str(env)] if env else [], _listed(build_arg)"),
    ("the names a preview may never receive are written and not said", CATALOG,
     "    if dropped:\n        said += (f\"; refused (a credential of the factory's own, or not a "
     "name): \"",
     "    if False:\n        said += (f\"; refused (a credential of the factory's own, or not a "
     "name): \""),

    # ── 3. the administrator's, and listed ─────────────────────────────────────────────────────
    ("a project's model is changed by a board or a product credential", CATALOG,
     "            required=(\"project\", \"model\"),\n            optional=(\"role\",),\n"
     "            installation=True,\n",
     "            required=(\"project\", \"model\"),\n            optional=(\"role\",),\n"),
    ("the contract stops listing the preview row", CONTRACT,
     "| `project_set_preview` | `project`,",
     "| project set preview | `project`,"),

    # ── 4. the command line maps ───────────────────────────────────────────────────────────────
    # RE-PINNED 2026-10-20, this row and the next two: the command prints its own success line
    # again, so it performs the row, refuses on the row's refusal, and then says what it saved.
    ("the command line writes a project's model itself again", CLI,
     "    outcome = _perform(\"project_set_model\", project=name, model=model, role=role or \"\")\n",
     "    ProjectRegistry().set_model(name, model, role=role)\n"
     "    outcome = _perform(\"project_set_model\", project=name, model=model, role=role or \"\")\n",
     LAYER),
    ("`--role` is dropped on the way to the row, so a per-role model is set for every role", CLI,
     "project=name, model=model, role=role or \"\")\n",
     "project=name, model=model, role=\"\")\n", MODEL),
    # the two guards re-pointed through the row, each proven on its own hop. THIS ONE IS THE CUT
    # THAT WALKED THROUGH THE OLD GUARD: it leaves the call's name in a comment above the note, and
    # the order of the words in the source was all that guard read. The guard runs the command now.
    ("the command asks the harness about the model before the row has saved it, with the row's "
     "call left in a comment where it was", CLI,
     "    outcome = _perform(\"project_set_model\", project=name, model=model, role=role or \"\")\n"
     "    if not outcome.ok:\n        _refuse_the_row(outcome, name)\n    scope = ",
     "    # _perform(\"project_set_model\", ...) saves; the harness is asked below\n"
     "    if note := _model_recognition_note(name, model):\n        typer.echo(note)\n"
     "    outcome = _perform(\"project_set_model\", project=name, model=model, role=role or \"\")\n"
     "    if not outcome.ok:\n        _refuse_the_row(outcome, name)\n    scope = ",
     RECOGNISED),
    ("`set-language` stops reaching its row", CLI,
     "    _says_the_row(_perform(\"project_set_language\", project=name, language=language), "
     "name)",
     "    _says_the_row(_perform(\"project_remove\", project=name), name)",
     "tests/test_a_project_can_change_the_language_it_speaks_first.py"),
    ("`project remove` takes the project out of the registry itself, beside its row", CLI,
     "    outcome = _perform(\"project_remove\", project=name)\n",
     "    ProjectRegistry().remove(name)\n    outcome = _perform(\"project_remove\", project=name)\n"),

    # ── 5. the model ───────────────────────────────────────────────────────────────────────────
    ("the model row trims the string it was given", CATALOG,
     "        ProjectRegistry().set_model(project, str(model), role=chosen)",
     "        ProjectRegistry().set_model(project, str(model).strip(), role=chosen)"),
    ("the model row lowercases the string it was given", CATALOG,
     "        ProjectRegistry().set_model(project, str(model), role=chosen)",
     "        ProjectRegistry().set_model(project, str(model).lower(), role=chosen)"),
    ("the model row answers a front end in silence about the harness", CATALOG,
     "                f\"restart needed (the registry is read per run). Not checked against the harness \"\n"
     "                f\"here: the first job proves it, and fails naming this model if the harness will \"\n"
     "                f\"not run it\", project=project, model=str(model), role=chosen, checked=False)",
     "                f\"restart needed (the registry is read per run)\", project=project,\n"
     "                model=str(model), role=chosen)"),

    # ── 6. what the preview row says ───────────────────────────────────────────────────────────
    ("`clear_env` is read and ignored", CATALOG,
     "        if _either(clear_env):\n            policy[\"env\"] = {}\n",
     "        _either(clear_env)\n"),
    ("hours that are not a number are saved as the default and reported as a success", CATALOG,
     "                raise ValueError(f\"{hours!r} is not a number of hours, 1 to 168\") from None",
     "                hours = None"),
    ("a network the policy refused is not said, so `egress: none` reads as what was asked",
     CATALOG,
     "    if network not in (None, \"\") and saved.network != str(network).strip():",
     "    if False:"),
]
