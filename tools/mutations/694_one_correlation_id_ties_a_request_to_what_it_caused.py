"""One correlation id ties a request to every record it caused (#694, criterion 5), proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/694_one_correlation_id_ties_a_request_to_what_it_caused.py

The claims, each a group of rows (`ai/tasks/todo.md` tasks 26-30):
  A. the panel takes the id from `X-Request-ID` when it is one, and replaces — never stores, even
     in part — one that is not (`api/app.py::_correlation_of`, `audit.correlation_or_new`);
  B. the CLI mints one per command (`cli.py::_cli_actor`), read off the `by` the CLI handed
     `perform`, so a `perform` that minted it instead does not satisfy the guard;
  C. `perform` mints one for a caller that carries none, BEFORE the row runs, so a relayed call
     shares it — and keeps the one a caller already carries;
  D. the factory's own `SYSTEM`, once `perform` hands its row a copy carrying an id, is still
     recorded as `system` (`audit.AuditRecord.of`);
  E. an action that starts a job writes the id into that job's journal — durable start, local
     start, each card a scan started and no card it skipped — under `data.correlation_id`, in a
     `note` line;
  F. a journal that cannot be written is logged by name and the start stands, on every path;
  G. on a remote-box deployment the start note on the panel's host is followed by the box's
     journal, in `_events` and in the live feed, and never read as an ending or a job.

Every row names the one test (or test file) that holds its claim.

ONE GUARD WAS WRITTEN WITH THIS PLAN (2026-10-21): the durable start's journal failure. Its row,
"the durable start writes its note unguarded", survived the file as it stood (16 passed with the
cut applied): the local start and the scan were held to log and keep the start, and the durable
path only to write the note. `test_a_durable_start_whose_journal_cannot_be_written_still_starts_
and_says_so` is green on the code and red under the row (`Outcome(ok=False, "could not start:
unknown event sink 'no-such-sink' …")`). First full run: 29/29 red.
"""

TEST = "tests/test_one_correlation_id_ties_a_request_to_what_it_caused.py"

_ACTIONS = "openfactory/actions/__init__.py"
_AUDIT = "openfactory/observability/audit.py"
_APP = "openfactory/api/app.py"
_CLI = "openfactory/cli.py"
_CATALOG = "openfactory/actions/catalog.py"
_JOB_RECORD = "openfactory/observability/job_record.py"
_QUERY = "openfactory/observability/query.py"

_T = TEST + "::"
_PANEL_READS = "tests/test_panel_reads_events_without_aws.py::"
_OUTCOMES = ("tests/test_the_outcomes_are_read_never_inferred.py::"
             "test_a_start_note_is_a_line_of_the_job_it_started_never_an_ending_or_a_job_of_its_own")

MUTATIONS = [
    # ── A. the panel ───────────────────────────────────────────────────────────────────────────
    ("the panel ignores the X-Request-ID header", _APP,
     '    return correlation_or_new(request.headers.get("x-request-id"))\n',
     '    return correlation_or_new(None)\n',
     _T + "test_the_panel_takes_the_correlation_id_from_the_header"),
    ("the panel stores the header as sent, unvalidated", _APP,
     '    return correlation_or_new(request.headers.get("x-request-id"))\n',
     '    return request.headers.get("x-request-id") or correlation_or_new(None)\n',
     _T + "test_a_header_that_is_not_an_id_is_replaced_not_stored"),
    ("correlation_or_new keeps any non-empty string", _AUDIT,
     "    if isinstance(value, str) and _CORRELATION.fullmatch(value):\n",
     "    if isinstance(value, str) and value:\n",
     _T + "test_a_header_that_is_not_an_id_is_replaced_not_stored"),
    ("correlation_or_new matches a prefix, not the whole header", _AUDIT,
     "    if isinstance(value, str) and _CORRELATION.fullmatch(value):\n",
     "    if isinstance(value, str) and _CORRELATION.match(value):\n",
     _T + "test_a_header_that_is_not_an_id_is_replaced_not_stored"),
    ("_actor drops the request's id, leaving perform to mint one", _APP,
     "                     correlation=_correlation_of(request))\n",
     '                     correlation="")\n',
     _T + "test_the_panel_takes_the_correlation_id_from_the_header"),
    # ── B. the CLI ─────────────────────────────────────────────────────────────────────────────
    ("the CLI passes no id, leaving perform to mint one", _CLI,
     "                           correlation=new_correlation_id())\n",
     '                           correlation="")\n',
     _T + "test_the_cli_generates_one_per_call"),
    # ── C. perform ─────────────────────────────────────────────────────────────────────────────
    ("perform mints no id for a caller that carries none", _ACTIONS,
     "        by = dataclasses.replace(by, correlation=audit.new_correlation_id())\n",
     "        pass\n",
     _T + "test_a_caller_that_carries_none_still_gets_one"),
    ("perform mints a fresh id even for a call that already carries one (a relay)", _ACTIONS,
     '    key = (name or "").strip().lower()\n    if not by.correlation:\n',
     '    key = (name or "").strip().lower()\n    if True:\n',
     _T + "test_a_relayed_call_shares_the_id_perform_minted_for_its_caller"),
    ("the id is minted for the record only: the row runs on an actor without it", _ACTIONS,
     "        outcome = await _decide(name, key, by, params)\n",
     '        outcome = await _decide(name, key,'
     ' dataclasses.replace(by, correlation=""), params)\n',
     _T + "test_a_relayed_call_shares_the_id_perform_minted_for_its_caller"),
    # ── D. SYSTEM is still the system ──────────────────────────────────────────────────────────
    ("the record recognises the factory's own actor by identity only", _AUDIT,
     '        system = by is SYSTEM or dataclasses.replace(by, correlation="") == SYSTEM\n',
     "        system = by is SYSTEM\n",
     _T + "test_the_factorys_own_call_is_still_recorded_as_the_system_once_it_carries_an_id"),
    # ── E. the job's journal ───────────────────────────────────────────────────────────────────
    ("a durable start writes no start note", _CATALOG,
     '    _journal_the_start(found, issue, by=by)\n    return done(f"#{issue}: durable job started',
     '    return done(f"#{issue}: durable job started',
     _T + "test_a_durable_start_writes_it_into_the_jobs_events"),
    ("a local start writes no start note", _CATALOG,
     "    # note saying who started it reads first.\n    _journal_the_start(found, issue, by=by)\n",
     "    # note saying who started it reads first.\n",
     _T + "test_a_local_start_writes_it_into_the_jobs_events"),
    ("a scan writes no start note for the cards it started", _CATALOG,
     "                # deferred, was not started by this scan,"
     " and its journal must not say it was.\n"
     "                _journal_the_start(proj, issue, by=by)\n",
     "                # deferred, was not started by this scan,"
     " and its journal must not say it was.\n",
     _T + "test_scan_writes_it_into_each_started_jobs_events"),
    ("a scan writes a start note for a card the engine already ran", _CATALOG,
     "                    skipped.append(issue)\n"
     "                    claimed += 1  # this ticket already holds a slot",
     "                    skipped.append(issue)\n"
     "                    _journal_the_start(proj, issue, by=by)\n"
     "                    claimed += 1  # this ticket already holds a slot",
     _T + "test_scan_writes_it_only_into_the_jobs_it_started"),
    ("a scan writes a start note for a card it deferred (floor full)", _CATALOG,
     "                skipped.append(issue)  # deferred — floor"
     " full, a later scan/tick picks it up\n",
     "                skipped.append(issue)  # deferred — floor"
     " full, a later scan/tick picks it up\n"
     "                _journal_the_start(proj, issue, by=by)\n",
     _T + "test_scan_writes_it_only_into_the_jobs_it_started"),
    ("the start note carries the id under another key", _JOB_RECORD,
     '"correlation_id": correlation}',
     '"correlation": correlation}',
     TEST),
    ("the start note carries the actor's name where the id belongs", _CATALOG,
     "        record_started(project, issue, by=by, correlation=by.correlation)\n",
     "        record_started(project, issue, by=by, correlation=str(by))\n",
     TEST),
    # ── F. a journal that cannot be written ────────────────────────────────────────────────────
    ("_journal_the_start no longer catches a journal it cannot build", _CATALOG,
     "    except Exception as exc:  # noqa: BLE001 — the start"
     " stands; only its journal line is missing\n",
     "    except ImportError as exc:\n",
     _T + "test_a_start_whose_journal_cannot_be_written_still_starts_and_says_so"),
    ("_journal_the_start no longer catches: a scan stops at its first card", _CATALOG,
     "    except Exception as exc:  # noqa: BLE001 — the start"
     " stands; only its journal line is missing\n",
     "    except ImportError as exc:\n",
     _T + "test_a_scan_whose_journals_cannot_be_written_still_starts_every_card"),
    ("a journal that cannot be written is swallowed without a warning", _CATALOG,
     '        log.warning("OPENFACTORY_START_NOT_JOURNALLED'
     ' project=%s issue=%s — the job was started "\n',
     '        log.debug("OPENFACTORY_START_NOT_JOURNALLED'
     ' project=%s issue=%s — the job was started "\n',
     _T + "test_a_start_whose_journal_cannot_be_written_still_starts_and_says_so"),
    ("the durable start writes its note unguarded: a journal it cannot build fails the start",
     _CATALOG,
     '    _journal_the_start(found, issue, by=by)\n    return done(f"#{issue}: durable job started',
     "    from openfactory.observability.job_record import record_started\n"
     "    record_started(found, issue, by=by, correlation=by.correlation)\n"
     '    return done(f"#{issue}: durable job started',
     _T + "test_a_durable_start_whose_journal_cannot_be_written_still_starts_and_says_so"),
    # ── G. the readers of the journal ──────────────────────────────────────────────────────────
    ("_events answers any local line alone, the start note included", _APP,
     "    if _the_job_wrote(local) or not _boxes_are_remote():\n",
     "    if local or not _boxes_are_remote():\n",
     _PANEL_READS + "test_a_start_noted_on_the_panels_host_does_not_hide_the_remote_boxs_journal"),
    ("_events drops the start note once it reads the box", _APP,
     "        return local + tail.fetch_new()\n",
     "        return tail.fetch_new()\n",
     _PANEL_READS + "test_a_start_noted_on_the_panels_host_does_not_hide_the_remote_boxs_journal"),
    ("the live feed tails any local line alone, the start note included", _APP,
     "            if _the_job_wrote(_a_line(ln) for ln in local):\n",
     "            if local:\n",
     _PANEL_READS + ("test_the_live_feed_reads_the_remote_box_past_a_start_noted_on_the_panels_hos"
                     "t")),
    ("the live feed drops the start note once it reads the box", _APP,
     "                seen = local + fetched\n",
     "                seen = fetched\n",
     _PANEL_READS + ("test_the_live_feed_reads_the_remote_box_past_a_start_noted_on_the_panels_hos"
                     "t")),
    ("is_start_note recognises no line", _JOB_RECORD,
     '    return isinstance(event, dict) and (event.get("kind"),'
     ' event.get("message")) == START_NOTE\n',
     "    return False\n",
     _PANEL_READS + "test_a_start_noted_on_the_panels_host_does_not_hide_the_remote_boxs_journal"),
    ("_the_job_wrote says yes to a journal of start notes only", _APP,
     "    return any(not is_start_note(e) for e in events)\n",
     "    return bool(list(events))\n",
     _PANEL_READS + ("test_the_live_feed_reads_the_remote_box_past_a_start_noted_on_the_panels_hos"
                     "t")),
    ("the start note is written as a state line, which query reads as an ending", _JOB_RECORD,
     'START_NOTE = ("note", "started")\n',
     'START_NOTE = ("state", "started")\n',
     _OUTCOMES),
    ("query reads any line carrying a `by` as an ending, the start note included", _QUERY,
     '    return event.get("kind") == "state" and isinstance(event.get("data"), dict) \\\n',
     '    return isinstance(event.get("data"), dict) \\\n',
     _OUTCOMES),
]
