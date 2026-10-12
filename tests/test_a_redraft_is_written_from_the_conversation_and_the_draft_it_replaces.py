"""A redraft is written from the conversation and the draft it replaces, never from the adjustment
alone (#661).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, C-03). The owner asked for a CSV export of
the reservations, filtered by period in the API, in the client's currency. Before any yes they
wrote "Ah, mudei de ideia num ponto: o filtro também tem que ser por situação … Pode ajustar a
proposta?". The role answered "Ajustei a proposta … O resto da proposta continua igual"; under
that, the platform staged "Filtrar a lista de reservas por período e por situação" — no file, no
currency — because the requirement's drafter was handed `ex.text`, the adjustment, and nothing
else. The person confirmed what they read as an adjustment, and the export was in no requirement.
#383 had given the card's drafter the conversation; the requirement's never had it, and neither
drafter was shown the draft it was replacing.

THE RULE THIS FILE HOLDS, swept over EVERY drafter a turn reaches — the requirement
(`module.draft`), the requested card and the defect (`module.compose_card`) — and over both ways
an adjustment arrives (read as neither yes nor no, so the draft is still on the table; or read as
a no, which takes it off):
  1. the drafter receives the conversation, the role's reply, and the draft it replaces, whole;
  2. what reaches the model says so: each drafter's prompt carries the three, and the rule to keep
     what the person did not change;
  3. a first draft, with nothing on the table, is written from the conversation too, and is told
     it replaces nothing;
  4. the module and the card loop carry all of it to the model, not only the engine's call.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import openfactory.product.channel as pc
from openfactory.contracts import AgentRunResult
from openfactory.product.cards import REPLACING_RULE, draft_prompt, load_template
from openfactory.product.role import ProductAnswer, ProductRole, RequirementDraft
from tests.test_a_card_is_drafted_and_judged_before_the_yes import GOOD, PT, _World
from tests.test_a_card_is_drafted_and_judged_before_the_yes import (  # noqa: F401
    _clean as _clean,  # the fixture, reused
)
from tests.test_confirmation_by_click import ADMIN, KEY, _project
from tests.the_chat_turn import chat_turn

ASKED = ("Quero que o atendimento consiga exportar as reservas em CSV pela tela de reservas. O "
         "filtro por período tem que rodar na API, e os valores saem na moeda do cliente.")
ADJUSTED = ("Ah, mudei de ideia num ponto: o filtro também tem que ser por situação, além do "
            "período. Pode ajustar a proposta?")
CONVERSATION = (f"## Conversa até aqui (mais antigo primeiro)\n- pessoa: {ASKED}\n"
                "- você: Foi isto que eu entendi — *Exportar as reservas em CSV* …")
FIRST = RequirementDraft(title="Exportar as reservas em CSV pela tela de reservas",
                         why="o atendimento manda a lista ao cliente",
                         must_be_true=["um botão baixa um CSV com as reservas do período",
                                       "os valores saem na moeda do cliente"],
                         out_of_scope=["outros formatos"])
SECOND = RequirementDraft(title="Exportar as reservas em CSV, por período e por situação",
                          must_be_true=["o filtro aceita situação além do período"])
REPLY = "Ajustei a proposta: além do período, filtra por situação. O resto continua igual."
CARD = {**GOOD, "title": "Reservas: exportar a lista em CSV na moeda do cliente",
        "objective": "O atendimento baixa as reservas do período em CSV.",
        "description": "Um botão na tela de reservas baixa um CSV com as reservas do período, "
                       "filtradas na API, com os valores na moeda do cliente.",
        "done_when": ["O CSV traz as reservas do período, com os valores na moeda do cliente"],
        "related": [], "source_quote": "exportar as reservas em CSV pela tela de reservas"}

#: drafter → the gesture the role's answer carries, and what the first draft is known by
DRAFTERS = {
    "requirement": ({"is_request": True}, FIRST.title),
    "card": ({"is_ticket": True, "ticket_title": CARD["title"]}, CARD["title"]),
    "defect": ({"is_defect": True}, CARD["title"]),
}


class _Drafting(_World):
    """`_World`'s real card loop, the requirement's drafter recorded beside it, and the role's
    answer scripted: the same gesture on both turns, its reply the one the run read."""

    def __init__(self, gesture: dict, verdict: str):
        super().__init__(CARD, CARD)
        self.gesture, self.verdict, self.drafted = gesture, verdict, []

    def confirmed(self, reply, *, proposal):
        return self.verdict

    def answer(self, question, **_):
        first = not self.drafted and not self.composed
        return SimpleNamespace(**{"ok": True, "decisions": [], "gesture": "", "violates": None,
                                  "is_ticket": False, "is_defect": False, "is_request": False,
                                  "ticket_title": "", "text": "Certo." if first else REPLY,
                                  **self.gesture})

    def draft(self, request, *, asked_by="", **written_from):
        self.drafted.append({"request": request, **written_from})
        return ProductAnswer(ok=True, draft=FIRST if len(self.drafted) == 1 else SECOND)

    def calls(self) -> list[dict]:
        return self.drafted or self.composed


@pytest.fixture
def conversation(monkeypatch):
    from openfactory.memory import transcript

    monkeypatch.setattr(transcript, "render", lambda *a, **k: CONVERSATION)


def _adjust(drafter: str, verdict: str) -> _Drafting:
    gesture, _known_by = DRAFTERS[drafter]
    world = _Drafting(gesture, verdict)
    chat_turn(_project(), text=ASKED, user=ADMIN, thread=KEY, module=world)
    assert pc.find_waiting(KEY, KEY, person=ADMIN)[1] is not None, "nothing was staged first"
    chat_turn(_project(), text=ADJUSTED, user=ADMIN, thread=KEY, module=world)
    return world


# ── 1. what each drafter receives ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("verdict", ["neither", "reject"], ids=["still-on-the-table", "taken-off"])
@pytest.mark.parametrize("drafter", sorted(DRAFTERS))
def test_TODAYS_RUN_an_adjustment_is_drafted_from_the_conversation_and_the_draft_it_replaces(
        drafter, verdict, conversation):
    world = _adjust(drafter, verdict)

    second = world.calls()[1]
    assert second["request"] == ADJUSTED
    assert "exportar as reservas em CSV" in second.get("conversation", ""), second
    assert second.get("reply", "").startswith("Ajustei a proposta"), second
    assert DRAFTERS[drafter][1] in second.get("replacing", ""), second


def test_the_requirement_it_replaces_reaches_the_drafter_whole(conversation):
    replaced = _adjust("requirement", "neither").drafted[1]["replacing"]

    for kept in (FIRST.title, FIRST.why, *FIRST.must_be_true, *FIRST.out_of_scope):
        assert kept in replaced, (kept, replaced)


@pytest.mark.parametrize("drafter", sorted(DRAFTERS))
def test_a_first_draft_is_written_from_the_conversation_and_replaces_nothing(drafter,
                                                                             conversation):
    world = _Drafting(DRAFTERS[drafter][0], "neither")

    chat_turn(_project(), text=ASKED, user=ADMIN, thread=KEY, module=world)

    [first] = world.calls()
    assert "exportar as reservas em CSV" in first.get("conversation", ""), first
    assert not first.get("replacing"), first


# ── 2. what reaches the model ──────────────────────────────────────────────────────────────────

class _Harness:
    name = "recording"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def ask(self, *, sandbox, workspace, prompt, phase="ask"):
        self.prompts.append(prompt)
        return AgentRunResult(ok=True, summary="ok")


def _requirement_prompt(**written_from) -> str:
    from openfactory.adapters.sandbox.base import Workspace

    harness = _Harness()
    ProductRole(harness).draft(sandbox=SimpleNamespace(run=lambda **k: (0, "")),
                               workspace=Workspace(path="/tmp", branch="main",
                                                   base_branch="main"),
                               request=ADJUSTED, **written_from)
    return harness.prompts[0]


def _card_prompt(**written_from) -> str:
    return draft_prompt(conversation=written_from.get("conversation", ""), request=ADJUSTED,
                        reply=written_from.get("reply", ""), intake="", title="",
                        template=load_template(language=PT), feedback=[], language=PT,
                        replacing=written_from.get("replacing", ""))


@pytest.mark.parametrize("prompt_of", [_requirement_prompt, _card_prompt],
                         ids=["requirement", "card"])
def test_each_drafters_prompt_carries_the_conversation_the_reply_and_the_draft_it_replaces(
        prompt_of):
    prompt = prompt_of(conversation=CONVERSATION, reply=REPLY, replacing="REPLACED-DRAFT")

    for part in ("exportar as reservas em CSV", REPLY, "REPLACED-DRAFT", REPLACING_RULE):
        assert part in prompt, part


@pytest.mark.parametrize("prompt_of", [_requirement_prompt, _card_prompt],
                         ids=["requirement", "card"])
def test_with_nothing_to_replace_no_rule_about_it_is_written(prompt_of):
    assert REPLACING_RULE not in prompt_of(conversation=CONVERSATION, reply=REPLY)


# ── 3. the module and the card loop carry it to the model ──────────────────────────────────────

def test_the_module_hands_the_role_what_the_draft_is_written_from(monkeypatch):
    from openfactory.product.module import ProductModule

    seen = {}

    class _Role:
        def draft(self, *, sandbox, workspace, request, asked_by="", conversation="", reply="",
                  replacing=""):
            seen.update(conversation=conversation, reply=reply, replacing=replacing)
            return ProductAnswer(ok=True, draft=SECOND)

    module = ProductModule.__new__(ProductModule)
    monkeypatch.setattr(module, "context", lambda: SimpleNamespace(available=True), raising=False)
    monkeypatch.setattr(module, "_workspace", lambda: (None, None), raising=False)
    monkeypatch.setattr(module, "_role", lambda: _Role(), raising=False)

    module.draft(ADJUSTED, asked_by=ADMIN, conversation=CONVERSATION, reply=REPLY,
                 replacing="REPLACED-DRAFT")

    assert seen == {"conversation": CONVERSATION, "reply": REPLY, "replacing": "REPLACED-DRAFT"}


def test_the_module_hands_the_card_loop_the_draft_it_replaces(monkeypatch):
    from openfactory.product import cards
    from openfactory.product.module import ProductModule

    seen = {}
    monkeypatch.setattr(cards, "load_template", lambda docs, kind, language=None: "")
    monkeypatch.setattr(cards, "load_rubric", lambda docs: None)
    monkeypatch.setattr(cards, "compose", lambda **kw: seen.setdefault("replacing", kw["replacing"]))
    module = ProductModule.__new__(ProductModule)
    module.project = SimpleNamespace(name="p", language="pt-BR")
    module._agent = SimpleNamespace(name="engine")
    module._handed_card_judge = None
    monkeypatch.setattr(module, "context",
                        lambda: SimpleNamespace(available=True, docs_path=""), raising=False)
    monkeypatch.setattr(module, "_card_judge", lambda harness: None, raising=False)

    module.compose_card(request=ADJUSTED, replacing="REPLACED-CARD")

    assert seen == {"replacing": "REPLACED-CARD"}


def test_the_card_loop_writes_the_draft_it_replaces_into_the_drafters_prompt():
    from openfactory.product.cards import compose, load_rubric
    from tests.test_a_card_is_drafted_and_judged_before_the_yes import _Script

    script = _Script(CARD)

    compose(draft=script, judge=None, rubric=load_rubric(), template=load_template(language=PT),
            conversation=CONVERSATION, request=ADJUSTED, reply=REPLY, replacing="REPLACED-CARD")

    assert "REPLACED-CARD" in script.prompts[0] and REPLACING_RULE in script.prompts[0]
