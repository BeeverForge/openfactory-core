"""#988: a product's knowledge is searchable through the front-end API, in the owner's ranking.

Each cut breaks one promise the read makes and must turn `TEST` red: the published kinds are the
only ones a client reaches, every index kind is classified, the order is the product owner's own,
the read records nothing, and a degraded semantic stage is said rather than swallowed.

The rows labelled "review of #989" break the guards that review asked for — the owner's blank and
switched-off guards, the cap on `q`, the declared parameters and refusals, the gate closed, and the
refusal of a project with no product role — and run alone with `--only "review of #989"`.
"""

TEST = "tests/test_the_product_search_read_model.py"
RETRIEVAL = "openfactory/product/index/retrieval.py"
ITEMS = "openfactory/product/index/items.py"
APP = "openfactory/api/app.py"

MUTATIONS = [
    ("the read drops the published-kinds filter, so a conversation line and a distillate leak",
     RETRIEVAL,
     "    query = Query(text=text, audience=audience, limit=limit, kinds=PUBLISHED_KINDS)",
     "    query = Query(text=text, audience=audience, limit=limit, kinds=())"),

    ("a kind joins the index and nobody classifies it as published or a conversation's",
     ITEMS,
     "KINDS = (DOCUMENT, DECISION, REQUIREMENT, CARD, TURN, DISTILLATE)",
     'KINDS = (DOCUMENT, DECISION, REQUIREMENT, CARD, TURN, DISTILLATE, "note")'),

    ("the read records like a turn — a read becomes a write",
     RETRIEVAL,
     "    return search(Index(key), query, embedder=row, degraded=why)",
     '    return run(project, query, by=DONE_BEFORE, conversation="")'),

    ("the hits are handed over in another order than the pipeline ranked them",
     APP,
     "                 for rank, hit in enumerate(found.hits, start=1)]",
     "                 for rank, hit in enumerate(list(reversed(found.hits)), start=1)]"),

    ("a degraded semantic stage is swallowed instead of said",
     APP,
     '        "degraded": found.degraded,',
     '        "degraded": "",'),

    ("review of #989: a blank query is embedded and searched like any other",
     RETRIEVAL,
     '    if not str(text or "").strip():',
     "    if False:"),

    ("review of #989: a switched-off deployment searches what is left of its index",
     RETRIEVAL,
     "    if not enabled():",
     "    if False:"),

    ("review of #989: a switched-off deployment answers no hits and says nothing of why",
     RETRIEVAL,
     "degraded=KNOWLEDGE_OFF)",
     'degraded="")'),

    ("review of #989: a query of any length reaches the embedder",
     APP,
     "    if len(q) > retrieval.QUERY_CHARS:",
     "    if False:"),

    ("review of #989: the description's cap on q drifts from the one the read enforces",
     APP,
     "_SEARCH_QUERY_CHARS = 300",
     "_SEARCH_QUERY_CHARS = 400"),

    ("review of #989: q is declared with no bound, so the description says none",
     APP,
     'json_schema_extra={"maxLength": _SEARCH_QUERY_CHARS})] = "",',
     ')] = "",'),

    ("review of #989: limit is declared as text, so not a number is no longer refused by its type",
     APP,
     "        limit: Annotated[int, Query(",
     "        limit: Annotated[int | str, Query("),

    ("review of #989: a limit reaches the index unclamped",
     APP,
     "    return max(1, min(retrieval.KNOWLEDGE_MAX, asked))",
     "    return asked"),

    ("review of #989: the read's 400 and 404 are left out of the description",
     APP,
     '    extra = {"responses": described} if described else {}',
     "    extra = {}"),

    ("review of #989: an unknown project is a 500 instead of the house 404",
     APP,
     "    proj = _project_or_404(project)\n    if not _has_product_role(proj):",
     "    proj = ProjectRegistry().get(project)\n    if not _has_product_role(proj):"),

    ("review of #989: a project with no product role has its index opened, made or rebuilt",
     APP,
     "    if not _has_product_role(proj):",
     "    if False:"),

    ("review of #989: a project with no product role is refused in words that say it is registered",
     APP,
     "    if not _has_product_role(proj):\n        raise _no_such_project(project)",
     "    if not _has_product_role(proj):\n        raise HTTPException(status_code=404, "
     "detail=f\"{proj.name} has no product role\")"),

    ("review of #989: the gate lets the search through without a credential",
     APP,
     '    return path.startswith("/api/")',
     '    return path.startswith("/api/") and not path.endswith("/search")'),

    ("review of #989: the versioned address falls out of the product area, so a product credential "
     "is refused it",
     APP,
     '        _VERSIONED_READS.append(compile_path(API_V1 + path.removeprefix("/api"))[0])',
     '        _VERSIONED_READS.append(compile_path(API_V1 + path.removeprefix("/api"))[0]) '
     'if not path.endswith("/search") else None'),
]
