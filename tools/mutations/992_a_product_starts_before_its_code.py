"""#992, proven by breaking it — a product can start before its code.

FOUR CLAIMS, each cut where it is decided:

  1. **The state is admitted and is never the current directory.** The registry admits a project
     with a context and no code and refuses one with neither; the link reads `sources: []` as a
     product that has not started, and keeps the isolation; the code's own resolver refuses it.
  2. **The family rule.** `perform` refuses every row that needs the code, by name, before it
     runs; a row says it needs the code unless it says otherwise; the reasons follow the rule.
  3. **What waits says so, at every door.** The acceptance, the conversation's breakdowns, the
     sink, the worker's report, pickup, the verbs that read the code, the doctor and the
     knowledge refresh.
  4. **The first source**: the context first, then the registry; once; on the context's forge;
     found, not written twice, when a scaffold listed it.

The guard under test is `tests/test_a_product_can_start_before_its_code.py`.
"""

TEST = T = "tests/test_a_product_can_start_before_its_code.py"

LAYER = "openfactory/actions/__init__.py"
BASE = "openfactory/actions/base.py"
CAT = "openfactory/actions/catalog.py"
REG = "openfactory/registry.py"
PROJECT = "openfactory/contracts/project.py"
CFG = "openfactory/product/config.py"
FACT = "openfactory/factory.py"
CLI = "openfactory/cli.py"
ACTS = "openfactory/runtime/temporal/activities.py"
BRK = "openfactory/product/breaking.py"
MOD = "openfactory/product/module.py"
CONF = "openfactory/product/confirm.py"
UNF = "openfactory/product/unfiled.py"
DOC = "openfactory/doctor.py"
BC = "openfactory/product/before_code.py"
LOCAL = "openfactory/adapters/forge/local.py"

MUTATIONS = [
    # ── 1. the state ─────────────────────────────────────────────────────────────────────────────
    ("the registry admits a project with neither a code nor a context repository", REG,
     "            if before_its_code(project) and not str(getattr(",
     "            if False and not str(getattr(",
     T + "::test_the_registry_admits_one_with_a_context_and_refuses_one_with_neither"),
    ("the registry gives a project its code a second time", REG,
     "            if not before_its_code(Project(**raw[name])):",
     "            if False:",
     T + "::test_the_registry_gives_a_project_its_code_once"),
    ("a stand-in that carries no `repo_path` is judged as a product before its code", PROJECT,
     "    return isinstance(repo, str) and not repo.strip()",
     '    return not str(repo or "").strip()',
     T + "::test_a_project_with_no_code_repository_is_before_its_code"),
    ("the registry keeps the context's name when the code's forge qualifies it", REG,
     '            if docs_repo and isinstance(entry.get("product"), dict):',
     "            if False:",
     T + "::test_the_registry_writes_the_contexts_name_as_the_codes_forge_addresses_it"),
    ("the link warns about a source repository that does not exist yet", CFG,
     "    code_less = before_its_code(project)\n", "    code_less = False\n",
     T + "::test_sources_empty_is_a_product_that_has_not_started_not_an_error"),
    ("a local row's own name, listed, admits a product of another name", CFG,
     "            code_less or not _listed(project, docs)):",
     "            not _listed(project, docs)):",
     T + "::test_the_declarations_that_must_agree_still_agree_when_there_is_no_source"),
    ("no code repository is read as the directory the process stands in", FACT,
     "    if before_its_code(project):\n        raise NoCodeYet(",
     "    if False:\n        raise NoCodeYet(",
     T + "::test_the_code_of_a_project_before_it_is_never_the_current_directory"),

    # ── 2. the family rule ───────────────────────────────────────────────────────────────────────
    ("perform runs a row that needs the code on a project before it", LAYER,
     "    if waits_for_code(found):\n        waiting = _waiting_for_its_code(",
     "    if False:\n        waiting = _waiting_for_its_code(",
     T + "::test_every_row_that_needs_the_code_refuses_a_project_before_it_by_name"
         "[product_break_down]"),
    ("a row added without a word about the code runs before it", BASE,
     "    needs_code: bool = True", "    needs_code: bool = False",
     T + "::test_the_catalogue_has_rows_on_both_sides_of_the_rule"),
    ("the breakdown is declared to work without the code", CAT,
     '            name="product_break_down",\n            scope=PRODUCT,\n',
     '            name="product_break_down",\n            scope=PRODUCT,\n'
     '            needs_code=False,\n',
     T + "::test_the_catalogue_has_rows_on_both_sides_of_the_rule"),
    ("the acceptance waits for the code, so nothing can be agreed before it", CAT,
     '            name="product_accept",\n            scope=PRODUCT,\n            needs_code=False,\n',
     '            name="product_accept",\n            scope=PRODUCT,\n',
     T + "::test_an_acceptance_records_the_promise_and_says_its_breakdown_waits"),
    ("every row says it may be refused for the code, whether or not it can be", LAYER,
     "                  and (r != NO_CODE_YET or waits_for_code(found))]",
     "                  ]",
     T + "::test_a_row_says_it_may_wait_for_the_code_exactly_when_it_does"),

    # ── 3. what waits says so ────────────────────────────────────────────────────────────────────
    ("the panel's acceptance starts a breakdown on the worker for a product with no code", CAT,
     "    if before_its_code(proj):\n        return _with_the_breakdown_waiting(",
     "    if False:\n        return _with_the_breakdown_waiting(",
     T + "::test_an_acceptance_records_the_promise_and_says_its_breakdown_waits"),
    ("the conversation starts a breakdown on the engine for a product with no code", BRK,
     "    if before_its_code(project):\n        log.info(",
     "    if False:\n        log.info(",
     T + "::test_every_conversation_door_into_a_breakdown_says_the_wait"),
    ("a written requirement stages no second yes when it has no card to give it on", CONF,
     '    if cards or code_less:\n        entry["next"] = {',
     '    if cards:\n        entry["next"] = {',
     T + "::test_every_conversation_door_into_a_breakdown_says_the_wait"),
    ("the sink asks a model to draft cards nothing could be worked in", MOD,
     "        if before_its_code(self.project):\n"
     "            from openfactory.product.voice import breakdown_waits_for_code",
     "        if False:\n"
     "            from openfactory.product.voice import breakdown_waits_for_code",
     T + "::test_the_breakdown_itself_files_nothing_and_asks_no_model"),
    ("the worker's report of the wait reads as a breakdown that filed nothing", CONF,
     "    if waiting is not None:\n", "    if False:\n",
     T + "::test_the_worker_reports_the_wait_as_the_module_said_it_and_files_no_front_as_left_out"),
    ("the wait is kept as a front the breakdown left out", UNF,
     '            and not getattr(r, "waits_for_code", False)\n', "",
     T + "::test_the_worker_reports_the_wait_as_the_module_said_it_and_files_no_front_as_left_out"),
    ("pickup polls a project before its code", ACTS,
     "        if before_its_code(p):\n", "        if False:\n",
     T + "::test_pickup_leaves_it_off_the_poll_list"),
    ("the knowledge refresh clones a code repository that does not exist", ACTS,
     '    if before_its_code(project):\n        return "no-repo"',
     '    if False:\n        return "no-repo"',
     T + "::test_the_knowledge_refresh_maps_no_code_and_clones_nothing"),
    ("box prove reads a project before its code", CLI,
     '    project = _with_its_code(_get_project(name), "proving its box")',
     "    project = _get_project(name)",
     T + "::test_a_verb_that_reads_the_code_refuses_it_and_writes_nothing_where_it_stands"
         "[verb0]"),
    ("project init scaffolds a manifest into the directory it stands in", CLI,
     '        project = _with_its_code(reg.get(name), "setting up its board and manifest")',
     "        project = reg.get(name)",
     T + "::test_a_verb_that_reads_the_code_refuses_it_and_writes_nothing_where_it_stands"
         "[verb3]"),
    ("the doctor says one red line per reader of the code", DOC,
     "    if said:\n        # ONE LINE FOR THE STATE", "    if False:\n        # ONE LINE FOR THE STATE",
     T + "::test_the_doctor_says_the_state_once_instead_of_a_line_per_reader_of_the_code"),

    # ── the start ────────────────────────────────────────────────────────────────────────────────
    ("a product started before its code is seeded with the project's own name as its source", BC,
     "            created, _ = seed_context_repository(project, coordinate, sources=[])",
     "            created, _ = seed_context_repository(project, coordinate, sources=[name])",
     T + "::test_a_product_starts_with_its_context_and_no_code"),
    ("starting a product again is refused instead of found", BC,
     "        project, registered = existing, False",
     '        raise Refused(CONFLICT, "already registered")',
     T + "::test_starting_it_again_finds_it_and_starting_one_with_code_is_refused"),
    ("a context named as the project's own code is accepted on one machine", BC,
     "        if coordinate == name:", "        if False:",
     T + "::test_a_context_nobody_could_read_is_refused_before_anything_is_written"),
    ("the local forge makes the current directory a context repository", LOCAL,
     "        if not answered:\n            # NO PATH IS NOT THE CURRENT DIRECTORY",
     "        if False:\n            # NO PATH IS NOT THE CURRENT DIRECTORY",
     T + "::test_the_local_forge_never_makes_the_current_directory_a_context_repository"),
    ("an Azure DevOps context with no organisation or project is accepted", BC,
     "        if not (org and ado_project and repository):", "        if False:",
     T + "::test_a_hosted_context_names_no_code_repository_on_any_axis"),

    # ── 4. the first source ──────────────────────────────────────────────────────────────────────
    ("the first source writes the registry before the context", BC,
     "    listed_now = _list_in_context(project, would_be, entry)\n"
     "    try:\n        registry.set_code(name, would_be)\n"
     "    except ValueError as exc:\n        raise Refused(CONFLICT, str(exc)) from None\n",
     "    try:\n        registry.set_code(name, would_be)\n"
     "    except ValueError as exc:\n        raise Refused(CONFLICT, str(exc)) from None\n"
     "    listed_now = _list_in_context(project, would_be, entry)\n",
     T + "::test_a_context_that_cannot_be_written_leaves_the_registry_as_it_was"),
    ("a source the context lists in another spelling is listed a second time", BC,
     "            if docs is not None and any(repo_match(entry, s) == MATCH_EXACT\n"
     "                                        for s in docs.sources):\n                return False",
     "            if False:\n                return False",
     T + "::test_a_context_that_already_lists_it_is_not_written_again"),
    ("a project with code is given a first source, and its context is written first", BC,
     "    if not before_its_code(project):\n        raise Refused(CONFLICT, f\"{name} already has",
     "    if False:\n        raise Refused(CONFLICT, f\"{name} already has",
     T + "::test_a_first_source_is_given_once"),
    ("a code repository on another forge is given to the product", BC,
     "    if foreign:\n        raise Refused(INVALID, f\"{ref!r} is not on the {kind} forge",
     "    if False:\n        raise Refused(INVALID, f\"{ref!r} is not on the {kind} forge",
     T + "::test_a_code_repository_on_another_forge_is_refused"),
    ("an Azure DevOps code repository in another organisation is given to the product", BC,
     '    if (theirs.get("organization") or "").lower() != (code.get("organization") or "").lower():',
     "    if False:",
     T + "::test_an_azure_code_repository_is_read_with_the_contexts_organisation"),
]
