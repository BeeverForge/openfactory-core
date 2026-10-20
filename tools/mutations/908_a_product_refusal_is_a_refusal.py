"""A product write the module declines on purpose answers its refusal code, and only a write
nobody decided answers FAILED, with a reference (#908), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/908_a_product_refusal_is_a_refusal.py

On 620bb577 `_write_outcome` rendered every not-ok `WriteResult` as FAILED, so a stranger's
`product_withdraw_card` answered HTTP 500 with the module's own "only the person who asked for
#1 … can close or remove it". The claims, each a row:

  1. a not-ok result whose `refusal` names a word answers that word's code, never FAILED — and
     each word answers ITS code over `/api/act/<row>` (one row per word, aimed at the HTTP family
     alone, so the table-equality test is not what turns it red);
  2. the module says why at every deliberate refusal: the stranger's withdrawal says `not_yours`,
     the closed card's close says `already_closed`; the structural guard reads it off the source,
     and its detector finds a site inside a `lambda`;
  3. the word crosses the worker: both activities' dicts carry `refusal`;
  4. a failure is logged with a reference, in `_write_outcome`'s line and in `perform`'s RAISED
     arm, and a result that names no word (an older worker) is a failure; and a card or board the
     card's door could not READ is a failure too, never the card's state refusing (`unread`);
  5. the rows that render a list — promote, reorder, breakdown — answer the refusal every result
     names, not FAILED; words that disagree are a failure, and an unknown word is logged;
  6. the family drives every row that renders a write;
  7. a refusal word this panel does not know (a worker newer than it) is read as nobody's
     decision when a breakdown's rows are said, never raised on — so the fronts that landed are
     still said (human decision 2026-10-20, option A).
"""

TEST = "tests/test_every_refusal_a_product_write_names_answers_its_code_over_http.py"
HTTP_FAMILY = (TEST + "::test_each_refusal_reason_answers_its_code_and_the_modules_sentence_on_"
               "every_row_that_renders_a_write")
NEVER_500 = "tests/test_a_product_refusal_answers_as_a_refusal_and_never_500.py"
STRUCTURAL = "tests/test_every_deliberate_product_refusal_says_why.py"
BOUNDARY = "tests/test_a_product_refusal_crosses_the_worker_with_its_reason.py"
FAILURE = "tests/test_a_product_write_that_failed_is_still_a_failure_logged_with_a_reference.py"

CATALOG = "openfactory/actions/catalog.py"
ACTIONS = "openfactory/actions/__init__.py"
MODULE = "openfactory/product/module.py"
ACTIVITIES = "openfactory/runtime/temporal/activities.py"
CONFIRM = "openfactory/product/confirm.py"
AUTHORING = "openfactory/product/authoring.py"
GATES = "tests/test_a_merge_gates_answer_is_a_refusal_or_a_failure_as_it_is.py"
DROPPED = "tests/test_requirement_can_be_dropped.py"
PORTS = "openfactory/lifecycle/ports.py"
CARD = "openfactory/lifecycle/card.py"

MUTATIONS = [
    # 1. a refusal answers its code — the issue's own sabotage, then each word's code
    ("TODAY'S DEFECT: every not-ok result is rendered FAILED", CATALOG,
     "        return _not_done(said, _refusal_word(result), did=did, **payload)\n",
     "        return _not_done(said, \"\", did=did, **payload)\n",
     HTTP_FAMILY),
    ("TODAY'S DEFECT, seen as the stranger sees it: the withdrawal answers 500", CATALOG,
     "        return _not_done(said, _refusal_word(result), did=did, **payload)\n",
     "        return _not_done(said, \"\", did=did, **payload)\n",
     NEVER_500),
    ("not_yours answers 409, not 403", CATALOG,
     '    "not_yours": DENIED,\n', '    "not_yours": CONFLICT,\n', HTTP_FAMILY),
    ("not_found answers 409, not 404", CATALOG,
     '    "not_found": NOT_FOUND,\n', '    "not_found": CONFLICT,\n', HTTP_FAMILY),
    ("not_waiting answers 403, not 409", CATALOG,
     '    "not_waiting": CONFLICT,\n', '    "not_waiting": DENIED,\n', HTTP_FAMILY),
    ("already_closed answers 404, not 409", CATALOG,
     '    "already_closed": CONFLICT,\n', '    "already_closed": NOT_FOUND,\n', HTTP_FAMILY),
    ("already_there answers 400, not 409", CATALOG,
     '    "already_there": CONFLICT,\n', '    "already_there": INVALID,\n', HTTP_FAMILY),
    ("not_valid answers 409, not 400", CATALOG,
     '    "not_valid": INVALID,\n', '    "not_valid": CONFLICT,\n', HTTP_FAMILY),

    # 2. the module says why
    ("the stranger's withdrawal names no refusal (the guard sees it)", MODULE,
     "            return WriteResult(ok=False, refusal=NOT_YOURS, detail=card_withdrawn_result(\n",
     "            return WriteResult(ok=False, detail=card_withdrawn_result(\n",
     STRUCTURAL),
    ("the stranger's withdrawal names no refusal (and answers 500 again)", MODULE,
     "            return WriteResult(ok=False, refusal=NOT_YOURS, detail=card_withdrawn_result(\n",
     "            return WriteResult(ok=False, detail=card_withdrawn_result(\n",
     NEVER_500),
    ("a closed card's close names no refusal (the guard sees it)", MODULE,
     "            # confirmation that authorised this was about a card that no longer needs it.\n"
     "            return WriteResult(ok=False, refusal=ALREADY_CLOSED, existed=True,",
     "            # confirmation that authorised this was about a card that no longer needs it.\n"
     "            return WriteResult(ok=False, existed=True,",
     STRUCTURAL),
    ("a closed card's close names no refusal (and answers 500 again)", MODULE,
     "            # confirmation that authorised this was about a card that no longer needs it.\n"
     "            return WriteResult(ok=False, refusal=ALREADY_CLOSED, existed=True,",
     "            # confirmation that authorised this was about a card that no longer needs it.\n"
     "            return WriteResult(ok=False, existed=True,",
     NEVER_500),
    ("the structural guard's detector skips a lambda", STRUCTURAL,
     "        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "
     "_THE_FAILURE:\n",
     "        if isinstance(node, ast.Lambda) or (isinstance(node, (ast.FunctionDef, "
     "ast.AsyncFunctionDef)) and node.name == _THE_FAILURE):\n",
     STRUCTURAL + "::test_the_detector_would_catch_one"),

    # 3. the word crosses the worker
    ("the card activity's dict drops the refusal", ACTIVITIES,
     '            "existed": bool(getattr(result, "existed", False)),\n'
     '            "refusal": str(getattr(result, "refusal", "") or "")}\n',
     '            "existed": bool(getattr(result, "existed", False))}\n',
     BOUNDARY),
    ("the breakdown activity's dicts drop the refusal", ACTIVITIES,
     '             "nothing_to_build": bool(getattr(r, "nothing_to_build", False)),\n'
     '             "refusal": str(getattr(r, "refusal", "") or "")}\n',
     '             "nothing_to_build": bool(getattr(r, "nothing_to_build", False))}\n',
     BOUNDARY),

    # 4. a failure is a failure, with a reference
    ("the failure's log line names no reference", CATALOG,
     '    log.error("OPENFACTORY_PRODUCT_WRITE_FAILED reference=%s did=%s project=%s ref=%s — %s",\n'
     "              reference, did,",
     '    log.error("OPENFACTORY_PRODUCT_WRITE_FAILED did=%s project=%s ref=%s — %s",\n'
     "              did,",
     FAILURE),
    ("an action that raised answers no reference", ACTIONS,
     '        return refused(FAILED, f"could not {key}: {_why(exc)}", reason=RAISED,\n'
     "                       reference=reference)\n",
     '        return refused(FAILED, f"could not {key}: {_why(exc)}", reason=RAISED)\n',
     FAILURE),
    # AIMED AT THE ATTRIBUTE READ, not the Mapping one: `_product_card` rebuilds the worker's dict
    # as a `SimpleNamespace` before `_write_outcome` reads it (a cut of the `Mapping` branch
    # survived, 2026-10-20 — that branch is `_none_done`'s, for the breakdown's list of dicts).
    ("an older worker's dict, naming no word, is read as a refusal", CATALOG,
     '    return str(getattr(result, "refusal", "") or "")\n',
     '    return str(getattr(result, "refusal", "") or "not_found")\n',
     FAILURE),

    # 4b. the door's "could not see" is a failure (review round 1, point 2)
    ("UNREAD: the door's helper reads an unread card as a refusal of its state", MODULE,
     '    if getattr(moved, "unread", False):\n',
     "    if False:\n",
     FAILURE + "::test_a_card_its_door_could_not_read_is_a_failure_with_a_reference_not_a_conflict"),
    ("UNREAD: a card the tracker could not give the door is not marked unread", PORTS,
     "            return Seen(unread=True, cannot_tell=(\n",
     "            return Seen(cannot_tell=(\n",
     FAILURE + "::test_a_card_its_door_could_not_read_is_a_failure_with_a_reference_not_a_conflict"),
    ("UNREAD: a board the door could not read is not marked unread", PORTS,
     "            return Seen(title=title, unread=True, cannot_tell=(\n",
     "            return Seen(title=title, cannot_tell=(\n",
     FAILURE + "::test_a_board_its_door_could_not_read_is_a_failure_with_a_reference_not_a_conflict"),
    ("UNREAD: the door's transition drops what it could not see", CARD,
     "            return Transition(card=card, event=event, refused=seen.cannot_tell,\n"
     "                              unread=seen.unread)\n",
     "            return Transition(card=card, event=event, refused=seen.cannot_tell)\n",
     FAILURE + "::test_a_card_its_door_could_not_read_is_a_failure_with_a_reference_not_a_conflict"),

    # 4c. the classification tables: a failure is never read as a refusal (review round 1,
    #     point 3 — each of these survived 1229 to 2965 tests on 3a996b0a)
    ("TABLES: an acceptance that could not be written is read as a gate state", MODULE,
     "    waits = {adjust.NOT_WAITING, adjust.WORKING, adjust.DEAF, adjust.SPENT, accept.UNTRIED,\n"
     "             accept.MOVED}\n",
     "    waits = {adjust.NOT_WAITING, adjust.WORKING, adjust.DEAF, adjust.SPENT, accept.UNTRIED,\n"
     "             accept.MOVED, accept.UNRECORDED}\n",
     GATES),
    ("TABLES: an engine that could not be asked is read as a gate state", MODULE,
     "    waits = {adjust.NOT_WAITING, adjust.WORKING, adjust.DEAF, adjust.SPENT, accept.UNTRIED,\n"
     "             accept.MOVED}\n",
     "    waits = {adjust.NOT_WAITING, adjust.WORKING, adjust.DEAF, adjust.SPENT, accept.UNTRIED,\n"
     "             accept.MOVED, adjust.UNREACHABLE}\n",
     GATES),
    ("TABLES: an unparseable requirement's acceptance answers 409", AUTHORING,
     "            if outcome in _SETTLED:\n",
     "            if True:\n",
     DROPPED),
    ("TABLES: the client's own decision is read as a broken file", AUTHORING,
     "            if outcome in _SETTLED:\n",
     "            if False:\n",
     DROPPED),
    ("TABLES: a superseded requirement's drop is read as a broken file", AUTHORING,
     '            if outcome == "superseded":\n'
     "                # already off the table: a state with a next step, as `_drop_refusal` says (#908)\n",
     "            if False:\n"
     "                # already off the table: a state with a next step, as `_drop_refusal` says (#908)\n",
     DROPPED + "::test_dropping_a_requirement_another_already_replaced_is_a_refusal_with_a_next_"
     "step"),
    ("TABLES: an unparseable requirement's drop answers 409", AUTHORING,
     '            if outcome == "superseded":\n'
     "                # already off the table: a state with a next step, as `_drop_refusal` says (#908)\n",
     "            if True:\n"
     "                # already off the table: a state with a next step, as `_drop_refusal` says (#908)\n",
     DROPPED + "::test_dropping_a_requirement_file_NOBODY_can_parse_is_a_failure"),

    # 5. the rows that render a list
    ("a promotion nobody may make answers FAILED again", CATALOG,
     '        return _none_done(results, detail or "nothing could be moved into the queue, and the "\n',
     '        return _none_done([], detail or "nothing could be moved into the queue, and the "\n',
     NEVER_500 + "::test_a_promotion_the_person_may_not_make_answers_403_not_500"),
    ("a reorder nobody may make answers FAILED again", CATALOG,
     '        return _none_done(results, detail or "nothing could be reordered, and the module said "\n',
     '        return _none_done([], detail or "nothing could be reordered, and the module said "\n',
     NEVER_500 + "::test_a_reorder_the_person_may_not_make_answers_403_not_500"),
    ("a breakdown whose every front was refused answers FAILED again", CATALOG,
     "    return _none_done(filed, f\"nothing was filed for requirement {num}{why.rstrip('.')}.\",\n",
     "    return _none_done([], f\"nothing was filed for requirement {num}{why.rstrip('.')}.\",\n",
     NEVER_500 + "::test_a_breakdown_whose_every_front_was_refused_answers_that_refusal"),

    # 5b. #752's slice refusals (review round 1, point 1): another project's card is a refusal
    ("SLICE: a promotion of another project's card is read as a failure again", MODULE,
     '                            ok=False, refusal=NOT_WAITING, ref=f"#{number}",\n'
     '                            detail=board_move_said("outside_the_slice", ref=number,\n',
     '                            ok=False, refusal=NOT_REFUSED, ref=f"#{number}",\n'
     '                            detail=board_move_said("outside_the_slice", ref=number,\n',
     NEVER_500 + "::test_a_promotion_of_a_card_outside_the_projects_slice_answers_409_with_the_"
     "modules_sentence"),
    ("SLICE: a reorder of another project's card is read as a failure again", MODULE,
     '                    out.append(WriteResult(ok=False, refusal=NOT_WAITING, ref=f"#{number}",\n'
     '                                           detail=board_move_said("outside_the_slice", ref=number,\n',
     '                    out.append(WriteResult(ok=False, refusal=NOT_REFUSED, ref=f"#{number}",\n'
     '                                           detail=board_move_said("outside_the_slice", ref=number,\n',
     NEVER_500 + "::test_a_reorder_of_a_card_outside_the_projects_slice_answers_409_with_the_"
     "modules_sentence"),
    ("SLICE: the promotion's out-of-slice site names no refusal (the guard sees it)", MODULE,
     '                            ok=False, refusal=NOT_WAITING, ref=f"#{number}",\n'
     '                            detail=board_move_said("outside_the_slice", ref=number,\n',
     '                            ok=False, ref=f"#{number}",\n'
     '                            detail=board_move_said("outside_the_slice", ref=number,\n',
     STRUCTURAL),

    # 5c. a list's words (review round 1, the non-blocking point): disagreeing words are a
    #     failure, and a word this panel does not know is said in the log
    ("LIST: the first word answers a list whose words disagree", CATALOG,
     '    why = next(iter(words)) if len(words) == 1 else ""\n',
     '    why = next(iter(words), "")\n',
     FAILURE + "::test_a_list_whose_refusals_disagree_is_a_failure_with_a_reference"),
    ("LIST: a word this panel does not know is answered unsaid", CATALOG,
     '        log.error("OPENFACTORY_PRODUCT_REFUSAL_UNKNOWN did=%s refusal=%r — answered as a "\n'
     '                  "failure; this panel knows %s", did, why, ", ".join(sorted(_REFUSAL_CODE)))\n',
     "        pass\n",
     FAILURE + "::test_a_word_this_panel_does_not_know_is_a_failure_and_is_logged"),

    # 6. the family's table
    ("the family stops driving the defect filing row", TEST,
     '    "product_file_defect": ({"restated": "the report is weekly", "yes": True}, "file_defect"),\n',
     "",
     TEST + "::test_every_row_that_renders_a_write_is_in_the_table_this_family_drives"),

    # 7. a newer worker's word
    ("a breakdown front naming a word this panel does not know raises again", CONFIRM,
     '            fields["refusal"] = NOT_REFUSED\n',
     "            pass\n",
     NEVER_500 + "::test_a_breakdown_from_a_newer_worker_whose_front_names_an_unknown_refusal_"
     "still_answers_what_landed"),
]
