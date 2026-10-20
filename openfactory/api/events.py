"""One typed event, for every stream the API pushes (#679, slice a).

Four streams carry frames today, each in a shape of its own: the floor's socket (`/api/stream`), the
product chat's socket (`/api/product/stream`), the durable jobs' state (`/api/temporal/stream`) and
one run's log (`/api/jobs/{project}/{issue}/stream`). A screen of one's own had to read
`panel.html` to learn any of them. This module describes them ONCE:

  · an ENVELOPE — `kind`, `id`, `at`, `project`, `product` when one applies, and `data`;
  · a DATA MODEL PER KIND, which is what each stream's frame of that kind carries today.

`from_frame` maps a frame of today's streams onto the envelope, and `validate` reads an envelope as
its kind's model. The description is committed beside the OpenAPI one, generated, never edited:

    python -m openfactory.api.events

writes `docs/reference/events.schema.json` again, and a test fails when it is apart from these.

THE KINDS ARE ONE NAMESPACE. A frame's `kind` names what it says, not which stream said it: the two
sockets' `hello` and `bye` are one kind each, and the two event streams' `ended` is one kind. The
temporal stream's unnamed frame is `jobs`, and a run's journal line is `log` — whose own `kind`
(`state`, `review`…) stays in `data`, where it always was.

`product` IS THE CONVERSATION'S, AND ONLY ITS. The kinds a product chat subscription emits
(`PRODUCT_KINDS`) are about one product's conversation, and carry its key (`product_key`); every
other kind carries none. `ack` and `refused` are NOT product kinds: they answer what the page sent
on the socket, and are sent before any subscription as readily as after it — "open a conversation
before writing in it", "there is no product role to talk to" — where there is no product to name.

THE DATA MODELS FOLLOW `read_models`' FIRST RULE: each allows what it does not name, so a key a
producer adds tomorrow reaches a reader as it does today. A field a producer always writes is
required; one it writes only sometimes is optional.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter

from openfactory.api.read_models import EngineJob, MessagesRead, Number

#: Where the description is committed, from the repository's root — beside `openapi.json`.
COMMITTED = Path("docs") / "reference" / "events.schema.json"

#: What writes it again — said by the test that finds it stale.
COMMAND = "python -m openfactory.api.events"

#: The SSE event name a stream ends on (`app.STREAM_ENDED_EVENT`); every other SSE frame is unnamed.
ENDED = "ended"

#: Every kind, in the order the description lists them.
Kind = Literal["hello", "update", "bye", "subscribed", "history", "earlier", "said", "reply",
               "staged", "presence", "ack", "refused", "resync", "jobs", "log", "ended"]
KINDS: tuple[str, ...] = get_args(Kind)

#: The kinds that are about one product's conversation, and so carry its `product`.
PRODUCT_KINDS = ("subscribed", "history", "earlier", "said", "reply", "staged", "presence",
                 "resync")

#: Which kinds each of today's streams emits. A socket's frame names its kind; an event stream's
#: does not, so its unnamed frame is the first kind here and its named `ended` event the second.
STREAMS: dict[str, tuple[str, ...]] = {
    "/api/stream": ("hello", "update", "bye"),
    "/api/product/stream": ("hello", "subscribed", "history", "earlier", "said", "reply",
                            "staged", "presence", "ack", "refused", "resync", "bye"),
    "/api/temporal/stream": ("jobs", ENDED),
    "/api/jobs/{project}/{issue}/stream": ("log", ENDED),
}

#: The streams whose frames are server-sent events, and so carry no `kind` of their own.
_EVENT_STREAMS = ("/api/temporal/stream", "/api/jobs/{project}/{issue}/stream")


class EventData(BaseModel):
    """What one kind of event carries: its named fields, and whatever else it carries."""

    model_config = ConfigDict(extra="allow")


# ── a stream's own life ─────────────────────────────────────────────────────────────────────────

class HelloData(EventData):
    """A socket opened. The floor's says how often it re-reads (`tick`, seconds); the chat's says
    nothing more."""

    tick: Number | None = None


class EndedData(EventData):
    """Why a stream stopped: the gate's answer to the credential it was opened with (#208)."""

    why: Literal["signed_out", "not_allowed", "unavailable"]
    status: int
    detail: str | None = None


class ByeData(EventData):
    """A socket is closing. `ended` is there when the credential stopped opening it; without it,
    `reason` is what broke."""

    reason: str
    ended: EndedData | None = None


# ── the floor ───────────────────────────────────────────────────────────────────────────────────

class UpdateData(EventData):
    """What changed for the project the floor's socket follows — only the sections that changed.
    A section the store could not read is `null`, never empty."""

    projects: list[dict[str, Any]] | None = None
    chat: MessagesRead | None = None


class JobsData(EventData):
    """The durable jobs' state (`/api/temporal/stream`). `jobs` is ALWAYS sent, and is `null` when
    the engine could not be read — never `[]`, which is an engine that answered with nothing."""

    connected: bool
    jobs: list[EngineJob] | None
    address: str | None = None
    error: str | None = None
    intake: dict[str, Any] | None = None
    build: dict[str, Any] | None = None


class LogData(EventData):
    """One line of a run's log, as the journal wrote it (`observability.events.JobEvent`)."""

    ts: str
    job_id: str
    ticket_id: str
    kind: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


# ── the product chat ────────────────────────────────────────────────────────────────────────────

class Turn(EventData):
    """One turn of a conversation, as the transcript keeps it."""

    role: str | None = None
    actor: str | None = None
    text: str | None = None
    ts: str | None = None
    id: str | None = None
    in_reply_to: str | None = None
    mine: bool | None = None
    overheard: bool | None = None
    attachments: list[dict[str, Any]] | None = None


class Staged(EventData):
    """What waits for the person's answer in this conversation."""

    token: str | None = None
    approve: str | None = None
    reject: str | None = None


class SubscribedData(EventData):
    """The socket follows a conversation now: the room, or one of the person's own."""

    project: str
    private: bool
    room: bool
    session: str


class HistoryData(EventData):
    """The conversation's recent turns, handed on (re)subscribing. `earlier` is the cursor of the
    page before them, `""` when these are all of it."""

    turns: list[Turn]
    staged: Staged | None = None
    earlier: str


class EarlierData(EventData):
    """The page of turns before the one shown, as the page asked."""

    turns: list[Turn]
    earlier: str


class SaidData(EventData):
    """A person said something in the conversation."""

    seq: int
    id: str
    text: str
    speaker: str
    mine: bool
    overheard: bool
    attachments: list[dict[str, Any]] | None = None


class ReplyData(EventData):
    """The role answered."""

    seq: int
    id: str
    text: str
    type: str
    in_reply_to: str
    options: list[Any] | None = None
    final: bool


class StagedData(EventData):
    """What waits for the person's answer changed; `null` when nothing does any more."""

    staged: Staged | None


class PresenceData(EventData):
    """What the role is doing, as this person may see it: `ahead` is how many turns come before
    theirs, `stage` what it is doing while it thinks."""

    state: Literal["idle", "thinking", "answering", "offline"]
    ahead: int
    stage: str | None = None


class AckData(EventData):
    """What became of a message the page sent, by the id the page gave it."""

    id: str
    ok: bool
    text: str
    state: str | None = None
    ahead: int | None = None


class RefusedData(EventData):
    """What the page asked was refused, and why."""

    why: str
    id: str | None = None


class ResyncData(EventData):
    """The socket fell behind: read the conversation again from the transcript."""


# ── the envelope ────────────────────────────────────────────────────────────────────────────────

class Envelope(BaseModel):
    """One event, from any stream. `id` names it within its stream; `at` is when it was sent;
    `project` is the project it is about, when there is one; `product` is the product
    conversation's key, for the kinds in `PRODUCT_KINDS` and no other."""

    kind: Kind
    id: str = Field(min_length=1)
    at: AwareDatetime
    project: str | None = None
    product: str | None = None
    data: EventData


class _Unowned(Envelope):
    """A kind no product owns: `product` is absent or null."""

    product: None = None


class _Owned(Envelope):
    """A kind a product's conversation emits: `product` is its key."""

    product: str = Field(min_length=1)


class HelloEvent(_Unowned):
    kind: Literal["hello"]
    data: HelloData


class UpdateEvent(_Unowned):
    kind: Literal["update"]
    data: UpdateData


class ByeEvent(_Unowned):
    kind: Literal["bye"]
    data: ByeData


class SubscribedEvent(_Owned):
    kind: Literal["subscribed"]
    data: SubscribedData


class HistoryEvent(_Owned):
    kind: Literal["history"]
    data: HistoryData


class EarlierEvent(_Owned):
    kind: Literal["earlier"]
    data: EarlierData


class SaidEvent(_Owned):
    kind: Literal["said"]
    data: SaidData


class ReplyEvent(_Owned):
    kind: Literal["reply"]
    data: ReplyData


class StagedEvent(_Owned):
    kind: Literal["staged"]
    data: StagedData


class PresenceEvent(_Owned):
    kind: Literal["presence"]
    data: PresenceData


class AckEvent(_Unowned):
    kind: Literal["ack"]
    data: AckData


class RefusedEvent(_Unowned):
    kind: Literal["refused"]
    data: RefusedData


class ResyncEvent(_Owned):
    kind: Literal["resync"]
    data: ResyncData


class JobsEvent(_Unowned):
    kind: Literal["jobs"]
    data: JobsData


class LogEvent(_Unowned):
    kind: Literal["log"]
    data: LogData


class EndedEvent(_Unowned):
    kind: Literal["ended"]
    data: EndedData


#: Any event, read by its `kind`.
Event = Annotated[
    HelloEvent | UpdateEvent | ByeEvent | SubscribedEvent | HistoryEvent | EarlierEvent
    | SaidEvent | ReplyEvent | StagedEvent | PresenceEvent | AckEvent | RefusedEvent
    | ResyncEvent | JobsEvent | LogEvent | EndedEvent,
    Field(discriminator="kind")]

_EVENT: TypeAdapter[Any] = TypeAdapter(Event)

#: Each kind's data model, by kind.
DATA_MODELS: dict[str, type[EventData]] = {
    "hello": HelloData, "update": UpdateData, "bye": ByeData, "subscribed": SubscribedData,
    "history": HistoryData, "earlier": EarlierData, "said": SaidData, "reply": ReplyData,
    "staged": StagedData, "presence": PresenceData, "ack": AckData, "refused": RefusedData,
    "resync": ResyncData, "jobs": JobsData, "log": LogData, "ended": EndedData,
}


def from_frame(stream: str, frame: dict, *, id: str, at: str | datetime,
               event: str | None = None, project: str | None = None,
               product: str | None = None) -> dict:
    """`frame`, as one of today's `stream`s sends it, on the envelope.

    A socket's frame names its kind and loses it to the envelope. An event stream's names none:
    it is the stream's own kind, or `ended` when the SSE `event` was. The floor's `update` carries
    its `project` on the envelope. `product` is written only when given — a kind it does not apply
    to leaves it absent, and `validate` refuses one that names it.

    Raises `ValueError` for a stream that is not one of today's, or a kind it does not emit."""
    kinds = STREAMS.get(stream)
    if kinds is None:
        raise ValueError(f"{stream!r} is not a stream the API pushes ({', '.join(STREAMS)})")
    data = dict(frame)
    if stream in _EVENT_STREAMS:
        kind = ENDED if event == ENDED else kinds[0]
    else:
        kind = str(data.pop("kind", ""))
    if kind not in kinds:
        raise ValueError(f"{stream} does not emit a {kind!r} frame (it emits {', '.join(kinds)})")
    if kind == "update" and "project" in data:
        project = data.pop("project")
    out: dict[str, Any] = {"kind": kind, "id": id,
                           "at": at.isoformat() if isinstance(at, datetime) else at,
                           "project": project, "data": data}
    if product is not None:
        out["product"] = product
    return out


def validate(envelope: dict) -> Any:
    """`envelope` as its kind's typed event. Raises `pydantic.ValidationError` when it does not fit
    — an unknown kind, data its kind's model refuses, or a `product` where the kind has none or
    none where it must."""
    return _EVENT.validate_python(envelope)


def schema() -> dict:
    """The JSON Schema of an event: one of the kinds, read by `kind`, with the envelope beside."""
    described = _EVENT.json_schema(ref_template="#/$defs/{model}")
    envelope = Envelope.model_json_schema(ref_template="#/$defs/{model}")
    defs = {**described.pop("$defs", {}), **envelope.pop("$defs", {}), "Envelope": envelope}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "OpenFactory event",
        "description": (__doc__ or "").split("\n\n")[0].strip(),
        **described,
        "$defs": dict(sorted(defs.items())),
    }


def render() -> str:
    """`schema()` as the committed file holds it."""
    return json.dumps(schema(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the schema to the path given, or to `COMMITTED` under the current directory."""
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]) if args else COMMITTED
    try:
        target.write_text(render(), encoding="utf-8")
    except OSError as exc:
        print(f"could not write {target}: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
