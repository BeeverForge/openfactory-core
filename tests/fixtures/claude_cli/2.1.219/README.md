# What `claude` 2.1.219 printed on stdout, measured

The pinned CLI (`docker/worker.Dockerfile`, `@anthropic-ai/claude-code@2.1.219`), taken from
`npm pack @anthropic-ai/claude-code-linux-x64@2.1.219` (`package/claude`) and run on 2026-10-19
with `echo ok |` on stdin, from a fresh empty directory, under
`env -i HOME=$(mktemp -d) PATH=/usr/bin:/bin` — no credential, no configuration of this machine.

| file | argv after `claude` | exit |
|---|---|---|
| `json.stdout.jsonl` | `-p --output-format json --permission-mode plan --strict-mcp-config --mcp-config {"mcpServers":{}}` | 1 |
| `stream-json-verbose.stdout.jsonl` | `-p --output-format stream-json --verbose --permission-mode plan --strict-mcp-config --mcp-config {"mcpServers":{}}` | 1 |
| (no stdout) | `-p --output-format stream-json --permission-mode plan …` (no `--verbose`) | 1, stderr `Error: When using --print, --output-format=stream-json requires --verbose` |

Verbatim, key order kept, except two values that named the machine the run was taken on:
`cwd` → `"/work"`, `memory_paths.auto` → `"<stripped>"`.

The json envelope and the stream's last line are the same object with the same keys
(`is_error`, `num_turns`, `total_cost_usd`, `usage`, `result`, `type: "result"`); the stream opens
with `{"type":"system","subtype":"init",…}`, which has no `result`. 2.1.303 (measured the same day)
prints the same shapes, with `result_index` added to the result event.

No credentialed run was made, so neither file holds a `rate_limit_event`. Its shape is the one the
binary declares (`type: "rate_limit_event"`, `rate_limit_info: {status, resetsAt?, rateLimitType?,
utilization?, …}`, `uuid`, `session_id` — "Rate limit event emitted when rate limit info changes."),
and `tests/claude_cli_output.py` builds it from that declaration.
