# Baseline — main at 1be1835 (task 0, #751)

Measured 2026-10-19 in a detached worktree of `origin/main` at `1be1835`
(`../openfactory-core-751-baseline`, own venv, Python 3.12.3), removed afterwards.
CI on `1be1835`: `ci` success, `release` success (`gh run list --branch main`).

| run | result | duration |
|---|---|---|
| `.venv/bin/python -m pytest -q -n auto` | **4 failed, 18485 passed, 207 skipped**, 56 warnings | 836.49s (13:56) |
| `.venv/bin/python -m pytest -q -n auto -p no:randomly` | **5 failed, 18484 passed, 207 skipped**, 56 warnings | 1371.31s (22:51) |

Both runs collect 18696 tests (passed + failed + skipped). Task 13 compares against 18696 + the
tests this branch adds.

## Failures (all on main, none touches a tracker)

Random order:
- `tests/test_a_preview_runs_on_a_real_daemon.py::test_the_s1_product_comes_up_through_prove_with_nothing_of_the_factory_in_it`
- `tests/test_a_preview_starts_on_a_real_daemon.py::test_an_offered_card_is_started_watched_and_ended_on_a_real_daemon`
- `tests/test_a_preview_opens_on_one_machine.py::test_s1_opens_at_its_preview_host_through_a_host_process_panel`
- `tests/test_the_board_lives_in_one_file.py::test_two_openers_of_a_BRAND_NEW_file_both_get_in`
  (`2 of 60 openers were refused the brand-new file: OperationalError: database is locked`)

Ordered (`-p no:randomly`): the same four, plus
- `tests/test_the_board_lives_in_one_file.py::test_two_writers_never_take_the_same_number`
  (`a writer lost its card: OperationalError('database is locked')`); the BRAND_NEW test reported
  7 of 60 this time.

Rerun of the five node ids alone, serially, `-p no:randomly`, same tree: **4 failed, 1 passed**
in 785.50s (`test_two_writers_never_take_the_same_number` passed; the three previews and the
BRAND_NEW test still failed).

## Why (a note, not a fix)

- **The three docker previews: the known docker preview flake.** Each failure is `docker compose
  up` exit 1, `dependency failed to start: container openfactory-pv-acme-<n>-db-1 is unhealthy`.
  The machine was loaded by other worktrees' suites while these ran (load average 38–62 on 12
  cores; pytest processes from 747, 749, 752 and three review worktrees, all on one docker
  daemon). A bare `postgres:16` container started by hand at the same time had not finished
  `initdb` after 15 s (`pg_isready` → `no response`, exit 2). The s1 fixture's db healthcheck is
  `interval: 2s` with the default retries, so it is declared unhealthy before initdb ends. The
  compose project names (`openfactory-pv-acme-0`, `-12`) are the same in every worktree, so
  concurrent suites on one daemon can also meet each other's containers: one such
  `openfactory-pv-acme-12-db-1 (unhealthy)` belonging to no run of this baseline was seen
  during the rerun.
- **The two `board.db` locking tests**: timing under the same load (the tests are
  probabilistic races by design; their docstring says so). One passed alone, the other did not
  at load average ~20–30.

Neither area is reached by `JiraTracker._text`. Task 13 names any of these five that recur and
expects nothing else to fail.

# Branch — `fix/751-jira-headings-bullets-lost` at 92585ff (task 13)

Measured 2026-10-19 in this worktree with its own venv, Python 3.12.3. Other worktrees' suites
(749, 752, review-818) ran at the same time; load average 25–40 on 12 cores.

`PATH=$PWD/.venv/bin:$PATH make lint`: `ruff check openfactory/ tests/` → `All checks passed!`;
shellcheck ran through docker (`koalaman/shellcheck:stable`, no local binary); exit 0.

| run | result | duration | main (1be1835) |
|---|---|---|---|
| `.venv/bin/python -m pytest -q -n auto` | **4 failed, 18519 passed, 207 skipped**, 56 warnings | 1445.40s (24:05) | 4 failed, 18485 passed, 207 skipped |
| `.venv/bin/python -m pytest -q -n auto -p no:randomly` | **4 failed, 18519 passed, 207 skipped**, 56 warnings | 591.37s (9:51) | 5 failed, 18484 passed, 207 skipped |

(Both runs also passed `-p no:cacheprovider`. The ordered run also passed `-rs`, which only
changes what the summary prints.)

Both runs collect **18730** = 18696 + **34**. That is exactly the three modules this branch adds;
none of them exists on 1be1835, and no existing test module changed (`git diff --name-status
1be1835 -- tests/` lists only these three, all `A`):

| module (new) | tests |
|---|---|
| `tests/test_a_jira_description_keeps_its_headings_and_bullets.py` | 25 |
| `tests/test_a_card_written_in_jiras_editor_passes_the_gate_it_passes_on_github.py` | 5 |
| `tests/test_what_the_factory_writes_to_jira_reads_back_as_it_wrote_it.py` | 4 |

Those three modules alone: 34 passed, 0 skipped. Skipped is 207 in both runs, the same as on main.

## Failures

Random order: the same four tests as main, failing the same way.
- The three docker previews (`test_a_preview_runs_on_a_real_daemon`,
  `test_a_preview_starts_on_a_real_daemon`, `test_a_preview_opens_on_one_machine`): `docker
  compose up` exit 1, `container openfactory-pv-acme-{0,12}-db-1 is unhealthy`. This is the known
  docker preview flake from the baseline.
- `test_the_board_lives_in_one_file.py::test_two_openers_of_a_BRAND_NEW_file_both_get_in`: `4 of
  60 openers were refused the brand-new file: OperationalError: database is locked`. This is the
  baseline's board.db race under load.

Ordered: the three docker previews again (same `db-1 is unhealthy`). Neither board.db test failed
this time. The fourth failure is a test that did not fail on main:
- `tests/test_a_stream_ends_when_its_credential_does.py::test_a_person_DROPPED_from_the_token_map_loses_their_stream_and_nobody_else`:
  `TimeoutError` out of `asyncio.wait_for(queue.get(), timeout=5)` (test lines 117/123/451) on
  xdist worker gw10.
  Run alone afterwards with `-p no:randomly` it passed **5 of 5** (1.4–6.0 s each), and the whole
  module passed 36/36. The load average had dropped to about 11 by then. It does not still fail,
  so the task's rule did not call for a run on 1be1835. It cannot reach this diff: the only
  package file the branch changes is `openfactory/adapters/tracker/jira.py`, and this test
  configures the `github` tracker. It is a 5-second wait timing out under load, not a regression.

A void ordered run, so nobody reads it as a measurement: my first ordered launch was started
with `&` from a shell I took for dead. It was still running when the second launch began, so two
full ordered suites ran together in one tree and wrote one log. Its tail (`5 failed, 18517
passed, 208 skipped`) is from that overlap and is not recorded above. The 4/18519/207 row is
the rerun, alone.

Net against main: passed rises by exactly the 34 new tests (18485 → 18519 random; 18484 → 18519
ordered, where the board.db writer race that failed on main passed). Nothing fails that is not
either a baseline failure or a load timeout that passes when run alone.
