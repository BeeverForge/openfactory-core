"""The product owner puts a card in the queue from their own page (#562).

WHAT WAS MISSING. Since #562 the product owner reads the board, and a card they open there lands on
their own page — where it could be closed or removed, and not started. Starting was only a yes to a
queue proposal in a conversation, though the row that yes reaches (`product_promote`) has been on
the product scope all along, gated by `promote` itself. The product owner is the person who says
what the factory does next, and the card was the one place they could not say it.

WHAT IS PROVEN HERE:

  · an approver opening a card nobody started is offered "Queue it", in the board's own name for
    the queue; pressing it puts the card in the queue, and the card no longer offers it;
  · a person who may not start work is told who can and gets no button — and the row refuses them
    whatever the page draws: the view asks the same `may_act` the row does;
  · a card in the queue, taken up, or closed offers nothing; the KEY decides, never the name;
  · the page asks before it spends, sends the row with `yes`, says the row's own sentence on the
    card, and draws only what the server offered; the floor's drawer is unchanged.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

#: The product admin, and the person who asked for the card (no approver).
ADMIN, ASKER = "po-admin-12", "ana-asked-77"


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    """A registered local project with a product role, whose board `project init` created."""
    monkeypatch.setenv("OPENFACTORY_BOARD_DB", str(tmp_path / "board.db"))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_LOG_DIR", str(tmp_path / "logs"))
    from openfactory.adapters.board_setup.local import LocalBoardSetup
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.product.board import forget_board
    from openfactory.registry import ProjectRegistry

    registry = ProjectRegistry()
    registry.add(Project(name="acme", repo_path=str(tmp_path), language="en",
                         tracker=ProviderRef(kind="local", repo="acme", options={}),
                         product=ProductConfig(docs_repo="acme/docs", admins=[ADMIN])))
    project = registry.get("acme")
    LocalBoardSetup().create(project=project, owner="", title="acme", token=None)
    forget_board()
    yield project
    forget_board()


@pytest.fixture
def tracker(deployment):
    from openfactory.adapters.tracker.registry import build_tracker

    return build_tracker(deployment)


@pytest.fixture
def board(deployment):
    from openfactory.adapters.board import build_board

    return build_board(deployment)


def _card(tracker, board, *, column: str = "Backlog") -> str:
    from openfactory.product.authoring import ticket_body

    ref = tracker.create_ticket(title="A monthly report",
                                body=ticket_body(described="um relatório mensal",
                                                 reported_by=ASKER, source="chat"),
                                requester=ASKER)
    board.set_column(issue=ref, issue_url="", name=column)
    return ref


def _act(name: str, *, who: str, **params):
    """One action row, driven as the product page drives it: a product credential, which the panel
    makes an admin OF THE PRODUCT AREA (`app._actor_of`) — who may start work is then the product
    role's own allowlist, asked by `promote`."""
    from openfactory import actions
    from openfactory.policy.authz import PRODUCT

    by = actions.Actor(id=who, display=who, via="panel", admin=True, scopes=frozenset({PRODUCT}))
    return asyncio.run(actions.perform(name, by=by, **params))


def _opened(who: str, ref: str) -> dict:
    out = _act("product_board", who=who, project="acme", card=ref)
    assert out.ok, out.message
    return out.data["card"]


def _column(board, ref: str) -> str:
    from openfactory.contracts.refs import canonical_ref

    return (board.columns() or {}).get(canonical_ref(ref), "")


# ── the row: offered where it would act, and acting ─────────────────────────────────────────────

def test_an_approver_opening_a_backlog_card_is_offered_the_queue_in_the_boards_words(
        deployment, tracker, board):
    ref = _card(tracker, board)

    queue = _opened(ADMIN, ref)["queue"]

    assert queue["offered"] is True, queue
    assert queue["words"]["queue"] == "Queue it (TO-DO)", queue
    assert "spends money" in queue["words"]["ask"] and f"#{ref.lstrip('#')}" in (
        queue["words"]["ask"]), queue


def test_the_press_puts_the_card_in_the_queue_and_the_card_no_longer_offers_it(
        deployment, tracker, board):
    ref = _card(tracker, board)

    out = _act("product_promote", who=ADMIN, project="acme", numbers=[ref.lstrip("#")], yes=True)

    assert out.ok, out.message
    assert _column(board, ref) == "TO-DO", board.columns()
    assert _opened(ADMIN, ref)["queue"] == {"offered": False}, (
        "a card already in the queue still offers to be queued")


def test_a_person_who_may_not_start_work_is_told_who_can_and_the_row_refuses_them(
        deployment, tracker, board):
    ref = _card(tracker, board)

    queue = _opened(ASKER, ref)["queue"]
    out = _act("product_promote", who=ASKER, project="acme", numbers=[ref.lstrip("#")], yes=True)

    assert queue["offered"] is False and "words" not in queue, queue
    assert "approver's yes" in queue["note"] and "TO-DO" in queue["note"], queue
    assert not out.ok and _column(board, ref) == "Backlog", (out.message, board.columns())


@pytest.mark.parametrize("column", ["In progress", "In review", "Needs Action"])
def test_a_card_the_factory_took_up_offers_nothing(deployment, tracker, board, column):
    ref = _card(tracker, board, column=column)

    assert "queue" not in _opened(ADMIN, ref)


def test_a_closed_card_offers_nothing(deployment, tracker, board, monkeypatch):
    from openfactory.product import events

    monkeypatch.setattr(events, "_tell", lambda project, **kw: True)
    ref = _card(tracker, board)
    closed = _act("product_withdraw_card", who=ASKER, project="acme", number=ref,
                  reason="filed twice")
    assert closed.ok, closed.message

    view = _opened(ADMIN, ref)

    assert view["readable"] and not view["open"] and "queue" not in view, view


# ── the module: the key decides, and the board names the queue ──────────────────────────────────

#: A client's board that renamed both of the operator's columns.
RENAMED = SimpleNamespace(
    stage_key=lambda name: {"Pendências": "backlog", "A Fazer": "todo"}.get(name, ""),
    stage_column=lambda key: {"backlog": "Pendências", "todo": "A Fazer"}.get(key, ""))


def _module(project, language: str = "pt-BR"):
    from openfactory.product.module import ProductModule

    return ProductModule(project.model_copy(update={"language": language}), via="panel")


def test_the_queue_is_named_as_the_board_names_it_in_the_projects_language(deployment):
    view = _module(deployment).queue_view("7", actor=ADMIN, column="Pendências", board=RENAMED)

    assert view == {"offered": True, "words": {
        "queue": "Pôr na fila (A Fazer)",
        "ask": ("Pôr o #7 em A Fazer começa o trabalho: a fábrica o pega de lá, e a partir daí "
                "isso custa dinheiro. Pôr na fila?")}}, view


def test_the_key_decides_never_the_name(deployment):
    """`A Fazer` is this board's queue: a card there is queued, though no column is called TO-DO;
    and a column nobody maps is not called the queue for sounding like one."""
    module = _module(deployment)

    assert module.queue_view("7", actor=ADMIN, column="A Fazer", board=RENAMED) == {
        "offered": False}
    assert module.queue_view("7", actor=ADMIN, column="TO-DO", board=RENAMED)["offered"] is True


def test_a_person_who_may_not_start_work_is_told_in_the_projects_language(deployment):
    view = _module(deployment).queue_view("7", actor=ASKER, column="Pendências", board=RENAMED)

    assert view == {"offered": False, "note": (
        "Pôr o #7 em A Fazer começa o trabalho, e isso custa dinheiro — é um sim de quem aprova. "
        "Peça a uma dessas pessoas, ou diga na conversa.")}, view


# ── the page: asks before it spends, says the row's sentence, draws what the server offered ─────

WORDS = {"close": "Close card", "remove": "Remove from the board", "confirm": "Confirm",
         "cancel": "Cancel", "reason": "Why?", "ask_close": "c", "ask_remove": "r", "note": "n"}
OFFERED = {"offered": True, "words": {"queue": "Queue it (TO-DO)",
                                      "ask": "Putting #7 in TO-DO starts the work."}}


def _drive(scenario: str, *, queue: dict, confirmed: bool = True, answer: dict | None = None):
    from tests.test_a_refusal_is_not_an_answer import run

    card = {"ref": "7", "readable": True, "title": "A monthly report", "body": "asked",
            "state": "open", "column": "Backlog", "opened_by_product": "request",
            "started": False, "removes": True, "words": WORDS, "queue": queue}
    answer = answer or {"ok": True, "message": "started 1 of 1: #7."}
    stubs = ("let _prod={project:'acme'},_bd={};"
             "let _pv={board:undefined,boardMsg:'',card:null,ask:null,said:null,adjusting:null};"
             f"const CARD={json.dumps(card)};const acts=[],asked=[];"
             f"function confirm(q){{asked.push(q);return {json.dumps(confirmed)}}}"
             "async function act(name,params){acts.push([name,params]);"
             "if(name==='product_promote'){"
             f"const a={json.dumps(answer)};if(a.ok){{CARD.column='TO-DO';"
             "CARD.queue={offered:false}}return {ok:a.ok,message:a.message,data:{}}}"
             # a copy, as a response is: the card on the page changes only when it is read again
             "return {ok:true,message:'',data:{cards:[{ref:'7',title:CARD.title,"
             "column:CARD.column}],card:params.card?JSON.parse(JSON.stringify(CARD)):null}}}")
    return run("nodes['#pvBoard']=node();await pvCardOpen('7');"
               "const opened=nodes['#pvBoard'].innerHTML;" + scenario,
               "pvCardOpen", "pvCardRead", "paintPvBoard", "_bcontrols", "pvAdjustBlock",
               "pvAcceptBlock", "pvQueueBlock", "pvQueueSend", stubs=stubs)


def test_the_page_asks_before_it_spends_sends_the_row_with_yes_and_says_its_sentence():
    got = _drive("await pvQueueSend();"
                 "return {opened,after:nodes['#pvBoard'].innerHTML,acts,asked}", queue=OFFERED)

    assert "Queue it (TO-DO)" in got["opened"], got["opened"]
    assert got["asked"] == ["Putting #7 in TO-DO starts the work."], got["asked"]
    assert ["product_promote", {"project": "acme", "numbers": ["7"], "yes": True}] in (
        got["acts"]), got["acts"]
    assert "started 1 of 1: #7." in got["after"], "the row's answer did not stay on the card"
    assert "Queue it" not in got["after"], (
        "the server no longer offers it, and the page still draws the button")


def test_a_question_declined_spends_nothing():
    got = _drive("await pvQueueSend();return {acts}", queue=OFFERED, confirmed=False)

    assert not [a for a in got["acts"] if a[0] == "product_promote"], got["acts"]


def test_a_refusal_is_said_on_the_card_as_the_row_said_it():
    got = _drive("await pvQueueSend();return {after:nodes['#pvBoard'].innerHTML}", queue=OFFERED,
                 answer={"ok": False, "message": "only an approver can start work."})

    assert 'class="pv-note err"' in got["after"], got["after"]
    assert "only an approver can start work." in got["after"], got["after"]


def test_the_page_draws_only_what_the_server_offered():
    note = _drive("return {opened}", queue={"offered": False, "note": "Ask an approver."})
    nothing = _drive("return {opened}", queue={"offered": False})

    assert "Ask an approver." in note["opened"] and "pvQueueSend" not in note["opened"], note
    assert "data-queue" not in nothing["opened"], nothing


def test_the_floors_drawer_is_unchanged():
    from tests.test_a_refusal_is_not_an_answer import run

    card = {"ref": "7", "readable": True, "state": "open", "started": False,
            "opened_by_product": "", "words": WORDS, "queue": OFFERED}
    got = run(f"return {{html:_bcontrols({json.dumps(card)},'board')}}", "_bcontrols",
              "pvQueueBlock", stubs="let _bd={ask:null},_pv={ask:null};")

    assert "Queue it" not in got["html"] and "pvQueueSend" not in got["html"], got["html"]
