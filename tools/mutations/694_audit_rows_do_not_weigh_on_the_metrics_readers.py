"""The audit rows in the metrics store do not weigh on the readers that scan it, nor change what
they read (#694, PR #1039 review N2, 2026-10-21), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/694_audit_rows_do_not_weigh_on_the_metrics_readers.py

The claims: every whole-store read (`metrics_view.scan_records`/`scan_all_or_raise`, through
`_scanned`, and `query._store_rows`) asks a store that can leave a kind out for every kind but
`metrics.SCANNED_APART`, which the sqlite store answers without parsing an audit row; a store that
cannot is scanned and the audit rows dropped. On c310ba28 the dashboard parsed 53 rows for 3, and
with 100,000 audit rows beside 50 cost rows took 9.99 s (the review's measure).
"""

TEST = "tests/test_audit_rows_do_not_weigh_on_the_metrics_readers.py"

_MV = "openfactory/api/metrics_view.py"
_T = TEST + "::"

MUTATIONS = [
    ("a store that can leave the audit rows out is scanned whole", _MV,
     "        return sink.scan_except(list(SCANNED_APART))\n",
     "        return sink.scan()\n",
     _T + "test_the_cost_dashboard_parses_no_audit_row"),
    ("a store that can leave the audit rows out is scanned whole (the dashboard's selector)", _MV,
     "        return sink.scan_except(list(SCANNED_APART))\n",
     "        return sink.scan()\n",
     "tests/test_the_audit_record_is_kept_in_the_metrics_store.py::"
     "test_audit_rows_in_the_store_do_not_change_the_cost_dashboard"),
    ("a store that can only scan hands its audit rows on", _MV,
     '    return [r for r in sink.scan() if r.get("kind") not in SCANNED_APART]\n',
     "    return sink.scan()\n",
     _T + "test_a_store_that_cannot_leave_a_kind_out_is_scanned_and_its_audit_rows_dropped"),
    ("the sqlite store leaves no kind out", "openfactory/observability/sqlite_metrics.py",
     '            f"SELECT data FROM metrics WHERE kind NOT IN ({marks})"\n',
     '            f"SELECT data FROM metrics WHERE kind IN ({marks}) OR 1"\n',
     _T + "test_a_full_scan_of_the_store_hands_its_readers_no_audit_row"),
    ("the outcome aggregates scan the store whole", "openfactory/observability/query.py",
     "        rows = _scanned(sink)   # no audit row: they are read by their kind, apart (#694)\n",
     "        rows = sink.scan()\n",
     _T + "test_the_outcome_aggregates_read_no_audit_row"),
    ("no kind is read apart", "openfactory/observability/metrics.py",
     'SCANNED_APART = ("audit",)\n',
     "SCANNED_APART = ()\n",
     _T + "test_a_full_scan_of_the_store_hands_its_readers_no_audit_row"),
]
