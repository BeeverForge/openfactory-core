"""#738: the CLI image builds with a root certificate in `docker/extra-ca/`, and its pip trusts it.

Until this guard, the CLI image was only ever built with `docker/extra-ca/` empty — by the release
workflow and by every contributor — so the extra-CA branch of its trust step never ran anywhere,
and it could not run: it imported `certifi`, which `python:3.12-slim` does not carry, and the layer
exited 2 (measured 2026-10-17, docker 29.9.1). A person behind TLS interception building the
image from source — the release's upgrade rehearsal, the compose file's `--profile build`, a
self-built deployment — was the first to find out.

So this BUILDS the image with a throwaway root, then asks the image which file pip reads and loads
that file the way pip's TLS does. The sandbox test beside it
(`test_the_cli_image_trusts_an_extra_root_without_certifi.py`) holds the step's logic without
docker; this holds that the step works in the base image it actually runs in.

IT NEVER TOUCHES THE CHECKOUT'S `docker/extra-ca/`. It builds from a copy of the build context in
`tmp_path`, and asserts afterwards that the real directory is byte-for-byte as it was. That
directory's `.gitignore` ignores `*.crt`, so a leaked PEM would not even show in `git status` — and
every later build on that machine would trust it.

WHAT IT NEEDS, and what it does without it: a docker daemon (probed at import, cheaply, only to
feed `skipif` — collection never changes), the image's three `FROM`s from a registry (pulled at run
time; one that cannot be pulled skips naming it), PyPI for the wheel's install, and `openssl` on the
host to make a certificate pip will load. Under `TEST_REQUIRE_DOCKER` (CI's integration job) neither
the daemon nor a pull skips: a CI that lost its daemon must not pass this in silence, as
`tests/one_live_preview.py` does for the live previews.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import uuid
from collections.abc import Iterator

import dockerfiles
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCKERFILE = "docker/cli.Dockerfile"
THROWAWAY = "openfactory-738-throwaway"
#: A cold build: three pulls and the wheel's `pip install`. Minutes, not seconds.
BUILD_TIMEOUT = 900

_CACHES = shutil.ignore_patterns("__pycache__", "*.egg-info", ".pytest_cache", ".ruff_cache",
                                 ".mypy_cache")


def _ignored(directory: str, names: list[str]) -> set[str]:
    """What `.dockerignore` keeps out of the context, so the copy is the context docker would send:
    the caches anywhere, and `build/` only directly under an add-on (`addons/*/build/`)."""
    parent = pathlib.Path(directory)
    overlay = {"build"} if parent.parent.name == "addons" and parent.parent.parent == ROOT else set()
    return set(_CACHES(directory, names)) | (overlay & set(names))
#: `COPY [--chown=…] <src>… <dest>` — every source but those copied from another stage.
_COPY = re.compile(r"^COPY\s+(?!--from)(.+)$", re.MULTILINE)


def _a_daemon_answers() -> bool:
    """Asked at import, so it is cheap and cannot raise; it only feeds `skipif`.

    WHERE `TEST_REQUIRE_DOCKER` IS SET it answers yes regardless, so the build runs and fails on
    the missing daemon rather than skipping (the policy of `one_live_preview._docker_and_compose`).
    """
    if os.environ.get("TEST_REQUIRE_DOCKER"):
        return True
    if not shutil.which("docker"):
        return False
    try:
        daemon = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                                capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return daemon.returncode == 0


def _sources() -> list[str]:
    """The context paths `docker/cli.Dockerfile`'s `COPY` instructions name, comments stripped."""
    found: list[str] = []
    for args in _COPY.findall(dockerfiles.instructions((ROOT / DOCKERFILE).read_text())):
        words = [w for w in args.split() if not w.startswith("--")]
        found.extend(words[:-1])
    return found


def _snapshot(directory: pathlib.Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir()) if p.is_file()}


@pytest.fixture
def checkout_extra_ca() -> Iterator[dict[str, bytes]]:
    """The checkout's `docker/extra-ca/` as it was before the test, for the test to compare with.

    AND THE THROWAWAY REMOVED FROM IT AFTERWARDS, whatever the test concluded: a helper that wrote
    it there (the mutation that proves the comparison) would otherwise leave a root that every
    later build on this machine trusts, behind a `.gitignore` that hides it."""
    before = _snapshot(ROOT / "docker/extra-ca")
    try:
        yield before
    finally:
        (ROOT / f"docker/extra-ca/{THROWAWAY}.crt").unlink(missing_ok=True)


def _build_context(dest: pathlib.Path, pem: str) -> pathlib.Path:
    """A copy of the CLI image's build context in `dest`, with `pem` added to its extra-ca.

    THE CHECKOUT'S OWN `*.crt` ARE COPIED TOO: on a machine behind TLS interception the person's
    root is already there, and without it the build's `pip install` would fail for a reason that is
    not this guard's."""
    for src in [*_sources(), DOCKERFILE, ".dockerignore"]:
        for path in ROOT.glob(src.rstrip("/")):  # `addon[s]` is a glob: absent from the public tree
            target = dest / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.is_dir():
                shutil.copytree(path, target, ignore=_ignored, dirs_exist_ok=True)
            else:
                shutil.copy2(path, target)
    (dest / "docker/extra-ca").mkdir(parents=True, exist_ok=True)
    (dest / f"docker/extra-ca/{THROWAWAY}.crt").write_text(pem)
    return dest


def _throwaway_root(tmp_path: pathlib.Path) -> str:
    """A REAL self-signed certificate. pip loads the whole bundle and refuses a malformed PEM, so a
    dummy body would turn this guard red for a reason that is not the defect."""
    if not shutil.which("openssl"):
        pytest.skip("openssl is not on PATH: no throwaway root certificate can be made here")
    key, cert = tmp_path / "throwaway.key", tmp_path / "throwaway.crt"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                    "-subj", f"/CN={THROWAWAY}", "-keyout", str(key), "-out", str(cert)],
                   check=True, capture_output=True, timeout=60)
    key.unlink()
    return cert.read_text()


def _pull_or_skip(image: str) -> None:
    pulled = subprocess.run(["docker", "pull", "-q", image], capture_output=True, text=True,
                            timeout=BUILD_TIMEOUT)
    if pulled.returncode != 0:
        why = f"{image} could not be pulled here, so the CLI image cannot be built:\n{pulled.stderr}"
        if os.environ.get("TEST_REQUIRE_DOCKER"):
            pytest.fail(why)
        pytest.skip(why)


def _in_image(tag: str, entrypoint: str, *args: str) -> str:
    ran = subprocess.run(["docker", "run", "--rm", "--entrypoint", entrypoint, tag, *args],
                         capture_output=True, text=True, timeout=120)
    assert ran.returncode == 0, f"{entrypoint} {args} failed in the image:\n{ran.stderr}"
    return ran.stdout.strip()


def test_the_build_context_is_a_copy_and_the_checkouts_extra_ca_is_left_as_it_was(
        tmp_path, checkout_extra_ca):
    """The guard's own hygiene, without docker: a PEM written into the checkout would be trusted by
    every later build on this machine, and `.gitignore` would hide it."""
    extra_ca, before = ROOT / "docker/extra-ca", checkout_extra_ca

    context = _build_context(tmp_path / "ctx", "-----BEGIN CERTIFICATE-----\nY29ycA==\n"
                                               "-----END CERTIFICATE-----\n")

    assert _snapshot(extra_ca) == before, "the checkout's docker/extra-ca/ was changed"
    assert "Y29ycA==" in (context / f"docker/extra-ca/{THROWAWAY}.crt").read_text()
    for name, body in before.items():
        assert (context / "docker/extra-ca" / name).read_bytes() == body, f"{name} was not carried"
    missing = [src for src in _sources()
               if any(ROOT.glob(src.rstrip("/"))) and not any(context.glob(src.rstrip("/")))]
    assert not missing, f"the copy lacks what the Dockerfile COPYs: {missing}"


@pytest.mark.slow
@pytest.mark.xdist_group("docker")
@pytest.mark.skipif(not _a_daemon_answers(), reason="no Docker daemon answers here")
def test_the_cli_image_builds_with_a_throwaway_root_and_pip_trusts_it(tmp_path, checkout_extra_ca):
    """Criteria 1 and 4: the build succeeds with a root present, and the file pip is pointed at
    holds that root beside the system's."""
    extra_ca, before = ROOT / "docker/extra-ca", checkout_extra_ca
    context = _build_context(tmp_path / "ctx", _throwaway_root(tmp_path))
    for image, _stage in dockerfiles.froms(ROOT / DOCKERFILE):
        _pull_or_skip(image)

    tag = f"openfactory-cli-guard-738-{uuid.uuid4().hex[:12]}"
    try:
        built = subprocess.run(["docker", "build", "--progress=plain", "-f",
                                str(context / DOCKERFILE), "-t", tag, str(context)],
                               capture_output=True, text=True, timeout=BUILD_TIMEOUT)
        assert built.returncode == 0, (
            f"the CLI image does not build with a root in docker/extra-ca/:\n{built.stderr[-3000:]}")

        # `pip config list`, NOT `pip config get global.cert`: `get` reads the user file alone and
        # answers "No such key" for /etc/pip.conf (pip 25.0.1); `list` is every file pip loads.
        listing = dict(line.split("=", 1) for line in
                       _in_image(tag, "pip", "config", "list").splitlines() if "=" in line)
        assert "global.cert" in listing, f"pip in the image has no cert configured: {listing}"
        cert = listing["global.cert"].strip("'\"")
        # LOADED AS pip's TLS LOADS IT: an `ssl` context from that file, listing what it trusts.
        listed = _in_image(tag, "python", "-c",
                           "import ssl, sys; c = ssl.create_default_context(cafile=sys.argv[1]); "
                           "r = c.get_ca_certs(); print(len(r)); "
                           "print(*[dict(x[0] for x in s['subject']).get('commonName', '') "
                           "for s in r], sep='\\n')",
                           cert)
        count, *names = listed.splitlines()
        assert THROWAWAY in names, f"pip's trust file {cert} does not hold the extra root"
        assert int(count) > 1, f"pip's trust file {cert} holds the extra root ALONE"
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, timeout=120)

    assert _snapshot(extra_ca) == before, "the checkout's docker/extra-ca/ was changed by the build"
