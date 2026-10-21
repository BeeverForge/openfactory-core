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

NO FIELD IS REQUIRED, AND EVERY ONE MAY BE `None`. The rows behind these bodies are read from
journals, stores and the engine, and a row written before a field existed, or by a producer that
leaves it null, is still a row the panel showed before these were declared. A body the model refuses
is a 500 on the panel, and a declaration must not be what breaks a page — so a field names what a
read carries, and never what it must.

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


class Refusal(ReadModel):
    """What a read answers when it refuses: ONE SENTENCE in `detail` — the shape every refusal of
    this API has (`docs/reference/the-front-end-api.md`, *Refusals*), declared for the statuses a
    read names (`app._read`'s `refusals`) so its description says them beside the body."""

    detail: str | None = None


# ── the floor ───────────────────────────────────────────────────────────────────────────────────

class FloorRead(ReadModel):
    """`/api/floor[/{project}]` — whether the factory is working (`floor.ladder.FloorState`)."""

    scope: str | None = None
    word: str | None = None
    short: str | None = None
    level: str | None = None
    rung: int | None = None
    cause: str | None = None
    clause: str | None = None
    line: str | None = None
    detail: str | None = None
    cmd: str | None = None
    meta: str | None = None
    actions: list[dict[str, Any]] | None = None
    also: list[dict[str, Any]] | None = None
    also_more: int | None = None
    census: dict[str, Any] | None = None
    census_line: str | None = None
    per_project: dict[str, Any] | None = None
    ok: bool | None = None


# ── the jobs ────────────────────────────────────────────────────────────────────────────────────

class JournalJob(ReadModel):
    """One local job, read from its journal (`/api/jobs`, `/api/attention`)."""

    project: str | None = None
    issue: str | None = None
    state: str | None = None
    updated: str | None = None
    events: int | None = None
    pr_url: str | None = None
    cost_usd: Number | None = None


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

    connected: bool | None = None
    build: dict[str, Any] | None = None
    jobs: list[EngineJob] | None = None
    address: str | None = None
    error: str | None = None
    intake: dict[str, Any] | None = None


class JobDetailRead(ReadModel):
    """`/api/jobs/{project}/{issue}/detail` — one job's briefing, or `connected: false` and why."""

    connected: bool | None = None
    error: str | None = None


# ── the board ───────────────────────────────────────────────────────────────────────────────────

class BoardCard(ReadModel):
    ref: str | None = None
    column: str | None = None
    title: str | None = None
    labels: list[str] | None = None
    updated_at: str | None = None


class CardComment(ReadModel):
    author: str | None = None
    body: str | None = None
    created_at: str | None = None


class CardDetail(ReadModel):
    """The card a person opened: `readable: false` when it could not be read, and `comments: None`
    when its thread could not be, which is not `[]`."""

    ref: str | None = None
    readable: bool | None = None
    title: str | None = None
    body: str | None = None
    comments: list[CardComment] | None = None
    state: str | None = None
    opened_by_product: str | None = None


class PullRequestDetail(ReadModel):
    """The pull request a person opened (`app._pr_detail`). `events: None` could not be read."""

    ref: str | None = None
    state: str | None = None
    readable: bool | None = None
    body: str | None = None
    diff: str | None = None
    events: list[dict[str, Any]] | None = None
    refused: str | None = None
    can_merge_here: bool | None = None


class BoardRead(ReadModel):
    """`/api/board/{project}` — `columns`/`cards` are `None` when the board could not be read."""

    project: str | None = None
    columns: list[str] | None = None
    cards: list[BoardCard] | None = None
    poll_seconds: Number | None = None
    board: bool | None = None
    card: CardDetail | None = None
    pr: PullRequestDetail | None = None


# ── what needs a person ─────────────────────────────────────────────────────────────────────────

class HowToAnswer(ReadModel):
    method: str | None = None
    url: str | None = None


class Option(ReadModel):
    key: str | None = None
    label: str | None = None
    consequence: str | None = None


class InboxItem(ReadModel):
    """One thing a person must answer, and exactly how to POST the answer."""

    project: str | None = None
    issue: str | None = None
    title: str | None = None
    state: str | None = None
    kind: str | None = None
    note: str | None = None
    pr_url: str | None = None
    review: dict[str, Any] | None = None
    parked_at: Any = None
    wakes_at: Any = None
    retry_at: Any = None
    answer: HowToAnswer | None = None
    decision: dict[str, Any] | None = None
    options: list[Option] | None = None
    accepted: dict[str, Any] | None = None


class InboxRead(RootModel[list[InboxItem]]):
    """`/api/inbox` — what needs a person right now, in one shape for every channel."""


class ParkedDecision(ReadModel):
    project: str | None = None
    issue: str | None = None
    title: str | None = None
    state: str | None = None
    decision: dict[str, Any] | None = None


class DecisionsRead(RootModel[list[ParkedDecision]]):
    """`/api/decisions` — every job parked on a person's decision, with its question and options."""


# ── the budget ──────────────────────────────────────────────────────────────────────────────────

class BudgetRow(ReadModel):
    """One tracker credential's budget (`floor.reading.budgets`). `state` is
    `ok | low | unread | not_reported`; the numbers are there only for a vendor that reports one."""

    state: str | None = None
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

    summary: BudgetRow | None = None
    rows: list[BudgetRow] | None = None


# ── the loops and the messages ──────────────────────────────────────────────────────────────────

class WaitingLoop(ReadModel):
    kind: str | None = None
    subject: str | None = None
    about: str | None = None
    owner: str | None = None
    state: str | None = None
    opened: str | None = None
    chased: str | None = None
    context: dict[str, Any] | None = None


class LoopsRead(ReadModel):
    """`/api/loops/{project}` — everything the agents are still waiting on."""

    project: str | None = None
    waiting: list[WaitingLoop] | None = None


class ChannelMessage(ReadModel):
    kind: str | None = None
    text: str | None = None
    ts: str | None = None
    channel: str | None = None
    token: str | None = None
    answer: str | None = None
    by: str | None = None


class PendingQuestion(ReadModel):
    token: str | None = None
    text: str | None = None
    ts: str | None = None
    options: list[Option] | None = None
    answer: HowToAnswer | None = None


class StagedSuggestion(ReadModel):
    """The one action the tech-lead proposed; `live: false` with a `reason` when it may be shown
    and not pressed."""

    token: str | None = None
    ts: str | None = None
    action: str | None = None
    issue: str | None = None
    params: dict[str, Any] | None = None
    labels: dict[str, str] | None = None
    live: bool | None = None
    reason: str | None = None
    act: HowToAnswer | None = None


class MessagesRead(ReadModel):
    """`/api/messages/{project}` — what the factory said to a project, and what it waits to hear."""

    project: str | None = None
    messages: list[ChannelMessage] | None = None
    pending: list[PendingQuestion] | None = None
    suggestion: StagedSuggestion | None = None


# ── the product room ────────────────────────────────────────────────────────────────────────────

class ProductProject(ReadModel):
    name: str | None = None


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

    accept: list[str] | None = None
    max_bytes: int | None = None
    max_per_message: int | None = None
    files: list[SentFile] | None = None


class ProductDocument(ReadModel):
    path: str | None = None
    title: str | None = None
    type: str | None = None
    audience: str | None = None


class UnreadableDocument(ReadModel):
    path: str | None = None
    type: str | None = None
    audience: str | None = None
    reason: str | None = None


class DocumentsRead(ReadModel):
    """`/api/product/{project}/documents` — `product.documents.ingest.overview`. `checked_at` is
    `None` before the first pass: nothing read yet is not nothing there."""

    project: str | None = None
    product: str | None = None
    checked_at: str | None = None
    read: int | None = None
    documents: list[ProductDocument] | None = None
    listed_all: bool | None = None
    unreadable: list[UnreadableDocument] | None = None
    internal_withheld: int | None = None
    unreadable_internal: list[UnreadableDocument] | None = None
    documents_internal: list[ProductDocument] | None = None


class ProductSearchHit(ReadModel):
    """One item a search of the product's published knowledge found. `kind` is `requirement`,
    `decision`, `document` or `card`; `source` is where it is — a document's path or a card's ref;
    `rank` is its place in this product's results, best first (`1` is the best). There is no raw
    score: a score is the index's own and is not comparable across products."""

    kind: str | None = None
    source: str | None = None
    product: str | None = None
    title: str | None = None
    snippet: str | None = None
    locator: str | None = None
    date: str | None = None
    rank: int | None = None


class ProductSearchRead(ReadModel):
    """`/api/product/{project}/search` — one product's published knowledge (its requirements, the
    decisions recorded in its documents, the documents and its board's cards), searched with `q`
    and a `limit`, in the product owner's own ranking. `degraded` says why the semantic stage did
    not run or ran on part of the index — or that the deployment turned the search off and nothing
    was searched — and is `""` when it ran whole; never silence. A blank `q` finds nothing. A line
    of a conversation and a conversation's distillate are never returned."""

    project: str | None = None
    product: str | None = None
    query: str | None = None
    degraded: str | None = None
    searched: int | None = None
    hits: list[ProductSearchHit] | None = None


# ── the metrics ─────────────────────────────────────────────────────────────────────────────────

class MetricsTotals(ReadModel):
    cost_usd: Number | None = None
    tokens: int | None = None
    tasks: int | None = None
    avg_cost_per_task: Number | None = None
    avg_wall_s: Number | None = None
    agent_runs: int | None = None


class MetricsRead(ReadModel):
    """`/api/metrics` — `api.metrics_view.cost_dashboard`: spend by period, model, harness and role,
    the per-task table, and the project's autonomy."""

    projects: list[str] | None = None
    project: str | None = None
    runs: list[dict[str, Any]] | None = None
    knowledge_ab: dict[str, Any] | None = None
    by_day: dict[str, Number] | None = None
    by_model: dict[str, Number] | None = None
    by_harness: dict[str, Number] | None = None
    by_role: dict[str, Number] | None = None
    tasks: list[dict[str, Any]] | None = None
    totals: MetricsTotals | None = None
    autonomy: dict[str, Any] | None = None


# ── who is asking, and what may be asked ────────────────────────────────────────────────────────

class WhoamiRead(ReadModel):
    """`/api/whoami`. `scopes: None` is unscoped — not `[]`, which is no area at all."""

    id: str | None = None
    display: str | None = None
    known: bool | None = None
    scopes: list[str] | None = None
    logout: str | None = None


class ActionRow(ReadModel):
    """One catalogued action. `still_in` names the old route an action not yet moved into the layer
    still lives behind; `available` is its absence. `refusals` is every reason a refusal of the row
    may carry in `data["reason"]`."""

    name: str | None = None
    summary: str | None = None
    required: list[str] | None = None
    optional: list[str] | None = None
    needs_admin: bool | None = None
    params: dict[str, str] | None = None
    choose_when: str | None = None
    available: bool | None = None
    still_in: str | None = None
    refusals: list[str] | None = None


class ActionsRead(RootModel[list[ActionRow]]):
    """`/api/actions` — the catalogue of what this deployment can be asked to do."""
