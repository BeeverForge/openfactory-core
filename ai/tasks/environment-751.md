# #751, task 11: environment variance (2026-10-19)

The change is a pure function over the JSON Jira returns (`JiraTracker._text` and the ADF block
renderer, then `parse.parse_ticket_body`). It runs no subprocess, reads no file and calls no
locale-aware API, so git version, the CI machine and the process locale do not reach it. The locale
was checked once anyway.

## Process locale

Task 2's module, `tests/test_a_card_written_in_jiras_editor_passes_the_gate_it_passes_on_github.py`,
including its `jira_pt_br` param (a card whose headings are in Portuguese), on this machine
(`locale -a` lists `C.utf8`, `pt_BR.utf8`; `locale.setlocale(LC_ALL, '')` returned the requested
locale in each run):

| Environment | Result |
|---|---|
| `LANG=pt_BR.UTF-8 LC_ALL=pt_BR.UTF-8` | `5 passed` (github, azure_devops, jira, jira_pt_br, board read) |
| `LANG=C.UTF-8 LC_ALL=C.UTF-8` | `5 passed` (the same five) |

## The Jira site: what differs between deployments

- **Company-managed and team-managed projects.** Both store a description in the same Atlassian
  Document Format through the same editor and return it from the same `GET /rest/api/3/issue`
  endpoint, so the renderer has no per-project-type branch. **Measured only on team-managed:** task
  10's live run (KAN-4 written in the browser editor, and the KAN-5 create/read-back round-trip)
  was on project KAN, which is team-managed, the only project the test site's credentials could see.
  A company-managed project was not tested live. The claim that it reads the same rests on the
  shared ADF schema (task 9 validated the live document against ADF 57.7.18), not on a measurement.
- **The site's language.** It changes the text a person types as a heading, not the document's
  shape: a heading is a `heading` node whatever its words. The words are matched by the parser's
  existing alias table, the same one GitHub and Azure DevOps cards use. The `jira_pt_br` param
  covers a Portuguese heading. The live KAN-4 headings were in English
  (`Acceptance criteria`), so a non-English heading is covered by the fixture, not by a live run.
- **Jira Data Center / Server is out of scope.** It serves REST API v2, where a description is wiki
  markup (`h2. Acceptance criteria`, `* item`), not ADF. The tracker's `_call` builds every issue URL under `/rest/api/3` (`openfactory/adapters/tracker/jira.py:218-225`; `agile/1.0` only for ranking), so
  this is not a shape the factory reads, before or after this change. This fix does not add support
  for it.
