# Plan — #751: A Jira description loses its headings and bullets, so the sizing gate sees no Acceptance criteria section

Issue: https://github.com/Open-Factory-Digital/openfactory-core/issues/751
Branch: fix/751-jira-headings-bullets-lost
Worktree: /home/henrique/projetos/openfactory-core-751
Milestone: 0.7.0 (RC Monday 2026-10-19, stable Wednesday 2026-10-21; if it is not finished, it moves to the next weekly cycle)
Reporter: hermes-felipe (downstream deployer, ~19 projects on one Jira site). They offered their fork's fix as a PR. See "Hand-off questions".

## The issue, in one paragraph
`JiraTracker._text` (`openfactory/adapters/tracker/jira.py:237-257` on `1be1835`; `:230` in v0.6.0-rc.2)
walks an ADF document and joins **every text node** with `"\n"`. `parse.py` reads only markdown
shapes. A section is a line starting with `"## "` exactly (`_sections`, `parse.py:117`), and a
criterion is a `"- "` bullet or a Gherkin scenario (`_read_criteria`). So in a ticket written in
Jira's editor, where typing `## ` or `- ` turns into a `heading` or `bulletList` node, the
description reaches `parse_ticket_body` as `Acceptance criteria\nitem`. The gate
(`orchestrator/machine.py:_spec_gate` → `_spec_refusal`) then says "no sections at all".

Measured on `1be1835`: a level-2 heading plus a one-item bullet whose text carries a `code` mark
reads as `'Acceptance criteria\nthe \nx\n is created'`, and `criteria()` is `[]`. Reading the code
turned up three more things the issue does not say:
1. **Inline nodes are split across lines.** A heading or bullet with a bold or code run
   becomes several lines, so drawing a `#`×level in front of the first text node alone still breaks
   `## Acceptance **criteria**`. The issue's "plus its text" must mean "plus all of its inline
   content, joined with nothing".
2. **The fix as worded would create a new defect.** Once items read as `- ` lines, a paragraph
   that follows a list in the editor sits on the very next line. `_continues_the_item`
   (#163, lazy continuation) then reads it into the last criterion. A list must end with a blank
   line.
3. **Second instance of the same defect, on the platform's own writes.** `_adf` writes one
   paragraph per line, with an empty paragraph for a blank line. `_text` drops empty paragraphs,
   so blank lines are lost on the way back. Measured: `_text(_adf(_child_body(...)))` returns
   `"…(this is part 1/2; run in order).\n_Auto-split from CONT-1 by the pre-flight sizer
   (ADR-0013)._"`, and the parsed `out_of_scope` of a split child on Jira is
   `['Everything covered … run in order). _Auto-split from CONT-1 by the pre-flight sizer
   (ADR-0013)._']`. On GitHub it is the first sentence alone. The cause is the same: the walk
   discards the shape of the blocks.

After the fix, a description written in Jira's editor reads as the markdown the parser expects.
A heading is `#`×level plus its inline text. Each list item, bulleted or numbered, is a `- ` line.
A list ends with a blank line. An empty paragraph is a blank line. Unknown containers (panel,
table, expand) are still walked for their text, so the ADR-0022 property stays: a description is
never read as empty because of the nodes it uses. GitHub, Azure and local trackers are untouched,
because only Jira goes through `_text`.

### Settled from the code, not invented
- **Other trackers**: GitHub and local pass markdown through as written. Azure converts HTML with
  `_HtmlToMarkdown` (`azure_devops.py:977`), which already draws `<hN>` as `#`×N and every `<li>`,
  inside `<ul>` or `<ol>`, as `- `, flat. The Jira rendering follows that same rule, so the three
  converters agree. Their behaviour stays as it is, and a cross-vendor test pins the GitHub and
  Azure readings as the controls.
- **Ordered lists**: `- `, like Azure's `<ol><li>`. `parse.py` does not read `1.` as a criterion
  (`_keyword` → prose; `tests/test_what_the_card_shows_inside_a_bullet_is_what_is_read.py:117`
  treats `1.` as a block that starts a new item). Drawing `1.` would leave a numbered list of
  criteria unread. The issue says "a `listItem` as `- `" and does not tell the two lists apart.
- **Nested lists**: each nested item is a `- ` line of its own, flat, as Azure does. The issue's
  "stop descending" taken literally would glue the child items' text onto the parent's line, so
  the nested lists are descended and drawn. Indenting them was considered: the parser treats an
  indented `- ` as an item of its own too, so indentation would only change what a human reads in
  the brief. Flat is the sibling's rule. See open question Q2.
- **A list item with several paragraphs**: the first paragraph after `- `, and the next ones on the
  lines directly below. `#163`'s lazy continuation joins them into one criterion, exactly as it
  does on GitHub.
- **`hardBreak`**: a line break. Without this, joining inline nodes with nothing would glue two
  lines into one word.
- **Heading level**: `#`×`attrs.level` for 1..6. A level that is missing or out of range is drawn
  as a plain paragraph, never as an invented heading. Only `## ` is a section to the parser, as on
  GitHub (see Follow-ups).
- **Write path**: openfactory writes ADF to Jira with `_adf` (`jira.py:260`). It is used by
  `comment` (:373), `create_ticket` (:523) and `update_body` (:691), and it sends markdown as plain
  paragraphs, one per line: it never writes `heading` or `bulletList` nodes. "Round trip" in this
  plan therefore means two separate properties. (a) An editor-written ADF document reads as
  markdown, which is the issue. (b) A body the factory wrote with `_adf` reads back byte-identical,
  which is the second instance. Making `_adf` write real headings and lists is a different change
  with a different blast radius (what a person sees on the Jira card) and is a follow-up.
  Consequence to state in the PR: a read-modify-write of an editor-written card (refine through
  `update_body`, the panel's edit door at `catalog.py:5046`) now writes `## Objective` as a literal
  paragraph instead of a bare `Objective` paragraph. Both lose the editor formatting, as they do
  today, but the new text reads back as a section.
- **Comments** are read through `_text` as well (`jira.py:402`). A bulleted answer from a requester
  now reaches the model as `- ` lines. Nothing parses comments for sections, so no gate changes.
- **Jira Cloud only**: the adapter uses `/rest/api/3`, where descriptions are ADF. Data Center's
  v2 wiki-markup string is not a supported shape today and stays out of scope.

## Acceptance criteria → tests
The issue's acceptance criterion is its "Fix" section: a heading reads as `#`×level plus its text,
a list item reads as `- ` plus its text, and a round-trip test with a level-2 heading and a bullet
list pins it. Criteria 3–6 follow from the findings above. Criterion 6 is the second instance and is
marked as such.

| criterion | test that holds it | red on main because |
|---|---|---|
| C1. "render a `heading` node as `#`×`attrs.level` plus its text", with all of its inline content on one line | `tests/test_a_jira_description_keeps_its_headings_and_bullets.py::test_a_heading_reads_as_its_level_in_hashes_and_its_text` (levels 1–6), `::test_a_heading_written_with_bold_and_code_is_one_line`, `::test_a_heading_with_no_level_is_read_as_a_plain_line` | `_text` returns `Acceptance criteria` with no `#`. A heading with marks comes back as one line per text node |
| C2. "a `listItem` as `- ` plus its text", for bulleted and numbered lists, nested items included, inline marks kept on one line | same file: `::test_a_bullet_list_reads_as_one_dash_line_per_item`, `::test_a_numbered_list_reads_as_bullets_the_gate_counts`, `::test_a_nested_list_item_is_a_criterion_of_its_own`, `::test_an_inline_mark_inside_a_bullet_does_not_split_the_criterion`, `::test_a_list_item_of_two_paragraphs_is_one_criterion` | items come back with no `- `, and `the \nx\n is created` is three lines |
| C3. "A round-trip test with an ADF document containing a level-2 heading and a bullet list pins it", through the gate the issue names | `tests/test_a_card_written_in_jiras_editor_passes_the_gate_it_passes_on_github.py::test_the_same_card_gives_the_gate_the_same_criteria_on_every_vendor` (params `github`, `azure_devops`, `jira`, plus a pt-BR `## Critérios de aceite` card), through each vendor's own `get_ticket`, asserting the criteria and `spec_verdict(ticket) == ""` | the `jira` params: `acceptance_criteria == []`, and `spec_verdict` says "no sections at all". The `github` and `azure_devops` params pass on main **on purpose**: they are the "unchanged elsewhere" control, and the PR must say so |
| C3b. the list read (queue, triage, refine) sees the same thing as `get_ticket` | same file `::test_a_jira_card_in_the_board_read_carries_the_same_criteria` (`list_tickets` → `_summary` → `parse.criteria(body)`) | `criteria(summary.body) == []` |
| C4. a paragraph after a list is not read into its last criterion | `tests/test_a_jira_description_keeps_its_headings_and_bullets.py::test_a_paragraph_after_a_list_is_not_read_into_its_last_criterion` (asserts `criteria(...) == ["a", "b"]` exactly) | `criteria(...) == []`, for the issue's reason. Without the blank line, the naive fix gives `["a", "b Note…"]`, which is mutation cut M5 |
| C5. ADR-0022's property holds: text inside containers (panel, table, expand) and a `hardBreak` is never lost | existing `tests/test_tracker_is_vendor_neutral.py::test_jira_reads_a_description_written_with_rich_formatting` (stays green, unchanged), plus new `::test_a_table_cell_and_an_expand_still_give_up_their_text` and `::test_a_hard_break_is_a_line_break_not_a_glued_word` in the new file | the table/expand test is green on main and is a regression guard (said so in the PR). The hard-break test is red on main only if it asserts the exact `"line one\nline two"` inside a heading or bullet (`- line one\nline two`), so write it that way |
| C6. (second instance) a body the factory wrote to Jira reads back as it wrote it, blank lines included | `tests/test_what_the_factory_writes_to_jira_reads_back_as_it_wrote_it.py::test_a_body_the_factory_wrote_reads_back_byte_identical` (bodies built by the real writers: `activities._child_body`, with and without a carried block, and a multi-blank-line body) and `::test_a_split_childs_out_of_scope_does_not_swallow_the_auto_split_line_on_jira` | blank lines are dropped (`'**Focus:** t\n## Objective…'`), and `out_of_scope[0]` ends with `_Auto-split from CONT-1 …_` |

## Tasks
- [x] 0. Baseline. In a **detached worktree of `origin/main` at `1be1835`** (not this one; see
  memory "Baseline needs a git worktree"), run `.venv/bin/python -m pytest -q -n auto` and
  `-n auto -p no:randomly`, and record both counts in `ai/tasks/baseline.md` (the known docker
  preview flake in ordered `-n auto` gets a note, not a fix). The red counts in tasks 1–3 are
  measured in this worktree before task 4 touches `jira.py`.
- [x] 1. Write `tests/test_a_jira_description_keeps_its_headings_and_bullets.py` (C1, C2, C4, C5).
  Build ADF fixtures in the shape the Jira editor stores, taken from task 10's recorded document
  where it exists and from the ADF schema otherwise: `heading` with `attrs.level`; `bulletList` /
  `orderedList` → `listItem` → `paragraph` → `text` with `marks`; nested `bulletList` inside a
  `listItem`; `hardBreak`; `table` → `tableRow` → `tableCell` → `paragraph`; `expand`. Assert on
  **two levels**: the exact string `JiraTracker._text(adf)` returns, and what the parser reads from
  it (`parse.criteria`, `parse.section_names`). The lessons say not to pin a rendering the gate
  does not read. Exact expectations:
  - heading L2 `[text "Acceptance "][text "criteria", strong]` → `"## Acceptance criteria"`
  - levels 1..6 → `"#"*n + " Title"`. Heading with no `attrs` or `level: 9` → `"Title"`
  - bulletList [a, b] → `"- a\n- b"`. orderedList [a, b] → `"- a\n- b"`, `criteria == ["a","b"]`
  - listItem [p "parent", bulletList[p "child"]] → `"- parent\n- child"`, criteria `["parent","child"]`
  - listItem [p "the ", code "x", " is created"] → criterion `"the x is created"`
  - listItem [p "first", p "second"] → criterion `"first second"`
  - [heading AC, bulletList[a, b], paragraph "Note that this was agreed"] → criteria exactly `["a","b"]`
  - a hardBreak inside a list item → the criterion keeps both halves, `"line one line two"`, with
    no space lost. The exact string from `_text` is `"- line one\nline two"`
  Run it on this tree before any code changes. Record "N failed, M passed" and confirm that each
  failure is the missing `#`/`- `, or the split inline runs. The table/expand test is expected to
  pass (a guard), and the docstring says so.
- [x] 2. Write `tests/test_a_card_written_in_jiras_editor_passes_the_gate_it_passes_on_github.py`
  (C3, C3b). Reuse `_Gh`, `_Jira`, `_ado_tracker` from `tests/test_the_tracker_has_a_read_side.py`,
  as `test_the_tracker_reads_what_a_person_wrote.py` does. Parametrize one card (Objective
  section plus a two-item criteria list, including a `code` mark) as each vendor's editor stores it:
  GitHub markdown, Azure `<h2>`/`<ul><li>` HTML with `multilineFieldsFormat: html`, and Jira ADF
  heading/bulletList. Add a pt-BR card (`Critérios de aceite`, `Objetivo`) on Jira. Through each
  vendor's `get_ticket`, assert the same `objective`, the same `[c.text for c in
  acceptance_criteria]`, and `machine.spec_verdict(ticket) == ""`. Add the `list_tickets` case for
  Jira (fake `search/jql` page, as `JIRA_PAGE_2` is shaped) asserting
  `parse.criteria(summary.body)`. On main the Jira params fail (criteria `[]`; the verdict says "no
  sections at all") and the GitHub/Azure params pass. Record both.
- [x] 3. Write `tests/test_what_the_factory_writes_to_jira_reads_back_as_it_wrote_it.py` (C6, second
  instance). Bodies come **from the writers' source** (lesson 5): `activities._child_body(...)` with
  `carried=("", [])` and with a carried block, plus `"a\n\n\nb"`. Assert
  `JiraTracker._text(JiraTracker._adf(body)) == body.strip()`. Then, through `_Jira.get_ticket`
  on a description built by `_adf(_child_body(...))`, assert `out_of_scope == ["Everything covered
  by the sibling sub-tickets of CONT-1 (this is part 1/2; run in order)."]`, the same as
  `parse_ticket_body` gives on the raw markdown, which the test computes rather than hardcodes. On
  main it is red: blank lines are dropped, and the auto-split line is glued into the out-of-scope
  item. Record it.
- [x] 4. Code: replace the body of `JiraTracker._text` (`openfactory/adapters/tracker/jira.py:237-257`)
  with a block renderer. Keep the signature and the `@staticmethod`, because tests call
  `JiraTracker._text` directly. Shape:
  - `_inline(node) -> str`: concatenates the `text` of `text` nodes in document order, `hardBreak`
    → `"\n"`, other inline nodes walked for nested text (today's behaviour for them: no new
    rendering of mention/emoji/inlineCard, see Follow-ups).
  - `_blocks(node, out: list[str])`: `paragraph` → `out.append(_inline(p))`, so an empty paragraph
    is `""`. `heading` with an int `level` in 1..6 → `"#"*level + " " + _inline(h)`, otherwise as a
    paragraph. `bulletList`/`orderedList` → each `listItem`: its first child paragraph as
    `"- " + inline`, further paragraphs as plain lines, nested lists recursively as `- ` lines;
    after the outermost list, append `""` unless the next block already gives a blank. `codeBlock`
    → its text as lines, as today. Anything else (`doc`, `panel`, `table`, `tableRow`, `tableCell`,
    `expand`, `blockquote`, unknown) → recurse into `content`. A bare `text` node reached at block
    level (a malformed document) → its own line, so nothing that read before reads as empty now.
  - result: `"\n".join(out).strip()`, with no other normalisation. Do not collapse blank runs:
    task 3 asserts `"a\n\n\nb"` survives.
  Rewrite the docstring to say why. The parser reads markdown shapes (`## `, `- `), the editor
  stores those shapes as nodes, the measured `'Acceptance criteria\nthe \nx\n is created'` → `[]`
  of 2026-10-19, lists drawn `- ` flat to agree with `azure_devops._HtmlToMarkdown`, a list ends on
  a blank line because of #163's lazy continuation, and empty paragraphs are blank lines because
  `_adf` writes them. Keep the ADR-0022 sentence about panels and tables. Re-run tasks 1–3 green.
- [x] 5. Mutation plan `tools/mutations/751_a_jira_description_keeps_its_headings_and_bullets.py`.
  `TEST` = task 1's file, with a 5th element targeting tasks 2/3 or `test_tracker_is_vendor_neutral.py`
  where named. Each cut must turn a named test red:
  - M1 THE DEFECT ITSELF: the heading is drawn without its `#` marker → C1, C3
  - M2 the level is ignored (always `"## "`) → `test_a_heading_reads_as_its_level…`
  - M3 a list item is drawn without `"- "` → C2, C3
  - M4 inline runs are joined with `"\n"` instead of `""` → marks tests (C1, C2)
  - M5 no blank line after a list → `test_a_paragraph_after_a_list_is_not_read_into_its_last_criterion`
  - M6 `orderedList` is not treated as a list (falls through to generic recursion) → numbered test
  - M7 nested lists inside a `listItem` are skipped ("stop descending" taken literally) → nested test
  - M8 the empty paragraph is dropped → task 3's byte-identical test and the out-of-scope test
  - M9 `hardBreak` is ignored → hard-break test
  - M10 generic recursion into unknown containers is removed → `test_tracker_is_vendor_neutral.py::test_jira_reads_a_description_written_with_rich_formatting` and the table/expand test
  - M11 a heading with no or invalid level is drawn as `"#"*0`/`"## "` → no-level test
  Run `.venv/bin/python tools/mutate.py tools/mutations/751_….py` (never two `mutate.py` at once;
  it rewrites files in place). Every cut must be killed, and the summary goes into the PR body.
- [x] 6. Re-pin check. Run `git grep -l "tracker/jira.py" tools/mutations/`, which names 11 plans:
  162j, 166b, 203, 414a, 480, 543, a_malformed_fence_is_not_a_dead_tracker,
  a_withdrawn_card_lands_in_the_sites_own_status_on_jira, public_core_names_no_forge,
  public_identity_guard_has_no_names, the_doctrine_says_what_is_now_true. None of them anchors
  `_text`/`_adf` today (grepped), but the rewrite moves lines. Run
  `.venv/bin/python -m pytest -q tests/test_every_mutation_plan_can_run.py`, and re-pin any anchor
  it refuses in this PR, with a dated `# re-pinned` comment.
- [x] 7. Docs:
  - `docs/adr/0022-provider-seams.md` §4, bullet "**ADF is walked as a tree.**" (line ~105). Add,
    in place, `**Amended (2026-10-xx, #751):**`: walking for text was not enough. The parser reads
    markdown shapes, so the walk now keeps the shape of each block (heading → `#`×level, list item →
    `- `, a list ends on a blank line, an empty paragraph is a blank line), as the Azure
    converter already does. This follows `docs/adr/README.md`'s house style. Update the README row
    for 0022 only if the house style asks for amended sections there (rows 0024/0052 do; follow
    them: "Accepted; shipped (§4 amended 2026-10-xx by #751: …)").
  - `openfactory/adapters/tracker/jira.py`: the `_text` docstring (task 4) and the `_adf` docstring.
    The second says that the write path sends markdown as paragraphs and that `_text` reads it back
    byte-identical, naming task 3's test.
  - Grepped claims found nowhere else: `docs/reference/`, `docs/STATUS.md` and the onboarding/setup
    docs do not describe how Jira descriptions are read. `docs/STATUS.md:211` (the live Jira run)
    makes no claim about descriptions, so leave it. Re-grep at the end
    (`git grep -n -i "ADF\|walked as a tree\|plain text" -- docs openfactory`) and list in the PR
    any claim found and changed.
- [x] 8. Blast radius: run every module that reads a Jira body or `_text`/`_adf` (listed below) on
  the changed tree, and record pass counts. For any test that compared an exact `_text` string and
  now sees the kept blank lines, fix the **expectation** only when the new string is what the
  factory wrote (task 3's property), and name each such change in the PR. A change elsewhere is a
  finding: stop and report it.
- [x] 9. Against the real thing, the ADF schema: read the published ADF JSON schema
  (`@atlaskit/adf-schema`, record the version and URL in the PR) for `heading.attrs.level` (1..6),
  `listItem.content` (first child paragraph, then nested lists), `orderedList.attrs.order`,
  `hardBreak`, `codeBlock`, `taskList`. Confirm that the fixtures in task 1 are the shapes the
  schema allows. A shape that the renderer of task 4 mishandles and that is the same defect (block
  shape lost) goes into this PR. A different one (e.g. `taskItem` content is inline, not
  paragraphs, so its text is read but its `- [ ]` is not) becomes a follow-up.
- [x] 10. Against the real thing, a live Jira Cloud document. **Needs the human** (see Q3). On a
  Jira Cloud site (the maintainers' DAR project of 2026-08-05 if a token is available), create one
  issue in the **browser editor**: a Heading 2 "Acceptance criteria" with "criteria" in bold, a
  bullet list with a `code` run in one item and a nested item, a numbered list, a paragraph
  directly after the list, a table, and a hard break (Shift+Enter). Run `GET
  /rest/api/3/issue/<KEY>?fields=description`, redact ids and account ids, and commit the JSON as a
  recorded shape in task 1's test module (the way `JIRA_COMMENTS` is recorded in
  `test_the_tracker_has_a_read_side.py`), with the date and the site's editor. Then run
  `JiraTracker._text` on it and the gate on the parsed ticket. Second, `create_ticket` with a
  `_child_body` through the real API, `GET` it back, and confirm `_text` gives the body
  byte-identical (Jira does not merge or strip the empty paragraphs `_adf` sends). Record both
  commands and outputs in the PR body. If no site is reachable, ask the reporter for one redacted
  `description` JSON from their site, and say in the PR that the shape is from the schema, not
  measured. An empty `HOME` / no-credential run does not apply: this is a pure function over a JSON
  answer, not a CLI.
  **Credentials (human, 2026-10-19):** `.env` in the worktree root (git-ignored) holds `site`, `email`,
  `token` (basic auth `email:token`; prefix `https://` if `site` has no scheme). Verified
  `GET /rest/api/3/myself` → 200. The only visible project is **KAN** (team-managed). Never print or
  commit the values. The `create_ticket` round-trip goes in KAN. The browser-editor issue is created by
  the human; its key will be written here as `Browser issue: KAN-<n>`. If it is absent when this task
  is reached, do the API round-trip, and end the report with `NEEDS A DECISION:` asking for the key.
  Browser issue: KAN-4
- [x] 11. Environment variance. The change is a pure function, so locale, git version and the CI
  machine do not reach it. Check `pt_BR` once anyway: task 2's pt-BR param runs under
  `LANG=pt_BR.UTF-8` and under `LANG=C.UTF-8`. What differs between deployments is the **Jira
  site**: company-managed and team-managed projects use the same ADF editor, the site's language
  only changes the heading text (covered by the alias table and the pt-BR param), and Jira Data
  Center (API v2, wiki markup) is not a supported shape. Say each of these in the PR.
- [x] 12. Release-note fragment `changes/751.fix.md`, one line:
  "**A Jira ticket written in Jira's own editor keeps its headings and bullets.** A description with an Acceptance criteria heading and a bulleted or numbered list reached the factory as bare lines, so it found no sections and no criteria and refused the ticket as incomplete; headings and list items now arrive as the sections and criteria they are, and a description the factory wrote to Jira reads back with its blank lines, so a split card's last item no longer swallows the line under it."
  No number in the text.
- [ ] 13. `make lint` (ruff + shellcheck). Then `.venv/bin/python -m pytest -q -n auto` and
  `.venv/bin/python -m pytest -q -n auto -p no:randomly`. Record both counts against task 0's
  baseline: the new tests are the only difference in passed, and failed is 0 apart from the known
  docker preview flake, named if it appears.
- [ ] 14. Hand-off. Draft `ai/tasks/pr-body.md` in the maintainers' shape (`factory-developer.md`,
  "The pull request body"). It covers: the measured before (`'Acceptance criteria\nthe \nx\n is
  created'` → `[]`) and after; the red counts of tasks 1–3 on the pre-change tree, saying that the
  GitHub/Azure params and the table/expand guard pass on main on purpose; the mutation summary;
  the live/schema measurement of tasks 9–10; the second instance (C6) named as such; the write-path
  consequence (literal `## ` paragraphs on read-modify-write); the follow-ups; the credit to the
  reporter (per Q1). Commit it with the fragment. Stop, and name the HEAD for `/review`. No push,
  no PR.

## Blast radius
`JiraTracker._text` has three callers in `openfactory/adapters/tracker/jira.py`: `get_ticket`
(:287), `comments` (:402) and `_summary` (:649). Its body reaches:
- `parse.parse_ticket_body` / `criteria` / `section_names` / `criteria_heading` /
  `unread_criteria_lines` / `carried_sections` / `changed_sections` → `orchestrator/machine.py`
  `_spec_gate`/`_spec_refusal`/`spec_verdict` (:476-540); `product/triage.py:331`;
  `product/queue.py:253`; `product/module.py:4691` (refine: on Jira a card with a heading now has a
  `criteria_heading`, so refine says "would be ignored" instead of appending a second set, which is
  correct); `runtime/temporal/activities.py:1353` (`carried_sections` of a Jira parent: its
  sections are now found and carried); `actions/catalog.py:5005` (the edit door compares
  `current.raw`, now with `## ` and blank lines, against the form's body).
- Modules to run: `tests/test_tracker_is_vendor_neutral.py`,
  `tests/test_the_tracker_has_a_read_side.py`, `tests/test_the_tracker_reads_what_a_person_wrote.py`,
  `tests/test_every_row_writes_only_the_doors_comment.py`,
  `tests/test_a_withdrawn_card_is_not_delivered_on_jira.py`,
  `tests/test_a_withdrawn_card_lands_in_the_sites_own_status_on_jira.py`,
  `tests/test_the_board_row_says_which_stage_its_column_is.py`,
  `tests/test_the_queues_readers_read_columns_by_key.py`, `tests/test_a_jira_*.py`,
  `tests/test_an_order_of_jira_keys_is_written_from_the_conversation.py`,
  `tests/test_the_techlead_sees_a_jira_floor.py`, `tests/test_one_card_says_why_it_closed.py`,
  `tests/test_a_card_the_sizer_splits_keeps_what_its_author_wrote.py`,
  `tests/test_the_board_is_a_page_on_the_panel.py`, `tests/test_the_action_layer.py`,
  `tests/test_what_the_card_shows_inside_a_bullet_is_what_is_read.py`,
  `tests/test_a_scenario_is_one_criterion.py`, `tests/test_a_ticket_written_in_portuguese.py`,
  `tests/test_provider_seams.py`, `tests/test_the_product_role_moves_cards_by_key.py`,
  `tests/test_the_product_owner_writes_the_backlog_order.py`,
  `tests/test_every_mutation_plan_can_run.py`. Also grep `git grep -n "JiraTracker\|tracker.jira" --
  tests addons` again at task 8 for anything added since this plan.
- `_adf` is not changed. Its callers (`comment`, `create_ticket`, `update_body`) are affected only
  through what reads back.

## Follow-ups, not in this plan (open as issues; evidence below)
1. **Jira write path sends markdown as literal paragraphs.** `_adf` (`jira.py:260`) writes
   `## Objective` and `- item` as paragraph text, so a card the factory creates or rewrites shows
   raw markdown in Jira's UI. After this fix, a read-modify-write of an editor-written card also
   turns its headings into literal `## ` paragraphs. Writing real `heading`/`bulletList` nodes
   changes what a person sees, and it needs its own live measurement.
2. **Azure's HTML converter has the same two holes** (measured on `1be1835`):
   `description_text('<h2>Acceptance criteria</h2><ol><li><p>a</p></li><li>b<ul><li>c</li></ul></li></ol><p>after</p>')`
   → `'## Acceptance criteria\n-\na\n- b\n- c\nafter'`. A `<li><p>` gives an empty bullet, so the
   criterion `a` is lost, and a paragraph after a list is glued into the last item. Different
   adapter, so it is a separate issue.
3. **Inline nodes whose text is not a `text` node are dropped**: `mention` (`attrs.text`),
   `inlineCard` (`attrs.url`), `emoji`, `date`, `status`. A criterion "notify @Ana" reads as
   "notify ". This is the behaviour before and after this change.
4. **Only `## ` opens a section** (`parse._sections`). A Jira author who picks Heading 1 or
   Heading 3 for "Acceptance criteria" is still refused, as on GitHub, and `section_names` does not
   list such a heading in the refusal, so the refusal cannot point at it. This is a parser
   decision across all vendors.
5. **An action-item list (`taskList`) or a decision list in a Jira description is read as bare
   lines, not criteria** (found by task 9 against `@atlaskit/adf-schema` 57.7.18, measured
   2026-10-19 on the block renderer). In the schema a `taskItem` / `decisionItem` holds INLINE
   content directly (no paragraph), with `attrs.state` `TODO`/`DONE`; a `blockTaskItem` holds
   paragraphs; a `taskList` nests a `taskList`. The renderer has no case for them, so the generic
   walk reaches their `text` nodes at block level and draws each run as its own line, with no
   `- `, no `[ ]`/`[x]` and no blank after the list:
   `[heading AC, taskList[taskItem("the ", code "x", " is created"), taskItem(DONE "done one")], p "after"]`
   → `'## Acceptance criteria\nthe \nx\n is created\ndone one\nafter'`, `criteria == []`; a
   `decisionList` reads `'## Acceptance criteria\nwe decided'`, `criteria == []`. The text is read
   (ADR-0022 holds) and it read the same way on 1be1835, so nothing regresses. Left out of #751
   because the fix is a decision the issue does not make: draw an action item as `- [ ] x` /
   `- [x] x` (GitHub's shape; the parser then keeps `[ ] ` in the criterion's text,
   `parse._keyword:271` strips it only to find a Gherkin keyword) or as `- x`, and whether a DONE
   item is still a criterion. A `taskList` INSIDE a list item is already drawn as that item's `- `
   line by this PR.

## Notes
- Scope: `jira.py` `_text` only, plus tests, the plan, the ADR-0022 note, the docstrings and the
  fragment. Do not touch `parse.py`, the Azure converter or `_adf` (follow-ups 1, 2, 4).
- Lesson 4 / CONTRIBUTING "a guard reads the thing": every assertion is either the value `_text`
  returns for a given document, or what `parse`/`spec_verdict` makes of the ticket the vendor's
  `get_ticket` built. No grep of source text.
- Lesson 5: the bodies in task 3 come from `_child_body` and `_adf` themselves, and the Jira/ADO/GH
  doubles are the existing `_Jira`/`_ado_tracker`/`_Gh` from `test_the_tracker_has_a_read_side.py`,
  not new fakes.
- Lesson 2: a description that cannot be read must not look empty. Keep the generic recursion
  (M10 proves it).
- Do not run two `tools/mutate.py` at once. The suite's conftest strips `OPENFACTORY_*` env vars,
  so a live Jira measurement (task 10) runs outside pytest, and its token is never written to the
  repository or the PR.
- No git, docker or harness CLI is involved, so there is no oldest-version measurement.
- Card ids: `#751`/`#163` in comments are fine (provenance). No card id goes into user-facing text
  (`tests/test_no_card_id_reaches_a_stranger.py`). The fragment has none.

## Hand-off questions for the human
- **Q1 (credit).** The reporter, hermes-felipe, has a fork fix with a test and offered it as a PR.
  Options: (a) invite them to open it and review it against this plan (it would need C4, C6 and the
  inline join, which the issue's wording misses); (b) implement here and credit them in the PR
  body. If any of their code or test is used, add a `Co-authored-by:` trailer, which needs their
  commit email or GitHub noreply address. The plan assumes (b) until told otherwise.
- **Q2 (nested lists).** Flat `- ` (Azure's rule, as planned) or indented by depth (the parser reads
  it the same, and a human reading the brief sees the nesting)?
- **Q3 (live site).** Is a Jira Cloud token for a test site available for task 10, or do we ask the
  reporter for a redacted `description` JSON?
- **Q4 (scope of C6).** Keeping blank lines (empty paragraph → blank line) is the same defect on the
  factory's own writes, and it fixes the split child's out-of-scope swallowing the auto-split
  line. It also changes the exact text of every Jira comment and body read back (more blank lines).
  Keep it in this PR (planned), or split it out?

## Human answers (2026-10-19)
- **Q1:** (b) implement here and credit hermes-felipe in the PR body; add a `Co-authored-by:` only if their code or test is used.
- **Q2:** flat `- ` for nested items, as planned.
- **Q3:** the human will provide a Jira Cloud token and site for task 10. Delivery waits for the credentials (base URL, email, API token, and a project key to create the test issue in).
- **Q4:** keep C6 in this PR, as planned.
