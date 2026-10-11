"""A close in favour of another card asks the yes on what the closed card carries and the survivor
does not (#567).

THE RUN (v0.5.0-rc.1, the same afternoon as #563). The role offered to close "#1000009 ou
#1000010" as if they were equal, and took the person's choice of #1000009. That card was the only
one carrying the requirement's first front, "keep each delivered version instead of deleting it";
#1000010 builds on it. The confirmation said the two cards "ask for the same thing" — a claim the
role had made from their titles.

Now the close reads both cards off the board before it is staged. The criteria only the closed one
states, and the requirement only it executes, are listed in the question the yes answers, and the
sentence no longer claims the two are the same. When the two cannot be read, it says so.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from openfactory.product.module import Carried, ProductModule, only_in
from openfactory.product.voice import close_confirmation, jargon_in
from tests.test_card_maintenance_channel import _Module, _Project, _waiting  # noqa: F401
from tests.the_chat_turn import chat_turn

KEEP = "Each delivered version is kept instead of deleted"
LIST = "Past versions are listed, newest first"
OPEN = "A past version can be opened and downloaded"


def _body(*criteria: str, executes: int | None = None) -> str:
    parts = ["## Objective", "", "Versions.", "", "## Acceptance criteria", ""]
    parts += [f"- {c}" for c in criteria]
    if executes is not None:
        parts += ["", "## Source", "", f"Executes **REQ-{executes:04d}** in docs — #66."]
    return "\n".join(parts) + "\n"


# ── the comparison ──────────────────────────────────────────────────────────────────────────────

def test_TODAYS_RUN_the_card_closed_carried_a_front_the_survivor_does_not():
    """#1000009 (a requested card, no source) closed in favour of #1000010 (the breakdown's,
    executing REQ-0066): the closed card's first criterion is nowhere on the survivor."""
    closing = _body(KEEP, LIST, OPEN)
    staying = _body(LIST, OPEN, executes=66)

    assert only_in(closing, staying) == Carried(criteria=(KEEP,), executes=None)


def test_a_criterion_is_the_same_whatever_its_case_and_punctuation():
    closing = _body("Past versions are LISTED, newest first.")
    staying = _body(LIST)

    assert not only_in(closing, staying)


def test_the_requirement_only_the_closed_card_executes_is_carried():
    assert only_in(_body(LIST, executes=66), _body(LIST)) == Carried(executes=66)
    assert only_in(_body(LIST, executes=66), _body(LIST, executes=70)) == Carried(executes=66)
    assert not only_in(_body(LIST, executes=66), _body(LIST, executes=66))


def test_the_list_is_bounded():
    many = [f"Criterion number {n} holds" for n in range(9)]

    assert len(only_in(_body(*many), _body()).criteria) == 5


# ── the module reads both cards off the board ──────────────────────────────────────────────────

def _module_over(cards, error=""):
    module = ProductModule.__new__(ProductModule)
    module._read_board = lambda **_kw: (cards, error)
    return module


def test_the_module_reads_both_cards_from_the_board_it_already_reads():
    cards = [SimpleNamespace(number="1000009", body=_body(KEEP, LIST)),
             SimpleNamespace(number="1000010", body=_body(LIST, executes=66))]

    assert _module_over(cards).what_only_it_carries("#1000009", "1000010") == \
        Carried(criteria=(KEEP,))


@pytest.mark.parametrize("cards, error", [
    ([SimpleNamespace(number="1000009", body=_body(KEEP))], ""),
    ([], "the board could not be read"),
], ids=["the-survivor-is-not-on-the-board", "the-board-is-unreadable"])
def test_a_card_that_cannot_be_read_is_none_never_an_empty_comparison(cards, error):
    """`None` is "could not compare"; an empty `Carried` would read as "nothing is lost"."""
    assert _module_over(cards, error).what_only_it_carries("1000009", "1000010") is None


# ── the question the yes answers ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("language, overlap", [("pt-BR", "não são iguais"),
                                               ("en", "they are not the same")])
def test_the_question_lists_what_is_lost_and_never_claims_the_two_are_the_same(language,
                                                                               overlap):
    said = close_confirmation(number="1000009", in_favour_of="1000010",
                              carried=Carried(criteria=(KEEP,), executes=66), language=language)

    assert overlap in said and f"• {KEEP}" in said and "66" in said, said
    assert "pedem a mesma coisa" not in said and "ask for the same thing" not in said
    assert "{" not in said and not jargon_in(said), jargon_in(said)
    assert said.rstrip().endswith(("Confirma?", "Confirm?"))


@pytest.mark.parametrize("language", ["pt-BR", "en"])
def test_two_cards_that_could_not_be_compared_are_said_before_the_question(language):
    said = close_confirmation(number="1000009", in_favour_of="1000010", unread=True,
                              language=language)

    assert ("Não consegui ler os dois cartões" in said
            or "I could not read the two cards" in said), said
    assert said.rstrip().endswith(("Confirma?", "Confirm?")), said
    assert not jargon_in(said), jargon_in(said)


@pytest.mark.parametrize("language", ["pt-BR", "en"])
def test_a_closed_card_that_states_nothing_to_compare_is_said_not_compared(language):
    """REVIEW OF #602. A card of prose alone — no criteria, no `## Source` — carries nothing the
    comparison can see, which is not the same as carrying nothing: the question still claims the
    two ask for the same thing, so it says they were not compared."""
    carried = only_in("Só um parágrafo explicando o pedido.", f"## Acceptance criteria\n- [ ] {KEEP}")
    said = close_confirmation(number="1000009", in_favour_of="1000010", carried=carried,
                              language=language)

    assert not carried and carried.stated is False, carried
    assert ("não deu para comparar" in said or "could not be compared" in said), said
    assert said.rstrip().endswith(("Confirma?", "Confirm?")), said
    assert not jargon_in(said), jargon_in(said)


def test_a_closed_card_whose_criteria_the_survivor_states_too_was_compared():
    carried = only_in(f"## Acceptance criteria\n- [ ] {KEEP}", f"## Acceptance criteria\n- [ ] {KEEP}")

    assert not carried and carried.stated is True, carried
    said = close_confirmation(number="511", in_favour_of="288", carried=carried, language="pt-BR")
    assert "não deu para comparar" not in said, said


def test_two_cards_that_carry_the_same_things_keep_the_duplicate_question():
    said = close_confirmation(number="511", in_favour_of="288", carried=Carried(),
                              language="pt-BR")

    assert said == close_confirmation(number="511", in_favour_of="288", language="pt-BR")


# ── through the conversation ────────────────────────────────────────────────────────────────────

class _Comparing(_Module):
    """The channel's module double, with the comparison the engine now asks for."""

    def __init__(self, carried):
        super().__init__()
        self.carried, self.compared = carried, []

    def what_only_it_carries(self, number, survivor):
        self.compared.append((number, survivor))
        return self.carried


def test_closing_in_favour_of_another_card_asks_on_what_only_the_closed_card_carries():
    """Four-digit cards: the close pattern reads no longer ref today, which is #565's to fix."""
    module = _Comparing(Carried(criteria=(KEEP,)))

    ask = chat_turn(_Project(), text="fecha o #9009 em favor do #9010", user="UADM",
                    thread="C1", channel="C1", module=module)

    assert module.compared == [("9009", "9010")], module.compared
    assert f"• {KEEP}" in ask and "não são iguais" in ask, ask
    assert module.closed_with is None, "it wrote before anybody confirmed"


def test_a_close_with_no_survivor_reads_nothing():
    module = _Comparing(Carried(criteria=(KEEP,)))

    chat_turn(_Project(), text="fecha o #9009", user="UADM", thread="C1", channel="C1",
              module=module)

    assert module.compared == []
