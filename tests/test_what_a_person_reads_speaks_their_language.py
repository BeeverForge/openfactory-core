"""What a person reads from the product role and the tech lead is in their project's language (#535).

FOUND by the sweep's guard (`test_no_portuguese_is_welded_into_the_core`): past the docs
repository's writes (`test_what_the_docs_repository_records_speaks_the_projects_language`), the
sentences a person still read in Portuguese on an `en` project were the ones composed outside any
catalogue — a requirement's card held back "a revisão automática não respondeu", a decision row
named its conversation "conversa com o time de produto", a case's reading said "leitura: problema ·
confiança média", and the tech lead's memory of a remedy ended "— precisa de alguém olhando a
causa".

THE RULE THIS FILE HOLDS: each of those sentences comes from a catalogue with `en` beside `pt-BR`,
and its caller hands it the project's language; a `pt-BR` project reads what it read before; a card
closed, merged into another and withdrawn on an `en` project carries no Portuguese in any comment.
The reason a close carries is the role's marker since #565 slices b and c, in any language.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from openfactory.product import cards
from openfactory.product.confirm import _where_it_came_from
from openfactory.product.reading import ALTA, BAIXA, MEDIA, render_reading
from openfactory.product.role import Reading
from openfactory.techlead.memory import MEMORY
from openfactory.techlead.voice import say
from tests import test_card_maintenance as maintenance
from tests.test_a_card_is_drafted_and_judged_before_the_yes import ISSUE, SOURCE, _body
from tests.test_card_maintenance import ADMIN, _isolate, world  # noqa: F401 — the bed, reused
from tests.test_no_portuguese_is_welded_into_the_core import (
    _PT_ALONE,
    _PT_LETTERS,
    fragments,
    is_portuguese,
)
from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parent.parent


def _portuguese(text: str) -> list[str]:
    return [f for f in fragments(text) if is_portuguese(f)]


# ── the card's comments on an `en` project ──────────────────────────────────────────────────────

@pytest.fixture
def english(monkeypatch):
    plain = maintenance._project
    monkeypatch.setattr(maintenance, "_project",
                        lambda: plain().model_copy(update={"language": "en"}))


def test_a_card_closed_merged_and_withdrawn_on_an_en_project_carries_no_portuguese(
        english, world):  # noqa: F811
    mod, _ = world()

    assert mod.close_card(511, actor=ADMIN, in_favour_of=288, reason="it was the same request").ok
    assert mod.close_card(602, actor=ADMIN, reason="nobody needs it any more").ok
    assert mod.withdraw_card("600", actor=ADMIN, reason="the client gave it up").ok
    assert mod.withdraw_card("604", actor=ADMIN, reason="filed twice", remove=True).ok

    written = ([note for _ref, note in world.tracker.closed]
               + [body for _ref, body in world.tracker.comments])
    assert len(written) >= 5, written          # four closing notes, and the survivor's
    for text in written:
        # STRICTER THAN THE SWEEP'S TEST: a word only Portuguese writes is Portuguese here even
        # beside an English one — "Fechado a pedido of U0ADMIN" is half a translation, and the
        # sweep's two-language arithmetic reads it as English
        assert not _PT_LETTERS.search(text) and not _PT_ALONE.search(text), text


# ── one sentence each, in the project's language ────────────────────────────────────────────────

def _vet(judge, language):
    from openfactory.product.cards import load_rubric

    return cards.vet_issue(dict(ISSUE), body_of=_body, source=SOURCE, rubric=load_rubric(),
                           judge=judge, redraft=None, project_name="books", language=language)


def test_a_card_held_for_an_unread_review_says_so_in_the_projects_language():
    assert _vet(lambda p: "looks fine to me", "en") == (None, "the automatic review did not answer")
    assert _vet(lambda p: "looks fine to me", "pt-BR") == (
        None, "a revisão automática não respondeu")


def test_the_module_hands_the_vet_its_projects_language():
    tree = parsed(ROOT / "openfactory/product/module.py")
    [call] = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute) and n.func.attr == "vet_issue"]

    assert any(k.arg == "language" and "language" in ast.unparse(k.value)
               for k in call.keywords), ast.unparse(call)


def test_a_decision_row_names_its_conversation_in_the_projects_language():
    def project(language):
        return maintenance._project().model_copy(update={"language": language})

    assert _where_it_came_from(project("en"), "") == "conversation with the product team"
    assert _where_it_came_from(project("en"), "C9") == "conversation with the product team (C9)"
    assert _where_it_came_from(project("pt-BR"), "") == "conversa com o time de produto"


@pytest.mark.parametrize(("language", "line"), [
    ("en", "reading: defect · confidence medium"),
    ("pt-BR", "leitura: problema · confiança média"),
    ("pt-PT", "leitura: problema · confiança média"),
])
def test_a_reading_is_said_in_the_projects_language(language, line):
    reading = Reading(kind="defect", confidence=MEDIA)

    assert render_reading(reading, language=language).startswith(line), (
        render_reading(reading, language=language))


def test_every_level_of_confidence_has_its_english():
    said = {level: render_reading(Reading(kind="question", confidence=level), language="en")
            for level in (ALTA, MEDIA, BAIXA)}

    assert [s.split("confidence ")[1].split(" ")[0] for s in said.values()] == [
        "high", "medium", "low"], said


def test_the_tech_leads_memory_says_a_remedy_needs_a_person_in_the_projects_language():
    assert say(MEMORY, "needs_a_person", "en") == " — it needs somebody looking at the cause"
    assert say(MEMORY, "needs_a_person", "pt-BR") == " — precisa de alguém olhando a causa"


def test_the_watch_hands_the_memory_its_projects_language():
    source = (ROOT / "openfactory/runtime/temporal/activities.py").read_text(encoding="utf-8")
    calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "temper"]

    assert calls, "the watch no longer tempers a remedy, and this guard went blind"
    for call in calls:
        assert any(k.arg == "language" for k in call.keywords), ast.unparse(call)
    assert 'tech_say(MEMORY, "needs_a_person", lang)' in source
