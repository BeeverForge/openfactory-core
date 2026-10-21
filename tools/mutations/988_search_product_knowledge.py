"""#988: a product's knowledge is searchable through the front-end API, in the owner's ranking.

Each cut breaks one promise the read makes and must turn `TEST` red: the published kinds are the
only ones a client reaches, every index kind is classified, the order is the product owner's own,
the read records nothing, and a degraded semantic stage is said rather than swallowed.
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
]
