Closes #749.

## What changed
- **On Jira, a 404 asks `GET /rest/api/3/myself` once, and a 401 there is refused as an email and a token of different accounts, not read as a missing card.** `JiraTracker._call` (`openfactory/adapters/tracker/jira.py:281`) calls `_who_is_asking()` (`:288`) on a 404 and only on a 404. The probe asks `api/3` whatever family the call used (`myself` exists nowhere else; the board's rank is `agile/1.0`), with the same `Authorization` header, straight through `urlopen` with the same 45 s timeout, never through `_call` (so a `myself` that 404s cannot recurse). A 401 raises `JiraRefused(code=401)` from the 404. A 2xx, any other status, or an `OSError` (DNS, timeout, reset; logged at info) keeps the original 404 byte for byte: the raise line is unchanged, so `203`'s anchor still matches once. The refusal stays a `RuntimeError`, so every catch-all caller (the card's door, the preflight, `_project_exists`, `comments`, `person`, the board's `_search`) keeps working. Only the sentence and the code change.
- **The sentence puts the cause first and never carries the token** (`_not_one_account`, `jira.py:114`). The park line (`activities.py:979`) and the card's door (`ports.py:137`) keep 120 characters, and "different accounts" stays inside them for the longest path this adapter 404s on with a 40-character email. The sentence names a revoked token too, because nothing tells the two apart.
- **With no token at all, the refusal says no API token reached the tracker and names `tracker.options.token_env`.** This is the second instance of the same defect, found in the code: `_headers` sends `email:` with an empty password, and Jira answers it the same anonymous way (measured, below). Calling that "different accounts" would be false. `registry.py`'s comment ("the adapter fails saying which variable to set") was not true before and now points at this sentence.
- **A job parked on either refusal is classified as a credential** (`openfactory/techlead/classify.py:150`). This widens the plan's scope (it changes what a caller does with the refusal), by the human's decision on 2026-10-19. On 82500f9 both sentences, cut at 120 behind `ticket: `, classified as `unknown`. Now `remedy_for` retries twice, 900 s apart, then escalates (measured), as any credential does.
- **The docs say what is true:** the `jira.py` module docstring (AUTH), `JiraRefused` (code 401 over a 404 cause), the `_call` docstring (the rule, the request counts, up to 45 s on a slow site), the `observes` comment, `_project_exists`, `registry.py`, and `docs/reference/configuration.md` (`email` and the token must be one account's, and what a mismatch, an empty token or a revoked one read as). Checked and left unchanged: `docs/adr/0022-provider-seams.md` §4 (history), `docs/STATUS.md:97-99,211-214`, `docs/operations.md:186-188` (no claim about a refused pair). The only other hit of `git grep -i "404\|not found\|anonymous"` near this code is ADR-0022:164 (a `#` fragment in a REST URL, unrelated).
- Mutation plans: `749_a_mismatched_jira_account_is_named_not_read_as_missing`, 13/13 red. These plans anchor `jira.py` or `classify.py` and still run red with no re-pin: `203_a_withdrawn_card_is_not_delivered_on_jira` 29/29, `a_withdrawn_card_lands_in_the_sites_own_status_on_jira` 18/18, `159_the_engine_death_is_not_a_mystery` 9/9, `623_a_branch_held_elsewhere_holds_the_job` 33/33, `a_machine_made_hold_says_its_own_cause` 16/16, `one_definition_of_the_park_classes_and_the_merged_states` 5/5, `what_git_refuses_the_person_reads` 23/23. `tests/test_every_mutation_plan_can_run.py`: 6 passed.
- `changes/749.fix.md`.

## Tests first
`tests/test_on_jira_an_email_and_a_token_of_different_accounts_are_named_not_read_as_missing.py`: 12 functions, 22 items. It drives the real `JiraTracker` through its real `_call` against a fake site at `urllib.request.urlopen`, which records every request with its `Authorization` header and refuses any route it does not have. The issue's 404 body is pt-BR, so the rule is shown to read the status code, never the body.

On `main` (82500f9, the test module alone): **21 failed, 1 passed.**

| test | what fails on 82500f9 |
|---|---|
| `test_a_404_whose_myself_answers_401_is_refused_with_code_401_naming_the_email_and_the_remedy` | `.code == 401`: got 404, `jira GET issue/DAR-7 failed: 404 {"errorMessages": ["O item não existe…"]}` |
| `test_the_refusal_never_carries_the_token` | `.code == 401`: got 404 |
| `test_myself_is_asked_with_the_same_credential_as_the_call_that_404d` | requests `['/rest/api/3/issue/DAR-7'] == [issue, myself]` |
| `test_a_404_on_the_agile_api_asks_myself_of_the_core_api` | `asked(myself)`: `0 == 1` |
| `test_a_404_whose_myself_answers_200_is_the_original_404_unchanged` | `asked(myself)`: `0 == 1` |
| `test_a_myself_that_cannot_answer_keeps_the_original_404` [dns, timeout, reset, 500, 502, 503, 403, 404] | `asked(myself)`: `0 == 1` (×8) |
| `test_myself_is_asked_once_per_404_and_never_for_any_other_answer` | "one 404 asks once" |
| `test_a_card_read_through_the_door_says_the_account_is_mismatched_not_that_it_is_missing` | `cannot_tell` is "DAR-7 could not be read (jira GET issue/DAR-7 failed: 404 …não existe…)" |
| `test_the_cause_comes_first_in_the_sentence_so_a_park_line_keeps_it` | `str(exc)[:120]` is "jira GET issue/DAR-7/comment?startAt=0&maxResults=100 failed: 404 …" |
| `test_a_board_read_with_a_mismatched_pair_is_unreadable_and_the_log_names_the_pair` | the warning carries only "jira GET project/DAR failed: 404 …No project could be found…" |
| `test_a_job_parked_on_the_refusal_is_classified_as_a_credential` [another-accounts-token, no-token] | `classify("ticket: jira GET issue/DAR-7 failed: 404 …").cause` is `unknown` |
| `test_with_no_token_the_refusal_says_no_token_reached_the_tracker` [none, empty] | `.code == 401`: got 404 |

Two tests are red on a narrower base:
- The classifier test, run with the fix in `jira.py` and 82500f9's `classify.py`: 2 failed (`ticket: jira: the email alice@acme.ai and the API token belong to different accounts…` → `unknown`).
- `test_a_card_that_reads_costs_no_extra_request` **passes on main**, because main has no probe. It guards the new path against a probe on every answer. The plan's "the probe runs on a call that succeeded" cut turns it red; the `exc.code >= 400` cut cannot, because a 200 never reaches the `except HTTPError` branch.

The 749 plan, each cut and what it turns red:

| cut | red |
|---|---|
| THE DEFECT: the 404 never asks (`if False:`) | 19 (every item that existed then) |
| every non-200 answer of the probe reads as a mismatch | 6: `myself` 403/404/500/502/503, and the C3 test |
| a probe that cannot be made reads as a mismatch (`OSError` → `True`) | 3: dns, timeout, reset |
| the refusal keeps `code=404` | 5: the C1 401 test, token, agile, no-token ×2 |
| the probe runs on every failure (`>= 400`) | 1: the C3 test |
| the probe follows the call's API family | 1: the agile test |
| the probe goes through `_call` (recursion) | 12 |
| the probe asks without the credential | 1: the same-credential test |
| the token in the sentence | 1: the token test |
| the remedy before the cause | 3: door, park line, board log |
| no empty-token sentence | 2: no-token ×2 |
| the probe runs on a call that succeeded | 2: the cost test, the C3 test |
| the classifier drops the two phrases | 2: the classifier test ×2 |

## Reproduced by hand
Against a real Jira Cloud site, 2026-10-19, with an empty `HOME` and the credential only on the command line (`env -i PATH=/usr/bin:/bin HOME="$(mktemp -d)" curl -sS -D - -o - -u "$EMAIL:$TOKEN" "$SITE/rest/api/3/<route>"`). Redacted: the site as `acme-team.atlassian.net`, the email as `alice@acme.ai`, the issue as `DAR-7`, and no token or account id. Account A's email is used throughout; `tokenB` belongs to a different account B.

| case | route | status | `X-AAccountId` | `X-Seraph-LoginReason` | body |
|---|---|---|---|---|---|
| (a) A's email + A's token | `issue/DAR-7`, `project/DAR`, `myself` | 200 | present | absent | the issue / project / account A |
| (b) A's email + B's token | `issue/DAR-7` | **404** | absent | `AUTHENTICATED_FAILED` | `Issue does not exist or you do not have permission to see it.` |
| (b) | `project/DAR` | **404** | absent | `AUTHENTICATED_FAILED` | `No project could be found with key 'DAR'.` |
| (b) | `myself` | **401** | absent | `AUTHENTICATED_FAILED` | HTML; `WWW-Authenticate: OAuth realm=…` |
| (b) | bounded `search/jql` (`project=DAR …`) | **200** | absent | `AUTHENTICATED_FAILED` | `{"issues":[],"isLast":true}` |
| (c) revoked token | — | not measured: no revoked token was available | | | |
| (d) A's email + empty token | `issue/DAR-7`, `project/DAR` | **404** | absent | `AUTHENTICATED_FAILED` | as (b) |
| (d) | `myself` | **401** | absent | `AUTHENTICATED_FAILED` | as (b) |
| (e) A's pair, a key that does not exist | `issue/DAR-999999` | 404 | **present** | absent | the same text as (b) |
| (e) | `myself` | 200 | present | absent | account A |

The issue reproduces: (b) and (d) get a 404 on an issue and a project that exist, with the body a really missing issue gets in (e). `myself` tells them apart: 401 under (b) and (d), 200 under (e). An empty token answers exactly as another account's token on every route measured. Through the fake site, the tracker turns (b) into the "different accounts" refusal, (d) into the "no API token" one, and (e) into the original 404.

## Checks
- `make lint`: clean.
- The test module: 22 passed. On 85170df, before the classifier test, the Jira and blast-radius modules (the read side, both withdrawn-card modules, why a card closed, the Jira queue, the Jira order of keys, the Jira key as a card ref, the Jira floor, what a person wrote, the Jira project as a board, the Jira card name, the born-in-queue writers, the board row stage, the queue readers, the product role's moves, the human gate, and the guards `no_silent_failures`, `tracker_is_vendor_neutral`, `provider_seams`, `public_core_names_no_forge`, `the_product_carries_no_owners_name`, `every_mutation_plan_can_run`): 605 passed, 1 skipped (`tests/vendor_addons.py:73`, the public tree has no `addons/`). The modules that read the classifier: 1598 passed, 48 skipped. The modules that read the docs: 622 passed, 17 skipped; `test_the_public_cut_is_written_down`: 41 passed, 4 skipped.
- The whole suite with `-n auto -p no:randomly`: `3 failed, 18231 passed, 207 skipped` (load 45 → 13) and, rerun, `5 failed, 18229 passed, 207 skipped` (load 47 → 39). With `-n auto`: `3 failed, 18231 passed, 207 skipped` (load 2 → 49). (`main` 82500f9 on this machine: `18212 passed, 207 skipped` fixed order; random order 3 and 4 failed from load, as below.) The difference is the 22 new items. Every failure is also red on `main` on this machine, from load: suites of four other worktrees ran at the same time.
  - The three docker preview tests (`test_a_preview_opens_on_one_machine`, `test_a_preview_runs_on_a_real_daemon`, `test_a_preview_starts_on_a_real_daemon`) failed in every full run with `container openfactory-pv-acme-*-db-1 is unhealthy`, the cause main's random-order runs gave. Run alone on HEAD: 3 passed.
  - `test_the_requesters_loop_walks_through_the_door::test_a_card_walks_the_requesters_whole_loop_through_its_door` failed on HEAD with `assert ('pr_opened', …) == ('resumed', …)`: the workflow ran a row ahead of the assertion that reads the last row. Run alone on 82500f9, 13 times: 2 failed, one with this same assertion and one with `never saw: the merge gate …`. Run alone on HEAD: 2 failed of 8.
  - `test_delivered_means_the_last_declared_stage::test_a_deploy_green_at_the_watchs_first_look_leaves_the_card_done` failed once in the fixed-order rerun with temporalio's `RuntimeError: No completion event found` (the history poll on the ephemeral server). Alone it passed 5/5 on HEAD and 4/4 on 82500f9. It drives the local tracker and a green deploy, so nothing this change touches is on its path.
- Locale: the test module gives 22 passed under `LANG=C.UTF-8` and under `pt_BR.UTF-8`.
- No network: `unshare -rn` is refused on this machine (`/proc/self/uid_map: Operation not permitted`). Instead, a pytest plugin made `socket.connect`, `getaddrinfo` and `create_connection` raise and counted the attempts: the test module passed with **0 socket attempts**. Under the same plugin, an unpatched `get_ticket` fails on `create_connection(('acme-team.atlassian.net', 443), 45)`, which shows the plugin works.
- A person's box: with `HTTPS_PROXY=http://proxy.corp.example:3128`, both the call and the probe went to `('proxy.corp.example', 3128)` with a 45 s timeout. The probe goes to the same host through the same `urlopen`, so an air-gapped or allowlisted network sees no new egress. A slow site can add up to 45 s to a 404 that was already going to fail (said in the `_call` docstring).
- Cost, requests per call through the real `_call` (82500f9 → now):

  | call | 82500f9 | now |
  |---|---|---|
  | `get_ticket`, the card reads | 1 | 1 |
  | `get_ticket`, 404 (`myself` 200, 401 or unreachable) | 1 | 2 |
  | `get_ticket`, 403 | 1 | 1 |
  | `list_tickets`, issues on the board | 1 | 1 |
  | `list_tickets`, empty board, project 200 | 2 | 2 |
  | `list_tickets`, empty board, project 404 (whatever `myself` says) | 2 | 3 |
- `scripts/release_notes.py check`, fed `git diff --name-status --no-renames 82500f9 HEAD`: "This pull request carries its release note: changes/749.fix.md."

## Notes for the reviewer
- **A zero-cost alternative exists on the measured site and is not taken here.** Every 404 under (b) and (d) lacks `X-AAccountId` and carries `X-Seraph-LoginReason: AUTHENTICATED_FAILED`. The 404 under (e), from a signed-in caller on a missing key, carries `X-AAccountId` and no `X-Seraph-LoginReason`. So the 404 itself says whether the request ran anonymous, with no second call. That holds on one site, on one date, for two credential shapes, and Atlassian does not document it. The shape the issue asked for (probe `myself` on a 404) stays.
- **The reporter's offer.** The issue's author said a fix with a test exists in their fork, and offered to open it as a PR if the shape was acceptable. No PR, branch or assignee existed when this was planned. Whether to credit them, or to reply on the issue before this goes up, is the maintainers' call. Nothing was posted on the issue from this branch.

## Risks, not addressed here
- **Scope widened by decision:** the classifier change above is a caller's behaviour, which the plan had left out. The human chose it on 2026-10-19.
- **`openfactory doctor` has no Jira credential check.** `doctor.py`'s `_board` guesses "almost always the tracker credential", and nothing asks `myself` before the first job. A `tracker_credential` finding is its own change.
- **The onboarding to-do line says nothing about pairing** (`openfactory/onboarding/deployment.py:941-947`): it says to fill `JIRA_API_TOKEN`, but not that the token must be created by the email's account.
- **A Jira refusal at the command line is still a traceback**, as on main. `cli_refusals.looks_like_a_provider` is False for the old 404 sentence and for both new ones (measured), so `speaks_plainly` does not translate any of them. If it were widened, `name_the_cause` would read "401" first and say `gh auth login`, which is wrong for Jira. This was unchanged before this PR.
- Not in scope, as the plan set: caching the probe's answer across calls (a pair fixed mid-run would stay refused), probing on a 403, and the revoked-token measurement (case c).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
