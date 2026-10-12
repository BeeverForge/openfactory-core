"""A proposal tells each conflict as the kind the drafter recorded (#676).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640). The drafter classifies every conflict it
raises — `contradicts`, `duplicates`, `narrows`, `depends_on` — and the requirement file keeps the
kind. The proposal dropped it: every conflict was framed as going against something already
decided, "a change of mind, not an addition". A date format that only narrowed REQ-0001 — in the
drafter's own words, without contradicting anything — was told to the person as a change of mind,
right before the yes. A frame that says it of everything stops meaning it of the one that is.

THE RULE THIS FILE HOLDS, for every kind the drafter may return and every language the
confirmation speaks — both read from the code, so a kind or a language added later is held too:
  1. each kind has its own words, and only a contradiction is called a change of mind;
  2. a proposal with several kinds says each in its own words, each conflict under its own kind;
  3. the engine hands the drafter's kind to the frame, so the record and the proposal agree;
  4. a kind the platform does not know, and a conflict handed in as bare text, is told as the
     strongest one: a contradiction.
"""

from __future__ import annotations

import re

import pytest

from openfactory.product import engine, voice
from openfactory.product.role import _DRAFT_SCHEMA, Conflict
from openfactory.product.voice import confirmation_request
from tests.test_product_channel import _clean, _draft_answer, _Module, _project, _told  # noqa: F401


def _kinds_the_drafter_may_return() -> list[str]:
    """The kinds the drafter is told it may return, read from its own schema."""
    found = re.search(r'"kind":\s*((?:"\w+"\|?)+)', _DRAFT_SCHEMA)
    assert found, "the drafter's schema no longer names the conflict kinds"
    return re.findall(r'"(\w+)"', found.group(1))


KINDS = _kinds_the_drafter_may_return()
LANGS = sorted(voice._CONFIRM)
#: The words that call a conflict a change of mind, in each language the confirmation speaks.
CHANGE_OF_MIND = {"pt-BR": "mudança de ideia", "en": "change of mind"}


def _frame(kinds_and_lines, lang) -> str:
    return confirmation_request(title="t", must_be_true=["x"], conflicts=list(kinds_and_lines),
                                language=lang)


def test_the_kinds_and_the_languages_are_read_from_the_code():
    assert {"contradicts", "duplicates", "narrows", "depends_on"} <= set(KINDS), KINDS
    assert set(CHANGE_OF_MIND) == set(LANGS), (
        "a language the confirmation speaks has no words for a change of mind here: add them")


# ── 1. each kind its own words ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
def test_every_kind_the_drafter_may_return_has_its_own_words_in_every_language(lang):
    frames = {kind: _frame([(kind, "requisito 1 — x")], lang) for kind in KINDS}

    for kind, text in frames.items():
        others = [k for k, t in frames.items() if k != kind and t == text]
        assert not others, f"{kind} is told in the same words as {others} ({lang})"


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind", KINDS)
def test_TODAYS_RUN_only_a_contradiction_is_called_a_change_of_mind(kind, lang):
    text = _frame([(kind, "requisito 1 — acrescenta o formato sem contradizer nada")], lang)

    assert (CHANGE_OF_MIND[lang] in text) == (kind == "contradicts"), (kind, lang, text)


# ── 2. several kinds in one proposal ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
def test_a_proposal_with_several_kinds_says_each_under_its_own_words(lang):
    """Each conflict sits between its kind's words and the next kind's: a `depends_on` line read
    under the contradiction's heading is the same defect, one conflict at a time."""
    text = _frame([(kind, f"item-{kind}") for kind in reversed(KINDS)], lang).lower()

    for kind in KINDS:
        lead, coda = (said.lower() for said in voice._CONFLICT_KINDS[lang][kind])
        start, end = text.index(lead), text.index(coda)
        assert text.count(f"item-{kind}") == 1, (kind, text)
        assert start < text.index(f"item-{kind}") < end, (kind, lang, text)
        assert not [o for o in KINDS if o != kind and f"item-{o}" in text[start:end]], (kind, text)


# ── 3. the engine hands the kind on ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", KINDS)
def test_the_engine_hands_the_drafters_kind_to_the_frame(kind):
    mod = _Module(draft=_draft_answer(conflicts=[
        Conflict(requirement=1, kind=kind, explanation="o requisito 1 não define o formato")]))

    reply = engine.offer_draft(_project(), request="x", user="U1", thread="t1", module=mod).text

    expected = _frame([(kind, "requisito 1 — o requisito 1 não define o formato")], "pt-BR")
    assert expected[expected.index("⚠️"):] in reply, reply
    assert (CHANGE_OF_MIND["pt-BR"] in reply) == (kind == "contradicts"), reply


# ── 4. what is not known is told as the strongest ───────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
def test_an_unknown_kind_and_bare_text_are_told_as_a_contradiction(lang):
    contradiction = _frame([("contradicts", "requisito 1 — x")], lang)

    assert _frame([("overlaps", "requisito 1 — x")], lang) == contradiction
    assert _frame(["requisito 1 — x"], lang) == contradiction
