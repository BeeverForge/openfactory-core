"""`openfactory init`'s closing line names a command the person reading it can run — #652.

THE LINE THAT SHIPPED, through the installer, on every fresh install from v0.5.0 to v0.6.0-rc.2:

    then: `docker compose --env-file /out/.env.compose up -d --build`

`/out` is where `install.sh` mounts the installation directory INSIDE the CLI container, so no
shell on the host has it; and `--build` builds `docker/worker.Dockerfile`, which an installation
from published images does not have (the release ships `docker-compose.yml`, the template and the
checksums, nothing else). Two lines further down the installer printed its own, correct command.

THE `/out` OF THE TESTS IS THE WORKING DIRECTORY. A test machine cannot write `/out`; the image's
`WORKDIR` is the mount (`docker/cli.Dockerfile`), so a working directory with the destination
passed as an absolute path inside it is exactly the shape `--out /out/.env.compose` has there.

READ AS A LINE. The `✓ wrote …` line legitimately names the destination, so "the path is not
anywhere in the output" would be the wrong question; the `then:` line is the one that is a command.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest
from typer.testing import CliRunner

from openfactory.cli import app

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _vendor_flags() -> list[str]:
    """The answers the installer's own end-to-end run gives, read out of it rather than copied."""
    e2e = (ROOT / "scripts" / "e2e-in-container.sh").read_text()
    supplied = e2e.split("set -- \"$@\" --", 1)[1].split("\n\n")[0]
    return [w for w in supplied.replace("\\\n", " ").split() if w]


@pytest.fixture
def by_hand(tmp_path, monkeypatch):
    """No installer, and a work directory of the test's own so no real `$HOME` is touched."""
    monkeypatch.delenv("OPENFACTORY_INSTALLER", raising=False)
    monkeypatch.setenv("OPENFACTORY_WORK_DIR", str(tmp_path / "work"))
    return tmp_path


def _an_installation_directory(root: pathlib.Path) -> pathlib.Path:
    """What the release leaves in a directory: the tracked compose file verbatim (ADR-0043 §2) and
    no `docker/`, so nothing in it can build."""
    where = root / "installation"
    where.mkdir()
    shutil.copy(ROOT / "docker-compose.yml", where / "docker-compose.yml")
    return where


def _then(*args: str) -> str | None:
    result = CliRunner().invoke(app, ["init", *args, "--runtime", "compose", *_vendor_flags()])
    assert result.exit_code == 0, result.output
    lines = [ln.strip() for ln in result.output.splitlines() if ln.strip().startswith("then:")]
    return lines[-1] if lines else None


@pytest.mark.parametrize("declared", ["installer", "by hand"])
def test_the_installers_destination_and_a_published_version_name_neither_out_nor_build(
        by_hand, monkeypatch, declared):
    """The criterion as the issue words it: the installer's `/out` destination and a published
    version. Run by the installer there is no `then:` line at all — the installer starts the stack
    itself, or under `--no-run` prints its own command; by hand the line may stay, without either."""
    where = _an_installation_directory(by_hand)
    monkeypatch.chdir(where)
    monkeypatch.setenv("OPENFACTORY_VERSION", "v0.6.0")
    if declared == "installer":
        monkeypatch.setenv("OPENFACTORY_INSTALLER", "1")
    dest = where / ".env.compose"

    line = _then("--out", str(dest))

    if declared == "installer":
        assert line is None, f"run by the installer, init still names a next command: {line}"
    else:
        assert line is None or (str(dest) not in line and "--build" not in line), line


def test_a_destination_inside_the_working_directory_is_named_from_there(by_hand, monkeypatch):
    """The README's by-hand path: `docker run … -v "$PWD:/out" … init --out /out/.env.compose`.
    The mount is the working directory, so the file is named from it — the same command the README
    prints two lines later, and the one compose runs from where it reads `docker-compose.yml`."""
    where = _an_installation_directory(by_hand)
    monkeypatch.chdir(where)

    line = _then("--out", str(where / ".env.compose"))

    assert line == "then: `docker compose --env-file .env.compose up -d`"


def test_a_working_directory_reached_through_a_symlink_still_names_the_file_from_there(
        by_hand, monkeypatch):
    """macOS keeps `/tmp` and the temporary directories behind `/private`: the working directory
    the process reports is the resolved one, the path the person passed is not."""
    where = _an_installation_directory(by_hand)
    link = by_hand / "link"
    link.symlink_to(where, target_is_directory=True)
    monkeypatch.chdir(link)

    line = _then("--out", str(link / ".env.compose"))

    assert line == "then: `docker compose --env-file .env.compose up -d`"


def test_a_destination_outside_the_working_directory_is_named_as_it_was_passed(
        by_hand, monkeypatch):
    """`~` is the person's own word for the path; expanded, it is a path they did not type."""
    where = _an_installation_directory(by_hand)
    monkeypatch.chdir(where)
    monkeypatch.setenv("HOME", str(by_hand / "home"))

    line = _then("--out", "~/elsewhere/.env.compose")

    assert line is not None and "--env-file ~/elsewhere/.env.compose " in line, line


def test_an_installation_from_published_images_is_told_up_d_alone(by_hand, monkeypatch):
    where = _an_installation_directory(by_hand)
    monkeypatch.chdir(where)

    line = _then()

    assert line is not None and line.endswith("up -d`") and "--build" not in line, line


def test_a_checkout_that_builds_its_images_is_told_to_build(by_hand, monkeypatch):
    """GREEN ON MAIN, ON PURPOSE: the half that must not be lost. A contributor standing in this
    checkout builds the worker from `docker/worker.Dockerfile`, so `--build` is right there. The
    destination is outside the checkout, so nothing is written into it."""
    monkeypatch.chdir(ROOT)

    line = _then("--out", str(by_hand / ".env.compose"))

    assert line is not None and " --build`" in line, line


def test_no_compose_file_in_the_working_directory_is_not_a_checkout(by_hand, monkeypatch):
    where = by_hand / "empty"
    where.mkdir()
    monkeypatch.chdir(where)

    line = _then()

    assert line is not None and "--build" not in line, line
