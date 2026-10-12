"""What each read of the front-end API answers, as a model (#678, slice a).

The routes in `app.py` answered `-> dict`, so the description FastAPI serves said "an object" for
the floor, the board and the inbox alike, and a screen of one's own had to read `panel.html` to
learn what any of them carries. Each read route now declares one of these as its
`response_model`, and the description names its fields.

THE BODIES DID NOT CHANGE, AND TWO RULES KEEP IT SO:

  · EVERY MODEL ALLOWS WHAT IT DOES NOT NAME (`extra="allow"`). A key a route adds tomorrow, or one
    a nested producer carries today and nothing here spells out, reaches the client as it did —
    a model that filtered it would be a body change made by a declaration.
  · A KEY A ROUTE LEAVES OUT STAYS OUT. The routes declare these with
    `response_model_exclude_unset=True` (`app._reads`), so a field with a default is never written
    into a body that did not carry it: `pr` is absent from a board with no board, not `null`.

A FIELD IS REQUIRED WHERE EVERY BRANCH THAT PRODUCES THE BODY WRITES IT, and has a default
otherwise. The card and the pull request a person opens on the board are drawn by helpers that each
ask a vendor and degrade on their own, so beyond `ref` their fields are named with defaults: a body
the model refuses is a 500 on the panel, and a declaration must not be what breaks a page.

A NUMBER IS `int | float`, never `float`: validated as `float`, a `3` is sent as `3.0`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, RootModel

#: A count or an amount, sent as the route computed it — see the module's last paragraph.
Number = int | float


class ReadModel(BaseModel):
    """A body one read route answers: its named fields, and whatever else it carries."""

    model_config = ConfigDict(extra="allow")


# ── the floor ───────────────────────────────────────────────────────────────────────────────────

class FloorRead(ReadModel):
    """`/api/floor[/{project}]` — whether the factory is working (`floor.ladder.FloorState`)."""

    scope: str
    word: str
    short: str
    level: str
    rung: int
    cause: str
    clause: str
    line: str
    detail: str
    cmd: str
    meta: str
    actions: list[dict[str, Any]]
    also: list[dict[str, Any]]
    also_more: int
    census: dict[str, Any] | None
    census_line: str
    per_project: dict[str, Any] | None
    ok: bool


# ── the jobs ────────────────────────────────────────────────────────────────────────────────────

class JournalJob(ReadModel):
    """One local job, read from its journal (`/api/jobs`, `/api/attention`)."""

    project: str
    issue: str
    state: str | None
    updated: str
    events: int
    pr_url: str | None
    cost_usd: Number | None


class JournalJobs(RootModel[list[JournalJob]]):
    """The local jobs, the most recently updated first."""


class EngineJob(ReadModel):
    """One job as the durable engine lists it (`runtime.temporal.view.list_jobs`)."""

    workflow_id: str | None = None
    run_id: str | None = None
    project: str | None = None
    issue: str | None = None
    title: str | None = None
    status: str | None = None
    state: str | None = None
    action: dict[str, Any] | None = None
    attention: bool | None = None
    wedged: bool | None = None


class EngineJobsRead(ReadModel):
    """`/api/temporal/jobs` — the jobs, live. `jobs` is `None` when nobody could ask the engine,
    `[]` when it answered and nothing is there."""

    connected: bool
    build: dict[str, Any] | None = None
    jobs: list[EngineJob] | None = None
    address: str | None = None
    error: str | None = None
    intake: dict[str, Any] | None = None


class JobDetailRead(ReadModel):
    """`/api/jobs/{project}/{issue}/detail` — one job's briefing, or `connected: false` and why."""

    connected: bool
    error: str | None = None


# ── the board ───────────────────────────────────────────────────────────────────────────────────

class BoardCard(ReadModel):
    ref: str
    column: str
    title: str
    labels: list[str]
    updated_at: str


class CardComment(ReadModel):
    author: str | None = None
    body: str | None = None
    created_at: str | None = None


class CardDetail(ReadModel):
    """The card a person opened: `readable: false` when it could not be read, and `comments: None`
    when its thread could not be, which is not `[]`."""

    ref: str
    readable: bool | None = None
    title: str | None = None
    body: str | None = None
    comments: list[CardComment] | None = None
    state: str | None = None
    opened_by_product: str | None = None


class PullRequestDetail(ReadModel):
    """The pull request a person opened (`app._pr_detail`). `events: None` could not be read."""

    ref: str
    state: str | None = None
    readable: bool | None = None
    body: str | None = None
    diff: str | None = None
    events: list[dict[str, Any]] | None = None
    refused: str | None = None
    can_merge_here: bool | None = None


class BoardRead(ReadModel):
    """`/api/board/{project}` — `columns`/`cards` are `None` when the board could not be read."""

    project: str
    columns: list[str] | None
    cards: list[BoardCard] | None
    poll_seconds: Number | None
    board: bool
    card: CardDetail | None
    pr: PullRequestDetail | None = None


# ── what needs a person ─────────────────────────────────────────────────────────────────────────

class HowToAnswer(ReadModel):
    method: str
    url: str


class Option(ReadModel):
    key: str
    label: str | None = None
    consequence: str | None = None


class InboxItem(ReadModel):
    """One thing a person must answer, and exactly how to POST the answer."""

    project: str | None
    issue: str | None
    title: str | None
    state: str | None
    kind: str
    note: str | None
    pr_url: str | None
    review: dict[str, Any]
    parked_at: Any
    wakes_at: Any
    retry_at: Any
    answer: HowToAnswer
    decision: dict[str, Any] | None = None
    options: list[Option] | None = None
    accepted: dict[str, Any] | None = None


class InboxRead(RootModel[list[InboxItem]]):
    """`/api/inbox` — what needs a person right now, in one shape for every channel."""


class ParkedDecision(ReadModel):
    project: str | None
    issue: str | None
    title: str | None
    state: str | None
    decision: dict[str, Any]


class DecisionsRead(RootModel[list[ParkedDecision]]):
    """`/api/decisions` — every job parked on a person's decision, with its question and options."""


# ── the budget ──────────────────────────────────────────────────────────────────────────────────

class BudgetRow(ReadModel):
    """One tracker credential's budget (`floor.reading.budgets`). `state` is
    `ok | low | unread | not_reported`; the numbers are there only for a vendor that reports one."""

    state: str
    kind: str | None = None
    projects: list[str] | None = None
    vendor: str | None = None
    resource: str | None = None
    remaining: Number | None = None
    limit: Number | None = None
    reset_epoch: Number | None = None
    floor: Number | None = None
    reset_at: str | None = None
    error: str | None = None


class BudgetRead(ReadModel):
    """`/api/budget` — one row per credential, and the one row a single sentence renders."""

    summary: BudgetRow
    rows: list[BudgetRow]


# ── the loops and the messages ──────────────────────────────────────────────────────────────────

class WaitingLoop(ReadModel):
    kind: str
    subject: str
    about: str
    owner: str
    state: str
    opened: str
    chased: str
    context: dict[str, Any]


class LoopsRead(ReadModel):
    """`/api/loops/{project}` — everything the agents are still waiting on."""

    project: str
    waiting: list[WaitingLoop]


class ChannelMessage(ReadModel):
    kind: str
    text: str
    ts: str
    channel: str
    token: str
    answer: str
    by: str


class PendingQuestion(ReadModel):
    token: str
    text: str
    ts: str
    options: list[Option]
    answer: HowToAnswer


class StagedSuggestion(ReadModel):
    """The one action the tech-lead proposed; `live: false` with a `reason` when it may be shown
    and not pressed."""

    token: str
    ts: str
    action: str
    issue: str | None
    params: dict[str, Any]
    labels: dict[str, str]
    live: bool
    reason: str
    act: HowToAnswer


class MessagesRead(ReadModel):
    """`/api/messages/{project}` — what the factory said to a project, and what it waits to hear."""

    project: str
    messages: list[ChannelMessage]
    pending: list[PendingQuestion]
    suggestion: StagedSuggestion | None


# ── the product room ────────────────────────────────────────────────────────────────────────────

class ProductProject(ReadModel):
    name: str


class ProductProjectsRead(RootModel[list[ProductProject]]):
    """`/api/product/projects` — the projects that have a product role, by name and nothing else."""


class SentFile(ReadModel):
    id: str | None = None
    name: str | None = None
    type: str | None = None
    size: int | None = None
    filed: bool | None = None


class AttachmentLimitsRead(ReadModel):
    """`/api/product/{project}/attachments` — what a message may carry, and, for a conversation the
    page names, the files sent in it."""

    accept: list[str]
    max_bytes: int
    max_per_message: int
    files: list[SentFile] | None = None


class ProductDocument(ReadModel):
    path: str
    title: str
    type: str
    audience: str


class UnreadableDocument(ReadModel):
    path: str
    type: str
    audience: str
    reason: str


class DocumentsRead(ReadModel):
    """`/api/product/{project}/documents` — `product.documents.ingest.overview`. `checked_at` is
    `None` before the first pass: nothing read yet is not nothing there."""

    project: str
    product: str
    checked_at: str | None
    read: int
    documents: list[ProductDocument]
    listed_all: bool
    unreadable: list[UnreadableDocument]
    internal_withheld: int
    unreadable_internal: list[UnreadableDocument] | None = None
    documents_internal: list[ProductDocument] | None = None


# ── the metrics ─────────────────────────────────────────────────────────────────────────────────

class MetricsTotals(ReadModel):
    cost_usd: Number
    tokens: int
    tasks: int
    avg_cost_per_task: Number
    avg_wall_s: Number
    agent_runs: int


class MetricsRead(ReadModel):
    """`/api/metrics` — `api.metrics_view.cost_dashboard`: spend by period, model, harness and role,
    the per-task table, and the project's autonomy."""

    projects: list[str]
    project: str
    runs: list[dict[str, Any]]
    knowledge_ab: dict[str, Any]
    by_day: dict[str, Number]
    by_model: dict[str, Number]
    by_harness: dict[str, Number]
    by_role: dict[str, Number]
    tasks: list[dict[str, Any]]
    totals: MetricsTotals
    autonomy: dict[str, Any]


# ── who is asking, and what may be asked ────────────────────────────────────────────────────────

class WhoamiRead(ReadModel):
    """`/api/whoami`. `scopes: None` is unscoped — not `[]`, which is no area at all."""

    id: str | None
    display: str
    known: bool
    scopes: list[str] | None
    logout: str | None


class ActionRow(ReadModel):
    """One catalogued action. `still_in` names the old route an action not yet moved into the layer
    still lives behind; `available` is its absence."""

    name: str
    summary: str
    required: list[str]
    optional: list[str]
    needs_admin: bool
    params: dict[str, str]
    choose_when: str | None
    available: bool
    still_in: str | None


class ActionsRead(RootModel[list[ActionRow]]):
    """`/api/actions` — the catalogue of what this deployment can be asked to do."""
