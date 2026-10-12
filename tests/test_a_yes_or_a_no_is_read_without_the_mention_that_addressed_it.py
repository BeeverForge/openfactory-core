"""A yes or a no is read without the mention that addressed it (#667).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, C-13). In a project's room the panel writes
`@po ` in front of every message (`api/panel.html::pchatAddressed`), so a late "sim" reached the
core as "@po sim". The word list wants every word catalogued, and `po` is not: `is_yes` and
`is_no` both said False, the expiry notice the platform had just written down was never said, and
the "sim" went to the role as an ordinary message — which proposed the note again, in the late
person's name, for a yes nobody could give.

THE RULE THIS FILE HOLDS:
  1. every word and phrase of the assent catalogue, and every opener of a rejection, is read the
     same with every mention the panel can produce — the prefix its own code writes, and each
     handle it reads as the role, before or after, with or without a vocative comma. The mentions
     are READ FROM THE PANEL'S CODE, not listed here, so a new handle falls under the sweep;
  2. a mention asserts nothing: a mention alone is no yes, and it does not make a question or a
     hedge into one; a word joined to an `@` (an address) is not a mention;
  3. ONLY THE ROLE'S ADDRESS IS READ PAST (review of #667). A mention of a person stays where it
     is: "@ana sim" is somebody answering Ana, and every assent and every rejection addressed to a
     person — alone, or behind the panel's own prefix — is read as neither, because a misread yes
     executes what that person has waiting (#272);
  4. a late yes or no that arrives addressed to the role, by a handle or by its name, hears that
     its proposal expired.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

import openfactory.product.channel as pc
from openfactory.api.product_chat import HANDLES as PANEL_SERVER_HANDLES
from openfactory.language import assent
from openfactory.product.addressing import HANDLES, without_the_roles_address
from openfactory.product.staging import NO_ALONE, NO_OPENERS, is_no, is_yes
from openfactory.product.voice import proposal_expired
from tests.test_sweep_client_surface import _Project, _QuietModule
from tests.the_chat_turn import chat_turn

PANEL = Path(__file__).resolve().parents[1] / "openfactory" / "api" / "panel.html"
PROJECT = _Project()
AGENT = PROJECT.product.agent_name
#: People in the room, as a room names them — never the role
PEOPLE = ("ana", "Ana", "joão.silva", "dev")


def _the_panels_addressing() -> tuple[str, tuple[str, ...]]:
    """`(prefix, handles)` as `pchatAddressed` writes and reads them."""
    body = re.search(r"function pchatAddressed\(q\)\{(.*?)\n\}", PANEL.read_text(),
                     re.DOTALL).group(1)
    prefix = re.search(r"`([^`$]*)\$\{q\}`", body).group(1)
    handles = tuple(re.search(r"@\(([\w|]+)\)", body).group(1).split("|"))
    return prefix, handles


PREFIX, PANEL_HANDLES = _the_panels_addressing()


def _addressed(said: str) -> list[str]:
    """`said` as every mention the panel can produce would carry it."""
    names = (*PANEL_HANDLES, *HANDLES, AGENT, AGENT.lower())
    return [PREFIX + said,
            *(form.format(name=name, said=said) for name in names
              for form in ("@{name} {said}", "@{name}, {said}", "@{name}: {said}",
                           "{said} @{name}", "{said}, @{name}"))]


def test_the_panel_the_server_and_the_core_read_the_same_handles():
    assert set(PANEL_HANDLES) == set(HANDLES) == set(PANEL_SERVER_HANDLES), PANEL_HANDLES
    assert PREFIX.startswith("@") and PREFIX[1:].strip() in HANDLES, PREFIX


# ── 1. the catalogue, addressed ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said", sorted(assent.core_words() | assent.core_phrases()))
def test_every_assent_is_a_yes_however_it_is_addressed(said):
    missed = [m for m in _addressed(said) if not is_yes(m, project=PROJECT)]

    assert not missed, missed


@pytest.mark.parametrize("said", [*NO_OPENERS, NO_ALONE])
def test_every_rejection_is_a_no_however_it_is_addressed(said):
    missed = [m for m in _addressed(said) if not is_no(m, project=PROJECT)]

    assert not missed, missed


def test_TODAYS_RUN_the_late_yes_as_the_room_sent_it():
    assert is_yes("@po sim") and not is_no("@po sim")
    assert is_no("@po não") and not is_yes("@po não")


# ── 2. a mention asserts nothing ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said", ["@po", PREFIX, "@po sim?", "@po sim, mas e o prazo",
                                  "@po o que é isso", "@po no sistema de férias"])
def test_a_mention_makes_nothing_a_yes_or_a_no(said):
    assert not is_yes(said) and not is_no(said), said


def test_a_word_joined_to_an_at_sign_is_an_address_not_a_mention():
    for address in ("a@po.com sim", "vale@po sim", "sim@po"):
        assert without_the_roles_address(address, PROJECT) == address
        assert not is_yes(address, project=PROJECT), address


# ── 3. only the role's address ──────────────────────────────────────────────────────────────────

def _to_a_person(said: str) -> list[str]:
    """`said` addressed to a person in the room: typed alone, and as the panel sends it."""
    return [form.format(person=person, said=said) for person in PEOPLE
            for form in ("@{person} {said}", "@{person}, {said}", PREFIX + "@{person} {said}")]


@pytest.mark.parametrize("said", sorted(assent.core_words() | assent.core_phrases()))
def test_REVIEW_OF_667_an_assent_to_a_person_is_no_yes_to_the_role(said):
    misread = [m for m in _to_a_person(said) if is_yes(m, project=PROJECT) or is_no(m, project=PROJECT)]

    assert not misread, misread


@pytest.mark.parametrize("said", [*NO_OPENERS, NO_ALONE])
def test_REVIEW_OF_667_a_rejection_to_a_person_is_no_no_to_the_role(said):
    misread = [m for m in _to_a_person(said) if is_no(m, project=PROJECT) or is_yes(m, project=PROJECT)]

    assert not misread, misread


def test_the_roles_name_is_its_address_only_where_the_project_names_it():
    assert is_yes(f"@{AGENT} sim", project=PROJECT)
    assert not is_yes(f"@{AGENT} sim"), "without a project only the handles name the role"
    assert is_yes("@Nína sim", project=PROJECT), "accents are not what names the role"


# ── 4. the late yes, through the turn ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("late", ["@po sim", "@po não", "@po, pode seguir", f"@{AGENT} sim"])
def test_a_late_answer_addressed_to_the_role_hears_that_its_proposal_expired(late):
    project, module = PROJECT, _QuietModule()
    pc.remember("C1", {"kind": "accept", "number": 3, "channel": "C1"})
    pc._PENDING["C1"]["staged_at"] = time.time() - pc.PROPOSAL_TTL_SECONDS - 1

    reply = chat_turn(project, text=late, user="UADM", thread="C1", channel="C1", module=module)

    assert reply == proposal_expired(language="pt-BR"), reply
    assert module.accepted_with is None
