"""A front the breakdown meant for another repository of the product never runs in this project's.

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, #665). One product of three local projects;
accepting a requirement broke it into two fronts, one meant for `reservas-api`. The local board keeps
every card in one place, so both were filed on `reservas-web`'s board, and the conversation said so.
Nothing on the card said where the API front belonged beyond the "(API)" a model wrote into its
title. The owner queued it, pre-flight judged it fit, and the job ran in `reservas-web`'s
repository. The agent changed nothing, no pull request was opened, and the park held the
deployment's only job slot for hours.

THE RULE THIS FILE HOLDS, for a product of one project and a product of several:
  1. a front filed outside the repository it belongs to records that repository on the card, in
     its front matter (`belongs_to:`, read back as `Ticket.belongs_to`) and in a sentence a person
     reads. A front of this project's own repository records nothing;
  2. such a card is never put in the queue through the card's door. The refusal names where it
     belongs, and nothing is written;
  3. one that reached the queue anyway, by a drag on the vendor's own board, is taken out of it at
     the pickup with that sentence, and no job starts;
  4. a job started on one regardless is not sized: pre-flight parks it with the sentence.
"""

from __future__ import annotations

import asyncio

import pytest

from openfactory.adapters.tracker.parse import parse_ticket_body
from openfactory.contracts.ticket import Ticket
from openfactory.lifecycle.card import transition
from openfactory.lifecycle.ports import Seen
from openfactory.lifecycle.table import CardEvent, State
from openfactory.product.config import ProductLink
from openfactory.product.loader import ProductContext
from openfactory.product.role import IssueDraft
from tests.product_shapes import ProductShape
from tests.product_shapes import product_shape as product_shape  # noqa: F401 — the fixture
from tests.test_the_card_lifecycle_does_what_its_table_says import Ports


class _OnePlace:
    """A tracker that keeps every card in one place, as the local row does."""

    def __init__(self):
        self.bodies: list[str] = []

    def find_ticket(self, *, title):
        return None

    def create_ticket(self, *, title, body):
        self.bodies.append(body)
        return f"#{20 + len(self.bodies)}"

    def ticket_url(self, ref):
        return ""


def _requirement():
    from openfactory.product.corpus import Requirement

    return Requirement(number=4, slug="filtro", path="0004-filtro.md", title="Filtro",
                       status="accepted")


def _owner_module(shape: ProductShape, tracker, monkeypatch):
    from openfactory.product.module import ProductModule

    owner = shape.members[0]
    ctx = ProductContext(link=ProductLink(active=True, docs_repo=shape.docs_repo, kind="ok"))
    mod = ProductModule(shape.project(owner), context=ctx, tracker=tracker)
    monkeypatch.setattr(mod, "_sources", lambda: [shape.source(m) for m in shape.members])
    monkeypatch.setattr(mod, "_docs_url", lambda: "")
    return mod


def _filed(shape: ProductShape, member: str, monkeypatch) -> Ticket:
    tracker = _OnePlace()
    mod = _owner_module(shape, tracker, monkeypatch)
    draft = IssueDraft(title=f"the filter ({member})", objective="filter the list",
                       target_repo=shape.source(member), cites=4)

    assert mod._file_one(draft, _requirement(), tracker, None).ok
    [body] = tracker.bodies
    return parse_ticket_body(id="#21", title=draft.title, body=body, repo=shape.members[0])


# ── 1. the card records where it belongs ────────────────────────────────────────────────────────

def test_TODAYS_RUN_a_front_filed_outside_its_repository_records_where_it_belongs(
        product_shape, monkeypatch):
    owner = product_shape.members[0]
    for member in product_shape.members:
        ticket = _filed(product_shape, member, monkeypatch)

        expected = None if member == owner else product_shape.source(member)
        assert ticket.belongs_to == expected, (member, ticket.belongs_to)


def test_the_person_reading_the_card_is_told_where_it_belongs(product_shape, monkeypatch):
    owner = product_shape.members[0]
    for member in product_shape.members:
        raw = _filed(product_shape, member, monkeypatch).raw

        told = f"Its change belongs to `{product_shape.source(member)}`" in raw
        assert told is (member != owner), (member, raw)


# ── 2. the door does not queue it ───────────────────────────────────────────────────────────────

def test_TODAYS_RUN_a_card_of_another_repository_is_not_queued(product_shape):
    owner = product_shape.project(product_shape.members[0])
    for member in product_shape.members:
        home = "" if member == product_shape.members[0] else product_shape.source(member)
        ports = Ports(seen_as=Seen(state=State.BACKLOG, belongs_to=home))

        moved = transition(owner, "#4", CardEvent.PROMOTED, by="po", ports=ports)

        if home:
            assert moved.refused and f"`{home}`" in moved.refused, (member, moved.refused)
            assert ports.calls == [], "a refused queueing wrote something"
        else:
            assert not moved.refused, (member, moved.refused)


def test_a_card_that_names_this_projects_own_repository_is_queued(product_shape):
    """A person may write the key by hand; naming the repository the card runs in is no reason to
    refuse it."""
    owner = product_shape.project(product_shape.members[0])
    ports = Ports(seen_as=Seen(state=State.BACKLOG,
                               belongs_to=product_shape.source(product_shape.members[0])))

    assert not transition(owner, "#4", CardEvent.PROMOTED, by="po", ports=ports).refused


def test_the_door_reads_where_a_card_belongs_from_the_card_itself(product_shape):
    from openfactory.lifecycle.ports import Ports as DoorPorts

    owner = product_shape.project(product_shape.members[0])
    for member in product_shape.members:
        class _Tracker:
            def get_ticket(self, ref, member=member):
                return Ticket(id="#4", title="t", objective="o", repo=owner.name, state="open",
                              belongs_to=product_shape.source(member))

        seen = DoorPorts(owner, tracker=_Tracker(), board=None).seen("#4")

        assert seen.belongs_to == product_shape.source(member), (member, seen)


def test_the_refusal_is_said_in_the_projects_language(product_shape):
    if len(product_shape.members) < 2:
        pytest.skip("a product of one project has no other repository to belong to")
    owner = product_shape.project(product_shape.members[0]).model_copy(
        update={"language": "pt-BR"})
    ports = Ports(seen_as=Seen(state=State.BACKLOG, belongs_to=product_shape.members[1]))

    moved = transition(owner, "#4", CardEvent.PROMOTED, by="po", ports=ports)

    assert "não foi posto na fila" in moved.refused, moved.refused


# ── 3. the pickup takes it out of the queue ─────────────────────────────────────────────────────

def test_a_card_of_another_repository_in_the_queue_is_taken_out_and_not_started(
        product_shape, monkeypatch, tmp_path):
    import openfactory.adapters.board as board_pkg
    import openfactory.lifecycle as lifecycle
    import openfactory.runtime.temporal.activities as acts
    from openfactory import box_prove
    from openfactory.runtime.temporal.io import ScanInput

    owner = product_shape.project(product_shape.members[0])
    homes = {str(n): ("" if m == owner.name else product_shape.source(m))
             for n, m in enumerate(product_shape.members, start=4)}

    class _Board:
        def items_in_status(self, status):
            return list(homes)

    class _Tracker:
        def get_ticket(self, ref):
            return Ticket(id=f"#{ref}", title="t", objective="o", repo=owner.name,
                          state="open", belongs_to=homes[ref] or None)

    refused: list[tuple[str, str]] = []

    def _transition(project, card, event, **kw):
        refused.append((card, kw["facts"]["note"]))
        return type("T", (), {"refused": ""})()

    monkeypatch.setenv("OPENFACTORY_PROOFS", str(tmp_path))
    monkeypatch.setattr(box_prove, "PROOF_DIR", tmp_path)
    monkeypatch.setattr(acts.ProjectRegistry, "get", lambda self, name: owner)
    monkeypatch.setattr(board_pkg, "build_board", lambda *a, **kw: _Board())
    monkeypatch.setattr(acts, "_tracker_for", lambda p: _Tracker())
    monkeypatch.setattr("openfactory.credentials.tracker_token_for", lambda p: "tok")
    monkeypatch.setattr("openfactory.box_prove.gate_reason", lambda *a, **kw: None)
    monkeypatch.setattr(lifecycle, "transition", _transition)

    got = asyncio.run(acts.scan_todo(ScanInput(project=owner.name, board_owner="o",
                                               board_number="1", pickup_status="TO-DO")))

    assert got == [ref for ref, home in homes.items() if not home], got
    assert [card for card, _ in refused] == [ref for ref, home in homes.items() if home]
    for card, note in refused:
        assert f"`{homes[card]}`" in note, note


# ── 4. a job started on it regardless is not sized ──────────────────────────────────────────────

def test_a_job_on_a_card_of_another_repository_is_parked_at_pre_flight(product_shape,
                                                                      monkeypatch):
    import openfactory.runtime.temporal.activities as acts
    from openfactory.runtime.temporal.io import PreflightInput

    owner = product_shape.project(product_shape.members[0])
    for member in product_shape.members:
        home = "" if member == owner.name else product_shape.source(member)

        class _Tracker:
            def get_ticket(self, ref, home=home):
                return Ticket(id="#4", title="t", objective="o", repo=owner.name,
                              belongs_to=home or None)

        monkeypatch.setattr(acts.ProjectRegistry, "get", lambda self, name: owner)
        monkeypatch.setattr(acts, "_tracker_for", lambda p: _Tracker())
        monkeypatch.setattr(acts, "_pf_emit", lambda *a, **kw: None)
        sized = []
        monkeypatch.setattr(acts, "_ref_repo", lambda *a, sized=sized: sized.append(a) or ("", ""))
        monkeypatch.setattr("openfactory.adapters.forge.registry.clone_url_for",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("stop here")))

        verdict = acts._do_preflight(PreflightInput(project=owner.name, issue="4"))

        if home:
            assert verdict.verdict == "unclear" and f"`{home}`" in verdict.questions[0], verdict
            assert sized == [], "a card of another repository was sized"
        else:
            assert verdict.verdict != "unclear" and sized, (member, verdict)
