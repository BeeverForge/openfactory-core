"""#679 slice a, proven by breaking it — the event models describe what the streams write.

THE CLAIM: `openfactory/api/events.py` names every kind and every field the four streams write
today, so a client reading `docs/reference/events.schema.json` learns each frame's shape without
reading the default front end. A description no test compares with the emitters drifts the first
time somebody renames a frame, so the guard reads the emitters' source as well as their outputs.

THE FIRST FIVE CUTS ARE THE REVIEW'S (on 2e105d7): each was green against a test whose frames
were dict literals written beside it. The next four put back the fields that review found unnamed —
the temporal frame's `ui_base`/`ui_hint`, which the default front end reads, and the refusal's
`detail` and `login` on `ended` and `bye.ended`.

G1 TO G5 ARE THE RE-REVIEW'S (on f22e034): each renames a key that reaches a frame other than
as a constant key of the frame's own literal — through a function a frame spreads by a name bound
from it (`first`), a conditional dict it spreads, or a row it nests (a turn, what waits) — and each
stayed green while the guard read only the literal's own keys.

The guard under test is `tests/test_the_event_models_describe_every_frame_the_streams_send.py`.
"""

TEST = "tests/test_the_event_models_describe_every_frame_the_streams_send.py"

APP = "openfactory/api/app.py"
CHAT = "openfactory/api/product_chat.py"
EVENTS = "openfactory/api/events.py"
STAGING = "openfactory/product/staging.py"

MUTATIONS = [
    # ── the emitters move, the models do not ───────────────────────────────────────────────────
    ("E1: the chat's `resync` frame is renamed, and the models still say `resync`", CHAT,
     '            sub.frames.put_nowait((sub.generation, {"kind": "resync"}))',
     '            sub.frames.put_nowait((sub.generation, {"kind": "behind"}))'),

    ("E2: the ack's `ahead` is renamed, and `AckData` still names `ahead`", CHAT,
     '"state": data.get("state", ""), "ahead": data.get("ahead", 0)})',
     '"state": data.get("state", ""), "behind": data.get("ahead", 0)})'),

    ("E3: the temporal frame's `connected` is renamed, and `JobsData` still requires it", APP,
     '                frame = {"connected": True, "address": addr, **_engine_ui(tv),',
     '                frame = {"online": True, "address": addr, **_engine_ui(tv),'),

    ("E4: the floor's `hello` is renamed, and `STREAMS` still says the floor sends `hello`", APP,
     '        await ws.send_text(json.dumps({"kind": "hello", "tick": _STREAM_TICK}))',
     '        await ws.send_text(json.dumps({"kind": "hi", "tick": _STREAM_TICK}))'),

    ("C9: `STREAMS` claims the floor's socket emits `presence`, which it never writes", EVENTS,
     '    "/api/stream": ("hello", "update", "bye"),',
     '    "/api/stream": ("hello", "update", "bye", "presence"),'),

    # ── the fields the review found unnamed ────────────────────────────────────────────────────
    ("`JobsData` stops naming the engine UI's `ui_base` and `ui_hint`, which every connected "
     "frame carries and the default front end reads", EVENTS,
     "    ui_base: str | None = None\n    ui_hint: str | None = None\n", ""),

    ("`EndedData` makes `detail` optional again, though every refusal body writes it", EVENTS,
     "    detail: str\n", "    detail: str | None = None\n"),

    ("`EndedData` stops naming `login`, which a 401 from a provider with a login page writes",
     EVENTS,
     "    detail: str\n    login: str | None = None\n", "    detail: str\n"),

    ("`LogData` loses a field the journal's `JobEvent` writes", EVENTS,
     "    ts: str\n    job_id: str\n    ticket_id: str\n",
     "    ts: str\n    ticket_id: str\n"),

    # ── a key that reaches a frame other than as the literal's own ─────────────────────────────
    ("G1: the floor's `update` writes `project_list` for `projects`, through `_stream_snapshot` "
     "and the `first` it is bound to", APP,
     'out["projects"] = list_projects()', 'out["project_list"] = list_projects()'),

    ("G2: a turn of `history` and `earlier` writes `who` for `actor` (`_history`)", CHAT,
     '"actor": agent if t.role == "agent" else (t.actor or ""),',
     '"who": agent if t.role == "agent" else (t.actor or ""),'),

    ("G3: `presence` writes `doing` for `stage`, in the conditional dict it spreads", CHAT,
     '**({"stage": stage} if stage else {})}', '**({"doing": stage} if stage else {})}'),

    ("G4: what waits writes `ticket` for `token` (`staging.waiting_in`)", STAGING,
     'return {"token": wait.token,', 'return {"ticket": wait.token,'),

    ("G5: `said` writes `files` for `attachments`, in the conditional dict it spreads", CHAT,
     '**({"attachments": list(entry["attachments"])}', '**({"files": list(entry["attachments"])}'),
]
