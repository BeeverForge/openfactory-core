"""Every command the Codex row builds carries only options its pinned subcommand takes (#636).

A paused Codex job came back as `codex exec resume <id> … -s workspace-write …`, and codex-cli
0.146.0 — the version `docker/worker.Dockerfile` pins — refused it before it called a model:
`error: unexpected argument '-s' found`, exit 2. Read in `codex-rs/exec/src/cli.rs` at
`rust-v0.146.0` (be449751a978f02e5bbba886999662956c7f38f5): `exec` flattens `SharedCliOptions`
(`codex-rs/utils/cli/src/shared_options.rs`) and `mark_exec_global_args` makes only the model and
the two bypass flags of it global, so `-s/--sandbox`, `-C/--cd`, `--oss`, `--local-provider`,
`-p/--profile` and `--add-dir` belong to `exec` alone; `-c/--config` is global on the multitool
root (`codex-rs/utils/cli/src/config_override.rs`), so `exec resume` takes it.

The two tables below are that surface, transcribed, and `test_the_tables_are_the_pinned_binarys_own_help`
checks them against the binary's own `exec --help` and `exec resume --help` wherever a 0.146.0 is
found. Hidden aliases `--help` does not print are left out; the row passes none of them.

A TOKEN CHECK IS ENOUGH HERE because the refusal is clap's "is this option known to this
subcommand", not anything about what the option does: the command is tokenised as the shell would,
past the `cat <path> |` that stages the prompt, each option's value skipped and nothing after `--`
counted. A pin bump must read `cli.rs` again and change the tables here first.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from openfactory.adapters.agent.codex import CodexAdapter

#: The version whose `cli.rs` the tables below were read from.
PINNED = "0.146.0"

#: Options `exec` declares `global = true`, plus the root's `-c` and feature toggles — the ones
#: `exec resume` takes too (0.146.0). `option -> takes a value`.
_GLOBAL = {
    "-c": True, "--config": True,
    "--enable": True, "--disable": True,
    "--strict-config": False,
    "-m": True, "--model": True,
    "--dangerously-bypass-approvals-and-sandbox": False,
    "--dangerously-bypass-hook-trust": False,
    "--skip-git-repo-check": False,
    "--ephemeral": False,
    "--ignore-user-config": False,
    "--ignore-rules": False,
    "--output-schema": True,
    "--json": False,
    "-o": True, "--output-last-message": True,
}

#: `codex exec resume` (0.146.0): the globals and resume's own.
EXEC_RESUME_TAKES = _GLOBAL | {"--last": False, "--all": False, "-i": True, "--image": True}

#: `codex exec` (0.146.0): the globals, `SharedCliOptions`, and `--color`.
EXEC_TAKES = _GLOBAL | {
    "-i": True, "--image": True,
    "--oss": False, "--local-provider": True,
    "-p": True, "--profile": True,
    "-s": True, "--sandbox": True,
    "-C": True, "--cd": True,
    "--add-dir": True,
    "--color": True,
}

SANDBOX_MODES = {"read-only", "workspace-write", "danger-full-access"}

HARNESS = "/opt/openfactory-toolbox/codex"
STAGED = "/work/.openfactory-prompt"
SESSION = "0199-abc"


class _FakeSandbox:
    """Records each command and answers canned; `staged` offers the off-argv channel (#326)."""

    def __init__(self, *, staged: bool = False) -> None:
        self.commands: list[str] = []
        if staged:
            self.stage_input = lambda *, workspace, text: STAGED  # noqa: ARG005

    def harness_path(self, name: str) -> str:  # noqa: ARG002
        return HARNESS

    def run(self, *, workspace, command: str, timeout: int):  # noqa: ARG002
        self.commands.append(command)
        return 0, "done"


def _ctx(**kw):
    from openfactory.adapters.agent.base import AgentContext
    from openfactory.contracts import Ticket

    return AgentContext(
        ticket=Ticket(id="#7", title="add health check", objective="expose /health", repo="o/r"),
        **kw,
    )


def _ws():
    from openfactory.adapters.sandbox.base import Workspace

    return Workspace(path="/work", branch="b", base_branch="main")


def _built(shape: str, adapter: CodexAdapter) -> str:
    """The command the row hands the shell for one shape, through its public methods."""
    if shape == "smoke":
        return adapter.smoke_command(harness=HARNESS, prompt="Reply with the word ok.")
    sb = _FakeSandbox(staged="staged" in shape)
    resume = {"resume_handle": SESSION} if "resumed" in shape else {}
    if shape.startswith("execute"):
        adapter.execute(sandbox=sb, workspace=_ws(), context=_ctx(**resume))
    elif shape == "repair":
        adapter.repair(sandbox=sb, workspace=_ws(), context=_ctx(), failure_log="2 failed")
    elif shape == "plan":
        adapter.plan(sandbox=sb, workspace=_ws(), context=_ctx())
    elif shape == "ask":
        adapter.ask(sandbox=sb, workspace=_ws(), prompt="answer -s read-only or -c x=1")
    [command] = [c for c in sb.commands if HARNESS in c]
    return command


def _argv(command: str) -> list[str]:
    """The harness's argv past `codex`: the `cat <path> |` that stages the prompt stripped."""
    tokens = shlex.split(command)
    if tokens[0] == "cat":
        assert tokens[1:3] == [STAGED, "|"], tokens[:3]
        tokens = tokens[3:]
    assert tokens[0] == HARNESS, tokens[:1]
    return tokens[1:]


def _invocation(command: str) -> tuple[str, str | None, list[tuple[str, str | None]]]:
    """`(subcommand, session, [(option, value)])`, stopping at `--`."""
    argv = _argv(command)
    assert argv[0] == "exec", argv[:1]
    rest, subcommand, session = argv[1:], "exec", None
    if rest[:1] == ["resume"]:
        subcommand, session, rest = "resume", rest[1], rest[2:]
    arity = EXEC_TAKES | EXEC_RESUME_TAKES
    options, tokens = [], iter(rest)
    for token in tokens:
        if token == "--":
            break
        assert token.startswith("-"), f"{token!r} is not an option of codex exec {PINNED}"
        assert token in arity, f"{token!r} is not an option of any codex exec {PINNED} subcommand"
        options.append((token, next(tokens) if arity[token] else None))
    return subcommand, session, options


def _values(options, *names: str) -> list[str | None]:
    return [value for option, value in options if option in names]


def _sandbox_overrides(options) -> list[dict]:
    """Each `-c` value that sets `sandbox_mode`, parsed as the TOML `key = value` codex reads."""
    parsed = [tomllib.loads(value) for value in _values(options, "-c", "--config")]
    return [table for table in parsed if "sandbox_mode" in table]


SHAPES = ["execute", "execute, staged", "execute, resumed", "execute, resumed, staged",
          "repair", "plan", "ask", "smoke"]

MODES = {
    "default": lambda monkeypatch: CodexAdapter(model="gpt-5"),
    "full-access": lambda monkeypatch: CodexAdapter(model="gpt-5", full_access=True),
    "full-access-env": lambda monkeypatch: (
        monkeypatch.setenv("OPENFACTORY_CODEX_FULL_ACCESS", "1"), CodexAdapter(model="gpt-5"))[1],
}


@pytest.fixture(autouse=True)
def _no_full_access_from_the_environment(monkeypatch):
    monkeypatch.delenv("OPENFACTORY_CODEX_FULL_ACCESS", raising=False)


@pytest.mark.parametrize("mode", list(MODES))
@pytest.mark.parametrize("shape", SHAPES)
def test_every_codex_command_carries_only_options_its_pinned_subcommand_takes(
    shape, mode, monkeypatch,
):
    subcommand, session, options = _invocation(_built(shape, MODES[mode](monkeypatch)))
    assert (subcommand == "resume") == ("resumed" in shape)
    takes = EXEC_RESUME_TAKES if subcommand == "resume" else EXEC_TAKES
    name = "codex exec resume" if subcommand == "resume" else "codex exec"
    refused = [option for option, _ in options if option not in takes]
    assert not refused, f"{refused} is not an option `{name}` {PINNED} takes"
    if session is not None:
        assert session == SESSION


@pytest.mark.parametrize("shape", ["execute, resumed", "execute, resumed, staged"])
def test_a_resumed_job_is_handed_the_sandbox_it_started_under_as_a_config_override(shape):
    """A resume re-derives its sandbox from the invocation rather than restoring the stored one
    (`thread_resume_params_from_config`, rust-v0.146.0), so it is said again — by `-c`."""
    _, _, options = _invocation(_built(shape, CodexAdapter(model="gpt-5")))
    assert _values(options, "-s", "--sandbox") == []
    assert _sandbox_overrides(options) == [{"sandbox_mode": "workspace-write"}]


@pytest.mark.parametrize("shape, mode", [
    ("execute", "workspace-write"), ("execute, staged", "workspace-write"),
    ("repair", "workspace-write"),
    ("plan", "read-only"), ("ask", "read-only"), ("smoke", "read-only"),  # ADR-0018's table
])
def test_a_fresh_job_keeps_its_sandbox_flag(shape, mode):
    _, _, options = _invocation(_built(shape, CodexAdapter(model="gpt-5")))
    assert _values(options, "-s", "--sandbox") == [mode]
    assert mode in SANDBOX_MODES
    assert _sandbox_overrides(options) == [], "one way to say the sandbox per path"


#: What the row built on main (3a582f1) in full access, token for token, past `codex exec`.
_FULL_ACCESS = ["--json", "-o", ".openfactory-codex-last-message", "--skip-git-repo-check",
                "--ignore-user-config", "--dangerously-bypass-approvals-and-sandbox", "-m", "gpt-5"]


@pytest.mark.parametrize("mode", ["full-access", "full-access-env"])
def test_full_access_hands_the_same_bypass_on_the_fresh_and_the_resumed_path(mode, monkeypatch):
    adapter = MODES[mode](monkeypatch)
    fresh = _argv(_built("execute, staged", adapter))
    resumed = _argv(_built("execute, resumed, staged", adapter))
    assert fresh == ["exec", *_FULL_ACCESS]
    assert resumed == ["exec", "resume", SESSION, *_FULL_ACCESS]


def _repo() -> Path:
    return Path(__file__).resolve().parents[1]


def test_the_option_tables_are_read_from_the_version_the_worker_image_pins():
    lines = (_repo() / "docker" / "worker.Dockerfile").read_text().splitlines()
    pins = [m.group(1) for line in lines if not line.lstrip().startswith("#")
            if (m := re.fullmatch(r"\s*ARG HARNESS_CODEX=@openai/codex@(\S+)\s*", line))]
    assert pins == [PINNED], f"the worker image pins codex {pins}; the tables are {PINNED}'s"


_OPTION_LINE = re.compile(r"^\s+(?:(-\w), )?(--[\w-]+)(?: <[^>]+>(?:\.\.\.)?)?\s*$")


def _help_options(text: str) -> dict[str, bool]:
    """`option -> takes a value`, read from the `Options:` section clap prints."""
    found, section = {}, False
    for line in text.splitlines():
        if line and not line.startswith(" "):
            section = line.strip() == "Options:"
            continue
        if section and (m := _OPTION_LINE.match(line)):
            short, long_ = m.group(1), m.group(2)
            if long_ in ("--help", "--version"):
                continue
            takes = "<" in line
            found[long_] = takes
            if short:
                found[short] = takes
    return found


def test_the_tables_are_the_pinned_binarys_own_help(tmp_path):
    """Executes the binary, not a file. Skips at run time — never at collection — wherever no
    0.146.0 is found: CI has none, and a person's `PATH` may hold another version."""
    # NOT `OPENFACTORY_*`: `conftest.py` strips that prefix as the operator's before any test runs.
    binary = os.environ.get("CODEX_PINNED_BIN") or shutil.which("codex")
    if not binary:
        pytest.skip(f"no codex binary (set CODEX_PINNED_BIN to a codex-cli {PINNED})")
    (tmp_path / ".codex").mkdir()
    env = {"HOME": str(tmp_path), "CODEX_HOME": str(tmp_path / ".codex"),
           "PATH": os.environ.get("PATH", ""), "LC_ALL": "C"}

    def run(*args: str) -> str:
        return subprocess.run([binary, *args], env=env, cwd=tmp_path, capture_output=True,
                              text=True, timeout=60, check=True).stdout

    version = run("--version").strip()
    if version != f"codex-cli {PINNED}":
        pytest.skip(f"{binary} is {version!r}, not codex-cli {PINNED}")
    assert _help_options(run("exec", "--help")) == EXEC_TAKES
    assert _help_options(run("exec", "resume", "--help")) == EXEC_RESUME_TAKES
