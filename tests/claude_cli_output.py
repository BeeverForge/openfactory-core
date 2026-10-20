"""What `claude` prints on stdout, for tests that read a review: built from the pinned CLI's own output.

`tests/fixtures/claude_cli/2.1.219/` holds what 2.1.219 printed for the reviewer's command, with
`--output-format json` (one envelope) and with `--output-format stream-json --verbose` (init, an
assistant message, the result event), measured with no credential — see its README. A test changes
only the values a review is read from (`result`, `is_error`, `total_cost_usd`, `num_turns`,
`usage`), so every other key and the order the CLI wrote them in stay the CLI's own.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "claude_cli" / "2.1.219"


def measured(name: str) -> list[dict]:
    """The objects of one measured stdout, one per line, in the order the CLI printed them."""
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def verdict(decision: str, score: int, summary: str) -> str:
    """A review as the reviewer's schema asks for it: the text the result event's `result` carries."""
    return json.dumps({"decision": decision, "score": score, "summary": summary,
                       "acceptance": [], "findings": []})


def _with(event: dict, *, result: str, cost: float, turns: int, tokens: tuple[int, int]) -> dict:
    return {**event, "is_error": False, "result": result, "total_cost_usd": cost,
            "num_turns": turns,
            "usage": {**event["usage"], "input_tokens": tokens[0], "output_tokens": tokens[1]}}


def envelope(result: str, *, cost: float = 0.0, turns: int = 1,
             tokens: tuple[int, int] = (0, 0)) -> dict:
    """2.1.219's `--output-format json` envelope, carrying this review and what it cost."""
    [only] = measured("json.stdout.jsonl")
    return _with(only, result=result, cost=cost, turns=turns, tokens=tokens)


def init_event() -> dict:
    """The first line of 2.1.219's stream: `system/init`, which carries no `result`."""
    return measured("stream-json-verbose.stdout.jsonl")[0]


def assistant_event(text: str, *, tokens: tuple[int, int] = (0, 0)) -> dict:
    """An assistant message of 2.1.219's stream, saying `text`, with its own `message.usage`."""
    event = measured("stream-json-verbose.stdout.jsonl")[1]
    message = event["message"]
    return {**{k: v for k, v in event.items() if k not in ("error", "is_api_error_message")},
            "message": {**message, "content": [{"type": "text", "text": text}],
                        "usage": {**message["usage"], "input_tokens": tokens[0],
                                  "output_tokens": tokens[1]}}}


def result_event(result: str, *, cost: float = 0.0, turns: int = 1,
                 tokens: tuple[int, int] = (0, 0)) -> dict:
    """The last line of 2.1.219's stream (`type: "result"`), carrying this review and its cost."""
    last = measured("stream-json-verbose.stdout.jsonl")[-1]
    return _with(last, result=result, cost=cost, turns=turns, tokens=tokens)


def rate_limit_event(*, status: str = "allowed_warning", rate_limit_type: str = "five_hour",
                     utilization: float = 0.91, resets_at: int = 1_792_454_400) -> dict:
    """A `rate_limit_event` in the shape 2.1.219 declares for it (`type`, `rate_limit_info`, `uuid`,
    `session_id`; `status` one of allowed / allowed_warning / rejected, `rateLimitType` one of
    five_hour / seven_day / …, `resetsAt` an integer). Not observed on a credentialed call: no
    credential was available, so this is the binary's own schema, not an invented shape."""
    return {"type": "rate_limit_event",
            "rate_limit_info": {"status": status, "resetsAt": resets_at,
                                "rateLimitType": rate_limit_type, "utilization": utilization},
            "uuid": "5f0c1a52-6a3e-4d1b-9a43-2c7f1b0e8d11",
            "session_id": init_event()["session_id"]}


def tool_result_event(content: str) -> dict:
    """A `user` event carrying what a tool the reviewer called returned — a file it read, a command's
    output. The stream holds these; the json envelope never did. Not in the measured files (a run
    with no credential calls no tool): the content block is the shape Claude Code writes to its own
    session transcript (`tool_use_id`, `type`, `content`, `is_error`), the event around it the
    stream's (`type`, `message`, `parent_tool_use_id`, `session_id`, `uuid`)."""
    return {"type": "user",
            "message": {"role": "user", "content": [
                {"tool_use_id": "toolu_01", "type": "tool_result", "content": content,
                 "is_error": False}]},
            "parent_tool_use_id": None, "session_id": init_event()["session_id"],
            "uuid": "0b6d2f3e-1c4a-4f9e-8e21-7a5c3d9b4e60"}


def stdout(*events: dict) -> str:
    """The objects as the CLI writes them: one compact JSON object per line, UTF-8 as is."""
    return "".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in events)
