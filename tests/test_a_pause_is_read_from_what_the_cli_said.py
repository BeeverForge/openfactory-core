"""A run that died with no result event is a pause only when the CLI said so (#750).

MEASURED ON 0e66a6b6. `ClaudeCodeAdapter._parse_stream`, with `rc != 0` and no `result` event, ran
`_detect_pause` over the WHOLE captured output. That output is mostly the repository: a `user`
event holds what a tool returned, an assistant message the model's prose and its `tool_use`
inputs, `system/init` the repository's own skills, commands and working directory. A repository
whose domain is throttling parked its own killed runs as rate limited, with a resume timer, on an
account nobody had limited; so did any killed run whose stream held a `rate_limit_event`, matched
on the event's name whatever its status.

THE RULE, FOR EVERY HARNESS IN THE REGISTRY: limit-shaped text inside any event the harness's
parser knows (read from its own module and from its stream reader) never makes a pause; what the
CLI itself said still does, each signal read from the code (`claude_code._CLI_SIGNALS`, and the
event a harness's own `_pause_from` reads by its type).
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json

import pytest

from openfactory.adapters.agent import claude_code, stream
from openfactory.adapters.agent.registry import HARNESSES
from tests import claude_cli_output as cli

#: Every way a pattern of every harness says "limit" or "auth": rate, usage, session, quota, the
#: numbers, a reset time. What a repository about rate limiting has in its source and its logs.
LIMIT = ("429 Too Many Requests: rate limit exceeded, usage limit reached, You've hit your "
         "session limit, quota exhausted — resets 10:30pm; 401 Unauthorized: invalid api key, "
         "authentication failed, not logged in, 403 forbidden")


def _module(kind: str):
    return importlib.import_module(f"openfactory.adapters.agent.{kind}")


def _kinds_known(kind: str) -> set[str]:
    """The event kinds a harness's parser tells apart, READ FROM ITS CODE: every string its module
    and its stream reader compare a `type` or `role` (or a local `kind`) against."""
    found: set[str] = set()
    for src in (inspect.getsource(_module(kind)), inspect.getsource(stream._READERS[kind])):
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Compare):
                continue
            left = node.left
            named = (isinstance(left, ast.Name) and left.id == "kind") or (
                isinstance(left, ast.Call) and getattr(left.func, "attr", "") == "get"
                and left.args and isinstance(left.args[0], ast.Constant)
                and left.args[0].value in ("type", "role"))
            if not named:
                continue
            for comp in node.comparators:
                values = comp.elts if isinstance(comp, ast.Tuple | ast.List | ast.Set) else [comp]
                found |= {v.value for v in values
                          if isinstance(v, ast.Constant) and isinstance(v.value, str)}
    return found


def _carrier(kind: str) -> dict:
    """An event of `kind` with the limit text in every place a harness keeps repository text:
    message content, tool input and output, an item's command and output, a part's text and
    state, the init's working directory and command lists."""
    blocks = [{"type": "text", "text": LIMIT},
              {"type": "tool_use", "name": "Bash", "input": {"command": LIMIT}},
              {"type": "tool_result", "tool_use_id": "toolu_01", "content": LIMIT}]
    return {"type": kind, "role": kind, "subtype": "init", "cwd": f"/work/{LIMIT}",
            "slash_commands": [LIMIT], "skills": [LIMIT], "content": LIMIT, "text": LIMIT,
            "message": {"role": kind, "content": blocks},
            "item": {"type": "command_execution", "command": LIMIT, "aggregated_output": LIMIT,
                     "text": LIMIT},
            "part": {"type": "tool", "text": LIMIT, "state": {"output": LIMIT}},
            "tool_use_result": {"stdout": LIMIT, "stderr": LIMIT}}


#: The one event kind a harness's own `_pause_from` reads BY ITS TYPE as the CLI's report, and so
#: is a signal rather than repository text: opencode's `error` event, its provider's answer.
#: Read from the code below (`test_the_signal_kinds_are_the_ones_the_detectors_read`).
SIGNAL_KINDS = {"opencode": {"error"}}


def _pause(kind: str, out: str) -> tuple[str | None, str | None]:
    """The harness's pause detector over `out`, called as its signature asks."""
    module = _module(kind)
    detector = getattr(module, "_pause_from", None)
    assert detector is not None, f"{kind} has no `_pause_from` — its pause cannot be read"
    if "events" in inspect.signature(detector).parameters:
        return detector(module._parse_jsonl(out), out)
    return detector(out)


def _stream(*events: dict) -> str:
    return "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in events)


#: An event cut in half when the CLI died mid-write: it starts with `{` and does not parse.
CUT = _stream(cli.tool_result_event(LIMIT))[:60] + LIMIT + "\n"


# ── the family: no event the parser knows makes a pause ─────────────────────────────────────────

@pytest.mark.parametrize("kind", sorted(HARNESSES))
def test_limit_text_in_any_event_the_parser_knows_is_no_pause(kind: str):
    kinds = _kinds_known(kind) - SIGNAL_KINDS.get(kind, set())
    assert kinds, f"no event kind read from {kind}'s code — this guard is measuring nothing"
    for each in sorted(kinds):
        assert _pause(kind, _stream(_carrier(each))) == (None, None), (kind, each)
    assert _pause(kind, CUT) == (None, None), f"{kind}: a cut-off event was read as the CLI's"
    assert _pause(kind, _stream(*map(_carrier, sorted(kinds))) + CUT) == (None, None), kind


def test_no_measured_claude_event_carrying_repository_text_is_a_pause():
    """The pinned CLI's own shapes (`tests/claude_cli_output.py`), each carrying the limit text
    where a run puts repository text — and a `rate_limit_event` that says the account still
    works, whose NAME the old match read."""
    init = {**cli.init_event(), "cwd": "/work/rate-limiter",
            "slash_commands": ["throttle-429", "quota-report"], "skills": ["rate-limit"]}
    tool_use = cli.assistant_event("checking")
    tool_use["message"]["content"] = [{"type": "tool_use", "id": "toolu_01", "name": "Bash",
                                       "input": {"command": f"grep -rn '{LIMIT}' src"}}]
    carriers = {
        "system/init": init,
        "assistant (the model's prose)": cli.assistant_event(LIMIT),
        "assistant (a tool_use)": tool_use,
        "user (a tool_result)": cli.tool_result_event(LIMIT),
        "rate_limit_event allowed": cli.rate_limit_event(status="allowed"),
        "rate_limit_event allowed_warning": cli.rate_limit_event(status="allowed_warning"),
    }
    for name, event in carriers.items():
        res = claude_code._parse_stream(1, _stream(init, event))
        assert res.pause_reason is None and res.retry_at is None, (name, res.pause_reason)
        assert not res.ok, name
    res = claude_code._parse_stream(137, _stream(*carriers.values()) + CUT)
    assert res.pause_reason is None, "a killed run's own transcript parked it as a pause"


# ── the real signals still do, each one ─────────────────────────────────────────────────────────

def _synthetic(text: str, error: str) -> dict:
    """The measured message the CLI writes in the model's place (2.1.219), saying `text`."""
    [measured] = [e for e in cli.measured("stream-json-verbose.stdout.jsonl")
                  if e.get("type") == "assistant"]
    assert measured.get("is_api_error_message") is True, "the measured shape moved"
    message = {**measured["message"], "content": [{"type": "text", "text": text}]}
    return {**measured, "message": message, "error": error}


#: One case per signal in `claude_code._CLI_SIGNALS`: (output of a run killed before its result
#: event, the pause it is). Each output also carries repository text, so the pause is the signal's.
CLAUDE_SIGNALS = {
    "_stderr": [
        (_stream(cli.tool_result_event("ok")) + "Claude AI usage limit reached · resets 10:30pm\n",
         ("rate_limit", "10:30pm")),
        (_stream(cli.tool_result_event("ok")) + "Error: Invalid API key · Please run /login\n",
         ("auth", None)),
    ],
    "_api_error_message": [
        (_stream(cli.tool_result_event("ok"),
                 _synthetic("You've hit your session limit · resets 10:30pm (UTC)", "rate_limit")),
         ("rate_limit", "10:30pm")),
        (_stream(*cli.measured("stream-json-verbose.stdout.jsonl")[:2]), ("auth", None)),
    ],
    "_rejected_rate_limit": [
        (_stream(cli.tool_result_event("ok"),
                 cli.rate_limit_event(status="rejected", resets_at=1_792_454_400)),
         ("rate_limit", "2026-10-20T00:00:00Z")),
    ],
}


def test_every_signal_the_claude_parser_reads_has_its_case():
    names = [s.__name__ for s in claude_code._CLI_SIGNALS]
    assert sorted(names) == sorted(CLAUDE_SIGNALS), (
        f"a signal `_CLI_SIGNALS` reads has no case here, or a case names no signal: {names}")


@pytest.mark.parametrize("signal", sorted(CLAUDE_SIGNALS))
def test_each_claude_signal_still_makes_its_pause(signal: str):
    for out, pause in CLAUDE_SIGNALS[signal]:
        res = claude_code._parse_stream(1, out)
        assert (res.pause_reason, res.retry_at) == pause, (signal, out[-120:])
        assert claude_code._parse_stream(0, out).pause_reason is None, (
            "a clean exit with no result event became a pause — the rc rule moved")


def test_a_rate_limit_wins_over_an_auth_stop_in_the_same_stream():
    out = (_stream(_synthetic("Not logged in · Please run /login", "authentication_failed"),
                   cli.rate_limit_event(status="rejected", resets_at=1_792_454_400)))
    assert claude_code._pause_from(out) == ("rate_limit", "2026-10-20T00:00:00Z")


@pytest.mark.parametrize("kind", sorted(HARNESSES))
def test_what_the_cli_printed_outside_the_stream_is_still_a_pause(kind: str):
    out = _stream(_carrier("user")) + "Error: 429 Too Many Requests — rate limit exceeded\n"
    assert _pause(kind, out)[0] == "rate_limit", kind
    out = _stream(_carrier("user")) + "Error: 401 Unauthorized — invalid api key\n"
    assert _pause(kind, out)[0] == "auth", kind


def test_the_signal_kinds_are_the_ones_the_detectors_read():
    """`SIGNAL_KINDS` is not a list of exemptions written by hand: each is a kind its harness's
    own `_pause_from` compares an event's type against, and a real report of it is a pause."""
    for kind, kinds in SIGNAL_KINDS.items():
        src = inspect.getsource(_module(kind)._pause_from)
        assert all(f'"{k}"' in src for k in kinds), (kind, kinds)
    error = {"type": "error", "error": {"name": "APIError",
                                        "data": {"statusCode": 429, "message": "slow down"}}}
    assert _pause("opencode", _stream(error))[0] == "rate_limit"
