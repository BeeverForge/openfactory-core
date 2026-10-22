"""An audit record that is not kept is seen by readiness, and a `memory` deployment still keeps its
records (#694, PR #1039 review, 2026-10-21), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/694_an_audit_record_not_kept_is_seen.py

The claims, one group of rows each:
  1. readiness has an `audit` check, failing while the last record this process wrote was not
     kept — a store that answered False, one that raised, or no store that could be built — and
     passing again once one is kept; its logged cause counts the records not kept;
  2. a deployment naming the `memory` metrics sink keeps its records in the fallback file, says so
     once per process, and `openfactory audit` lists them.

Every row names the one test that holds its claim.
"""

TEST = "tests/test_an_audit_record_that_is_not_kept_is_seen.py"

_AUDIT = "openfactory/observability/audit.py"
_ACTIONS = "openfactory/actions/__init__.py"
_HEALTH = "openfactory/observability/health.py"
_T = TEST + "::"
_NAMES = _T + "test_readiness_names_the_audit_trail_while_the_last_record_was_not_kept"

MUTATIONS = [
    # 1. readiness
    ("readiness has no audit check", _HEALTH,
     '    "audit": _audit,\n',
     "",
     _NAMES),
    ("a write the store answered False to is not counted", _AUDIT,
     '        _KEEPING.lost(f"{_named(store)} did not take it")\n',
     "        pass\n",
     _NAMES + "[refusing]"),
    ("a write the store raised on is not counted", _AUDIT,
     '        _KEEPING.lost(f"{_named(store)} raised ({exc})")\n',
     "        pass\n",
     _NAMES + "[raising]"),
    ("a record no store could be built for is not counted", _ACTIONS,
     '        audit.lost(f"the record could not be made or no store could be built ({exc})")\n',
     "        pass\n",
     _NAMES + "[unbuildable]"),
    ("a record that lands does not clear the check", _AUDIT,
     "    _KEEPING.kept()\n    return True\n",
     "    return True\n",
     _T + "test_readiness_is_ready_again_once_a_record_is_kept"),
    ("the records not kept are not counted, only the last cause kept", _AUDIT,
     "            self.not_kept += 1\n",
     "            self.not_kept = 1\n",
     _T + "test_readiness_counts_the_records_not_kept_in_the_cause_it_logs"),
    # 2. the memory sink
    ("a memory deployment's records go to its memory sink", _AUDIT,
     'KEEPS_NO_RECORD = frozenset({"null", "memory"})\n',
     'KEEPS_NO_RECORD = frozenset({"null"})\n',
     _T + "test_a_deployment_on_the_memory_sink_keeps_its_audit_records_in_the_fallback_file"),
    ("a memory deployment's records go to its memory sink (the reader)", _AUDIT,
     'KEEPS_NO_RECORD = frozenset({"null", "memory"})\n',
     'KEEPS_NO_RECORD = frozenset({"null"})\n',
     _T + "test_openfactory_audit_on_a_memory_deployment_lists_what_its_commands_recorded"),
    ("the memory fallback is not said", _AUDIT,
     '    if kind != "null" and _KEEPING.first_fallback(kind):\n',
     "    if False:\n",
     _T + "test_the_memory_sink_is_said_once_when_its_records_go_to_the_fallback_file"),
    ("the memory fallback is said on every call", _AUDIT,
     "            if kind in self._fell_back:\n                return False\n",
     "            if False:\n                return False\n",
     _T + "test_the_memory_sink_is_said_once_when_its_records_go_to_the_fallback_file"),
]
