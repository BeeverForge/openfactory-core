"""Closing, correcting and aligning a card are acts the role proposes, and a breakdown and a refine
wait for a yes like every other write (#565, slices b and c).

THE RUN (v0.5.0-rc.1). "pode fechar o final 9" matched no row of `intents.py` — the close pattern
wanted "fecha o #N" — and the role, which understood it and could read #1000009 on the board, had
no act to hand it to: it told the person that only they could close a card. And "ok, pode escrever
o card e colocar no backlog", said of an agreed requirement whose breakdown was already running,
filed a free-standing card beside it: the breakdown was the one write that ran on a matched
sentence alone, so nothing asked first, and nothing proposed the act the person meant.

Now each act on a card is a marker the role writes — `[[FECHAR: <card>; em favor de <card>; …]]`,
`[[CORRIGIR: <card>; …]]`, `[[TITULO: <card>; …]]`, `[[ALINHAR: <card>; REQ-N]]`,
`[[REFINAR: <card>]]` — with the card read as the board spells it (`contracts.refs.REF_AS_WRITTEN`),
and the breakdown is `[[QUEBRAR: REQ-N]]`. Each is staged by the branch the pattern reached
(`engine._run_intent`), and the yes executes it (`confirm._EXECUTORS`) — the breakdown and the
refine included, which wrote before the person could say anything.

WHAT IS DRIVEN HERE. The conversation itself, `engine.turn` through `chat_turn`, with a module
double that answers through `read_answer` — the model's text read the way the turn reads it.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import openfactory.product.channel as pc
from openfactory.product import breaking
from openfactory.product.intents import match_intent
from openfactory.product.role import CARD_ACTS, read_answer
from tests.the_chat_turn import chat_turn

ADMIN, CLIENT, KEY = "UADM", "UCLI", "C1"
ROOT = Path(__file__).resolve().parents[1]


class _Req:
    def __init__(self, number=66, status="accepted"):
        self.number, self.status = number, status
        self.title, self.slug, self.path = "Versões entregues", "versoes", "0066-versoes.md"

    @property
    def is_live(self):
        return self.status not in ("superseded", "dropped")

    @property
    def is_promise(self):
        return self.status == "accepted"


class _Role:
    """The product module as the turn sees it: one requirement in the corpus, the model's text read
    by the role's own parser, and every write recorded — none of them may run before a yes."""

    def __init__(self, said: str, req: _Req | None = None) -> None:
        self.said, self.reqs, self.wrote = said, [req or _Req()], []

    def context(self):
        reqs = self.reqs

        class _Corpus:
            def by_number(self, n):
                return next((r for r in reqs if r.number == n), None)

        return SimpleNamespace(available=True, corpus=_Corpus(), reason="")

    def answer(self, question, **_):
        return read_answer(self.said)

    def _wrote(self, verb, number, **kw):
        self.wrote.append((verb, number, kw))
        return SimpleNamespace(ok=True, detail="", existed=False, ref=f"#{number}")

    def close_card(self, number, **kw):
        return self._wrote("close_card", number, **kw)

    def correct_card(self, number, **kw):
        return self._wrote("correct_card", number, **kw)

    def align_card(self, number, **kw):
        return self._wrote("align_card", number, **kw)

    def refine(self, number, **kw):
        return self._wrote("refine", number, **kw)

    def what_only_it_carries(self, number, other):
        return ""

    def break_down(self, *a, **k):  # pragma: no cover — reaching it is the defect
        raise AssertionError("the conversation ran the breakdown in its own process")

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

    def __init__(self, accept_on_behalf=False):
        self.product = SimpleNamespace(admins=[ADMIN], agent_name="Nina", docs_repo="a/docs",
                                       channel_id=KEY, enabled=True, docs_branch="main",
                                       accept_on_behalf=accept_on_behalf)


@pytest.fixture(autouse=True)
def _clean_stage(monkeypatch):
    from openfactory.memory import transcript
    from openfactory.product import staging as _staging

    monkeypatch.setattr(_staging, "_PENDING", {})
    monkeypatch.setattr(_staging, "_EXPIRED_TOMBSTONES", {})
    monkeypatch.setattr(transcript, "record", lambda *a, **k: "")
    monkeypatch.setattr(transcript, "recent", lambda *a, **k: [])
    yield


@pytest.fixture
def started(monkeypatch):
    """`breaking.start_now`, recorded: the breakdown starts on the worker, never in the turn."""
    seen = SimpleNamespace(calls=[])

    def _start(project, number, **kw):
        seen.calls.append((number, kw))
        return breaking.STARTED

    monkeypatch.setattr(breaking, "start_now", _start)
    return seen


def _say(role: _Role, text: str, user: str = ADMIN, project: _Project | None = None) -> str:
    return str(chat_turn(project or _Project(), text=text, user=user, thread=KEY, channel=KEY,
                         module=role) or "")


def _staged() -> dict | None:
    return pc.find_waiting(KEY, KEY)[1]


# ── the run ─────────────────────────────────────────────────────────────────────────────────────

def test_TODAYS_RUN_closing_the_one_ending_in_9_is_proposed_staged_and_closed_on_a_yes():
    role = _Role("Fecho o #1000009, o que termina em 9.\n[[FECHAR: #1000009]]")

    asked = _say(role, "pode fechar o final 9")

    staged = _staged()
    assert staged and staged["kind"] == "close" and staged["number"] == "1000009", (staged, asked)
    assert asked.startswith("Fecho o #1000009, o que termina em 9."), asked
    assert "[[" not in asked and "só você" not in asked, asked
    assert role.wrote == [], "the card was closed before anybody said yes"

    _say(role, "sim")

    assert role.wrote == [("close_card", "1000009",
                           {"actor": ADMIN, "in_favour_of": None, "reason": ""})]
    assert _staged() is None


def test_TODAYS_RUN_writing_the_card_of_an_agreed_requirement_is_its_breakdown_on_a_yes(started):
    """Never a free-standing card: an agreed requirement's cards come from its breakdown, which
    the role proposes, and which waits for the yes like every other write."""
    role = _Role("Os cards do 66 vêm da quebra dele.\n[[QUEBRAR: REQ-0066]]")

    asked = _say(role, "ok, pode escrever o card e colocar no backlog")

    staged = _staged()
    assert staged and staged["kind"] == "breakdown" and staged["number"] == 66, (staged, asked)
    assert asked.startswith("Os cards do 66 vêm da quebra dele."), asked
    assert started.calls == [] and role.wrote == [], "it started before the person's yes"

    done = _say(role, "sim")

    ((number, kw),) = started.calls
    assert number == 66 and kw["asked_for"] is True and kw["actor"] == ADMIN, kw
    assert done.startswith("Comecei a quebrar o requisito 66"), done


# ── what the breakdown checks before it asks ───────────────────────────────────────────────────

def test_a_breakdown_of_a_requirement_not_agreed_is_refused_before_it_is_asked(started):
    from openfactory.product.module import _not_a_promise

    req = _Req(status="proposed")
    asked = _say(_Role("Vou preparar.\n[[QUEBRAR: REQ-0066]]", req), "quebra o 66")

    assert asked == "Vou preparar.\n\n" + _not_a_promise(66, req, language="pt-BR"), asked
    assert _staged() is None and started.calls == []


def test_a_breakdown_of_a_requirement_the_base_does_not_have_is_said(started):
    from openfactory.product.voice import requirement_not_found

    asked = _say(_Role("Vou preparar.\n[[QUEBRAR: REQ-0099]]"), "quebra o 99")

    assert asked == "Vou preparar.\n\n" + requirement_not_found(number=99, language="pt-BR"), (
        asked)
    assert _staged() is None and started.calls == []


# ── each act on a card, staged with what its marker carries ────────────────────────────────────

def test_a_close_in_favour_of_another_card_carries_the_survivor_and_their_reason():
    role = _Role("Certo.\n[[FECHAR: #511; em favor de #288; o cliente pediu o mesmo no 288]]")

    _say(role, "o 511 é o mesmo pedido do 288, pode fechar")

    staged = _staged()
    assert (staged["kind"], staged["number"], staged["in_favour_of"]) == ("close", "511", "288")
    assert staged["reason"] == "o cliente pediu o mesmo no 288", staged


@pytest.mark.parametrize("card", ["CONT-412", "acme/web#1"])
def test_a_card_is_read_as_the_board_spells_it(card):
    _say(_Role(f"Certo.\n[[FECHAR: {card}]]"), f"pode fechar o {card}")

    assert _staged()["number"] == card, _staged()


def test_a_new_title_is_a_correction_of_the_title_alone():
    role = _Role("Certo.\n[[TITULO: #512; Relatório semanal]]")

    _say(role, "o título do 512 devia ser Relatório semanal")
    staged = _staged()
    assert (staged["kind"], staged["new_title"], staged["text"]) == (
        "correct", "Relatório semanal", ""), staged

    _say(role, "sim")
    assert role.wrote == [("correct_card", "512",
                           {"actor": ADMIN, "text": "", "title": "Relatório semanal"})]


def test_an_alignment_names_the_card_and_the_requirement():
    role = _Role("Certo.\n[[ALINHAR: #288; REQ-0066]]")

    _say(role, "o 288 tem que seguir o requisito 66")
    staged = _staged()
    assert (staged["kind"], staged["number"], staged["requirement"]) == ("align", "288", 66)

    _say(role, "sim")
    assert role.wrote == [("align_card", "288", {"requirement": 66, "actor": ADMIN})]


def test_a_refine_waits_for_the_yes_and_then_writes():
    role = _Role("Certo.\n[[REFINAR: #412]]")

    asked = _say(role, "escreve os critérios do 412")

    assert _staged()["kind"] == "refine" and role.wrote == [], asked
    _say(role, "sim")
    assert role.wrote == [("refine", "412", {"actor": ADMIN})]


def test_somebody_off_the_admin_list_stages_it_for_the_admins():
    """Where an admin's yes counts on the requester's behalf, the admins are named under it."""
    role = _Role("Certo.\n[[REFINAR: #412]]")

    asked = _say(role, "escreve os critérios do 412", user=CLIENT,
                 project=_Project(accept_on_behalf=True))

    assert _staged()["kind"] == "refine" and role.wrote == [], asked
    assert asked.endswith(f"({ADMIN}: escrever o que ele precisa cumprir precisa da sua "
                          "confirmação.)"), asked



@pytest.mark.parametrize(("marker", "text"), [
    ("[[QUEBRAR: REQ-0066]]", "quebra o 66"),
    ("[[REFINAR: #412]]", "escreve os critérios do 412"),
], ids=["breakdown", "refine"])
def test_REVIEW_OF_634_a_yes_nobody_can_give_is_never_asked_for(marker, text, started):
    """Off the admin list, where no admin's yes counts for the requester (no `accept_on_behalf`),
    a staged question would wait for a yes nobody can give, and their own is refused: refused at
    once instead, naming who can, as before it was staged."""
    from openfactory.product.module import unauthorized_message

    project = _Project()
    role = _Role("Certo.\n" + marker)

    asked = _say(role, text, user=CLIENT, project=project)

    assert asked == "Certo.\n\n" + unauthorized_message(project), asked
    assert _staged() is None and started.calls == [] and role.wrote == []


def test_a_breakdown_off_the_admin_list_is_staged_for_the_admins_where_their_yes_counts(started):
    asked = _say(_Role("Certo.\n[[QUEBRAR: REQ-0066]]"), "quebra o 66", user=CLIENT,
                 project=_Project(accept_on_behalf=True))

    assert _staged()["kind"] == "breakdown" and started.calls == [], asked
    assert f"({ADMIN}: " in asked and "confirmação" in asked, asked

# ── one act per reply, one way in ───────────────────────────────────────────────────────────────

def test_one_act_per_reply_the_first_is_staged():
    answer = read_answer("Certo.\n[[FECHAR: #511]]\n[[ALINHAR: #288; REQ-6]]")

    assert answer.gesture == "close" and answer.gesture_args == {"number": "#511"}, answer


@pytest.mark.parametrize("sentence", [
    "pode fechar o final 9", "fecha o #511", "corrige o #512: o relatório é semanal",
    "alinha o #288 ao requisito 6", "refina o #12", "quebra o requisito 8 em tarefas",
    "ok, pode escrever o card e colocar no backlog"])
def test_no_sentence_reaches_an_act_on_a_card_or_a_breakdown(sentence):
    assert match_intent(sentence) is None, (sentence, match_intent(sentence))


def test_a_reply_with_no_marker_stages_nothing():
    role = _Role("Posso fechar o #511, se você quiser.")

    _say(role, "fecha o #511")

    assert _staged() is None and role.wrote == []


def test_no_write_on_a_card_or_a_breakdown_runs_in_the_turn():
    """D17: what wrote on the match alone — `module.break_down`, `module.refine` — and every write
    on a card is reached through the yes (`confirm._EXECUTORS`) and nowhere in the engine."""
    src = (ROOT / "openfactory" / "product" / "engine.py").read_text(encoding="utf-8")

    for call in ("module.break_down(", "module.refine(", "module.close_card(",
                 "module.correct_card(", "module.align_card("):
        assert call not in src, f"{call} is reached in the turn, before a yes"


def test_the_close_instruction_refuses_a_question_and_a_negation():
    """What the pattern's negators and its question test refused — "não fecha o #511", "fecha o
    #511?" — is the role's to refuse now, and its instruction says so (#161's claim, carried)."""
    src = (ROOT / "openfactory" / "product" / "role.py").read_text(encoding="utf-8")
    taught = src[src.index('"IF THEY ASK TO CLOSE A CARD'):]
    # the paragraph as the model reads it: the source's adjacent string pieces joined
    taught = re.sub(r'"\s*\n\s*f?"', "", taught[:taught.index('"IF THEY CORRECT WHAT A CARD')])

    assert "for a question about a card, nor for one they say NOT to close" in taught, taught


def test_every_card_act_is_named_as_the_board_spells_it():
    """The card in each marker is read with `REF_AS_WRITTEN` — the board's spelling, never the last
    digits a person said."""
    from openfactory.contracts.refs import REF_AS_WRITTEN

    for marker, pattern, _gesture, _intent in CARD_ACTS:
        assert REF_AS_WRITTEN in pattern.pattern, marker
