"""A product's knowledge is searchable through the front-end API, in the product owner's own
ranking (#988).

THE ACCEPTANCE CRITERIA, each a test below by name:

  - the read returns the kinds a product publishes — requirements, decisions, documents, cards —
    and NEVER a line of a conversation or a model's distillate of one; the restriction is what
    leaves them out, not absence, so the owner's raw search still finds them;
  - every kind the index holds is classified as published or a conversation's — a kind added to
    `KINDS` later turns this red until it is placed;
  - each hit carries its kind, its source, its product, a snippet and its rank within the product,
    and the order is exactly the one the shared pipeline ranks a turn's search in;
  - it is a read: it records nothing, and the route is GET-only;
  - a product whose semantic stage is degraded says so in the answer, and the read runs under no
    product semaphore.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from openfactory.contracts.document import CLIENT, INTERNAL
from openfactory.product.index import retrieval
from openfactory.product.index.items import (
    CARD,
    CLOSED,
    CONVERSATION_KINDS,
    DECISION,
    DISTILLATE,
    DOCUMENT,
    KINDS,
    PUBLISHED_KINDS,
    REQUIREMENT,
    TURN,
    Item,
    conversation_digest,
)
from openfactory.product.index.search import Query, search
from openfactory.product.index.store import Index
from openfactory.product.key import product_key
from tests import index_bed as bed

#: A rare word every planted item carries, so a lexical search alone finds all of them.
WORD = "zephyr"


@pytest.fixture
def served(tmp_path, monkeypatch):
    """One product registered and its API served, with nothing configured — so a read is open and
    the gate scopes `/api/product/` to the product area. The index is each test's to build."""
    monkeypatch.setenv("OPENFACTORY_HOME", str(tmp_path / ".openfactory"))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    for var in ("OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_PRODUCT_TOKENS",
                "OPENFACTORY_IDENTITY"):
        monkeypatch.delenv(var, raising=False)
    from openfactory.adapters.embed import registry as embed_registry

    embed_registry._reset_for_tests()
    project = bed.project(tmp_path)
    from openfactory.registry import ProjectRegistry

    ProjectRegistry().add(project)
    from openfactory.api.app import app

    yield SimpleNamespace(client=TestClient(app), project=project, key=product_key(project),
                          tmp_path=tmp_path)
    embed_registry._reset_for_tests()


def _plant_every_kind(key: str) -> Index:
    """One item of EACH of the index's kinds, each in its own group and each carrying `WORD`, so a
    single query matches all six and a hit per kind is a group of its own."""
    convo = conversation_digest("room:tidewater")
    items = [
        Item(id="doc:a.md#0", grp="doc:a.md", product=key, kind=DOCUMENT, source="a.md",
             title="A document", text=f"the {WORD} in a document", audience=CLIENT),
        Item(id="doc:b.md!d0", grp="doc:b.md", product=key, kind=DECISION, source="b.md",
             title="A document", text=f"a decision about {WORD}", audience=CLIENT,
             origin="a model's reading"),
        Item(id="req:0001", grp="req:0001", product=key, kind=REQUIREMENT,
             source="requirements/0001.md", title="REQ-0001 — one", text=f"the {WORD} requirement",
             audience=CLIENT, requirements=(1,)),
        Item(id="card:tidewater:100", grp="card:tidewater:100", product=key, kind=CARD,
             source="card #100 (tidewater)", title="#100 — a card", text=f"a card about {WORD}",
             audience=CLIENT, cards=("100",), status=CLOSED),
        Item(id=f"turn:{convo}:1", grp=f"turn:{convo}:1", product=key, kind=TURN,
             source="a conversation", text=f"someone said {WORD} in a conversation",
             audience=CLIENT, conversation=convo, private=False, addressed=True),
        Item(id=f"dist:{convo}#0", grp=f"dist:{convo}", product=key, kind=DISTILLATE,
             source=".openfactory/conversations/room/x/d.md", title="a conversation, distilled",
             text=f"the conversation agreed on {WORD}", audience=CLIENT, conversation=convo,
             private=False),
    ]
    index = Index(key)
    with index.open() as con:
        for item in items:
            index.replace_group(con, item.grp, "v1", [item])
        con.commit()
    return index


# ── what a product publishes, and what it never returns ──────────────────────────────────────────

def test_every_index_kind_is_classified_as_published_or_a_conversation():
    """The guard AC #2 asks for: a kind added to `KINDS` later is on one side here or the suite
    does not pass — so a new kind can never reach a client's read by default."""
    assert set(PUBLISHED_KINDS) | set(CONVERSATION_KINDS) == set(KINDS)
    assert not set(PUBLISHED_KINDS) & set(CONVERSATION_KINDS)
    assert set(PUBLISHED_KINDS) == {DOCUMENT, DECISION, REQUIREMENT, CARD}
    assert set(CONVERSATION_KINDS) == {TURN, DISTILLATE}


def test_the_read_returns_published_kinds_and_never_a_conversation(served):
    """The read returns the four published kinds; a conversation's line and its distillate are
    never a hit — and the OWNER'S raw search over the same index finds them, so what leaves them
    out is the restriction, not absence."""
    index = _plant_every_kind(served.key)

    found = retrieval.search_knowledge(served.project, text=WORD, limit=20)

    assert {h.kind for h in found.hits} == {DOCUMENT, DECISION, REQUIREMENT, CARD}
    assert TURN not in {h.kind for h in found.hits}
    assert DISTILLATE not in {h.kind for h in found.hits}
    raw = search(index, Query(text=WORD, audience=INTERNAL, limit=20))
    assert {TURN, DISTILLATE} <= {h.kind for h in raw.hits}, "the owner's own search finds them"


def test_the_api_answers_a_hit_per_published_kind_with_its_citation(served):
    index = _plant_every_kind(served.key)

    got = served.client.get(f"/api/product/{served.project.name}/search",
                            params={"q": WORD, "limit": "20"})

    assert got.status_code == 200, got.text
    body = got.json()
    assert body["project"] == served.project.name and body["product"] == served.key
    assert body["query"] == WORD
    assert {h["kind"] for h in body["hits"]} == {"document", "decision", "requirement", "card"}
    for rank, hit in enumerate(body["hits"], start=1):
        assert hit["rank"] == rank
        assert hit["product"] == served.key
        assert hit["source"] and hit["snippet"], hit
    # the order is the product owner's own: the pipeline's, restricted to the published kinds
    owner = search(index, Query(text=WORD, audience=INTERNAL, limit=20, kinds=PUBLISHED_KINDS))
    assert [(h["kind"], h["source"]) for h in body["hits"]] == [(h.kind, h.source)
                                                                for h in owner.hits]


# ── the product owner's own ranking ───────────────────────────────────────────────────────────────

def test_the_read_inherits_the_product_owners_exact_term_tier(served):
    """On the years-old fixture, "requirement 6" puts REQ-0006 first — the exact-term tier of the
    shared pipeline — and the whole order is exactly what that pipeline hands a turn's search,
    restricted to the published kinds."""
    bed.build(served.tmp_path, project_=served.project)

    body = served.client.get(f"/api/product/{served.project.name}/search",
                             params={"q": "requirement 6"}).json()

    assert body["hits"], body
    first = body["hits"][0]
    # the exact-term tier surfaces REQ-0006's group first (its requirement, or a row of its own
    # register — they share one group, as the owner's search returns them)
    assert first["kind"] in ("requirement", "decision") and "0006" in str(first["title"]), first
    owner = search(Index(served.key), Query(text="requirement 6", audience=INTERNAL,
                                            limit=retrieval.KNOWLEDGE_LIMIT, kinds=PUBLISHED_KINDS))
    assert [(h["kind"], h["source"], h["rank"]) for h in body["hits"]] == [
        (h.kind, h.source, rank) for rank, h in enumerate(owner.hits, start=1)]


def test_a_limit_is_honoured_and_clamped(served):
    _plant_every_kind(served.key)

    assert len(served.client.get(f"/api/product/{served.project.name}/search",
                                 params={"q": WORD, "limit": "2"}).json()["hits"]) == 2
    # a limit past the ceiling is clamped, never refused, and a non-number falls back to the default
    big = served.client.get(f"/api/product/{served.project.name}/search",
                            params={"q": WORD, "limit": "9999"})
    assert big.status_code == 200 and len(big.json()["hits"]) == 4  # the four published kinds
    assert served.client.get(f"/api/product/{served.project.name}/search",
                             params={"q": WORD, "limit": "nonsense"}).status_code == 200


# ── a read, not a turn ──────────────────────────────────────────────────────────────────────────

def test_the_read_records_nothing_and_the_route_is_get_only(served):
    """A turn's search is recorded (`searches.jsonl`); a client's read is not — it belongs to no
    conversation. And the route serves only GET: nothing mutates the product through it."""
    _plant_every_kind(served.key)

    served.client.get(f"/api/product/{served.project.name}/search", params={"q": WORD})

    assert retrieval.recorded(served.key) == [], "a client's read recorded a search like a turn"
    from openfactory.api.app import app

    methods = {m for route in app.routes
               if getattr(route, "path", "") in ("/api/product/{project}/search",
                                                  "/api/v1/product/{project}/search")
               for m in (getattr(route, "methods", None) or set())}
    assert methods and methods <= {"GET", "HEAD"}, methods


# ── never silent, never under the semaphore ──────────────────────────────────────────────────────

def test_a_degraded_semantic_stage_is_said_in_the_answer(served):
    """No embedder on this machine: the answer says the semantic stage did not run, naming the
    variable that would turn it on — never silence."""
    from openfactory.adapters.embed.local import MODEL_ENV

    _plant_every_kind(served.key)

    body = served.client.get(f"/api/product/{served.project.name}/search",
                             params={"q": WORD}).json()
    assert body["degraded"] and MODEL_ENV in body["degraded"], body


def test_the_read_runs_under_no_product_semaphore(served):
    """The read goes through the same guard a turn's search does: asked while the product's
    semaphore on what becomes work is held, it refuses rather than run under it (ADR-0053 D7)."""
    from openfactory.product import semaphore

    _plant_every_kind(served.key)

    with semaphore.held(served.project):
        with pytest.raises(semaphore.ModelUnderSemaphore):
            retrieval.search_knowledge(served.project, text=WORD)
