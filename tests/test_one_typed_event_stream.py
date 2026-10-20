"""One typed event envelope for every stream the API pushes (#679, a).

Four streams carry frames today, each in a shape of its own: the floor's socket (`/api/stream`),
the product chat's socket (`/api/product/stream`), one run's log (`/api/jobs/{project}/{issue}/
stream`) and the durable jobs' state (`/api/temporal/stream`). Slice a describes them ONCE: an
envelope — `kind`, `id`, `at`, `project`, `product` when one applies, `data` — and a data model per
kind, committed beside the OpenAPI description as `docs/reference/events.schema.json`.

WHAT IS PROVEN HERE:

  · the committed schema is the one the models generate, and the test that finds them apart says
    the command that writes it again;
  · a representative frame of every kind each stream emits today maps onto the envelope and
    validates against its kind's model — built by the producers themselves where they are plain
    functions (`frames_of`, `presence_for`, `JobEvent`);
  · `product` is required for the kinds that belong to a product, and absent or null for the rest.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / "docs" / "reference" / "events.schema.json"

AT = "2026-10-20T12:00:00+00:00"
PRODUCT = "project:acme"

FLOOR, CHAT = "/api/stream", "/api/product/stream"
LOG, JOBS = "/api/jobs/{project}/{issue}/stream", "/api/temporal/stream"


def _subscriber():
    from openfactory.api.product_chat import Subscriber

    return Subscriber(person="ana", own="person:ana", product=PRODUCT, project="acme",
                      conversation="acme", may_read_room=True, frames=asyncio.Queue())


def _ended(why="signed_out", status=401):
    return {"why": why, "status": status, "detail": "unauthorized"}


def _turn():
    return {"role": "person", "actor": "ana", "text": "hi", "ts": AT, "id": "m1",
            "in_reply_to": "", "mine": True, "overheard": False}


def _frames() -> list[tuple[str, str, dict]]:
    """(stream, kind, frame) — one representative frame of every kind every stream emits today."""
    from openfactory.api.product_chat import frames_of, presence_for
    from openfactory.observability.events import JobEvent

    sub = _subscriber()
    said = frames_of({"seq": 3, "type": "said", "id": "m1", "text": "hi", "speaker": "ana"}, sub)
    reply = frames_of({"seq": 4, "type": "answer", "final": True,
                       "replies": [{"text": "hello", "kind": "answer", "in_reply_to": "m1"}]}, sub)
    log_event = JobEvent(ts=AT, job_id="acme-7", ticket_id="7", kind="state",
                         message="picked up", data={"to": "running"}).model_dump()
    return [
        # `/api/stream`
        (FLOOR, "hello", {"kind": "hello", "tick": 2.0}),
        (FLOOR, "update", {"kind": "update", "project": "acme",
                           "projects": [{"name": "acme", "enabled": True}],
                           "chat": {"project": "acme", "messages": [], "pending": []}}),
        (FLOOR, "bye", {"kind": "bye", "reason": "unauthorized", "ended": _ended()}),
        # `/api/product/stream`
        (CHAT, "hello", {"kind": "hello"}),
        (CHAT, "subscribed", {"kind": "subscribed", "project": "acme", "private": False,
                              "room": True, "session": ""}),
        (CHAT, "history", {"kind": "history", "turns": [_turn()],
                           "staged": {"token": "t", "approve": "yes", "reject": "no"},
                           "earlier": "c1"}),
        (CHAT, "earlier", {"kind": "earlier", "turns": [_turn()], "earlier": ""}),
        (CHAT, "said", said[0]),
        (CHAT, "reply", reply[0]),
        (CHAT, "staged", {"kind": "staged", "staged": None}),
        (CHAT, "presence", presence_for({"running": True, "stage": "lendo o quadro"}, "ana")),
        (CHAT, "ack", {"kind": "ack", "id": "m1", "ok": True, "text": "sent", "state": "queued",
                       "ahead": 0}),
        (CHAT, "refused", {"kind": "refused", "why": "this credential may not read the product "
                                                     "area."}),
        (CHAT, "resync", {"kind": "resync"}),
        (CHAT, "bye", {"kind": "bye", "reason": "", "ended": _ended("unavailable", 503)}),
        # `/api/temporal/stream`
        (JOBS, "jobs", {"connected": True, "address": "localhost:7233", "jobs": [
            {"workflow_id": "job-acme-7", "project": "acme", "issue": "7", "state": "running"}],
            "intake": {"known": True}, "build": {}}),
        (JOBS, "jobs", {"connected": False, "address": "localhost:7233", "error": "down",
                        "jobs": None, "build": {}}),
        (JOBS, "ended", _ended("not_allowed", 403)),
        # `/api/jobs/{project}/{issue}/stream`
        (LOG, "log", log_event),
        (LOG, "ended", _ended()),
    ]


def _map(stream: str, kind: str, frame: dict, **kw) -> dict:
    """`from_frame`, told the SSE event name an `ended` frame arrives under."""
    from openfactory.api.events import from_frame

    return from_frame(stream, frame, event="ended" if kind == "ended" else None, **kw)


def _product_of(kind: str) -> str | None:
    from openfactory.api.events import PRODUCT_KINDS

    return PRODUCT if kind in PRODUCT_KINDS else None


# ── the committed schema ────────────────────────────────────────────────────────────────────────

def test_the_committed_schema_is_the_one_the_models_generate():
    from openfactory.api.events import COMMAND, render

    committed = COMMITTED.read_text(encoding="utf-8") if COMMITTED.exists() else ""
    assert committed == render(), (
        f"{COMMITTED.relative_to(ROOT)} is not what the models generate. "
        f"Write it again with:\n\n    {COMMAND}\n")


def test_the_schema_names_the_envelope_and_a_data_model_for_every_kind():
    from openfactory.api.events import KINDS

    schema = json.loads(COMMITTED.read_text(encoding="utf-8"))
    defs = schema["$defs"]
    assert {"kind", "id", "at", "project", "product", "data"} <= set(defs["Envelope"]["properties"])
    mapping = schema["discriminator"]["mapping"]
    assert set(mapping) == set(KINDS)
    for kind in KINDS:
        event = defs[mapping[kind].removeprefix("#/$defs/")]
        assert event["properties"]["kind"]["const"] == kind
        assert event["properties"]["data"]["$ref"].removeprefix("#/$defs/") in defs


def test_the_command_writes_the_schema(tmp_path):
    from openfactory.api.events import main, render

    target = tmp_path / "events.schema.json"
    assert main([str(target)]) == 0
    assert target.read_text(encoding="utf-8") == render()


def test_the_command_says_why_it_could_not_write(tmp_path, capsys):
    from openfactory.api.events import main

    assert main([str(tmp_path / "missing" / "events.schema.json")]) == 1
    assert "could not write" in capsys.readouterr().err


# ── every frame of today, on the envelope ───────────────────────────────────────────────────────

def test_every_kind_has_a_representative_frame_here():
    from openfactory.api.events import KINDS

    assert {kind for _stream, kind, _frame in _frames()} == set(KINDS)


@pytest.mark.parametrize(("stream", "kind", "frame"), _frames(),
                         ids=[f"{s}:{k}" for s, k, _f in _frames()])
def test_every_frame_maps_onto_the_envelope_and_validates(stream, kind, frame):
    from openfactory.api.events import DATA_MODELS, Envelope, validate

    product = _product_of(kind)
    event = _map(stream, kind, frame, id="e-1", at=AT, project="acme", product=product)

    assert set(event) <= {"kind", "id", "at", "project", "product", "data"}
    assert event["kind"] == kind and event["id"] == "e-1" and event["at"] == AT
    assert event["project"] == "acme"
    assert event.get("product") == product
    assert "kind" not in event["data"] or kind == "log"   # a log event's own `kind` is its data
    Envelope.model_validate(event)
    typed = validate(event)
    assert type(typed.data) is DATA_MODELS[kind]
    # what the frame carried is all still there, in `data`
    for key, value in frame.items():
        if key == "kind" and kind != "log" or key == "project" and kind == "update":
            continue
        assert event["data"][key] == value, key


def test_the_temporal_frame_keeps_jobs_null():
    from openfactory.api.events import from_frame, validate

    down = {"connected": False, "address": "a", "error": "down", "jobs": None, "build": {}}
    typed = validate(from_frame(JOBS, down, id="e", at=AT))
    assert typed.data.jobs is None
    assert typed.model_dump(mode="json")["data"]["jobs"] is None


def test_the_floor_update_takes_its_project_onto_the_envelope():
    from openfactory.api.events import from_frame

    event = from_frame(FLOOR, {"kind": "update", "project": "acme", "projects": []},
                       id="e", at=AT)
    assert event["project"] == "acme" and "project" not in event["data"]


def test_a_frame_of_a_kind_its_stream_does_not_emit_is_refused():
    from openfactory.api.events import from_frame

    with pytest.raises(ValueError, match="said"):
        from_frame(FLOOR, {"kind": "said"}, id="e", at=AT)
    with pytest.raises(ValueError, match="stream"):
        from_frame("/api/elsewhere", {"kind": "hello"}, id="e", at=AT)


def test_a_frame_whose_data_does_not_fit_its_kind_is_refused():
    from openfactory.api.events import from_frame, validate

    event = from_frame(CHAT, {"kind": "presence", "state": "dancing", "ahead": 0},
                       id="e", at=AT, product=PRODUCT)
    with pytest.raises(ValidationError):
        validate(event)


# ── product, when one applies ───────────────────────────────────────────────────────────────────

def test_the_product_kinds_are_the_conversations_own():
    from openfactory.api.events import KINDS, PRODUCT_KINDS

    assert set(PRODUCT_KINDS) == {"subscribed", "history", "earlier", "said", "reply", "staged",
                                  "presence", "resync"}
    assert set(PRODUCT_KINDS) < set(KINDS)


@pytest.mark.parametrize(("stream", "kind", "frame"),
                         [f for f in _frames() if f[1] in {"subscribed", "history", "earlier",
                                                           "said", "reply", "staged", "presence",
                                                           "resync"}],
                         ids=lambda v: v if isinstance(v, str) else "")
def test_product_is_required_for_a_kind_that_belongs_to_a_product(stream, kind, frame):
    from openfactory.api.events import validate

    assert validate(_map(stream, kind, frame, id="e", at=AT, product=PRODUCT)).product == PRODUCT
    for missing in (None, ""):
        with pytest.raises(ValidationError):
            validate(_map(stream, kind, frame, id="e", at=AT, product=missing))


@pytest.mark.parametrize(("stream", "kind", "frame"),
                         [f for f in _frames() if f[1] not in {"subscribed", "history", "earlier",
                                                               "said", "reply", "staged",
                                                               "presence", "resync"}],
                         ids=lambda v: v if isinstance(v, str) else "")
def test_product_is_absent_or_null_for_a_kind_that_does_not(stream, kind, frame):
    from openfactory.api.events import validate

    absent = _map(stream, kind, frame, id="e", at=AT)
    assert "product" not in absent
    assert validate(absent).product is None
    nulled = {**absent, "product": None}
    assert validate(nulled).product is None
    with pytest.raises(ValidationError):
        validate({**absent, "product": PRODUCT})
