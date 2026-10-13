"""No proposal is staged while what it would write waits on an answer (#670).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, C-02). The owner asked for a CSV export in
the client's currency. The role named both conflicts and wrote "Preciso de duas respostas suas
antes de fechar o texto: 1. «Moeda do cliente» é sempre real …? 2. O filtro … vale só para a
exportação ou também para a lista?" — and under it, in the same message, the platform staged a
proposal with a yes button that had already chosen both answers for the person: the filter for
the export only, values "na moeda do cliente da reserva". It happened three times in one sitting.

THE SIGNAL, AND WHY IT IS THE DRAFTER'S. The role's prose is a model's sentence, and reading "I need
answers first" out of it would be a word list over a sentence, which ADR-0028 refused for a yes.
The drafter already writes, in a field, what it could not determine (`questions`, kept in the
requirement as open questions). It now writes apart what it CANNOT WRITE WITHOUT
(`RequirementDraft.ask_first`): a question whose answer would change `must_be_true`. The platform
reads the field, never the prose — any entry and nothing is staged — as the card's loop already
holds a card whose judge has a question (#383).

THE RULE THIS FILE HOLDS, swept over every drafter a turn reaches — the requirement, the requested
card, the defect:
  1. a drafter that says its text waits on an answer stages nothing, and the person is asked;
     what was already on the table for them stays there;
  2. every question the draft waits on reaches the person once: listed under the role's reply
     unless the reply already carries it — read per question off the field, never by a scan of
     the prose for a question mark (review of #721);
  3. a requirement staged with questions still open says, under it, that they can be answered
     after the text;
  4. the drafter is told what `ask_first` is for, and its answer is read.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import openfactory.product.channel as pc
from openfactory.contracts import AgentRunResult
from openfactory.product.role import _DRAFT_SCHEMA, ProductAnswer, ProductRole, RequirementDraft
from openfactory.product.voice import asked_first, card_needs, still_open
from tests.test_a_card_is_drafted_and_judged_before_the_yes import GOOD, _judge_says, _World
from tests.test_a_card_is_drafted_and_judged_before_the_yes import (  # noqa: F401
    _clean as _clean,  # the fixture, reused
)
from tests.test_a_redraft_is_written_from_the_conversation_and_the_draft_it_replaces import (
    ADJUSTED,
    ASKED,
    CARD,
    CONVERSATION,
)
from tests.test_confirmation_by_click import ADMIN, KEY, _project
from tests.the_chat_turn import chat_turn

QUESTIONS = ["A moeda do cliente é sempre real, ou há clientes em outras moedas?",
             "O filtro por período vale só para a exportação ou também para a lista?"]
ASKING = ("Preciso de duas respostas suas antes de fechar o texto:\n1. " + QUESTIONS[0] + "\n2. "
          + QUESTIONS[1])
WRITTEN = RequirementDraft(title="Exportar as reservas em CSV pela tela de reservas",
                           must_be_true=["um botão baixa um CSV com as reservas do período"])
WAITS = WRITTEN.model_copy(update={"ask_first": QUESTIONS})


class _Asking(_World):
    """The card loop of `_World`, a requirement drafter beside it, and the role's reply scripted."""

    def __init__(self, gesture: dict, *, reply: str = ASKING, drafts=(WAITS,), judge=None):
        super().__init__(CARD, CARD, CARD, CARD, judge=judge)
        self.gesture, self.reply, self.drafts = gesture, reply, list(drafts)

    def answer(self, question, **_):
        return SimpleNamespace(**{"ok": True, "decisions": [], "gesture": "", "violates": None,
                                  "is_ticket": False, "is_defect": False, "is_request": False,
                                  "ticket_title": "", "text": self.reply, **self.gesture})

    def draft(self, request, **_):
        return ProductAnswer(ok=True, draft=self.drafts.pop(0))


#: drafter → the role's gesture, and how that drafter says its text waits on an answer
WAITING = {
    "requirement": lambda: _Asking({"is_request": True}),
    "card": lambda: _Asking({"is_ticket": True, "ticket_title": CARD["title"]},
                            judge=lambda p: _judge_says(2, ask=QUESTIONS[0])),
    "defect": lambda: _Asking({"is_defect": True}, judge=lambda p: _judge_says(2, ask=QUESTIONS[0])),
}


@pytest.fixture
def conversation(monkeypatch):
    from openfactory.memory import transcript

    monkeypatch.setattr(transcript, "render", lambda *a, **k: CONVERSATION)


def _waiting():
    return pc.find_waiting(KEY, KEY, person=ADMIN)[1]


# ── 1. nothing staged, the person asked ────────────────────────────────────────────────────────

@pytest.mark.parametrize("drafter", sorted(WAITING))
def test_a_drafter_whose_text_waits_on_an_answer_stages_nothing_and_asks(drafter, conversation):
    said = str(chat_turn(_project(), text=ASKED, user=ADMIN, thread=KEY, module=WAITING[drafter]()))

    assert _waiting() is None, _waiting()
    assert QUESTIONS[0] in said, said


def test_TODAYS_RUN_the_requirement_is_not_proposed_under_the_questions_it_needs(conversation):
    said = str(chat_turn(_project(), text=ASKED, user=ADMIN, thread=KEY,
                         module=_Asking({"is_request": True})))

    assert _waiting() is None
    assert said == f"{ASKING}\n\n" + asked_first(questions=[], language="pt-BR"), said


def test_what_was_on_the_table_stays_when_its_redraft_waits_on_an_answer(conversation):
    world = _Asking({"is_request": True}, reply="Certo.", drafts=(WRITTEN, WAITS))
    world.confirmed = lambda reply, *, proposal: "neither"
    chat_turn(_project(), text=ASKED, user=ADMIN, thread=KEY, module=world)
    staged = _waiting()

    chat_turn(_project(), text=ADJUSTED, user=ADMIN, thread=KEY, module=world)

    assert _waiting() is not None and _waiting()["answer"].draft == staged["answer"].draft


# ── 2. the questions, listed when the reply did not ask them ───────────────────────────────────

def test_the_questions_are_listed_when_the_reply_did_not_ask_them(conversation):
    said = str(chat_turn(_project(), text=ASKED, user=ADMIN, thread=KEY,
                         module=_Asking({"is_request": True}, reply="Certo, entendi o pedido.")))

    assert said.endswith(asked_first(questions=QUESTIONS, language="pt-BR")), said
    assert f"1. {QUESTIONS[0]}" in said and f"2. {QUESTIONS[1]}" in said


#: What the role may write above a draft that waits on an answer: asking nothing, asking something
#: else, asking one of the drafter's questions — in its own case, spacing and punctuation — or all.
REPLIES = {
    "asks nothing": "Certo, entendi o pedido.",
    "asks something else": "Entendi o pedido. Posso seguir?",
    "quotes another question": ('Entendi. (O requisito 2 pergunta "a moeda e sempre o real?" — vou '
                                "conferir.)"),
    "asks one of them": "Preciso saber: " + QUESTIONS[0],
    "asks one, in its own case and spacing": ("preciso saber:  "
                                              + QUESTIONS[1].upper().rstrip("?") + "."),
    "asks all of them": ASKING,
}


def _flat(text: str) -> str:
    return " ".join(text.casefold().split())


@pytest.mark.parametrize("reply", sorted(REPLIES))
def test_REVIEW_OF_721_every_question_the_draft_waits_on_reaches_the_person_once(reply,
                                                                               conversation):
    """Read off the FIELD, per question: a reply that asked something else, or one of the two, left
    the person with 0 or 1 of the questions the hold waits on, and the hold looped. Each question
    the drafter cannot write without is shown — once: listed unless the reply already carries it."""
    said = str(chat_turn(_project(), text=ASKED, user=ADMIN, thread=KEY,
                         module=_Asking({"is_request": True}, reply=REPLIES[reply])))

    assert _waiting() is None
    for question in QUESTIONS:
        shown = _flat(said).count(_flat(question).rstrip("?"))
        assert shown == 1, (reply, question, shown, said)


# ── 3. a draft staged with questions open ──────────────────────────────────────────────────────

def test_a_staged_requirement_says_what_it_leaves_open_can_be_answered_after_it(conversation):
    open_ = WRITTEN.model_copy(update={"questions": ["Qual o nome do arquivo?"]})

    said = chat_turn(_project(), text=ASKED, user=ADMIN, thread=KEY,
                     module=_Asking({"is_request": True}, reply="Certo.", drafts=(open_,)))

    assert _waiting() is not None
    assert str(getattr(said, "text", said)).endswith(
        still_open(questions=["Qual o nome do arquivo?"], language="pt-BR"))


def test_a_staged_requirement_with_nothing_open_says_nothing_of_it(conversation):
    said = chat_turn(_project(), text=ASKED, user=ADMIN, thread=KEY,
                     module=_Asking({"is_request": True}, reply="Certo.", drafts=(WRITTEN,)))

    assert _waiting() is not None
    assert "Fica em aberto" not in str(getattr(said, "text", said))


# ── 4. the drafter is told, and its answer read ────────────────────────────────────────────────

class _Harness:
    name = "recording"

    def __init__(self, said: str) -> None:
        self.said, self.prompts = said, []

    def ask(self, *, sandbox, workspace, prompt, phase="ask"):
        self.prompts.append(prompt)
        return AgentRunResult(ok=True, summary=self.said)


def test_the_drafter_is_told_what_ask_first_is_for_and_its_answer_is_read():
    from openfactory.adapters.sandbox.base import Workspace

    harness = _Harness(WAITS.model_dump_json())
    answer = ProductRole(harness).draft(
        sandbox=SimpleNamespace(run=lambda **k: (0, "")),
        workspace=Workspace(path="/tmp", branch="main", base_branch="main"), request=ASKED)

    assert '"ask_first": [str]' in _DRAFT_SCHEMA
    assert "`ask_first` IS FOR WHAT YOU CANNOT WRITE WITHOUT" in harness.prompts[0]
    assert answer.draft.ask_first == QUESTIONS


def test_a_card_that_waits_on_an_answer_asks_the_judges_question(conversation):
    """The card's loop held this before #670 (#383); it is in the sweep so the family stays one."""
    said = str(chat_turn(_project(), text=ASKED, user=ADMIN, thread=KEY, module=WAITING["card"]()))

    assert card_needs(ask=QUESTIONS[0], language="pt-BR") in said
    assert GOOD["title"] not in said
