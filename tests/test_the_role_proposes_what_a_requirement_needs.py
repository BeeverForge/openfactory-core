"""Agreeing to a requirement, dropping it, writing a decision into it and noting a fact are acts
the role proposes from what it understood (#565, first slice).

THE RUN (v0.5.0-rc.1). The role told the person "when you tell me it is agreed it becomes a
promise", and telling it so reached nothing: the only sentence that did was "aceita o requisito
66", matched by a pattern before the model ran (`intents.py`). "pode aceitar o 66", "sim, concordo
com o requisito 66" and "ok, I agree with requirement 66" matched nothing, and the model that
understood each of them had no act to hand it to.

Now each of the four is a marker the role writes — `[[ACORDO: REQ-N]]`, `[[DESCARTE: REQ-N; …]]`,
`[[REGISTRO: REQ-N; …]]`, `[[FATO: …]]` — read by the role's own parser (`role.read_answer`) and
staged by the branch the pattern reached (`engine._run_intent`), so what is checked before the
question and what the yes executes did not change. The patterns are gone: one way in.

WHAT IS DRIVEN HERE. The conversation itself, `engine.turn` through `chat_turn`, with a module
double that answers through `read_answer` — the model's text read the way the turn reads it.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

import openfactory.product.channel as pc
from openfactory.product.confirm import _EXECUTORS
from openfactory.product.intents import match_intent
from openfactory.product.role import (
    ACCEPT_MARKER,
    ADJUST_MARKER,
    DEFECT_MARKER,
    ORDER_MARKER,
    QUEUE_MARKER,
    REQUEST_MARKER,
    REQUIREMENT_ACTS,
    STAGING_MARKERS,
    TICKET_MARKER,
    read_answer,
)
from tests.the_chat_turn import chat_turn

ADMIN, KEY = "UADM", "C1"


class _Req:
    def __init__(self, number=66, status="proposed"):
        self.number, self.status = number, status
        self.title, self.slug, self.path = "Versões entregues", "versoes", "0066-versoes.md"

    @property
    def is_live(self):
        return self.status not in ("superseded", "dropped")

    @property
    def is_promise(self):
        return self.status == "accepted"


class _Role:
    """The product module as the turn sees it: one requirement in the corpus, and the model's text
    read by the role's own parser."""

    def __init__(self, said: str, req: _Req | None = None) -> None:
        self.said, self.reqs = said, [req if req is not None else _Req()]

    def context(self):
        reqs = self.reqs

        class _Corpus:
            def by_number(self, n):
                return next((r for r in reqs if r.number == n), None)

        return SimpleNamespace(available=True, corpus=_Corpus(), reason="")

    def answer(self, question, **_):
        return read_answer(self.said)

    def settle_acceptance(self, *_a, **_k):
        return None

    def confirmed(self, *_a, **_k):
        return "neither"

    def close_decisions_answered(self, **_):
        return 0

    def record_decisions(self, *_a, **_k):
        return None


class _Project:
    name, language = "books", "pt-BR"

    def __init__(self):
        self.product = SimpleNamespace(admins=[ADMIN], agent_name="Nina", docs_repo="a/docs",
                                       channel_id=KEY, enabled=True, docs_branch="main")


@pytest.fixture(autouse=True)
def _clean_stage(monkeypatch):
    from openfactory.memory import transcript
    from openfactory.product import staging as _staging

    monkeypatch.setattr(_staging, "_PENDING", {})
    monkeypatch.setattr(_staging, "_EXPIRED_TOMBSTONES", {})
    monkeypatch.setattr(transcript, "record", lambda *a, **k: "")
    monkeypatch.setattr(transcript, "recent", lambda *a, **k: [])
    yield


def _turn(text: str, said: str, req: _Req | None = None) -> tuple[str, dict | None]:
    asked = chat_turn(_Project(), text=text, user=ADMIN, thread=KEY, channel=KEY,
                      module=_Role(said, req))
    return str(asked or ""), pc.find_waiting(KEY, KEY)[1]


# ── the run: the sentences that matched nothing now reach the act ──────────────────────────────

@pytest.mark.parametrize("sentence", ["pode aceitar o 66", "sim, concordo com o requisito 66",
                                      "ok, I agree with requirement 66"])
def test_TODAYS_RUN_agreeing_in_any_words_stages_the_acceptance(sentence):
    said = "Entendi: o requisito 66 fica acordado.\n[[ACORDO: REQ-0066]]"

    asked, staged = _turn(sentence, said)

    assert staged and staged["kind"] == "accept" and staged["number"] == 66, (staged, asked)
    # THE ROLE'S UNDERSTANDING, THEN THE QUESTION — and the plumbing never reaches the person
    assert asked.startswith("Entendi: o requisito 66 fica acordado."), asked
    assert "[[" not in asked, asked


def test_TODAYS_RUN_dropping_in_any_words_stages_the_drop_with_their_reason():
    said = ("Certo, o 66 sai da mesa.\n"
            "[[DESCARTE: REQ-66; o cliente vai manter a planilha por enquanto]]")

    asked, staged = _turn("pode jogar fora o 66, vão manter a planilha por enquanto", said)

    assert staged and staged["kind"] == "drop" and staged["number"] == 66, (staged, asked)
    assert staged["reason"] == "o cliente vai manter a planilha por enquanto", staged
    assert asked.startswith("Certo, o 66 sai da mesa."), asked


def test_a_decision_is_staged_in_the_words_the_marker_carries():
    said = "Vou registrar no 66.\n[[REGISTRO: REQ-0066; o corte é sempre no dia 25]]"

    asked, staged = _turn("anota no 66 que o corte é dia 25", said)

    assert staged and staged["kind"] == "decision", (staged, asked)
    assert (staged["number"], staged["decision"]) == (66, "o corte é sempre no dia 25"), staged
    assert "o corte é sempre no dia 25" in asked, asked


def test_a_fact_is_staged_in_the_words_the_marker_carries():
    said = "Anotado o que você disse.\n[[FATO: a firma fecha o mês sempre no dia 5]]"

    asked, staged = _turn("para constar: a firma fecha o mês no dia 5", said)

    assert staged and staged["kind"] == "fact", (staged, asked)
    assert staged["body"] == "a firma fecha o mês sempre no dia 5", staged


def test_the_branch_still_judges_what_the_role_proposed():
    """The checks before the question are the branch's, unchanged: a requirement already agreed is
    said so after the role's reply, with no name in front of it, and nothing is staged."""
    said = "Entendi: o requisito 66 fica acordado.\n[[ACORDO: REQ-0066]]"

    asked, staged = _turn("pode aceitar o 66", said, _Req(status="accepted"))

    assert staged is None, staged
    assert asked.startswith("Entendi: o requisito 66 fica acordado.\n\n"), asked
    assert "Nina:" not in asked, asked


def test_a_requirement_that_does_not_exist_is_said_after_the_reply():
    said = "Vou registrar no 70.\n[[REGISTRO: REQ-0070; o corte é dia 25]]"

    asked, staged = _turn("anota no 70 que o corte é dia 25", said)

    assert staged is None, staged
    assert asked.startswith("Vou registrar no 70.\n\n") and "70" in asked[20:], asked


def test_the_sentence_alone_acts_no_more():
    """ONE WAY IN. The pattern that read "aceita o requisito 66" is gone; a reply with no marker
    stages nothing, whatever the person wrote."""
    asked, staged = _turn("aceita o requisito 66", "Posso dar o 66 como acordado, se você quiser.")

    assert staged is None, (staged, asked)
    for sentence in ("aceita o requisito 66", "registra no requisito 6 que o corte é dia 25",
                     "cancela o requisito 2", "anota que a firma usa Primavera",
                     "accept requirement 6"):
        assert match_intent(sentence) is None, (sentence, match_intent(sentence))


# ── the markers ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("written", ["REQ-0066", "REQ-66", "req-66", "66", "#66", "REQ66"])
def test_each_act_reads_the_requirement_as_the_role_writes_it(written):
    for marker, gesture, args in (
            (f"[[ACORDO: {written}]]", "agree", {}),
            (f"[[DESCARTE: {written}; fora de escopo]]", "drop", {"reason": "fora de escopo"}),
            (f"[[DESCARTE: {written}]]", "drop", {}),
            (f"[[REGISTRO: {written}; o corte é dia 25]]", "record",
             {"decision": "o corte é dia 25"})):
        answer = read_answer(f"Certo.\n{marker}")
        captured = dict(answer.gesture_args)
        assert answer.gesture == gesture, (marker, answer.gesture)
        assert int(captured.pop("number")) == 66 and captured == args, (marker, captured)
        assert answer.text == "Certo.", (marker, answer.text)


@pytest.mark.parametrize("said", ["[[ACORDO: o requisito 66]]", "[[ACORDO]]",
                                  "[[REGISTRO: REQ-66]]", "[[REGISTRO: REQ-66; ok]]",
                                  "[[FATO: curto]]", "[[DESCARTE: o 66]]"])
def test_prose_in_the_marker_is_not_an_act(said):
    """A requirement where the marker names one, and words where it carries them: what does not
    fit is not read as an act — the net strips it, and nothing is staged on a guess."""
    answer = read_answer(f"Certo.\n{said}")

    assert answer.gesture == "" and answer.gesture_args == {}, (said, answer)
    assert answer.text == "Certo.", answer.text


def test_two_acts_in_one_reply_stage_the_first_and_say_the_second(caplog):
    with caplog.at_level(logging.WARNING, logger="openfactory.product.role"):
        answer = read_answer("Certo.\n[[FATO: a firma usa o Primavera desde 2019]]\n"
                             "[[ACORDO: REQ-66]]")

    assert answer.gesture == "agree" and answer.gesture_args == {"number": "66"}, answer
    assert answer.text == "Certo.", answer.text
    assert "OPENFACTORY_PRODUCT_ONE_ACT_PER_REPLY" in caplog.text, caplog.text


def test_a_change_waiting_on_the_person_outranks_an_act_on_a_requirement():
    answer = read_answer("Certo.\n[[ACEITE: #12]]\n[[ACORDO: REQ-66]]")

    assert (answer.gesture, answer.gesture_card, answer.gesture_args) == ("accept", "12", {})


def test_every_act_is_taught_with_the_sentence_that_says_what_comes_next():
    """The prompt teaches each marker, and each stages: the four are in `STAGING_MARKERS`, so the
    guard of #430 holds them to the phrase that tells the model the platform asks the question."""
    for marker, _pattern, _gesture, _intent in REQUIREMENT_ACTS:
        assert marker in STAGING_MARKERS, marker


# ── the guard ───────────────────────────────────────────────────────────────────────────────────

#: WHAT EACH STAGING MARKER STAGES, as `_EXECUTORS` names it. `[[PEDIDO]]` stages a draft, which has
#: no executor of its own (`confirm._confirm_draft`).
STAGED_BY = {DEFECT_MARKER: "defect", TICKET_MARKER: "ticket", ORDER_MARKER: "reorder",
             QUEUE_MARKER: "queue", ADJUST_MARKER: "adjust", ACCEPT_MARKER: "accept_change",
             **{marker: intent for marker, _pattern, _gesture, intent in REQUIREMENT_ACTS}}

#: THE KINDS A PERSON STILL REACHES ONLY THROUGH A FIXED SENTENCE (#565). Each later slice moves its
#: kinds to a marker and takes them off this list; the guard below fails on a kind added here that
#: a pattern does not reach, so the list can only shrink.
STILL_BY_A_SENTENCE = {"close": "fecha o #511", "correct": "corrige o #512: o relatório é semanal",
                       "align": "alinha o #288 ao requisito 6"}


def test_every_staging_marker_says_what_it_stages():
    assert set(STAGED_BY) == set(STAGING_MARKERS) - {REQUEST_MARKER}


def test_every_act_the_role_has_is_one_it_can_propose_or_is_still_listed():
    """THE NEXT ACT CANNOT BE ADDED THE OLD WAY. A kind the confirmation executes is staged by a
    marker the model can write, or is on the shrinking list of kinds a sentence still reaches."""
    proposed = set(STAGED_BY.values())

    assert set(_EXECUTORS) - proposed == set(STILL_BY_A_SENTENCE), (
        set(_EXECUTORS) - proposed, set(STILL_BY_A_SENTENCE))
    for kind, sentence in STILL_BY_A_SENTENCE.items():
        matched = match_intent(sentence)
        assert matched and matched[0] == kind, (kind, sentence, matched)
