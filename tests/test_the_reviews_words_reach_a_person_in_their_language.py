"""What the automatic review found reaches a person in their own language (#677).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, rows C-07 and B-05). A breakdown's front
did not pass the automatic review, and the owner's pt-BR conversation was told "não passou na
revisão automática, então não abri esse cartão. O que falta: Name the reservations screen and the
filters … in the objective so the card stands alone.; The 'limpar filtros' criterion relies on
controls from another card; …". The one part that said what the person could do about it was the
review's instructions to the redraft, in English. The requirements list on the owner's page showed
the same, and a requested card shown for the yes while still disputed quoted the same findings.

THE RULE THIS FILE HOLDS, for every problem the floor can raise (read from its own source) and
every language the review's relay speaks — so a problem or a language added later is held too:
  1. every problem the floor raises has a sentence for a person in every language;
  2. a breakdown's card the floor refuses is told in the person's language, never as the redraft's
     instruction;
  3. a card the judge refuses is told in the judge's words for the person, asked of it in the
     person's language, never its findings for the redraft; a judge that gave none is told in
     the language's own sentence;
  4. a card shown for the yes while the review still disputes it carries the person's words;
  5. the redraft keeps receiving the findings as they are.
"""

from __future__ import annotations

import inspect
import json
import re

import pytest

import openfactory.product.channel as pc
from openfactory.language.written import base
from openfactory.product import cards, voice
from openfactory.product.cards import load_rubric
from tests.test_a_card_is_drafted_and_judged_before_the_yes import (
    GESTURE,
    GOOD,
    ISSUE,
    SOURCE,
    _body,
    _scores,
    _World,
)
from tests.test_a_card_is_drafted_and_judged_before_the_yes import (
    _clean as _clean,  # noqa: F401 — the fixtures, reused
)
from tests.test_a_card_is_drafted_and_judged_before_the_yes import (
    _earlier_turns as _earlier_turns,  # noqa: F401
)
from tests.test_confirmation_by_click import ADMIN, KEY, _project
from tests.the_chat_turn import chat_turn

KINDS = re.findall(r'_problem\(\s*"(\w+)"', inspect.getsource(cards.floor))
LANGS = sorted(voice._CARD_DISPUTED)
FINDING = "Name the reservations screen in the objective so the card stands alone"
TOLD = {"pt-BR": "diga no objetivo qual é a tela de reservas", "en": "say which screen it is"}


def _judge(level: int, *, findings=(), told=(), ask=""):
    return json.dumps({"scores": _scores(level), "evidence": {}, "critical": [],
                       "findings": list(findings), "told": list(told), "ask": ask})


def _vet(fields, judge, redraft=None, *, language):
    return cards.vet_issue(fields, body_of=_body, source=SOURCE, rubric=load_rubric(),
                           judge=judge, redraft=redraft, project_name="books", language=language)


def test_the_problems_and_the_languages_are_read_from_the_code():
    assert len(KINDS) >= 7 and len(set(KINDS)) == len(KINDS), KINDS
    assert {"en", "pt-BR"} <= set(LANGS) and set(TOLD) == set(LANGS)


# ── 1. every problem, every language ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind", KINDS)
def test_every_problem_the_floor_raises_has_a_sentence_for_a_person(kind, lang):
    problem = cards._problem(kind, "an instruction for the redraft", length=130, limit=120)

    told = cards.review_said([problem], None, lang)

    assert told and told != cards.review_said([], None, lang), (kind, lang, told)
    assert "an instruction for the redraft" not in " ".join(told)
    assert "{" not in " ".join(told), f"a field of {kind} was left unfilled: {told}"
    others = {other: cards.review_said([problem], None, other) for other in LANGS if other != lang}
    assert all(said != told for said in others.values()), (
        f"{kind} is told in {lang} with another language's words: {told}")


# ── 2. the floor's refusal ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
def test_a_card_the_floor_refuses_is_told_in_the_persons_language(lang):
    fields = {**ISSUE, "acceptance_criteria": []}

    kept, why = _vet(fields, None, language=lang)

    assert kept is None
    problems = cards.floor(cards.CardDraft(title=fields["title"], objective=fields["objective"]),
                           _body(fields), request="x", conversation=SOURCE, described=False)
    assert problems and why == "; ".join(cards.review_said(problems, None, lang)), why
    assert not [p for p in problems if str(p) in why], "the redraft's instruction reached the person"


# ── 3. the judge's refusal ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
def test_TODAYS_RUN_a_card_the_judge_refuses_is_told_in_the_judges_words_for_the_person(lang):
    kept, why = _vet(dict(ISSUE), lambda p: _judge(2, findings=[FINDING], told=[TOLD[lang]]),
                     lambda p: dict(ISSUE), language=lang)

    assert kept is None and why == TOLD[lang] and FINDING not in why, why


@pytest.mark.parametrize("lang", LANGS)
def test_a_judge_that_said_nothing_for_the_person_is_told_in_the_languages_own_sentence(lang):
    kept, why = _vet(dict(ISSUE), lambda p: _judge(2, findings=[FINDING]), lambda p: dict(ISSUE),
                     language=lang)

    assert kept is None and why and why == "; ".join(cards.review_said([], None, lang)), why
    assert FINDING not in why


@pytest.mark.parametrize("lang", LANGS)
def test_the_judge_is_asked_for_the_persons_words_in_their_language(lang):
    prompts: list[str] = []

    _vet(dict(ISSUE), lambda p: prompts.append(p) or _judge(5), language=lang)

    [prompt] = prompts
    assert "`told`" in prompt and '"told": [str]' in prompt, prompt[-600:]
    assert cards._LANGUAGE_NAMES[base(lang)] in prompt.split("`told`", 1)[1][:300], prompt[-600:]


# ── 4. the card shown while disputed ────────────────────────────────────────────────────────────

def test_a_card_shown_while_disputed_carries_the_persons_words(_earlier_turns):
    told = "diga em que tamanho de tela a página quebra"
    asks = iter([_judge(2, findings=["say at which height the page breaks"],
                        ask="Em qual altura de tela isso acontece?")] * 2
                + [_judge(2, findings=["name the screen size"], told=[told])])
    world = _World(GOOD, GOOD, GOOD, judge=lambda p: next(asks))
    chat_turn(_project(), text=GESTURE, user=ADMIN, thread=KEY, module=world)

    shown = str(chat_turn(_project(), text="em telas baixas", user=ADMIN, thread=KEY,
                          module=world))

    assert f"A revisão automática ainda aponta: {told}" in shown, shown
    assert "name the screen size" not in shown, shown
    assert pc.find_waiting(KEY, KEY)[1]["judged"]["disputed"] == ["name the screen size"], (
        "the record keeps what the judge found")


# ── 5. the redraft is unchanged ─────────────────────────────────────────────────────────────────

def test_the_redraft_still_reads_the_findings_as_they_are():
    asked: list[str] = []

    _vet(dict(ISSUE), lambda p: _judge(2, findings=[FINDING], told=[TOLD["pt-BR"]]),
         lambda p: asked.append(p) or dict(ISSUE), language="pt-BR")

    assert asked and FINDING in asked[0] and TOLD["pt-BR"] not in asked[0], asked[:1]
