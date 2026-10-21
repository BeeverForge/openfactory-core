"""The product owner says where its requirements came from (#994): an import is an event, the
briefing names it, and what is still open is the agenda.

After an import (#993) the product's role found `proposed` requirements and a design and treated them
as any files. Now the import is told once to the product's room; the briefing carries where the
requirements came from and how much of it is still proposed; what is still open — the requirements'
own questions, the questions the import's record brings, the decisions its documents raise, a text
kept beside an agreed requirement — is the agenda, each an item to ask; and the role's instructions
say an import is a review to hold with the person who asked.

THE BED IS THE BATTERY'S `saltmarsh` FIXTURE, and its context is what the core's import WRITES:
`test_the_fixture_is_exactly_what_the_import_lands` imports `brought/` into the fixture's base and
compares every byte. Each test states a family's rule with its cases read from the code — every
status the corpus knows, every kind of open item `importing` can say, every language the event's
sentence is written in — and the event's producer is read from `events.PRODUCERS`.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from openfactory.product import agenda, briefing, events, importing, voice
from openfactory.product.corpus import _KNOWN_STATUS, Requirement, load_corpus
from openfactory.product.model import ProductModel, render
from tests.test_requirements_are_imported_under_the_corpus_rules import (  # noqa: F401
    ADMIN,
    _a_round,
    _act,
    _bare,
    _requirement,
    _seeded,
    deployment,
)

FIXTURE = Path(__file__).parent / "fixtures" / "evaluation" / "saltmarsh"
RECORD = next((FIXTURE / "context" / ".openfactory" / "imports").glob("*/record.json"))
ASKED = "joana"


def _review(corpus=None, *, decisions=None, record=None) -> importing.Review:
    record = record or json.loads(RECORD.read_text())
    corpus = corpus if corpus is not None else load_corpus(FIXTURE / "context" / "requirements")
    return importing.review(record, corpus, decisions=decisions)


def _with_status(tmp_path: Path, number: int, status: str):
    """The fixture's corpus with requirement `number` in `status` — a superseded one pointing at
    another of the fixture's, so the corpus stays one the reader takes."""
    import re

    folder = tmp_path / "requirements"
    shutil.copytree(FIXTURE / "context" / "requirements", folder)
    path = next(folder.glob(f"{number:04d}-*.md"))
    word = f"superseded-by {1 if number != 1 else 2:04d}" if status == "superseded" else status
    path.write_text(re.sub(r"^- \*\*Status:\*\* .*$", f"- **Status:** {word}", path.read_text(),
                           count=1, flags=re.M))
    return load_corpus(folder)


# ── 0. the bed is what the import writes ────────────────────────────────────────────────────────

def test_the_fixture_is_exactly_what_the_import_lands(tmp_path):
    """The fixture's base — its context without what the import landed — with `brought/` imported
    into it by the core's own import, is the fixture's context, byte for byte."""
    record = json.loads(RECORD.read_text())
    base = tmp_path / "base"
    shutil.copytree(FIXTURE / "context", base)
    for path in record["landed"]:
        (base / path).unlink()
    shutil.rmtree(base / ".openfactory" / "imports")
    shutil.rmtree(base / importing.IMPORTED_FOLDER)
    brought = importing.read(FIXTURE / "brought")
    brought.name = record["brought"]
    day = record["id"][:10]
    the_plan = importing.plan(brought, root=base, requirements_dir="requirements",
                              first=importing.first_number(base, "requirements", []),
                              ident=importing.import_id(brought, day),
                              origin=brought.manifest["origin"])

    importing.land(the_plan, brought, root=base, requirements_dir="requirements", by=ASKED,
                   at=record["landed_at"])

    def tree(root: Path) -> dict[str, bytes]:
        return {p.relative_to(root).as_posix(): p.read_bytes()
                for p in sorted(root.rglob("*")) if p.is_file()}

    assert tree(base) == tree(FIXTURE / "context")


# ── 1. an import is an event, told once to the room ─────────────────────────────────────────────

def test_the_import_tells_its_room_once_what_arrived_from_where(deployment, monkeypatch):  # noqa: F811
    told: list[tuple[str, str, str]] = []
    monkeypatch.setattr(events, "_tell", lambda project, *, id, conversation, text: (
        told.append((id, conversation, text)) or True))
    _seeded(deployment)
    folder = _a_round(deployment.tmp)

    assert _act(source=str(folder), yes=True).ok
    assert _act(source=str(folder), yes=True).ok           # the same import: said already

    assert len(told) == 1, told
    ident, conversation, text = told[0]
    assert conversation == events.room_of(deployment.project)
    assert "the second prototyping round" in text and "1 new" in text and "1 revising" in text
    assert ADMIN not in text and "bia" not in text, "a person was named in the room"


def test_one_import_is_one_event_however_often_it_is_told(deployment, monkeypatch):  # noqa: F811
    told: list[str] = []
    monkeypatch.setattr(events, "_tell", lambda project, *, id, conversation, text: (
        told.append(id) or True))
    counts = {"new": 2, "revision": 0, "beside": 0}

    first = events.imported(deployment.project, ident="2026-10-14-a733e54bca",
                            origin="the second round", counts=counts)
    again = events.imported(deployment.project, ident="2026-10-14-a733e54bca",
                            origin="the second round", counts=counts)
    other = events.imported(deployment.project, ident="2026-10-15-0000000000",
                            origin="the third round", counts=counts)

    assert (first, again, other) == (True, False, True) and len(set(told)) == 2


@pytest.mark.parametrize("language", sorted(voice._IMPORTED))
def test_the_event_is_said_in_the_products_language(language):
    said = voice.imported(origin="the second round", new=2, revision=1, beside=1,
                          language=language)
    assert said == voice._IMPORTED[language].format(sig="", origin="the second round", new=2,
                                                    revision=1, beside=1)


def test_the_import_is_the_events_producer_and_it_tells_it():
    import inspect

    from openfactory.product.module import ProductModule

    assert events.IMPORTED in events.KINDS
    assert events.PRODUCERS[events.IMPORTED] == \
        "openfactory/product/module.py::import_requirements"
    assert "events.imported(" in inspect.getsource(ProductModule.import_requirements)


# ── 2. the briefing names where the requirements came from ─────────────────────────────────────

def _model(imported: dict | None) -> ProductModel:
    return ProductModel(key="repo:saltmarsh-context", members=["saltmarsh"],
                        read_at=datetime.now(UTC).isoformat(), imported=imported)


@pytest.mark.parametrize("days", [0, briefing.DELIVERED_DAYS - 1, briefing.DELIVERED_DAYS + 30])
@pytest.mark.parametrize("under_review", [True, False], ids=["under review", "settled"])
def test_the_briefing_says_where_the_requirements_came_from_with_its_age(days, under_review):
    """A line, with its source and its age, while the import is a review to hold — and after,
    only while it is recent."""
    imported = _review().as_dict()
    imported["landed_at"] = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    imported["under_review"] = under_review

    lines = briefing.render(_model(imported)).lines

    said = [line for line in lines if "Requirements arrived from" in line]
    if not under_review and days >= briefing.DELIVERED_DAYS:
        assert said == [], lines
        return
    assert len(said) == 1, lines
    line = said[0]
    assert "«the second prototyping round»" in line and "2 still proposed, 0 agreed" in line
    assert "design: imported/design/order-flow.md" in line
    age = briefing.age(imported["landed_at"], datetime.now(UTC))
    assert line.endswith(f"(import record — imported {age})"), line
    assert ("imported.md" in line) is under_review


def test_a_product_nothing_was_imported_into_has_no_such_line():
    assert not [line for line in briefing.render(_model(None)).lines if "arrived" in line]


# ── 3. what is still open is the agenda ─────────────────────────────────────────────────────────

def test_what_the_import_left_open_is_read_from_its_record_and_the_corpus():
    review = _review(decisions=lambda path: ["the cut-off moves to Wednesday"]
                     if path == "imported/design/order-flow.md" else [])

    assert review.origin == "the second prototyping round"
    assert review.proposed == [2, 3] and review.agreed == [] and review.order == [3, 2]
    assert review.design == "imported/design/order-flow.md" and review.under_review
    assert sorted((o.kind, o.requirement, o.ask) for o in review.open) == [
        (importing.DECISION, None, ""),
        (importing.QUESTION, 2, ""), (importing.QUESTION, 2, ASKED),
        (importing.QUESTION, 3, "")]


@pytest.mark.parametrize("status", sorted(_KNOWN_STATUS))
def test_a_question_is_open_while_its_requirement_waits_for_its_yes(tmp_path, status):
    """Whatever becomes of REQ-0002 — agreed, dropped, replaced, or still waiting — its questions
    are on the agenda exactly while it is live and not a promise."""
    corpus = _with_status(tmp_path, 2, status)
    waits = Requirement(number=2, slug="x", path="x", status=status)

    review = _review(corpus)

    about_two = [o for o in review.open if o.requirement == 2]
    assert bool(about_two) is (waits.is_live and not waits.is_promise), review.as_dict()
    assert (2 in review.proposed) is bool(about_two)


@pytest.mark.parametrize("status", sorted(_KNOWN_STATUS))
def test_a_text_kept_beside_an_agreed_requirement_waits_while_that_one_is_the_promise(
        tmp_path, status):
    """A proposal to change REQ-0001 stays open while REQ-0001 is the agreed text — and closes
    the moment a person's yes replaced it, dropped it, or it is anything but a promise."""
    record = json.loads(RECORD.read_text())
    record["requirements"].append({"kind": importing.BESIDE, "number": 1,
                                   "title": "Members sign in with a passkey",
                                   "path": ".openfactory/imports/x/proposals/0001-sign-in.md"})
    corpus = _with_status(tmp_path, 1, status)

    changes = [o for o in _review(corpus, record=record).open if o.kind == importing.CHANGE]

    promise = Requirement(number=1, slug="x", path="x", status=status).is_promise
    assert bool(changes) is promise, changes


def test_every_kind_of_open_item_is_one_the_agenda_says():
    kinds = {importing.QUESTION, importing.DECISION, importing.CHANGE}
    assert set(agenda._IMPORT_KEYS) == kinds
    assert {agenda._IMPORT_KEYS[k] for k in kinds} <= set(voice._AGENDA_SAID)


@pytest.mark.parametrize("viewer,yours", [(ASKED, True), ("bia", False), ("", False)])
def test_an_item_is_yours_only_when_the_record_says_so_and_the_person_is_named_to_nobody(
        viewer, yours):
    review = _review()
    seen = agenda.from_the_import(review, agenda.Viewer(person=viewer), language="en")

    addressed = [i for i in seen if "public holiday" in i.what]
    assert len(seen) == len(review.open) and len(addressed) == 1
    assert addressed[0].yours is yours and addressed[0].to == ("you" if yours else "the room")
    assert all(i.direction == agenda.AWAITED for i in seen)
    assert ASKED not in json.dumps([i.as_dict() for i in seen]), "a person was named"


def test_a_viewer_who_may_not_read_the_room_sees_none_of_it():
    assert agenda.from_the_import(_review(), agenda.Viewer(person=ASKED, may_read_room=False)) \
        == []


def test_the_pending_tab_lists_what_the_import_left_open(deployment):  # noqa: F811
    """The row the panel's Pending tab reads, after an import: one item to ask per question the
    import brought — the requirements' own and the record's."""
    import asyncio

    from openfactory import actions

    _seeded(deployment)
    folder = _a_round(deployment.tmp)
    (folder / importing.MANIFEST).write_text(
        "origin: the second prototyping round\nquestions:\n  - text: Weekly or daily?\n"
        "    requirement: 2\n    ask: ana\n")
    assert _act(source=str(folder), yes=True).ok

    said = asyncio.run(actions.perform("product_agenda", by=actions.Actor(
        id=ADMIN, via="panel", admin=True, scopes=frozenset({actions.PRODUCT})), project="lark"))

    items = [i for i in said.data["items"] if i["kind"] == agenda.IMPORT]
    assert [(i["what"], i["yours"]) for i in items] == [("Weekly or daily?", True)], items


# ── 4. the role reads it whole ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("speaker", [ASKED, "bia"])
def test_the_pack_carries_the_order_the_design_and_what_is_open_naming_nobody(speaker):
    files = render(_model(_review().as_dict()), speaker=speaker)

    text = files["imported.md"]
    assert "the second prototyping round" in text and "REQ-0003 → REQ-0002" in text
    assert "imported/design/order-flow.md" in text and "never code to build on" in text
    assert "public holiday" in text and "Which allergens" in text
    assert ("yours to answer" in text) is (speaker == ASKED)
    assert ASKED not in text.replace("yours to answer", "")


def test_the_role_is_told_an_import_is_a_review_to_hold_not_a_backlog():
    from openfactory.adapters.agent.roles import role_prompt

    told = " ".join(role_prompt("product").split())
    for rule in ("a review to hold with the person who asked, not a backlog to execute",
                 "Propose the order the import suggests, and ask the person to confirm it",
                 "accept it only on the requester's own yes",
                 "never answer it for the person",
                 "**what the person saw**: cite it as that, never as code to build on"):
        assert rule in told, rule


# ── 5. the battery asks it ──────────────────────────────────────────────────────────────────────

def test_the_battery_asks_the_conversation_that_opens_after_an_import(tmp_path):
    from openfactory.product.evaluation.battery import load_battery
    from openfactory.product.evaluation.run import isolated, load_fixture

    battery = load_battery(FIXTURE / "questions.yaml", fixture=FIXTURE)
    with isolated(tmp_path):
        project, ctx = load_fixture(FIXTURE, tmp_path)

    (question,) = battery.questions
    assert question.id == "after-the-import" and question.audience == "product admin"
    assert ctx.available, ctx.reason
    assert importing.newest(Path(ctx.docs_path))["origin"] == "the second prototyping round"
    assert {r.number for r in ctx.corpus.requirements} == {1, 2, 3}
