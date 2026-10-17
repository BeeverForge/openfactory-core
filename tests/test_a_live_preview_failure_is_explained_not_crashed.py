"""A live preview test that cannot bring S1 up says why, and skips where S1 cannot be built (#358).

TWO DEFECTS, ONE MODULE. The three live preview tests ended in
`assert up.ok, f"{up.why}\\n{(Path(live.log_dir) / 'build.log').read_text()}"`, and a start refused
before the build leaves `log_dir` empty: the message read a relative `build.log`, raised
`FileNotFoundError`, and `why` was lost. And their guard asked only whether a daemon answers, so on
a machine where docker runs but a base image cannot be pulled they failed instead of skipping —
CONTRIBUTING's "your machine is not the reference". Held here without a daemon: the message is
built from what exists, and the build probe names the image it could not get.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from tests import one_live_preview
from tests.one_live_preview import Probe, explained, required

TESTS = Path(__file__).parent


def test_a_start_refused_before_the_build_is_explained_by_why_alone():
    assert explained("the plan names no service", "") == "the plan names no service"


def test_a_log_dir_without_a_build_log_is_explained_by_why_alone(tmp_path):
    assert explained("the build did not start", str(tmp_path)) == "the build did not start"
    assert explained("gone", str(tmp_path / "never-made")) == "gone"


def test_a_build_log_adds_its_tail(tmp_path):
    (tmp_path / "build.log").write_text("x" * 3000 + "pull access denied for node")

    said = explained("the build failed", str(tmp_path))

    assert said.startswith("the build failed\n")
    assert said.endswith("pull access denied for node")
    assert len(said) == len("the build failed\n") + 2000


def test_no_live_preview_test_reads_the_build_log_inside_an_assert_message():
    """The shape that crashed: a file read in the message of the assertion meant to explain."""
    crashing = []
    for path in sorted(TESTS.glob("test_a_preview_*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Assert) and node.msg is not None \
                    and "build.log" in ast.unparse(node.msg):
                crashing.append(f"{path.name}:{node.lineno}")

    assert not crashing, f"{crashing} read build.log in an assert message; use `explained`"


class _Daemon:
    """`docker` as the probe runs it: every call answers `0`, except the ones named to fail."""

    def __init__(self, fails: dict[str, str] | None = None, *, images=("busybox:latest",),
                 pulls=()):
        self.fails = fails or {}
        self.images = list(images)
        self.pulls = pulls
        self.ran: list[list[str]] = []

    def __call__(self, argv, *, env, timeout):
        self.ran.append(list(argv))
        line = " ".join(argv)
        for needle, said in self.fails.items():
            if needle in line:
                return subprocess.CompletedProcess(argv, 1, "", said)
        if argv[1:3] == ["image", "ls"]:
            return subprocess.CompletedProcess(argv, 0, "\n".join(self.images), "")
        if argv[1] in ("pull", "build"):
            self.images.extend(self.pulls)
        return subprocess.CompletedProcess(argv, 0, "", "")


def test_a_base_that_cannot_be_pulled_is_named_with_the_daemons_words():
    daemon = _Daemon({"pull postgres:16": "toomanyrequests: You have reached your pull rate limit"})

    probe = one_live_preview.probe_the_s1_build(daemon)

    assert not probe.ok
    assert "`postgres:16` could not be pulled on this daemon" in probe.why
    assert "toomanyrequests: You have reached your pull rate limit" in probe.why


def test_a_service_that_cannot_be_built_names_its_base():
    daemon = _Daemon({"openfactory-s1-probe-web": "failed to resolve source metadata for node"})

    probe = one_live_preview.probe_the_s1_build(daemon)

    assert not probe.ok
    assert "`web`" in probe.why and "`node:20-slim`" in probe.why
    assert "failed to resolve source metadata for node" in probe.why


def test_a_probe_that_builds_removes_its_tags_and_says_which_bases_it_brought():
    daemon = _Daemon(pulls=("postgres:16", "python:3.12-slim", "node:20-slim"),
                     images=("busybox:latest", "node:20-slim"))

    probe = one_live_preview.probe_the_s1_build(daemon)

    assert probe.ok, probe.why
    assert probe.brought == {"postgres:16", "python:3.12-slim"}
    assert ["docker", "image", "rm", "-f", "openfactory-s1-probe-api",
            "openfactory-s1-probe-web"] in daemon.ran
    assert all(call[0] == "docker" for call in daemon.ran)


def test_a_probe_that_fails_still_removes_its_tags():
    daemon = _Daemon({"openfactory-s1-probe-web": "no space left on device"})

    one_live_preview.probe_the_s1_build(daemon)

    assert daemon.ran[-2][:3] == ["docker", "image", "rm"]


def test_a_docker_that_cannot_be_run_is_a_failed_probe_not_a_crash():
    def gone(argv, *, env, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    probe = one_live_preview.probe_the_s1_build(gone)

    assert not probe.ok and "docker" in probe.why


def test_the_probe_runs_docker_in_the_environment_the_preview_runs_in(monkeypatch, tmp_path):
    """Same registry logins and daemon as the runtime (`compose._base_env`): a probe that read the
    shell's own could pass where the test then fails."""
    monkeypatch.setenv("OPENFACTORY_PREVIEW_DOCKER_CONFIG", str(tmp_path / "logins"))
    monkeypatch.setenv("SOMETHING_OF_THE_SHELL", "1")
    seen = []

    def daemon(argv, *, env, timeout):
        seen.append(env)
        return subprocess.CompletedProcess(argv, 0, "", "")

    one_live_preview.probe_the_s1_build(daemon)

    assert seen and all(env["DOCKER_CONFIG"] == str(tmp_path / "logins") for env in seen)
    assert all("SOMETHING_OF_THE_SHELL" not in env for env in seen)


def test_a_probe_that_built_is_handed_to_the_test(monkeypatch):
    monkeypatch.delenv("TEST_REQUIRE_DOCKER", raising=False)
    probe = Probe(ok=True, brought=frozenset({"postgres:16"}))

    assert required(probe) is probe


def test_a_probe_that_failed_skips_the_test_with_its_sentence(monkeypatch):
    monkeypatch.delenv("TEST_REQUIRE_DOCKER", raising=False)

    with pytest.raises(pytest.skip.Exception, match="`postgres:16` could not be pulled"):
        required(Probe(ok=False, why="`postgres:16` could not be pulled on this daemon: denied"))


def test_where_docker_is_required_a_probe_that_failed_fails_the_test(monkeypatch):
    """CI's integration job sets it: a test that silently skips forever is worse than one that
    fails (`tests/demo_projects.py`)."""
    monkeypatch.setenv("TEST_REQUIRE_DOCKER", "1")

    with pytest.raises(pytest.fail.Exception, match="`postgres:16` could not be pulled"):
        required(Probe(ok=False, why="`postgres:16` could not be pulled on this daemon: denied"))


def test_ci_requires_docker_where_the_live_previews_run():
    workflow = (TESTS.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    step = workflow[workflow.index("- run: make test-integration"):]
    step = step[:step.index("- run:", 1)]

    assert 'TEST_REQUIRE_DOCKER: "1"' in step
