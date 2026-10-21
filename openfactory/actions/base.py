"""What an action IS — the vocabulary the front ends and the catalog share (C-23).

Three types and nothing else, because every one of them exists to stop a specific thing from
leaking across the seam:

    Actor       who asked, so an action never has to guess and a front end never has to decide
    Outcome     values out — no HTTP status, no mrkdwn, no emoji, no exception
    ActionSpec  a row in a table, so "which actions exist" is data a test can walk

**Outcome, not exceptions.** Both front ends already had a hard rule that they must always reply —
the Slack bot's `act_job` docstring says "NEVER raises (the bot must always reply)" and the panel
turns everything into an `HTTPException` by hand. Two front ends, two hand-written translations of
the same failures, and they disagreed: a job that is not parked is a 409 in the panel and the
sentence "não está parado esperando ação" in Slack, with no shared notion that those are the same
answer. `code` is that shared notion; rendering it stays each front end's job, which is the only
part that is genuinely theirs.

**`ok` is about the platform, not about the answer.** `scan` finding nothing in TO-DO is `ok=True`
with a message saying so — nothing went wrong, the queue is empty. `ok=False` means the platform
could not do the thing it was asked to do. Getting this backwards would make every empty queue
look like an outage in whatever dashboard reads these.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only the annotation needs it: the action layer is imported by the panel and the CLI, and
    # neither should load the identity package (its provider registry) just to name a type.
    from openfactory.identity.base import Subject

# ── the codes a front end maps ───────────────────────────────────────────────────────────────────
#
# A CLOSED SET, and `openfactory/api/app.py` holds a status for every member — asserted by a test,
# because
# a code with no mapping is a 500 wearing an action's name. Adding one here without adding it there
# fails the suite rather than production.

OK = ""
#: the caller asked for something malformed — a missing parameter, a ref no tracker could issue
INVALID = "invalid"
#: the caller is not allowed to do this
DENIED = "denied"
#: the project, ticket or job named does not exist
NOT_FOUND = "not_found"
#: the world is not in a state where this makes sense — a job not parked, one already running
CONFLICT = "conflict"
#: a dependency the platform needs is not answering — the durable engine, the forge
UNAVAILABLE = "unavailable"
#: it was attempted and it did not work
FAILED = "failed"
#: the action is catalogued but its implementation has not been moved into the layer yet
UNIMPLEMENTED = "unimplemented"

CODES = frozenset({OK, INVALID, DENIED, NOT_FOUND, CONFLICT, UNAVAILABLE, FAILED, UNIMPLEMENTED})


# ── why, in a word a program reads (#678, part 3) ────────────────────────────────────────────────
#
# A CODE IS WHAT A FRONT END MAPS; A REASON IS WHAT A PROGRAM BRANCHES ON. They are the same word
# wherever nothing finer was said — a row's own refusal states its code as its reason — and they
# part where one code covers answers a caller must tell apart: `denied` is both "this credential is
# scoped away from that area" and "you are not an admin", and only one of them is fixed by asking
# an admin. Every refusing Outcome carries one in `data["reason"]`, and every row declares in the
# catalogue which it can say (`ActionSpec.refuses`, `actions.reasons`).

#: `perform` was asked for a name no row has. Not any row's reason: there is no row to declare it.
UNKNOWN_ACTION = "unknown_action"
#: a required parameter is missing, or one the row does not take was passed
BAD_PARAMETERS = "bad_parameters"
#: the ticket ref is not one any tracker could issue
BAD_REF = "bad_ref"
#: the credential is scoped away from the area the row belongs to
OUT_OF_SCOPE = "out_of_scope"
#: the row needs an admin and the actor is not one
NOT_ADMIN = "not_admin"
#: the row needs the project's code and the project started before it (#992): its product has a
#: context repository and no code repository yet
NO_CODE_YET = "no_code_yet"
#: the durable engine did not answer in time
ENGINE_UNREACHABLE = "engine_unreachable"
#: the row's implementation raised — the answer's `data["reference"]` names its log line (#908)
RAISED = "raised"
#: the row's implementation returned something that is not an Outcome
REPORTED_NOTHING = "reported_nothing"

#: What `perform` itself may refuse ANY row with, before or around its runner — in the order it
#: checks them. `actions.reasons` narrows it per row: `bad_ref` only for a row that takes an
#: `issue`, `not_admin` only for one that `needs_admin`, `no_code_yet` only for one that
#: `needs_code` and takes a `project`.
AROUND_EVERY_ROW = (BAD_PARAMETERS, BAD_REF, OUT_OF_SCOPE, NOT_ADMIN, NO_CODE_YET,
                    ENGINE_UNREACHABLE, RAISED, REPORTED_NOTHING)

#: Every reason a refusal may carry. Closed, like `CODES`, so a typo is an error at the refusal
#: rather than a word no program was told to expect.
REASONS = frozenset(CODES - {OK}) | {UNKNOWN_ACTION, *AROUND_EVERY_ROW}


# ── where an action lives, and where a credential may go ─────────────────────────────────────────
#
# TWO AREAS TODAY, and the split is the one the product owner drew: *"if the person wants to write
# the tickets and drop them in TO-DO, fine — but the product role is available ON THE PLATFORM"*.
# A business analyst writing requirements is not an operator of the floor, and the panel's posture
# until now was that holding its credential made you both.

#: Jobs, the board, merges, the engine — the operator's console. The default for every row.
FLOOR = "floor"
#: The product role: requirements, their drafting, sign-off and withdrawal.
PRODUCT = "product"

#: Every area a row may declare. A registry rather than a free string, for the reason every other
#: registry in this codebase exists: a typo'd scope would otherwise be an area nobody can reach and
#: nothing would say so.
SCOPES = frozenset({FLOOR, PRODUCT})


# ── who asked ────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Actor:
    """The human (or bot) on whose behalf an action runs.

    EVERY ACTION TAKES ONE, including the read-only ones. Not because they all check it today —
    most do not — but because the parameter is the seam C-26 fills, and a parameter added later to
    forty call sites is a migration, while a parameter carried from the start is a rename. It is
    also already useful: `perform` makes one audit record of each call naming this (an
    `observability.audit.AuditRecord`), beside the audit line it already wrote, which is the first
    time this platform can answer *who approved that production release*.

    `admin` IS DECIDED BY THE TRANSPORT TODAY, and that is a stated limitation rather than a
    design. Slack knows its answer (`project.admins`), the panel's answer is "did they hold the
    panel token", and the CLI's is "they have a shell on the host, which outranks every action
    here". C-26 (#55) moves the decision behind this field into a policy the Core owns; until then
    the field is where the three front ends' three different answers meet, which is already one
    place fewer than before.
    """

    #: Stable id in whatever namespace the transport owns: a Slack user id (`U04…`), a panel
    #: principal, `cli`. Not required to be globally unique across transports — `via` disambiguates.
    id: str
    #: What to write in a note a human reads. Falls back to `id` when the transport has no name.
    display: str = ""
    #: Which front end carried the request: `panel`, `slack`, `cli`, `test`.
    via: str = ""
    #: Whether this actor may run an action marked `needs_admin`. See the caveat above.
    admin: bool = False
    #: WHICH AREAS OF THE PLATFORM this credential may act in at all, or `None` for one that is
    #: not scoped. `None` and `frozenset()` are different answers and the distinction is the whole
    #: point: `None` means nobody restricted this caller (the CLI, a Slack admin, the panel's own
    #: token — every actor that existed before scopes did, which is why the default cannot be
    #: `frozenset()` without denying all of them); `frozenset()` means somebody scoped it to
    #: nothing. The same `None` vs `[]` rule this codebase pays for everywhere else.
    #:
    #: WHY THIS IS NOT `admin`. A business analyst who writes requirements needs `needs_admin` to
    #: be TRUE for `product_accept` — accepting is the most consequential act on that surface — and
    #: needs `merge` to be refused outright. Those are two different questions: *how much authority
    #: within an area*, and *which areas at all*. Folding them into one flag is how handing a BA a
    #: credential to write a requirement also handed them the button that lands a pull request.
    scopes: frozenset[str] | None = None
    #: THE CONVERSATION THIS ACTOR IS IN, when the transport keys one per person (#33). On Slack
    #: a thread comes free and the rows take it as `thread`; on the web nothing did, so every
    #: person who typed into the panel's box wrote into ONE conversation keyed by the project's
    #: name, and the product role read A and B as one person. The panel fills this from the
    #: subject it resolved — `person:<id>` for somebody known, `visitor:<cookie>` for a browser
    #: nobody has identified yet — and a product row uses it when the caller passed no thread.
    #: Empty means the transport keys nothing, which is every actor that predates this.
    conversation: str = ""
    #: WHAT AN ANONYMOUS CALLER SAYS IT IS — a script's or a bot's own name for itself, sent on a
    #: shared token. A DISPLAY HINT AND NOTHING ELSE: it is not `id`, not `display`, and `str()`
    #: leaves it out, because those are what a row records as who acted, vouched or decided. Only
    #: `perform`'s audit line prints it, as `label=`, beside the credential that was really used.
    #: Empty for a named person, whose name is the provider's and not theirs to change.
    label: str = ""
    #: WHO THE IDENTITY AXIS SAID THIS IS, as the transport resolved it (ADR-0057 D1: "`Actor`
    #: carries the `Subject`"). The audit record reads its provider off `subject.via` — `local`,
    #: `oidc`, `anonymous` on the panel, `cli` for a shell login — so there is no second field
    #: naming the provider here. The panel (`api/app.py::_actor_of`) and the CLI
    #: (`cli.py::_cli_actor`) fill it. `None` when no subject was resolved: `SYSTEM`, a test, and
    #: every transport (the Slack add-on included) that predates this field.
    subject: Subject | None = None
    #: THE ID THAT TIES THIS CALL TO THE REQUEST THAT CAUSED IT, and to what it caused. Not *who
    #: asked*, which is all ADR-0039 §2 says an `Actor` is — it sits here because the `Actor` is the
    #: one value that already travels into the `perform` calls a row relays (`merge` → `approve`,
    #: the product rows that act on the floor), so a relayed call keeps its caller's id without
    #: every row passing a second argument. The panel fills it from `X-Request-ID`
    #: (`api/app.py::_correlation_of`), the CLI mints one per command (`cli.py::_cli_actor`), and
    #: `perform` gives a call that arrives with `""` one of its own before the row runs.
    correlation: str = ""

    def may_enter(self, scope: str) -> bool:
        """Whether this actor may act in `scope`. Unscoped actors may enter anywhere."""
        return self.scopes is None or scope in self.scopes

    def __str__(self) -> str:
        who = self.display or self.id or "anonymous"
        return f"{who} (via {self.via})" if self.via else who


#: For the paths that genuinely have no subject yet — a scheduled poll, an internal call. Kept as a
#: named constant rather than `Actor("")` at each site so a grep for it finds every place the
#: platform acts on nobody's behalf, which is exactly the list C-26 will want.
SYSTEM = Actor(id="system", display="the factory", via="internal", admin=True)


# ── what comes back ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Outcome:
    """Values out. No status code, no markup, no vendor.

    `message` is ONE human sentence in plain text. It may be shown to a client, so it says what
    happened and — when something is wrong — what to do about it, in the register the rest of this
    platform uses. It must not contain mrkdwn, HTML, or a provider's link syntax: the front end
    that knows the surface decorates it, and a message pre-decorated for Slack renders as literal
    asterisks in the panel (which is how the first version of the impediment alert shipped).
    """

    ok: bool
    message: str
    #: Values for a machine — what a panel renders as a table, what a script greps. Free-form per
    #: action and documented on its spec.
    data: Mapping[str, object] = field(default_factory=dict)
    #: One of CODES. Empty when `ok`.
    code: str = OK


def done(message: str, **data: object) -> Outcome:
    """It worked. `data` carries whatever the caller may want to render."""
    return Outcome(ok=True, message=message, data=data, code=OK)


def refused(code: str, message: str, *, reason: str = "", **data: object) -> Outcome:
    """It did not work, and this is why — in a word a front end can map and a sentence a human can
    read. Both are required: the word alone gives an operator nothing, and the sentence alone makes
    every front end parse prose to decide a status.

    `reason` lands in `data["reason"]`, and is `code` when nothing finer is said — so a refusal
    never lacks one. It must be one of `REASONS`, and one the row declares (`ActionSpec.refuses`).
    """
    if code not in CODES or code == OK:
        raise ValueError(f"unknown outcome code {code!r} — one of {sorted(CODES - {OK})}")
    why = reason or code
    if why not in REASONS:
        raise ValueError(f"unknown refusal reason {why!r} — one of {sorted(REASONS)}")
    return Outcome(ok=False, message=message, data={**data, "reason": why}, code=code)


def failure_reference() -> str:
    """A short reference for one failure, put in BOTH its log line and its answer (`data.reference`,
    #908), so the person who reports "it said it could not" hands an operator the line to read.
    Eight hex digits: a reference to quote, not an identifier to guess — the line it names carries
    nothing the answer did not already say to the same person."""
    return secrets.token_hex(4)


# ── the table ────────────────────────────────────────────────────────────────────────────────────

#: The signature every action has. Keyword-only, always async, always returns an Outcome.
Runner = Callable[..., Awaitable[Outcome]]


#: WHAT TO PUT IN EACH PARAMETER, keyed by its name — the vocabulary of the action layer (#172).
#:
#: SHARED RATHER THAN PER ROW, because `project` is required by 38 of the 40 rows and `issue` by
#: 12. Forty copies of "the project this concerns" is thirty-nine chances to drift, and the one
#: that drifts is the one somebody reads. A row that means something DIFFERENT by a shared word
#: says so on itself, in `ActionSpec.params`, and that override is the signal to a reader that this
#: row is unusual.
#:
#: THE AUDIENCE IS SOMEBODY WHO MUST FILL THE VALUE IN, which is why these say what goes in rather
#: than what the word denotes. Since #170 that audience includes a model composing a proposal for a
#: button a human presses: `adjust` required an `instruction` and nothing anywhere said what an
#: instruction should contain, so the only guidance was the English of the word.
PARAMS: dict[str, str] = {
    # the two nearly every row takes
    "project": "the project's name in this deployment's registry, e.g. `podbeam`",
    "issue": "the ticket's number on the client's board, digits only, e.g. `87`",
    # confirmation and shape
    "yes": "`true` to actually do it — without it the action reports what it WOULD do",
    "number": "the ticket's number on the client's board, digits only",
    "numbers": "the ticket numbers, comma-separated, e.g. `87,88,91`",
    "limit": "how many rows to return at most; the default is this deployment's",
    "force": "`true` to proceed past a check that would otherwise stop it — say why in `reason`",
    # words a human will read afterwards
    "reason": "one sentence a person will read later, saying WHY — it is stored and shown",
    "comment": "a sentence posted on the pull request as this platform's own voice",
    "instruction": "WHAT TO CHANGE, in one or two concrete sentences the coding pass will work "
                   "from: name the file or behaviour and the change wanted, not the symptom. It "
                   "is shown on the button a person presses, so it must be readable by them too",
    "message": "what you want to say, in your own words",
    "question": "the question, in one sentence",
    "query": "what to look for — a few words, a card number, a name",
    "answer": "the answer, in your own words",
    "answers": "answers to the questions asked, one per line as `field: value`",
    "choice": "which of the options the parked job offered — its exact label",
    "enabled": "`true` to let this project pick work up, `false` to hold it",
    # the release gate
    "version": "the version being released, exactly as it is tagged",
    "approver": "who is approving, by name — it is written into the release record",
    "password": "the release password this deployment was configured with",
    "promote": "`true` to carry the change on through the promotion chain after it lands",
    "sandbox": "`true` to run the job without letting it write anywhere real",
    "durable": "`true` to run on the durable engine rather than in this process",
    # the product role
    "token": "the token identifying the proposal being answered — copy it from the proposal",
    "thread": "the conversation this turn belongs to, if continuing one",
    "before": "the cursor of an earlier page of a conversation — the `earlier` value the page "
              "after it handed back; empty for the newest page",
    "context": "what the person is looking at: `{page, project, card}` as the panel's page says "
               "it — checked against who they are before the role reads it",
    "message_id": "this message's own id, so a retry of it is the same message and its answer "
                  "can be matched to it — letters, digits, `-` and `_`",
    "wait": "`false` to hand the message over and return at once, the answer arriving where the "
            "conversation is shown; the default waits for it",
    "mentioned": "`false` when the message was said in the room to the people there and does "
                 "not name the product role — it is kept, and starts no turn; the default is "
                 "that calling this row names the role",
    "in_favour_of": "the number of the card that STAYS — the one this duplicates",
    "requirement": "the requirement's id in its register, e.g. `REQ-014`",
    "decision": "the decision, stated as what will now be true",
    "term": "the word or phrase being defined, as the business says it",
    "body": "what it means, in the business's own words",
    "restated": "the broken promise, restated as what should happen and what happens instead",
    "text": ("what the card should say instead — it replaces what was asked, or what is "
             "happening, on a card the product role opened"),
    "title": "what it is called, in the person's own words — short",
    "head": ("the head the card's preview was built from, as the card showed it — the version the "
             "person tried; empty takes the one the preview shows now"),
    "criteria": ("what must be true for the card to be done, one statement per line — it replaces "
                 "the card's acceptance criteria; empty leaves them as they are"),
    "session": "which of your conversations — its id, as the page lists it; empty is your first",
    "attachments": "the ids of the files sent with the message, as the upload answered them",
    "attachment": "the id of one file sent in the conversation, as the upload answered it",
    "room": "yes for the project's room, no for one of your own conversations",
    "column": "the column's name as it is written on the board, e.g. `TO-DO`",
    "violates": "the id of the requirement this breaks, if one is known",
    "severity": "how bad it is: `low`, `medium` or `high`",
    # reading a repository
    "target": "the repository to read, as a URL or an `owner/name`",
    "ask": "a specific question to answer about the repository, if you have one",
    "write": "`true` to write the result into the repository rather than only report it",
    "accept": "which proposed fields to keep, comma-separated — the rest are dropped",
    "out": "where to write the file, if not the default place",
    "pr": "`true` to open a pull request with the change instead of committing directly",
    # a preview of the product (ADR-0050)
    "unit": "what the preview is of: a card's number, e.g. `34`, or a requirement as `req0012`",
}

#: THE PARAMETERS WHOSE VALUE IS A PERSON'S OWN WORDS — what they said, asked, decided or want
#: changed, as they typed it — named in the vocabulary above, the one place a parameter is
#: declared for every row (#694). The audit record keeps each of these as its length and sha256,
#: never as text (`observability.audit`): ADR-0024 holds a client's words for a retention period
#: and erases them on request (`forget-conversations`), and a record kept for a year beside every
#: call would otherwise hold a second copy nothing erases. The digest is unsalted, so it still
#: reveals a short answer ("yes", a six-digit code) to whoever tries the candidates.
#: A row that takes one of these names
#: takes it as free text; a new word of the same kind belongs here, beside its prose.
FREE_TEXT: frozenset[str] = frozenset({
    "reason", "comment", "instruction", "message", "question", "query", "answer", "answers",
    "decision", "term", "body", "restated", "text", "title", "criteria", "ask",
})


@dataclass(frozen=True)
class ActionSpec:
    """One row of the catalog: a name, what it needs, and the one implementation.

    `required`/`optional` are declared rather than read off the function signature by
    introspection. Introspection would be shorter and would also mean `perform` cannot tell a
    parameter it forgot to pass from one the action does not want — and the whole reason the
    parameters are checked centrally is that the two front ends validated different things.
    """

    name: str
    #: One line, present tense, for `openfactory act --list` and `GET /api/actions`. This is the
    #: text an operator reads when deciding what to run, so it says what happens, not what it is
    #: called.
    summary: str
    run: Runner
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    #: Whether `Actor.admin` is required. Default True: an action exists to CHANGE something, and
    #: the read-only ones say so explicitly. A default of False would mean a new action is
    #: unguarded unless somebody remembers, which is the wrong way round for this class of mistake.
    needs_admin: bool = True
    #: WHICH AREA of the platform this row belongs to — see `Actor.scopes`. Defaults to the floor
    #: (jobs, the board, merges, the engine), so a row added without thinking about scope lands in
    #: the area a scoped credential CANNOT reach. Same direction as `needs_admin`'s default: the
    #: forgetful case is the closed one.
    scope: str = FLOOR
    #: WHETHER THIS ROW NEEDS THE PROJECT'S CODE (#992). A product may start before its code — a
    #: context repository and no code repository (`contracts.project.before_its_code`) — and on
    #: such a project `perform` refuses a row that needs one, by name and before it runs, rather
    #: than letting it fail three layers down in a sentence about a clone. Default True, the
    #: direction of `needs_admin`'s and `scope`'s: a row added without thinking about it waits for
    #: the code, and the rows that work without it — the product owner's conversation, its
    #: requirements, its context — say so on themselves.
    needs_code: bool = True
    #: WHEN A PROPOSER SHOULD PICK THIS ROW over its neighbours — the judgment, not the definition
    #: (#172). `summary` says what the row does; this says when it is the right answer, which is a
    #: different question and the one that actually decides. It lived in a private map inside
    #: `techlead/conversation.py`, where it could disagree with the row it described — and did:
    #: `adjust` had no entry at all, so the verb that most needed the guidance had the least.
    #: Empty is honest for the rows nobody may propose; `proposable` is a much smaller set than
    #: the catalogue and only it is offered as a choice.
    choose_when: str = ""
    #: WHAT THIS ROW means by a parameter, when the shared `PARAMS` word is wrong for it. An
    #: override rather than a copy: a row that agrees says nothing, so the diff of this field is a
    #: list of the rows that are unusual.
    params: Mapping[str, str] = MappingProxyType({})
    #: WHAT THIS ROW'S OWN CODE PATHS REFUSE WITH — the reasons its runner can put in
    #: `data["reason"]`. Written on the row rather than discovered, because it is a promise to
    #: whoever reads `/api/actions`; `tests/test_the_action_layer.py` reads the runner's source and
    #: fails when the two disagree in either direction. What `perform` adds around every row is
    #: not repeated here: `actions.reasons` is the whole list.
    refuses: tuple[str, ...] = ()
    #: THE ROWS WHOSE OUTCOME THIS ONE HANDS BACK AS ITS OWN, reason included — `ask` performs the
    #: row a sentence names. Their reasons are this row's too.
    relays: tuple[str, ...] = ()

    def prose_for(self, param: str) -> str:
        """What to put in `param`, or `""` when nobody has said (#172).

        THREE ANSWERS COLLAPSED TO TWO ON PURPOSE, unlike the reads elsewhere in the platform: a
        parameter nobody wrote prose for and a parameter that needs no explanation are the same
        thing to the person filling it in. What must NOT happen is inventing a sentence from the
        name, which is what every front end would do on its own."""
        return self.params.get(param) or PARAMS.get(param, "")

    @property
    def described(self) -> dict[str, str]:
        """Every parameter this row takes, each with what to put in it — the shape a front end
        renders and `/api/actions` serves. Includes the ones with no prose, as empty strings: a
        parameter missing from this mapping would read as one the action does not take."""
        return {p: self.prose_for(p) for p in self.parameters}

    @property
    def pending(self) -> str:
        """Where the implementation still lives, or `""` when it has been moved into the layer.

        Not a boolean: an operator who hits `unimplemented` needs to know which old route still
        works, and a test needs to see the migration shrink."""
        return getattr(self.run, "moved_from", "")

    @property
    def parameters(self) -> tuple[str, ...]:
        return self.required + self.optional


def not_moved_yet(name: str, *, still_in: str) -> Runner:
    """A placeholder implementation that REFUSES, naming where the working path is.

    WHY A REFUSING RUNNER RATHER THAN AN ABSENT ROW. The catalog is what the guards walk, what the
    panel lists and what `openfactory act --list` prints. An action left out of it until somebody
    moves the code is invisible: no test can assert it is missing, and the migration has no
    measurable end. A row that refuses is visible in all three places and its refusal is a sentence
    somebody can act on, which is the same standard every other wait in this platform is held to.
    """

    async def run(**_params: object) -> Outcome:
        return refused(
            UNIMPLEMENTED,
            f"'{name}' is catalogued but its implementation has not moved into the action layer "
            f"yet — it still lives in {still_in}, which is where it works today (C-23).",
        )

    run.moved_from = still_in  # type: ignore[attr-defined]
    return run
