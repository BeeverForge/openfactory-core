"""#169, proven by breaking it — `product init` writes a `sources:` its own check accepts.

The command kept a candidate source only when it contained a `/`, the `owner/name` shape of one
forge, while the membership check the file must pass (`resolve_product_link`) asks for
`_source_repo(project)` read by `normalize_repo`. On a forge whose registry names repositories
bare, the project's own repository and every bare `--source` were dropped, the file said
`sources: []`, and the link refused the project that had just proposed it.

FOUR CLAIMS:

  1. **The project's own repository is written**, whatever the forge's spelling — the one the
     check asks for, from the check's own function.
  2. **Every `--source` the check can read is written**, bare or qualified.
  3. **The tracker's repository is not a source** because it is the tracker's — `_source_repo`
     reads the forge and falls back to the tracker only when there is no forge — not because of
     how it is spelled.
  4. **One repository is written once**, and a `--source` the check cannot read is refused by name
     before the client's repository is touched.

The guard is `tests/test_product_init_writes_a_file_its_own_check_accepts.py`.
"""

TEST = "tests/test_product_init_writes_a_file_its_own_check_accepts.py"

CLI = "openfactory/cli.py"
#: RE-PINNED 2026-10-23 (#741), every row: `product init` maps onto the `product_init` row, and the
#: sources are read in `_product_sources` there. The claims are unchanged; the project's own
#: repository is now `own`, which is empty for a product that started before its code (#992).
CATALOG = "openfactory/actions/catalog.py"

MUTATIONS = [
    ("THE DEFECT ITSELF: the slash rule is back, and a bare repository is not a source", CATALOG,
     "        if (key := normalize_repo(candidate)) and key not in spelled:\n",
     '        if (key := normalize_repo(candidate)) and key not in spelled and "/" in candidate:\n'),

    ("the project's own repository is left out of the file", CATALOG,
     "    for candidate in [*own, *given]:\n",
     "    for candidate in [*given]:\n"),

    ("the operator's --source arguments are ignored", CATALOG,
     "    for candidate in [*own, *given]:\n",
     "    for candidate in [*own]:\n"),

    ("the tracker's repository is swept in beside the forge's, as the slash rule did for GitHub",
     CATALOG,
     "    for candidate in [*own, *given]:\n",
     "    for candidate in [*own, project.tracker.repo or '', *given]:\n"),

    ("one repository in two spellings is written twice: deduplicated by spelling, as a set was",
     CATALOG,
     "        if (key := normalize_repo(candidate)) and key not in spelled:\n"
     "            spelled[key] = candidate\n",
     "        if (key := normalize_repo(candidate)) and candidate not in spelled:\n"
     "            spelled[candidate] = candidate\n"),

    ("an unreadable --source is dropped without a word instead of refused", CATALOG,
     "    if unreadable:\n        # REFUSED BEFORE ANYTHING IS CLONED",
     "    if False:\n        # REFUSED BEFORE ANYTHING IS CLONED"),
]
