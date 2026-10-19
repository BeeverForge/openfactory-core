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
    the tracker intact through a registry file.
"""

TEST = "tests/test_several_projects_on_one_jira_project_read_only_their_own_slice.py"
BOARD = "openfactory/adapters/board/jira.py"
JIRA = "openfactory/adapters/tracker/jira.py"
REGISTRY = "openfactory/adapters/tracker/registry.py"
DOCS = "docs/reference/configuration.md"
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
]
