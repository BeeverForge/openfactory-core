"""The typed reads are served under `/api/v1`, and the API's description is committed (#678, b).

Slice a gave every read a front end makes a declared model. A front end of one's own builds on
those shapes, so they get an address that says which version of them it reads — `/api/v1/…` —
and a description it can read without running the core: `docs/reference/openapi.json`.

WHAT IS PROVEN HERE:

  · every read that declares a model is served under `/api/v1/…` by the same handler and model,
    and its unversioned path stays, marked `deprecated` in the description the app generates;
  · the committed description is the one the app generates, `info.version` the package's own, and
    a test that finds them apart says the command that writes it again;
  · a versioned path belongs to the same area as its alias, at the gate;
  · EVERY `GET` UNDER `/api/` IS ONE OF THOSE READS, OR A ROUTE THE CONTRACT NAMES AS LEFT OUT OF
    `/api/v1/` WITH ITS REASON (#940) — and a route left out has no `/api/v1/` form, at the router
    or at the gate.

That both forms answer the same body is proven, route by route, with a populated bench, in
`tests/test_the_read_routes_declare_their_model.py`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

import openfactory
from tests.test_the_front_end_api_is_a_contract import _left_out

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / "docs" / "reference" / "openapi.json"


def _typed_reads() -> dict[str, APIRoute]:
    """Every GET route under `/api/` that declares a Pydantic model, by path — not one whose
    `-> dict` FastAPI reads as a model of `dict`."""
    from openfactory.api.app import app

    return {r.path: r for r in app.routes
            if isinstance(r, APIRoute) and r.path.startswith("/api/")
            and "GET" in (r.methods or set()) and isinstance(r.response_model, type)
            and issubclass(r.response_model, BaseModel)}


def _unversioned() -> dict[str, APIRoute]:
    return {p: r for p, r in _typed_reads().items() if not p.startswith("/api/v1/")}


def test_there_are_typed_reads_to_version():
    assert len(_unversioned()) >= 18, sorted(_unversioned())


def test_every_typed_read_is_served_under_api_v1_by_the_same_handler():
    reads = _typed_reads()
    for path, alias in _unversioned().items():
        versioned = reads.get("/api/v1" + path.removeprefix("/api"))
        assert versioned is not None, f"{path} has no /api/v1 form"
        assert versioned.endpoint is alias.endpoint, path
        assert versioned.response_model is alias.response_model, path


def _gets() -> dict[str, APIRoute]:
    from openfactory.api.app import app

    return {r.path: r for r in app.routes if isinstance(r, APIRoute)
            and r.path.startswith("/api/") and "GET" in (r.methods or set())}


def test_every_read_is_typed_or_named_as_left_out():
    """#940 found seven reads the default front end made that declared no model and were not under
    `/api/v1/`, and nothing said whether they would be. A `GET` under `/api/` declares its model —
    and is then served under `/api/v1/`, as above — or is a row of the contract's list of the reads
    left out of it, which says why."""
    typed, left_out = _typed_reads(), _left_out()
    assert sorted(set(_gets()) - set(typed) - set(left_out)) == [], (
        "GET routes that declare no model and that the contract does not name as left out")


def test_a_read_left_out_is_a_route_that_declares_no_model_and_says_why():
    gets, typed = _gets(), _typed_reads()
    assert _left_out(), "the contract's list of reads left out of /api/v1 was not found"
    for path, why in _left_out().items():
        assert path in gets, f"{path} is named as left out of /api/v1 and is no GET route"
        assert path not in typed, f"{path} declares its model: it is under /api/v1, not left out"
        assert why.strip(" -"), f"{path} is left out of /api/v1 and the contract does not say why"


def test_a_read_left_out_has_no_api_v1_form_and_borrows_no_area():
    """A read left out is not served under `/api/v1/`, and the gate does not read its `/api/v1/`
    form as its alias: that address keeps its own area and is not found (#764's review)."""
    from openfactory.api.app import _unversioned as as_alias
    from openfactory.api.app import app

    served = {getattr(r, "path", "") for r in app.routes}
    for path in _left_out():
        versioned = "/api/v1" + path.removeprefix("/api")
        assert versioned not in served, f"{path} is named as left out and is served at {versioned}"
        concrete = re.sub(r"\{[^}]+\}", "x", versioned)
        assert as_alias(concrete) == concrete, f"the gate reads {concrete} as {path}'s"


def test_only_the_unversioned_alias_is_deprecated():
    for path, route in _typed_reads().items():
        assert bool(route.deprecated) is (not path.startswith("/api/v1/")), (path, route.deprecated)


def test_the_generated_document_marks_the_aliases_deprecated():
    from openfactory.api.openapi import document

    paths = document()["paths"]
    for path in _unversioned():
        assert paths[path]["get"].get("deprecated") is True, path
        assert "deprecated" not in paths["/api/v1" + path.removeprefix("/api")]["get"], path


def test_the_document_says_the_package_version():
    from openfactory.api.app import app

    assert json.loads(COMMITTED.read_text(encoding="utf-8"))["info"]["version"] == (
        openfactory.__version__)
    served = TestClient(app).get("/openapi.json").json()
    assert served["info"]["version"] == openfactory.__version__


def test_the_committed_document_is_the_one_the_app_generates():
    from openfactory.api.openapi import COMMAND, render

    committed = COMMITTED.read_text(encoding="utf-8") if COMMITTED.exists() else ""
    assert committed == render(), (
        f"{COMMITTED.relative_to(ROOT)} is not what the app generates. "
        f"Install the pinned fastapi and pydantic (`make install` applies constraints.txt), "
        f"then write it again with:\n\n    {COMMAND}\n")


def test_the_document_does_not_carry_the_deployments_name(monkeypatch):
    """`OPENFACTORY_PLATFORM_NAME` names a deployment's own panel; the committed description is the
    core's, the same on every machine that generates it."""
    from openfactory.api import app as api
    from openfactory.api.openapi import document

    monkeypatch.setattr(api.app, "title", "Acme Factory")
    monkeypatch.setattr(api.app, "openapi_schema", None)
    assert document()["info"]["title"] == "OpenFactory"


def test_the_command_writes_the_document(tmp_path):
    from openfactory.api.openapi import main, render

    target = tmp_path / "openapi.json"
    assert main([str(target)]) == 0
    assert target.read_text(encoding="utf-8") == render()


# ── the gate reads a versioned path as its alias ────────────────────────────────────────────────

@pytest.mark.parametrize(("path", "area"), [
    ("/api/v1/whoami", None),
    ("/api/v1/product/projects", "product"),
    ("/api/v1/product/x/documents", "product"),
    ("/api/v1/floor", "floor"),
    ("/api/v1/board/x", "floor"),
    ("/api/v1/projects", "floor"),
    ("/api/v1/preview/x/12", None),
])
def test_a_versioned_path_is_in_its_aliases_area(path, area):
    from openfactory.api.app import _scope_of_path

    assert _scope_of_path(path) == area
    assert _scope_of_path(path.replace("/api/v1/", "/api/", 1)) == area


def test_every_registered_typed_read_is_mapped_to_its_alias():
    from openfactory.api.app import _unversioned as as_alias

    for path in _unversioned():
        concrete = path.replace("{", "").replace("}", "")   # `/api/board/project`
        assert as_alias("/api/v1" + concrete.removeprefix("/api")) == concrete, path


@pytest.mark.parametrize("path", [
    "/api/v1/nothing-registered",
    "/api/v1/whoami/more",
    "/api/v1/product/x",
    "/api/v1/board/x/y",
    "/api/v1/",
])
def test_an_unregistered_versioned_path_is_not_mapped(path):
    """Only a typed read registered under `/api/v1` borrows its alias's area: any other path keeps
    its own address, so it cannot inherit an area by sharing a prefix with one."""
    from openfactory.api.app import _unversioned as as_alias

    assert as_alias(path) == path


def test_an_unregistered_versioned_path_is_not_found(gated):
    assert gated.get("/api/v1/nothing-registered",
                     headers={"Authorization": "Bearer the-operator"}).status_code == 404


@pytest.fixture
def gated(monkeypatch):
    for var in ("OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_PRODUCT_TOKEN", "OPENFACTORY_IDENTITY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", "the-operator")
    monkeypatch.setenv("OPENFACTORY_PRODUCT_TOKENS", "the-analyst:bia")
    from openfactory.api.app import app

    return TestClient(app)


def test_a_product_credential_is_refused_the_versioned_floor_and_reads_whoami(gated):
    analyst = {"Authorization": "Bearer the-analyst"}

    floor = gated.get("/api/v1/floor", headers=analyst)
    assert floor.status_code == 403, floor.text
    assert floor.json()["detail"].startswith("this credential is scoped to product")
    assert gated.get("/api/v1/whoami", headers=analyst).status_code == 200
    assert gated.get("/api/v1/floor").status_code == 401


def test_the_product_owners_board_is_read_at_its_versioned_path(monkeypatch):
    from openfactory import actions
    from openfactory.api import app as api

    class _Registry:
        def get(self, name):
            if name != "acme":
                raise KeyError(name)
            return object()

    monkeypatch.setattr(api, "ProjectRegistry", _Registry)
    monkeypatch.setattr(api, "_has_product_role", lambda _p: True)
    product = {actions.PRODUCT}

    assert api._the_product_owners_board("/api/v1/board/acme", product)
    assert not api._the_product_owners_board("/api/v1/board/acme", product, "pr=3")
    assert not api._the_product_owners_board("/api/v1/board/other", product)
