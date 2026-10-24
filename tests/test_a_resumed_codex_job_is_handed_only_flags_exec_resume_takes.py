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
checks them against the binary's own `exec --help` and `exec resume --help`. Hidden aliases
`--help` does not print are left out; the row passes none of them.

WHERE THAT CHECK RUNS (#805). It used to look only at `CODEX_PINNED_BIN` and `PATH`, and CI has
neither, so it skipped on every CI run: the defect above, re-introduced into a table, stayed green.
It now reads the codex the worker image installs: it builds `docker/worker.Dockerfile`'s `toolbox`
stage, where `HARNESS_CODEX` is installed (2026-10-19, docker 29.9.1, `node:20-slim` present: 45 s
for the first build and 124 s for a later one with `--no-cache`, 5 s from cached layers), and runs the entry
a box runs, `harness_path("codex")`. That entry is a wrapper naming its runtime and script by absolute paths under the toolbox's mount point, so the stage's `/toolbox` is
linked there first. `HOME` is kept out of `/tmp`, where codex prints a PATH-alias warning. It is
marked `slow` and `xdist_group("docker")`, so CI runs it in the integration job, beside the daemon;
under `TEST_REQUIRE_DOCKER` (that job) it reads the image only, and anything that stops it from
reading the image FAILS rather than skips. On a person's box it takes `CODEX_PINNED_BIN`, else the
image where docker answers, else `codex` on `PATH`, else skips naming both remedies.
`tests/test_the_codex_tables_are_checked_against_the_worker_images_codex_in_ci.py` holds that.

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
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

import dockerfiles
import pytest

from openfactory.adapters.agent.codex import CodexAdapter
from openfactory.adapters.sandbox.container import TOOLBOX_MOUNT, ContainerSandbox

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
        if token.startswith("--") and "=" in token:  # the one-token `--opt=value` form (#741)
            option, value = token.split("=", 1)
            assert option in arity, f"{option!r} is not an option of any codex exec {PINNED} subcommand"
            options.append((option, value))
            continue
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
                "--ignore-user-config", "--dangerously-bypass-approvals-and-sandbox",
                "--model=gpt-5"]


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


#: The Dockerfile whose `toolbox` stage installs the codex a box runs, and that stage's name.
WORKER_DOCKERFILE = _repo() / "docker" / "worker.Dockerfile"
TOOLBOX_STAGE = "toolbox"
#: A cold build pulls `node:20-slim` and npm-installs the harnesses: minutes, not seconds (#738's
#: bound for the same kind of build).
BUILD_TIMEOUT = 900
#: The container's `HOME`, empty and outside `/tmp`: under `/tmp` codex 0.146.0 writes
#: `WARNING: proceeding, even though we could not create PATH aliases` to stderr (2026-10-19).
_CONTAINER_HOME = "/var/lib/codex-help"


def _docker_is_required() -> bool:
    return bool(os.environ.get("TEST_REQUIRE_DOCKER"))


def _cannot(why: str) -> None:
    """The image could not be read: a failure where docker is required (CI's integration job, the
    policy of `one_live_preview.required`), a skip naming the cause anywhere else."""
    if _docker_is_required():
        pytest.fail(why)
    pytest.skip(why)


def _a_daemon_answers() -> bool:
    """Cheap and cannot raise: whether the image route is worth trying on a person's box."""
    try:
        daemon = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                                capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return daemon.returncode == 0


@contextmanager
def _the_worker_images_codex() -> Iterator[Callable[..., str]]:
    """`run(*args) -> stdout` of the codex the worker image installs, in a throwaway build of its
    `toolbox` stage, with no network and no credential; the tag is removed on the way out."""
    stages = [stage for _, stage in dockerfiles.froms(WORKER_DOCKERFILE)]
    if TOOLBOX_STAGE not in stages:
        pytest.fail(f"docker/worker.Dockerfile has no `{TOOLBOX_STAGE}` stage (its stages: "
                    f"{stages}), so the stage that installs codex cannot be built for this check")
    tag = f"openfactory-codex-guard-805-{uuid.uuid4().hex[:12]}"
    entry = ContainerSandbox(image=tag).harness_path("codex")
    # The entry names `TOOLBOX_MOUNT/...` absolutely; the stage holds the same tree at `/toolbox`.
    script = (f"mkdir -p {_CONTAINER_HOME}/.codex && ln -s /toolbox {shlex.quote(TOOLBOX_MOUNT)}"
              f' && exec {shlex.quote(entry)} "$@"')
    try:
        try:
            built = subprocess.run(
                ["docker", "build", "--progress=plain", "-f", str(WORKER_DOCKERFILE),
                 "--target", TOOLBOX_STAGE, "-t", tag, str(_repo())],
                capture_output=True, text=True, timeout=BUILD_TIMEOUT)
        except FileNotFoundError:
            _cannot("docker is not on PATH, so the worker image's codex cannot be built to read "
                    "its help")
        except subprocess.TimeoutExpired:
            _cannot(f"docker did not build the worker image's {TOOLBOX_STAGE} stage within "
                    f"{BUILD_TIMEOUT} s")
        if built.returncode != 0:
            _cannot(f"docker could not build the worker image's {TOOLBOX_STAGE} stage (exit "
                    f"{built.returncode}):\n{built.stderr[-2000:]}")

        def run(*args: str) -> str:
            argv = ["docker", "run", "--rm", "--network", "none",
                    "-e", f"HOME={_CONTAINER_HOME}", "-e", f"CODEX_HOME={_CONTAINER_HOME}/.codex",
                    "-e", "LC_ALL=C", "--entrypoint", "sh", tag, "-c", script, "codex", *args]
            try:
                ran = subprocess.run(argv, capture_output=True, text=True, timeout=120)
            except (OSError, subprocess.SubprocessError) as error:
                _cannot(f"docker could not run `codex {' '.join(args)}` in the worker image: {error}")
            if ran.returncode != 0:
                _cannot(f"`codex {' '.join(args)}` exited {ran.returncode} in the worker image:\n"
                        f"{ran.stderr[-2000:]}")
            return ran.stdout

        yield run
    finally:
        with suppress(OSError, subprocess.SubprocessError):
            subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, timeout=120)


@contextmanager
def _a_local_codex(binary: str, tmp_path: Path) -> Iterator[Callable[..., str]]:
    """`run(*args) -> stdout` of a codex on this machine, with an empty `HOME`."""
    (tmp_path / ".codex").mkdir()
    env = {"HOME": str(tmp_path), "CODEX_HOME": str(tmp_path / ".codex"),
           "PATH": os.environ.get("PATH", ""), "LC_ALL": "C"}

    def run(*args: str) -> str:
        return subprocess.run([binary, *args], env=env, cwd=tmp_path, capture_output=True,
                              text=True, timeout=60, check=True).stdout

    yield run


@pytest.mark.slow
@pytest.mark.xdist_group("docker")
def test_the_tables_are_the_pinned_binarys_own_help(tmp_path):
    """Executes the binary, not a file, and decides which one at run time — never at collection.

    Under `TEST_REQUIRE_DOCKER` (CI's integration job) only the worker image's codex counts: a
    `codex` on the runner's `PATH` is not what the image installs, and a lost daemon or a failed
    build fails. Elsewhere: `CODEX_PINNED_BIN`, else the image where docker answers, else `codex`
    on `PATH`, else a skip naming both remedies. A version other than the pin fails from the image
    (the image IS the pin) and skips from this machine's own binary."""
    # NOT `OPENFACTORY_*`: `conftest.py` strips that prefix as the operator's before any test runs.
    pinned_bin = os.environ.get("CODEX_PINNED_BIN")
    if _docker_is_required() or (not pinned_bin and _a_daemon_answers()):
        codex, from_image = _the_worker_images_codex(), True
    elif binary := pinned_bin or shutil.which("codex"):
        codex, from_image = _a_local_codex(binary, tmp_path), False
    else:
        pytest.skip(f"no codex to read: start docker (this builds the worker image's codex) or "
                    f"set CODEX_PINNED_BIN to a codex-cli {PINNED}")

    with codex as run:
        version = run("--version").strip()
        if version != f"codex-cli {PINNED}":
            where = "the worker image's codex" if from_image else "this machine's codex"
            message = f"{where} is {version!r}, not codex-cli {PINNED}, which the tables are read from"
            if from_image:
                pytest.fail(message)
            pytest.skip(message)
        assert _help_options(run("exec", "--help")) == EXEC_TAKES
        assert _help_options(run("exec", "resume", "--help")) == EXEC_RESUME_TAKES
