"""Every call into the action layer leaves one durable record of who asked for what (#694),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/694_every_action_leaves_one_durable_record.py

The claims, each a group of rows (the numbers are the plan's, `ai/tasks/todo.md` task 21):
  1-3, 18. `perform` writes one record on every way out — not none, not two, not only on the
     paths that return, and not before an early refusal returns;
  4, 17. what the record keeps of the parameters is masked like the log line, a person's words
     are kept as their length and digest, and every other value is bounded;
  5-6. the record cannot be changed once made;
  7-9. it is a row of kind `audit`, keyed by its own id, and read for its period and no longer;
  10. `project forget` keeps it;
  11. it is made and written off the event loop, and a cancel while it is written does not lose it;
  12. a record the store did not take is said;
  13-14. `openfactory audit` lists by each filter, refuses a date that is not one by name, keeps
     the most recent when cut, and tells an unreadable store and a sink it cannot read back apart
     from an empty store;
  15. the INFO line is still written beside the record, and prints the parameters as the record
     keeps them, made once (the human's decision of 2026-10-21);
  16. the record names which identity provider named the caller, on the panel and the CLI;
  19-20. a host CLI with no store named still keeps its records beside `registry.yaml`, and the
     deployment's own metrics inference is unchanged;
  and the deployment's name, the product, the correlation id, and the people store's read under
  the deployment-wide key the records share; and the cost dashboard's project selector and its
  default view, which an audit row under a typed or deployment-wide key moved (fixed 2026-10-21);
  and a caller the panel could not name listed as `-` rather than an empty column (found running
  `openfactory serve` and a curl by hand, 2026-10-21); and the row's key, the project and the
  action a caller sent, kept storable (a lone surrogate written as its escape) and bounded to
  `VALUE_CHARS` (branch review round 1, 2026-10-21), and the parameters bounded in number
  and by name (round 2), with what that bound leaves out counted and said and the project kept
  first (round 3); and four documented behaviours round 1's cuts showed no test held — the
  fallback file `OPENFACTORY_METRICS_DB` names, the action
  recorded and filtered by its resolved name, and an unreadable registry's product.

FOUR GUARDS WERE WRITTEN WITH THIS PLAN (2026-10-20), each for a row nothing held: the record of
a call raising outside the row's guard, and a store's other kinds read as records — both rows
printed `!!GREEN!!` on the first run (51 of 53 red) — and the WARNING when no store can be
built, and the refusal of a `--since`/`--until` that is not a date, both driven only by hand
before. Each is green on the code and red under its row.

Cut 9's second half, `AUDIT_KEPT_DAYS` changed without `docs/rotation-and-retention.md`, was
added when that page's §5 stated the period (2026-10-20): until then its guard,
`test_the_period_is_stated_where_the_other_retentions_are`, was red, and a cut aimed at a red test
reads RED whether or not it was seen. Every row aimed at the store's test file names one test, so
each row is proved by the guard that holds its claim and by no other.
"""

TEST = "tests/test_every_action_leaves_one_audit_record.py"

_ACTIONS = "openfactory/actions/__init__.py"
_AUDIT = "openfactory/observability/audit.py"
_BASE = "openfactory/actions/base.py"
_CLI = "openfactory/cli.py"
_APP = "openfactory/api/app.py"
_FORGET = "openfactory/product/forget.py"
_REGISTRY = "openfactory/observability/registry.py"
_SQLITE = "openfactory/observability/sqlite_metrics.py"

_STORE = "tests/test_the_audit_record_is_kept_in_the_metrics_store.py::"
_LIST = "tests/test_openfactory_audit_lists_who_did_what.py"
_EVERY = TEST + "::"
_ONE_EACH = _EVERY + "test_each_way_out_of_perform_leaves_one_record_and_only_one"

MUTATIONS = [
    # 1. no record at all
    ("perform writes no record", _ACTIONS,
     "        await audit.write(record)\n",
     "        pass\n",
     _ONE_EACH),
    # 2. two records for one call
    ("the record is written twice: once more inside _decide", _ACTIONS,
     '    the one record of the call around this, whichever `return` it took."""\n',
     '    the one record of the call around this, whichever `return` it took."""\n'
     '    await audit.write(audit.AuditRecord.of(name, by, params, refused(FAILED, "twice",'
     ' reason=RAISED)))\n',
     _ONE_EACH),
    # 3. an early return ahead of the record. Re-pinned 2026-10-20: `perform` now mints the
    # call's correlation id right after the name is resolved (#694, task 26).
    ("the unknown-action refusal returns from perform before the record is made", _ACTIONS,
     '    key = (name or "").strip().lower()\n    if not by.correlation:\n',
     '    key = (name or "").strip().lower()\n'
     '    if _catalog().get(key) is None:\n'
     '        return refused(NOT_FOUND, f"there is no action called {name!r}",'
     ' reason=UNKNOWN_ACTION)\n'
     '    if not by.correlation:\n',
     _ONE_EACH + "[unknown_action]"),
    # 18. the record only on a return
    ("the finally is gone: a call that raises (a cancel) leaves no record", _ACTIONS,
     "        raise\n    finally:\n        # ONE EXIT",
     "        raise\n    if True:\n        # ONE EXIT",
     _EVERY + "test_a_cancelled_call_still_leaves_one_record"),
    ("a call that raises outside the row's guard is swallowed, with no record", _ACTIONS,
     "        if outcome is None:\n            outcome = Outcome(ok=False, code=FAILED, "
     "data={\"reason\": RAISED},\n",
     "        if outcome is None:\n            return\n            outcome = Outcome(ok=False, "
     "code=FAILED, data={\"reason\": RAISED},\n",
     _EVERY + "test_a_call_that_raises_outside_the_rows_guard_leaves_one_record_and_raises"),
    ("a call that raises outside the row's guard goes on and leaves no record", _ACTIONS,
     "        if outcome is None:\n            outcome = Outcome(ok=False, code=FAILED, "
     "data={\"reason\": RAISED},\n",
     "        if outcome is None:\n            by = None  # the record cannot be made\n"
     "            outcome = Outcome(ok=False, code=FAILED, data={\"reason\": RAISED},\n",
     _EVERY + "test_a_call_that_raises_outside_the_rows_guard_leaves_one_record_and_raises"),

    # 4. the secret reaches the record. Re-pinned 2026-10-21: `_kept` now orders the names before
    # it bounds how many it keeps (branch review round 2), and masks by `is_secret` itself rather
    # than through `redact` (PR #1039 review).
    ("the record keeps the parameters unmasked: no name is a secret's", _AUDIT,
     "        if is_secret(name):\n            kept[shown] = MASK\n",
     "        if False:\n            kept[shown] = MASK\n",
     _STORE + "test_a_password_reaches_neither_the_record_nor_the_store_file"),
    # 17. a person's words, and the bound
    ("a free-text parameter is stored as its text", _AUDIT,
     "        if name in FREE_TEXT and value is not None:\n",
     "        if False and name in FREE_TEXT and value is not None:\n",
     _STORE + "test_a_clients_words_never_reach_the_audit_record"),
    ("`message` is no longer a free-text name", _BASE,
     '    "reason", "comment", "instruction", "message", "question",',
     '    "reason", "comment", "instruction", "question",',
     _STORE + "test_every_free_text_parameter_in_the_catalog_is_hashed"),
    ("a person's words are encoded strictly, so a lone surrogate loses the record", _AUDIT,
     '    digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()\n',
     '    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()\n',
     _EVERY + "test_words_holding_a_lone_surrogate_are_still_kept_as_their_length_and_digest"),
    ("a value of any length is kept whole", _AUDIT,
     "        if len(text) <= VALUE_CHARS:\n",
     "        if True:\n",
     _EVERY + "test_a_long_value_is_kept_to_its_bound_and_the_cut_is_said"),

    # 5-6. immutability
    ("AuditRecord loses frozen=True", _AUDIT,
     "@dataclass(frozen=True)\nclass AuditRecord:",
     "@dataclass\nclass AuditRecord:",
     _EVERY + "test_an_audit_record_cannot_be_changed_once_it_is_made"),
    # Re-pinned 2026-10-21: the record takes the view `perform` already made for its line.
    # Re-pinned 2026-10-21: the parameters are frozen all the way down (PR #1039 review).
    ("the record's params are a plain dict, not a read-only mapping", _AUDIT,
     "            params=_frozen(view),\n",
     "            params=view,\n",
     _EVERY + "test_an_audit_record_cannot_be_changed_once_it_is_made"),
    ("a nested mapping in the record's params can be edited", _AUDIT,
     "        return MappingProxyType({k: _frozen(v) for k, v in value.items()})\n",
     "        return {k: _frozen(v) for k, v in value.items()}\n",
     _EVERY + "test_a_value_nested_in_the_records_parameters_cannot_be_changed_either"),
    ("a nested list in the record's params can be edited", _AUDIT,
     "        return tuple(_frozen(v) for v in value)\n",
     "        return [_frozen(v) for v in value]\n",
     _EVERY + "test_a_value_nested_in_the_records_parameters_cannot_be_changed_either"),

    # 7-9. the row
    ("the row is of kind agent_run, not audit", _AUDIT,
     'MetricRecord(kind="audit", project=',
     'MetricRecord(kind="agent_run", project=',
     _STORE + "test_an_action_on_a_sqlite_deployment_leaves_a_row_of_kind_audit"),
    ("the row's ticket is the action, so two records in one instant share a key", _AUDIT,
     "ticket=record.record_id, ts=record.ts",
     "ticket=record.action, ts=record.ts",
     _STORE + "test_two_records_in_the_same_instant_are_both_kept"),
    ("the row's key is no longer its own record id", _AUDIT,
     "ticket=record.record_id, ts=record.ts",
     "ticket=record.action, ts=record.ts",
     _STORE + "test_an_audit_rows_key_is_its_own_record_id"),
    ("the row never expires", _AUDIT,
     "                        expires_at=int(datetime.fromisoformat(record.ts).timestamp())\n"
     "                        + AUDIT_KEPT_DAYS * 86_400,\n",
     "                        expires_at=None,\n",
     _STORE + "test_a_record_is_still_read_the_day_before_its_period_ends_and_not_after"),
    ("the row expires two days short of its period", _AUDIT,
     "                        + AUDIT_KEPT_DAYS * 86_400,\n",
     "                        + (AUDIT_KEPT_DAYS - 2) * 86_400,\n",
     _STORE + "test_a_record_is_still_read_the_day_before_its_period_ends_and_not_after"),
    ("the period changes and the retention page still states the old one", _AUDIT,
     "AUDIT_KEPT_DAYS = 365\n",
     "AUDIT_KEPT_DAYS = 366\n",
     _STORE + "test_the_period_is_stated_where_the_other_retentions_are"),

    # 10. project forget
    ("project forget removes the audit records", _FORGET,
     '                "preview_shape": "preview allowances"}',
     '                "preview_shape": "preview allowances", "audit": "audit records"}',
     _STORE + "test_forgetting_a_project_keeps_its_audit_records"),

    # 11. off the loop, and shielded
    ("the write runs on the event loop", _AUDIT,
     "    return await asyncio.to_thread(_keep, record)",
     "    return _keep(record)",
     _STORE + "test_the_audit_write_does_not_run_on_the_event_loop"),
    # Re-pinned 2026-10-21: the record is handed the line's view (`kept=`) on the next line.
    ("the record is made on the event loop", _ACTIONS,
     "        record = await asyncio.to_thread(audit.AuditRecord.of, name, by, params, outcome,\n"
     "                                         kept=kept)\n",
     "        record = audit.AuditRecord.of(name, by, params, outcome, kept=kept)\n",
     _STORE + "test_the_record_reads_the_registry_off_the_event_loop"),
    ("a cancel while the record is written cancels the write", _ACTIONS,
     "        await asyncio.shield(_leave_record(name, key, by, params, outcome))\n",
     "        await _leave_record(name, key, by, params, outcome)\n",
     _STORE + "test_a_call_cancelled_while_its_record_is_made_still_leaves_it"),

    # 12. failure is said
    ("a store that answered False is not said", _AUDIT,
     "    if not landed:\n",
     "    if False:\n",
     _STORE + "test_a_store_that_refuses_the_write_is_said_and_the_outcome_stands"),
    ("a store that raised is said without naming the store", _AUDIT,
     '        log.warning("audit: the record of %s by %s was not kept: %s raised (%s)",\n'
     "                    printable(record.action), printable(record.actor_id), _named(store), "
     "exc)\n"
     '        _KEEPING.lost(f"{_named(store)} raised ({exc})")\n        return False\n',
     "        raise\n",
     _STORE + "test_a_store_that_refuses_the_write_is_said_and_the_outcome_stands"),
    ("a record that could not be made, or no store built, is not said", _ACTIONS,
     '        log.warning("audit: the record of %s by %s was not kept (%s)",\n'
     "                    audit.printable(audit._scrub(key or name)), audit.printable(by), exc)\n",
     "        pass\n",
     _STORE + "test_a_sink_that_cannot_be_built_is_said_and_the_outcome_stands"),

    # 13. openfactory audit's filters, one cut each
    ("audit ignores --actor", _CLI,
     '        if actor is not None and r.get("actor_id") != actor:\n',
     '        if False:\n',
     _LIST),
    ("audit ignores --action", _CLI,
     '        if action is not None and r.get("action") != action.strip().lower():\n',
     '        if False:\n',
     _LIST),
    ("audit ignores --project", _CLI,
     '        if project is not None and r.get("project") != project:\n',
     '        if False:\n',
     _LIST),
    ("audit ignores --outcome ok", _CLI,
     '        if outcome == "ok" and not r.get("ok"):\n',
     '        if False:\n',
     _LIST),
    ("audit ignores --outcome refused", _CLI,
     '        if outcome == "refused" and (r.get("ok") or r.get("code") == FAILED):\n',
     "        if False:\n",
     _LIST),
    ("audit ignores --outcome <code or reason>", _CLI,
     '        if outcome not in (None, "ok", "refused") and (\n',
     '        if False and (\n',
     _LIST),
    # Re-pinned 2026-10-21: --since is where the newest-first read stops (PR #1039 review).
    ("audit ignores --since", _CLI,
     '            if start is not None and _audit_when(r["ts"]) < start:\n                break',
     "            if False:\n                break",
     _LIST),
    ("audit ignores --until", _CLI,
     "        return end is None or when < end\n",
     "        return True\n",
     _LIST),
    ("--until excludes its own day", _CLI,
     "    end = datetime.combine(hi + timedelta(days=1), time(), UTC) if hi else None\n",
     "    end = datetime.combine(hi, time(), UTC) if hi else None\n",
     _LIST),
    ("a --since or --until that is not a date is read as no bound", _CLI,
     '        typer.echo(f"audit: {flag} takes a UTC date, YYYY-MM-DD; {text!r} is not one", '
     "err=True)\n        raise typer.Exit(2) from None\n",
     "        return None\n",
     _LIST),
    # Re-pinned 2026-10-21: the rows are read newest first and cut as they are read (PR #1039
    # review); the cut keeping the oldest is `694_openfactory_audit_reads_a_bounded_store.py`'s.
    ("a cut list keeps the oldest, not the most recent", _CLI,
     "    found = sorted(found[:limit], key=",
     "    found = sorted(found[-limit:], key=",
     _LIST),
    ("a cut list is not said", _CLI,
     "    cut = len(found) > limit\n",
     "    cut = False\n",
     _LIST),
    # Re-pinned 2026-10-21: a store that cannot be asked by kind is scanned and filtered here
    # (PR #1039 review); the sqlite store is asked by kind, its own cut in the bounded-read plan.
    ("audit lists rows of every kind, not only audit", _CLI,
     '        yield from sorted((r for r in store.scan() if r.get("kind") == "audit"), key=when,\n',
     "        yield from sorted(store.scan(), key=when,\n",
     _LIST + "::test_a_store_that_cannot_ask_by_kind_is_still_listed_through_its_scan"),
    ("a caller with no id leaves an empty column, not a dash", _CLI,
     'r.get("actor_id") or "-", r.get("action"),',
     'r.get("actor_id"), r.get("action"),',
     _LIST + "::test_a_caller_the_panel_could_not_name_is_listed_as_a_dash_keeping_each_line_in_"
     "columns"),
    # 14. three answers, never one
    ("an unreadable store is printed as no records", _CLI,
     '        typer.echo(f"audit: {audit._named(store)} cannot be read, so this cannot say who '
     'did "\n                   f"what — {exc}", err=True)\n'
     "        raise typer.Exit(2) from None\n",
     "        rows = []\n",
     _LIST),
    ("a sink kind nothing answers to is printed as no records", _CLI,
     '        typer.echo(f"audit: the metrics sink {kind!r} (OPENFACTORY_METRICS_SINK) could not '
     'be "\n                   f"built, so no record can be read — {exc}", err=True)\n'
     "        raise typer.Exit(2) from None\n",
     "        typer.echo('audit: no audit record yet', err=True)\n        return\n",
     _LIST),
    ("a sink that cannot be read back is not told apart", _CLI,
     "    if not isinstance(store, ReadableSink):\n",
     "    if False:\n",
     _LIST),
    ("audit reads the deployment's sink, not the one the record is written to", _CLI,
     "        store = audit.sink()\n",
     "        from openfactory.observability.registry import deployment_metrics_sink\n"
     "        store = deployment_metrics_sink()\n",
     _LIST),

    # 15. the line beside the record
    ("the INFO line is not written", _ACTIONS,
     '    log.info("action=%s by=%s%s ok=%s code=%s params=%s", audit.printable(audit._scrub(key)),\n',
     '    log.debug("action=%s by=%s%s ok=%s code=%s params=%s", audit.printable(audit._scrub(key)),\n',
     _STORE + "test_the_info_line_is_still_written_beside_the_record"),
    ("the INFO line is not written (the line's own password guard)", _ACTIONS,
     '    log.info("action=%s by=%s%s ok=%s code=%s params=%s", audit.printable(audit._scrub(key)),\n',
     '    log.debug("action=%s by=%s%s ok=%s code=%s params=%s", audit.printable(audit._scrub(key)),\n',
     "tests/test_the_action_layer.py::test_a_password_never_reaches_a_log_line"),
    # 15, the human's decision of 2026-10-21: the line prints what the record keeps, made once.
    ("the INFO line logs redact(params): a person's words in full", _ACTIONS,
     "        shown: object = kept\n",
     "        shown: object = redact(params)\n",
     _EVERY + "test_the_info_line_shows_a_persons_words_only_as_the_record_keeps_them"),
    ("the record makes its own view again, so a cut is said twice", _ACTIONS,
     "                                         kept=kept)\n",
     "                                         kept=None)\n",
     _EVERY + "test_a_value_cut_for_the_record_is_cut_in_the_line_and_the_cut_is_said_once"),
    ("parameters that cannot be read are printed as sent", _ACTIONS,
     '        shown = f"<not shown: they could not be read ({exc})>"\n',
     "        shown = params\n",
     _EVERY + "test_parameters_that_cannot_be_read_leave_the_line_saying_so_"
     "and_the_outcome_stands"),

    # 16. which identity provider named the caller. Re-pinned 2026-10-20: both actors now also
    # carry the call's correlation id on the next line (#694, task 26).
    ("the panel's actor carries no subject", _APP,
     '                         label="" if known else label, subject=subject,\n',
     '                         label="" if known else label,\n',
     _EVERY + "test_the_panel_records_which_identity_provider_named_the_caller"),
    ("the command line's subject says host, not cli", _CLI,
     '                           subject=Subject(id=who, display=who, via="cli"),\n',
     '                           subject=Subject(id=who, display=who, via="host"),\n',
     _EVERY + "test_the_command_line_records_the_shell_login_as_its_own_provider"),

    # 19-20. where a host CLI keeps them, and the inference left alone
    ("audit_path falls back to a file relative to the shell's directory", _AUDIT,
     "    return ProjectRegistry().path.parent / AUDIT_FILE\n",
     "    return Path(AUDIT_FILE)\n",
     _STORE + "test_a_host_cli_with_no_store_configured_still_keeps_the_record"),
    # Re-pinned 2026-10-21: `sink` reads the kind once and falls back for `memory` too (PR #1039
    # review).
    ("sink() never replaces a null store", _AUDIT,
     "    if kind not in KEEPS_NO_RECORD:\n",
     "    if True:\n",
     _STORE + "test_a_host_cli_with_no_store_configured_still_keeps_the_record"),
    ("metrics_sink_kind() answers sqlite when nothing is set", _REGISTRY,
     '    return "dynamodb" if os.environ.get("OPENFACTORY_METRICS_TABLE") else "null"',
     '    return "dynamodb" if os.environ.get("OPENFACTORY_METRICS_TABLE") else "sqlite"',
     _STORE + "test_the_metrics_sink_kind_inference_is_unchanged"),

    # the deployment, the product, the correlation
    ("the record ignores OPENFACTORY_DEPLOYMENT", _AUDIT,
     '    named = os.environ.get(DEPLOYMENT_ENV, "").strip()\n',
     '    named = ""\n',
     _EVERY + "test_the_record_names_the_deployment_its_operator_named"),
    ("a deployment nobody named ignores TEMPORAL_NAMESPACE", _AUDIT,
     '    return named or os.environ.get("TEMPORAL_NAMESPACE", "default")\n',
     '    return named or "default"\n',
     _EVERY + "test_a_deployment_nobody_named_is_named_by_its_engine_namespace"),
    ("naming the deployment imports the engine's client", _AUDIT,
     '    named = os.environ.get(DEPLOYMENT_ENV, "").strip()\n',
     "    import openfactory.runtime.temporal.connection  # noqa: F401\n"
     '    named = os.environ.get(DEPLOYMENT_ENV, "").strip()\n',
     _EVERY + "test_naming_the_deployment_does_not_import_the_engines_client"),
    ("a project of one is recorded under its own product key", _AUDIT,
     '    return key if key.startswith("repo:") else ""\n',
     "    return key\n",
     _EVERY + "test_a_project_with_a_product_names_it_and_one_without_leaves_it_empty"),
    ("the record drops the caller's correlation id", _AUDIT,
     "            correlation_id=by.correlation,\n",
     '            correlation_id="",\n',
     _EVERY + "test_a_relayed_row_leaves_its_own_record_under_the_callers_correlation"),

    # the people store reads past the records that share its key
    ("the sqlite read of one kind returns every kind under the key", _SQLITE,
     '            "SELECT data FROM metrics WHERE pk = ? AND kind = ?"\n'
     '            " AND (expires_at IS NULL OR expires_at > ?)"\n'
     '            " ORDER BY ts DESC, sk DESC LIMIT ?",\n'
     "            (project, kind, int(time.time()), max(0, limit)))\n",
     '            "SELECT data FROM metrics WHERE pk = ? AND ? IS NOT NULL"\n'
     '            " AND (expires_at IS NULL OR expires_at > ?)"\n'
     '            " ORDER BY ts DESC, sk DESC LIMIT ?",\n'
     "            (project, kind, int(time.time()), max(0, limit)))\n",
     _STORE + "test_audit_rows_under_the_deployment_key_do_not_hide_a_registered_person"),

    # the dashboard reads the whole store, and its selector is built from the rows' keys
    # RETIRED 2026-10-21: `dashboard` no longer filters audit rows — its one caller reads through
    # `metrics_view._scanned`, which leaves them out, so the filter was dead and its cut survived
    # (78/79). That claim is `694_audit_rows_do_not_weigh_on_the_metrics_readers.py`'s now, and
    # `test_audit_rows_in_the_store_do_not_change_the_cost_dashboard` is red under its first cut.

    # the row's key is a value the caller sent: storable, and bounded (branch review round 1,
    # 2026-10-21 — a lone surrogate in it left no record; a million characters of it were kept)
    # Re-pinned 2026-10-21: the project is escaped and then cut (branch review round 2).
    ("a lone surrogate in the project reaches the row's key", _AUDIT,
     '        project = _cut(_storable(_scrub(str(params.get("project") or ""))))\n',
     '        project = _cut(_scrub(str(params.get("project") or "")))\n',
     _STORE + "test_a_lone_surrogate_in_the_rows_key_still_leaves_the_record"),
    ("a lone surrogate in the action reaches the row's key", _AUDIT,
     "        action = _storable(asked)[:VALUE_CHARS]\n",
     "        action = asked[:VALUE_CHARS]\n",
     _STORE + "test_a_lone_surrogate_in_the_rows_key_still_leaves_the_record"),
    ("the record's project is the parameter as sent, uncut", _AUDIT,
     '        project = _cut(_storable(_scrub(str(params.get("project") or ""))))\n',
     '        project = _storable(_scrub(str(params.get("project") or "")))\n',
     _STORE + "test_the_project_a_caller_typed_is_kept_to_the_bound_like_any_value"),
    ("the record's action is the name as asked, uncut", _AUDIT,
     "        action = _storable(asked)[:VALUE_CHARS]\n",
     "        action = _storable(asked)\n",
     _STORE + "test_the_action_name_a_caller_typed_is_kept_to_the_bound_like_any_value"),
    ("an action name cut to the bound is not said", _AUDIT,
     '            log.info("audit: an action name of %d characters was asked; '
     'the record keeps the "\n'
     '                     "first %d", len(asked), VALUE_CHARS)\n',
     "            pass\n",
     _STORE + "test_an_action_name_cut_to_the_bound_is_said_once_at_INFO"),
    ("the project is cut and then escaped, so its key is six times the bound", _AUDIT,
     '        project = _cut(_storable(_scrub(str(params.get("project") or ""))))\n',
     '        project = _storable(_cut(_scrub(str(params.get("project") or ""))))\n',
     _STORE + "test_a_project_of_lone_surrogates_is_kept_to_the_bound_once_it_is_escaped"),
    # the number of parameters and their names are a caller's too (branch review round 2,
    # 2026-10-21 — 5,000 parameters in one refused request wrote a 10 MB row)
    ("every parameter a caller sent is kept, however many", _AUDIT,
     "    for name in names[:PARAMS_KEPT]:\n",
     "    for name in names:\n",
     _STORE + "test_the_parameters_a_caller_sent_are_kept_to_a_bound_however_many_and_however_"
              "named[five_thousand_parameters]"),
    ("a parameter's name is kept whole, however long", _AUDIT,
     "    if len(text) <= NAME_CHARS:\n        return text\n",
     "    if True:\n        return text\n",
     _STORE + "test_the_parameters_a_caller_sent_are_kept_to_a_bound_however_many_and_however_"
              "named[one_name_of_a_million_characters]"),
    # what the bound leaves out is said, and the project is never what it leaves out: four
    # documented behaviours each cut with all 144 audit tests green (branch review round 3,
    # 2026-10-21) — the record's `project` field is read from the parameters as sent, so only the
    # list the record keeps can show the order
    ("the project is not put first among the parameters kept", _AUDIT,
     '    names = sorted(params, key=lambda n: n != "project")\n',
     "    names = list(params)\n",
     _STORE + "test_the_parameters_a_record_leaves_out_are_counted_in_it_and_said_once"),
    ("the parameters left out are not counted in the record", _AUDIT,
     '        kept["…"] = f"{len(names) - PARAMS_KEPT} more parameters not kept"\n',
     "        pass\n",
     _STORE + "test_the_parameters_a_record_leaves_out_are_counted_in_it_and_said_once"),
    ("the parameters left out are not said at INFO", _AUDIT,
     '        log.info("audit: %s was passed %d parameters; the record keeps %d", '
     'printable(action),\n'
     "                 len(names), PARAMS_KEPT)\n",
     "        pass\n",
     _STORE + "test_the_parameters_a_record_leaves_out_are_counted_in_it_and_said_once"),
    ("a long parameter name is cut without the note", _AUDIT,
     '    return f"{text[:NAME_CHARS]}… [{len(text) - NAME_CHARS} more characters not kept]"\n',
     "    return text[:NAME_CHARS]\n",
     _STORE + "test_the_parameters_a_record_leaves_out_are_counted_in_it_and_said_once"),

    # documented behaviours no test held: each survived the branch review's own cut (round 1,
    # 2026-10-21, 133 passed under each), and each has a guard of its own now
    ("the fallback store ignores OPENFACTORY_METRICS_DB", _AUDIT,
     '    if named := os.environ.get("OPENFACTORY_METRICS_DB", "").strip():\n',
     '    if named := "":\n',
     _STORE + "test_a_deployment_with_no_store_keeps_the_record_in_the_file_"
              "OPENFACTORY_METRICS_DB_names"),
    ("audit --action is matched as typed, not lower-cased", _CLI,
     '        if action is not None and r.get("action") != action.strip().lower():\n',
     '        if action is not None and r.get("action") != action:\n',
     _LIST + "::test_an_action_asked_in_capitals_is_recorded_and_listed_by_its_name"),
    ("the record keeps the action as asked, not as resolved", _AUDIT,
     '        asked = _scrub((name or "").strip()).lower() or _scrub(name or "")\n',
     '        asked = name\n',
     _LIST + "::test_an_action_asked_in_capitals_is_recorded_and_listed_by_its_name"),
    ("an unreadable registry gives the product no product has", _AUDIT,
     "        return PRODUCT_UNREAD\n",
     '        return ""\n',
     _EVERY + "test_a_registry_that_cannot_be_read_names_the_product_unread_not_none"),
]
