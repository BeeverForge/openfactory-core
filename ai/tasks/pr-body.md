Closes #751.

Thanks to @hermes-felipe for the report, with the code path and the fix's shape, and for offering the fork's fix. This branch was written from the plan and does not reuse any of that code or its tests, so it has no `Co-authored-by` line. The report is what made it quick.

## What changed
- **A Jira description written in Jira's own editor now reads as the markdown the parser expects.** `JiraTracker._text` (`openfactory/adapters/tracker/jira.py:238`) used to walk the ADF tree and join every `text` node with `"\n"`. On `1be1835`, a level-2 heading over a one-item bullet with a `code` run read as `'Acceptance criteria\nthe \nx\n is created'`. `criteria()` was `[]`, and the gate (`machine._spec_gate` → `spec_verdict`) refused the card with "no sections at all". `_text` now draws each block:
  - A `heading` is `#` × `attrs.level` (1..6) plus all of its inline content on one line. A missing or out-of-range level is a plain line, never an invented heading.
  - Every list item, bulleted or numbered, nested or not, is a flat `- ` line. That is `azure_devops._HtmlToMarkdown`'s rule, so the converters agree. The `- ` goes on the item's first line whatever block gives it: a paragraph, a code block, or the paragraph after an image.
  - A list ends on one blank line. Without it, #163's lazy continuation would read the paragraph after a list into its last criterion. The editor's own empty paragraph after a list is that blank, not a second one.
  - An empty paragraph is a blank line.
  - A `hardBreak` is a line break.
  - Panels, tables, expands and unknown nodes are still walked for their blocks, so ADR-0022 §4's property holds: a description never reads as empty because of the nodes it uses.
  - Deliberately unchanged: `parse.py`, the Azure converter and `_adf`. GitHub, Azure DevOps and local trackers do not go through `_text`.
- **Second instance of the same defect, named as such: a body the factory writes to Jira now reads back as it wrote it.** `_adf` (`jira.py:341`) writes one paragraph per line and an empty paragraph for a blank line. The old `_text` dropped the empty ones. So on Jira, a split child's `out_of_scope` swallowed the auto-split line under it: `['Everything covered … (this is part 1/2; run in order). _Auto-split from CONT-1 by the pre-flight sizer (ADR-0013)._']`. On GitHub the same field is the first sentence alone. Now `_text(_adf(body)) == body.strip()`, byte for byte. The live API was measured too (below).
- **ADR-0022 §4, the bullet "ADF is walked as a tree", is amended in place, dated 2026-10-19.** The `_text` and `_adf` docstrings say the same. The README row for 0022 is unchanged: other shipped and amended ADRs (0013, 0018, 0050) keep a plain row.
- Mutation plan: `tools/mutations/751_a_jira_description_keeps_its_headings_and_bullets.py`, **21/21 red**.
  - It has M1–M14, with M11 split into three variants (always `## `, `"#" * 0`, the 1..6 bound dropped).
  - M1 and M3 (the defect itself) also run through every vendor's `get_ticket` and the gate.
  - M7 was re-pinned when task 9 rewrote the item loop.
  - M14 is red by an `IndexError`, and its label says so.
  - The other 12 plans that anchor `jira.py` were checked: their 61 anchors are each still found exactly once, so none needed re-pinning. `tests/test_every_mutation_plan_can_run.py`: 6 passed.
- `changes/751.fix.md`.

## Tests first
Three new modules, 34 tests:
- `tests/test_a_jira_description_keeps_its_headings_and_bullets.py` (25)
- `tests/test_a_card_written_in_jiras_editor_passes_the_gate_it_passes_on_github.py` (5)
- `tests/test_what_the_factory_writes_to_jira_reads_back_as_it_wrote_it.py` (4)

Each was run before the code change, with `openfactory/` as on `1be1835`:

| module | when written, on the pre-change `jira.py` | the 34 together, re-run on `1be1835`'s `jira.py` |
|---|---|---|
| headings and bullets (task 1) | 17 failed, 4 passed (21 tests) | 21 failed, 4 passed (25 tests) |
| a card written in Jira's editor (task 2) | 3 failed, 2 passed | 3 failed, 2 passed |
| what the factory writes (task 3) | 4 failed, 0 passed | 4 failed, 0 passed |
| **total** | | **28 failed, 6 passed** |

The four tests task 1's module gained later were each red on the code they hold:
- Task 9 added `test_a_list_item_that_opens_with_another_block_is_still_a_criterion_of_its_own`, three params. On `1db60e3`, the first block renderer, it gave 2 failed, 22 passed. The `code-block` param read `criteria == ["a make test passes", "c"]`. The `image-then-paragraph` param lost the item's `- `. The `nested-list` param passed there: it guards against a `- - child`. On `1be1835` all three fail.
- Task 10 added `test_the_editors_empty_paragraph_between_two_lists_does_not_end_the_criteria`, which reads the whole recorded KAN-4 document. On `1be1835`'s `jira.py` it fails with `assert [] == ['Acceptance criteria']`.

What each red test saw on `1be1835`. The assertion texts were re-measured for this body, with `jira.py` restored from `1be1835` and put back afterwards:

| test | what fails on `1be1835` |
|---|---|
| `test_a_heading_reads_as_its_level_in_hashes_and_its_text[1..6]` | `assert 'Title' == '# Title'` … `== '###### Title'`: no `#` |
| `test_a_heading_written_with_bold_and_code_is_one_line[kan-4-bold, schema-bold-and-code]` | `assert 'Acceptance \ncriteria' == '## Acceptance criteria'`, and `'Acceptance \n…\n for \nmake'`: one line per text node, no `#` |
| `test_a_bullet_list_reads_as_one_dash_line_per_item` | `assert 'a\nb' == '- a\n- b'` |
| `test_a_numbered_list_reads_as_bullets_the_gate_counts[schema, kan-4]` | `assert 'a\nb' == '- a\n- b'`; `assert 'test 1\ntest 2\ntest 3' == '- test 1\n- test 2\n- test 3'` |
| `test_a_nested_list_item_is_a_criterion_of_its_own[schema, kan-4]` | `assert 'parent\nchild' == '- parent\n- child'`; KAN-4's `'the card 4 i…est\nsub list'` has no `- ` either |
| `test_an_inline_mark_inside_a_bullet_does_not_split_the_criterion` | `assert 'the \nx\n is created' == '- the x is created'` |
| `test_a_list_item_of_two_paragraphs_is_one_criterion` | `assert 'first\nsecond' == '- first\nsecond'` |
| `test_a_list_item_that_opens_with_another_block_is_still_a_criterion_of_its_own[code-block, image-then-paragraph, nested-list]` | `assert 'a\nmake test passes\nc' == '- a\n- make test passes\n- c'`, and the same shape for the image and the nested list: no `- ` on any item |
| `test_a_paragraph_after_a_list_is_not_read_into_its_last_criterion` | `assert 'Acceptance c…is was agreed' == '## Acceptanc…is was agreed'`: no `#`, no `- ` (the naive fix with no blank line after the list gives `["a", "b Note…"]`, which is cut M5) |
| `test_the_editors_empty_paragraph_between_two_lists_does_not_end_the_criteria` | `assert [] == ['Acceptance criteria']` |
| `test_a_hard_break_is_a_line_break_not_a_glued_word` | `assert 'line one\nline two' == '- line one\nline two'` |
| `test_the_same_card_gives_the_gate_the_same_criteria_on_every_vendor[jira, jira_pt_br]` | `acceptance_criteria == []`, objective is the title, `spec_verdict` says "ticket has no acceptance criteria — in fact no sections at all" |
| `test_a_jira_card_in_the_board_read_carries_the_same_criteria` | `criteria(summary.body) == []` |
| `test_a_body_the_factory_wrote_reads_back_byte_identical[3 bodies]` | blank lines lost: `'a\nb' != 'a\n\n\nb'` |
| `test_a_split_childs_out_of_scope_does_not_swallow_the_auto_split_line_on_jira` | `out_of_scope[0]` ends with `_Auto-split from CONT-1 by the pre-flight sizer (ADR-0013)._` |

Six tests pass on `1be1835` on purpose. Each says so in its docstring.
- **`test_a_heading_with_no_level_is_read_as_a_plain_line[no-attrs, level-9, level-0]`** guards the new renderer's 1..6 bound. **It cannot be red on main:** the old walk drew every heading as a plain line, so a plain line is what main already gives. The plan's C1 row lists this test with C1's red-on-main tests; that row is wrong for this test. M11a/b/c turn it red.
- **`test_a_table_cell_and_an_expand_still_give_up_their_text`** guards ADR-0022's property, which the old walk already had. M10 turns it red. So does M10's cut against the unchanged `tests/test_tracker_is_vendor_neutral.py::test_jira_reads_a_description_written_with_rich_formatting`.
- **The `github` and `azure_devops` params of the cross-vendor test** are the "unchanged elsewhere" control: the same card through each vendor's `get_ticket` passes the gate.
  - On GitHub the criterion with the code run keeps its backticks, because they are the stored text. Azure and Jira read it plain, so each param names its own vendor's criteria.
  - The card ends at its list, because Azure's converter glues a paragraph after a list into the last item (follow-up 2). C4 holds that property for Jira.

**One assertion changed after it was written (task 4).** `test_a_heading_written_with_bold_and_code_is_one_line[schema-bold-and-code]` first asserted `criteria_heading()` of `'## Acceptance criteria for make'`. No renderer could satisfy that, because that heading is not an alias of the criteria section. It now asserts `section_names(body) == ['Acceptance criteria for make']`. It was re-checked red on the old code: the three modules on the old `jira.py` gave 24 failed, 6 passed, as recorded.

## Reproduced by hand
**The issue's shape, on `1be1835`:** a level-2 heading "Acceptance criteria" over one bullet `the `, code `x`, ` is created`:
```
_text  -> 'Acceptance criteria\nthe \nx\n is created'
criteria(...) -> []
```
On this branch the same document reads `'## Acceptance criteria\n- the x is created'` (the code run is drawn plain on one line), and `criteria == ['the x is created']`.

**A live Jira Cloud site, team-managed project, 2026-10-19.** The host, email and token are redacted. Every call went through the real `JiraTracker`.

1. KAN-4 was written by a person in the browser editor. It has a Heading 2 with a bold run, a bullet list with a nested item, a numbered list, a paragraph, a table and a hard break. `GET /rest/api/3/issue/KAN-4?fields=description` equals the recorded `KAN_4_DESCRIPTION` once its 44 `localId`s are removed.
   - Before, with `jira.py` from `1be1835`:
     ```
     _text@1be1835: 'Acceptance \ncriteria\nthe card 4 is created\ntest\nsub list\ntest 1\ntest 2\ntest 3\nTest paragraph → …\ncol1\ncol2\ncol3\naaa\nbbb\nccc\naaa\nbbb\nccc\nLine with hard break\nafter hard break'
     criteria: []    section_names: []
     spec_verdict: "ticket has no acceptance criteria — in fact no sections at all. …"
     ```
   - After, through the real `JiraTracker.get_ticket("KAN-4")`:
     ```
     _text: '## Acceptance criteria\n- the card 4 is created\n- test\n- sub list\n\n- test 1\n- test 2\n- test 3\n\nTest paragraph → …\n\ncol1\ncol2\ncol3\naaa\nbbb\nccc\naaa\nbbb\nccc\n\nLine with hard break\nafter hard break'
     criteria: ['the card 4 is created', 'test', 'sub list', 'test 1', 'test 2', 'test 3']
     section_names: ['Acceptance criteria']
     spec_verdict: ''      # the gate takes the ticket
     ```
   - The live document had one shape the fixtures did not: an empty paragraph between the two lists under one heading. It gets its own test, named above.
2. **The write path round-trips.** The body came from `activities._child_body("KAN-4", 1, 2, carried=parse.carried_sections(PARENT_BODY))`. It has 8 blank lines; `_adf` makes it 23 paragraphs, 8 of them empty. It went through the real `create_ticket` and came back as KAN-5.
   ```
   GET /rest/api/3/issue/KAN-5?fields=description
   paragraphs stored: 23   types: ['paragraph']   empty: 8
   _text(GET) == body (after .strip()): True
   out_of_scope via get_ticket("KAN-5") == parse_ticket_body(body).out_of_scope: True
   ```
   Jira stores the empty paragraphs as sent and does not turn the literal `## ` and `- ` paragraphs into other nodes. KAN-5 was then deleted (`DELETE` → 2xx, `GET` → 404). KAN-4 was only read.

**The ADF schema.** Checked against `@atlaskit/adf-schema` 57.7.18, at https://unpkg.com/@atlaskit/adf-schema@57.7.18/dist/json-schema/v1/full.json, with jsonschema 4.26.0 (Draft 4). Every fixture in the three modules and the recorded KAN-4 document validate. The three deliberately invalid headings (no level, level 0, level 9) are the exception: they guard the bound. The schema showed that a `listItem` may open with a `codeBlock`, a `mediaSingle` or a nested list. That is the same defect (the item's `- ` was lost), so it is fixed here (task 9).

## Checks
- `make lint`: clean (ruff `All checks passed!`; shellcheck through docker, exit 0).
- The three new modules: 34 passed. `tests/test_tracker_is_vendor_neutral.py`: 17 passed, unchanged.
- Blast radius: 38 modules read a Jira body, `_text`/`_adf`, or the Jira tracker. That is the plan's list plus a grep of `tests/` for `JiraTracker`, `tracker/jira`, `tracker.jira`, `board/jira`, `_Jira`, `_text(` and `_adf(`. Result: **1473 passed, 37 skipped, 0 failed**. All 37 skips are in `test_the_action_layer.py`, because the Slack add-on is not installed. No expectation changed: no test compared an exact `_text` string that the kept blank lines alter.
- The whole suite, collected **18730 = 18696 + 34**. The 34 are the three new modules; no existing test module changed.

  | run | branch (`8ed2548`) | `main` (`1be1835`, same machine) |
  |---|---|---|
  | `-n auto` | 4 failed, 18519 passed, 207 skipped | 4 failed, 18485 passed, 207 skipped |
  | `-n auto -p no:randomly` | 4 failed, 18519 passed, 207 skipped | 5 failed, 18484 passed, 207 skipped |

  The machine was loaded by other worktrees' suites, at load average 25–40 on 12 cores (38–62 for main's runs). The failures:
  - **The three docker previews** (`test_a_preview_runs_on_a_real_daemon`, `test_a_preview_starts_on_a_real_daemon`, `test_a_preview_opens_on_one_machine`) failed in both runs, on main and on the branch, all the same way: `docker compose up` exit 1, `container openfactory-pv-acme-<n>-db-1 is unhealthy`. This is the known docker preview flake.
  - **The `board.db` races** fail with `OperationalError: database is locked` under load, on main too. In random order, `test_the_board_lives_in_one_file.py::test_two_openers_of_a_BRAND_NEW_file_both_get_in` failed on both. In fixed order, main also failed `test_two_writers_never_take_the_same_number`, and the branch failed neither.
  - **In fixed order only, on the branch only:** `tests/test_a_stream_ends_when_its_credential_does.py::test_a_person_DROPPED_from_the_token_map_loses_their_stream_and_nobody_else` hit a `TimeoutError` in a 5 s `asyncio.wait_for(queue.get(), timeout=5)` under load.
    - Run alone afterwards with `-p no:randomly`, it passed 5 of 5, and its module passed 36/36.
    - The diff cannot reach it: the only package file this branch changes is `jira.py`, and this test configures the `github` tracker.
    - **I did not run it on `main`.** It was not red when re-run, so the comparison was not taken. A load timeout is my reading, not a measurement on main.
- Locale: the cross-vendor module, with its `jira_pt_br` param (Portuguese headings), gave 5 passed under `LANG=LC_ALL=pt_BR.UTF-8` and 5 passed under `LANG=LC_ALL=C.UTF-8`. The change is a pure function over JSON; it runs no subprocess and calls no locale-aware API.
- Deployments:
  - **Team-managed Jira Cloud:** measured live (KAN).
  - **Company-managed projects: not tested live.** They use the same ADF editor and endpoint, so they should read the same, but that rests on the shared schema, not on a measurement.
  - **Site language:** changes the heading words, not the shape. The parser's alias table covers the words, and the pt-BR fixture covers one non-English heading. The live headings were English.
  - **Jira Data Center / Server: out of scope.** It serves API v2 with wiki markup, and the tracker only calls `/rest/api/3`. This is unchanged by this PR.
- Docs re-grep (`git grep -n -i "ADF\|walked as a tree\|plain text" -- docs openfactory`): the only claim about how a Jira description is read is ADR-0022 §4, amended here.

## Risks, not addressed here
- **A read-modify-write of an editor-written card now writes literal `## ` and `- ` paragraphs.** This is the second instance's write side. `_adf` still sends markdown as plain paragraphs. So refine through `update_body`, or the panel's edit door, writes `## Objective` back as a literal paragraph where it used to write a bare `Objective`. Both lose the editor's formatting, as before. The new text at least reads back as a section. Writing real `heading` and `bulletList` nodes changes what a person sees on the Jira card, so it needs its own live measurement. *Follow-up 1: the Jira write path sends markdown as literal paragraphs.*
- *Follow-up 2: Azure's HTML converter has the same two holes.* Measured on `1be1835`: `description_text('<h2>Acceptance criteria</h2><ol><li><p>a</p></li><li>b<ul><li>c</li></ul></li></ol><p>after</p>')` → `'## Acceptance criteria\n-\na\n- b\n- c\nafter'`. A `<li><p>` gives an empty bullet, and a paragraph after a list is glued into its last item. It is a different adapter.
- *Follow-up 3: inline nodes that carry no `text` node are dropped:* `mention`, `inlineCard`, `emoji`, `date`, `status`. "notify @Ana" reads as "notify ", before and after this change.
- *Follow-up 4: only `## ` opens a section.* A Jira author who picks Heading 1 or 3 for "Acceptance criteria" is still refused, as on GitHub, and the refusal cannot name that heading. This is a parser decision across all vendors.
- *Follow-up 5: an action-item list (`taskList`) or a `decisionList` is read as bare lines, not criteria.* Measured against ADF 57.7.18: `taskItem` content is inline, so `'## Acceptance criteria\nthe \nx\n is created\ndone one\nafter'` gives `criteria == []`. It read the same way on `1be1835`, so nothing regresses. Fixing it needs a choice the issue does not make: draw `- [ ] x`/`- [x] x` or `- x`, and decide whether a DONE item is still a criterion.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
