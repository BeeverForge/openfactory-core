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

THE REQUIRED-OR-OPTIONAL ROWS cut a model, and every cut to a model is also red through the
byte-for-byte schema test, which writing the schema again satisfies. So each is aimed at the one
test that reads the emitters and must see it without that help: a key every frame of a kind
writes is required, and a row's model requires exactly what its builder always writes.

THE TYPED SHAPES (review point 7): the floor's `projects` rows are `/api/projects`' rows, a log
line's `kind` is the journal's closed set, and the temporal read's model names the engine UI's
two keys the stream's model already named.

THE PUBLISHED TEXT (review point 9): a description in the schema names no card; the ids stay
in the code's comments.

AN ANSWER NAMES ITS PRODUCT (#1088): an `ack` or a `refused` about a product this person may read
names it on the socket, and its event carries it; one about none, or to a credential that may
not read the product area, names none. The socket's rows are aimed at the chat's own tests, which
drive the real socket (`tests/test_the_panel_is_a_chat.py`).

THE LAST ROWS hold the rules the tests state that the first review named and no row covered:
how `from_frame` reads a frame (C10, C11), what the command answers when it cannot write (C12),
and which kinds carry a product (C5, C6, C14) — the latter aimed, like the model rows above, at
the test that states the rule rather than at the schema drift test — and three more cuts of the
same rules, taken from the factory's own repair of this plan.

The guard under test is `tests/test_the_event_models_describe_every_frame_the_streams_send.py`.
"""

TEST = "tests/test_the_event_models_describe_every_frame_the_streams_send.py"
ONE = TEST + "::"

APP = "openfactory/api/app.py"
CHAT = "openfactory/api/product_chat.py"
EVENTS = "openfactory/api/events.py"
STAGING = "openfactory/product/staging.py"
READS = "openfactory/api/read_models.py"
CHAT_TEST = "tests/test_the_panel_is_a_chat.py::"

MUTATIONS = [
    # ── the emitters move, the models do not ───────────────────────────────────────────────────
    ("E1: the chat's `resync` frame is renamed, and the models still say `resync`", CHAT,
     '            sub.frames.put_nowait((sub.generation, {"kind": "resync"}))',
     '            sub.frames.put_nowait((sub.generation, {"kind": "behind"}))'),

    ("E2: the ack's `ahead` is renamed, and `AckData` still names `ahead`", CHAT,
     '"state": data.get("state", ""), "ahead": data.get("ahead", 0),',
     '"state": data.get("state", ""), "behind": data.get("ahead", 0),'),

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

    # ── what every frame writes is required ────────────────────────────────────────────────────
    ("C1: `JobsData.jobs` is optional, though every temporal frame writes it", EVENTS,
     "    jobs: list[EngineJob] | None\n", "    jobs: list[EngineJob] | None = None\n",
     ONE + "test_the_temporal_frame_writes_only_what_jobs_data_names"),

    ("C2: `SaidData.mine` is optional, though every `said` writes it", EVENTS,
     "    speaker: str\n    mine: bool\n", "    speaker: str\n    mine: bool | None = None\n",
     ONE + "test_a_key_every_frame_of_a_kind_writes_is_required"),

    ("`HistoryData.staged` is optional, though every `history` writes it (`null` when nothing "
     "waits)", EVENTS,
     "    turns: list[Turn]\n    staged: Staged | None\n",
     "    turns: list[Turn]\n    staged: Staged | None = None\n",
     ONE + "test_a_key_every_frame_of_a_kind_writes_is_required"),

    ("a turn's `actor` is optional, though `_history` writes it on every turn", EVENTS,
     "    role: str\n    actor: str\n", "    role: str\n    actor: str | None = None\n",
     ONE + "test_a_turn_and_what_waits_are_the_rows_their_builders_write"),

    ("G6: `reply` stops writing `options`, which it always wrote", CHAT,
     '"options": reply.get("options") or None,', ""),

    # ── how a frame is read onto the envelope, and the command ─────────────────────────────────
    ("C10: `from_frame` keeps the floor `update`'s `project` in `data` as well", EVENTS,
     'project = data.pop("project")', 'project = data.get("project")'),

    ("C11: an event stream's `ended` is read as the stream's own kind", EVENTS,
     "kind = ENDED if event == ENDED else kinds[0]", "kind = kinds[0]"),

    ("C12: the command exits 0 when it could not write the schema", EVENTS,
     '        return 1\n    print(f"wrote {target}")',
     '        return 0\n    print(f"wrote {target}")'),

    # ── which kinds carry a product ────────────────────────────────────────────────────────────
    ("C5: `hello` is made a kind a product owns", EVENTS,
     "class HelloEvent(_Unowned):", "class HelloEvent(_Owned):",
     ONE + "test_product_is_absent_or_null_for_a_kind_that_does_not"),

    ("C6: `resync` is no longer a kind a product owns", EVENTS,
     "class ResyncEvent(_Owned):", "class ResyncEvent(_Unowned):",
     ONE + "test_product_is_required_for_a_kind_that_belongs_to_a_product"),

    ("C14: a product kind accepts an empty `product`", EVENTS,
     "    product: str = Field(min_length=1)\n", "    product: str\n",
     ONE + "test_product_is_required_for_a_kind_that_belongs_to_a_product"),

    # the next three are cuts the factory's own repair of this plan made (28272dc3, rows C6, C11
    # and C12 there): the same rules, broken another way
    ("a kind no product owns accepts a `product`", EVENTS,
     "    product: None = None\n", "    product: str | None = None\n",
     ONE + "test_product_is_absent_or_null_for_a_kind_that_does_not"),

    ("`from_frame` writes `product` on every envelope, `null` where the kind has none", EVENTS,
     '    if product is not None:\n        out["product"] = product\n',
     '    out["product"] = product\n'),

    ("the command exits 1 without saying why it could not write", EVENTS,
     '        print(f"could not write {target}: {exc}", file=sys.stderr)\n', ""),

    # ── the shapes that were left open ─────────────────────────────────────────────────────────
    ("`UpdateData.projects` is free-form rows again, not the rows `/api/projects` declares", EVENTS,
     "    projects: list[ProjectRow] | None = None\n",
     "    projects: list[dict[str, Any]] | None = None\n",
     ONE + "test_the_floor_update_carries_the_bodies_of_the_reads_it_repeats"),

    ("`LogData.kind` is any string, not the journal's `EventKind`", EVENTS,
     "    kind: EventKind\n", "    kind: str\n",
     ONE + "test_a_log_frame_is_a_journal_line_field_for_field"),

    ("`EngineJobsRead` stops naming `ui_base` and `ui_hint`, which `/api/temporal/jobs` answers",
     READS, "    ui_base: str | None = None\n    ui_hint: str | None = None\n", "",
     ONE + "test_the_temporal_read_names_every_key_it_answers"),

    # ── the published text names no card ───────────────────────────────────────────────────────
    ("the schema's own description is the module's first line again, card id and all", EVENTS,
     '        "description": DESCRIPTION,\n',
     '        "description": (__doc__ or "").split("\\n\\n")[0].strip(),\n',
     ONE + "test_no_description_the_schema_publishes_names_a_card"),

    ("`JobsData`'s published description names the card its UI fields came from", EVENTS,
     'for the link when nobody said (`ui_hint`, `""` when `ui_base` is known)."""',
     'for the link when nobody said (`ui_hint`, `""` when `ui_base` is known) — #183."""',
     ONE + "test_no_description_the_schema_publishes_names_a_card"),

    ("`AckData`'s published description names a card four digits long (#1088), which the "
     "three-digit pattern of the help-screen sweep reads as a year", EVENTS,
     'What became of a message the page sent, by the id the page gave it."""',
     'What became of a message the page sent, by the id the page gave it (#1088)."""',
     ONE + "test_no_description_the_schema_publishes_names_a_card"),

    # ── an answer names the product it is about (#1088) ────────────────────────────────────────
    ("the ack of a message sent into the subscribed conversation stops naming its product", CHAT,
     '"ahead": data.get("ahead", 0),\n                     "product": sub.product})',
     '"ahead": data.get("ahead", 0)})',
     CHAT_TEST + "test_an_ack_and_a_refusal_name_the_product_they_answer_about"),

    ("the refusal of a conversation of a product the person may read stops naming it", CHAT,
     '"why": why, "product": product_key(project)})', '"why": why})',
     CHAT_TEST + "test_an_ack_and_a_refusal_name_the_product_they_answer_about"),

    ("the refusal of a message that broke stops naming the product it was sent to", CHAT,
     '**({"product": sub.product}', '**({}',
     CHAT_TEST + "test_an_ack_and_a_refusal_name_the_product_they_answer_about"),

    ("a credential that may not read the product area is told the product's key", CHAT,
     'await _tell({"kind": "refused", "why": "this credential may not read the product "',
     'await _tell({"kind": "refused", "product": product_key(project), '
     '"why": "this credential may not read the product "',
     CHAT_TEST + "test_a_credential_that_may_not_read_the_product_area_is_not_told_its_product"),

    ("an `ack` refuses a `product` again", EVENTS,
     "class AckEvent(_Answer):", "class AckEvent(_Unowned):",
     ONE + "test_an_answer_names_the_product_it_was_about_or_none"),

    ("an answer accepts an empty `product`", EVENTS,
     "    product: str | None = Field(default=None, min_length=1)\n",
     "    product: str | None = None\n",
     ONE + "test_an_answer_names_the_product_it_was_about_or_none"),

    ("`from_frame` leaves an answer's `product` in its `data` as well", EVENTS,
     'product = data.pop("product")', 'product = data.get("product")'),
]
