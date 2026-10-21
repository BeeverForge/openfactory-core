"""Every project of a product is linked to its context repository, however many projects it has
(journey 0, #640, #663), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/every_member_of_a_product_is_linked.py

The claims, each a row:
  1. every project the context lists in `sources:` is linked, whatever the product is called;
  2. a project the context does not list is refused, and the refusal says so;
  3. the product's name admits a project alone only when it is the project's own name, and a
     listing on the repository's name alone does not stand in for it.
"""

TEST = "tests/test_every_member_of_a_product_is_linked.py"
CFG = "openfactory/product/config.py"

MUTATIONS = [
    # 1. every member
    # RE-PINNED (#992): the condition reads `code_less` first — a product before its code has no
    # code repository for `sources:` to list, so only its name can admit it
    ("TODAY'S RUN: only the project named like the product is linked", CFG,
     '    if (docs.product or "").strip().lower() != str(project.name).strip().lower() and (\n'
     "            code_less or not _listed(project, docs)):",
     '    if (docs.product or "").strip().lower() != str(project.name).strip().lower():'),

    # 2. the isolation
    ("the refusal no longer says the project is missing from `sources:`", CFG,
     "if code_less else \"its code repository is not in that product's `sources:`. \")",
     'if code_less else ". ")'),
    ("a project is admitted as listed whether or not the context lists it", CFG,
     "    return bool(source) and any(\n"
     "        repo_match(source, normalize_repo(s)) == MATCH_EXACT for s in docs.sources)",
     "    return True"),

    # 3. what the name alone admits
    ("a listing on the repository's name alone admits the project", CFG,
     "        repo_match(source, normalize_repo(s)) == MATCH_EXACT for s in docs.sources)",
     "        repo_match(source, normalize_repo(s)) for s in docs.sources)"),
    ("the product's name no longer decides where nothing is listed", CFG,
     '    if (docs.product or "").strip().lower() != str(project.name).strip().lower() and (\n'
     "            code_less or not _listed(project, docs)):",
     "    if False:"),
    ("the name is compared as written, case and padding included", CFG,
     '    if (docs.product or "").strip().lower() != str(project.name).strip().lower() and (',
     "    if (docs.product or \"\") != str(project.name) and ("),
]
