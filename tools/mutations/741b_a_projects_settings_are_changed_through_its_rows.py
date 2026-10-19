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
  4. the command line maps onto the rows and writes nothing itself.
"""

TEST = "tests/test_the_installation_is_changed_through_its_rows.py"
LAYER = "tests/test_the_action_layer.py"
MODEL = "tests/test_the_model_is_set_from_the_cli.py"

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
    ("the command line writes a project's model itself again", CLI,
     "    _says_the_row(_perform(\"project_set_model\", project=name, model=model, "
     "role=role or \"\"), name)",
     "    ProjectRegistry().set_model(name, model, role=role)\n    typer.echo(\"✓\")", LAYER),
    ("`--role` is dropped on the way to the row, so a per-role model is set for every role", CLI,
     "project=name, model=model, role=role or \"\"), name)",
     "project=name, model=model, role=\"\"), name)", MODEL),
    # the two guards re-pointed through the row, each proven on its own hop
    ("the command asks the harness about the model before the row has saved it", CLI,
     "    _says_the_row(_perform(\"project_set_model\", project=name, model=model, "
     "role=role or \"\"), name)\n    if note := _model_recognition_note(name, model):\n"
     "        typer.echo(note)\n",
     "    if note := _model_recognition_note(name, model):\n        typer.echo(note)\n"
     "    _says_the_row(_perform(\"project_set_model\", project=name, model=model, "
     "role=role or \"\"), name)\n",
     "tests/test_a_model_nobody_can_run_is_not_a_setting.py"),
    ("`set-language` stops reaching its row", CLI,
     "    _says_the_row(_perform(\"project_set_language\", project=name, language=language), "
     "name)",
     "    _says_the_row(_perform(\"project_remove\", project=name), name)",
     "tests/test_a_project_can_change_the_language_it_speaks_first.py"),
]
