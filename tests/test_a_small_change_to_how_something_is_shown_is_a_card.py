"""A small change to how something already built is shown or worded is a card the person asked for.

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640 row C-01, #669). The owner wrote "Na tela de
reservas a data aparece como 2026-11-03. Aqui a gente lê dd/mm/aaaa … Dá pra corrigir?". The role
found the line that prints the date, then proposed a REQUIREMENT. On the yes it wrote REQ-0003 as
`proposed` and filed no card. To get the fix built, the owner had to come back, say the requirement
was agreed, confirm again, and wait for a breakdown. The role followed its prompt: a request is
"a change … argued into a requirement", the malfunction list has no wrong format, and a card is
only for "abre um ticket" in so many words.

THE RULE THIS FILE HOLDS:
  1. the line is drawn once, `role.SHOWN_OR_WORDED`: a small change to how something the product
     already does is shown or worded, which contradicts no agreed requirement. The card
     instruction takes it, and the requirement instruction leaves it out and points at the card.
     No other instruction mentions it, so both sides of the line read the same words;
  2. the platform stages what the role's markers say, read by the parser the turn uses. A card
     the person asked for is staged as a card, and a reply that carries both a request and a card
     stages the card: the person asked for that, and it reaches the board on one yes.

What the model now chooses for C-01 is a judgement a test without a model cannot show; #683 and the
journey's rerun read it with a real one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import openfactory.product.channel as pc
from openfactory.product.role import REQUEST_MARKER, SHOWN_OR_WORDED, read_answer
from tests.test_a_plain_card_reaches_the_person_who_asked import ANA, ANAS, _pen
from tests.test_a_plain_card_reaches_the_person_who_asked import (
    project as project,  # noqa: F401 — the fixture, reused
)
from tests.test_product_role import _call, _role
from tests.the_chat_turn import chat_turn

C_01 = ("Na tela de reservas a data aparece como 2026-11-03. Aqui a gente lê dd/mm/aaaa, tipo "
        "03/11/2026. Dá pra corrigir?")
TITLE = "Data das reservas no formato dd/mm/aaaa"
SAID = ("A tela mostra a data como ela chega do sistema (`reservas_web/pages.py:13`). Dá para "
        "mostrar no formato dd/mm/aaaa.")


def _instructions() -> list[str]:
    """The answer prompt as the model reads it, one paragraph per instruction."""
    role, harness = _role()
    _call(role, "answer", question=C_01)
    return harness.prompts[0].split("\n\n")


def _the(marker: str) -> str:
    [found] = [p for p in _instructions() if marker in p][:1]
    return found


# ── 1. the line is drawn once, and both sides read it ─────────────────────────────────────────

def test_TODAYS_RUN_the_card_instruction_takes_a_small_change_to_how_something_is_shown():
    assert SHOWN_OR_WORDED in _the("[[TICKET:"), (
        "a date format asked to be fixed is not one of the things the card instruction names")


def test_the_requirement_instruction_leaves_it_out_and_points_at_the_card():
    request = _the(REQUEST_MARKER)

    assert SHOWN_OR_WORDED in request, "the requirement instruction still takes every change"
    assert "card" in request[request.index(SHOWN_OR_WORDED):].lower(), (
        "the requirement instruction leaves the change out without saying where it goes")


def test_no_other_instruction_draws_the_line_again():
    drawn = [p for p in _instructions() if SHOWN_OR_WORDED in p]

    assert len(drawn) == 2, [p[:80] for p in drawn]
    assert all(REQUEST_MARKER in p or "[[TICKET:" in p for p in drawn)


def test_the_line_keeps_a_change_of_design_a_requirement():
    """The narrow reading: only how something already built is shown or worded, and only when no
    agreed requirement says otherwise. A change to what the product does stays a requirement."""
    assert "already" in SHOWN_OR_WORDED and "contradicts no agreed requirement" in SHOWN_OR_WORDED


# ── 2. the platform stages what the markers say ───────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean():
    pc._PENDING.clear()
    yield
    pc._PENDING.clear()


class _Role:
    """The role in the conversation, answering through the parser the turn uses: whatever it
    writes is read as the model's reply is. It drafts nothing (a card is staged as said) and has
    no pen for a requirement, so a requirement staged here would fail loudly."""

    def __init__(self, pen, reply: str) -> None:
        self.file_ticket, self._reply = pen.file_ticket, reply

    def settle_acceptance(self, text, **_):
        return None

    def close_decisions_answered(self, **_):
        return 0

    def confirmed(self, reply, *, proposal):
        return "neither"

    def context(self):
        return SimpleNamespace(available=True, reason="")

    def answer(self, question, **_):
        return read_answer(self._reply)


@pytest.mark.parametrize("markers", [f"[[TICKET: {TITLE}]]",
                                     f"{REQUEST_MARKER}\n[[TICKET: {TITLE}]]"],
                         ids=["the card alone", "a request and the card"])
def test_a_card_the_person_asked_for_is_staged_as_a_card_and_filed_on_one_yes(project, tmp_path,
                                                                                 markers):
    from openfactory.adapters.tracker.registry import build_tracker

    talk = _Role(_pen(project, tmp_path), f"{SAID}\n{markers}")

    staged = chat_turn(project, text=C_01, user=ANA, thread=ANAS, module=talk)
    assert staged and TITLE in str(staged), staged

    chat_turn(project, text="sim", user=ANA, thread=ANAS, module=talk)
    assert build_tracker(project).find_ticket(title=TITLE), "the card did not reach the board"
