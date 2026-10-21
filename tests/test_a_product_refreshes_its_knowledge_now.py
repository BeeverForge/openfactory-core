"""A product's knowledge is brought up to date when somebody asks, not only on the schedule (#1004).

`product_refresh` starts the pass on the worker and answers at once — started, or joined to the pass
already running for the product — and `product_status` says afterwards when it finished, how, and
what it did not bring up. The pass is the scheduled one's (`product/refresh.py`): the documents read
by their own pass, the index brought up by the one indexer, and an asked pass reads every registry
project's board besides.

Each rule is held over a family read from the code: the sources the index reads only when handed
(`sync.sync`'s own `is not None` branches), the kinds a client's read searches
(`items.PUBLISHED_KINDS`), the registry projects of a product (`model.members`), the ways a pass
ends (`refresh.OUTCOMES`), and the three transports through the action layer. What is real: the
documents' pass over the years-old fixture, its corpus and board, the index, the record, the row,
and — in the one test that owns it — the durable engine. Stood in: a model's reading of a document,
the embedder, the board's tracker, and the context repository's checkout.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from openfactory import actions
from openfactory.actions import catalog
from openfactory.product import refresh as knowledge
from openfactory.product.index import retrieval
from openfactory.product.index.items import PUBLISHED_KINDS
from openfactory.runtime.temporal import activities as acts
from openfactory.runtime.temporal.io import KnowledgeRefreshInput
from tests import index_bed as bed

#: A pass long enough for the fixture, and the one the worker hands every pass.
BUDGET = float(acts.DOCUMENT_PASS_SECONDS)


def _context(world):
    """The product role's own context as `ProductModule.context` answers it — a real
    `ProductContext`, active or not, over the fixture's checkout."""
    from openfactory.product.config import ProductLink
    from openfactory.product.corpus import Corpus
    from openfactory.product.loader import ProductContext

    link = ProductLink(active=world.available, docs_repo="tidewater/context",
                       kind="ok" if world.available else "config",
                       reason="" if world.available else "the manifest could not be read")
    return ProductContext(link=link,
                          corpus=bed.corpus(world.tree) if world.available else Corpus(),
                          docs_path=world.docs_path, docs_commit="c0ffee",
                          requirements_dir="requirements")


@pytest.fixture
def product(tmp_path, monkeypatch):
    """The years-old fixture as a registry project with a product role: its context repository
    checked out, its corpus read, its board readable, a model's reading and an embedder stood in.
    `world` is what a case changes: the context's availability or checkout, a context that raises,
    each registry project's board (None: unreadable), the embedder."""
    from openfactory.product.module import ProductModule
    from openfactory.registry import ProjectRegistry

    project = bed.project(tmp_path)
    ProjectRegistry().add(project)
    tree = bed.context(tmp_path)
    world = SimpleNamespace(project=project, tree=tree, available=True, docs_path=str(tree),
                            raises=None, boards={project.name: bed.cards()},
                            embedder=bed.ConceptEmbedder())

    def context(self, **_k):
        if world.raises is not None:
            raise world.raises
        return _context(world)

    monkeypatch.setattr(ProductModule, "context", context)
    monkeypatch.setattr(ProductModule, "_board_cards",
                        lambda self: world.boards.get(self.project.name))
    monkeypatch.setattr("openfactory.product.documents.ingest.ModelReader",
                        lambda **_k: bed.FixtureReader())
    monkeypatch.setattr(retrieval, "embedder", lambda: (world.embedder, ""))
    return world


def _inp(world) -> KnowledgeRefreshInput:
    return KnowledgeRefreshInput(project=world.project.name)


def _groups(project, prefix: str) -> dict[str, str]:
    from openfactory.product.index.store import Index
    from openfactory.product.key import product_key

    with Index(product_key(project)).open() as con:
        return Index.groups(con, prefix)


def _kinds(project) -> set[str]:
    from openfactory.product.index.store import Index
    from openfactory.product.key import product_key

    with Index(product_key(project)).open() as con:
        return {str(row[0]) for row in con.execute("SELECT DISTINCT kind FROM items")}


# ── the pass: every source the index reads, through the one indexer ─────────────────────────────

def _sources_of_the_index() -> set[str]:
    """The parameters `sync` reads only when it is handed them — each `<param> is not None` in its
    body, read off its syntax tree: the sources an index is brought up to."""
    from openfactory.product.index import sync as module

    fn = ast.parse(inspect.getsource(module.sync)).body[0]
    params = {a.arg for a in [*fn.args.args, *fn.args.kwonlyargs]}
    return {node.left.id for node in ast.walk(fn)
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
            and node.left.id in params and all(isinstance(op, ast.IsNot) for op in node.ops)
            and all(isinstance(c, ast.Constant) and c.value is None for c in node.comparators)}


def _spied(monkeypatch) -> list[set[str]]:
    """Every call the pass makes to the one indexer, as the set of sources it handed — the real
    `sync` runs underneath."""
    real = retrieval.sync
    calls: list[set[str]] = []
    sources = _sources_of_the_index()

    def spy(index, **kwargs):
        calls.append({name for name in sources if kwargs.get(name) is not None})
        return real(index, **kwargs)

    monkeypatch.setattr(retrieval, "sync", spy)
    return calls


def test_the_index_s_sources_are_read_off_its_code():
    """A derivation that broke would report an empty family, which every rule below would pass."""
    assert {"records", "corpus", "cards", "said"} <= _sources_of_the_index()


def test_an_asked_pass_hands_the_index_every_source_it_reads_but_the_ones_it_names(product,
                                                                                   monkeypatch):
    handed = _spied(monkeypatch)

    acts._do_refresh_product_knowledge(_inp(product))

    sources = _sources_of_the_index()
    assert set(knowledge.NOT_REFRESHED) <= sources, "a source left out that the index no longer has"
    assert all(why.strip() for why in knowledge.NOT_REFRESHED.values())
    assert set().union(*handed) == sources - set(knowledge.NOT_REFRESHED), handed


def test_what_the_schedule_hands_the_index_an_asked_pass_hands_it_too(product, monkeypatch):
    handed = _spied(monkeypatch)
    assert acts._do_ingest_documents(_inp(product)).endswith("0 unchanged")
    scheduled = set().union(*handed)
    handed.clear()

    acts._do_refresh_product_knowledge(_inp(product))

    assert scheduled and scheduled <= set().union(*handed), (scheduled, handed)


def test_after_an_asked_pass_every_kind_a_client_reads_is_in_the_index(product):
    assert not set(PUBLISHED_KINDS) & _kinds(product.project)

    said = acts._do_refresh_product_knowledge(_inp(product))

    assert said.startswith(knowledge.REFRESHED), said
    assert set(PUBLISHED_KINDS) <= _kinds(product.project)
    found = retrieval.search_knowledge(product.project, text="invoice numbering sequence")
    assert any(hit.kind == "requirement" for hit in found.hits), found.hits


def test_an_asked_pass_reads_the_board_of_every_registry_project_of_the_product(product,
                                                                                tmp_path):
    from openfactory.product.model import members
    from openfactory.registry import ProjectRegistry

    ledger = bed.project(tmp_path, name="ledger")
    ProjectRegistry().add(ledger)
    product.boards["ledger"] = bed.cards()[:1]
    names = [p.name for p in members(ledger)]
    assert sorted(names) == ["ledger", "tidewater"]

    done = knowledge.documents_and_index(ledger, by=knowledge.ASKED, budget_seconds=BUDGET,
                                         boards=True)

    assert done.outcome == knowledge.REFRESHED, done
    for name in names:
        assert _groups(ledger, f"card:{name}:"), f"the board of {name} is not in the index"
        assert f"board:{name}" in done.sources


def test_a_board_that_cannot_be_read_is_said_and_its_cards_are_kept(product):
    knowledge.documents_and_index(product.project, by=knowledge.ASKED, budget_seconds=BUDGET,
                                  boards=True)
    kept = _groups(product.project, "card:tidewater:")
    assert kept
    product.boards["tidewater"] = None

    done = knowledge.documents_and_index(product.project, by=knowledge.ASKED,
                                         budget_seconds=BUDGET, boards=True)

    assert done.outcome == knowledge.DEGRADED
    assert any("the board of tidewater could not be read" in d for d in done.degraded)
    assert _groups(product.project, "card:tidewater:") == kept


def test_the_schedule_does_not_read_the_boards_and_an_asked_pass_does(product, monkeypatch):
    """The one difference between the two callers, and the reason `boards` exists: a board read
    is a tracker call the schedule never made."""
    read: list[str] = []
    real = product.boards

    def counted(self):
        read.append(self.project.name)
        return real.get(self.project.name)

    from openfactory.product.module import ProductModule

    monkeypatch.setattr(ProductModule, "_board_cards", counted)
    acts._do_ingest_documents(_inp(product))
    assert read == []
    acts._do_refresh_product_knowledge(_inp(product))
    assert read == ["tidewater"]


# ── the answer: at once, one flight per product, on every transport ─────────────────────────────

class _Engine:
    """The durable engine as the row meets it: a workflow started under an id, refused with the
    engine's own error while a run under that id is open. `execute_workflow` is absent on purpose —
    a row that waited for the pass would fail here."""

    def __init__(self) -> None:
        self.started: list[dict] = []
        self.open: set[str] = set()

    async def start_workflow(self, name, arg, *, id, task_queue, **options):
        from temporalio.exceptions import WorkflowAlreadyStartedError

        if id in self.open:
            raise WorkflowAlreadyStartedError(id, name)
        self.open.add(id)
        self.started.append({"name": name, "arg": arg, "id": id, "task_queue": task_queue,
                             **options})
        return SimpleNamespace(id=id)


@pytest.fixture
def engine(monkeypatch):
    made = _Engine()

    async def _connected():
        return made, None

    monkeypatch.setattr(catalog, "_connected", _connected)
    return made


def _admin() -> actions.Actor:
    return actions.Actor(id="ana", display="Ana", via="panel", admin=True)


def _ask(transport: str, project: str) -> tuple[bool, dict]:
    """`(ok, data)` — one ask, through the action layer, the panel's route or the command line."""
    if transport == "layer":
        out = asyncio.run(actions.perform("product_refresh", by=_admin(), project=project))
        return out.ok, dict(out.data)
    if transport == "http":
        from fastapi.testclient import TestClient

        from openfactory.api.app import app

        r = TestClient(app).post("/api/act/product_refresh", json={"params": {"project": project}})
        body = r.json()
        return r.status_code == 200 and body["ok"], body["data"]
    from typer.testing import CliRunner

    from openfactory.cli import app as cli

    result = CliRunner().invoke(cli, ["act", "product_refresh", "--param", f"project={project}",
                                      "--json"])
    body = json.loads(result.output)
    return result.exit_code == 0 and body["ok"], body["data"]


TRANSPORTS = ("layer", "http", "cli")


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_every_transport_starts_the_pass_on_the_worker_and_answers_at_once(product, engine,
                                                                           transport,
                                                                           monkeypatch):
    monkeypatch.delenv("OPENFACTORY_PANEL_TOKEN", raising=False)
    from openfactory.runtime.temporal import TASK_QUEUE

    ok, data = _ask(transport, product.project.name)

    assert ok, data
    assert data["refresh"] == knowledge.STARTED
    (started,) = engine.started
    assert started["name"] == "ProductKnowledgeRefreshWorkflow"
    assert started["arg"].project == product.project.name
    assert started["id"] == knowledge.workflow_id(product.project)
    assert started["task_queue"] == TASK_QUEUE
    assert started["execution_timeout"] == knowledge.FLIGHT_CEILING
    assert set(data["knowledge"]) == set(knowledge.state(product.project))
    assert not _kinds(product.project) & set(PUBLISHED_KINDS), "the request ran the pass itself"


def test_the_flight_is_the_product_s_whichever_registry_project_asks(tmp_path):
    from openfactory.product.model import members
    from openfactory.registry import ProjectRegistry

    for name in ("tidewater", "ledger"):
        ProjectRegistry().add(bed.project(tmp_path, name=name))
    elsewhere = bed.project(tmp_path, name="acme", docs_repo="acme/context")
    group = members(bed.project(tmp_path))

    assert len(group) == 2
    assert len({knowledge.workflow_id(p) for p in group}) == 1
    assert knowledge.workflow_id(elsewhere) != knowledge.workflow_id(group[0])


async def test_a_second_ask_while_one_runs_joins_it_and_starts_nothing(product, engine, tmp_path):
    from openfactory.registry import ProjectRegistry

    ProjectRegistry().add(bed.project(tmp_path, name="ledger"))

    first, second = await asyncio.gather(
        actions.perform("product_refresh", by=_admin(), project="tidewater"),
        actions.perform("product_refresh", by=_admin(), project="ledger"))

    assert first.ok and second.ok, (first, second)
    assert sorted([first.data["refresh"], second.data["refresh"]]) == [knowledge.JOINED,
                                                                         knowledge.STARTED]
    assert len(engine.started) == 1
    engine.open.clear()  # the pass ended
    again = await actions.perform("product_refresh", by=_admin(), project="ledger")
    assert again.data["refresh"] == knowledge.STARTED and len(engine.started) == 2


async def test_a_start_the_engine_refuses_for_another_reason_is_said_with_a_reference(
        product, monkeypatch, caplog):
    class _Broken:
        async def start_workflow(self, *_a, **_k):
            raise RuntimeError("namespace not found")

    async def _connected():
        return _Broken(), None

    monkeypatch.setattr(catalog, "_connected", _connected)
    out = await actions.perform("product_refresh", by=_admin(), project="tidewater")

    assert not out.ok and out.code == actions.FAILED
    assert out.data["reference"] and out.data["reference"] in caplog.text


async def test_with_no_engine_it_is_refused_as_unavailable_and_nothing_is_read(product,
                                                                              monkeypatch):
    from openfactory.actions.base import UNAVAILABLE, refused

    async def _connected():
        return None, refused(UNAVAILABLE, "the durable engine is not answering")

    monkeypatch.setattr(catalog, "_connected", _connected)
    out = await actions.perform("product_refresh", by=_admin(), project="tidewater")

    assert not out.ok and out.code == actions.UNAVAILABLE
    assert not knowledge.record_path(product.project).exists()


async def test_only_an_admin_may_ask_and_the_engine_is_not_asked_first(product, engine):
    assert catalog.CATALOG["product_refresh"].needs_admin
    reader = actions.Actor(id="bia", display="Bia", via="panel", admin=False)

    out = await actions.perform("product_refresh", by=reader, project="tidewater")

    assert not out.ok and out.code == actions.DENIED and engine.started == []


async def test_product_ingest_still_answers_what_it_read_inside_the_request(product, monkeypatch):
    """`product_ingest`'s callers read its answer — a named file, read now and reported on — and
    it asks no engine for it."""
    async def _no_engine():
        raise AssertionError("product_ingest asked the durable engine")

    monkeypatch.setattr(catalog, "_connected", _no_engine)
    out = await actions.perform("product_ingest", by=_admin(), project="tidewater",
                                path="notes/2020-02-10-kickoff.md")

    assert out.ok, out.message
    assert out.data["ingested"] == ["notes/2020-02-10-kickoff.md"]


# ── bounded, and heartbeating ───────────────────────────────────────────────────────────────────

def test_the_pass_is_bounded_inside_its_flight():
    assert acts.DOCUMENT_PASS_SECONDS < knowledge.PASS_CEILING.total_seconds()
    assert knowledge.PASS_HEARTBEAT < knowledge.PASS_CEILING <= knowledge.FLIGHT_CEILING
    assert knowledge.STOPPED_AFTER >= knowledge.FLIGHT_CEILING


def test_the_workflow_runs_its_one_activity_with_the_pass_s_bounds_and_a_heartbeat():
    from openfactory.runtime.temporal import workflow as wf

    tree = ast.parse(inspect.getsource(wf.ProductKnowledgeRefreshWorkflow))
    (call,) = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
               and getattr(n.func, "attr", "") == "execute_activity"]
    given = {k.arg: ast.unparse(k.value) for k in call.keywords}

    assert ast.unparse(call.args[0]) == "refresh_product_knowledge"
    assert given == {"start_to_close_timeout": "KNOWLEDGE_PASS_CEILING",
                     "heartbeat_timeout": "KNOWLEDGE_PASS_HEARTBEAT", "retry_policy": "_ONCE"}
    assert (wf.KNOWLEDGE_PASS_CEILING, wf.KNOWLEDGE_PASS_HEARTBEAT) == (
        knowledge.PASS_CEILING, knowledge.PASS_HEARTBEAT)


async def test_the_activity_heartbeats_while_the_pass_runs(monkeypatch):
    beats: list[str] = []
    monkeypatch.setattr(acts.activity, "heartbeat", lambda *a: beats.append(a[0] if a else ""))
    monkeypatch.setattr(acts, "_TURN_PULSE", 0.02)

    def _slow(inp):
        time.sleep(0.3)
        return f"refreshed {inp.project}"

    monkeypatch.setattr(acts, "_do_refresh_product_knowledge", _slow)

    said = await acts.refresh_product_knowledge(KnowledgeRefreshInput(project="tidewater"))

    assert said == "refreshed tidewater"
    assert len(beats) >= 3 and all("tidewater" in b for b in beats), beats


# ── the outcome, said by an existing read however the pass ends ─────────────────────────────────

def _ends_refreshed(world):
    return None


def _ends_degraded(world):
    world.boards[world.project.name] = None
    return "the board of tidewater could not be read"


def _ends_failed(world):
    world.raises = RuntimeError("the checkout broke")
    return "the documents could not be read"


def _ends_with_no_context(world):
    world.docs_path = ""
    return "the context repository could not be checked out"


#: How a pass is made to end each way, and the words the read must then say.
_ENDINGS = {knowledge.REFRESHED: _ends_refreshed, knowledge.DEGRADED: _ends_degraded,
            knowledge.FAILED: _ends_failed, knowledge.NO_CONTEXT: _ends_with_no_context}


def test_every_way_a_pass_ends_has_a_case():
    assert set(_ENDINGS) == set(knowledge.OUTCOMES)


@pytest.mark.parametrize("outcome", knowledge.OUTCOMES)
async def test_the_status_says_how_the_last_pass_ended(product, outcome):
    words = _ENDINGS[outcome](product)
    before = datetime.now(UTC).isoformat(timespec="seconds")

    await asyncio.to_thread(acts._do_refresh_product_knowledge, _inp(product))
    product.raises, product.docs_path = None, str(product.tree)
    status = await actions.perform("product_status", by=_admin(), project="tidewater")

    seen = status.data["knowledge"]
    assert seen["outcome"] == outcome and seen["by"] == knowledge.ASKED
    assert seen["finished_at"] >= before and seen["running_since"] is None
    if outcome == knowledge.REFRESHED:
        assert seen["degraded"] == [] and seen["refreshed_at"] == seen["finished_at"]
        assert {"documents", "requirements", "board:tidewater"} <= set(seen["sources"])
    else:
        assert any(words in d for d in seen["degraded"]), seen["degraded"]
    if outcome in (knowledge.FAILED, knowledge.NO_CONTEXT):
        assert seen["refreshed_at"] is None, "a pass that brought nothing up refreshed nothing"


def _left_by_the_budget(world, monkeypatch):
    return {"budget_seconds": -1.0}


def _a_document_busy_with_another_pass(world, monkeypatch):
    from openfactory.product.documents.store import Store
    from openfactory.util.filelock import Waited

    real = Store.version_lock

    class _Held:
        def acquire(self, *, timeout):
            raise Waited("another pass", timeout)

    monkeypatch.setattr(Store, "version_lock", lambda self, path, digest: _Held()
                        if path.startswith("notes/") else real(self, path, digest))
    return {}


def _requirements_unread(world, monkeypatch):
    world.available = False
    return {}


def _a_board_unread(world, monkeypatch):
    world.boards[world.project.name] = None
    return {}


def _an_index_that_breaks(world, monkeypatch):
    def broken(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(retrieval, "sync", broken)
    return {}


def _an_index_held_elsewhere(world, monkeypatch):
    from openfactory.product.index.store import Index
    from openfactory.product.key import product_key
    from openfactory.util.filelock import lock_beside

    path = Index(product_key(world.project)).path
    path.parent.mkdir(parents=True, exist_ok=True)
    held, done = threading.Event(), threading.Event()

    def hold():
        with lock_beside(path).held(timeout=5):
            held.set()
            done.wait(10)

    threading.Thread(target=hold, daemon=True).start()
    assert held.wait(5)
    real = retrieval.sync
    monkeypatch.setattr(retrieval, "sync", lambda index, **k: real(index, **{**k, "wait": 0.05}))
    world.release = done
    return {}


def _records_the_index_cannot_read(world, monkeypatch):
    class _Unreadable:
        def index(self):
            raise OSError("the records' index is damaged")

    real = retrieval.sync
    monkeypatch.setattr(retrieval, "sync",
                        lambda index, **k: real(index, **{**k, "records": _Unreadable()}))
    return {}


def _no_checkout(world, monkeypatch):
    world.docs_path = ""
    return {}


def _a_checkout_that_breaks(world, monkeypatch):
    world.raises = RuntimeError("the checkout broke")
    return {}


def _a_fault_nobody_expected(world, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError("a fault nobody expected")

    monkeypatch.setattr(knowledge, "_boards", broken)
    return {}


class _Stopped(BaseException):
    """What stops a pass without being an `Exception`: a cancellation, an interrupt, an exit."""


def _a_stop(world, monkeypatch):
    def stopped(*_a, **_k):
        raise _Stopped

    monkeypatch.setattr(knowledge, "_boards", stopped)
    return {}


#: EVERY SENTENCE A PASS CAN SAY OF WHAT IT DID NOT BRING UP, made to be said: the words each case
#: must find in `degraded`, how the pass ends, and how the case is made. Held to the code below —
#: every `done.degraded.append` in `refresh.py` is one of these, and each of these is one of them.
_DEGRADATIONS = {
    "were not reached inside the pass's time budget": (knowledge.DEGRADED, _left_by_the_budget),
    "were being read by another pass": (knowledge.DEGRADED, _a_document_busy_with_another_pass),
    "the requirements could not be read": (knowledge.DEGRADED, _requirements_unread),
    "the board of tidewater could not be read": (knowledge.DEGRADED, _a_board_unread),
    "the index could not be brought up to date": (knowledge.DEGRADED, _an_index_that_breaks),
    "another sync of this product held the index": (knowledge.DEGRADED, _an_index_held_elsewhere),
    "the document records could not be read by the index": (knowledge.DEGRADED,
                                                             _records_the_index_cannot_read),
    "the context repository could not be checked out": (knowledge.NO_CONTEXT, _no_checkout),
    "the documents could not be read": (knowledge.FAILED, _a_checkout_that_breaks),
    "the pass failed": (knowledge.FAILED, _a_fault_nobody_expected),
    "the pass was stopped before it ended": (knowledge.FAILED, _a_stop),
}


def _said_by_the_pass() -> list[str]:
    """Every sentence `refresh.py` appends to a pass's `degraded`, read off its syntax tree, a value
    it interpolates written `{}`."""
    out = []
    for node in ast.walk(ast.parse(inspect.getsource(knowledge))):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "append"
                and ast.unparse(node.func.value) == "done.degraded"):
            continue
        (said,) = node.args
        parts = said.values if isinstance(said, ast.JoinedStr) else [said]
        out.append("".join(p.value if isinstance(p, ast.Constant) else "{}" for p in parts))
    return out


def test_every_sentence_a_pass_can_say_has_a_case_that_makes_it_say_it():
    said = _said_by_the_pass()
    assert len(said) >= 10, said  # a derivation that broke finds nothing, and nothing is uncovered
    for sentence in said:
        cases = [words for words in _DEGRADATIONS if words.replace("tidewater", "{}") in sentence]
        assert len(cases) == 1, (sentence, cases)
    assert len(_DEGRADATIONS) == len(said)


@pytest.mark.parametrize("words", sorted(_DEGRADATIONS))
def test_a_pass_that_did_not_bring_everything_up_says_what_and_why(product, monkeypatch, words):
    outcome, make = _DEGRADATIONS[words]
    options = make(product, monkeypatch)
    try:
        done = knowledge.documents_and_index(product.project, by=knowledge.ASKED, boards=True,
                                             **{"budget_seconds": BUDGET, **options})
    except _Stopped:
        done = None
    finally:
        if getattr(product, "release", None) is not None:
            product.release.set()

    seen = knowledge.state(product.project)
    assert seen["outcome"] == outcome and (done is None or done.outcome == outcome)
    assert any(words in d for d in seen["degraded"]), seen["degraded"]
    if outcome == knowledge.DEGRADED:
        assert seen["refreshed_at"] == seen["finished_at"], "a partial refresh is still a refresh"
    else:
        assert seen["refreshed_at"] is None, "a pass that brought nothing up refreshed nothing"


def test_a_pass_running_now_is_said_with_when_it_started(product, monkeypatch):
    seen: list[dict] = []
    real = knowledge._run

    def watched(project, done, **k):
        seen.append(knowledge.state(project))
        return real(project, done, **k)

    monkeypatch.setattr(knowledge, "_run", watched)
    done = knowledge.documents_and_index(product.project, by=knowledge.ASKED,
                                         budget_seconds=BUDGET, boards=True)

    assert seen[0]["running_since"] == done.started_at
    assert knowledge.state(product.project)["running_since"] is None


def test_a_pass_whose_worker_died_is_said_to_have_stopped_once_it_outlived_its_ceiling(
        product, monkeypatch):
    knowledge.documents_and_index(product.project, by=knowledge.SCHEDULE, budget_seconds=BUDGET)

    def dies(*_a, **_k):
        raise SystemExit("the worker was killed")  # BaseException: no `except Exception` sees it

    monkeypatch.setattr(knowledge, "_ended", lambda *_a, **_k: None)
    monkeypatch.setattr(knowledge, "_run", dies)
    with pytest.raises(SystemExit):
        knowledge.documents_and_index(product.project, by=knowledge.ASKED, budget_seconds=BUDGET)

    soon = knowledge.state(product.project)
    later = knowledge.state(product.project,
                            now=datetime.now(UTC) + knowledge.STOPPED_AFTER + timedelta(seconds=5))

    assert soon["running_since"] is not None and soon["outcome"] == knowledge.REFRESHED
    assert later["running_since"] is None and later["outcome"] == knowledge.FAILED
    assert later["by"] == knowledge.ASKED
    assert any("never finished" in d for d in later["degraded"]), later
    assert later["refreshed_at"] == soon["refreshed_at"], "the last refresh is still when it was"


def test_a_record_that_cannot_be_read_is_unknown_never_never(product):
    path = knowledge.record_path(product.project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ half a record", encoding="utf-8")

    seen = knowledge.state(product.project)

    assert seen["outcome"] is None and seen["refreshed_at"] is None
    assert any("unknown, not never" in d for d in seen["degraded"]), seen

    done = knowledge.documents_and_index(product.project, by=knowledge.ASKED,
                                         budget_seconds=BUDGET, boards=True)
    assert knowledge.state(product.project)["finished_at"] == done.finished_at


def test_the_schedule_s_pass_is_recorded_too(product):
    acts._do_ingest_documents(_inp(product))

    seen = knowledge.state(product.project)

    assert seen["by"] == knowledge.SCHEDULE and seen["outcome"] == knowledge.REFRESHED
    assert not any(s.startswith("board:") for s in seen["sources"])


# ── the durable engine itself: one flight, and the answers come back before the pass ends ───────

@pytest.mark.owns_its_engine
async def test_on_the_engine_two_asks_at_once_run_one_pass_and_both_answer_before_it_ends(
        product, monkeypatch, tmp_path):
    from temporalio.contrib.pydantic import pydantic_data_converter
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    from openfactory.registry import ProjectRegistry
    from openfactory.runtime.temporal import TASK_QUEUE
    from openfactory.runtime.temporal.workflow import ProductKnowledgeRefreshWorkflow

    ProjectRegistry().add(bed.project(tmp_path, name="ledger"))
    entered, release = threading.Event(), threading.Event()
    runs: list[str] = []

    def _held(inp):
        runs.append(inp.project)
        entered.set()
        release.wait(30)
        return "refreshed"

    monkeypatch.setattr(acts, "_do_refresh_product_knowledge", _held)
    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)

    async def _connected():
        return env.client, None

    monkeypatch.setattr(catalog, "_connected", _connected)
    try:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[ProductKnowledgeRefreshWorkflow],
                              activities=[acts.refresh_product_knowledge]):
                first, second = await asyncio.wait_for(asyncio.gather(
                    actions.perform("product_refresh", by=_admin(), project="tidewater"),
                    actions.perform("product_refresh", by=_admin(), project="ledger")), 20)
                assert sorted([first.data["refresh"], second.data["refresh"]]) == [
                    knowledge.JOINED, knowledge.STARTED], (first, second)
                assert await asyncio.to_thread(entered.wait, 20), "the pass never started"
                assert not release.is_set(), "an answer waited for the pass"
                release.set()
                flight = env.client.get_workflow_handle(knowledge.workflow_id(product.project))
                assert await asyncio.wait_for(flight.result(), 20) == "refreshed"

                again = await actions.perform("product_refresh", by=_admin(), project="ledger")
                assert again.data["refresh"] == knowledge.STARTED
                await asyncio.wait_for(env.client.get_workflow_handle(
                    knowledge.workflow_id(product.project)).result(), 20)
    finally:
        release.set()
        await env.shutdown()

    assert len(runs) == 2, runs
