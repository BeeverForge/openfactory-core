"""A project is registered and made ready through its rows, and a row of several steps says what
each came to (#741, slice 3), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/741c_a_project_is_registered_and_made_ready_through_its_rows.py

The claims, each a group of rows:

  1. `project_add` registers what was asked once: the same request again changes nothing, an
     option given since is no disagreement, and a different request is refused;
  2. the doors map onto the rows and write nothing themselves, and the panel's is the
     administrator's;
  3. a row of several steps says what each step came to — a failed step is not a success, the
     sentence names every step, and a step that raises is a failed step with the others standing;
  4. running it again does only what is missing: a registered project is not written over, a
     declaration whose review is open is not proposed twice;
  5. the installation's rows are declared — and the guard sees a write past the catalogue's edge,
     `product_start`'s in `product/before_code.py` and `product_init`'s in `product/onboard.py`;
  6. before its code, a product is declared with no source: `product_init` runs for it, refuses a
     source, and lists nothing of its own.
"""

TEST = "tests/test_the_installation_is_changed_through_its_rows.py"

CATALOG = "openfactory/actions/catalog.py"
CLI = "openfactory/cli.py"
API = "openfactory/api/app.py"

MUTATIONS = [
    # ── 1. registered once ────────────────────────────────────────────────────────────────────
    ("the same request again is refused as a difference", CATALOG,
     "        if differs:\n",
     "        if True:\n"),
    ("a different address reads as what is registered, and the request is told nothing changed",
     CATALOG,
     "            same = want == have\n",
     "            same = True\n"),
    ("a board attached since reads as a disagreement, so adding again fails after an init",
     CATALOG,
     "                    and all(have.options.get(k) == v for k, v in want.options.items()))",
     "                    and have.options == want.options)"),

    # ── 2. the doors are mappings ──────────────────────────────────────────────────────────────
    ("`project add` writes the project itself beside its row", CLI,
     '    outcome = _perform("project_add", project=name, repo_path=repo_path,\n',
     "    from openfactory.contracts.project import Project\n"
     "    ProjectRegistry().add(Project(name=name, repo_path=repo_path))\n"
     '    outcome = _perform("project_add", project=name, repo_path=repo_path,\n'),
    ("the panel's door registers as the system rather than as whoever asked", API,
     '        "project_add", by=_actor(request), project=body.name, repo_path=body.repo_path,',
     '        "project_add", by=actions.SYSTEM, project=body.name, repo_path=body.repo_path,'),

    # ── 3. what each step came to ──────────────────────────────────────────────────────────────
    ("a failed step is answered as a success", CATALOG,
     '    if not any(s["state"] == STEP_FAILED for s in steps):\n',
     "    if True:\n"),
    ("the sentence says only the last step, so what was done before it is not said", CATALOG,
     '    said = "; ".join(str(s["said"]) for s in steps)\n',
     '    said = str(steps[-1]["said"])\n'),
    ("a board step that raises takes every step down with it", CATALOG,
     "    except Exception as exc:  # noqa: BLE001 — a step that raised is a failed step, said\n",
     "    except ZeroDivisionError as exc:\n"),
    ("a declaration whose git could not run takes the context step down with it", CATALOG,
     "        except (OSError, subprocess.SubprocessError) as exc:\n",
     "        except ZeroDivisionError as exc:\n"),

    # ── 4. only what is missing ────────────────────────────────────────────────────────────────
    ("`project_init` sets the language it was given on a project already registered", CATALOG,
     '            steps = [_step("register", STEP_ALREADY, f"{name} is already registered")]\n',
     '            if language:\n                registry.set_language(name, language)\n'
     '            steps = [_step("register", STEP_ALREADY, f"{name} is already registered")]\n'),
    ("a review already open is proposed again", CATALOG,
     '    if found := (already_proposed(forge, result.docs_repo, branch) or ""):\n',
     '    if found := "":\n'),

    # ── 5. declared, and seen past the catalogue's edge ────────────────────────────────────────
    ("`project_add` forgets that it changes the installation", CATALOG,
     '                      "language"),\n            installation=True,\n',
     '                      "language"),\n'),
    ("`product_start` forgets it again — a write only a reading past the catalogue's edge sees",
     CATALOG,
     "            # see it, so a board credential could start a product until this said so\n"
     "            installation=True,\n",
     "            # see it, so a board credential could start a product until this said so\n"),
    ("`product_init` forgets it — its write is `product.onboard.create_context_repository`'s",
     CATALOG,
     "            # the row itself and named as the first source's.\n"
     "            needs_code=False,\n            installation=True,\n",
     "            # the row itself and named as the first source's.\n"
     "            needs_code=False,\n"),

    # ── 6. before the code ─────────────────────────────────────────────────────────────────────
    ("`product_init` waits for the code again, so `product start`'s remedy is refused", CATALOG,
     "            # the row itself and named as the first source's.\n"
     "            needs_code=False,\n",
     "            # the row itself and named as the first source's.\n"
     "            needs_code=True,\n"),
    ("a source is listed for a product that can vouch for none", CATALOG,
     "    if given and before_its_code(found):\n",
     "    if False:\n"),
    ("a product before its code lists the project's own name as its source", CATALOG,
     "    own = [] if before_its_code(project) else [_source_repo(project)]\n",
     "    own = [_source_repo(project)]\n"),
]
