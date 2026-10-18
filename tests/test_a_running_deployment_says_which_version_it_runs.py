"""A running deployment says which version it runs, and what is installed into it (#681).

WHAT WAS MISSING. `openfactory.__version__` reached the evidence pack and the job records and no
API: a supervisor could not ask a running deployment which version it was, which image it ran from,
or which add-ons were installed into it — and add-ons join every axis from outside the tree, through
the `openfactory.adapters` entry-point group, so the answer is not the same as the core's.

THE RULES THIS FILE HOLDS, at `GET /api/v1/version`:

  · it answers the package's own version, the one the evidence pack records;
  · `image` is null outside an image, and inside one carries the stamp the image wrote and the digest
    the deployment names (`OPENFACTORY_IMAGE_DIGEST`);
  · `engine.address_kind` is the kind of address the engine is reached at, for every kind
    `view.ADDRESS_KINDS` names — and never the address;
  · `addons` is every row an installed distribution declares in the group, with its distribution,
    version, axis and kind — read from a real distribution on disk, and never loaded;
  · it is credentialed like the floor: no credential is a 401, and a product credential a 403.
"""

from __future__ import annotations

import sys
from importlib.metadata import entry_points

import pytest
from fastapi.testclient import TestClient

import openfactory
from openfactory import plugins
from openfactory.observability import health
from tests import stranger_addon


@pytest.fixture
def client(monkeypatch):
    for name in ("OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_PRODUCT_TOKEN",
                 "OPENFACTORY_PRODUCT_TOKENS", "OPENFACTORY_IDENTITY",
                 health.IMAGE_DIGEST_VARIABLE):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("openfactory.namespace.build_stamp", lambda: ("", ""))
    from openfactory.api.app import app

    return TestClient(app)


def _version(client) -> dict:
    answer = client.get(health.VERSION_PATH)
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_it_answers_the_packages_own_version(client):
    assert _version(client)["version"] == openfactory.__version__


# ── the image ───────────────────────────────────────────────────────────────────────────────────

def test_outside_an_image_there_is_no_image(client):
    assert _version(client)["image"] is None


def test_inside_an_image_it_says_the_stamp_and_the_digest_its_deployment_names(client,
                                                                               monkeypatch):
    monkeypatch.setattr("openfactory.namespace.build_stamp",
                        lambda: ("3f9a1c0e2b7d", "2026-10-19T08:00:00Z"))
    assert _version(client)["image"] == {"digest": None, "code": "3f9a1c0e2b7d",
                                         "built_at": "2026-10-19T08:00:00Z"}

    monkeypatch.setenv(health.IMAGE_DIGEST_VARIABLE, " sha256:0123abcd ")
    assert _version(client)["image"]["digest"] == "sha256:0123abcd"


# ── the engine ──────────────────────────────────────────────────────────────────────────────────

#: An address of each kind `view.ADDRESS_KINDS` names; `None` is nobody saying anything. A kind
#: added there without an example here fails `test_every_address_kind_is_answered`.
ADDRESSES = {
    "undeclared": None,
    "unreadable": "localhost:not-a-port",
    "cloud": "acme-prod.a1b2c.tmprl.cloud:7233",
    "local": "127.0.0.1:7233",
    "remote": "temporal.internal.example:7233",
}


@pytest.mark.parametrize("kind", sorted(ADDRESSES))
def test_every_address_kind_is_answered_and_never_the_address(client, monkeypatch, kind):
    from openfactory.runtime.temporal import view

    assert set(ADDRESSES) == set(view.ADDRESS_KINDS)
    for name in ("TEMPORAL_ADDRESS", "TEMPORAL_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    if ADDRESSES[kind] is not None:
        monkeypatch.setenv("TEMPORAL_ADDRESS", ADDRESSES[kind])

    answer = client.get(health.VERSION_PATH)

    assert answer.json()["engine"] == {"address_kind": kind}, answer.text
    if ADDRESSES[kind]:
        assert ADDRESSES[kind].split(":")[0] not in answer.text


def test_without_the_engines_client_the_kind_is_null(client, monkeypatch):
    import openfactory.runtime.temporal as engine

    monkeypatch.delattr(engine, "view", raising=False)
    monkeypatch.setitem(sys.modules, "openfactory.runtime.temporal.view", None)

    assert _version(client)["engine"] == {"address_kind": None}


# ── the add-ons ─────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def stranger(tmp_path, monkeypatch):
    """The stranger's distribution, installed on disk — and NOT imported."""
    monkeypatch.syspath_prepend(str(stranger_addon.write_distribution(tmp_path)))
    monkeypatch.delitem(sys.modules, "acme_addons", raising=False)
    monkeypatch.setattr(plugins, "_cache", None)


def test_every_row_an_installed_distribution_declares_is_listed_unloaded(client, stranger):
    listed = _version(client)["addons"]

    for name in stranger_addon.ENTRY_POINTS:
        axis, _, kind = name.partition(".")
        assert {"distribution": "acme-addons", "version": "0.1", "axis": axis,
                "kind": kind} in listed, (name, listed)
    assert "acme_addons" not in sys.modules, "the version route imported a stranger's code"


def test_the_list_is_the_group_and_nothing_else(client, stranger):
    """Every row listed is an entry point of the group, and every well-formed one is listed."""
    declared = {(p.name, p.dist.name) for p in entry_points(group=plugins.GROUP) if "." in p.name}
    listed = {(f'{r["axis"]}.{r["kind"]}', r["distribution"]) for r in _version(client)["addons"]}

    assert listed == declared


def test_a_name_that_is_no_row_is_not_listed(client, monkeypatch):
    class _Dist:
        name, version = "acme-odd", "2.0"

    class _Point:
        def __init__(self, name):
            self.name, self.dist = name, _Dist()

        def load(self):
            raise AssertionError("listed by loading it")

    monkeypatch.setattr("importlib.metadata.entry_points",
                        lambda group=None: [_Point("forge.acme"), _Point("nodot")]
                        if group == plugins.GROUP else [])

    assert _version(client)["addons"] == [{"distribution": "acme-odd", "version": "2.0",
                                           "axis": "forge", "kind": "acme"}]


def test_a_metadata_store_that_cannot_be_read_lists_nothing_and_answers(client, monkeypatch):
    def _broken(group=None):
        raise OSError("the metadata store is corrupt")

    monkeypatch.setattr("importlib.metadata.entry_points", _broken)

    assert _version(client)["addons"] == []


# ── the credential ──────────────────────────────────────────────────────────────────────────────

def test_it_is_credentialed_like_the_floor(client, monkeypatch):
    from openfactory import actions
    from openfactory.api.app import _scope_of_path

    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", "the-operator")
    monkeypatch.setenv("OPENFACTORY_PRODUCT_TOKENS", "the-analyst:bia")

    assert _scope_of_path(health.VERSION_PATH) == actions.FLOOR
    assert client.get(health.VERSION_PATH).status_code == 401
    assert client.get(health.VERSION_PATH,
                      headers={"Authorization": "Bearer the-analyst"}).status_code == 403
    assert client.get(health.VERSION_PATH,
                      headers={"Authorization": "Bearer the-operator"}).status_code == 200


def test_it_declares_the_shape_it_answers_in(client):
    from fastapi.routing import APIRoute

    from openfactory.api import read_models
    from openfactory.api.app import app

    route = next(r for r in app.routes
                 if isinstance(r, APIRoute) and r.path == health.VERSION_PATH)
    assert route.response_model is read_models.VersionRead
    assert set(read_models.VersionRead.model_fields) == set(_version(client))
