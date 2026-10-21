"""An audit row is written once and never rewritten in the sqlite store (#694, PR #1039 review,
hermesfelipe's follow-up, 2026-10-21), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/694_an_audit_row_is_written_once.py

On 98b1b59f a second `record()` under an audit row's key replaced it (True, the row now saying
mallory), and a plain `UPDATE` rewrote it.
"""

TEST = "tests/test_an_audit_row_is_written_once_and_never_rewritten.py"

_SQLITE = "openfactory/observability/sqlite_metrics.py"
_T = TEST + "::"

MUTATIONS = [
    ("an audit row is written with INSERT OR REPLACE", _SQLITE,
     'WRITTEN_ONCE = frozenset({"audit"})\n',
     "WRITTEN_ONCE = frozenset()\n",
     _T + "test_a_second_write_under_an_audit_rows_key_is_refused_and_the_first_stands"),
    ("an audit row may be updated", _SQLITE,
     "    WHEN OLD.kind = 'audit' BEGIN SELECT RAISE(ABORT, 'an audit row is never rewritten'); END;\n",
     "    WHEN OLD.kind = 'never' BEGIN SELECT RAISE(ABORT, 'an audit row is never rewritten'); END;\n",
     _T + "test_an_audit_row_cannot_be_updated_in_the_file"),
    ("every kind is written once", _SQLITE,
     '            verb = "INSERT" if rec.kind in WRITTEN_ONCE else "INSERT OR REPLACE"\n',
     '            verb = "INSERT"\n',
     _T + "test_any_other_kind_still_replaces_its_row_on_a_retried_write"),
]
