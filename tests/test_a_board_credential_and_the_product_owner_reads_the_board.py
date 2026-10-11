"""A credential for the board and nothing else, and the product owner reads the board (#562, the
API's half).

Decided on 2026-10-08 and refined on 2026-10-11:

  - the product owner reaches the board of their projects, READ ONLY, with the credential they
    hold — a product credential was refused `GET /api/board/<project>` like the rest of the floor;
  - whoever runs the board does not reach the product owner — and the only credential limited to
    the floor came from an identity provider's group, so the token variables and `people invite`
    could issue "everything" or "the product area" and nothing in between;
  - the panel token stays the administrator's, and reaches both.

So `OPENFACTORY_BOARD_TOKENS` / `OPENFACTORY_BOARD_TOKEN` and `people invite --board` issue a board
credential (the floor's group), which the gate refuses the product area by name; and a product
credential reads `/api/board/<project>` for a project with a product role.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from openfactory.identity.local import (
    BOARD_GROUP,
    BOARD_PEOPLE_ENV,
    BOARD_SHARED_ENV,
    PEOPLE_ENV,
    PRODUCT_GROUP,
    PRODUCT_PEOPLE_ENV,
    PRODUCT_SHARED_ENV,
    SHARED_ENV,
    LocalIdentity,
)
from tests.test_a_person_is_invited_not_signed_up import local  # noqa: F401 — the fixture

OPERATOR, ANALYST, BOARD = "Bearer op-secret", "Bearer ba-secret", "Bearer bd-secret"


# ── the credential ──────────────────────────────────────────────────────────────────────────────

def test_a_board_row_is_a_person_scoped_to_the_floor():
    who = LocalIdentity(env={BOARD_PEOPLE_ENV: "bd-secret:leo:Leo"}).identify(credential="bd-secret")

    assert (who.id, who.display, who.groups) == ("leo", "Leo", (BOARD_GROUP,)), who


def test_the_shared_board_token_is_anonymous_and_still_scoped():
    who = LocalIdentity(env={BOARD_SHARED_ENV: "bd-shared"}).identify(credential="bd-shared")

    assert who.id == "" and who.groups == (BOARD_GROUP,), who


def test_a_token_in_both_a_product_and_a_board_row_is_the_product_credential():
    env = {PRODUCT_PEOPLE_ENV: "same:bia:Bia", BOARD_PEOPLE_ENV: "same:leo:Leo"}

    assert LocalIdentity(env=env).identify(credential="same").groups == (PRODUCT_GROUP,)


@pytest.mark.parametrize("var", [BOARD_PEOPLE_ENV, BOARD_SHARED_ENV])
def test_the_board_variables_close_the_door(var):
    value = "bd:leo:Leo" if var == BOARD_PEOPLE_ENV else "bd"
    assert not LocalIdentity(env={var: value}).open_to_everyone(), var


# ── the door ────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def deployment(tmp_path, monkeypatch):
    """An operator, a product owner and a board credential; `acme` has a product role and `solo`
    has none, both on the local board."""
    from openfactory.adapters.board_setup.local import LocalBoardSetup
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.registry import ProjectRegistry

    monkeypatch.setenv("OPENFACTORY_BOARD_DB", str(tmp_path / "board.db"))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv(PEOPLE_ENV, "op-secret:rob:Rob")
    monkeypatch.setenv(PRODUCT_PEOPLE_ENV, "ba-secret:bia:Bia")
    monkeypatch.setenv(BOARD_PEOPLE_ENV, "bd-secret:leo:Leo")
    for var in (SHARED_ENV, PRODUCT_SHARED_ENV, BOARD_SHARED_ENV):
        monkeypatch.delenv(var, raising=False)
    registry = ProjectRegistry()
    for name, product in (("acme", ProductConfig(docs_repo="acme/docs")), ("solo", None)):
        registry.add(Project(name=name, repo_path=str(tmp_path / name), product=product,
                             tracker=ProviderRef(kind="local", repo=name, options={})))
        LocalBoardSetup().create(project=registry.get(name), owner="", title=name, token=None)
    from openfactory.api.app import app

    return TestClient(app)


def _get(client, path: str, who: str):
    return client.get(path, headers={"authorization": who})


def test_TODAYS_RULE_the_product_owner_reads_the_board_of_a_project_with_a_product_role(
        deployment):
    board = _get(deployment, "/api/board/acme", ANALYST)

    assert board.status_code == 200, board.text
    assert board.json()["columns"], board.json()


def test_and_not_the_board_of_a_project_without_one(deployment):
    other = _get(deployment, "/api/board/solo", ANALYST)

    assert other.status_code == 403
    assert "solo has none" in other.json()["detail"], other.json()


def test_the_rest_of_the_floor_is_still_refused_to_the_product_owner(deployment):
    assert _get(deployment, "/api/projects", ANALYST).status_code == 403


def test_TODAYS_RULE_the_board_credential_is_refused_the_product_owners_area_by_name(deployment):
    for path in ("/api/product/projects", "/api/product/acme/documents"):
        refused = _get(deployment, path, BOARD)
        assert refused.status_code == 403, (path, refused.status_code)
        assert refused.json()["detail"] == ("this credential is scoped to floor and that is part "
                                            "of the product."), refused.json()


def test_the_board_credential_reaches_the_board(deployment):
    assert _get(deployment, "/api/board/solo", BOARD).status_code == 200
    assert _get(deployment, "/api/whoami", BOARD).json()["scopes"] == ["floor"]


def test_the_board_credential_cannot_open_the_product_chat(deployment):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as refused:
        with deployment.websocket_connect("/api/product/stream",
                                          headers={"authorization": BOARD}):
            pass
    assert refused.value.code == 1008


def test_the_panel_token_stays_the_administrators_and_reaches_both(deployment):
    assert _get(deployment, "/api/board/solo", OPERATOR).status_code == 200
    assert _get(deployment, "/api/product/projects", OPERATOR).status_code == 200
    assert _get(deployment, "/api/whoami", OPERATOR).json()["scopes"] is None


def test_the_readiness_report_counts_a_board_credential_as_a_closed_door():
    """`product_role` asks whether a product credential is issued once the door is closed; a
    deployment that issued only board credentials has a closed door and no product one."""
    from types import SimpleNamespace

    from openfactory.onboarding import readiness as R

    probes = SimpleNamespace(project_name="demo", product_enabled=lambda: True,
                             product_admins=lambda: ["ana@acme.example"],
                             environ=lambda: {BOARD_PEOPLE_ENV: "bd-secret:leo:Leo"})

    found, _ = R._product_role(probes, on="worker")

    assert not found.ok and "no product credential is issued" in found.message, found.message


def test_the_operators_documents_name_the_board_variables():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for doc in ("docs/configuration.md", "docs/reference/configuration.md", ".env.compose.example"):
        text = (root / doc).read_text(encoding="utf-8")
        assert BOARD_PEOPLE_ENV in text and BOARD_SHARED_ENV in text, doc


def test_a_worktree_workload_never_holds_a_board_credential(monkeypatch):
    """A workload holding one could act on the board as whoever it names; stripped from the day
    the credential exists."""
    from openfactory.adapters.sandbox.worktree import _scrubbed_env

    monkeypatch.setenv(BOARD_PEOPLE_ENV, "bd-secret:leo:Leo")
    monkeypatch.setenv(BOARD_SHARED_ENV, "bd-shared")

    left = _scrubbed_env()

    assert BOARD_PEOPLE_ENV not in left and BOARD_SHARED_ENV not in left


# ── the invitation ──────────────────────────────────────────────────────────────────────────────

def _invite(**kw):
    from openfactory import actions

    return asyncio.run(actions.perform(
        "people_invite", by=actions.Actor(id="rob", display="Rob", via="panel", admin=True),
        person="leo@acme.example", **kw))


def test_an_invitation_to_the_board_is_scoped_to_the_floor(local):  # noqa: F811
    from openfactory.identity.people import PeopleStore

    out = _invite(board="yes")

    assert out.ok and out.data["board"] is True, out.message
    assert PeopleStore().pending()[0].groups == (BOARD_GROUP,)


def test_an_invitation_to_both_areas_is_refused_as_the_administrators(local):  # noqa: F811
    from openfactory import actions

    out = _invite(board="yes", product="yes")

    assert not out.ok and out.code == actions.INVALID, out
    assert "administrator" in out.message and local.rows == [], out.message


def test_the_shell_invites_to_the_board(local):  # noqa: F811
    from typer.testing import CliRunner

    from openfactory.cli import app
    from openfactory.identity.people import PeopleStore

    r = CliRunner().invoke(app, ["people", "invite", "leo@acme.example", "--by", "rob", "--board"])

    assert r.exit_code == 0 and "(the board only)" in r.output, r.output
    token = r.output.split("invite=")[1].split()[0]
    assert PeopleStore().invitation_for(token).groups == (BOARD_GROUP,)
