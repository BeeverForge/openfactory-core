"""#805: the Codex option tables are checked against the worker image's codex in CI, and never skip there.

`tests/test_a_resumed_codex_job_is_handed_only_flags_exec_resume_takes.py` holds every Codex
command to `EXEC_TAKES` / `EXEC_RESUME_TAKES`, transcribed from codex-cli 0.146.0. The one test
that holds those tables to codex itself, `test_the_tables_are_the_pinned_binarys_own_help`, took
`CODEX_PINNED_BIN` or `codex` on `PATH` and skipped when it found neither or another version. CI has
neither, and the test carried no marker, so it ran in the four unit shards and skipped on every run:
the issue's cut (`"-s": True` in `EXEC_RESUME_TAKES`, the defect #636 fixed) left that module at
`100 passed, 1 skipped`.

THIS MODULE DRIVES THE REAL GUARD, not a copy of its logic: it runs that one node in a nested
pytest with a `PATH` it controls — the host's `git` and `sh`, plus per case a fake `docker` and/or
a fake `codex` — and reads the outcome from the junit XML (`<skipped>`, `<failure>`, neither),
never from what the run printed. The fake `docker` logs its argv, so the image route's commands are
read as the guard issued them. No daemon is needed: this module is a unit test.

THE FIXTURES ARE CODEX'S OWN OUTPUT. `tests/fixtures/codex/0.146.0/exec-help.txt` and
`exec-resume-help.txt` are the stdout, byte for byte, of the codex the worker image installs,
recorded 2026-10-19 with docker 29.9.1 (linux/amd64):

    docker build --progress=plain -f docker/worker.Dockerfile --target toolbox -t <tag> .
    docker run --rm --network none -e HOME=/var/lib/codex-help \\
      -e CODEX_HOME=/var/lib/codex-help/.codex -e LC_ALL=C --entrypoint sh <tag> \\
      -c 'mkdir -p /var/lib/codex-help/.codex && ln -s /toolbox /opt/openfactory-toolbox \\
          && exec /opt/openfactory-toolbox/codex "$@"' codex exec [resume] --help

`--version` printed `codex-cli 0.146.0`; each run exited 0 with empty stderr (a `HOME` under
`/tmp` adds a PATH-alias warning). The entry is linked at the mount point because the toolbox's
codex wrapper names its runtime and script by absolute paths under `/opt/openfactory-toolbox`
(`docker/worker.Dockerfile`, the harness-entry `RUN`). The guard's `_help_options` over each file
equals its table: symmetric difference empty for both. A case that "differs" adds or removes one
`Options:` line of a copy.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from openfactory.adapters.sandbox.container import ContainerSandbox
from tests.test_a_resumed_codex_job_is_handed_only_flags_exec_resume_takes import PINNED

ROOT = Path(__file__).resolve().parents[1]
GUARD_FILE = "tests/test_a_resumed_codex_job_is_handed_only_flags_exec_resume_takes.py"
GUARD = f"{GUARD_FILE}::test_the_tables_are_the_pinned_binarys_own_help"
FIXTURES = ROOT / "tests" / "fixtures" / "codex" / PINNED
#: The line `codex exec resume` would print if it took the sandbox option — #636's refusal, undone.
SANDBOX_LINE = "  -s, --sandbox <SANDBOX_MODE>\n"
#: `--color` is `exec`'s own option; a help without it is a table that says too much.
COLOR_LINE = "      --color <COLOR>\n"


def _fake_docker(bin_dir: Path, log: Path, version: str, exec_help: Path, resume_help: Path) -> None:
    """A `docker` that answers the guard's image route with recorded output, and logs its argv.

    Each call appends `<argc>\\0<arg>\\0…` to `log`: a count, then the arguments NUL-terminated, so
    an argument with a space or a newline (the `sh -c` script) is read back exactly. Its answers
    and its log are baked into the script, not read from the environment, because the guard may
    hand docker an environment of its own. Anything it was not written for exits 2, naming it."""
    cat = shutil.which("cat")
    script = f"""#!/bin/sh
{{ printf '%s\\0' "$#"; for arg in "$@"; do printf '%s\\0' "$arg"; done; }} >> {shlex.quote(str(log))}
case "$1" in
  build|rmi|pull) exit 0 ;;
  version) echo 29.9.1; exit 0 ;;
  run)
    a= b= c=
    for arg in "$@"; do a=$b; b=$c; c=$arg; done
    if [ "$c" = --version ]; then echo {shlex.quote(f"codex-cli {version}")}; exit 0; fi
    if [ "$a $b $c" = "exec resume --help" ]; then exec {cat} {shlex.quote(str(resume_help))}; fi
    if [ "$b $c" = "exec --help" ]; then exec {cat} {shlex.quote(str(exec_help))}; fi
    echo "fake docker: no recorded answer for run ... $a $b $c" >&2; exit 2 ;;
  *) echo "fake docker: no recorded answer for $1" >&2; exit 2 ;;
esac
"""
    (bin_dir / "docker").write_text(script)
    (bin_dir / "docker").chmod(0o755)


def _fake_codex(bin_dir: Path, version: str, exec_help: Path, resume_help: Path) -> None:
    """A `codex` on `PATH` printing the pinned version and help: what a runner image could carry."""
    cat = shutil.which("cat")
    (bin_dir / "codex").write_text(f"""#!/bin/sh
case "$*" in
  --version) echo {shlex.quote(f"codex-cli {version}")} ;;
  "exec --help") exec {cat} {shlex.quote(str(exec_help))} ;;
  "exec resume --help") exec {cat} {shlex.quote(str(resume_help))} ;;
  *) echo "fake codex: no recorded answer for $*" >&2; exit 2 ;;
esac
""")
    (bin_dir / "codex").chmod(0o755)


def _bin(tmp_path: Path) -> Path:
    """`PATH` for the nested run: the host's `git` and `sh` and nothing else, so no `docker` and
    no `codex` of the machine's own is found. The fakes call `cat` by its absolute path."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("git", "sh"):
        (bin_dir / tool).symlink_to(shutil.which(tool))
    return bin_dir


def _help_copy(tmp_path: Path, name: str, *, add: str = "", drop: str = "") -> Path:
    """The recorded help, or a copy with one `Options:` line added (after the heading) or removed."""
    text = (FIXTURES / name).read_text()
    if not add and not drop:
        return FIXTURES / name
    if drop:
        assert text.count(drop) == 1, f"{name} does not print {drop!r} exactly once"
        text = text.replace(drop, "")
    if add:
        assert text.count("Options:\n") == 1, f"{name} has no single Options: section"
        text = text.replace("Options:\n", "Options:\n" + add)
    copy = tmp_path / f"changed-{name}"
    copy.write_text(text)
    return copy


def _run_guard(tmp_path: Path, bin_dir: Path, *, require_docker: bool) -> tuple[str, str]:
    """Runs the guard node alone; returns `(outcome, message)` read from the junit XML."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("CODEX_PINNED_BIN", "TEST_REQUIRE_DOCKER", "PYTEST_ADDOPTS")
           and not k.startswith("PYTEST_XDIST")}
    env["PATH"] = str(bin_dir)
    if require_docker:
        env["TEST_REQUIRE_DOCKER"] = "1"
    report = tmp_path / "r.xml"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:xdist",
         "-p", "no:cacheprovider", f"--junitxml={report}", GUARD],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert report.exists(), f"the nested run wrote no report:\n{done.stdout[-2000:]}{done.stderr[-800:]}"
    cases = ET.parse(report).getroot().iter("testcase")
    cases = [c for c in cases if c.get("name") == "test_the_tables_are_the_pinned_binarys_own_help"]
    assert len(cases) == 1, f"the guard ran {len(cases)} times:\n{done.stdout[-2000:]}"
    for outcome in ("skipped", "failure", "error"):
        if (node := cases[0].find(outcome)) is not None:
            return outcome, node.get("message", "")
    return "passed", ""


#: id → (docker answers, codex on PATH, the image's version, (help line added to resume, line
#: removed from exec), outcome, a word the failure's message must hold).
ROWS = {
    "no docker on PATH": (False, False, PINNED, ("", ""), "failure", "docker"),
    "a pinned codex on PATH and no docker": (False, True, PINNED, ("", ""), "failure", "docker"),
    "the image's codex is another version": (True, False, "0.145.0", ("", ""), "failure", "0.145.0"),
    "the image's codex prints the pinned help": (True, False, PINNED, ("", ""), "passed", ""),
    "the image's resume help takes -s": (True, False, PINNED, (SANDBOX_LINE, ""), "failure",
                                         "--sandbox"),
    "the image's exec help lacks --color": (True, False, PINNED, ("", COLOR_LINE), "failure",
                                            "--color"),
}


@pytest.mark.parametrize("row", list(ROWS))
def test_under_TEST_REQUIRE_DOCKER_the_tables_guard_reads_the_worker_images_codex_and_never_skips(
        tmp_path, row):
    """Criterion: in CI the guard runs against the codex the worker image installs and does not
    skip; a table that differs from that codex's help turns the job red. On main the guard asked
    only `CODEX_PINNED_BIN` and `PATH`: it skipped with no binary or another version, PASSED off a
    runner's `PATH`, and never asked docker, so every row here but none came out as written."""
    answers, on_path, version, (added, dropped), outcome, word = ROWS[row]
    bin_dir = _bin(tmp_path)
    exec_help = _help_copy(tmp_path, "exec-help.txt", drop=dropped)
    resume_help = _help_copy(tmp_path, "exec-resume-help.txt", add=added)
    if answers:
        _fake_docker(bin_dir, tmp_path / "docker.log", version, exec_help, resume_help)
    if on_path:
        _fake_codex(bin_dir, PINNED, exec_help, resume_help)

    got, message = _run_guard(tmp_path, bin_dir, require_docker=True)

    assert got == outcome, f"{row}: the guard's outcome is {got} ({message!r}), not {outcome}"
    assert word in message, f"{row}: the guard failed, but not naming {word!r}: {message!r}"


def _calls(log: Path) -> list[list[str]]:
    """The fake docker's log: `<argc>\\0` then that many NUL-terminated arguments, per call."""
    fields = log.read_bytes().decode().split("\0") if log.exists() else []
    calls, at = [], 0
    while at < len(fields) - 1:
        count = int(fields[at])
        calls.append(fields[at + 1: at + 1 + count])
        at += 1 + count
    return calls


def _after(argv: list[str], option: str) -> str | None:
    """The value of `option` in `argv`, given as `option value` or `option=value`."""
    for i, arg in enumerate(argv):
        if arg == option and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith(option + "="):
            return arg.split("=", 1)[1]
    return None


def test_the_image_route_builds_the_worker_dockerfiles_toolbox_stage_and_runs_the_entry_a_box_runs(
        tmp_path):
    """Criterion: the guard reads "the codex the worker image installs". That is the toolbox stage
    of `docker/worker.Dockerfile` (where `HARNESS_CODEX` is installed), run through the entry a box
    runs, `harness_path("codex")`, with no network, and the built tag removed after. On main the
    guard never called docker: the log is empty."""
    bin_dir = _bin(tmp_path)
    log = tmp_path / "docker.log"
    _fake_docker(bin_dir, log, PINNED, FIXTURES / "exec-help.txt",
                 FIXTURES / "exec-resume-help.txt")

    _run_guard(tmp_path, bin_dir, require_docker=True)
    calls = _calls(log)

    builds = [c for c in calls if c[:1] == ["build"]]
    assert len(builds) == 1, f"the guard built {len(builds)} images; its docker calls: {calls}"
    build = builds[0]
    assert _after(build, "-f") == str(ROOT / "docker" / "worker.Dockerfile"), build
    assert _after(build, "--target") == "toolbox", build
    assert build[-1] == str(ROOT), f"the build context is {build[-1]!r}, not the checkout"
    tag = _after(build, "-t")
    assert tag, build

    entry = ContainerSandbox(image="x").harness_path("codex")
    runs = [c for c in calls if c[:1] == ["run"]]
    assert runs, f"the guard built the stage and ran nothing in it: {calls}"
    for run in runs:
        assert "--rm" in run, run
        assert _after(run, "--network") == "none", run
        assert tag in run, f"the run is not of the built image {tag!r}: {run}"
        assert any(entry in arg for arg in run), f"the run does not exec {entry}: {run}"

    last_run = max(i for i, c in enumerate(calls) if c[:1] == ["run"])
    assert ["rmi", "-f", tag] in calls[last_run + 1:], f"{tag} is left behind: {calls}"


def _make_n(target: str) -> str:
    return subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True, text=True,
                          timeout=60).stdout


def _collected(tmp_path: Path, target: str) -> set[str]:
    """The node ids of the guard's module that `make <target>`'s marker expression selects, read
    from the suite's own `--record-ids` listing."""
    expression = re.search(r'-m "([^"]+)"', _make_n(target)).group(1)
    ids = tmp_path / f"{target}.txt"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--collect-only", "-p", "no:randomly",
         "-p", "no:cacheprovider", "-m", expression, f"--record-ids={ids}", GUARD_FILE],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert done.returncode in (0, 5), f"collection failed:\n{done.stdout[-2000:]}{done.stderr[-800:]}"
    return set(ids.read_text().split()) if ids.exists() else set()


def test_the_tables_guard_is_selected_by_the_integration_run_where_docker_is_required(tmp_path):
    """Criterion: the guard runs in CI where docker is (`make test-integration`, the integration
    job, `TEST_REQUIRE_DOCKER: "1"`), not in the unit shards, where no daemon answers. On main it
    carried no marker: the unit expression collected it and the integration one did not."""
    unit, integration = _collected(tmp_path, "test-unit"), _collected(tmp_path, "test-integration")

    assert unit, "the unit run selects nothing from the guard's module: the expression was misread"
    assert GUARD in integration, f"the integration run does not select the guard: {integration}"
    assert GUARD not in unit, "the unit shards, where no daemon answers, still select the guard"

    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]
    steps = [s for s in jobs["integration"]["steps"] if s.get("run") == "make test-integration"]
    assert len(steps) == 1, steps
    assert steps[0].get("env", {}).get("TEST_REQUIRE_DOCKER") == "1", steps[0]


def test_without_TEST_REQUIRE_DOCKER_no_docker_and_no_codex_skips_the_tables_guard_naming_both(
        tmp_path):
    """A person's box keeps its skip (CONTRIBUTING, "Your machine is not the reference"), and the
    skip names both remedies: start docker, or set `CODEX_PINNED_BIN`. On main the skip named
    only `CODEX_PINNED_BIN`."""
    got, message = _run_guard(tmp_path, _bin(tmp_path), require_docker=False)

    assert got == "skipped", f"the guard's outcome is {got} ({message!r}), not skipped"
    assert "docker" in message.lower(), f"the skip does not name docker: {message!r}"
    assert "CODEX_PINNED_BIN" in message, f"the skip does not name CODEX_PINNED_BIN: {message!r}"
