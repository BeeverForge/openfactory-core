"""The worker's breakdown, run in the test's own process, for a test that drives a conversation door.

Since #563 slice 18b a conversation door does not break a requirement down: it starts
`ProductBreakdownWorkflow` (`breaking.start_now`) and replies that it began, and the workflow's
activity runs `break_down` and tells the conversation what was filed (`confirm.breakdown_told`).
A test of the conversation has no engine, so `run_here` stands in for it: `breaking.start_now`
becomes the activity's two steps on the test's module double, recorded — `started` is what each
door asked for, and `told` is what the conversation would be told when the breakdown ends.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from openfactory.product import breaking


def run_here(monkeypatch, module, *, answer: str = breaking.STARTED) -> SimpleNamespace:
    """`breaking.start_now` replaced by the activity's work on `module`. `answer` other than
    `STARTED` is the engine's answer instead (`RUNNING`), and nothing runs."""
    from openfactory.product.confirm import breakdown_told

    ran = SimpleNamespace(started=[], told=[])

    def _start(project, number, *, actor, asked_for, conversation="", room="", requester="",
               language=""):
        ran.started.append({"number": number, "actor": actor, "asked_for": asked_for,
                            "conversation": conversation, "room": room, "requester": requester,
                            "language": language})
        if answer != breaking.STARTED:
            return answer
        try:
            results = module.break_down(number, actor=actor, asked_for=asked_for,
                                        **_where(module.break_down, conversation, requester))
        except Exception:  # noqa: BLE001 — the activity tells the failure and the workflow fails
            results = None
        ran.told.append(breakdown_told(project, number, results, asked_for=asked_for,
                                       module=module, language=language or None))
        return breaking.STARTED

    monkeypatch.setattr(breaking, "start_now", _start)
    return ran


def _where(write, conversation: str, requester: str) -> dict:
    """Where it was asked, for a double whose `break_down` takes it — as the worker's module does."""
    params = inspect.signature(write).parameters
    takes = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()) or (
        "conversation" in params and "requester" in params)
    return {"conversation": conversation, "requester": requester} if takes else {}
