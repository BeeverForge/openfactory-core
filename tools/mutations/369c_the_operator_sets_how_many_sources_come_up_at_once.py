"""The operator sets how many of a product's sources are brought up at once, eight when unset, and
a value nobody can read is eight, said once (#369).

Run:  .venv/bin/python tools/mutate.py tools/mutations/369c_the_operator_sets_how_many_sources_come_up_at_once.py

`sources.check_out` ran every source on a pool fixed at eight. At a few hundred sources that is the
bound on how long a first turn waits, and only the deployment knows what its forge and its machine
take. Row 1 is the setting being read at all; rows 2-4 are the fallback (the default, not one at a
time; the default stays eight; never silent); row 5 is the configuration reference telling an
operator the default the code has.
"""

TEST = "tests/test_the_operator_sets_how_many_sources_are_brought_up_at_once.py"

SOURCES = "openfactory/product/sources.py"
REFERENCE = "docs/reference/configuration.md"

MUTATIONS = [
    ("TODAY'S DEFECT: the operator's setting is ignored, eight is fixed", SOURCES,
     "max_workers=min(parallel(), len(found.sources))",
     "max_workers=min(DEFAULT_PARALLEL, len(found.sources))"),

    ("a parallelism nobody can read throttles the turn to one source at a time", SOURCES,
     "\"are brought up at once\", raw, DEFAULT_PARALLEL)\n"
     "        return DEFAULT_PARALLEL\n",
     "\"are brought up at once\", raw, DEFAULT_PARALLEL)\n"
     "        return 1\n"),

    ("the default moved from eight", SOURCES,
     "DEFAULT_PARALLEL = 8\n",
     "DEFAULT_PARALLEL = 4\n"),

    ("a parallelism nobody can read is silent", SOURCES,
     "            log.warning(\"OPENFACTORY_SOURCES_PARALLEL=%r",
     "            (lambda *_: None)(\"OPENFACTORY_SOURCES_PARALLEL=%r"),

    ("the reference tells an operator a default the code does not have", REFERENCE,
     "Unset → `8`; a value that is not a positive number is 8",
     "Unset → `16`; a value that is not a positive number is 8",
     "tests/test_the_documented_default_is_the_real_one.py"),
]
