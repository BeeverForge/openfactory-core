"""A sentence that sends a person to the product's approvers names them (#666).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, row C-12). Someone off the admin list asked
the product owner to accept a requirement and break it down. Nothing was staged, which is right,
and the reply ended "Peça a confirmação a uma dessas pessoas e eu registro" — ask one of these
people to confirm and I'll record it. "These people" were never named, though the registry lists
the product's admins; the act it spoke of, writing an agreed requirement, was not the one refused;
and it promised a recording nothing was waiting for. Five more sentences sent a person to "one of
them" the same way: closing or removing a card, queueing it, sending it back, accepting its change,
and telling the room it was tried.

THE RULE THIS FILE HOLDS, over every sentence the voice can say, in every language — read from the
voice itself, so a sentence added later is held too:
  1. no sentence tells a person to ask or tell "one of them", people it does not name;
  2. every sentence that sends a person to the approvers carries their names, and is said by a
     builder handed them; a builder handed none refuses rather than says it;
  3. the names are the product's admins as the platform knows them, at most three, joined as the
     language joins a list; with nobody set up, the person who can set one up;
  4. through the conversation, the refusal of someone off the list names the admins (C-12), and
     neither names an act it did not refuse nor promises a recording.
"""

from __future__ import annotations

import re

import pytest

from openfactory.product import voice
from openfactory.product.module import unauthorized_message
from tests.test_closing_correcting_and_aligning_are_acts_the_role_proposes import (
    ADMIN,
    CLIENT,
    _Project,
    _Role,
    _say,
)
from tests.test_closing_correcting_and_aligning_are_acts_the_role_proposes import (
    _clean_stage as _clean_stage,  # noqa: F401 — the fixture, reused
)
from tests.test_closing_correcting_and_aligning_are_acts_the_role_proposes import (
    started as started,  # noqa: F401 — the fixture, reused
)


def _sentences() -> list[tuple[tuple[str, ...], str]]:
    """Every sentence in the voice's tables, with the path that names it."""
    found: list[tuple[tuple[str, ...], str]] = []

    def walk(value, path):
        if isinstance(value, str):
            found.append((path, value))
        elif isinstance(value, dict):
            for key, inner in value.items():
                walk(inner, (*path, str(key)))
        elif isinstance(value, (list, tuple)):
            for i, inner in enumerate(value):
                walk(inner, (*path, str(i)))

    for name, value in vars(voice).items():
        if isinstance(value, dict) and not name.startswith("__"):
            walk(value, (name,))
    return found


SENTENCES = _sentences()
LANGS = sorted(voice._APPROVERS)
#: Asking or telling people the sentence does not name, in each language the voice speaks.
UNNAMED = {
    "pt-BR": re.compile(r"\b(peça|diga)\b[^.]*\b(uma dessas|dessas pessoas|um deles|uma delas)\b",
                        re.IGNORECASE),
    "en": re.compile(r"\b(ask|tell)\b (one of them|them)\b", re.IGNORECASE),
}
#: Each table holding a sentence that names the approvers, said through the builder that fills it.
SAYS = {
    "_CANNOT_WRITE_SOME": lambda lang, who: voice.cannot_write(approvers=who, language=lang),
    "_CARD_WITHDRAWN_RESULT": lambda lang, who: voice.card_withdrawn_result(
        ref="7", how="not_yours", language=lang, approvers=who),
    "_CARD_QUEUE": lambda lang, who: voice.card_queue_not_yours(
        ref="7", column="TO-DO", language=lang, approvers=who),
    "_ADJUST_SAID": lambda lang, who: voice.adjust_said("not_yours", ref="7", language=lang,
                                                        approvers=who),
    "_ACCEPT_CHANGE_SAID": lambda lang, who: voice.accept_change_said(
        "not_yours", ref="7", language=lang, approvers=who),
    "_SAID_RIGHT_ROOM": lambda lang, who: voice.requester_said_right(
        ref="7", told=False, language=lang, approvers=who),
}


def test_the_sweep_reads_the_voice():
    assert len(SENTENCES) > 500 and set(UNNAMED) == set(LANGS), (len(SENTENCES), LANGS)


# ── 1. nobody is pointed at without a name ──────────────────────────────────────────────────────

def test_no_sentence_sends_a_person_to_people_it_does_not_name():
    pointing = [(path, text[:100]) for path, text in SENTENCES
                for rule in UNNAMED.values() if rule.search(text)]

    assert not pointing, pointing


# ── 2. the sentences that name the approvers, and their builders ───────────────────────────────

def test_every_sentence_that_names_the_approvers_is_said_by_a_builder_handed_them():
    naming = {path[0] for path, text in SENTENCES if "{names}" in text}

    assert naming == set(SAYS), (
        f"a table names the approvers with no builder registered here: {naming - set(SAYS)}")
    for table, say in SAYS.items():
        for lang in LANGS:
            said = say(lang, ["po", "ana"])
            assert "po" in said and "ana" in said and "{names}" not in said, (table, lang, said)


@pytest.mark.parametrize("table", sorted(SAYS))
def test_a_builder_handed_no_approvers_refuses_rather_than_names_nobody(table):
    with pytest.raises(ValueError):
        SAYS[table]("pt-BR", None)


# ── 3. the names ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
def test_the_names_are_at_most_three_joined_as_the_language_joins_a_list(lang):
    joins = voice._APPROVERS[lang]["or"]

    assert voice.approvers_named(["po"], lang) == "po"
    assert voice.approvers_named(["po", "ana"], lang) == f"po{joins}ana"
    assert voice.approvers_named(["po", "ana", "rui", "eva", "ivo"], lang) == f"po, ana{joins}rui"
    assert voice.approvers_named([], lang) == voice._APPROVERS[lang]["nobody"]


def test_the_names_are_the_products_admins_as_the_platform_knows_them():
    project = _Project()

    project.product.admins = ["po", "ana", "rui", "eva"]
    said = unauthorized_message(project)
    assert all(name in said for name in ("po", "ana", "rui")) and "eva" not in said, said

    project.product.admins = []
    assert unauthorized_message(project) == voice._pick(voice._CANNOT_WRITE_NONE, "pt-BR")


# ── 4. through the conversation ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("marker", "text"), [
    ("[[QUEBRAR: REQ-0066]]", "quebra o 66"),
    ("[[REFINAR: #412]]", "escreve os critérios do 412"),
], ids=["breakdown", "refine"])
def test_TODAYS_RUN_the_refusal_of_someone_off_the_list_names_the_admins(marker, text, started):
    asked = _say(_Role("Certo.\n" + marker), text, user=CLIENT, project=_Project())

    assert ADMIN in asked, asked
    assert "requisito acordado" not in asked and "eu registro" not in asked, asked
