"""An open card is found by its words, with its body, as a closed one is (#567, second slice).

THE RUN (v0.5.0-rc.1). The role advised closing #1000009 "or" #1000010 as if the two were equal.
#1000009 was the only card carrying the requirement's first front; #1000010's body opened with
"building on the per-version storage introduced for REQ-0066". The role said #1000010 "covers only
listing, opening and downloading past versions" — its title, paraphrased — because the board it is
handed carries a number, a state and a title, and the product's memory indexed closed cards only:
"an open one is the board's business".

Now an open card is indexed with its body, marked open as the board showed it when last read, and
a card that opens or closes since is replaced, its state with it. The search before the turn and
`[[BUSCA` reach the cards a question is about.
"""

from __future__ import annotations

from openfactory.contracts.document import CLIENT
from openfactory.product.index.items import CLOSED, OPEN, from_card
from openfactory.product.index.retrieval import render
from openfactory.product.index.search import Query, search
from openfactory.product.index.store import Index
from openfactory.product.index.sync import sync
from openfactory.product.key import product_key
from openfactory.product.triage import Ticket
from tests import index_bed as bed

KEEP = Ticket(number="1000009", title="Guardar cada versão entregue", state="open",
              updated_at="2026-10-01T16:30:00Z",
              body="## Acceptance criteria\n\n- Each delivered version is kept instead of "
                   "deleted\n")
LIST = Ticket(number="1000010", title="Listar, abrir e baixar versões passadas", state="open",
              updated_at="2026-10-01T16:31:00Z",
              body="Building on the per-version storage introduced for REQ-0066.\n\n"
                   "## Acceptance criteria\n\n- Past versions are listed, newest first\n")


def _index(tmp_path, *cards):
    project = bed.project(tmp_path)
    index = Index(product_key(project))
    sync(index, cards=list(cards), member=project.name)
    return project, index


def _status(index, grp: str) -> str | None:
    with index.open() as con:
        row = con.execute("SELECT status FROM items WHERE grp = ?", (grp,)).fetchone()
    return row[0] if row else None


# ── the item ────────────────────────────────────────────────────────────────────────────────────

def test_an_open_card_is_an_item_with_its_body_marked_open():
    [item] = from_card(LIST, product="p", member="m")

    assert item.status == OPEN
    assert "per-version storage introduced for REQ-0066" in item.text
    assert item.requirements == (66,) and item.cards == ("1000010",)
    assert "open" in item.origin and "closed" not in item.origin


def test_a_closed_card_is_still_an_item_marked_closed():
    done = LIST.model_copy(update={"state": "closed", "state_reason": "completed"})

    [item] = from_card(done, product="p", member="m")

    assert item.status == CLOSED and item.origin == "the board — closed as delivered"


# ── the sync ────────────────────────────────────────────────────────────────────────────────────

def test_TODAYS_RUN_both_open_cards_are_in_the_index(tmp_path):
    project, index = _index(tmp_path, KEEP, LIST)

    for card in (KEEP, LIST):
        assert _status(index, f"card:{project.name}:{card.number}") == OPEN, card.number


def test_a_card_that_closes_is_replaced_closed_and_one_that_reopens_is_kept_open(tmp_path):
    project, index = _index(tmp_path, KEEP)
    grp = f"card:{project.name}:{KEEP.number}"

    sync(index, cards=[KEEP.model_copy(update={"state": "closed", "state_reason": "completed"})],
         member=project.name)
    assert _status(index, grp) == CLOSED

    sync(index, cards=[KEEP], member=project.name)
    assert _status(index, grp) == OPEN, "a reopened card left the index"


# ── the search ──────────────────────────────────────────────────────────────────────────────────

def test_TODAYS_RUN_a_question_about_two_open_cards_finds_both_bodies(tmp_path):
    _project, index = _index(tmp_path, KEEP, LIST)

    found = search(index, Query(text="o #1000009 e o #1000010 se sobrepõem?", audience=CLIENT))

    assert {"1000009", "1000010"} <= {c for h in found.hits for c in h.cards}, [
        h.grp for h in found.hits]
    said = render(found, heading="this message")
    assert "Building on the per-version storage introduced for REQ-0066" in said, said
    assert "Each delivered version is kept instead of deleted" in said, said


def test_an_open_card_is_shown_to_the_role_as_open_and_where_it_stands_is_the_boards(tmp_path):
    _project, index = _index(tmp_path, LIST)

    said = render(search(index, Query(text="#1000010", audience=CLIENT)), heading="this message")

    assert "an open card, as the board showed it when last read" in said, said
    assert "`board.md`" in said, said
