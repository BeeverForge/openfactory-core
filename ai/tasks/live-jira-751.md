# #751, task 10: the live Jira Cloud check (2026-10-19)

Site: a Jira Cloud site (host redacted as `<site>`), team-managed project KAN, basic auth
`<email>:<token>` read from the git-ignored `.env`. All calls went through the real
`JiraTracker` (`openfactory/adapters/tracker/jira.py`) at the worktree's HEAD `88bc1e6`, built as
`JiraTracker(site="https://<site>", project_key="KAN", email=<email>, token=<token>)`; its
`_call` is the adapter's own HTTP path. The scripts redacted the host, the email and the token
from every line they printed.

## Part 1: KAN-4, written by a person in the browser editor

KAN-4's description was written by the human in Jira Cloud's browser editor and recorded by
task 1 as `KAN_4_DESCRIPTION` in
`tests/test_a_jira_description_keeps_its_headings_and_bullets.py`, with `localId`s removed.

Re-fetch, through `JiraTracker._call`:

```
GET https://<site>/rest/api/3/issue/KAN-4?fields=description
```

```
live == recorded (localIds removed): True
localId keys in live answer: 44
```

`JiraTracker._text` on the live answer (HEAD 88bc1e6):

```
'## Acceptance criteria\n- the card 4 is created\n- test\n- sub list\n\n- test 1\n- test 2\n- test 3\n\nTest paragraph → The reviewer ran the interrupted-add test file on git 2.34.1, 2.43.0, 2.47.3 (the worker image\'s git) and 2.55.0 (CI\'s), and it passed on all four. The 746 mutation checks caught all 29 on both 2.43.0 and 2.55.0.\n\ncol1\ncol2\ncol3\naaa\nbbb\nccc\naaa\nbbb\nccc\n\nLine with hard break\nafter hard break'
criteria:      ['the card 4 is created', 'test', 'sub list', 'test 1', 'test 2', 'test 3']
section_names: ['Acceptance criteria']
```

The gate on the live ticket, through the real `JiraTracker.get_ticket("KAN-4")`
(`GET /rest/api/3/issue/KAN-4`, then `parse_ticket_body`), then `machine.spec_verdict`:

```
get_ticket.title: 'GH issue 752'
get_ticket.objective: 'GH issue 752'
get_ticket.acceptance_criteria: 6 items, the six above, verified_by=None
get_ticket.state: open
spec_verdict: ''            # the gate takes the ticket
```

The verdict is an acceptance, not a refusal for another missing section. KAN-4 has no
`## Objective` heading, but `parse_ticket_body` falls back to the title
(`parse.py:501`, `objective=(s.get("objective") or title)`). `machine._spec_gate`
(`machine.py:520`) checks three things: a non-empty objective, at least one criterion, and no item
in both in-scope and out-of-scope. The title gives the objective, the six criteria are there, and
the ticket has no scope sections, so the gate takes it.

Before, the same recorded document read through `jira.py` at `1be1835` (the file loaded from
`git show 1be1835:openfactory/adapters/tracker/jira.py`), with the same title:

```
_text@1be1835: 'Acceptance \ncriteria\nthe card 4 is created\ntest\nsub list\ntest 1\ntest 2\ntest 3\nTest paragraph → <the paragraph above, unchanged>\ncol1\ncol2\ncol3\naaa\nbbb\nccc\naaa\nbbb\nccc\nLine with hard break\nafter hard break'
criteria:      []
section_names: []
spec_verdict:  "ticket has no acceptance criteria — in fact no sections at all. Add a `## Acceptance criteria` heading (or the same heading in the ticket's language) with one `- ` bullet per criterion, so the job can tell when it is done."
```

The live document is valid ADF 57.7.18 (task 9). The fixtures did not cover one thing: the editor
stores an empty paragraph between the bullet list and the numbered list, both under the one criteria
heading, and C4 ends each list on a blank line. Task 1's module now has
`test_the_editors_empty_paragraph_between_two_lists_does_not_end_the_criteria` for it, on the whole
recorded document. It passes on HEAD. With `jira.py` temporarily restored from `1be1835`, it is
red, `1 failed`, `AssertionError: assert [] == ['Acceptance criteria']`, and the file was restored
afterwards (`git status` clean for `jira.py`). Keeping the section open across that blank line is
the parser's own behaviour, which this change does not touch. The test pins that the new
renderer's output keeps it.

## Part 2: a body the factory writes round-trips through the real API

The body comes from the real writer, with a carried block. `CHILD` and `PARENT_BODY` are the
fixtures of `tests/test_what_the_factory_writes_to_jira_reads_back_as_it_wrote_it.py`:

```python
body = activities._child_body(CHILD, "KAN-4", 1, 2, carried=parse.carried_sections(PARENT_BODY))
```

```
'**Focus:** t\n\n## Objective\nWrite the config file.\n\n## Acceptance criteria\n- the file is written\n- a second run leaves it unchanged\n\n## Out of scope\n- Everything covered by the sibling sub-tickets of KAN-4 (this is part 1/2; run in order).\n\n## From the parent card (KAN-4)\n_What the parent card said beyond its objective and acceptance criteria, carried as its author wrote it. This card delivers only its own criteria above; the rest is its sibling cards\'._\n\nAsked by the operations team.\n\n### Context\nThe file is read at boot.\n\nIt is never edited by hand.\n\n_Auto-split from KAN-4 by the pre-flight sizer (ADR-0013)._'
blank lines in body: 8
JiraTracker._adf(body): 23 paragraphs, 8 of them empty
```

It was created through the real `JiraTracker.create_ticket` (`POST https://<site>/rest/api/3/issue`
with `project.key=KAN`, `issuetype.name=Task`, `description=_adf(body)`), with the summary
`[#751 round-trip check] a body the factory wrote reads back as written`:

```
created: KAN-5
```

Read back with `GET https://<site>/rest/api/3/issue/KAN-5?fields=description`:

```
paragraphs stored: 23   types: ['paragraph']   empty: 8
_text(GET) == body (after .strip()): True        # byte-identical; the strings are equal
out_of_scope as written (parse_ticket_body on the raw markdown):
  ['Everything covered by the sibling sub-tickets of KAN-4 (this is part 1/2; run in order).']
out_of_scope via the live JiraTracker.get_ticket("KAN-5"): the same list, equal: True
```

Jira Cloud stores all 8 empty paragraphs `_adf` sends. It does not merge or strip them, and it does
not turn the literal `## ` and `- ` paragraphs into other node types. The read gives back the body
as written, and the split child's out-of-scope item no longer takes in the auto-split line.

### Clean-up

The script read the summary back first and checked that it starts with
`[#751 round-trip check]`. Then:

```
DELETE https://<site>/rest/api/3/issue/KAN-5     -> 2xx, empty body (JiraTracker._call raised nothing)
GET    https://<site>/rest/api/3/issue/KAN-5     -> 404
GET    https://<site>/rest/api/3/issue/KAN-4     -> still present, untouched (read only)
```

KAN-5 is the only issue created, and the only one deleted. KAN-4 was only read.
