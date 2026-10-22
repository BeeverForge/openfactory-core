"""Rows past their period are deleted, not only hidden, as the worker and the panel start (#694,
#1027, PR #1039 review, 2026-10-21), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/694_rows_past_their_period_are_deleted.py

On 362e77aa nothing called `SqliteMetricsSink.purge_expired`: an expired row's bytes stayed. The
last two rows (branch review of 58cbd307, 2026-10-22) cut the purge of the audit fallback file, a
deployment with no metrics store: both survived until a test had two distinct stores.
"""

TEST = "tests/test_rows_past_their_period_are_deleted_at_start.py"

_RETENTION = "openfactory/observability/retention.py"
_T = TEST + "::"

MUTATIONS = [
    ("openfactory serve does not purge", "openfactory/cli.py",
     "        retention.purge_expired()\n",
     "        pass\n",
     _T + "test_an_expired_row_is_deleted_and_one_in_its_period_is_kept"),
    ("the worker does not purge", "openfactory/runtime/temporal/worker.py",
     "        await asyncio.to_thread(retention.purge_expired)\n",
     "        pass\n",
     _T + "test_the_worker_purges_as_it_starts"),
    ("the purge is unbounded", _RETENTION,
     "        gone = purge(limit=PURGE_BOUND)\n",
     "        gone = purge()\n",
     _T + "test_the_purge_is_bounded_and_says_when_the_bound_was_hit"),
    ("a bound hit is not said", _RETENTION,
     '            line += f"; more remain, and the next start deletes up to {PURGE_BOUND} more"\n',
     "            pass\n",
     _T + "test_the_purge_is_bounded_and_says_when_the_bound_was_hit"),
    ("the sqlite purge ignores its bound", "openfactory/observability/sqlite_metrics.py",
     "                if limit is None:\n",
     "                if True:\n",
     _T + "test_the_purge_is_bounded_and_says_when_the_bound_was_hit"),
    ("the purge deletes the rows inside their period too", "openfactory/observability/sqlite_metrics.py",
     '                        " WHERE expires_at IS NOT NULL AND expires_at <= ? LIMIT ?)",\n',
     '                        " WHERE expires_at IS NOT NULL OR expires_at <= ? LIMIT ?)",\n',
     _T + "test_an_expired_row_is_deleted_and_one_in_its_period_is_kept"),
    ("the audit's fallback file is not among the stores purged", _RETENTION,
     "    for build in (deployment_metrics_sink, audit.sink):\n",
     "    for build in (deployment_metrics_sink,):\n",
     _T + "test_a_deployment_with_no_store_has_its_fallback_audit_file_purged"),
    ("the de-duplication keeps the first store only", _RETENTION,
     "        if all((getattr(s, \"path\", None) or getattr(s, \"table\", None) or id(s)) != where\n"
     "               for s in found):\n",
     "        if not found:\n",
     _T + "test_a_deployment_with_no_store_has_its_fallback_audit_file_purged"),
]
