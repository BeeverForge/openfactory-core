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
  · every JSON read under `/api/` is typed, or named in the contract as deliberately unversioned
    with its reason (#940) — a new untyped read fails here until it is one or the other.

That both forms answer the same body is proven, route by route, with a populated bench, in
`tests/test_the_read_routes_declare_their_model.py`.
"""

from __future__ import annotations

import json
import re
import typing
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.responses import Response

import openfactory

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / "docs" / "reference" / "openapi.json"
CONTRACT = ROOT / "docs" / "reference" / "the-front-end-api.md"


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
    ("/api/v1/address", "floor"),
    ("/api/v1/coordinator/messages", "floor"),
    ("/api/v1/promote/x/1", "floor"),
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
    "/api/v1/factory/x",
    "/api/v1/jobs/x/1/events",
    "/api/v1/preview/x/y",
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


# ── every JSON read is typed, or named as deliberately unversioned (#940) ───────────────────────

def _untyped_json_reads(app: FastAPI) -> set[str]:
    """Every `GET` route under `/api/` that answers JSON and declares no Pydantic model. A route
    answers JSON unless its handler says it returns a `Response` — a stream, or a file's bytes."""
    found = set()
    for r in app.routes:
        if not (isinstance(r, APIRoute) and r.path.startswith("/api/")
                and "GET" in (r.methods or set())):
            continue
        if isinstance(r.response_model, type) and issubclass(r.response_model, BaseModel):
            continue
        answers = typing.get_type_hints(r.endpoint).get("return")
        if isinstance(answers, type) and issubclass(answers, Response):
            continue
        found.add(r.path)
    return found


def _named_unversioned() -> set[str]:
    """The paths the contract names as deliberately unversioned, one row each."""
    text = CONTRACT.read_text(encoding="utf-8")
    listed = text.split("<!-- unversioned:start -->")[1].split("<!-- unversioned:end -->")[0]
    return {m.group(1) for line in listed.splitlines()
            if (m := re.match(r"\|\s*`(/api/[^`]+)`\s*\|", line))}


def test_every_json_read_is_typed_or_named_unversioned():
    """Equal, not a subset: an untyped read the contract does not name fails, and so does a name
    the contract keeps for a read that has since been typed or removed."""
    from openfactory.api.app import app

    assert _untyped_json_reads(app) == _named_unversioned()


def test_the_guard_reports_an_untyped_json_read():
    scratch = FastAPI()

    @scratch.get("/api/new-read")
    def new_read() -> dict:
        return {}

    @scratch.get("/api/typed")
    def typed() -> BaseModel:
        return BaseModel()

    @scratch.get("/api/file")
    def file() -> Response:
        return Response(b"")

    assert _untyped_json_reads(scratch) == {"/api/new-read"}


def test_every_named_unversioned_read_says_why():
    text = CONTRACT.read_text(encoding="utf-8")
    listed = text.split("<!-- unversioned:start -->")[1].split("<!-- unversioned:end -->")[0]
    for line in listed.splitlines():
        if re.match(r"\|\s*`/api/", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            assert len(cells) == 2 and len(cells[1]) > 20, f"no reason given: {line}"
