"""Every command the Kimi row builds is one `kimi-code` agrees to start (#362).

`kimi-code` 0.31.1 — the version `docker/worker.Dockerfile` pins — checks its options in
`validateOptions` before it calls a model, and exits 1 on a pair it refuses. Read in its bundle
(`@moonshot-ai/kimi-code@0.31.1`, `dist/main.mjs`):

    if (promptMode && opts.yolo) throw new OptionConflictError("Cannot combine --prompt with --yolo.");
    if (promptMode && opts.auto) throw new OptionConflictError("Cannot combine --prompt with --auto.");
    if (promptMode && opts.plan) throw new OptionConflictError("Cannot combine --prompt with --plan.");

The row sent `--auto` beside `-p` on every run, and `--plan` beside it for the planner, every
read-only question and the `box prove` call, so every Kimi job was refused before it started.
Nothing caught it because nothing asked the binary; this test asks its option table instead.

A STRING CHECK IS ENOUGH HERE because the refusals are about which flags appear together, not
about what they do: the harness part of the command is tokenised as the shell would, past the
guard that runs first and before the prompt's own text, so a flag-like word inside a prompt is not
counted. The refusals below are 0.31.1's; a pin bump must read `validateOptions` again and change
them here first.
"""

from __future__ import annotations

import inspect
import shlex

import pytest

from openfactory.adapters.agent.kimi import BEFORE_THE_HARNESS, KimiAdapter

#: The version whose `validateOptions` the refusals below were read from.
PINNED = "0.31.1"

#: Flags `validateOptions` refuses beside `-p, --prompt` (0.31.1). `--yes` and `--auto-approve`
#: are hidden aliases `createProgram` maps to `yolo` before `validateOptions` sees them.
REFUSED_WITH_PROMPT = {"--yolo", "-y", "--yes", "--auto-approve", "--auto", "--plan"}

_YOLO = {"--yolo", "-y", "--yes", "--auto-approve"}
#: `-r`/`--resume` are hidden aliases of `--session`, and `-C` of `--continue` (0.31.1).
_SESSION = {"--session", "-S", "-r", "--resume"}
_CONTINUE = {"--continue", "-c", "-C"}

#: Pairs it refuses whatever the mode (0.31.1).
REFUSED_TOGETHER = [
    (_YOLO, {"--auto"}),
    (_CONTINUE, _SESSION),
    ({"--agent"}, {"--agent-file"}),
    ({"--agent", "--agent-file"}, _SESSION | _CONTINUE),
]

HARNESS = "/opt/openfactory-toolbox/kimi"


class _FakeSandbox:
    """The box double of `tests/test_agent_harness.py`: records each command, answers canned."""

    def __init__(self) -> None:
        self.commands: list[str] = []

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


def _built(shape: str) -> str:
    """The command the row hands the shell for one shape, through its public methods."""
    adapter, sb = KimiAdapter(model="k3"), _FakeSandbox()
    if shape == "execute":
        adapter.execute(sandbox=sb, workspace=_ws(), context=_ctx())
    elif shape == "execute, resumed":
        adapter.execute(sandbox=sb, workspace=_ws(), context=_ctx(resume_handle="sess-77"))
    elif shape == "repair":
        adapter.repair(sandbox=sb, workspace=_ws(), context=_ctx(), failure_log="2 failed")
    elif shape == "plan":
        adapter.plan(sandbox=sb, workspace=_ws(), context=_ctx())
    elif shape == "ask":
        adapter.ask(sandbox=sb, workspace=_ws(), prompt="is --auto set? answer --plan or -y")
    elif shape == "smoke":
        return adapter.smoke_command(harness=HARNESS, prompt="Reply with the word ok.")
    [command] = sb.commands
    return command


def _argv(command: str) -> list[str]:
    """The harness's own argv: past the guard the shell runs first, tokenised as the shell would."""
    rest = command.removeprefix(BEFORE_THE_HARNESS).lstrip()
    assert rest.startswith(f"{HARNESS} "), rest[:80]
    return shlex.split(rest.removeprefix(HARNESS))


def _options(argv: list[str]) -> list[str]:
    """The flags alone: each option's value (the prompt's text among them) is skipped."""
    takes_a_value = {"-p", "--prompt", "-m", "--model", "-S", "--session", "-r", "--resume",
                     "--output-format", "--add-dir", "--agent", "--agent-file"}
    flags, values = [], iter(argv)
    for token in values:
        flags.append(token)
        if token in takes_a_value:
            next(values, None)
    return flags


def _value(argv: list[str], *names: str) -> str | None:
    for i, token in enumerate(argv):
        if token in names:
            return argv[i + 1] if i + 1 < len(argv) else ""
    return None


#: Each public door of `KimiAdapter` that builds a command, and the shapes `_built` drives through
#: it. A shape is built by hand because each door needs its own arguments (a resumed run needs a
#: session); which doors there are is not: `test_every_door_that_builds_a_command_has_a_shape`
#: reads them off the class. Until review round 2 on dc0efac4 (2026-10-20, point 5) this list was
#: written by hand alone, and a new door would have left all three tables green.
DOORS = {
    "execute": ["execute", "execute, resumed"],
    "repair": ["repair"],
    "plan": ["plan"],
    "ask": ["ask"],
    "smoke_command": ["smoke"],
}

SHAPES = [shape for shapes in DOORS.values() for shape in shapes]


def _doors_of_the_row() -> set[str]:
    """The public methods of `KimiAdapter` that build a command: those that take the box to run
    it in (`sandbox`) or the harness path to build it for (`harness`). A method that takes
    neither (`smoke_reply` reads an answer) has no way to reach the CLI."""
    return {name for name, method in inspect.getmembers(KimiAdapter, inspect.isfunction)
            if not name.startswith("_")
            and {"sandbox", "harness"} & set(inspect.signature(method).parameters)}


def test_every_door_that_builds_a_command_has_a_shape():
    """Review round 2 on dc0efac4, point 5: `SHAPES` matched every door then, but nothing made a
    new one join it. Red under the cut that adds a public `review` door (plan
    `788_the_kimi_refusal_table_turns_red`, D1)."""
    doors = _doors_of_the_row()
    assert doors == set(DOORS), (
        f"doors with no shape: {sorted(doors - set(DOORS))}; "
        f"shapes for no door: {sorted(set(DOORS) - doors)}")


@pytest.mark.parametrize("shape", SHAPES)
def test_no_flag_the_pinned_cli_refuses_beside_the_prompt(shape):
    flags = set(_options(_argv(_built(shape))))
    assert "-p" in flags or "--prompt" in flags
    assert flags.isdisjoint(REFUSED_WITH_PROMPT), (
        f"kimi-code {PINNED} refuses {sorted(flags & REFUSED_WITH_PROMPT)} with --prompt")


@pytest.mark.parametrize("shape", SHAPES)
def test_no_pair_the_pinned_cli_refuses_together(shape):
    flags = set(_options(_argv(_built(shape))))
    for one, other in REFUSED_TOGETHER:
        assert not (flags & one and flags & other), (
            f"kimi-code {PINNED} refuses {sorted(flags & one)} with {sorted(flags & other)}")


@pytest.mark.parametrize("shape", SHAPES)
def test_every_value_is_one_the_pinned_cli_accepts(shape):
    argv = _argv(_built(shape))
    assert (_value(argv, "-p", "--prompt") or "").strip(), "a blank prompt is refused"
    assert _value(argv, "--output-format") == "stream-json"
    assert _value(argv, "-m", "--model") == "k3"
    session = _value(argv, "-S", "--session")
    if shape == "execute, resumed":
        assert session == "sess-77"
    else:
        assert session is None, "only a resumed run names a session"


def test_a_flag_inside_the_prompt_is_not_counted_as_one():
    """The `ask` prompt above says `--auto`, `--plan` and `-y`; the guard reads them as text."""
    argv = _argv(_built("ask"))
    assert "--auto" in _value(argv, "-p")
    assert "--auto" not in _options(argv)
