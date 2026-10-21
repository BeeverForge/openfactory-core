"""`openfactory audit` lists a call that failed as `failed`, not `refused`, and its `--outcome`
filter tells the two apart (#694, PR #1039 review N5, 2026-10-21), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/694_a_call_that_failed_is_listed_as_failed.py

On c310ba28 a row that raised after its side effect and a call cancelled mid-row read `refused`,
which tells an auditor the action did not happen when it may have.
"""

TEST = "tests/test_openfactory_audit_lists_who_did_what.py"

_CLI = "openfactory/cli.py"
_T = TEST + "::"

MUTATIONS = [
    ("a failed call is listed as refused", _CLI,
     '            w for w in ("failed" if code == FAILED else "refused",\n',
     '            w for w in ("refused",\n',
     _T + "test_a_call_that_raised_or_was_cancelled_is_listed_as_failed_not_refused"),
    ("--outcome refused lists the failed calls too", _CLI,
     '        if outcome == "refused" and (r.get("ok") or r.get("code") == FAILED):\n',
     '        if outcome == "refused" and r.get("ok"):\n',
     _T + "test_outcome_refused_lists_refusals_and_outcome_failed_lists_failures"),
]
