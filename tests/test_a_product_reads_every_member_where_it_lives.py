"""On the local row, a product reads each of its projects' code where that project lives.

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, #664). Three local projects, `reservas-web`,
`reservas-api` and `reservas-core`, each registered with its own `repo_path`, were one product
through one context repository. Onboarding said:

    ✗ could not clone reservas-api: fatal: repository '~/.openfactory/context/reservas-api.git'
    does not exist

and every conversation turn on `reservas-web` logged `sparse sync failed for
reservas-web--source--reservas-api`. The product role told the owner it could not open the code of
`reservas-api` and `reservas-core`. The local forge answered every short name that was not its own
project as a repository the installation owns, so a sibling member was looked for in the context
repositories' directory.

THE RULE THIS FILE HOLDS, for a product of one project and a product of several:
  1. every project reads every project of its product at that project's own `repo_path`, through
     the forge the readers ask (`build_forge(project).clone_url`);
  2. a registered project that is not of this product is never read as a member: the isolation
     between products holds on one machine as it does on a hosted forge;
  3. a context repository is still the installation's own, and a URL is still untouched;
  4. a registry that cannot be read answers as before, and says so in the log.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from openfactory import namespace
from openfactory.adapters.forge.registry import build_forge
from openfactory.contracts.product import ProductConfig
from openfactory.contracts.project import Project
from openfactory.registry import ProjectRegistry
from tests.product_shapes import ProductShape
from tests.product_shapes import product_shape as product_shape  # noqa: F401 — the fixture


def _git(where: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True,
                          check=True)


def _repository(where: Path, marker: str) -> Path:
    where.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(where)], check=True)
    (where / f"{marker}.txt").write_text(f"{marker}\n")
    _git(where, "-c", "user.email=a@b.c", "-c", "user.name=a", "add", "-A")
    _git(where, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", marker)
    return where


@pytest.fixture
def registered(product_shape: ProductShape, tmp_path) -> dict[str, Path]:
    """Every member of the shape registered on the local row, each a repository of its own."""
    registry = ProjectRegistry()
    paths = {}
    for member in product_shape.members:
        paths[member] = _repository(tmp_path / "repos" / member, member)
        registry.add(product_shape.project(member, repo_path=str(paths[member])))
    return paths


def _forge(shape: ProductShape, member: str, registered: dict[str, Path]):
    return build_forge(ProjectRegistry().get(member))


# ── 1. every member, where it lives ─────────────────────────────────────────────────────────────

def test_TODAYS_RUN_every_member_reads_every_member_where_it_lives(product_shape, registered,
                                                                  tmp_path):
    for reader in product_shape.members:
        forge = _forge(product_shape, reader, registered)
        for member, where in registered.items():
            url = forge.clone_url(member)

            assert url == str(where), (reader, member, url)
            clone = tmp_path / "clones" / reader / member
            subprocess.run(["git", "clone", "-q", url, str(clone)], check=True,
                           capture_output=True, text=True)
            assert (clone / f"{member}.txt").exists(), (reader, member)


# ── 2. the isolation between products ───────────────────────────────────────────────────────────

def test_a_project_of_another_product_is_never_read_as_a_member(product_shape, registered,
                                                                 tmp_path):
    outsider = _repository(tmp_path / "repos" / "outsider", "outsider")
    ProjectRegistry().add(Project(
        name="outsider", repo_path=str(outsider), tracker={"kind": "local", "repo": "outsider"},
        forge={"kind": "local", "repo": "outsider"},
        product=ProductConfig(docs_repo="another-context")))
    loner = _repository(tmp_path / "repos" / "loner", "loner")
    ProjectRegistry().add(Project(
        name="loner", repo_path=str(loner), tracker={"kind": "local", "repo": "loner"},
        forge={"kind": "local", "repo": "loner"}))

    for reader in product_shape.members:
        forge = _forge(product_shape, reader, registered)

        assert forge.clone_url("outsider") != str(outsider), reader
        assert forge.clone_url("loner") != str(loner), reader


def test_a_member_on_a_hosted_row_is_not_read_as_a_path_on_this_machine(product_shape, registered,
                                                                        tmp_path):
    """Its `repo_path` is a checkout somebody keeps, not the repository its forge holds."""
    hosted = product_shape.hosted()
    checkout = _repository(tmp_path / "repos" / "hosted-member", "hosted-member")
    ProjectRegistry().add(hosted.project("hosted-member", repo_path=str(checkout)).model_copy(
        update={"product": ProductConfig(docs_repo=product_shape.docs_repo)}))

    for reader in product_shape.members:
        assert _forge(product_shape, reader, registered).clone_url("hosted-member") != str(
            checkout), reader


# ── 3. what was right stays right ───────────────────────────────────────────────────────────────

def test_the_context_repository_is_still_the_installations_own(product_shape, registered):
    for reader in product_shape.members:
        forge = _forge(product_shape, reader, registered)

        assert forge.clone_url(product_shape.context) == str(
            namespace.operator_path(f"context/{product_shape.context}.git"))
        assert forge.clone_url("https://example.com/x.git") == "https://example.com/x.git"
        assert forge.clone_url("") == str(registered[reader])


# ── 4. a registry that cannot be read ───────────────────────────────────────────────────────────

def test_a_registry_that_cannot_be_read_answers_as_before_and_says_so(caplog, tmp_path,
                                                                     monkeypatch):
    from openfactory.adapters.forge.local import LocalForge

    broken = tmp_path / "broken.yaml"
    broken.write_text("projects: [this is: not a mapping\n")
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(broken))
    forge = LocalForge("reservas-web", str(tmp_path / "web"))

    with caplog.at_level(logging.WARNING):
        url = forge.clone_url("reservas-api")

    assert url == str(namespace.operator_path("context/reservas-api.git"))
    assert "OPENFACTORY_LOCAL_FORGE_MEMBERS_UNREAD" in caplog.text
