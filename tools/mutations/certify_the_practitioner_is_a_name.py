"""`certify deployment` keeps the practitioner's name and refuses an address typed in its place, and
`redactions.json` accounts for every field carried as typed (review of #549), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/certify_the_practitioner_is_a_name.py

The practitioner is kept past every rule a pack applies; `helena.prado@altiva.io` reached
`pack.json` and `summary.md` of a pack that promises no e-mail address. The claims, each a row:

  1. the pack's own rules are asked of the practitioner, and an address is refused before anything
     is read — by the CLI, and by `assemble` for any door that builds a pack (review of #588);
  2. the log names every field carried verbatim.
"""

TEST = "tests/test_certify_deployment_writes_only_when_told.py"
REFUSALS = "openfactory/cli_refusals.py"
REDACT = "openfactory/certify/redact.py"
PACK = "openfactory/certify/pack.py"

MUTATIONS = [
    ("TODAY'S DEFECT: an address typed as the practitioner is kept", REFUSALS,
     "    if carries:\n        return refuse_flag(\"--practitioner\"",
     "    if False:\n        return refuse_flag(\"--practitioner\""),
    # ADDED 2026-10-10 (review of #588)
    ("a door other than the CLI builds a pack around an address", PACK,
     "    carries = what_a_name_carries(practitioner)\n    if carries:\n        raise Unsafe(",
     "    carries = what_a_name_carries(practitioner)\n    if False:\n        raise Unsafe(",
     "tests/test_a_pack_names_nobody.py"),
    ("the rules are not asked of the practitioner", REDACT,
     '    return Redactor(salt=b"practitioner", identifiers={}).survivors(name)',
     "    return []"),
    ("the log names the practitioner alone", REDACT,
     'KEPT = ("practitioner", "partner", "profile")',
     'KEPT = ("practitioner",)',
     "tests/test_a_pack_names_nobody.py"),
]
