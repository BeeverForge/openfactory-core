"""A pull request waiting only for a person's review has a column of its own, apart from the parks,
and a deployment that maps none keeps today's board (#753).

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/753_a_pull_request_waiting_for_a_reviewer_has_its_own_column.py

THE CLAIMS, each with a red twin below:

  1. **The resolver answers `needs_review` for `pr_open` with a person, and nothing else moves.**
     Row 1 puts the defect back (`needs_action`, the key of every park); row 2 widens the new key to
     the whole review bucket, which `test_every_other_answer_of_the_resolver_is_unchanged` refuses.
  2. **The fallback is one table in the contract, and every row takes it.** Row 3 empties
     `FALLS_BACK_TO`; rows 4-10 cut the fallback out of each of the seven rows that resolve a key to
     a column (AC3[row]); rows 11-17 make each row take the fallback whatever the deployment mapped
     (AC2[row]); row 18 derives Azure's `needs_review` from the Resolved category, `in_review`'s;
     row 19 reads "mapped" on GitHub off the deployment's dict instead of the board's Status
     options; row 20 puts the Jira board's second instance of the defect back (`needs_person`
     dropped); row 21 hands GitHub's `set_column` the FIRST name when the board has neither option,
     so a pull request on a board without Needs Action moves nowhere instead of to Backlog; row 22
     silences the local board's warning that it fell back from `needs_review`.
  3. **The platform names the key and reads it back.** Row 23 drops it from `CANONICAL_COLUMNS`
     (#258's blocking defect), row 24 from `BOARD_ORDER`; rows 25-26 put it before or after the
     factory, which `has_started`/`may_be_running`/`has_finished` and the door refuse.
  4. **The door reads a card there as waiting on a person (AC5) and asks the engine before queueing
     it (AC6).** Row 27 removes its `BY_COLUMN` row, row 28 reads it as `running`; row 29 puts
     `card_move`'s check back to `needs_action` alone; row 30 shrinks `WAITING_ON_A_PERSON_KEYS`.
  5. **The readers beyond the plan's list.** Rows 31-32: triage's waiting-too-long reads only the
     park again (the default, and the comparison); row 33 lets the product role's parked review
     list a card in Needs Review (ADR-0019 §6: it holds what needs a decision).
  6. **The panel describes the column.** Row 34 removes its `_BCOL` row.
  7. **A status two keys share reads back as `in_review`** (the reporter's board maps both to "In
     Review"), **and a park already called "Needs Review" stays a park.** Row 35 empties
     `YIELDS_ITS_DEFAULT_NAME`, so `needs_review`'s default name no longer yields and a park a
     deployment already called "Needs Review" reads as `needs_review`, and the product role's
     parked review goes empty (the review's point 1); row 36 makes `key_for` answer the LAST key
     that spells a name, so the shared status, in either spelling and on GitHub as on Jira, reads
     as `needs_review` and the door would queue a card the factory may still be reviewing (the
     re-review's point 1).
  8. **A re-run of `project init` gives an existing local board its review column, in board order
     (Q1, answer B).** Row 37 puts back `init`'s skip of `create` on an attached board; row 38 takes
     the local row's say-so away; row 39 leaves the existing rows' positions as they were, so the
     new row ties with Needs Action and sorts after it; row 40 restores the platform's names on a
     re-run; row 41 back-fills the parked cards into the new column; rows 42-43 make the re-run
     silent about what it added, and loud about what it did not.
  9. **A board's write takes the rule its read takes (PR #1040's review).** Row 44 lets GitHub's
     `set_status` hand `needs_review`'s default "Needs Review" to a board whose `in_review` the
     deployment called that, so the card a person must review reads back as RUNNING; row 45 makes
     the default name yield on every board, so a GitHub board that HAS a Needs Review option sends
     the pull request to Needs Action. Row 46 makes the local board's fallback warning fire on
     every move of a board 0.6 wrote, instead of once per board (PR #1040's review). Row 47 lets
     a name the deployment WROTE for `needs_review` yield too, so `{needs_review: "In review"}`
     sends the pull request to Needs Action instead of where the deployment put it.
"""

TEST = "tests/test_a_pull_request_waiting_for_a_reviewer_is_not_a_blocked_card.py"

BASE = "openfactory/adapters/tracker/base.py"
COLUMNS = "openfactory/adapters/board/columns.py"
TABLE = "openfactory/lifecycle/table.py"
CATALOG = "openfactory/actions/catalog.py"
L_TRACKER = "openfactory/adapters/tracker/local.py"
L_BOARD = "openfactory/adapters/board/local.py"
GHP = "openfactory/adapters/tracker/github_project.py"
J_TRACKER = "openfactory/adapters/tracker/jira.py"
J_BOARD = "openfactory/adapters/board/jira.py"
A_TRACKER = "openfactory/adapters/tracker/azure_devops.py"
A_BOARD = "openfactory/adapters/board/azure_devops.py"
TRIAGE = "openfactory/product/triage.py"
PARKED = "openfactory/product/board.py"
PANEL = "openfactory/api/panel.html"

AC2 = "tests/test_a_board_that_maps_a_review_column_gets_its_pull_requests_there.py"
AC3 = "tests/test_a_board_that_maps_no_review_column_keeps_todays_board.py"
AC456 = "tests/test_a_card_in_the_review_column_is_one_the_platform_maps.py"
VOCABULARY = "tests/test_the_columns_and_the_identity_are_the_platforms.py"
QUEUE_READERS = "tests/test_the_queues_readers_read_columns_by_key.py"
CLI = "openfactory/cli.py"
L_SETUP = "openfactory/adapters/board_setup/local.py"
RERUN = "tests/test_a_rerun_of_init_gives_an_existing_local_board_its_review_column.py"


def _ac2(row: str) -> str:
    return f"{AC2}::test_the_pull_request_lands_in_the_review_column[{row}]"


def _ac3(row: str) -> str:
    return f"{AC3}::test_the_pull_request_still_lands_in_needs_action[{row}]"


MUTATIONS = [
    # ── 1. the resolver ─────────────────────────────────────────────────────────────────────────
    ("TODAY'S DEFECT: a pull request a person must review answers `needs_action`, a park's key",
     BASE,
     '    if needs_person and state is JobState.PR_OPEN:\n        return "needs_review"\n',
     ""),

    ("the new key widened to every review state with a person", BASE,
     "    if needs_person and state is JobState.PR_OPEN:\n",
     "    if needs_person and state in _REVIEW:\n",
     f"{TEST}::test_every_other_answer_of_the_resolver_is_unchanged"),

    # ── 2. the fallback, in the contract and on each row ────────────────────────────────────────
    ("`FALLS_BACK_TO` emptied: no row falls back", BASE,
     'FALLS_BACK_TO: dict[str, str] = {"needs_review": "needs_action"}',
     "FALLS_BACK_TO: dict[str, str] = {}",
     AC3),

    ("the local tracker tries only `needs_review`", L_TRACKER,
     "            for key in keys:\n", "            for key in keys[:1]:\n",
     _ac3("local tracker")),

    ("the local board tries only `needs_review`", L_BOARD,
     "            key = next((k for k in keys if conn.execute(",
     "            key = next((k for k in keys[:1] if conn.execute(",
     _ac3("local board")),

    ("GitHub tries only `needs_review` (an unmapped option falls to Backlog)", GHP,
     "for key in column_keys(state, needs_person=needs_person))",
     "for key in column_keys(state, needs_person=needs_person)[:1])",
     _ac3("GitHub Projects")),

    ("the Jira tracker tries only `needs_review`", J_TRACKER,
     "            key = next((k for k in keys if self.status_map.get(k)), None)",
     "            key = next((k for k in keys[:1] if self.status_map.get(k)), None)",
     _ac3("Jira tracker")),

    ("the Jira board tries only `needs_review`", J_BOARD,
     "        key = next((k for k in keys if status_map.get(k)), None)",
     "        key = next((k for k in keys[:1] if status_map.get(k)), None)",
     _ac3("Jira board")),

    ("the Azure tracker tries only `needs_review`", A_TRACKER,
     "        target = next((t for t in map(self._state_for_key, keys) if t), None)",
     "        target = next((t for t in map(self._state_for_key, keys[:1]) if t), None)",
     _ac3("Azure Boards tracker")),

    ("the Azure board tries only `needs_review`", A_BOARD,
     "        target = next((self._names[k] for k in keys if self._names.get(k)), \"\")",
     "        target = next((self._names[k] for k in keys[:1] if self._names.get(k)), \"\")",
     _ac3("Azure Boards board")),

    ("the local tracker ignores a mapped `needs_review` and always takes the fallback", L_TRACKER,
     "            for key in keys:\n", "            for key in keys[-1:]:\n",
     _ac2("local tracker")),

    ("the local board ignores a mapped `needs_review`", L_BOARD,
     "            key = next((k for k in keys if conn.execute(",
     "            key = next((k for k in keys[-1:] if conn.execute(",
     _ac2("local board")),

    ("GitHub ignores a mapped `needs_review` option", GHP,
     "        name = next((n for n in names if n in self._option_ids), names[-1])",
     "        name = names[-1]",
     _ac2("GitHub Projects")),

    ("the Jira tracker ignores a mapped `needs_review`", J_TRACKER,
     "            key = next((k for k in keys if self.status_map.get(k)), None)",
     "            key = next((k for k in keys[-1:] if self.status_map.get(k)), None)",
     _ac2("Jira tracker")),

    ("the Jira board ignores a mapped `needs_review`", J_BOARD,
     "        key = next((k for k in keys if status_map.get(k)), None)",
     "        key = next((k for k in keys[-1:] if status_map.get(k)), None)",
     _ac2("Jira board")),

    ("the Azure tracker ignores a mapped `needs_review`", A_TRACKER,
     "        target = next((t for t in map(self._state_for_key, keys) if t), None)",
     "        target = next((t for t in map(self._state_for_key, keys[-1:]) if t), None)",
     _ac2("Azure Boards tracker")),

    ("the Azure board ignores a mapped `needs_review`", A_BOARD,
     "        target = next((self._names[k] for k in keys if self._names.get(k)), \"\")",
     "        target = next((self._names[k] for k in keys[-1:] if self._names.get(k)), \"\")",
     _ac2("Azure Boards board")),

    ("Azure derives `needs_review` from the Resolved category, which is `in_review`'s", A_TRACKER,
     '    "in_review": "resolved",\n    "done": "completed",\n}',
     '    "in_review": "resolved",\n    "needs_review": "resolved",\n    "done": "completed",\n}',
     _ac3("Azure Boards tracker")),

    ("GitHub reads \"mapped\" off the deployment's dict, not the board's Status options", GHP,
     "        name = next((n for n in names if n in self._option_ids), names[-1])",
     "        name = names[0]",
     _ac3("GitHub Projects")),

    ("the Jira board drops `needs_person` again: the second instance of the defect", J_BOARD,
     "        keys = column_keys(state, needs_person=needs_person)",
     "        keys = column_keys(state)",
     _ac3("Jira board")),

    ("GitHub hands `set_column` the first name when the board has neither option", GHP,
     "        name = next((n for n in names if n in self._option_ids), names[-1])",
     "        name = next((n for n in names if n in self._option_ids), names[0])",
     f"{AC3}::test_a_github_board_with_neither_column_still_sends_the_pull_request_to_backlog"),

    ("the local board falls back without a word", L_BOARD,
     "            if key != keys[0]:\n",
     "            if False:\n",
     f"{AC3}::test_the_local_board_says_which_column_it_fell_back_from"),

    # ── 3. the vocabulary ───────────────────────────────────────────────────────────────────────
    ("#258'S DEFECT: `needs_review` is not in `CANONICAL_COLUMNS`", COLUMNS,
     '    "needs_review": "Needs Review",\n', "",
     AC456),

    ("`needs_review` is not in the board order", COLUMNS,
     '"in_review", "needs_review", "needs_action", "done",',
     '"in_review", "needs_action", "done",',
     f"{VOCABULARY}::test_the_order_covers_the_map_exactly"),

    ("a card in Needs Review reads as delivered", COLUMNS,
     'AFTER_THE_FACTORY: tuple[str, ...] = ("done",)',
     'AFTER_THE_FACTORY: tuple[str, ...] = ("done", "needs_review")',
     f"{AC456}::test_a_job_may_be_running_on_it_and_it_is_not_delivered"),

    ("a card in Needs Review reads as not yet taken up", COLUMNS,
     'BEFORE_THE_FACTORY: tuple[str, ...] = ("backlog", "todo")',
     'BEFORE_THE_FACTORY: tuple[str, ...] = ("backlog", "todo", "needs_review")',
     AC456),

    # ── 4. the door ─────────────────────────────────────────────────────────────────────────────
    ("the door refuses a card in Needs Review as \"not a column this platform maps\"", TABLE,
     '    "needs_review": State.WAITING_ON_A_PERSON,\n', "",
     f"{AC456}::test_the_door_reads_a_card_there_as_waiting_on_a_person"),

    ("the door reads a card in Needs Review as running", TABLE,
     '    "needs_review": State.WAITING_ON_A_PERSON,\n', '    "needs_review": State.RUNNING,\n',
     f"{AC456}::test_queueing_a_card_from_the_review_column_asks_whether_its_job_still_waits"),

    ("`card_move` asks the engine only for a card in Needs Action", CATALOG,
     "    parked = event is CardEvent.PROMOTED and stage.key in WAITING_ON_A_PERSON_KEYS",
     '    parked = event is CardEvent.PROMOTED and stage.key == "needs_action"',
     f"{AC456}::test_queueing_a_card_from_the_review_column_asks_whether_its_job_still_waits"),

    ("`WAITING_ON_A_PERSON_KEYS` loses `needs_review`", COLUMNS,
     'WAITING_ON_A_PERSON_KEYS: tuple[str, ...] = ("needs_review", "needs_action")',
     'WAITING_ON_A_PERSON_KEYS: tuple[str, ...] = ("needs_action",)',
     f"{AC456}::test_queueing_a_card_from_the_review_column_asks_whether_its_job_still_waits"),

    # ── 5. the readers ──────────────────────────────────────────────────────────────────────────
    ("triage's default reads only the park as waiting on a person", TRIAGE,
     "           waiting_keys: tuple[str, ...] = WAITING_ON_A_PERSON_KEYS,",
     '           waiting_keys: tuple[str, ...] = ("needs_action",),',
     "tests/test_product_triage.py"),

    ("triage compares the waiting stage with the park's key alone", TRIAGE,
     '        if stage in waiting_keys and t.state == "open":',
     '        if stage == "needs_action" and t.state == "open":',
     f"{QUEUE_READERS}::test_a_pull_request_left_unreviewed_on_a_renamed_jira_board_is_waiting_too_long"),

    ("the parked review lists a pull request waiting for its review", PARKED,
     '    waiting = [t for t in tickets if stages.get(t.column) == key and t.state == "open"]',
     '    waiting = [t for t in tickets if stages.get(t.column) in (key, "needs_review")'
     ' and t.state == "open"]',
     f"{QUEUE_READERS}::test_a_pull_request_waiting_for_review_is_not_in_the_parked_review"),

    # ── 6. the panel ────────────────────────────────────────────────────────────────────────────
    ("the panel gives Needs Review no tone and no note", PANEL,
     '  {name:"Needs Review", tone:"queued", note:"a pull request waiting on a person\'s review'
     ' — not stuck"},\n',
     "",
     "tests/test_the_panel_says_what_every_platform_column_means.py"),

    # ── 7. a status two keys share ──────────────────────────────────────────────────────────────
    ("a park a deployment already called \"Needs Review\" reads as `needs_review`", COLUMNS,
     'YIELDS_ITS_DEFAULT_NAME: tuple[str, ...] = ("needs_review",)',
     "YIELDS_ITS_DEFAULT_NAME: tuple[str, ...] = ()",
     QUEUE_READERS),

    ("a status `in_review` and `needs_review` share reads back as `needs_review`", COLUMNS,
     "    return next((key for key in hits",
     "    return next((key for key in reversed(hits)",
     AC456),

    # ── 8. a re-run of init on an existing local board ──────────────────────────────────────────
    ("init skips create on any attached board again", CLI,
     '    elif attached and not getattr(create_board, "completes_an_attached_board", False):',
     "    elif attached:",
     f"{RERUN}::test_the_rerun_adds_needs_review_between_in_review_and_needs_action"),

    ("the local row no longer says create completes an attached board", L_SETUP,
     "    completes_an_attached_board = True",
     "    completes_an_attached_board = False",
     f"{RERUN}::test_the_rerun_adds_needs_review_between_in_review_and_needs_action"),

    ("the existing rows keep their positions, so the new one ties", L_SETUP,
     '                conn.execute("UPDATE columns SET position = ? WHERE project = ? AND key = ?",\n'
     "                             (position, name, key))\n",
     "",
     f"{RERUN}::test_the_rerun_gives_every_column_a_position_of_its_own"),

    ("a re-run restores the platform's names", L_SETUP,
     '"INSERT OR IGNORE INTO columns(project, key, name, position) VALUES (?,?,?,?)",',
     '"INSERT OR REPLACE INTO columns(project, key, name, position) VALUES (?,?,?,?)",',
     f"{RERUN}::test_the_rerun_renames_no_column_the_deployment_had"),

    ("a re-run back-fills the parked cards into the new column", L_SETUP,
     "        return \"\", f\"{panel_url()}/p/{name}/board\"",
     "            conn.execute(\"UPDATE cards SET column_key = 'needs_review' WHERE project = ?\"\n"
     "                         \" AND column_key = 'needs_action'\", (name,))\n"
     "        return \"\", f\"{panel_url()}/p/{name}/board\"",
     f"{RERUN}::test_the_rerun_leaves_the_cards_where_they_were"),

    ("a re-run that added a column says nothing about it", CLI,
     "                typer.echo(f\"✓ board: added the columns it lacked — {now}\" if now != attached",
     "                typer.echo(f\"✓ board: the columns are there — {now}\" if now != attached",
     f"{RERUN}::test_the_rerun_says_what_it_added"),

    ("a re-run that added nothing says it added the columns", CLI,
     "                typer.echo(f\"✓ board: added the columns it lacked — {now}\" if now != attached",
     "                typer.echo(f\"✓ board: added the columns it lacked — {now}\" if True",
     f"{RERUN}::test_a_second_rerun_on_the_seven_row_board_changes_nothing"),

    # ── 9. the write takes the rule the read takes ──────────────────────────────────────────────
    ("GitHub moves a person-gated pull request to an `in_review` the deployment called "
     "\"Needs Review\"", GHP,
     "                 if name and not yields_its_name(key, name, renamed=self._columns)]",
     "                 if name]",
     f"{AC3}::test_a_github_board_whose_review_column_is_called_needs_review_parks_the_pull_request"),

    ("`needs_review`'s default name yields even when no other key carries it", COLUMNS,
     "    return any(other != key and str(spelled).strip().casefold() == wanted",
     "    return any(str(spelled).strip().casefold() == wanted",
     f"{AC2}::test_a_github_board_the_platform_made_gets_the_pull_request_in_its_needs_review"),

    ("the local board warns of its missing column on every move", L_BOARD,
     "                (log.debug if said in _FELL_BACK_SAID else log.warning)(",
     "                log.warning(",
     f"{AC3}::test_the_local_board_says_it_once_and_not_on_every_move"),

    ("a name the deployment wrote for `needs_review` yields like its default", COLUMNS,
     "    if CANONICAL_COLUMNS.get(key, \"\").casefold() != wanted:\n"
     "        return False\n",
     "",
     f"{AC2}::test_a_github_deployment_that_maps_needs_review_onto_its_review_column_gets_what_it_mapped"),
]
