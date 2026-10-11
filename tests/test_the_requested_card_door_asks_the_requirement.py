"""The requested-card door asks the requirement a card names before it files it (#563, ADR-0051
D18, slice 18c).

WHAT WAS MEASURED. On a live run (v0.5.0-rc.1) one requirement got three cards through three doors
in seven minutes. The conversation's requested card carried `(REQ-0066)` in its title and "the
first two bullets of REQ-0066" in its body; `file_ticket` checked it by title alone, wrote it as
having no requirement behind it, and filed it beside the breakdown's two cards for the same scope.

THE RULE THIS FILE HOLDS (D18 item 4): the work of an accepted requirement is filed by its
breakdown alone. A requested card that names one is never filed; the sentence says what the
requirement already has — a breakdown running, the open cards that execute it, or neither, and
then the breakdown is offered. A card naming no requirement, or one that is not a promise, is
free-standing by what it says, and is filed as before. Read from the card's own text, no model.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from openfactory.product import breaking
from openfactory.product.module import ProductModule, _requirements_named
from openfactory.product.voice import ticket_held_for_its_requirement
from tests.test_the_product_owner_opens_a_card_as_described import _Board, _module, _Tracker

#: The run's card, as the role wrote it: the requirement in its title and in its body. REQ-0006 is
#: the fixture corpus's accepted requirement.
RUN_TITLE = "Gerar o pacote de fecho (REQ-0006)"
RUN_BODY = "Isto cobre os dois primeiros itens do REQ-0006: o pacote e o resumo."


def _card(ref: str, *, executes: int | None = None, state: str = "open"):
    body = f"## Objective\n\nalgo\n\n## Source\n\nExecutes REQ-{executes:04d}\n" if executes else ""
    return SimpleNamespace(number=ref, title=f"card {ref}", body=body, state=state, column="Backlog")


@pytest.fixture
def held(monkeypatch):
    """The engine's answer about a running breakdown, and the board the module reads."""
    seen = SimpleNamespace(running=False, board=[], board_error="", asked=[])

    def _running(project, number):
        seen.asked.append(number)
        if isinstance(seen.running, Exception):
            raise seen.running
        return seen.running

    monkeypatch.setattr(breaking, "running_now", _running)
    monkeypatch.setattr(ProductModule, "_read_board",
                        lambda self, **_: (seen.board, seen.board_error))
    return seen


def _file(tmp_path, *, title=RUN_TITLE, described=RUN_BODY):
    tracker = _Tracker()
    result = _module(tmp_path, tracker).file_ticket(
        title=title, described=described, reported_by="<@U1>", tracker=tracker, board=_Board())
    return result, tracker


# ── the run ─────────────────────────────────────────────────────────────────────────────────────

def test_TODAYS_RUN_the_requested_card_for_an_agreed_requirement_is_not_filed(tmp_path, held):
    """Neither running nor carded: the breakdown is offered — one request away, in whatever words,
    for the person to confirm (#565 slice c: the role proposes it, no sentence is copied)."""
    result, tracker = _file(tmp_path)

    assert not result.ok and tracker.created == [], "the run's third card was filed"
    assert "requisito 6" in result.detail and "acordado" in result.detail, result.detail
    assert "me peça para quebrá-lo" in result.detail and "confirmar" in result.detail, result.detail
    assert "«" not in result.detail, "a sentence to copy is offered again"


def test_a_breakdown_running_holds_it_and_says_so(tmp_path, held):
    held.running = True

    result, tracker = _file(tmp_path)

    assert not result.ok and tracker.created == []
    assert "sendo quebrado em tarefas agora" in result.detail, result.detail
    assert held.asked == [6]


def test_the_cards_that_execute_it_are_listed(tmp_path, held):
    held.board = [_card("41", executes=6), _card("42", executes=6), _card("43", executes=9),
                  _card("44", executes=6, state="closed"), _card("45")]

    result, tracker = _file(tmp_path)

    assert not result.ok and tracker.created == []
    assert "#41, #42" in result.detail, result.detail
    for other in ("#43", "#44", "#45"):
        assert other not in result.detail, (other, result.detail)


def test_named_in_the_body_alone_is_named(tmp_path, held):
    result, tracker = _file(tmp_path, title="Gerar o pacote de fecho")

    assert not result.ok and tracker.created == [], result.detail


def test_an_engine_that_cannot_be_asked_still_holds_it(tmp_path, held, caplog):
    held.running = ConnectionError("no engine")
    held.board = [_card("41", executes=6)]

    with caplog.at_level("WARNING"):
        result, tracker = _file(tmp_path)

    assert not result.ok and tracker.created == [] and "#41" in result.detail, result.detail
    assert "could not ask the engine" in caplog.text


# ── what is still filed as before ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("title", "described"), [
    ("Exportar CSV", "o relatório mensal em CSV"),                 # names no requirement
    ("Fecho no dia 5 (REQ-0009)", "conforme o REQ-0009"),          # proposed, not a promise
    ("Conferência antiga (REQ-0004)", "o REQ-0004"),               # superseded
    ("Sem requisito", "revisar os 66 testes de fumaça"),           # a number is not a requirement
])
def test_a_card_that_names_no_agreed_requirement_is_filed_as_before(tmp_path, held, title,
                                                                     described):
    result, tracker = _file(tmp_path, title=title, described=described)

    assert result.ok and len(tracker.created) == 1, result.detail
    assert held.asked == [], "the engine was asked about a card that names no agreed requirement"


# ── the parts ───────────────────────────────────────────────────────────────────────────────────

def test_a_requirement_is_named_as_the_role_writes_it():
    assert _requirements_named("x (REQ-0066) y REQ-66, req 7 e REQ#8; REQ-0066 de novo") == [
        66, 7, 8]
    assert _requirements_named("os 66 testes, o requisito 66") == []


@pytest.mark.parametrize("language", ["pt-BR", "en"])
def test_each_sentence_holds_in_both_languages(language):
    offer = ticket_held_for_its_requirement(number=6, language=language)
    running = ticket_held_for_its_requirement(number=6, running=True, language=language)
    carded = ticket_held_for_its_requirement(number=6, cards=["#41"], language=language)

    assert len({offer, running, carded}) == 3
    assert "#41" in carded and all("6" in said for said in (offer, running, carded))


def test_the_conversation_is_told_why_nothing_was_opened(tmp_path, held):
    """Through the yes the person gave the card (`confirm._confirm_ticket`): the held sentence is
    what they read, never "opened"."""
    from openfactory.product.confirm import _confirm_ticket

    tracker = _Tracker()
    module = _module(tmp_path, tracker)

    said = _confirm_ticket(module.project, {"title": RUN_TITLE, "described": RUN_BODY,
                                            "reported_by": "<@U1>"},
                           module=module, user="U1", lang="pt-BR")

    assert said.startswith("Não abri esse card: ele é do *requisito 6*"), said
    assert tracker.created == []
