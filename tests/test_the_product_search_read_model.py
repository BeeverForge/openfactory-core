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

THE GUARDS OF THE REVIEW OF #989, each a test below:

  - the product owner's own guards (`product/module.py`): a blank `q` finds nothing and asks
    neither the embedder nor the index; a deployment that turned retrieval off says so in
    `degraded` and searches nothing — for every spelling of "off" the switch reads;
  - a `q` past `retrieval.QUERY_CHARS` is refused in the core's refusal shape before anything runs;
  - `q` and `limit` are declared, typed parameters, and the description says the bounds the read
    enforces, with the 400 and the 404 it refuses with;
  - WITH THE GATE CLOSED, on every address the read is served at: no credential and one nobody
    issued are 401, a product and a floor credential read it, an unknown project is a 404;
  - a project with no product role — none declared, or one switched off — is refused before its
    index is opened: no directory is made, and a corrupt file is left as it is; and it is answered
    byte for byte what it would be if nobody had registered it, so a product credential cannot
    tell the two apart.
"""

from __future__ import annotations

import string
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
    # a limit past the ceiling is clamped, never refused
    big = served.client.get(f"/api/product/{served.project.name}/search",
                            params={"q": WORD, "limit": "9999"})
    assert big.status_code == 200 and len(big.json()["hits"]) == 4  # the four published kinds


@pytest.mark.parametrize("asked", [-1, 0, 1, retrieval.KNOWLEDGE_LIMIT, retrieval.KNOWLEDGE_MAX,
                                   retrieval.KNOWLEDGE_MAX + 1])
def test_the_limit_the_index_is_asked_is_the_asked_one_clamped(served, monkeypatch, asked):
    """Both ends and both sides of each, read from the code's own bounds: what reaches the index is
    `asked` clamped to `1…KNOWLEDGE_MAX`, never refused."""
    seen = []
    real = retrieval.search_knowledge
    monkeypatch.setattr(retrieval, "search_knowledge",
                        lambda project, **kw: seen.append(kw["limit"]) or real(project, **kw))

    got = served.client.get(f"/api/product/{served.project.name}/search",
                            params={"q": WORD, "limit": str(asked)})

    assert got.status_code == 200, got.text
    assert seen == [max(1, min(retrieval.KNOWLEDGE_MAX, asked))]


def test_a_limit_that_is_not_a_number_is_refused_as_a_declared_integer(served):
    """`limit` is a declared integer (review of #989): not a number is the framework's 422, named
    by the parameter — never read as some other limit."""
    got = served.client.get(f"/api/product/{served.project.name}/search",
                            params={"q": WORD, "limit": "nonsense"})

    assert got.status_code == 422, got.text
    assert [e["loc"] for e in got.json()["detail"]] == [["query", "limit"]]


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


# ── the product owner's own guards (review of #989) ─────────────────────────────────────────────

def _nothing_is_asked(monkeypatch) -> list[str]:
    """The embedder and the pipeline replaced by doubles that record a call — what a guard that
    asks nothing must leave empty."""
    asked: list[str] = []
    monkeypatch.setattr(retrieval, "embedder", lambda: asked.append("embedder") or (None, ""))
    monkeypatch.setattr(retrieval, "search",
                        lambda *a, **k: asked.append("search") or pytest.fail("searched"))
    return asked


#: Every way a query can be blank as the owner's guard reads it (`not question.strip()`): absent,
#: empty, and every character `str.strip` removes.
BLANK = [None, "", string.whitespace]


@pytest.mark.parametrize("q", BLANK, ids=["absent", "empty", "whitespace"])
def test_a_blank_query_finds_nothing_and_asks_neither_the_embedder_nor_the_index(served,
                                                                                 monkeypatch, q):
    asked = _nothing_is_asked(monkeypatch)

    got = served.client.get(f"/api/product/{served.project.name}/search",
                            params={} if q is None else {"q": q})

    assert got.status_code == 200, got.text
    body = got.json()
    assert body["hits"] == [] and body["searched"] == 0 and body["degraded"] == "", body
    assert asked == [], f"a blank query asked {asked}"
    assert not Index(served.key).path.exists(), "a blank query opened the product's index"


#: Every spelling of "off" the switch reads (`retrieval.enabled`: stripped, any case).
SWITCHED_OFF = [*retrieval.SWITCHED_OFF, *(f" {v.upper()} " for v in retrieval.SWITCHED_OFF)]


@pytest.mark.parametrize("off", SWITCHED_OFF)
def test_a_deployment_that_turned_retrieval_off_says_so_and_searches_nothing(served, monkeypatch,
                                                                             off):
    """The index is no longer brought up to date for the role once the step is off, so the read
    does not search what is left of it — and the answer says why it is empty (AC4: never
    silently), naming the switch."""
    _plant_every_kind(served.key)
    monkeypatch.setenv(retrieval.SWITCH_ENV, off)
    asked = _nothing_is_asked(monkeypatch)

    body = served.client.get(f"/api/product/{served.project.name}/search",
                             params={"q": WORD}).json()

    assert body["hits"] == [] and body["searched"] == 0, body
    assert body["degraded"] == retrieval.KNOWLEDGE_OFF and retrieval.SWITCH_ENV in body["degraded"]
    assert asked == [], f"a switched-off deployment asked {asked}"


def test_a_query_up_to_the_cap_is_searched_and_one_past_it_is_refused_before_anything_runs(
        served, monkeypatch):
    """The cap is `retrieval.QUERY_CHARS` — the most of a query the found file repeats — so the two
    cannot drift. At the cap the read searches; one character past it is a 400 in the core's
    refusal shape, and neither the embedder nor the index is asked."""
    _plant_every_kind(served.key)
    at = f"/api/product/{served.project.name}/search"
    longest = (WORD + " ") * (retrieval.QUERY_CHARS // (len(WORD) + 1))
    longest += "x" * (retrieval.QUERY_CHARS - len(longest))
    assert len(longest) == retrieval.QUERY_CHARS

    searched = served.client.get(at, params={"q": longest})
    assert searched.status_code == 200 and searched.json()["hits"], searched.text

    asked = _nothing_is_asked(monkeypatch)
    refused = served.client.get(at, params={"q": longest + "x"})

    assert refused.status_code == 400, refused.text
    assert isinstance(refused.json()["detail"], str)
    assert str(retrieval.QUERY_CHARS) in refused.json()["detail"]
    assert asked == [], f"a query past the cap asked {asked}"


# ── the description says what the read does ────────────────────────────────────────────────────

def _addresses() -> list[str]:
    """Every address the read is served at, read from the app: its alias and its `/api/v1` form."""
    from openfactory.api.app import app, product_search

    return sorted(r.path for r in app.routes if getattr(r, "endpoint", None) is product_search)


def test_the_read_is_served_at_its_alias_and_its_versioned_address():
    """The parametrisations below run over `_addresses()`; this keeps them from passing on none."""
    assert _addresses() == ["/api/product/{project}/search", "/api/v1/product/{project}/search"]


@pytest.mark.parametrize("address", _addresses())
def test_the_description_declares_the_bounds_the_read_enforces_and_its_refusals(address):
    """`q` and `limit` are typed parameters of the description, and what it says of them is what the
    read enforces — the index's own constants — with the 400 and the 404 it refuses with, in the
    core's refusal shape."""
    from openfactory.api import app as api
    from openfactory.api.openapi import document

    described = document()
    get = described["paths"][address]["get"]
    params = {p["name"]: p for p in get["parameters"] if p["in"] == "query"}

    assert set(params) == {"q", "limit"}
    assert params["q"]["schema"]["type"] == "string"
    assert params["q"]["schema"]["maxLength"] == retrieval.QUERY_CHARS
    assert params["limit"]["schema"]["type"] == "integer"
    assert params["limit"]["schema"]["default"] == retrieval.KNOWLEDGE_LIMIT
    assert f"1…{retrieval.KNOWLEDGE_MAX}" in params["limit"]["description"]
    assert (api._SEARCH_QUERY_CHARS, api._SEARCH_LIMIT, api._SEARCH_MAX) == (
        retrieval.QUERY_CHARS, retrieval.KNOWLEDGE_LIMIT, retrieval.KNOWLEDGE_MAX)
    for status in ("400", "404"):
        schema = get["responses"][status]["content"]["application/json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/Refusal"}, (status, schema)
    assert described["components"]["schemas"]["Refusal"]["properties"]["detail"]


# ── the gate, closed (review of #989: `served` runs with it open) ────────────────────────────────

FLOOR_TOKEN = "floor-q989"
PRODUCT_TOKEN = "ana-q989"


@pytest.fixture
def gated(tmp_path, monkeypatch):
    """The product, served with the gate CLOSED: a floor credential and a product credential are
    issued, and nothing else is. Beside it, two registered projects with NO product role — one that
    declares none, one whose role is switched off."""
    monkeypatch.setenv("OPENFACTORY_HOME", str(tmp_path / ".openfactory"))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", FLOOR_TOKEN)
    monkeypatch.setenv("OPENFACTORY_PRODUCT_TOKENS", f"{PRODUCT_TOKEN}:ana:Ana")
    for var in ("OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_PRODUCT_TOKEN", "OPENFACTORY_IDENTITY"):
        monkeypatch.delenv(var, raising=False)
    from openfactory.adapters.embed import registry as embed_registry
    from openfactory.contracts.product import ProductConfig
    from openfactory.registry import ProjectRegistry

    embed_registry._reset_for_tests()
    project = bed.project(tmp_path)
    undeclared = bed.project(tmp_path, name="quiet").model_copy(update={"product": None})
    switched_off = bed.project(tmp_path, name="hushed").model_copy(update={
        "product": ProductConfig(docs_repo="tidewater/hushed-context", enabled=False)})
    for each in (project, undeclared, switched_off):
        ProjectRegistry().add(each)
    _plant_every_kind(product_key(project))
    from openfactory.api.app import app

    yield SimpleNamespace(client=TestClient(app), project=project,
                          roleless=(undeclared, switched_off))
    embed_registry._reset_for_tests()


def _at(address: str, project: str) -> str:
    return address.replace("{project}", project)


def _as(token: str) -> dict:
    return {"authorization": f"Bearer {token}"}


@pytest.mark.parametrize("address", _addresses())
@pytest.mark.parametrize("presented", [{}, _as("nobody-issued-this")], ids=["none", "unissued"])
def test_without_a_credential_it_issued_the_read_is_a_401(gated, address, presented):
    got = gated.client.get(_at(address, gated.project.name), params={"q": WORD},
                           headers=presented)

    assert got.status_code == 401, got.text
    assert got.json()["detail"] == "unauthorized"


@pytest.mark.parametrize("address", _addresses())
@pytest.mark.parametrize("token", [PRODUCT_TOKEN, FLOOR_TOKEN], ids=["product", "floor"])
def test_a_product_and_a_floor_credential_read_it_on_every_address(gated, address, token):
    got = gated.client.get(_at(address, gated.project.name), params={"q": WORD},
                           headers=_as(token))

    assert got.status_code == 200, got.text
    assert {h["kind"] for h in got.json()["hits"]} == set(PUBLISHED_KINDS)


@pytest.mark.parametrize("address", _addresses())
def test_an_unknown_project_is_a_404_in_the_house_sentence(gated, address):
    got = gated.client.get(_at(address, "nobody-registered-this"), params={"q": WORD},
                           headers=_as(PRODUCT_TOKEN))

    assert got.status_code == 404, got.text
    assert got.json()["detail"] == "no project named 'nobody-registered-this' in this deployment"


@pytest.mark.parametrize("address", _addresses())
@pytest.mark.parametrize("which", [0, 1], ids=["none-declared", "switched-off"])
def test_a_project_with_no_product_role_is_refused_before_its_index_is_opened(gated, address,
                                                                               which):
    """Opening a product's index makes its directory, and drops and rebuilds a file it cannot read
    (`store.Index._connect`) — work for a project the role never reads. Refused first: nothing is
    made, and a corrupt file is left exactly as it is."""
    project = gated.roleless[which]
    index = Index(product_key(project))

    first = gated.client.get(_at(address, project.name), params={"q": WORD},
                             headers=_as(PRODUCT_TOKEN))
    assert first.status_code == 404, first.text
    assert not index.path.parent.exists(), "the read made an index directory for it"

    for made in (index.path.parent.parent, index.path.parent):   # the product's, then its index's
        made.mkdir(exist_ok=True)
        made.chmod(0o755)
    index.path.write_bytes(b"not a database")
    again = gated.client.get(_at(address, project.name), params={"q": WORD},
                             headers=_as(PRODUCT_TOKEN))
    assert again.status_code == 404, again.text
    assert index.path.read_bytes() == b"not a database", "the read dropped its corrupt index"


@pytest.mark.parametrize("address", _addresses())
@pytest.mark.parametrize("which", [0, 1], ids=["none-declared", "switched-off"])
def test_a_project_with_no_product_role_is_answered_as_if_nobody_had_registered_it(gated, address,
                                                                                    which):
    """The gate's rule for the board read (`_the_product_owners_board`): an unknown project and one
    the product area does not reach are refused alike, so the refusal names nothing. Measured, not
    spelled: the body for the registered project is byte for byte the body once it is unregistered."""
    from openfactory.registry import ProjectRegistry

    project = gated.roleless[which]
    at = _at(address, project.name)

    registered = gated.client.get(at, params={"q": WORD}, headers=_as(PRODUCT_TOKEN))
    ProjectRegistry().remove(project.name)
    unknown = gated.client.get(at, params={"q": WORD}, headers=_as(PRODUCT_TOKEN))

    assert unknown.status_code == 404, unknown.text
    assert (registered.status_code, registered.content) == (unknown.status_code, unknown.content)
