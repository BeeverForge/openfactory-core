"""No option of the `openfactory` command line reads the environment by itself (#64, #905).

THE SHAPE, TWICE. A typer option declared with `envvar="X"` is resolved by typer, from
`os.environ`, before any of our code runs. That makes typer an independent reader of the
environment that no composition-root rule can see and no per-project override (nor, once it lands,
the credential store of #742 / PR #822, whose sweep walks `os.environ` reads in our modules) can
reach. #64 removed it from `bot-token --app-id` and `--installation-id`; the third flag of the same
command, `--key-path`, kept `envvar="OPENFACTORY_GH_APP_KEY"` (#905, measured 2026-10-20 on
bb929e49 and again on fa548ed4): the value typer read was bound to `key_path` and never used, the
key came from `app_private_key()` anyway, and `--help` advertised `[env var:
OPENFACTORY_GH_APP_KEY]` for a flag that did nothing.

So the guard is general: it walks every command the CLI builds and reads each parameter's
`envvar` off the built command object (not the source text, not the help), because the same defect
has now been written twice in one command.

WHY THE WALK IS DUCK-TYPED. typer 0.27.3 (this venv, 2026-10-21) builds its commands on a vendored
click (`typer._click.core`), so `isinstance(cmd, click.Group)` is False for every group and a walk
gated on it visits only the root (measured: 1 command, 2 parameters, instead of 89 and 234). A
group is recognised by the `commands` mapping it carries, which both the vendored and the real
click (typer >= 0.12, the floor in `pyproject.toml`) provide; and the walk asserts it reached a
sub-typer's command, so a walk that silently stops at the root fails instead of passing over
nothing.
"""

from __future__ import annotations

import re

import typer.main
from typer.testing import CliRunner

from openfactory.cli import app


def _walk(command, path: tuple[str, ...] = ()):
    """Every command under `command`, with the words a person types to reach it."""
    yield path, command
    for name, sub in sorted(getattr(command, "commands", {}).items()):
        yield from _walk(sub, (*path, name))


def _all_commands() -> dict[str, object]:
    return {" ".join(path): cmd for path, cmd in _walk(typer.main.get_command(app))}


def test_no_option_of_any_openfactory_command_declares_an_envvar():
    """Criterion: "an explicit `--key-path` wins and the `envvar` is dropped" (the envvar half).

    Before #905's fix this failed with `bot-token --key-path: envvar=OPENFACTORY_GH_APP_KEY`, the
    only `envvar=` left in the package (`git grep -n envvar -- openfactory addons tools`).
    """
    commands = _all_commands()
    # The walk must reach both a top-level command and a sub-typer's command, or it measured
    # nothing (see the module docstring: a click-isinstance walk stops at the root on typer 0.27).
    assert "bot-token" in commands and "preview login" in commands, (
        f"the walk did not reach the commands it must cover; it saw {sorted(commands)}")

    offenders = [
        f"{path} {param.opts[0] if param.opts else param.name}: envvar={param.envvar}"
        for path, cmd in commands.items()
        for param in cmd.params
        if param.envvar is not None
    ]
    assert offenders == [], (
        "these options are read from the environment by typer before any of our code runs; "
        "fall back to the composition root (`openfactory/credentials.py`) and name the variable "
        "in the help prose instead:\n" + "\n".join(offenders))


def test_the_bot_token_help_names_the_variables_in_prose_and_no_env_var_binding():
    """Criterion: the envvar is dropped, as a person reading `openfactory bot-token --help` sees it.

    Before #905's fix the help carried `[env var: OPENFACTORY_GH_APP_KEY]` beside `--key-path`
    (measured 2026-10-20, empty `HOME`, `COLUMNS=120`). The variables must still be named, in the
    prose of the options' help, since without the flag the key is still found through them.
    """
    result = CliRunner().invoke(app, ["bot-token", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "env var" not in result.output, (
        f"`bot-token --help` still shows an env-var binding:\n{result.output}")
    # The path form must be named on its own, not only as the prefix of `_CONTENT`.
    assert re.search(r"OPENFACTORY_GH_APP_KEY(?!_)", result.output), result.output
    assert "OPENFACTORY_GH_APP_KEY_CONTENT" in result.output, result.output
