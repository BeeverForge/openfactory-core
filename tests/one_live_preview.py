"""The live preview tests take turns on the daemon (#265).

THEY SHARE ONE DAEMON AND ONE SET OF NAMES. `tests/test_a_preview_runs_on_a_real_daemon.py`,
`tests/test_a_preview_starts_on_a_real_daemon.py` and `tests/test_a_preview_opens_on_one_machine.py`
each bring up `openfactory-pv-acme-12` — the unit a person's card is — and a start takes down
whatever of its unit is already on the daemon, which is the point of a fresh start and exactly
wrong when the stack belongs to the test next door. Under `-n auto` they land on different
workers and can run at once, so each takes this lock for its whole run: a file lock, because the
workers are processes, in the temporary directory every worker shares.

AND THEY ASK THE MACHINE WHAT THEY NEED (#358). A daemon that answers is not a daemon that can
build S1: a laptop behind a registry it cannot reach, or a runner past Docker Hub's pull limit,
failed all three with a traceback. The cheap question — does a daemon answer — stays in each
module's `skipif` and runs at import; the expensive one — can S1's images be pulled and built
here — is `s1_product_builds`, asked once per process at run time, which skips with a sentence
naming what was missing. Where `TEST_REQUIRE_DOCKER` says docker is required (CI's integration
job), neither skips: a missing daemon or an image that cannot be built fails the live tests, and
a missing daemon fails the reaches-nothing test that shares the cheap guard.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "preview" / "s1" / "tree"
#: What S1 builds each service from (its Dockerfiles), and the image its compose file pulls.
BUILT_FROM = {"api": "python:3.12-slim", "web": "node:20-slim"}
PULLED = "postgres:16"
#: A pull and two builds, cold: minutes, not seconds.
PROBE_TIMEOUT = 600


def _docker_and_compose() -> bool:
    """A daemon answers and the compose plugin is usable — asked at import, so it stays cheap.

    WHERE `TEST_REQUIRE_DOCKER` IS SET it answers yes regardless. A `skipif` at import can only
    skip, and CI losing its daemon would then be the live tests skipping in silence; instead they
    run, and `s1_product_builds` fails them with its sentence. What is collected is the same. It is
    also the guard of `test_a_preview_reaches_nothing_of_the_host.py`'s real-engine test, which has
    no probe: under the switch that one runs too, and fails on docker's own error rather than
    skipping — red, as intended, without the sentence."""
    if os.environ.get("TEST_REQUIRE_DOCKER"):
        return True
    if not shutil.which("docker"):
        return False
    try:
        daemon = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                                capture_output=True, timeout=20)
        plugin = subprocess.run(["docker", "compose", "version", "--short"], capture_output=True,
                                timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return daemon.returncode == 0 and plugin.returncode == 0


def explained(why: str, log_dir: str) -> str:
    """The message of an assertion that a preview came up: `why`, and the tail of its build log
    when there is one. A start refused before the build has no log dir — `""`, which a path would
    read as the working directory — and the message must not crash over the file it lacks."""
    log = Path(log_dir, "build.log") if log_dir else None
    try:
        if log is not None and log.is_file():
            return f"{why}\n{log.read_text(errors='replace')[-2000:]}"
    except OSError:
        pass
    return why


@contextlib.contextmanager
def one_at_a_time() -> Iterator[None]:
    import fcntl  # POSIX only, like the daemon these tests need

    path = os.path.join(tempfile.gettempdir(), "openfactory-live-preview.lock")
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


class TheCard:
    """The card's tracker, for a live preview test: what the preview says on the card is kept here.

    THESE TESTS REGISTER `Project(name="acme")`, whose GitHub row names no repository, and the step
    that brings a preview up comments on the card through the project's tracker. Through the real
    row that comment went to the repository the suite runs from, under the operator's own `gh`
    login: 31 "Preview up" comments on `openfactory-core#12` between 2026-09-29 and 2026-10-01
    (`adapters/github_cli.py`). Each test installs this in place of `activities._tracker_for`, and
    asserts what was said."""

    def __init__(self) -> None:
        self.said: list[tuple[str, str]] = []

    def comment(self, ref: str, body: str) -> None:
        self.said.append((str(ref), body))


@dataclass(frozen=True)
class Probe:
    """Whether S1's images can be pulled and built on this daemon; if not, `why`, one sentence. And
    the base images the probe brought, which a test that removes what its run pulled must count."""

    ok: bool
    why: str = ""
    brought: frozenset[str] = field(default_factory=frozenset)


Runner = Callable[..., subprocess.CompletedProcess]


def _docker(argv: list[str], *, env: dict[str, str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, env=env, timeout=timeout)


def _tail(cp: subprocess.CompletedProcess) -> str:
    said = ((cp.stderr or "") + (cp.stdout or "")).strip()
    return said[-600:] or f"exit {cp.returncode}"


def probe_the_s1_build(run: Runner = _docker) -> Probe:
    """Get what S1 pulls and build what it builds, the way the preview runtime's
    `docker compose up -d --build` will: a base is pulled only when this daemon lacks it, a build
    runs on the cached base and never asks the registry for a newer one (no `--pull`), and both in
    the runtime's reduced environment (`compose._base_env`: the same registry logins, the same
    daemon). So a machine with the bases loaded and no registry passes, as the tests would. The
    probe's own tags are removed; the bases stay, for the test that needs them next."""
    from openfactory.adapters.preview import compose

    tags = [f"openfactory-s1-probe-{svc}" for svc in BUILT_FROM]
    with tempfile.TemporaryDirectory(prefix="openfactory-s1-probe-") as home:
        env = compose._base_env(home)

        def images() -> set[str]:
            listed = run(["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"],
                         env=env, timeout=60)
            return set((listed.stdout or "").split()) if listed.returncode == 0 else set()

        try:
            before = images()
            try:
                why = ""
                for base in (PULLED, *BUILT_FROM.values()):
                    if run(["docker", "image", "inspect", base], env=env,
                           timeout=60).returncode == 0:
                        continue
                    pulled = run(["docker", "pull", base], env=env, timeout=PROBE_TIMEOUT)
                    if pulled.returncode != 0:
                        why = f"`{base}` could not be pulled on this daemon: {_tail(pulled)}"
                        break
                for (svc, base), tag in zip(BUILT_FROM.items(), tags, strict=True):
                    if why:
                        break
                    built = run(["docker", "build", "-t", tag, str(FIXTURE / svc)],
                                env=env, timeout=PROBE_TIMEOUT)
                    if built.returncode != 0:
                        why = (f"S1's `{svc}` could not be built from `{base}` on this daemon: "
                               f"{_tail(built)}")
            finally:
                run(["docker", "image", "rm", "-f", *tags], env=env, timeout=60)
            brought = frozenset((images() - before) & {PULLED, *BUILT_FROM.values()})
        except (OSError, subprocess.SubprocessError) as exc:
            return Probe(ok=False, why=f"docker could not be run to build S1 here: {exc}")
    return Probe(ok=not why, why=why, brought=brought)


def required(probe: Probe) -> Probe:
    """The probe, to a test that needs S1 built: handed over when it built, else the test skips
    with its sentence — or fails with it where `TEST_REQUIRE_DOCKER` is set (CI's integration
    job), since a test that silently skips forever is worse than one that fails."""
    if probe.ok:
        return probe
    if os.environ.get("TEST_REQUIRE_DOCKER"):
        pytest.fail(probe.why)
    pytest.skip(probe.why)


#: The probe's answer for this process, once asked (`the_s1_product_builds_here`).
_PROBED: Probe | None = None


def the_s1_product_builds_here() -> Probe:
    """The probe, run on the first request of the process and reused after. Held HERE because
    each live module binds `s1_product_builds` to find it, and pytest gives every binding a cache of
    its own: a session fixture alone ran the probe once per module, three pulls and six builds."""
    global _PROBED
    if _PROBED is None:
        with one_at_a_time():  # in turn with the live tests, which share the daemon
            _PROBED = probe_the_s1_build()
    return _PROBED


@pytest.fixture(scope="session")
def s1_product_builds() -> Probe:
    """Asked at run time — never at import, where it would cost a build on every collection —
    and once per process; each module that requests it still skips or fails with the sentence."""
    return required(the_s1_product_builds_here())
