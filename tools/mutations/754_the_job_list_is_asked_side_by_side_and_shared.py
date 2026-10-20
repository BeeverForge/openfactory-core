"""#754: the job list asks about its jobs side by side, and readers together or right after share
one scan.

Claims, each held by the row named under it:

  - the jobs are asked about `OPENFACTORY_LIST_CONCURRENCY` at a time (8 unset), the value is the
    operator's and an unreadable one is said once;
  - the list is the one the sequential walk made: the same rows, in list order, `limit` counted on
    the rows shown, and a row that cannot be built fails the list with its own error;
  - a list that ran out of time leaves no question running behind it;
  - readers arriving together share one scan, and only for the same loop, client and question;
  - a reader within `LIST_TTL_S` of a scan that answered is handed its rows, a copy of its own,
    never across loops or clients, never a failure, and never past the window;
  - an engine remembered as silent refuses the list even when a list is remembered;
  - a write through this process, and the stream's blip, drop the remembered list.

THE DEFAULT TARGET IS ONE TEST, NOT THE FILE: the reference-row test in the same file stays red
until the configuration reference gains its row (the plan's task 11), and a red baseline refuses
the whole plan. Every row names its own test, so each cut is seen by the guard written for it.
The reference's own row ("the documented default is 16", cut in the document the guard reads)
joins this plan with that document row; until then its anchor would match nothing.

NOT DUPLICATED HERE: "one reader going away cancels the read under everybody waiting on it"
(`asyncio.shield(flight.task)` → a bare await) is a row of
`165_the_intake_memo_is_read_once_and_handed_out_as_a_copy.py`, on the same line the job list now
shares (`util/single_flight.py`). This job list's own guard for it,
`test_an_asker_that_goes_away_does_not_take_the_scan_from_the_others`, was measured red under that
cut on 2026-10-19 (scratch plan, 1/1 red), and is not written twice.
"""

TEST = ("tests/test_the_job_list_asks_about_its_jobs_eight_at_a_time.py::"
        "test_a_busy_floors_job_list_answers_inside_the_read_deadline")
VIEW = "openfactory/runtime/temporal/view.py"
SINGLE_FLIGHT = "openfactory/util/single_flight.py"
APP = "openfactory/api/app.py"

EIGHT = "tests/test_the_job_list_asks_about_its_jobs_eight_at_a_time.py::"
SAME = "tests/test_the_job_list_is_the_same_list_however_many_are_asked_at_once.py::"
TOGETHER = "tests/test_askers_that_arrive_together_share_one_job_list.py::"
AFTER = "tests/test_a_job_list_read_a_moment_ago_is_shared_and_never_across_loops.py::"
FRAME = "tests/test_a_frame_does_not_erase_what_it_omits.py::"

MUTATIONS = [
    # ── side by side, k at a time ───────────────────────────────────────────────────────────────
    ("one job is asked about at a time, so a busy floor's list overruns the deadline", VIEW,
     "    room = asyncio.Semaphore(k)",
     "    room = asyncio.Semaphore(1)"),

    ("one job is asked about at a time, and the peak of eight is never reached", VIEW,
     "    room = asyncio.Semaphore(k)",
     "    room = asyncio.Semaphore(1)",
     EIGHT + "test_eight_jobs_are_asked_about_at_once_when_the_operator_says_nothing"),

    ("the workflows are taken from the listing one at a time, so a batch is one job", VIEW,
     "        if len(batch) < k:\n            continue",
     "        if len(batch) < 1:\n            continue"),

    ("the operator's concurrency is never read, so it is always eight", VIEW,
     '    raw = (os.environ.get("OPENFACTORY_LIST_CONCURRENCY") or "").strip()',
     '    raw = ""',
     EIGHT + "test_the_operator_sets_how_many_jobs_are_asked_about_at_once"),

    ("an unreadable concurrency is said on every list, every stream tick", VIEW,
     "        if raw not in _LIST_CONCURRENCY_SAID:",
     "        if True:",
     EIGHT + "test_a_concurrency_nobody_can_read_is_eight_said_once"),

    ("an unreadable concurrency is never said", VIEW,
     "            log.warning(\"OPENFACTORY_LIST_CONCURRENCY=%r is not a positive number",
     "            (lambda *a: None)(\"OPENFACTORY_LIST_CONCURRENCY=%r is not a positive number",
     EIGHT + "test_a_concurrency_nobody_can_read_is_eight_said_once"),

    # ── the same list as one at a time ──────────────────────────────────────────────────────────
    # The whole of `_enriched_in_order`'s body from `one` down, so the cut is the finishing order
    # and nothing else: the same tasks, the same unwrap, the rows handed back as each finished.
    ("a batch's rows are kept in the order the engine answered them, not the listing's", VIEW,
     "    async def one(wf):\n"
     "        async with room:\n"
     "            return await _enriched(client, wf, namespace)\n"
     "\n"
     "    tasks: list[asyncio.Task] = []\n"
     "    try:\n"
     "        async with asyncio.TaskGroup() as group:\n"
     "            tasks = [group.create_task(one(wf)) for wf in batch]\n"
     "    except BaseExceptionGroup as failed:\n"
     "        raised = [t.exception() for t in tasks if t.done() and not t.cancelled()\n"
     "                  and t.exception() is not None]\n"
     "        raise (raised[0] if raised else failed.exceptions[0]) from None\n"
     "    return [t.result() for t in tasks]",
     "    finished: list = []\n"
     "\n"
     "    async def one(wf):\n"
     "        async with room:\n"
     "            row = await _enriched(client, wf, namespace)\n"
     "        finished.append(row)\n"
     "        return row\n"
     "\n"
     "    tasks: list[asyncio.Task] = []\n"
     "    try:\n"
     "        async with asyncio.TaskGroup() as group:\n"
     "            tasks = [group.create_task(one(wf)) for wf in batch]\n"
     "    except BaseExceptionGroup as failed:\n"
     "        raised = [t.exception() for t in tasks if t.done() and not t.cancelled()\n"
     "                  and t.exception() is not None]\n"
     "        raise (raised[0] if raised else failed.exceptions[0]) from None\n"
     "    return finished",
     SAME + "test_the_same_rows_in_the_same_order_one_at_a_time_and_eight_at_a_time"),

    ("limit is counted on the workflows asked about, before the gone ones are dropped", VIEW,
     "    async for wf in client.list_workflows(full):\n        batch.append(wf)",
     "    taken = 0\n    async for wf in client.list_workflows(full):\n        taken += 1\n"
     "        if taken > limit:\n            break\n        batch.append(wf)",
     SAME + "test_the_limit_counts_the_jobs_shown_not_the_jobs_asked_about"),

    ("a row that cannot be built fails the list as an ExceptionGroup, not as itself", VIEW,
     "        raise (raised[0] if raised else failed.exceptions[0]) from None",
     "        raise",
     SAME + "test_a_row_that_cannot_be_built_fails_the_list_with_its_own_error"),

    # ── nothing outlives the read ───────────────────────────────────────────────────────────────
    ("the questions are detached tasks, and a list that ran out of time leaves them running",
     VIEW,
     "        async with asyncio.TaskGroup() as group:\n"
     "            tasks = [group.create_task(one(wf)) for wf in batch]",
     "        tasks = [asyncio.ensure_future(one(wf)) for wf in batch]\n"
     "        await asyncio.wait(tasks)",
     EIGHT + "test_a_job_list_that_ran_out_of_time_leaves_no_question_running"),

    # Slow by construction: unbounded, the stand-in's 30 s queries are waited out (~3 min).
    ("the shared scan is not bounded, so nobody is told and its questions keep running", VIEW,
     '    rows = await _within("the job list", _listed(client, namespace, limit, query))',
     "    rows = await _listed(client, namespace, limit, query)",
     EIGHT + "test_a_job_list_that_ran_out_of_time_leaves_no_question_running"),

    # ── readers together share one scan ─────────────────────────────────────────────────────────
    ("every reader scans for itself, so six together are six scans", VIEW,
     "    return copy.deepcopy(await _jobs_read.shared(\n"
     "        lambda flight: _scan(flight, client, namespace, limit, query, stamp),\n"
     "        key=(id(client), *question)))",
     "    return copy.deepcopy(await _scan(_Flight(loop), client, namespace, limit, query, stamp))",
     TOGETHER + "test_six_askers_arriving_together_cost_one_scan"),

    ("every reader behind a refusal is refused by a scan of its own", VIEW,
     "    return copy.deepcopy(await _jobs_read.shared(\n"
     "        lambda flight: _scan(flight, client, namespace, limit, query, stamp),\n"
     "        key=(id(client), *question)))",
     "    return copy.deepcopy(await _scan(_Flight(loop), client, namespace, limit, query, stamp))",
     TOGETHER + "test_askers_queued_behind_a_failing_scan_share_its_failure"),

    ("a reader asking another question joins the scan in flight", VIEW,
     "        key=(id(client), *question)))",
     "        key=None))",
     TOGETHER + "test_askers_with_a_different_question_do_not_share_a_scan"),

    ("the single flight forgets the key, and any question joins any scan on its loop",
     SINGLE_FLIGHT,
     "        if flight is None or flight.loop is not loop or flight.key != key:",
     "        if flight is None or flight.loop is not loop:",
     TOGETHER + "test_askers_with_a_different_question_do_not_share_a_scan"),

    ("a reader joins a scan of another client asking the same question", VIEW,
     "        key=(id(client), *question)))",
     "        key=question))",
     TOGETHER + "test_askers_on_two_engines_together_are_each_scanned"),

    ("the readers of a shared scan are handed one object between them", VIEW,
     "    return copy.deepcopy(await _jobs_read.shared(",
     "    return (await _jobs_read.shared(",
     TOGETHER + "test_every_asker_is_handed_a_list_of_its_own"),

    # ── readers right after are handed its answer ───────────────────────────────────────────────
    ("a reader inside the window is handed the remembered rows themselves", VIEW,
     "        return copy.deepcopy(memo[4])",
     "        return memo[4]",
     AFTER + "test_every_asker_right_after_is_handed_a_list_of_its_own"),

    ("the remembered list is never consulted, so every reader right after scans again", VIEW,
     "    if (memo is not None and memo[0] is loop",
     "    if (False and memo is not None and memo[0] is loop",
     AFTER + "test_an_asker_right_after_a_scan_is_handed_its_answer"),

    ("the remembered list never expires", VIEW,
     "            and stamp - memo[3] < LIST_TTL_S):",
     '            and stamp - memo[3] < float("inf")):',
     AFTER + "test_the_shared_answer_expires_after_its_window"),

    ("another loop is handed this loop's list", VIEW,
     "memo[0] is loop and memo[1] is client",
     "memo[1] is client",
     AFTER + "test_another_loops_asker_is_never_handed_this_loops_answer"),

    ("another client is handed this client's list", VIEW,
     "memo[0] is loop and memo[1] is client and memo[2] == question",
     "memo[0] is loop and memo[2] == question",
     AFTER + "test_another_clients_asker_is_never_handed_this_clients_answer"),

    ("another question is handed this question's list", VIEW,
     "memo[1] is client and memo[2] == question\n",
     "memo[1] is client\n",
     AFTER + "test_an_asker_with_another_question_right_after_is_scanned_for_it"),

    ("a scan that failed is remembered as an empty list", VIEW,
     '    rows = await _within("the job list", _listed(client, namespace, limit, query))\n',
     "    try:\n"
     '        rows = await _within("the job list", _listed(client, namespace, limit, query))\n'
     "    except Exception:\n"
     "        _jobs_memo = (flight.loop, client, (namespace, limit, query), stamp, [])\n"
     "        raise\n",
     AFTER + "test_a_scan_that_failed_is_not_handed_to_the_next_asker"),

    ("a scan that lost the slot to a write is remembered anyway", VIEW,
     "    if _jobs_read.holds(flight):\n        _jobs_memo =",
     "    if True:\n        _jobs_memo =",
     AFTER + "test_a_scan_in_flight_across_a_write_is_not_handed_to_the_next_asker"),

    ("a remembered list is handed out while the engine is remembered as silent", VIEW,
     '    if left := unreachable_for():\n        raise _still_silent("the job list", left)\n'
     "    loop = asyncio.get_running_loop()",
     "    loop = asyncio.get_running_loop()",
     AFTER + "test_an_engine_remembered_as_silent_refuses_a_list_remembered_before_it"),

    # ── what drops it ───────────────────────────────────────────────────────────────────────────
    ("forgetting leaves the remembered list in place", VIEW,
     "    _jobs_memo = None\n    _jobs_read.forget()",
     "    _jobs_read.forget()",
     AFTER + "test_a_write_through_this_process_is_seen_by_the_next_list"),

    ("forgetting leaves the scan in flight in the slot, so it fills the window after a write",
     VIEW,
     "    _jobs_memo = None\n    _jobs_read.forget()",
     "    _jobs_memo = None",
     AFTER + "test_a_scan_in_flight_across_a_write_is_not_handed_to_the_next_asker"),

    ("a write forgets nothing, so the panel's re-read shows the job as it was before the click",
     VIEW,
     "        finally:\n            forget_jobs()",
     "        finally:\n            pass",
     AFTER + "test_a_write_through_this_process_is_seen_by_the_next_list"),

    ("one write is not marked, and the list after it is the one from before it", VIEW,
     "@_a_write\nasync def gate_key_refusal(",
     "async def gate_key_refusal(",
     AFTER + "test_a_write_through_this_process_is_seen_by_the_next_list"),

    ("the stream's blip leaves the job list from before it standing", APP,
     "                _floor_reading.forget_intake()\n                tv.forget_jobs()\n",
     "                _floor_reading.forget_intake()\n",
     FRAME + "test_a_BLIP_does_not_carry_a_stale_job_list_across_it"),
]
