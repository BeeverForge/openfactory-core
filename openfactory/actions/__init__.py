"""The action layer — everything a human can ask the factory to DO, written once (C-23).

WHAT WAS ACTUALLY WRONG. The Slack bot never calls the HTTP API: zero httpx, zero requests, zero
aiohttp. The two front ends were written independently against the same domain, and by the time
this card was opened they had drifted in ways nobody chose:

    resume          the panel passes the DecisionRequest option key; Slack hard-codes ""
                    → a job parked with a real question can be answered from the panel and only
                      resumed blindly from Slack, in a channel where the question was posted
    ack             exists in Slack, does not exist in the panel at all
    enable / scan    exist in the panel, do not exist in Slack
    approve_prod    two implementations — a durable signal and an in-process PromotionRunner —
                    reachable from one front end each, under names that suggest they are the same
    validation      the panel checks the ref shape; Slack checks nothing

None of that is a bug anybody wrote. It is what happens when a capability has no home, and it is
the manifesto's empty SDK box: there was no layer for a third front end to be written against, so
a third front end would have made it three.

WHAT THIS LAYER IS. A table of actions. Each takes values and `by: Actor`, returns an `Outcome`,
and speaks no transport: no HTTP status, no mrkdwn, no Slack block, no exception escaping. The
front ends become mappings — a route or a verb picks a name and renders the result.

WHAT IT IS NOT. It is not authorization (C-26 / #55): `Actor.admin` is still decided by whoever
carried the request, and this layer only carries and records it. It is not the conversational
tech-lead (C-24 / #52): `ask` and `diagnose` are catalogued here and their brains still live in
the Slack package until that card moves them. Both are deliberate — putting either in this card
would mean designing identity or the agent's memory model inside a refactor, and that is how a
refactor becomes a rewrite.

REACHING IT. Two universal transports dispatch the whole catalog by name:

    POST /api/act/{name}    the panel and anything holding its token
    openfactory act <name> …  a shell on the host

and the named front-end paths (`/api/temporal/act`, the Slack verbs, `/api/projects/{n}/enabled`)
are mappings onto the same rows. That is the property the guards in
`tests/test_the_action_layer.py` hold: **every action is reachable from at least two transports and
implemented by none of them.**
"""

from __future__ import annotations

import logging
import re

from openfactory.actions.base import (
    AROUND_EVERY_ROW,
    BAD_PARAMETERS,
    BAD_REF,
    CODES,
    CONFLICT,
    DENIED,
    ENGINE_UNREACHABLE,
    FAILED,
    FLOOR,
    INVALID,
    NO_CODE_YET,
    NOT_ADMIN,
    NOT_FOUND,
    NOT_THE_INSTALLATIONS,
    OK,
    OUT_OF_SCOPE,
    PRODUCT,
    RAISED,
    REASONS,
    REPORTED_NOTHING,
    SCOPES,
    STEP_ALREADY,
    STEP_DONE,
    STEP_FAILED,
    STEP_SKIPPED,
    STEP_STATES,
    SYSTEM,
    UNAVAILABLE,
    UNIMPLEMENTED,
    UNKNOWN_ACTION,
    ActionSpec,
    Actor,
    Outcome,
    done,
    failure_reference,
    not_moved_yet,
    refused,
    step,
)

log = logging.getLogger("openfactory.actions")

__all__ = [
    "CATALOG", "CODES", "CONFLICT", "DENIED", "FAILED", "FLOOR", "INVALID", "NOT_FOUND", "OK",
    "PRODUCT", "REASONS", "SCOPES", "STEP_ALREADY", "STEP_DONE", "STEP_FAILED", "STEP_SKIPPED",
    "STEP_STATES", "SYSTEM", "UNAVAILABLE", "UNIMPLEMENTED", "ActionSpec", "Actor", "Outcome",
    "done", "names", "not_moved_yet", "perform", "proposable", "reasons", "refused", "run_staged",
    "spec", "step",
]


async def run_staged(*, project: str, by: Actor, token: str = "") -> Outcome:
    """Perform what the tech-lead staged for `project` — see `catalog.run_staged`.

    Re-exported lazily for the same reason `_Catalog` is: importing the implementations costs
    `temporalio`, and the panel is built to serve without the runtime extra."""
    from openfactory.actions.catalog import run_staged as _run

    return await _run(project=project, by=by, token=token)


def _catalog() -> dict[str, ActionSpec]:
    from openfactory.actions.catalog import CATALOG as rows

    return rows


class _Catalog:
    """A lazy mapping over `catalog.py`, so importing `openfactory.actions` costs nothing.

    The catalog's implementations reach Temporal, the forge and the approver store. Importing them
    eagerly would put `temporalio` on the import path of every front end — including the panel,
    which is explicitly built to serve without the `runtime` extra installed. The bodies already
    import lazily; this keeps the module itself lazy too, so the guard tests can walk the table on
    a machine that has none of it.

    THAT PROMISE IS HELD BY A GUARD SINCE #178, because for a while it was only written down: the
    page's own words came from `view.py` and `workflow.py`, so `/` and `/api/floor` answered 500
    on exactly the install this paragraph describes. It asks every GET route in an interpreter
    where `temporalio` cannot be found:
    `tests/test_the_panel_serves_without_the_engines_client.py`."""

    def __getitem__(self, name: str) -> ActionSpec:
        return _catalog()[name]

    def __contains__(self, name: object) -> bool:
        return name in _catalog()

    def __iter__(self):
        return iter(_catalog())

    def __len__(self) -> int:
        return len(_catalog())

    def values(self):
        return _catalog().values()

    def items(self):
        return _catalog().items()

    def get(self, name: str, default=None):
        return _catalog().get(name, default)


#: The one table. Iterating it is how a front end lists what it can offer, and how the guards
#: check that every row is reachable.
CATALOG = _Catalog()


def names() -> tuple[str, ...]:
    """Every action, in catalog order — which is grouped by what an operator is doing, not
    alphabetical, because this is what `openfactory act --list` prints."""
    return tuple(_catalog())


def spec(name: str) -> ActionSpec | None:
    return _catalog().get((name or "").strip().lower())


def waits_for_code(found: ActionSpec) -> bool:
    """Whether `perform` refuses this row for a project that started before its code (#992): it
    `needs_code` and it names a `project` to look at — a row that names none acts on no project's
    code and is never asked."""
    return found.needs_code and "project" in found.parameters


def _waiting_for_its_code(project: object, key: str) -> str:
    """The sentence a row that needs the code is refused with on a project that started before
    it — `""` for any other project, and for a name the registry cannot answer about: the row
    itself says "not registered" in its own words, and a registry that cannot be read is the row's
    to report, never this check's to swallow into a refusal about code."""
    from openfactory.contracts.project import before_its_code, no_code_yet
    from openfactory.registry import ProjectRegistry

    name = str(project or "").strip()
    if not name:
        return ""
    try:
        found = ProjectRegistry().get(name)
    except (KeyError, ValueError):
        return ""
    if not before_its_code(found):
        return ""
    return no_code_yet(name, key)


def reasons(name: str) -> tuple[str, ...]:
    """Every reason a refusal of `name` may carry in `data["reason"]` — what `perform` checks
    around the row, what the row's own code paths refuse with, and what the rows it hands back
    can say — in that order, each once. `()` for a name no row has.

    DERIVED HERE, NOT WRITTEN ON EACH ROW, for `perform`'s part: it is `perform`'s code that says
    them, so a copy of `not_admin` on every row would be one chance per row to forget the one
    that turns `needs_admin` off."""
    out: list[str] = []
    todo = [(name or "").strip().lower()]
    seen: set[str] = set()
    while todo:  # bounded: each row is visited once, and the catalogue is finite
        key = todo.pop(0)
        found = _catalog().get(key)
        if found is None or key in seen:
            continue
        seen.add(key)
        around = [r for r in AROUND_EVERY_ROW
                  if (r != BAD_REF or "issue" in found.parameters)
                  and (r != NOT_THE_INSTALLATIONS or found.installation)
                  and (r != NOT_ADMIN or found.needs_admin)
                  and (r != NO_CODE_YET or waits_for_code(found))]
        out += [r for r in (*around, *found.refuses) if r not in out]
        todo += list(found.relays)
    return tuple(out)


#: What a proposal may CARRY. It was `{project, issue}` — a ticket and nothing else — because the
#: channel back was `[[SUGGEST verb #NN]]`, with nowhere to put a sentence. That dropped `adjust`,
#: and the consequence was the shape of the whole role: the tech-lead could propose that you throw
#: work away (`discard`) or rerun it blind (`resume`), and could not propose the one thing a senior
#: engineer actually says, which is WHAT TO CHANGE (#170).
#:
#: A SECRET IS STILL NOT ADDRESSABLE, and that is the line this set now draws. `_SECRET` below
#: names what may never travel through a proposal; a parameter outside it is prose a human reads on
#: the button before pressing it.
_ADDRESSABLE = frozenset({"project", "issue", "instruction"})


def proposable(by: Actor) -> tuple[str, ...]:
    """The actions this actor may perform AND the tech-lead may propose, in catalog order (#121).

    THREE FILTERS, ALL DERIVED, because the alternative is the sentence this replaces: the
    tech-lead's guidance said *"never suggest prod/merge actions"* — a rule written when the
    catalogue had no merge row. #120 added one, gated, reachable from the chat, and the guidance
    went on forbidding it. A hand-written list of verbs in a prompt is a second copy of the
    catalogue that nobody updates.

    1. **The asker's own credential**, by the SAME two checks `perform` applies and in the same
       order — scope, then admin. A credential that cannot press the button must not be told to
       ask for it; being handed an action and then refused is worse than not being offered it.
       `perform`'s third, the installation's (#741), is not asked here because no row it guards
       can pass (2): a proposal is never to add a project or revoke a person, and
       `tests/test_the_installation_is_changed_through_its_rows.py` holds that.
    2. **What a human could have typed.** A suggestion is a proposal somebody approves with one
       word, so it must be something they could have said themselves: the operator grammar
       (`contracts/commands.py`, which is `resume`/`skip` and deliberately excludes prod) and the
       floor matcher (`actions/floor_intents.py`, which is merge/discard/adjust). Rows like
       `start`, `diagnose` and `product_release` are addressable by a ticket and are NOT things
       the floor's own grammar accepts — which is exactly the line the old rule was reaching for.
    3. **What a proposal can carry** — see `_ADDRESSABLE`. This used to drop `adjust`, because
       the channel was one verb and one ticket wide. It carries an instruction now (#170), and the
       blast radius is closed by (2): `typeable` is `{adjust, discard, merge, resume, skip, stop}`,
       so relaxing this admits EXACTLY `adjust`. `approve_prod` and `promote` stay out where they
       already were — not in the floor grammar — rather than by this filter's accident.

    `ack` is deliberately absent from (2). It is a person saying they have seen something, and
    nobody can propose that on somebody else's behalf.
    """
    from openfactory.actions.floor_intents import FLOOR_ROWS
    from openfactory.contracts.commands import ACTION_OF

    typeable = set(ACTION_OF.values()) | set(FLOOR_ROWS.values())
    out: list[str] = []
    for name, found in _catalog().items():
        if name not in typeable:
            continue
        if not by.may_enter(found.scope):
            continue
        if found.needs_admin and not by.admin:
            continue
        if set(found.required) - _ADDRESSABLE or "issue" not in found.required:
            continue
        out.append(name)
    return tuple(out)


async def perform(name: str, *, by: Actor, **params: object) -> Outcome:
    """Run one action. Never raises. Always returns an `Outcome`.

    THE SIX THINGS THAT HAPPEN HERE RATHER THAN IN THREE FRONT ENDS:

    1. **The name is resolved**, and an unknown one is refused with the list of what exists —
       the registry rule this codebase already holds everywhere else (`adapters/*/registry.py`).
    2. **Parameters are checked** against the spec, in both directions. A missing one is named; so
       is an unexpected one, because a front end that renames a field and keeps working silently
       is how `image=` came to be omitted at all four job-launch sites (see
       `a-negative-guard-needs-a-positive-twin`).
    3. **A ticket ref is normalised once.** `#189` and `189` are the same ticket, and until now the
       panel knew that and Slack did not.
    4. **`needs_admin` is enforced.** Slack had this gate, the panel had a token, the CLI had
       nothing; now the three answers meet in `Actor.admin` and the decision is made in one place.
       So is a row's `installation`: only an unscoped credential changes the deployment itself.
    5. **A row that needs the code waits for it** (`ActionSpec.needs_code`, #992): on a project
       whose product started before its code it is refused by name, naming the first source.
    6. **Everything is logged with the actor**, whatever the result. This is the audit line — the
       first time this platform can say who asked for a thing, which is the question an enterprise
       security review opens with.

    NEVER RAISING IS NOT POLITENESS. Both front ends already have a hard must-always-reply rule,
    and both implemented it by wrapping every call in `except Exception`. Doing it here means an
    action author cannot forget, and means the exception's real message survives — `first_message`
    walks the chain, because an error crossing a Temporal activity boundary otherwise arrives as
    the fixed string "Activity task failed" (#66).
    """
    key = (name or "").strip().lower()
    found = _catalog().get(key)
    if found is None:
        return refused(
            NOT_FOUND,
            f"there is no action called {name!r} — this deployment does: " + ", ".join(names()),
            reason=UNKNOWN_ACTION,
        )

    problem = _check_params(found, params)
    if problem:
        return refused(INVALID, problem, reason=BAD_PARAMETERS)

    if "issue" in params:
        ref, bad = _clean_ref(str(params["issue"]))
        if bad:
            return refused(INVALID, bad, reason=BAD_REF)
        params["issue"] = ref

    # SCOPE BEFORE ADMIN, because they answer different questions and the order is the point: a
    # business analyst holding a product credential IS an admin of the product area — accepting a
    # requirement is the most consequential act there — and must still be refused `merge` outright.
    # Asking `admin` first would let that credential through on every row it happens to satisfy.
    if not by.may_enter(found.scope):
        log.warning("DENIED_SCOPE %s (%s) by %s (%s)", key, found.scope, by, _loggable(params))
        # AN INSTALLATION ROW NAMES THE ADMINISTRATOR, NOT THE AREA (#741): a row that changes the
        # installation is refused to a credential of ANY area, so sending a product credential to
        # "somebody whose credential covers the floor" is the wrong remedy — a floor credential is
        # refused it too. The reason stays `out_of_scope` (the area check is what refused), but the
        # sentence points where the fix is.
        remedy = ("ask somebody who administers this deployment" if found.installation
                  else f"ask somebody whose credential covers the {found.scope}")
        return refused(
            DENIED,
            f"this credential is scoped to {', '.join(sorted(by.scopes or ())) or 'nothing'} and "
            f"{key} belongs to the {found.scope}. Nothing was done — {remedy}.",
            reason=OUT_OF_SCOPE,
        )

    # THE INSTALLATION IS THE ADMINISTRATOR'S (#741), asked after the area and before `admin`. A
    # credential scoped to ANY area — a board token, a product token, an invitation to one of them
    # — is somebody's operator or requirement-writer, and it is `admin` on its own surface; what it
    # may never do is change what the deployment is: its projects, the people it names, whether it
    # picks work up. Only an unscoped credential reaches these rows, which is the panel's own token
    # and its per-person rows, an invitation to neither area, and a shell on the host.
    if found.installation and by.scopes is not None:
        log.warning("DENIED_INSTALLATION %s by %s (%s)", key, by, _loggable(params))
        return refused(
            DENIED,
            f"{key} changes this installation, which is the administrator's; this credential is "
            f"scoped to {', '.join(sorted(by.scopes)) or 'nothing'}. Nothing was done — ask "
            f"somebody who administers this deployment.",
            reason=NOT_THE_INSTALLATIONS,
        )

    if found.needs_admin and not by.admin:
        log.warning("DENIED %s by %s (%s)", key, by, _loggable(params))
        return refused(
            DENIED,
            f"{by} is not allowed to {key} — ask somebody listed as an admin for this project.",
            reason=NOT_ADMIN,
        )

    # WHO FIRST, THEN WHAT THE PROJECT IS (#992): a row that needs the code is refused, by name and
    # before it runs, on a project whose product started before its code — a refusal somebody can
    # act on, where running it would fail in a clone, a board or a box with a sentence about that
    if waits_for_code(found):
        waiting = _waiting_for_its_code(params.get("project"), key)
        if waiting:
            log.info("NO_CODE_YET %s by %s (%s)", key, by, _loggable(params))
            return refused(CONFLICT, waiting, reason=NO_CODE_YET)

    from openfactory.runtime.temporal.vocabulary import EngineUnreachable

    try:
        outcome = await found.run(by=by, **params)
    except EngineUnreachable as exc:
        # NOT A FAILURE OF THE ACTION, a state of the deployment (#674): the engine did not answer
        # in time. FAILED is a 500 and a traceback; this is the panel's 503 and one line.
        log.warning("action %s by %s: the engine did not answer (%s)", key, by, exc)
        return refused(UNAVAILABLE, f"could not {key}: {exc}", reason=ENGINE_UNREACHABLE)
    except Exception as exc:  # noqa: BLE001 — an action must never take its caller down
        # THE REFERENCE IS IN THE LINE AND IN THE ANSWER (#908), so the person who reads "could
        # not …" can hand an operator the one traceback that is theirs; before, the answer named
        # nothing the log could be searched for.
        reference = failure_reference()
        log.exception("action %s raised for %s reference=%s", key, by, reference)
        return refused(FAILED, f"could not {key}: {_why(exc)}", reason=RAISED,
                       reference=reference)
    if not isinstance(outcome, Outcome):  # an action that returns None is a silent success (F5)
        log.error("action %s returned %r, not an Outcome", key, type(outcome).__name__)
        return refused(
            FAILED,
            f"'{key}' did not report what it did — treat this as a failure and check the logs "
            f"before assuming it happened.",
            reason=REPORTED_NOTHING,
        )
    if not outcome.ok and outcome.data.get("reason") not in reasons(key):
        # THE ANSWER STANDS — it is the row's, and rewriting it here would hide the very word the
        # caller needs to report. The guards in `tests/test_the_action_layer.py` read every
        # row's refusals off its source; this is for the one they could not see.
        log.error("action %s refused with an undeclared reason %r — it declares %s", key,
                  outcome.data.get("reason"), ", ".join(reasons(key)))
    # A LABEL IS PRINTED AS ONE (`Actor.label`): what an anonymous caller says it is, beside the
    # credential it used — never in `by=`, which is who that credential is.
    label = str(getattr(by, "label", "") or "")
    log.info("action=%s by=%s%s ok=%s code=%s params=%s", key, by,
             f" label={label!r}" if label else "", outcome.ok, outcome.code or "-",
             _loggable(params))
    return outcome


#: Parameters whose VALUE must never reach a log line. `approve_prod` and `promote` take the
#: approver's password, and this module writes an audit line on every call including the refusals —
#: which is precisely the path a wrong password takes.
_SECRET = frozenset({"password", "token", "secret", "key"})


def _why(exc: Exception) -> str:
    """What the refusal says an action died of — the install, when the install is what is missing.

    THE ROWS THAT ARE THE ENGINE'S IMPORT ITS MODULES INSIDE THEIR BODIES, by design: that is what
    keeps `temporalio` off every front end's import path (see `_Catalog`). So on an install made
    without the `runtime` extra, `start`, `stop`, `approve` and the rest raise here, and the person
    read `could not start: No module named 'temporalio'` — a cause with no remedy. The catch-all
    above is the one guard all of them share, so it is the one place that names the install:
    `host.CLIENT_MISSING`, the sentence every other surface gives for that condition (#178)."""
    from openfactory.runtime.host import CLIENT_MISSING, the_client_is_what_is_missing
    from openfactory.util.causes import first_message

    # The chain, not only its head: a row that wraps its own failures still died of the import.
    link: BaseException | None = exc
    for _ in range(8):  # bounded: a chain is short, and a hand-built cyclic one must not spin
        if link is None:
            break
        if the_client_is_what_is_missing(link):
            return CLIENT_MISSING
        link = link.__cause__ or link.__context__
    return first_message(exc)


def _loggable(params: dict[str, object]) -> dict[str, object]:
    return {k: ("***" if k in _SECRET else v) for k, v in params.items()}


def _check_params(found: ActionSpec, params: dict[str, object]) -> str:
    missing = [p for p in found.required if p not in params or params[p] in (None, "")]
    if missing:
        return (f"'{found.name}' needs {', '.join(missing)} — it takes "
                + ", ".join(found.parameters) + ".")
    unexpected = [p for p in params if p not in found.parameters]
    if unexpected:
        return (f"'{found.name}' does not take {', '.join(sorted(unexpected))} — it takes "
                + (", ".join(found.parameters) or "no parameters") + ".")
    return ""


#: What a tracker actually calls a ticket: `189` (GitHub, optionally `#`-prefixed), `CONT-412`
#: (Jira), `1234` (Azure DevOps). Letters, digits, one kind of separator, nothing else.
#:
#: Lifted verbatim from `api/app.py::_valid_issue`, which is the point: the panel held this and
#: Slack held nothing, so a ref typed in a channel went straight into a Temporal workflow id. The
#: bound matters for the same reason it did there — a ref becomes part of a workflow id and, via
#: `paths.journal_stem`, part of a filename.
_ISSUE_RE = re.compile(r"^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*$")
#: …and the same ref carrying the repository it lives in (C-18): `owner/name#189`. One product can
#: own several repositories, so on a multi-repo board a bare number names no single ticket. Kept as
#: a SECOND, fully-anchored pattern rather than by loosening the first: `/` and `#` reach a
#: workflow id and a filename, and the way to allow exactly two segments and one hash is to spell
#: that out, not to add characters to a class and hope.
_QUALIFIED_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*#[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*$")
_ISSUE_MAX = 64
#: The qualified form needs room for `owner/name#` on top of the ref itself. A SEPARATE bound, so
#: widening it here cannot quietly widen what a bare ref may be — the bound is what keeps a ref
#: from becoming an unreasonable workflow id or filename, and each shape deserves its own.
_QUALIFIED_MAX = 160


def _clean_ref(issue: str) -> tuple[str, str]:
    """`(ref, problem)` — the provider's own ref without the decoration a human types.

    `#189` and `189` must not be two tickets. The panel already knew that in `_valid_issue`; Slack
    passed whatever was typed straight into a Temporal workflow id, so `skip #250` and `skip 250`
    addressed different workflows and only one of them existed.

    REJECTING IS STILL WORTH DOING even though `paths.py` neutralises a hostile ref on its own
    (C-06a). This is where there is somebody to tell: a sentence naming the problem beats a job
    launched against a ref no provider will ever recognise, which surfaces minutes later as an
    unexplained 404."""
    ref = (issue or "").strip().lstrip("#").strip()
    bare = bool(ref) and len(ref) <= _ISSUE_MAX and bool(_ISSUE_RE.match(ref))
    qualified = bool(ref) and len(ref) <= _QUALIFIED_MAX and bool(_QUALIFIED_RE.match(ref))
    if not (bare or qualified):
        return "", ("that is not a ticket reference — letters, digits, '-' or '_', optionally "
                    "with the repository it lives in "
                    f"(e.g. 189, #189, CONT-412, owner/name#189), got {issue!r}")
    return ref, ""
