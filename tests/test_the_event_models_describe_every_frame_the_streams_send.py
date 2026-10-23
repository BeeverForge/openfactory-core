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
  · `product` is required for the kinds that belong to a product, and absent or null for the rest;
  · the kinds and keys are the ones the EMITTERS write — read from their source, so a kind
    renamed in `app.py` or `product_chat.py`, a kind `STREAMS` claims a stream emits that it does
    not, or a key renamed or added in a socket's or the temporal stream's frame, in a dict that
    frame spreads, or in a turn or what waits, fails here rather than drifting from the schema.
    What the reading follows, and the one spread it does not, is said where it reads.
"""

from __future__ import annotations

import ast
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


def _ended(why="signed_out", status=401, **more):
    return {"why": why, "status": status, "detail": "unauthorized", **more}


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
        (FLOOR, "bye", {"kind": "bye", "reason": "unauthorized",
                        "ended": _ended(login="/auth/login")}),
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
        (JOBS, "jobs", {"connected": True, "address": "localhost:7233", "ui_base": "",
                        "ui_hint": "nobody said where the engine's UI is", "jobs": [
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


# ── the emitters, read: the kinds and fields above are the ones the code writes ─────────────────
#
# WHAT IS READ. A frame is a dict literal in its emitter's source, and its keys are read as the
# code writes them: a constant key; the keys of a conditional dict it spreads, `**({…} if … else
# {})`, which it writes only sometimes; and the keys a function it spreads returns or assigns
# (`out["projects"] = …`), whether the spread is the call, `**_engine_ui(tv)`, or a name bound
# from it, `first = await asyncio.to_thread(_stream_snapshot, …)` — read as written only
# sometimes. A spread this cannot read fails here unless `UNREAD_SPREADS` names it and says where
# its keys are read instead. The rows a frame nests are read where they are built: a turn in
# `product_chat._history`, what waits in `staging.waiting_in`.

APP = ROOT / "openfactory" / "api" / "app.py"
PRODUCT_CHAT = ROOT / "openfactory" / "api" / "product_chat.py"
STAGING = ROOT / "openfactory" / "product" / "staging.py"

#: (the function a frame is written in, the name it spreads) → where that name's keys are read.
UNREAD_SPREADS = {
    ("stream", "changed"): "the floor's later `update` spreads the keys of the snapshot that "
                           "changed, a subset of what its first `update` spreads (`first`)",
}

#: The keys a frame of a kind carries that go onto the envelope rather than into its `data`.
LIFTED = {"update": {"project"}}

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)

#: What a frame writes: (the keys it always writes, the keys it writes only sometimes).
Written = tuple[set[str], set[str]]


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _function(tree: ast.AST, name: str) -> ast.AST:
    found = [n for n in ast.walk(tree) if isinstance(n, _FUNCTIONS) and n.name == name]
    assert len(found) == 1, f"expected one function {name!r}, found {len(found)}"
    return found[0]


def _keys(node: ast.Dict) -> set[str]:
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _returned_keys(tree: ast.AST, name: str) -> list[set[str]]:
    """The keys of every dict literal function `name` returns — either side of a conditional."""
    out = []
    for node in ast.walk(_function(tree, name)):
        if isinstance(node, ast.Return):
            values = [node.value]
            while values:
                value = values.pop()
                if isinstance(value, ast.IfExp):
                    values += [value.body, value.orelse]
                elif isinstance(value, ast.Dict):
                    out.append(_keys(value))
    return out


def _scopes(tree: ast.AST) -> dict[ast.AST, list[ast.AST]]:
    """Every node of `tree` → the functions it is written in, the innermost first."""
    out: dict[ast.AST, list[ast.AST]] = {}
    todo: list[tuple[ast.AST, list[ast.AST]]] = [(tree, [])]
    while todo:
        node, inside = todo.pop()
        for child in ast.iter_child_nodes(node):
            out[child] = inside
            todo.append((child, [child, *inside] if isinstance(child, _FUNCTIONS) else inside))
    return out


def _own(fn: ast.AST) -> list[ast.AST]:
    """The nodes of `fn`'s own body, not those of a function written inside it."""
    out, todo = [], list(ast.iter_child_nodes(fn))
    while todo:
        node = todo.pop()
        out.append(node)
        if not isinstance(node, (*_FUNCTIONS, ast.Lambda, ast.ClassDef)):
            todo += list(ast.iter_child_nodes(node))
    return out


def _either(one: Written, other: Written) -> Written:
    """What one of two dicts writes: what both always write, always; the rest, sometimes."""
    always = one[0] & other[0]
    return always, (one[0] | one[1] | other[0] | other[1]) - always


def _called(value: ast.AST) -> str | None:
    """The function `value` calls — `f(…)`, `await f(…)` or `await asyncio.to_thread(f, …)`."""
    if isinstance(value, ast.Await):
        value = value.value
    if not isinstance(value, ast.Call):
        return None
    if isinstance(value.func, ast.Name):
        return value.func.id
    if (isinstance(value.func, ast.Attribute) and value.func.attr == "to_thread"
            and value.args and isinstance(value.args[0], ast.Name)):
        return value.args[0].id
    return None


def _bindings(fn: ast.AST, name: str) -> list[ast.AST]:
    """Every value `fn` binds `name` to — `x = …`, `x: T = …`, and `x, y = a, b` element-wise."""
    out = []
    for node in _own(fn):
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            pairs = [(node.target, node.value)]
        elif isinstance(node, ast.Assign):
            pairs = [(target, node.value) for target in node.targets]
        else:
            continue
        for target, value in pairs:
            if isinstance(target, ast.Tuple) and isinstance(value, ast.Tuple):
                pairs += list(zip(target.elts, value.elts, strict=False))
            elif isinstance(target, ast.Name) and target.id == name:
                out.append(value)
    return out


def _made_by(tree: ast.AST, name: str, used: set) -> set[str]:
    """Every key the dict function `name` returns can carry: the keys of a dict literal it
    returns, and of the dict it returns by name — written in it, or assigned (`out["k"] = …`)."""
    fn = _function(tree, name)
    scopes = _scopes(tree)
    keys: set[str] = set()
    names: set[str] = set()
    for node in _own(fn):
        if isinstance(node, ast.Return) and node.value is not None:
            values = [node.value]
            while values:
                value = values.pop()
                if isinstance(value, ast.IfExp):
                    values += [value.body, value.orelse]
                elif isinstance(value, ast.Dict):
                    keys |= set().union(*_written(tree, scopes[value], value, used))
                elif isinstance(value, ast.Name):
                    names.add(value.id)
    for node in _own(fn):
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        for target in targets:
            if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                    and target.value.id in names and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)):
                keys.add(target.slice.value)
    for named in names:
        for value in _bindings(fn, named):
            if isinstance(value, ast.Dict):
                keys |= set().union(*_written(tree, scopes[value], value, used))
    assert keys, f"{name} returns no dict this test can read — has it moved?"
    return keys


def _spread(tree: ast.AST, inside: list[ast.AST], value: ast.AST, used: set) -> Written:
    """What a `**value` in a frame written inside `inside` writes into it."""
    if isinstance(value, ast.Dict):
        return _written(tree, inside, value, used)
    if isinstance(value, ast.IfExp):
        return _either(_spread(tree, inside, value.body, used),
                       _spread(tree, inside, value.orelse, used))
    if (called := _called(value)) is not None:
        return set(), _made_by(tree, called, used)
    if isinstance(value, ast.Name):
        for depth, fn in enumerate(inside):
            if (fn.name, value.id) in UNREAD_SPREADS:
                used.add((fn.name, value.id))
                return set(), set()
            bound = _bindings(fn, value.id)
            if bound:
                written = [_spread(tree, inside[depth:], b, used) for b in bound]
                out = written[0]
                for more in written[1:]:
                    out = _either(out, more)
                return out
    raise AssertionError(f"a spread this test cannot read: **{ast.unparse(value)} — read it, or "
                         f"name it in UNREAD_SPREADS with where its keys are read")


def _written(tree: ast.AST, inside: list[ast.AST], frame: ast.Dict, used: set) -> Written:
    """The keys `frame`, written inside the functions `inside`, writes: (always, sometimes)."""
    always: set[str] = set()
    sometimes: set[str] = set()
    for key, value in zip(frame.keys, frame.values, strict=True):
        if key is None:
            more_always, more_sometimes = _spread(tree, inside, value, used)
            always |= more_always
            sometimes |= more_sometimes
        elif isinstance(key, ast.Constant) and isinstance(key.value, str):
            always.add(key.value)
        else:
            raise AssertionError(f"a key this test cannot read: {ast.unparse(key)}")
    return always, sometimes - always


def _socket_frames(tree: ast.AST, scope: ast.AST, used: set) -> list[tuple[str, set, set]]:
    """(kind, always, sometimes) of every frame literal in `scope`: a dict whose `kind` is a
    constant string."""
    scopes = _scopes(tree)
    out = []
    for node in ast.walk(scope):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            if (isinstance(key, ast.Constant) and key.value == "kind"
                    and isinstance(value, ast.Constant) and isinstance(value.value, str)):
                always, sometimes = _written(tree, scopes[node], node, used)
                out.append((value.value, always - {"kind"}, sometimes))
    return out


def _fields(kind: str) -> tuple[set[str], set[str]]:
    """(named, required) fields of `kind`'s data model."""
    from openfactory.api.events import DATA_MODELS

    return _named_and_required(DATA_MODELS[kind])


def _named_and_required(model) -> tuple[set[str], set[str]]:
    fields = model.model_fields
    return set(fields), {name for name, f in fields.items() if f.is_required()}


def _emitted(used: set | None = None) -> dict[str, list[tuple[str, set, set]]]:
    used = set() if used is None else used
    app = _tree(APP)
    chat = _tree(PRODUCT_CHAT)
    return {FLOOR: _socket_frames(app, _function(app, "stream"), used),
            CHAT: _socket_frames(chat, chat, used)}


@pytest.mark.parametrize("stream", [FLOOR, CHAT])
def test_a_socket_emits_exactly_the_kinds_streams_says(stream):
    from openfactory.api.events import STREAMS

    frames = _emitted()[stream]
    assert frames, f"no frame literal found for {stream} — has its emitter moved?"
    assert {kind for kind, _always, _sometimes in frames} == set(STREAMS[stream])


@pytest.mark.parametrize("stream", [FLOOR, CHAT])
def test_every_field_a_socket_frame_writes_is_named_by_its_kind(stream):
    for kind, always, sometimes in _emitted()[stream]:
        named, required = _fields(kind)
        lifted = LIFTED.get(kind, set())   # onto the envelope
        keys = (always | sometimes) - lifted
        assert keys <= named, (kind, sorted(keys - named))
        assert required <= always, (kind, sorted(required - always))


def test_a_key_every_frame_of_a_kind_writes_is_required():
    """`events.py`'s rule: a field a producer always writes is required. A key every frame of a
    kind writes, on both sockets, is one a reader may count on — so its model requires it, and a
    key written only sometimes stays optional (`required <= always` above)."""
    always_by_kind: dict[str, list[set[str]]] = {}
    for frames in _emitted().values():
        for kind, always, _sometimes in frames:
            always_by_kind.setdefault(kind, []).append(always - LIFTED.get(kind, set()))
    for kind, alwayses in always_by_kind.items():
        _named, required = _fields(kind)
        every = set.intersection(*alwayses)
        assert every <= required, (kind, sorted(every - required))


def test_every_spread_this_cannot_read_is_one_it_says_where_it_reads():
    """An entry of `UNREAD_SPREADS` no frame spreads any more would excuse the next one silently."""
    used: set = set()
    _emitted(used)
    assert used == set(UNREAD_SPREADS), sorted(set(UNREAD_SPREADS) - used)


def test_a_turn_and_what_waits_are_the_rows_their_builders_write():
    """`history` and `earlier` carry turns, and `history` and `staged` what waits: a turn is the
    row `_history` builds, what waits the dict `staging.waiting_in` returns. Their models name
    every key either writes, and require exactly what it always writes."""
    from openfactory.api.events import Staged, Turn

    chat = _tree(PRODUCT_CHAT)
    turns = [n.elt for n in ast.walk(_function(chat, "_history"))
             if isinstance(n, ast.ListComp) and isinstance(n.elt, ast.Dict)]
    assert len(turns) == 1, "the turn `_history` builds has moved"
    staging = _tree(STAGING)
    waits = [n.value for n in ast.walk(_function(staging, "waiting_in"))
             if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
    assert len(waits) == 1, "what `waiting_in` returns has moved"
    for model, tree, row in ((Turn, chat, turns[0]), (Staged, staging, waits[0])):
        always, sometimes = _written(tree, _scopes(tree)[row], row, set())
        named, required = _named_and_required(model)
        assert always | sometimes <= named, (model.__name__, sorted((always | sometimes) - named))
        assert required == always, (model.__name__, sorted(required ^ always))


def test_the_temporal_frame_writes_only_what_jobs_data_names():
    app = _tree(APP)
    scopes = _scopes(app)
    gen = _function(app, "temporal_stream")
    named, required = _fields("jobs")
    frames = [_written(app, scopes[n], n, set()) for n in ast.walk(gen)
              if isinstance(n, ast.Dict) and "connected" in _keys(n)]
    assert len(frames) >= 3, "the frames before connecting, connected and after a blip have moved"
    for always, sometimes in frames:
        assert always | sometimes <= named, sorted((always | sometimes) - named)
        assert required <= always, sorted(required - always)
    # …and what EVERY frame writes, a reader may count on: the model requires it
    every = set.intersection(*(always for always, _sometimes in frames))
    assert every <= required, sorted(every - required)
    # the connected frame says where the engine's UI is, through `_engine_ui`, and carries the
    # cached intake and build it spreads
    assert any({"ui_base", "ui_hint", "intake", "build"} <= always | sometimes
               for always, sometimes in frames)


def test_the_temporal_read_names_every_key_it_answers():
    """`/api/temporal/jobs` answers the payload the temporal stream pushes, `ui_base` and `ui_hint`
    included, which the default front end reads: its read model names every key it writes."""
    from openfactory.api.read_models import EngineJobsRead

    keys = _made_by(_tree(APP), "temporal_jobs", set())
    named = set(EngineJobsRead.model_fields)
    assert {"connected", "jobs", "ui_base", "ui_hint"} <= keys, "the temporal read has moved"
    assert keys <= named, sorted(keys - named)


def test_the_floor_update_carries_the_bodies_of_the_reads_it_repeats():
    """`_stream_snapshot` fills each section of `update` by calling a read's handler — the
    projects `/api/projects` answers, the messages `/api/messages/{project}` answers — so each
    section is typed as the model that read declares, row for row."""
    from typing import get_args

    from fastapi.routing import APIRoute
    from pydantic import RootModel

    import openfactory.api.app as app_module
    from openfactory.api.events import UpdateData

    sections: dict[str, str] = {}
    for node in _own(_function(_tree(APP), "_stream_snapshot")):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                    sections[target.slice.value] = node.value.func.id
    assert set(sections) == set(UpdateData.model_fields), sections
    for section, handler in sections.items():
        endpoint = getattr(app_module, handler)
        declared = {r.response_model for r in app_module.app.routes
                    if isinstance(r, APIRoute) and r.endpoint is endpoint}
        assert len(declared) == 1, (handler, declared)
        (model,) = declared
        answered = (model.model_fields["root"].annotation if issubclass(model, RootModel)
                    else model)
        typed = [a for a in get_args(UpdateData.model_fields[section].annotation)
                 if a is not type(None)]
        assert typed == [answered], (section, typed, answered)


def test_ended_writes_why_status_and_a_refusal_body_ended_data_names():
    """`ended`, and `bye.ended`, are the gate's answer: `why`, `status`, and the body of whichever
    refusal it was — every `_Refusal` the gate builds."""
    from typing import get_args

    import openfactory.api.app as app_module
    from openfactory.api.events import EndedData

    app = _tree(APP)
    named, required = _fields("ended")
    whys = set(app_module._ENDED_WHY.values()) | {app_module._ENDED_UNAVAILABLE}
    assert whys == set(get_args(EndedData.model_fields["why"].annotation))
    answered = _returned_keys(app, "asked")
    assert answered == [{"why", "status"}], "the ended frame's own keys have moved"
    bodies = []
    for call in ast.walk(app):
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "_Refusal" and len(call.args) == 2):
            body = call.args[1]
            if isinstance(body, ast.Dict):
                bodies.append(_keys(body))
            elif isinstance(body, ast.Call) and isinstance(body.func, ast.Name):
                bodies += _returned_keys(app, body.func.id)
            else:
                raise AssertionError(f"a refusal body this test cannot read: {ast.dump(body)}")
    assert len(bodies) >= 4
    for body in bodies:
        keys = {"why", "status"} | body
        assert keys <= named, sorted(keys - named)
        assert required <= keys, sorted(required - keys)
    # …and what EVERY refusal writes, a reader may count on: the model requires it
    assert {"why", "status"} | set.intersection(*bodies) <= required


def test_a_log_frame_is_a_journal_line_field_for_field():
    from openfactory.api.events import LogData
    from openfactory.observability.events import JobEvent

    assert set(LogData.model_fields) == set(JobEvent.model_fields)
    assert ({n for n, f in LogData.model_fields.items() if f.is_required()}
            == {n for n, f in JobEvent.model_fields.items() if f.is_required()})
    # and each field is the journal's type — `kind` the journal's closed `EventKind`, not any
    # string; `data` is the journal's bare `dict`, spelled out here as `dict[str, Any]`
    for name, field in JobEvent.model_fields.items():
        if name != "data":
            assert LogData.model_fields[name].annotation == field.annotation, name
