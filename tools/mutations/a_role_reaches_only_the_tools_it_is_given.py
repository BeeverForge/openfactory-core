"""A role reaches only the tools it is given: no MCP server of the account running the harness —
proven by breaking it, harness by harness.

Run:  .venv/bin/python tools/mutate.py tools/mutations/a_role_reaches_only_the_tools_it_is_given.py

The claims, each a row: every command the platform hands a harness — every role, every door, the
smoke call and the model probe — starts it with no server of the account: Claude Code with an MCP
configuration that is strict and empty (the native reviewer's own command included); Codex with
the account's `config.toml` unread; OpenCode with a configuration directory made for the run, empty,
and gone when it ends, and the two variables that add one emptied; and Kimi Code, and OpenCode while `~/.opencode/` declares
one, not at all, the person told which file and what to do. A harness that joins the registry
without saying how is caught too.
"""

TEST = "tests/test_a_role_reaches_only_the_tools_it_is_given.py"
CLAUDE = "openfactory/adapters/agent/claude_code.py"
REVIEWER = "openfactory/adapters/reviewer/claude_code.py"
CODEX = "openfactory/adapters/agent/codex.py"
OPENCODE = "openfactory/adapters/agent/opencode.py"
KIMI = "openfactory/adapters/agent/kimi.py"
REGISTRY = "openfactory/adapters/agent/registry.py"

MUTATIONS = [
    # ── Claude Code ──
    ("TODAY'S RUN: every Claude role is handed the account's MCP servers again", CLAUDE,
     "            *(shlex.quote(a) for a in NO_MCP_SERVERS),\n", ""),
    ("the native reviewer builds its command without it, as it did", REVIEWER,
     "               *(shlex.quote(a) for a in NO_MCP_SERVERS)]", "               ]"),
    ("the model probe is started differently from the run it probes", CLAUDE,
     '"acceptEdits", *NO_MCP_SERVERS,', '"acceptEdits",'),
    ("the configuration is not strict: the account's own is read beside it", CLAUDE,
     "NO_MCP_SERVERS = (\"--strict-mcp-config\", \"--mcp-config\", '{\"mcpServers\":{}}')",
     "NO_MCP_SERVERS = (\"--mcp-config\", '{\"mcpServers\":{}}')"),
    ("the configuration given names servers of its own", CLAUDE,
     "'{\"mcpServers\":{}}')", "'{\"mcpServers\":{\"x\":{\"command\":\"x\"}}}')"),
    # ── Codex ──
    ("TODAY'S RUN: every Codex role is started with the account's MCP servers", CODEX,
     "            IGNORE_USER_CONFIG,\n", ""),
    ("the account's configuration is overridden instead of left unread: it merges", CODEX,
     'IGNORE_USER_CONFIG = "--ignore-user-config"', 'IGNORE_USER_CONFIG = "-c mcp_servers={}"'),
    # ── OpenCode ──
    ("every OpenCode role reads the account's global configuration again", OPENCODE,
     "        env += ACCOUNT_CONFIG_UNREAD\n", ""),
    ("the configuration directory handed is the account's own", OPENCODE,
     "'XDG_CONFIG_HOME=\"$of_cfg\"'", "'XDG_CONFIG_HOME=\"$HOME/.config\"'"),
    ("THE REVIEW'S CASE: one directory under $HOME for every run, trusted to stay empty", OPENCODE,
     "'of_cfg=\"$(mktemp -d)\" || {", "'of_cfg=\"$HOME/.openfactory/opencode-config\"; mkdir -p \"$of_cfg\" || {"),
    ("the directory made for a run outlives it, and what a role planted in it with it", OPENCODE,
     r"""trap 'rm -rf \"$of_cfg\"' EXIT; """, ""),
    ("a directory that cannot be made still starts OpenCode, on the account's configuration",
     OPENCODE, "'configuration.\"; exit 3; }; '", "'configuration.\"; }; '"),
    ("a deployment's OPENCODE_CONFIG still reaches the role", OPENCODE,
     '"OPENCODE_CONFIG=", "OPENCODE_CONFIG_DIR=")', '"OPENCODE_CONFIG_DIR=")'),
    ("a deployment's OPENCODE_CONFIG_DIR still reaches the role", OPENCODE,
     '"OPENCODE_CONFIG=", "OPENCODE_CONFIG_DIR=")', '"OPENCODE_CONFIG=")'),
    ("OpenCode starts while ~/.opencode/ declares a server", OPENCODE,
     'BEFORE_THE_HARNESS = f"{NOT_WHILE_DECLARED} {FRESH_CONFIG}"',
     'BEFORE_THE_HARNESS = f"{FRESH_CONFIG}"'),
    ("the guard reads only one of the two files OpenCode reads", OPENCODE,
     ' "$HOME/.opencode/opencode.jsonc"; do ', "; do "),
    ("the guard says so and starts it anyway", OPENCODE,
     "'exit 3; fi; done;')\n\n#: What the shell runs before OpenCode",
     "'fi; done;')\n\n#: What the shell runs before OpenCode"),
    # ── Kimi Code ──
    ("TODAY'S RUN: Kimi starts with every server the account declares", KIMI,
     "                else [BEFORE_THE_HARNESS, harness])", "                else [harness])"),
    ("the guard ignores a relocated KIMI_CODE_HOME", KIMI,
     "'k=\"${KIMI_CODE_HOME:-$HOME/.kimi-code}\"; '", "'k=\"$HOME/.kimi-code\"; '"),
    ("a plugin's servers are not looked for", KIMI,
     '\'for f in "$k/mcp.json" "$k/plugins/installed.json"; do \'',
     '\'for f in "$k/mcp.json"; do \''),
    ("the role is held back in silence: nobody reads which file or what to do", KIMI,
     "'if [ -e \"$f\" ]; then echo \"Kimi Code starts every MCP server declared in $f and cannot be '",
     "'if [ -e \"$f\" ]; then echo \"Kimi Code could not start, see the logs; it cannot be '"),
    # ── the registry ──
    ("a harness joins the registry without saying how its roles start without the account's",
     REGISTRY, '    "kimi": _kimi,\n', '    "kimi": _kimi,\n    "kimi-next": _kimi,\n'),
]
