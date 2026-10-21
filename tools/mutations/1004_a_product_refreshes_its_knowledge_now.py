"""#1004 — a product's knowledge brought up to date when somebody asks, proven by breaking it.

FIVE CLAIMS, each cut here and each required to go red:

  1. **The answer comes at once and the pass runs on the worker.** The row starts the workflow and
     never waits for it, bounded by the flight's ceiling; the workflow's one activity has the pass's
     ceiling and a heartbeat, and the activity heartbeats while the pass runs.
  2. **One flight per product.** The workflow's id is the product's, whichever registry project
     asks, and a second ask while one runs is answered as joined — never a failure, never a
     second pass.
  3. **Every source, through the one indexer.** An asked pass hands the index the documents, the
     requirements and the board of every registry project of the product; the schedule hands it
     nothing an asked pass does not, and reads no board.
  4. **The outcome is said by an existing read, never silent.** `product_status` answers the
     record; a pass that failed, was stopped, or whose worker died is said as failed; a running
     pass says since when; a record that cannot be read is unknown, never "never"; a board that
     cannot be read, and requirements that cannot, are said — and an unread corpus never empties
     the index.
  5. **Admin only**, like `product_ingest`.

And, since #992: a product that started before its code is refreshed — the row needs no code — and
the board of a project with no code repository is never read, only said to wait.

The guard under test: `tests/test_a_product_refreshes_its_knowledge_now.py`.
"""

TEST = "tests/test_a_product_refreshes_its_knowledge_now.py"

CATALOG = "openfactory/actions/catalog.py"
REFRESH = "openfactory/product/refresh.py"
ACTIVITIES = "openfactory/runtime/temporal/activities.py"
WORKFLOW = "openfactory/runtime/temporal/workflow.py"

MUTATIONS = [
    # ── 1. at once, on the worker, bounded ────────────────────────────────────────────────────────
    ("the row waits for the pass instead of starting it", CATALOG,
     "        await client.start_workflow(\n"
     "            \"ProductKnowledgeRefreshWorkflow\", KnowledgeRefreshInput(project=proj.name),",
     "        await client.execute_workflow(\n"
     "            \"ProductKnowledgeRefreshWorkflow\", KnowledgeRefreshInput(project=proj.name),"),

    ("the flight is started with no ceiling", CATALOG,
     "            id=knowledge.workflow_id(proj), task_queue=TASK_QUEUE,\n"
     "            execution_timeout=knowledge.FLIGHT_CEILING)",
     "            id=knowledge.workflow_id(proj), task_queue=TASK_QUEUE)"),

    ("the pass's activity runs with no heartbeat timeout", WORKFLOW,
     "            heartbeat_timeout=KNOWLEDGE_PASS_HEARTBEAT,\n",
     ""),

    ("the activity runs the pass without heartbeating", ACTIVITIES,
     "    return await _turning(lambda _abandoned: _do_refresh_product_knowledge(inp),\n"
     "                          f\"refreshing the knowledge of {inp.project}\")",
     "    return await asyncio.to_thread(_do_refresh_product_knowledge, inp)"),

    # ── 2. one flight per product ─────────────────────────────────────────────────────────────────
    ("the flight is keyed by the registry project, not by the product", REFRESH,
     "    return f\"openfactory-product-refresh-{product_slug(product_key(project))}\"",
     "    return f\"openfactory-product-refresh-{product_slug(project.name)}\""),

    ("a second ask while one runs is answered as a failure", CATALOG,
     "        if \"AlreadyStarted\" not in type(exc).__name__:",
     "        if True:"),

    # ── 3. every source, through the one indexer ──────────────────────────────────────────────────
    ("an asked pass reads no board", ACTIVITIES,
     "                                         boards=True).sentence()",
     "                                         boards=False).sentence()"),

    ("an asked pass reads only the board of the project it was asked through", REFRESH,
     "    for member in members(project):",
     "    for member in [project]:"),

    ("an asked pass hands the index no requirements", REFRESH,
     "        synced = refresh(project, corpus=corpus, requirements_dir=requirements_dir,",
     "        synced = refresh(project, corpus=None, requirements_dir=requirements_dir,"),

    ("the schedule reads the boards too", ACTIVITIES,
     "    done = knowledge.documents_and_index(project, by=knowledge.SCHEDULE,\n"
     "                                         budget_seconds=DOCUMENT_PASS_SECONDS)",
     "    done = knowledge.documents_and_index(project, by=knowledge.SCHEDULE,\n"
     "                                         budget_seconds=DOCUMENT_PASS_SECONDS, boards=True)"),

    # ── 4. said by an existing read, never silent ─────────────────────────────────────────────────
    ("product_status does not answer the knowledge", CATALOG,
     "                knowledge=refreshed,\n",
     ""),

    ("documents that could not be read leave the pass recorded as refreshed", REFRESH,
     "        log.warning(\"the documents of %s could not be ingested\", name, exc_info=True)\n"
     "        done.outcome = FAILED\n",
     "        log.warning(\"the documents of %s could not be ingested\", name, exc_info=True)\n"),

    ("a pass stopped half-way is recorded under the outcome's default", REFRESH,
     "        # interrupted half-way must never be recorded under the outcome's default\n"
     "        done.outcome = FAILED\n",
     "        # interrupted half-way must never be recorded under the outcome's default\n"),

    ("a pass whose worker died is never said to have stopped", REFRESH,
     "    if stopped:",
     "    if False:"),

    ("a pass running now is not said", REFRESH,
     "    out[\"running_since\"] = live[0] if live else None",
     "    out[\"running_since\"] = None"),

    ("a record that cannot be read reads as a product never refreshed", REFRESH,
     "        out[\"degraded\"] = [\"the record of the product's knowledge refreshes could not be "
     "read — \"\n"
     "                           \"when it was last brought up to date is unknown, not never\"]\n",
     ""),

    ("a partial refresh is not counted as a refresh", REFRESH,
     "        if done.outcome in (REFRESHED, DEGRADED):",
     "        if done.outcome == REFRESHED:"),

    ("a board that cannot be read is not said", REFRESH,
     "        if cards is None:\n"
     "            done.degraded.append(",
     "        if cards is None:\n"
     "            continue\n"
     "            done.degraded.append("),

    ("an unread corpus is handed to the index, and empties its requirements unsaid", REFRESH,
     "    corpus = getattr(ctx, \"corpus\", None) if getattr(ctx, \"available\", True) else None",
     "    corpus = getattr(ctx, \"corpus\", None)"),

    ("an index another sync held is said to have been brought up", REFRESH,
     "        if one.busy:\n",
     "        if False:\n"),

    # ── 4b. a product before its code (#992) ──────────────────────────────────────────────────────
    ("the row waits for the code it does not need", CATALOG,
     "by name (`refresh._boards`)\n"
     "            needs_code=False,\n",
     "by name (`refresh._boards`)\n"),

    ("the board of a project before its code is read, not said to wait", REFRESH,
     "        if before_its_code(member):\n",
     "        if False:\n"),

    # ── 5. admin only ─────────────────────────────────────────────────────────────────────────────
    ("anybody who may read the product may make it spend on a refresh", CATALOG,
     "            run=_product_refresh,\n",
     "            run=_product_refresh,\n            needs_admin=False,\n"),
]
