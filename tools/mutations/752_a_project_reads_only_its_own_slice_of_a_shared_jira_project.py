"""Several registry projects on one Jira project each read only their own slice of it (#752).

The claims, each held by a test this plan cuts under:

  - a project's `scope_jql` reaches its tracker and its board from the registry row;
  - every read the Jira board makes (`columns`, `items_in_status`, `place_after` through it) and
    `JiraTracker.list_tickets` carry `project = "<KEY>" AND (<scope>)`, so a poller picks up only
    its own slice;
  - `find_ticket`, the "is it already filed?" check, asks only within the slice;
  - the scope is wrapped in parentheses, so an OR inside it cannot widen the read past the project;
  - an empty slice is an empty board: the existence probe stays unscoped and is not skipped;
  - a project that declares no scope, or only whitespace, sends today's JQL byte for byte;
  - a search Jira refuses under a scope is named in the warning, and the read stays unreadable;
  - the configuration reference's Jira example declares the scope single-quoted, and it reaches
    the tracker intact through a registry file;
  - the edit/close/remove gate asks a scoped board whether a card it did not return is in the
    slice (`JiraProjectBoard.holds`), refuses one that is not by name, naming the scope, and
    refuses as unreadable when that search cannot be made; an unscoped board asks nothing more
    (review round 1 of #752);
  - the product role's queueing asks the same of a card its board read did not return, and
    refuses another project's card rather than move it back into the queue (review round 2),
    and refuses as an unreachable board when that search cannot be made (review round 3);
  - the pt-BR refusal of a card outside the slice names the project and both ways out, as the
    en one does (review round 3);
  - the queueing asks the slice about a card when the batch's board read was refused, so one 429
    followed by a good read cannot queue another project's card, and an empty slice (`{}`) is a
    read, asked about like any other (review of PR #884, points 1 and 6).
"""

TEST = "tests/test_several_projects_on_one_jira_project_read_only_their_own_slice.py"
BOARD = "openfactory/adapters/board/jira.py"
JIRA = "openfactory/adapters/tracker/jira.py"
REGISTRY = "openfactory/adapters/tracker/registry.py"
DOCS = "docs/reference/configuration.md"
CATALOG = "openfactory/actions/catalog.py"
PRODUCT = "openfactory/product/module.py"
VOICE = "openfactory/product/voice.py"
SLICE = TEST
EMPTY = "tests/test_an_empty_slice_of_a_jira_project_is_not_a_missing_project.py"
FILED = "tests/test_a_ticket_another_project_filed_on_one_jira_project_is_not_read_as_already_filed.py"

MUTATIONS = [
    ("the registry row drops the project's scope, and its board reads the whole Jira project",
     REGISTRY,
     'scope_jql=options.get("scope_jql", ""),',
     'scope_jql="",',
     f"{SLICE}::test_the_scope_a_project_declares_reaches_its_jira_board_from_the_registry"),

    ("…and the every-read test sees it too", REGISTRY,
     'scope_jql=options.get("scope_jql", ""),',
     'scope_jql="",',
     f"{SLICE}::test_every_read_the_jira_board_makes_carries_the_projects_scope"),

    ("`columns` reads the whole Jira project", BOARD,
     'self._search(f"{self._issues_where()} ORDER BY Rank ASC")',
     'self._search(f\'project = "{self.project_key}" ORDER BY Rank ASC\')',
     f"{SLICE}::test_every_read_the_jira_board_makes_carries_the_projects_scope"),

    ("`items_in_status` reads the whole Jira project", BOARD,
     "self._search(f'{self._issues_where()} AND status",
     "self._search(f'project = \"{self.project_key}\" AND status",
     f"{SLICE}::test_every_read_the_jira_board_makes_carries_the_projects_scope"),

    ("…and two projects' pollers each pick up the other's ticket", BOARD,
     "self._search(f'{self._issues_where()} AND status",
     "self._search(f'project = \"{self.project_key}\" AND status",
     f"{SLICE}::test_a_project_polls_only_the_tickets_in_its_own_scope"),

    ("`list_tickets` reads the whole Jira project", JIRA,
     "clauses = [within_scope(f'project = \"{self.project_key}\"', self.scope_jql)]",
     "clauses = [f'project = \"{self.project_key}\"']",
     f"{SLICE}::test_every_read_the_jira_board_makes_carries_the_projects_scope"),

    ("…and an empty slice is searched across the whole project", JIRA,
     "clauses = [within_scope(f'project = \"{self.project_key}\"', self.scope_jql)]",
     "clauses = [f'project = \"{self.project_key}\"']",
     EMPTY),

    ("`find_ticket` asks the whole Jira project, and a ticket outside the slice reads as filed",
     JIRA,
     "jql = (within_scope(f'project = \"{self.project_key}\"', self.scope_jql)",
     "jql = (f'project = \"{self.project_key}\"'",
     FILED),

    ("the scope is ANDed without parentheses, and an OR inside it escapes the project", JIRA,
     'return f"{where} AND ({scope})" if scope else where',
     'return f"{where} AND {scope}" if scope else where',
     f"{SLICE}::test_a_scope_with_an_OR_cannot_widen_the_read_past_the_project"),

    ("an empty slice is answered for by the slice alone, and reads as a missing project", JIRA,
     "if not rows and not self._project_exists():",
     "if not rows:",
     f"{EMPTY}::test_an_empty_slice_is_read_as_empty_and_the_project_is_asked_unscoped"),

    ("an empty scope emits `AND ()`, and a project that declared none sends a different query",
     JIRA,
     'return f"{where} AND ({scope})" if scope else where',
     'return f"{where} AND ({scope})"',
     f"{SLICE}::test_a_project_that_declares_no_scope_reads_its_jira_project_exactly_as_before"),

    # the one normalisation: on 2026-10-19 this cut was GREEN while `within_scope` stripped the
    # scope a second time, so the tracker's `.strip()` was dead; the helpers now take it stripped
    ("a whitespace-only scope is kept as a scope, and emits `AND (  )`", JIRA,
     'self.scope_jql = str(scope_jql or "").strip()',
     'self.scope_jql = str(scope_jql or "")',
     f"{SLICE}::test_a_project_that_declares_no_scope_reads_its_jira_project_exactly_as_before"),

    ("a search Jira refused under a scope no longer names the scope, and the person reading the "
     "warning looks at the credential", JIRA,
     'return f" within scope_jql {scope!r}" if scope else ""',
     'return ""',
     f"{SLICE}::test_a_scope_jira_refuses_is_named_and_the_read_stays_unreadable"),

    ("the configuration reference's Jira example no longer declares a scope", DOCS,
     "                          scope_jql: 'labels = \"of-api\"',    # this project's slice of DAR\n",
     "",
     f"{SLICE}::test_the_documented_scope_arrives_intact_from_a_registry_file"),

    ("a scoped board says it holds every card, and another project's running card is edited, "
     "closed and removed from this one", BOARD,
     "        if not self._scope():\n            return True\n        key = canonical_ref(ref)\n",
     "        return True\n",
     f"{SLICE}::test_a_card_outside_the_slice_is_not_read_as_never_taken_up"),

    ("an unscoped board searches for every card `columns()` did not return", BOARD,
     "        if not self._scope():\n            return True\n        key = canonical_ref(ref)\n",
     "        key = canonical_ref(ref)\n",
     f"{SLICE}::test_an_unscoped_jira_boards_gate_asks_nothing_more"),

    ("the gate ignores `holds`, and a card outside the slice reads as nobody moved it", CATALOG,
     "inside = holds(issue) if callable(holds) else True",
     "inside = True",
     f"{SLICE}::test_a_card_outside_the_slice_is_not_read_as_never_taken_up"),

    ("a slice that could not be asked about the card reads as holding it", CATALOG,
     "        if inside is None:\n            return unreadable\n",
     "",
     f"{SLICE}::test_a_slice_that_cannot_be_asked_about_a_card_refuses_as_unreadable"),

    ("the refusal of a card outside the slice no longer names the scope", CATALOG,
     "f\"{f' ({within})' if within else ''}, so {proj.name} cannot tell",
     "f\", so {proj.name} cannot tell",
     f"{SLICE}::test_a_card_outside_the_slice_is_refused_by_name_naming_the_scope"),

    ("the scope the refusal names keeps its leading space, and reads `( within scope_jql …)`",
     BOARD,
     "        return scope_named(self._scope()).strip()\n",
     "        return scope_named(self._scope())\n",
     f"{SLICE}::test_a_card_outside_the_slice_is_refused_by_name_naming_the_scope"),

    ("the product role's queueing ignores `holds`, and another project's running card is moved "
     "back into the queue", PRODUCT,
     "                inside = holds(str(number)) if callable(holds) else True\n",
     "                inside = True\n",
     f"{SLICE}::test_another_projects_running_card_is_not_queued_from_this_one"),

    ("a slice the queueing could not ask about reads as held, and the card goes to the door",
     PRODUCT,
     "                if inside is not True:\n",
     "                if inside is False:\n",
     f"{SLICE}::test_a_slice_that_cannot_be_asked_about_a_card_refuses_to_queue_it"),

    ("the queueing skips the slice when its board read was refused, and after one 429 the door's "
     "own read queues another project's running card", PRODUCT,
     "            if where is None or not where.get(str(number)):\n",
     "            if where is not None and not where.get(str(number)):\n",
     f"{SLICE}::test_a_board_read_refused_once_does_not_queue_another_projects_card"),

    ("an empty slice reads as an unread one, the card is not asked about, and the door queues "
     "another project's card", PRODUCT,
     "            if where is None or not where.get(str(number)):\n",
     "            if where and not where.get(str(number)):\n",
     f"{SLICE}::test_an_empty_slice_does_not_queue_another_projects_card"),

    ("the pt-BR refusal of a card outside the slice loses its middle, and no longer says nothing "
     "was changed nor how to act on the card", VOICE,
     '"saber se a fábrica já pegou esse card. Nada foi alterado — se ele é de outro "\n'
     '                  "projeto, mova-o por lá; se é do próprio {project}, inclua-o no escopo e tente "\n',
     '"saber. "\n',
     f"{SLICE}::test_another_projects_running_card_is_not_queued_from_this_one"),
]
