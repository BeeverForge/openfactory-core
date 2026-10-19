"""A role reaches only the tools it is given: no MCP server of the account running the harness.

THE RULE, FOR EVERY HARNESS, EVERY ROLE, EVERY DOOR. Each harness CLI reads MCP servers the account
running it declared: its own configuration, its plugins, its hosted connectors. None of them is a
role's tool, and every role — the product role that answers people included — was started with
them. So every command the platform can hand a harness carries that harness's way of starting with
no server of the account, or, where the CLI has none, is not started while the account declares one.
The sweep below reads the harnesses from the registry, the roles from the builders and the doors from
the objects they build, so a harness, a role or a door added later is held to the rule without a line
of this file changing — and a harness this file does not know how to check fails until it is said.

WHAT EACH CLI OFFERS, AND WHAT WAS MEASURED (2026-10-12, with no real configuration touched):

- **Claude Code** — `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`: an empty configuration,
  and none read from anywhere else. Measured with the exact command the adapter builds: without it a
  role started with `--tools Read` reported six MCP servers and eight of their tools in its `init`
  event; with it, `mcp_servers: []`. The native reviewer builds its own command, and was the one
  door still without it.
- **Codex** — `--ignore-user-config`: `$CODEX_HOME/config.toml` is not read, the login still is. A
  `-c mcp_servers={}` override merges and clears none, measured. 0.146.0 (the pinned
  `HARNESS_CODEX`) carries the flag; 0.157.1 parses it on `exec` and `exec resume`, and lists a
  repository's own `.codex/config.toml` servers for no untrusted project.
- **OpenCode** — no flag. Its global configuration is `$XDG_CONFIG_HOME/opencode/` (1.18.13,
  `packages/core/src/global.ts`), so every run is handed a configuration directory the command
  makes for it, empty, and removes when it ends: a fixed one under `$HOME` was trusted to stay
  empty, and a role on the worktree box — on the host, with that `$HOME` — could plant a server in
  it for every later role (review of this fix). `OPENCODE_CONFIG` and `OPENCODE_CONFIG_DIR` are
  emptied, so the deployment's environment cannot hand one back; the repository's own stays locked
  out. Measured on 1.18.28: an account server in the global file is resolved by `opencode debug
  config`, and is gone with the directory moved. `~/.opencode/opencode.json` is read too, from the
  home directory, and nothing moves it — so a role is not started while it exists.
- **Kimi Code** — no flag and no variable (0.31.1, pinned; read in its bundle): it starts every
  server in `$KIMI_CODE_HOME/mcp.json` and every enabled plugin's, and the login lives in the same
  directory. So a role is not started while the account declares either, and the person is told.

NOT MEASURED: a run against a real model with a real account server present, for OpenCode and Kimi
(it costs a call, and Kimi's row has never run); OpenCode's configurations fetched from its console
organisation, a provider's well-known address, or a managed or MDM-deployed file — sources an
administrator sets on purpose, and which no environment variable reaches.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from openfactory.adapters.agent import registry
from openfactory.adapters.agent.base import smoke_command_for
from openfactory.adapters.agent.claude_code import NO_MCP_SERVERS
from openfactory.adapters.agent.codex import IGNORE_USER_CONFIG
from openfactory.adapters.sandbox.base import Workspace
from openfactory.adapters.sandbox.worktree import WorktreeSandbox
from tests.test_no_harness_hands_its_prompt_to_the_command_line import (
    _ROLES,
    _arguments,
    _doors,
    _project,
)

STRICT = "--strict-mcp-config --mcp-config '{\"mcpServers\":{}}'"

#: The variables a stand-in writes down: the ones that decide which configuration a harness reads.
_WATCHED = ("XDG_CONFIG_HOME", "OPENCODE_", "KIMI_CODE_HOME", "CODEX_HOME")

_STAND_IN = '''\
#!{interpreter}
"""Stands in for a harness CLI: writes down what its PROCESS was handed, then answers."""
import json, os, sys
from pathlib import Path

calls = Path({calls!r})
calls.mkdir(parents=True, exist_ok=True)
n = len(list(calls.glob("*.json")))
(calls / f"{{n}}.json").write_text(json.dumps({{
    "argv": sys.argv[1:],
    "env": {{k: v for k, v in os.environ.items() if k.startswith({watched!r})}},
}}))
# a role writes what it likes where it is configured from: here, a server for whichever role comes
# next, in the configuration directory this run was handed
fresh = os.environ.get("XDG_CONFIG_HOME")
seen = None
if fresh:
    where = Path(fresh)
    seen = {{"path": fresh, "exists": where.is_dir(),
             "entries": sorted(p.name for p in where.iterdir()) if where.is_dir() else None}}
    if where.is_dir():
        (where / "opencode").mkdir(exist_ok=True)
        (where / "opencode" / "opencode.json").write_text(
            '{{"mcp": {{"planted": {{"type": "local", "command": ["true"]}}}}}}')
record = calls / f"{{n}}.json"
record.write_text(json.dumps({{**json.loads(record.read_text()), "fresh": seen}}))
args = sys.argv[1:]
if "-o" in args:  # codex's --output-last-message, read back by a second command
    Path(args[args.index("-o") + 1]).write_text("done")
print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                  "result": "answered", "num_turns": 1}}))
'''


@dataclass(frozen=True)
class Isolation:
    """How a harness's role is started with no MCP server of the account.

    `argv`: words that stand together on its command line. `env`: what its process is handed, by
    variable. `fresh_dir`: a variable naming a configuration directory that is the run's own —
    there and empty when the harness starts, gone when the door returns, never handed twice.
    `refused_when`: files of the account, under `$HOME`, while any of which no role of this harness
    starts at all — for a CLI that offers no way to start without them."""

    argv: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    fresh_dir: str = ""
    refused_when: tuple[str, ...] = ()


#: One row per harness the registry ships. A harness missing here fails the sweep: say how its roles
#: start with no server of the account before it ships.
ISOLATION = {
    "claude_code": Isolation(argv=NO_MCP_SERVERS),
    "codex": Isolation(argv=(IGNORE_USER_CONFIG,)),
    "opencode": Isolation(
        env=(("OPENCODE_CONFIG", ""), ("OPENCODE_CONFIG_DIR", ""),
             ("OPENCODE_DISABLE_PROJECT_CONFIG", "1")),
        fresh_dir="XDG_CONFIG_HOME",
        refused_when=(".opencode/opencode.json", ".opencode/opencode.jsonc")),
    "kimi": Isolation(refused_when=(".kimi-code/mcp.json", ".kimi-code/plugins/installed.json")),
}


@pytest.fixture
def box(tmp_path, monkeypatch):
    """The REAL worktree box — a real `/bin/sh` runs every command, guards included — whose harness
    is a stand-in, in a home of the test's own: no configuration of this machine is read."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in ("XDG_CONFIG_HOME", "KIMI_CODE_HOME", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR",
                "CODEX_HOME"):
        monkeypatch.delenv(var, raising=False)
    calls = tmp_path / "calls"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in = bin_dir / "harness"
    stand_in.write_text(_STAND_IN.format(interpreter=sys.executable, calls=str(calls),
                                         watched=_WATCHED))
    stand_in.chmod(0o755)
    sandbox = WorktreeSandbox(root=tmp_path / "worktrees")
    ws = Workspace(path=tmp_path / "worktrees" / "job", branch="openfactory/mcp",
                   base_branch="main")
    ws.path.mkdir(parents=True)
    monkeypatch.setattr(sandbox, "harness_path", lambda name: str(stand_in))
    yield sandbox, ws, calls, home, stand_in
    sandbox.cleanup(workspace=ws)


def _made(calls: Path) -> list[dict]:
    """What the stand-in wrote down since the last read — then forgotten, door by door."""
    made = []
    for record in sorted(calls.glob("*.json"), key=lambda p: int(p.stem)):
        made.append(json.loads(record.read_text()))
        record.unlink()
    return made


def _stands_together(argv: list[str], words: tuple[str, ...]) -> bool:
    return any(tuple(argv[i:i + len(words)]) == words for i in range(len(argv)))


def _isolated(kind: str, call: dict, home: Path) -> str | None:
    """None when this process was started with no server of the account; else what it lacks."""
    rule = ISOLATION[kind]
    if rule.argv and not _stands_together(call["argv"], rule.argv):
        return f"its command line lacks {' '.join(rule.argv)!r}: {call['argv']}"
    for var, want in rule.env:
        got = call["env"].get(var)
        if got != want.format(home=home):
            return f"{var} is {got!r}, not {want.format(home=home)!r}"
    if rule.fresh_dir:
        seen = call.get("fresh") or {}
        if not seen.get("exists") or seen.get("entries") != []:
            return f"{rule.fresh_dir} was not an empty directory of the run's own: {seen}"
        if Path(seen["path"]).resolve().is_relative_to((home / ".config").resolve()):
            return f"{rule.fresh_dir} is the account's own configuration: {seen['path']}"
    return None


def _gone(kind: str, made: list[dict]) -> str | None:
    """None when every directory made for these runs is gone; else the one left behind."""
    for call in made:
        if ISOLATION[kind].fresh_dir and Path(call["fresh"]["path"]).exists():
            return f"{call['fresh']['path']} outlived its run"
    return None


def _knock(built, door: str):
    fn = getattr(built, door)
    return fn, _arguments(fn, ["# ADR-0000 the one document\nThe decision."])


# ── every harness, every role, every door ────────────────────────────────────────────────────────


def test_every_harness_the_registry_ships_says_how_its_roles_start_without_the_accounts_servers():
    missing = sorted(set(registry.HARNESSES) - set(ISOLATION))
    assert not missing, (f"{missing}: say in ISOLATION how a role of this harness is started with "
                         f"no MCP server of the account running it, before it ships")
    for kind, rule in ISOLATION.items():
        assert rule.argv or rule.env or rule.refused_when, f"{kind}: an isolation that is nothing"


@pytest.mark.parametrize("role", sorted(_ROLES))
@pytest.mark.parametrize("kind", sorted(registry.HARNESSES))
def test_every_door_starts_its_harness_with_no_server_of_the_account(kind, role, box):
    sandbox, ws, calls, home, _ = box
    built = _ROLES[role](_project(kind))
    doors = _doors(built)
    assert doors, f"{kind}/{role}: {type(built).__name__} exposes no door that takes a box"

    handed: list[str] = []
    for door in doors:
        fn, kw = _knock(built, door)
        fn(sandbox=sandbox, workspace=ws, **kw)
        made = _made(calls)
        assert made, f"{kind}/{role}.{door}: the harness never ran"
        for call in made:
            lacks = _isolated(kind, call, home)
            assert lacks is None, f"{kind}/{role}.{door}: {lacks}"
        assert _gone(kind, made) is None, f"{kind}/{role}.{door}: {_gone(kind, made)}"
        handed += [c["fresh"]["path"] for c in made if c.get("fresh")]
    assert len(handed) == len(set(handed)), f"{kind}/{role}: a configuration directory handed twice"


@pytest.mark.parametrize("role", sorted(_ROLES))
def test_every_claude_door_streams_its_events_so_a_wrapper_in_front_of_claude_sees_them(role, box):
    """Every door of every Claude role hands the CLI `--output-format stream-json --verbose`, read
    off the argv its process was handed (#755). The native reviewer builds its own command outside
    `ClaudeCodeAdapter._cli`, asked for `json`, and a wrapper in front of `claude` never saw a
    review's `rate_limit_event`: the second drift on that door, after `NO_MCP_SERVERS` above. So
    the rule is held here as that one is, as a sweep the registry feeds (review of #922: with
    `_cli`'s flag cut to `json`, 63 modules and 1746 tests stayed green on 82c8e6d)."""
    sandbox, ws, calls, _, _ = box
    built = _ROLES[role](_project("claude_code"))
    for door in _doors(built):
        fn, kw = _knock(built, door)
        fn(sandbox=sandbox, workspace=ws, **kw)
        made = _made(calls)
        assert made, f"claude_code/{role}.{door}: the harness never ran"
        for call in made:
            argv = call["argv"]
            assert _stands_together(argv, ("--output-format", "stream-json")), (
                f"claude_code/{role}.{door}: a wrapper sees no event until the run ends: {argv}")
            assert "--verbose" in argv, (
                f"claude_code/{role}.{door}: stream-json without --verbose is refused (rc 1): {argv}")


@pytest.mark.parametrize("role", sorted(_ROLES))
@pytest.mark.parametrize("kind", sorted(k for k, r in ISOLATION.items() if r.refused_when))
def test_no_door_starts_a_harness_while_the_account_declares_what_it_cannot_leave_out(
        kind, role, box):
    """For a CLI with no way to start without the account's servers, the platform does not start it
    while one is declared — on every door, and whichever of its files declares it."""
    sandbox, ws, calls, home, _ = box
    built = _ROLES[role](_project(kind))

    for declared in ISOLATION[kind].refused_when:
        path = home / declared
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"mcpServers": {"account-server": {"command": "true"}}}')
        try:
            for door in _doors(built):
                fn, kw = _knock(built, door)
                fn(sandbox=sandbox, workspace=ws, **kw)
                assert _made(calls) == [], (
                    f"{kind}/{role}.{door}: started while ~/{declared} declares a server")
        finally:
            path.unlink()


@pytest.mark.parametrize("kind", sorted(k for k, r in ISOLATION.items() if r.refused_when))
def test_the_person_is_told_which_file_held_the_role_back_and_what_to_do(kind, box):
    sandbox, ws, calls, home, _ = box
    adapter = registry.HARNESSES[kind]()

    for declared in ISOLATION[kind].refused_when:
        path = home / declared
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        result = adapter.ask(sandbox=sandbox, workspace=ws, prompt="which module owns /health?")
        path.unlink()

        assert not result.ok and _made(calls) == [], result
        said = result.summary or ""
        assert str(path) in said and "MCP" in said and "remove" in said.lower(), said


def test_what_one_opencode_role_leaves_in_its_configuration_reaches_no_later_role(box):
    """THE REVIEW'S CASE. The stand-in plants a server in the configuration directory it was handed,
    as a role on the worktree box could; the next role starts from an empty one all the same."""
    sandbox, ws, calls, home, _ = box
    opencode = registry.HARNESSES["opencode"]()

    opencode.ask(sandbox=sandbox, workspace=ws, prompt="first")
    opencode.ask(sandbox=sandbox, workspace=ws, prompt="second")

    first, second = _made(calls)
    assert second["fresh"]["entries"] == [], second["fresh"]
    assert first["fresh"]["path"] != second["fresh"]["path"]
    assert not Path(first["fresh"]["path"]).exists(), "the planted server outlived its run"


def test_opencode_is_not_started_when_no_empty_directory_can_be_made(box, tmp_path, monkeypatch):
    """Not with an empty `XDG_CONFIG_HOME`, which OpenCode reads as unset: the account's own."""
    sandbox, ws, calls, _, _ = box
    broken = tmp_path / "broken-bin"
    broken.mkdir()
    (broken / "mktemp").write_text("#!/bin/sh\nexit 1\n")
    (broken / "mktemp").chmod(0o755)
    monkeypatch.setenv("PATH", f"{broken}:{os.environ['PATH']}")

    result = registry.HARNESSES["opencode"]().ask(sandbox=sandbox, workspace=ws, prompt="p")

    assert _made(calls) == [] and not result.ok, result
    assert "no empty configuration directory" in (result.summary or ""), result.summary


def test_kimi_s_relocated_home_is_the_one_read(box, tmp_path, monkeypatch):
    """`KIMI_CODE_HOME` moves the account's directory, and the guard follows it."""
    sandbox, ws, calls, _, _ = box
    elsewhere = tmp_path / "kimi-home"
    (elsewhere / "plugins").mkdir(parents=True)
    (elsewhere / "plugins" / "installed.json").write_text("{}")
    monkeypatch.setenv("KIMI_CODE_HOME", str(elsewhere))

    registry.HARNESSES["kimi"]().ask(sandbox=sandbox, workspace=ws, prompt="p")

    assert _made(calls) == []


def test_the_deployments_environment_cannot_hand_opencode_a_configuration_back(box, monkeypatch):
    sandbox, ws, calls, home, _ = box
    monkeypatch.setenv("OPENCODE_CONFIG", "/etc/the-accounts/opencode.json")
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", "/etc/the-accounts")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))

    registry.HARNESSES["opencode"]().ask(sandbox=sandbox, workspace=ws, prompt="p")

    [call] = _made(calls)
    assert _isolated("opencode", call, home) is None, call["env"]


# ── the probes ────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", sorted(registry.HARNESSES))
def test_every_harness_s_smoke_call_starts_it_the_same_way(kind, box):
    """`box prove`'s smoke call is built by the same `_cli` a ticket goes through (#129), and runs
    through a real shell here, guard and all."""
    sandbox, ws, calls, home, stand_in = box
    command = smoke_command_for(registry.HARNESSES[kind](), harness=str(stand_in), prompt="ok")
    assert command, f"{kind}: no smoke call"

    sandbox.run(workspace=ws, command=command, timeout=60)

    made = _made(calls)
    [call] = made
    assert _isolated(kind, call, home) is None, (kind, call)
    assert _gone(kind, made) is None, _gone(kind, made)


def test_the_model_probe_carries_it(monkeypatch):
    """The probe uses the real run's flags — a probe that behaves differently from the thing it
    probes answers a different question."""
    import subprocess

    from openfactory.adapters.agent import claude_code

    seen: list[list[str]] = []

    def _popen(argv, **_kw):
        seen.append(list(argv))
        raise OSError("not run in a test")

    monkeypatch.setattr(subprocess, "Popen", _popen)
    claude_code.recognises_model("opus", harness="claude")

    ((argv,),) = (seen,)
    assert _stands_together(argv, NO_MCP_SERVERS), argv


# ── what each flag is ─────────────────────────────────────────────────────────────────────────────


def test_the_claude_configuration_is_empty_and_strict():
    """Strict: no MCP configuration is read from anywhere but the one given. Empty: it names none."""
    flags = list(NO_MCP_SERVERS)
    assert flags[0] == "--strict-mcp-config"
    assert json.loads(flags[flags.index("--mcp-config") + 1]) == {"mcpServers": {}}
    assert shlex.split(STRICT) == flags


def test_the_codex_flag_is_the_one_that_skips_the_file():
    """`--ignore-user-config`: the file is not read, and the login still is. Not a `-c` override,
    which merges into the file and clears none of its servers."""
    assert IGNORE_USER_CONFIG == "--ignore-user-config"
