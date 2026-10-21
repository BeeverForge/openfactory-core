"""#750, proven by breaking it: a run that died with no result event is a pause only when the CLI
said so, never because the repository it read mentions rate limits.

TWO CLAIMS:

  1. **No event the parser knows makes a pause.** A `user` event's tool output, the model's prose
     and its `tool_use` inputs, `system/init`'s names, a `rate_limit_event` that says the account
     still works, an event cut in half: none is the CLI saying it was limited.
  2. **Each of the CLI's own signals still does**: what it printed outside the stream, the message
     it writes in the model's place, and a `rate_limit_event` whose status is `rejected`.

The guard under test is `tests/test_a_pause_is_read_from_what_the_cli_said.py`.
"""

TEST = "tests/test_a_pause_is_read_from_what_the_cli_said.py"

CLAUDE = "openfactory/adapters/agent/claude_code.py"

MUTATIONS = [
    # ── 1. no event the parser knows makes a pause ─────────────────────────────────────────────
    ("750: THE DEFECT, PUT BACK — a run with no result event is classified over its whole "
     "captured output, tool events included", CLAUDE,
     "        reason, retry = _pause_from(out) if rc != 0 else (None, None)\n",
     "        reason, retry = _detect_pause(out) if rc != 0 else (None, None)\n"),

    ("750: the CLI's stderr is read as the raw stream, so every event is classified", CLAUDE,
     "    return _detect_pause(prose_only(out))\n",
     "    return _detect_pause(out)\n"),

    ("750: any assistant message is read as the CLI's, so the model's prose about rate limits "
     "parks the run", CLAUDE,
     '        if evt.get("type") != "assistant" or evt.get("is_api_error_message") is not True:\n',
     '        if evt.get("type") != "assistant":\n'),

    ("750: a rate_limit_event is a pause whatever its status says", CLAUDE,
     '    if not (isinstance(info, dict) and info.get("status") == "rejected"):\n',
     '    if not isinstance(info, dict):\n'),

    ("750: a rejected status is read as a limit even while extra usage pays (review of #1019)",
     CLAUDE, '    if info.get("isUsingOverage") is True:\n', '    if False:\n'),

    ("750: the first rate_limit_event decides, though a later one says the account works again",
     CLAUDE, "    info = infos[-1] if infos else None\n", "    info = infos[0] if infos else None\n"),

    ("750: the CLI's error code is not read, only its sentence (review of #1019)", CLAUDE,
     '        words = [str(evt.get("error") or "")] + [\n', '        words = [] + [\n'),

    ("750: the first API error message decides, whatever it says", CLAUDE,
     '        found = _detect_pause(" · ".join(words))\n        if found[0]:\n            return found\n',
     '        found = _detect_pause(" · ".join(words))\n        return found\n'),

    ("750: a 429 the CLI retried past still parks the run", CLAUDE,
     "    last = events[-1] if events else {}\n",
     '    last = next((e for e in events if e.get("subtype") == "api_retry"), {})\n'),

    # the same rule, every harness in the registry (C-38 fixed these three; the family holds them)
    ("750: codex classifies its whole stream, item outputs included", "openfactory/adapters/agent/"
     "codex.py", "    tail = prose_only(out)[-4000:]\n", "    tail = out[-4000:]\n"),

    ("750: kimi classifies its whole stream, tool messages included", "openfactory/adapters/agent/"
     "kimi.py", "    tail = prose_only(out)[-4000:]\n", "    tail = out[-4000:]\n"),

    ("750: opencode classifies its whole stream, tool parts included", "openfactory/adapters/agent/"
     "opencode.py", "    tail = prose_only(out)[-4000:]\n", "    tail = out[-4000:]\n"),

    # ── 2. each of the CLI's own signals still does ────────────────────────────────────────────
    ("750: what the CLI printed outside the stream is no longer read", CLAUDE,
     "_CLI_SIGNALS = (_stderr, _api_error_message, _rejected_rate_limit, _retrying_a_rate_limit)\n",
     "_CLI_SIGNALS = (_api_error_message, _rejected_rate_limit, _retrying_a_rate_limit)\n"),

    ("750: the message the CLI writes in the model's place is no longer read", CLAUDE,
     "_CLI_SIGNALS = (_stderr, _api_error_message, _rejected_rate_limit, _retrying_a_rate_limit)\n",
     "_CLI_SIGNALS = (_stderr, _rejected_rate_limit, _retrying_a_rate_limit)\n"),

    ("750: a rejected rate_limit_event is no longer read", CLAUDE,
     "_CLI_SIGNALS = (_stderr, _api_error_message, _rejected_rate_limit, _retrying_a_rate_limit)\n",
     "_CLI_SIGNALS = (_stderr, _api_error_message, _retrying_a_rate_limit)\n"),

    ("750: the CLI dying while it retries a 429 is no longer read (review of #1019)", CLAUDE,
     "_CLI_SIGNALS = (_stderr, _api_error_message, _rejected_rate_limit, _retrying_a_rate_limit)\n",
     "_CLI_SIGNALS = (_stderr, _api_error_message, _rejected_rate_limit)\n"),

    ("750: a rejected rate_limit_event's reset is dropped", CLAUDE,
     '    return "rate_limit", when\n',
     '    return "rate_limit", None\n'),

    ("750: an auth stop seen first wins over a rate limit in the same stream, so a resumable "
     "pause becomes a hold", CLAUDE,
     '    return (next((s for s in said if s[0] == "rate_limit"), None)\n',
     '    return (next((s for s in said if s[0] == "auth"), None)\n'),
]
