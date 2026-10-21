"""`openfactory audit` asks the store for audit rows alone, newest first, and stops reading once its
answer is whole (#694, PR #1039 review, 2026-10-21), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/694_openfactory_audit_reads_a_bounded_store.py

The claims, one group of rows each:
  1. a store that streams one kind (`KindStreamingSink`, the sqlite sink) is asked for `audit`
     rows alone, newest first, and is never scanned whole;
  2. the read stops at `--limit` and one more, and at the first record older than `--since`, and
     what it keeps is the most recent `--limit`;
  3. a store without the capability is still listed, through its `scan`.

Every row names the one test that holds its claim. On c310ba28, `--limit 1` over 4 records and 200
rows of another kind parsed 204 rows; on a 336 MB store of 200,000 such rows and 2,000 records,
`--limit 20` peaked at 1,011 MB, and 47 MB after (`/usr/bin/time`, 2026-10-21).
"""

TEST = "tests/test_openfactory_audit_lists_who_did_what.py"

_CLI = "openfactory/cli.py"
_SQLITE = "openfactory/observability/sqlite_metrics.py"
_T = TEST + "::"

MUTATIONS = [
    # 1. asked by kind, never scanned
    ("the command scans the store even when it can be asked by kind", _CLI,
     "        if isinstance(store, KindStreamingSink):\n",
     "        if False:\n",
     _T + "test_the_store_is_asked_for_audit_rows_and_never_scanned_whole"),
    ("the store hands back every kind, not the one asked for", _SQLITE,
     '                    "SELECT data FROM metrics WHERE kind = ?"\n',
     '                    "SELECT data FROM metrics WHERE ? IS NOT NULL"\n',
     _T + "test_rows_of_other_kinds_in_the_store_are_not_read_as_audit_records"),
    ("the store hands its rows back oldest first", _SQLITE,
     '                    " AND (expires_at IS NULL OR expires_at > ?) ORDER BY ts DESC, sk DESC",\n',
     '                    " AND (expires_at IS NULL OR expires_at > ?) ORDER BY ts, sk",\n',
     _T + "test_the_store_is_read_to_the_limit_and_one_more_however_many_rows_it_holds"),
    ("a store that fails while it streams answers as an empty one", _SQLITE,
     "        except GeneratorExit:\n            raise\n        except Exception as exc:\n"
     "            raise self._unreadable(exc) from exc\n",
     "        except GeneratorExit:\n            raise\n        except Exception as exc:\n"
     "            return\n",
     _T + "test_a_store_that_cannot_be_read_exits_2_naming_it"),
    # 2. the read stops when the answer is whole
    ("the read does not stop at the limit", _CLI,
     "                if len(found) > limit:\n                    break\n",
     "                if False:\n                    break\n",
     _T + "test_the_store_is_read_to_the_limit_and_one_more_however_many_rows_it_holds"),
    ("the read does not stop at --since", _CLI,
     "                break   # newest first: every row after this one is older still\n",
     "                continue\n",
     _T + "test_the_store_is_read_back_to_since_and_no_further"),
    ("a cut list keeps the oldest of what it read, not the most recent", _CLI,
     "    found = sorted(found[:limit], key=",
     "    found = sorted(found[-limit:], key=",
     _T + "test_the_bound_is_said_when_it_is_hit"),
    # 3. the fallback
    ("a store that cannot be asked by kind lists nothing", _CLI,
     '        yield from sorted((r for r in store.scan() if r.get("kind") == "audit"), key=when,\n',
     '        yield from sorted((r for r in [] if r.get("kind") == "audit"), key=when,\n',
     _T + "test_a_store_that_cannot_ask_by_kind_is_still_listed_through_its_scan"),
]
