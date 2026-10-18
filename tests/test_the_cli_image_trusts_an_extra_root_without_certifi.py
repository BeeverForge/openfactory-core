"""#738: the CLI image's extra-CA step must work in the image it runs in, which has no `certifi`.

`docker/cli.Dockerfile` appended `docker/extra-ca/*.crt` to `$(python -c 'import certifi;
print(certifi.where())')` and wrote that path into `/etc/pip.conf`. At that point the image is a
bare `python:3.12-slim`, and `import certifi` fails there (measured 2026-10-17: Debian 13, Python
3.12.15, pip 25.0.1, `ModuleNotFoundError`). The substitution came back empty, the redirection to
`""` failed under `set -eu`, and the layer exited 2 — so the CLI image could not be built by anybody
who had put a root in `docker/extra-ca/`. Without a root the branch never ran, which is why the
release never saw it.

WHY THIS GUARD EXECUTES THE BLOCK, as `test_the_extra_ca_file_is_always_a_valid_pem.py` does: a
guard that read the Dockerfile would be satisfied by the comment explaining the defect. So this
runs the real `RUN` script under `sh` with its paths rebased into a sandbox and reads what it wrote.

THE SANDBOX STANDS FOR THE BASE IMAGE, and that is why `python` and `python3` are stubs first on
`PATH` that fail as the base image's `import certifi` does. It is also what keeps this test from
appending its certificate to the venv's real `certifi/cacert.pem`, which the old block would do on
any host whose Python has `certifi`.
"""

from __future__ import annotations

import configparser
import pathlib
import subprocess

from dockerfiles import instructions

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "docker/cli.Dockerfile"

STORE = "/etc/ssl/certs/ca-certificates.crt"
SYSTEM_PEM = "-----BEGIN CERTIFICATE-----\nc3lzdGVt\n-----END CERTIFICATE-----\n"
CORP_PEM = "-----BEGIN CERTIFICATE-----\nY29ycA==\n-----END CERTIFICATE-----\n"


def _trust_step() -> str:
    """The first `RUN` after `COPY docker/extra-ca/ /tmp/extra-ca/`, un-continued into one line.

    Found by ORDER, not by a string inside it, so a fix that renames a staging file cannot make
    the guard aim at nothing. Joined with a space, not a newline: `\\<newline>` collapses to nothing
    in sh (see `_blocks` in the sibling test)."""
    lines = instructions(DOCKERFILE.read_text()).splitlines()
    copies = [i for i, line in enumerate(lines)
              if line.strip() == "COPY docker/extra-ca/ /tmp/extra-ca/"]
    assert len(copies) == 1, f"cli.Dockerfile copies docker/extra-ca/ {len(copies)} times, not once"
    i = copies[0] + 1
    while not lines[i].startswith("RUN "):
        assert not lines[i].startswith(("FROM ", "COPY ")), "no RUN follows the extra-ca COPY"
        i += 1
    body = [lines[i][4:]]
    while body[-1].rstrip().endswith("\\"):
        i += 1
        body.append(lines[i])
    return " ".join(b.strip().removesuffix("\\") for b in body)


def _run(tmp_path: pathlib.Path, *, with_extra_cert: bool, with_store: bool = True):
    """Execute the real step with every absolute path rebased under `tmp_path/root`."""
    root = tmp_path / "root"
    (root / "etc/ssl/certs").mkdir(parents=True)
    (root / "tmp/extra-ca").mkdir(parents=True)
    if with_store:
        (root / STORE.lstrip("/")).write_text(SYSTEM_PEM)
    if with_extra_cert:
        (root / "tmp/extra-ca/corp.crt").write_text(CORP_PEM)

    # THE BASE IMAGE'S PYTHON, which has no certifi. Recorded, so a step that reaches for it is seen.
    called = tmp_path / "python-called"
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name in ("python", "python3"):
        stub = stubs / name
        stub.write_text(f'#!/bin/sh\necho "$@" >> {called}\n'
                        "echo \"ModuleNotFoundError: No module named 'certifi'\" >&2\nexit 1\n")
        stub.chmod(0o755)

    rebased = (_trust_step()
               .replace("/usr/local/share/openfactory", f"{root}/usr/local/share/openfactory")
               .replace("/etc/ssl/certs", f"{root}/etc/ssl/certs")
               .replace("/etc/pip.conf", f"{root}/etc/pip.conf")
               .replace("/tmp/extra-ca", f"{root}/tmp/extra-ca"))
    proc = subprocess.run(["sh", "-c", rebased], capture_output=True, text=True,
                          env={"PATH": f"{stubs}:/usr/bin:/bin", "HOME": str(tmp_path),
                               "LC_ALL": "C"})
    return proc, root, called


def _file_pip_reads(root: pathlib.Path) -> pathlib.Path:
    """The file `/etc/pip.conf`'s `[global] cert` names, as pip reads it — never a path assumed."""
    conf = configparser.ConfigParser()
    conf.read(root / "etc/pip.conf")
    return pathlib.Path(conf["global"]["cert"])


def test_with_an_extra_root_the_file_pip_is_pointed_at_holds_it(tmp_path):
    """Criterion 1: with a certificate, the step succeeds and pip's trust file contains it."""
    proc, root, _ = _run(tmp_path, with_extra_cert=True)

    assert proc.returncode == 0, f"the trust step failed:\n{proc.stdout}\n{proc.stderr}"
    assert (root / "etc/pip.conf").is_file(), "no /etc/pip.conf was written: pip trusts nothing new"
    assert "Y29ycA==" in _file_pip_reads(root).read_text(), (
        "the file pip.conf names does not hold the extra root")


def test_the_file_pip_is_pointed_at_keeps_the_system_roots(tmp_path):
    """Criterion 1, the other half: pip given the extra root ALONE would trust nothing else."""
    proc, root, _ = _run(tmp_path, with_extra_cert=True)

    assert proc.returncode == 0, f"the trust step failed:\n{proc.stdout}\n{proc.stderr}"
    assert "c3lzdGVt" in _file_pip_reads(root).read_text(), (
        "the file pip.conf names lost the system roots: pip would trust the extra root alone")


def test_the_trust_step_never_runs_python(tmp_path):
    """Criterion 3: the step imports no `certifi` — the base image has none to import."""
    proc, _, called = _run(tmp_path, with_extra_cert=True)

    assert not called.exists(), (
        f"the trust step ran python ({called.read_text().strip()!r}), which in python:3.12-slim "
        f"has no certifi; exit {proc.returncode}:\n{proc.stderr}")


def test_with_no_extra_root_no_pip_conf_is_written_and_the_store_is_unchanged(tmp_path):
    """Criterion 2 — preservation, so green on main by design: the public build, every time."""
    proc, root, _ = _run(tmp_path, with_extra_cert=False)

    assert proc.returncode == 0, f"the trust step failed:\n{proc.stdout}\n{proc.stderr}"
    assert not (root / "etc/pip.conf").exists(), "a pip.conf was written with no extra root"
    assert (root / STORE.lstrip("/")).read_text() == SYSTEM_PEM, "the system store was changed"


def test_a_missing_system_store_is_refused_by_name_not_created_with_one_root(tmp_path):
    """Criterion 3, "known to carry" checked rather than assumed: `>>` onto a missing store would
    CREATE one holding the extra root alone, and pip pointed at it would trust nothing else."""
    proc, root, _ = _run(tmp_path, with_extra_cert=True, with_store=False)

    assert proc.returncode != 0, "the step succeeded with no system store to join"
    assert f"{root}{STORE}" in proc.stdout + proc.stderr, (
        f"the refusal does not name the store it needed:\n{proc.stdout}\n{proc.stderr}")
    assert not (root / STORE.lstrip("/")).exists(), "a store holding only the extra root was created"
