"""A card the factory took up and has not finished says why it offers no pass (#668).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, row W-04). A hand-made card's job opened its
pull request and handed the card back for a person's merge. The owner, a product admin, opened it on
their page as soon as the board showed it In review: no Send back button, and no sentence saying
why. `adjust_view` had answered a bare `{"offered": False}` — for a gate it read as `not_waiting`,
and for one it could not read at all — though the voice holds a sentence for each.

THE RULE THIS FILE HOLDS, for every reason the gate can give (read from `adjust.WHY`) and every
language the sentences are written in — so a reason or a language added later is held too:
  1. the card's pass control is either offered or explained, never a bare refusal;
  2. a person who may not send the card back is told so, not shown nothing;
  3. an engine error read as "no job ever ran for the card" is said in the log, with what was
     matched.
"""

from __future__ import annotations

import logging

import pytest

from openfactory.product import adjust, voice
from tests.test_the_requester_asks_for_another_pass import ASKER, STRANGER, _module, _waiting_card
from tests.test_the_requester_asks_for_another_pass import (
    _nothing_staged as _nothing_staged,  # noqa: F401 — the fixtures, reused
)
from tests.test_the_requester_asks_for_another_pass import board as board  # noqa: F401
from tests.test_the_requester_asks_for_another_pass import deployment as deployment  # noqa: F401
from tests.test_the_requester_asks_for_another_pass import tracker as tracker  # noqa: F401

REASONS = sorted(adjust.WHY)
LANGS = sorted(voice._ADJUST_SAID[adjust.NOT_WAITING])


def _in(project, lang):
    return project.model_copy(update={"language": lang})


def test_the_reasons_and_the_languages_are_read_from_the_code():
    assert {"not_waiting", "unreachable"} <= set(REASONS) and {"en", "pt-BR"} <= set(LANGS)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("why", REASONS)
def test_TODAYS_RUN_every_reason_the_gate_gives_is_said_on_the_card(why, lang, deployment,
                                                                   tracker, board, monkeypatch):
    card = _waiting_card(tracker, board)
    gate = adjust.Gate(card=card, why=why, passes=2, left=0 if why == adjust.SPENT else 1)
    monkeypatch.setattr(adjust, "pass_gate_of", lambda project, number: gate)

    view = _module(_in(deployment, lang)).adjust_view(card, actor=ASKER)

    assert view["offered"] is False and view.get("note"), (why, lang, view)
    assert view["note"] == voice.adjust_said(why, ref=card, passes=2, language=lang), view


@pytest.mark.parametrize("lang", LANGS)
def test_a_person_who_may_not_send_it_back_is_told_so(lang, deployment, tracker, board):
    card = _waiting_card(tracker, board)

    view = _module(_in(deployment, lang)).adjust_view(card, actor=STRANGER)

    assert view == {"offered": False,
                    "note": voice.adjust_said("not_yours", ref=card, language=lang)}, view


def test_an_engine_error_read_as_no_job_is_said_in_the_log(deployment, monkeypatch, caplog):
    from openfactory.runtime.temporal import standing

    def _never_ran(_run):
        raise RuntimeError("workflow not found for ID: openfactory-acme-7")

    monkeypatch.setattr(standing, "from_a_thread", _never_ran)

    with caplog.at_level(logging.INFO):
        gate = adjust.pass_gate_of(deployment, "7")

    assert gate.why == adjust.NOT_WAITING
    assert "OPENFACTORY_ADJUST_GATE_NO_JOB" in caplog.text and "workflow not found" in caplog.text
