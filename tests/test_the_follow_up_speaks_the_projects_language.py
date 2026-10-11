"""What a person is told about a delivery's answer, and the reminder to give one, speak the
project's language (#535).

`followup.accepted_text`, `rejected_text` and `acceptance_chase_text` were Portuguese whatever the
project spoke: an English client who said "yes, it works" was thanked with "Ótimo — considero
encerrado então", and reminded with "voltando no que te entreguei". They take the language now, the
turn and the round hand it over, and the words that READ the answer are declared recognisers with
English beside the Portuguese.
"""

from __future__ import annotations

import pytest

from openfactory.memory.ledger import ACCEPTANCE, open_loop
from openfactory.product import followup
from tests.test_no_portuguese_is_welded_into_the_core import is_portuguese

REQUIREMENT = open_loop(ACCEPTANCE, "7", owner="product", ts="t")
DEFECT = open_loop(ACCEPTANCE, "7", owner="product", ts="t", context={"defect": "1"})


def _said(language: str, loop=REQUIREMENT) -> list[str]:
    return [followup.accepted_text(loop, agent_name="Nina", ambiguous=True, language=language),
            followup.rejected_text(loop, agent_name="Nina", ambiguous=True, language=language),
            followup.acceptance_chase_text(loop, mention="@ana", agent_name="Nina",
                                           language=language)]


@pytest.mark.parametrize("loop", [REQUIREMENT, DEFECT], ids=["a requirement", "a defect"])
def test_an_english_project_hears_no_portuguese(loop):
    for text in _said("en", loop):
        assert not is_portuguese(text), text


def test_the_delivery_is_named_in_the_project_s_language():
    english, portuguese = _said("en"), _said("pt-BR")

    assert "(requirement 7)" in english[0] and "(o requisito 7)" in portuguese[0]
    assert "(the problem you reported)" in _said("en", DEFECT)[1]


def test_a_portuguese_project_hears_what_it_always_heard():
    assert _said("pt-BR")[0] == ("Nina: Ótimo — considero encerrado então (o requisito 7). "
                                 "Obrigada por confirmar.")
    assert _said("pt-BR")[2].startswith("Nina: @ana voltando no que te entreguei")
