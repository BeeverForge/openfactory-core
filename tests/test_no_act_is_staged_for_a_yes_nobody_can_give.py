"""No act the role proposes is staged for a yes nobody can give (#667, and #638's three acts).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, C-13). `dev`, off the admin list on a
product without `accept_on_behalf`, said "sim" to a note that had expired; the role proposed the
note again and the engine staged it in `dev`'s name, "Fica registrado em seu nome … Confirma?".
`dev`'s yes is refused (a note is not the requester's own), and an admin's counts for them only
with `accept_on_behalf`: the question waited for a yes nobody could give. #634 had settled this for
the breakdown and the refine, by hand, in their two branches; #638 found close, correct and align
with the same shape. Nothing held the rule for the act added next.

THE RULE THIS FILE HOLDS, swept over EVERY act of `role.ACTS` — the table the parser and the engine
both read, so an act added to it falls under the sweep or fails `test_every_act_is_swept`:
  1. off the admin list, where no admin's yes counts for the person who asked: refused at once,
     naming who can (`unauthorized_message`), with the role's own words in front; nothing staged,
     nothing written, nothing started;
  2. where an admin's yes counts for them (`accept_on_behalf`): staged, with the admins named under
     the question;
  3. somebody who may act is asked as before.
"""

from __future__ import annotations

import pytest

from openfactory.product.module import unauthorized_message
from openfactory.product.role import ACTS
from tests.test_closing_correcting_and_aligning_are_acts_the_role_proposes import (
    ADMIN,
    CLIENT,
    _Project,
    _Req,
    _Role,
    _say,
    _staged,
)
from tests.test_closing_correcting_and_aligning_are_acts_the_role_proposes import (  # noqa: F401
    _clean_stage as _clean_stage,  # the fixture, reused
)
from tests.test_closing_correcting_and_aligning_are_acts_the_role_proposes import (  # noqa: F401
    started as started,  # the fixture, reused
)

#: One reply per act: the marker the role writes, and the requirement's status the act needs to
#: be staged at all (`accept` stages only what is not yet agreed; a breakdown, only what is).
EXAMPLES = {
    "agree": ("[[ACORDO: REQ-0066]]", "proposed"),
    "breakdown": ("[[QUEBRAR: REQ-0066]]", "accepted"),
    "drop": ("[[DESCARTE: REQ-0066; o cliente mudou de plano]]", "accepted"),
    "record": ("[[REGISTRO: REQ-0066; o prazo passa a ser sexta]]", "accepted"),
    "fact": ("[[FATO: o cliente quer a exportação pronta antes do fim de novembro]]", "accepted"),
    "close": ("[[FECHAR: #412]]", "accepted"),
    "correct": ("[[CORRIGIR: #412; o relatório é semanal]]", "accepted"),
    "retitle": ("[[TITULO: #412; Relatório semanal]]", "accepted"),
    "align": ("[[ALINHAR: #412; REQ-0066]]", "accepted"),
    "refine": ("[[REFINAR: #412]]", "accepted"),
}
GESTURES = sorted(gesture for _marker, _pattern, gesture, _intent in ACTS)


def _asked(gesture: str, *, user: str, project: _Project):
    marker, status = EXAMPLES[gesture]
    role = _Role("Certo.\n" + marker, _Req(status=status))
    return role, _say(role, "pode fazer isso", user=user, project=project)


def test_every_act_is_swept():
    """An act added to `role.ACTS` without a reply here would escape every row below."""
    assert sorted(EXAMPLES) == GESTURES, (sorted(EXAMPLES), GESTURES)


@pytest.mark.parametrize("gesture", GESTURES)
def test_TODAYS_RUN_off_the_list_where_no_yes_can_count_it_is_refused_at_once(gesture, started):
    project = _Project()

    role, asked = _asked(gesture, user=CLIENT, project=project)

    assert asked == "Certo.\n\n" + unauthorized_message(project), asked
    assert _staged() is None, _staged()
    assert role.wrote == [] and started.calls == []


@pytest.mark.parametrize("gesture", GESTURES)
def test_where_an_admins_yes_counts_it_is_staged_for_them_by_name(gesture, started):
    role, asked = _asked(gesture, user=CLIENT, project=_Project(accept_on_behalf=True))

    assert _staged() is not None, asked
    assert f"({ADMIN}: " in asked and "confirmação" in asked, asked
    assert role.wrote == [] and started.calls == []


@pytest.mark.parametrize("gesture", GESTURES)
def test_somebody_who_may_act_is_asked_as_before(gesture, started):
    role, asked = _asked(gesture, user=ADMIN, project=_Project())

    assert _staged() is not None, asked
    assert f"({ADMIN}: " not in asked and asked != "Certo.\n\n" + unauthorized_message(_Project())
    assert role.wrote == [] and started.calls == []
