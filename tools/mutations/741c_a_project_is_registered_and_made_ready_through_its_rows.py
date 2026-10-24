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
     sentence names every step, and a step that raises, whichever it is, is a failed step with
     the others standing, said at the terminal and never as a traceback;
  4. running it again does only what is missing: a registered project is not written over, a
     declaration whose review is open is not proposed twice;
  5. the installation's rows are declared — and the guard sees a write past the catalogue's edge,
     `product_start`'s in `product/before_code.py` and `product_init`'s in `product/onboard.py`;
  6. before its code, a product is declared with no source: `product_init` runs for it, refuses a
     source, and lists nothing of its own;
  7. the row completes a board that is there already where its row says it may, as the command
     did before it mapped onto the row (#753's opt-in): it adds the column the board lacks, says
     `done` only when the board has a key it lacked, and says a column it declined to add;
  8. what a step says carries no credential: a clone that runs out of time is said in a sentence,
     and git's own words, and whatever a git call raises, are said with the credential the
     context repository's address carries withheld.
"""

TEST = "tests/test_the_installation_is_changed_through_its_rows.py"

CATALOG = "openfactory/actions/catalog.py"
CLI = "openfactory/cli.py"
API = "openfactory/api/app.py"
RERUN = "tests/test_a_rerun_of_init_gives_an_existing_local_board_its_review_column.py"
AC3 = "tests/test_a_board_that_maps_no_review_column_keeps_todays_board.py"
NO_CREDENTIAL = f"{TEST}::test_whichever_git_call_fails_and_however_the_answer_carries_no_credential"

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
     "    except Exception as exc:  # noqa: BLE001 — the context step before it stands, said "
     "with it\n",
     "    except ZeroDivisionError as exc:\n"),
    # a step that raises, whichever it is (review of #1085)
    ("a registry that cannot be written raises out of `project_init`", CATALOG,
     "    except Exception as exc:  # noqa: BLE001 — a registry that cannot be written is a "
     "failed step\n",
     "    except ZeroDivisionError as exc:\n"),
    ("a checkout that cannot be written takes the registration and the board down with it",
     CATALOG,
     "    except Exception as exc:  # noqa: BLE001 — a checkout that cannot be written is a "
     "failed step\n",
     "    except ZeroDivisionError as exc:\n"),
    ("a context repository not made for a reason nobody named raises out of `product_init`",
     CATALOG,
     "        except Exception as exc:  # noqa: BLE001 — a repository not made is a failed step, "
     "said\n",
     "        except RuntimeError as exc:\n"),
    ("the declaration's guard holds only what git raises again, so a credential that cannot be "
     "resolved takes the context step down with it", CATALOG,
     "    except Exception as exc:  # noqa: BLE001 — the context step before it stands, said "
     "with it\n",
     '    except (OSError, __import__("subprocess").SubprocessError) as exc:\n'),
    ("a step that raised logs its traceback, which a terminal prints above the steps", CATALOG,
     '        log.warning("the board step of %s raised: %s", project.name,\n'
     "                    first_message(exc, limit=300))\n",
     '        log.warning("the board step of %s raised: %s", project.name,\n'
     "                    first_message(exc, limit=300), exc_info=True)\n"),
    ("`project init` exits 0 when the registration failed", CLI,
     '    if any(one["step"] == "register" and one["state"] == STEP_FAILED for one in steps):\n',
     "    if False:\n"),

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

    # ── 7. an attached board is completed by the row (#753, restacked onto main) ────────────────
    ("the row skips an attached board's `create` again, so a re-run adds no column", CATALOG,
     '        if attached and not getattr(creator, "completes_an_attached_board", False):',
     "        if attached:",
     f"{RERUN}::test_the_rerun_adds_needs_review_between_in_review_and_needs_action[the row]"),
    ("the row says a board it completed was already there", CATALOG,
     "    if added:\n",
     "    if False:\n",
     f"{RERUN}::test_the_rerun_says_what_it_added[the row]"),
    ("the row decides `added` by the position-ordered sentence", CATALOG,
     "            added = (bool(keys_of(project) - keys_before) if keys_before is not None",
     "            added = (now != attached if keys_before is not None",
     f"{RERUN}::test_init_decides_added_by_the_keys_not_by_the_sentence[the row]"),
    ("the row leaves the column it declined to add out of what the step says", CATALOG,
     '    also = f"; {declined}" if declined else ""\n',
     '    also = ""\n',
     f"{AC3}::test_a_rerun_of_init_adds_no_second_needs_review_where_another_column_carries_it"),

    # ── 8. what a step says carries no credential (review of #1085) ─────────────────────────────
    ("a clone that runs out of time is said as its command, address and all", CATALOG,
     "    except subprocess.TimeoutExpired:\n        # SAID IN A SENTENCE, NEVER AS THE COMMAND",
     "    except ZeroDivisionError:\n        # SAID IN A SENTENCE, NEVER AS THE COMMAND",
     f"{TEST}::test_a_git_call_that_carries_the_credential_and_runs_out_of_time_is_said_as_one"),
    ("the declaration's guard says what was raised as it was raised", CATALOG,
     '                            f"{_withheld(exc, *withhold)[:300]}")',
     '                            f"{exc}")',
     f"{NO_CREDENTIAL}[raises with its command]"),
    ("a clone git refused is said in git's words, address and all", CATALOG,
     "{_withheld(cloned.stderr, *withhold)[-200:]}",
     "{cloned.stderr[-200:]}",
     f"{NO_CREDENTIAL}[exits naming its remote]"),
    ("a push git refused is said in git's words, address and all", CATALOG,
     "said = _withheld(ran.stderr or '', *withhold)[-200:]",
     "said = (ran.stderr or '')[-200:]",
     f"{NO_CREDENTIAL}[exits naming its remote]"),
    ("the credential the address carries is not handed to what withholds", CATALOG,
     "    withhold.append(_the_credential_in(url))\n",
     "",
     NO_CREDENTIAL),
    ("no credential is read off an address", CATALOG,
     '        return urlsplit(address).password or ""\n',
     '        return ""\n',
     NO_CREDENTIAL),
    ("withholding withholds nothing", CATALOG,
     "    return scrubbed(text, *secrets, limit=sys.maxsize)\n",
     "    return str(text)\n",
     NO_CREDENTIAL),
]
