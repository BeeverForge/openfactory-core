"""A requirement's breakdown, started from the conversation (#563 slice 18b, ADR-0051 D18).

The conversation's two doors — "quebra o requisito 7" and the acceptance's second act — ran
`module.break_down` in their own process, while the panel, the command line and the API started
`ProductBreakdownWorkflow` under one id per requirement. Nothing shared told the two kinds of door
apart, so one requirement could be broken down twice at once and file its cards twice (#563).

Every door now starts the same workflow, under the same id (`io.breakdown_workflow_id`), and the
engine runs one execution of it at a time. A conversation does not wait on it: a breakdown drafts
for minutes, longer than a turn's ceiling (D6), so the door starts it and says so, and the
workflow tells that conversation what was filed when it ends (`activities._tell_the_breakdown`).

No temporalio import at the top: on an install without the runtime extra the door answers why the
engine cannot be reached, through its caller's own sentence (#178).
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

#: The breakdown was started by this door.
STARTED = "started"
#: One of the same requirement was already running, and this door started nothing (D18 item 2).
RUNNING = "running"


async def start(project, number: int, *, actor: str, asked_for: bool, conversation: str = "",
                room: str = "", requester: str = "", language: str = "", client=None) -> str:
    """Start the requirement's breakdown on the worker: `STARTED`, or `RUNNING` when the engine
    refused a second start of it. RAISES when the engine cannot be reached — the caller says that
    nothing was filed, in its own words.

    `asked_for` says whether a person asked for it or it is an acceptance's second act (#182);
    `conversation`, `room` and `requester` are where it was asked, and that conversation is told
    what was filed when it ends, in `language`."""
    from openfactory.product.door import _engine

    try:
        from temporalio.exceptions import WorkflowAlreadyStartedError

        from openfactory.runtime.temporal import TASK_QUEUE
        from openfactory.runtime.temporal.io import ProductBreakdownInput, breakdown_workflow_id
    except ImportError as exc:
        # AN INSTALL WITHOUT THE RUNTIME EXTRA (#178): said through the caller's own sentence
        from openfactory.runtime.host import why_the_engine_cannot_be_read

        raise RuntimeError(why_the_engine_cannot_be_read(exc)) from exc

    name = getattr(project, "name", "") or str(project)
    client = client or await _engine()
    try:
        await client.start_workflow(
            "ProductBreakdownWorkflow",
            ProductBreakdownInput(project=name, number=number, actor=actor, asked_for=asked_for,
                                  conversation=conversation, room=room, requester=requester,
                                  language=language or ""),
            id=breakdown_workflow_id(name, number), task_queue=TASK_QUEUE)
    except WorkflowAlreadyStartedError:
        log.info("OPENFACTORY_PRODUCT_BREAKDOWN_RUNNING project=%s req=%s — the conversation "
                 "asked while one runs; nothing was started", name, number)
        return RUNNING
    return STARTED


def start_now(project, number: int, **kwargs) -> str:
    """`start`, for the conversation's code, which is not async."""
    from openfactory.product.door import _run

    return _run(start(project, number, **kwargs))


async def running(project, number: int, *, client=None) -> bool:
    """Whether the requirement's breakdown is running on the engine now (#563 slice 18c) — the
    shared id's execution, asked of the engine itself. RAISES when the engine cannot be asked; a
    breakdown that ended, or never ran, is not running."""
    from openfactory.product.door import _engine

    try:
        from temporalio.client import WorkflowExecutionStatus
        from temporalio.service import RPCError, RPCStatusCode

        from openfactory.runtime.temporal.io import breakdown_workflow_id
    except ImportError as exc:
        from openfactory.runtime.host import why_the_engine_cannot_be_read

        raise RuntimeError(why_the_engine_cannot_be_read(exc)) from exc

    name = getattr(project, "name", "") or str(project)
    client = client or await _engine()
    try:
        described = await client.get_workflow_handle(breakdown_workflow_id(name, number)).describe()
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            return False
        raise
    return described.status == WorkflowExecutionStatus.RUNNING


def running_now(project, number: int) -> bool:
    """`running`, for the module's code, which is not async."""
    from openfactory.product.door import _run

    return bool(_run(running(project, number)))


#: The breakdowns running now, as the engine's visibility lists them: ONE query for the product,
#: never one per requirement.
_RUNNING = 'WorkflowType = "ProductBreakdownWorkflow" AND ExecutionStatus = "Running"'


async def running_numbers(project, *, client=None) -> set[int]:
    """The requirements of `project` whose breakdown is running now (#563 slice 18e) — what the
    role reads about each requirement. RAISES when the engine cannot be asked: the caller says
    "unknown", never "not running". The visibility store lags a start by a moment, so a breakdown
    started a second ago may not be listed yet."""
    from openfactory.product.door import _engine

    try:
        from openfactory.runtime.temporal.io import breakdown_workflow_id
    except ImportError as exc:
        from openfactory.runtime.host import why_the_engine_cannot_be_read

        raise RuntimeError(why_the_engine_cannot_be_read(exc)) from exc

    name = getattr(project, "name", "") or str(project)
    prefix = breakdown_workflow_id(name, 0)[:-1]
    client = client or await _engine()
    out: set[int] = set()
    async for wf in client.list_workflows(_RUNNING):
        tail = str(wf.id)[len(prefix):] if str(wf.id).startswith(prefix) else ""
        if tail.isdigit():
            out.add(int(tail))
    return out


def running_numbers_now(project) -> set[int]:
    """`running_numbers`, for the module's code, which is not async."""
    from openfactory.product.door import _run

    return set(_run(running_numbers(project)))


def written_from(project, number: int) -> str:
    """The conversation requirement `number` was asked in, as its delivery loop keeps it (the
    promise the first yes opened, `module._owed`) — "" when no loop names one. What a breakdown the
    panel, the command line or the API started is told to (#563 slice 18e, ADR-0051 D18 item 3).
    The latest loop that names a conversation wins. RAISES when the ledger cannot be read."""
    from openfactory.memory import store as loop_store
    from openfactory.memory.ledger import DELIVERY, fold
    from openfactory.product.events import OWNER

    name = getattr(project, "name", "") or str(project)
    subject = str(int(number))
    loops = [x for x in fold(loop_store.read(name))
             if x.kind == DELIVERY and x.owner == OWNER and x.subject == subject]
    for loop in sorted(loops, key=lambda x: x.ts, reverse=True):
        where = str((loop.context or {}).get("conversation") or "").strip()
        if where:
            return where
    return ""
