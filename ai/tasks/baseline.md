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
