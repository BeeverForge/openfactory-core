"""The address decides the surface, not the credential (#562, the default front end's half).

Every address returned the same page, which asked `/api/whoami` and drew the floor or the product
owner's page by the credential: a product credential at `/p/<project>/board` was rewritten to
`/product/<project>`, and a credential for the board opening `/product/<project>` got the product
page, its chat socket and a column of 403s. Decided for 0.6.0 and refined on 2026-10-11:

  - `/p/<project>/board` is the board; the product owner reaches it with the credential they hold,
    READ ONLY — no new card, nothing moves, and a card opens on their own page, where what they may
    do to it is (the link the role sends, which their boot already reads, #444);
  - `/product/<project>` is the product owner's surface, and a board credential is refused it by
    name, before anything on it is asked;
  - the administrator's credential reaches both, by address;
  - the product owner's Board tab links to the whole board.

Run under node on the page's own functions, with the harness of
`tests/test_a_refusal_is_not_an_answer.py`.
"""

from __future__ import annotations

import json

import pytest

from tests.test_a_refusal_is_not_an_answer import ANA, BIA, BOOT, CODE, run

LEO = {"id": "leo", "display": "Leo", "known": True, "scopes": ["floor"], "logout": "/auth/logout"}


def _boot(who: dict, path: str) -> dict:
    return run(f"location.pathname={json.dumps(path)};"
               f"routes={{'/api/whoami':[{{status:200,body:{json.dumps(who)}}}],"
               "'/api/projects':[{status:200,body:[]}]};await boot();"
               "return {order,_surface}", "boot", "loadProjects", stubs=BOOT)


# ── the boot ────────────────────────────────────────────────────────────────────────────────────

def test_TODAYS_RULE_the_product_owner_at_the_board_address_gets_the_board():
    assert _boot(BIA, "/p/acme/board")["order"] == ["board:acme"]


@pytest.mark.parametrize("path", ["/p/acme/card/7", "/p/acme/preview/7", "/product/acme"])
def test_a_card_or_preview_link_and_the_product_page_stay_the_product_owners(path):
    got = _boot(BIA, path)

    assert len(got["order"]) == 1 and got["order"][0].startswith("product:"), got


def test_TODAYS_RULE_the_board_credential_is_refused_the_product_owners_page():
    assert _boot(LEO, "/product/acme")["order"] == ["refused:acme"]


def test_the_board_credential_and_the_administrator_get_the_floor_at_the_board_address():
    for who in (LEO, ANA):
        got = _boot(who, "/p/acme/board")
        assert got["order"] == [] and got["_surface"] == "floor", (who["id"], got)


def test_the_administrator_reaches_the_product_owners_page_by_address():
    got = _boot(ANA, "/product/acme")

    assert len(got["order"]) == 1 and got["order"][0].startswith("product:"), got


# ── the product owner's read of the board ───────────────────────────────────────────────────────

def test_the_read_only_board_starts_no_clock_and_reads_nothing_of_the_floor():
    got = run("nodes['#app']=node();nodes['#floor']=node();nodes['#costs']=node();"
              "nodes['#board']=node();await bootBoardRead('acme');"
              "return {opened,calls,_surface,_boardReadOnly,"
              "hidden:['#floor','#costs','#board'].map(s=>nodes[s].style.display)}",
              "bootBoardRead", stubs="let opened=[];async function openBoard(n){opened.push(n)}")

    assert got["opened"] == ["acme"] and got["calls"] == [], got
    assert got["_surface"] == "product" and got["_boardReadOnly"] is True, got
    assert got["hidden"] == ["none", "none", "none"], got


_BOARD = ("let _bd={project:'acme',data:{columns:['Backlog','Done'],"
          "cards:[{ref:'7',title:'Versions',column:'Backlog',labels:[]}]}};"
          "function _bplace(){}function _breplace(){}function _bwire(){}"
          "function _bmeta(){return{pickup:false,tone:'',note:''}}")


def test_the_read_only_board_offers_no_new_card_and_drags_nothing():
    read = run("_boardReadOnly=true;nodes['#boardview']=node();paintBoard();"
               "return nodes['#boardview'].innerHTML", "paintBoard", "_bcard", stubs=_BOARD)
    full = run("nodes['#boardview']=node();paintBoard();return nodes['#boardview'].innerHTML",
               "paintBoard", "_bcard", stubs=_BOARD)

    assert "read only" in read and 'href="/product/acme"' in read, read
    assert "boardNewCard" not in read and 'draggable="false"' in read, read
    assert "boardNewCard" in full and 'draggable="true"' in full, "the floor's board lost a verb"


def test_a_card_on_the_read_only_board_opens_on_the_product_owners_page():
    got = run("_boardReadOnly=true;_bwire();listeners.click[0]();"
              "return {events:Object.keys(listeners).sort(),href:location.href}", "_bwire",
              stubs="const listeners={};let _bd={project:'acme'};"
                    "const k={dataset:{ref:'7'},classList:{add(){},remove(){}},"
                    "addEventListener:(e,f)=>{(listeners[e]=listeners[e]||[]).push(f)}};"
                    "nodes['#boardview']={querySelectorAll:s=>s==='.k'?[k]:[]};")

    assert got["events"] == ["click", "keydown"], "a card on the read-only board can be dragged"
    assert got["href"] == "/p/acme/card/7", got


# ── the refusal, and the way to the board ───────────────────────────────────────────────────────

def test_the_refusal_names_the_credential_and_the_board_it_may_open():
    got = run("nodes['#app']=node();nodes['#floor']=node();nodes['#costs']=node();"
              "nodes['#board']=node();refuseTheProductPage('acme');"
              "return {html:nodes['#app'].innerHTML,calls,_surface,"
              "hidden:['#floor','#costs','#board'].map(s=>nodes[s].style.display)}",
              "refuseTheProductPage", stubs="function movedNotice(){return ''}")

    assert "credential is for the board" in got["html"], got["html"]
    assert 'href="/p/acme/board"' in got["html"] and got["calls"] == [], got
    assert got["_surface"] == "refused"
    assert got["hidden"] == ["none", "none", "none"], "the floor's banner waits for a read never made"


def test_the_product_owners_board_tab_links_to_the_whole_board():
    render = CODE[CODE.index("function renderProduct("):CODE.index("function renderProduct(") + 9000]

    assert 'id="pbWhole" href="/p/${encodeURIComponent(name)}/board"' in render
