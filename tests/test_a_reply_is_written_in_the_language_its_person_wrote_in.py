"""A reply is written in the language the person wrote in, whatever the project's language is.

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640 row C-11, #655). On a `pt-BR` project, a
person asked the product owner in English what the product does today. The whole answer was in
Portuguese. Every harness prepends `roles.language_directive`, which says to answer in the language
the person wrote in. But the product role's own prompt then carried `voice.language_rules`, "Write in
BRAZILIAN Portuguese (pt-BR) … the reader is Brazilian", with no reply clause. The more specific
rule, written to keep pt-PT away from a Brazilian reader, also kept English away from an English
one.

THE RULE THIS FILE HOLDS:
  1. every language rule a conversation's prompt carries says to answer in the language the person
     wrote in. The project's language, and its dialect, govern what the role says first and its
     replies to anyone who writes in it. This holds for every language the platform has rules for,
     and for one it has none for;
  2. every harness prepends the same clause to every phase a person reads, including a phase this
     tree has never seen. It is one sentence, `roles.REPLY_CLAUSE`, so the two halves cannot
     drift apart;
  3. no prompt writes a language section of its own, so a new builder cannot bring back a hard
     rule without the clause;
  4. a document drafted in a NAMED language (#429: a card is written in the conversation's
     language) is not a reply: it keeps its dialect rule and gets no mirror clause.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from openfactory.adapters.agent import registry
from openfactory.adapters.agent.roles import HUMAN_PHASES, REPLY_CLAUSE
from openfactory.product.role import ProductRole
from openfactory.product.voice import LANGUAGE_RULES, language_rules
from tests.the_tree_read_once import parsed

#: every language the platform has rules for, one it has none for, and none set at all
LANGUAGES = [*sorted(LANGUAGE_RULES), "xx-YY", None]


def _client_prompt(language: str | None) -> str:
    return ProductRole(None, language=language)._prompt("Answer the person.", "corpo",
                                                        audience="client")


# ── 1. the product role's conversation ────────────────────────────────────────────────────────

def test_TODAYS_RUN_an_English_question_on_a_pt_BR_project_is_answered_in_English():
    prompt = _client_prompt("pt-BR")

    assert REPLY_CLAUSE in prompt, "the role is told to write Portuguese with no reply clause"
    assert prompt.index(REPLY_CLAUSE) < prompt.index("BRAZILIAN Portuguese"), (
        "the dialect rule comes before the clause that bounds it, and reads as the whole rule")
    assert "the reader is Brazilian" not in prompt, (
        "the prompt still says who the reader is, and an English writer is not Brazilian")


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_language_rule_a_conversation_gets_says_to_answer_in_the_writers_language(language):
    rule = language_rules(language, replying=True)

    assert rule.startswith("# Language"), rule
    assert REPLY_CLAUSE in rule, f"{language}: no reply clause"
    dialect = language_rules(language).removeprefix("# Language\n\n")
    if dialect:
        assert dialect in rule, f"{language}: the dialect rule was lost"
        assert rule.index(REPLY_CLAUSE) < rule.index(dialect), (
            f"{language}: the dialect rule comes before the clause that bounds it")


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_conversation_prompt_carries_the_clause_once(language):
    prompt = _client_prompt(language)

    assert prompt.count(REPLY_CLAUSE) == 1, prompt.count(REPLY_CLAUSE)


# ── 2. every harness, every phase a person reads ──────────────────────────────────────────────

@pytest.mark.parametrize("kind", sorted(registry.HARNESSES))
@pytest.mark.parametrize("language", ["pt-BR", "en", None])
def test_every_harness_prepends_the_clause_to_every_phase_a_person_reads(kind, language):
    agent = registry._build(kind, language=language)

    for phase in [*sorted(HUMAN_PHASES), "a_phase_this_tree_has_never_seen"]:
        assert REPLY_CLAUSE in agent._localised("the prompt", phase), (kind, phase)


# ── 3. no prompt writes its own language section ──────────────────────────────────────────────

#: the two builders of a language section: the harnesses' directive and the product voice's rules
_BUILDERS = {("openfactory/adapters/agent/roles.py", "language_directive"),
             ("openfactory/product/voice.py", "LANGUAGE_RULES"),
             ("openfactory/product/voice.py", "language_rules")}


def _owners(tree: ast.Module) -> dict[int, str]:
    """Each line of a module → the top-level name it belongs to."""
    owner: dict[int, str] = {}
    for node in tree.body:
        names = ([node.name] if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else
                 [t.id for t in getattr(node, "targets", [getattr(node, "target", None)])
                  if isinstance(t, ast.Name)])
        for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
            owner[line] = names[0] if names else ""
    return owner


def test_no_prompt_writes_a_language_section_of_its_own():
    found = []
    for path in sorted(Path("openfactory").rglob("*.py")):
        tree = parsed(path)
        owner = _owners(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and "# Language" in node.value):
                where = (str(path), owner.get(node.lineno, ""))
                if where not in _BUILDERS:
                    found.append(f"{path}:{node.lineno}")
    assert not found, f"a prompt writes its own language section: {found}"


# ── 4. a document in a named language is not a reply ──────────────────────────────────────────

def test_a_card_drafted_in_the_conversations_language_keeps_its_dialect_and_no_mirror_clause():
    from openfactory.product.cards import draft_prompt

    prompt = draft_prompt(conversation="", request="r", reply="", intake="", title="t",
                          template="", feedback=[], language="pt-BR")

    assert "BRAZILIAN Portuguese" in prompt
    assert REPLY_CLAUSE not in prompt, "a card is not a reply: its language is named (#429)"
