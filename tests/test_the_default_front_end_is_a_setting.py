"""The default front end is a setting: on by default, and off serves the API and no page (#561,
slice 2).

Decided on 2026-10-08 for 0.6.0: the core's API does not depend on a front end, and the panel's
page is OpenFactory's DEFAULT front end, which one setting turns on or off. Until now nothing could
turn it off — every page address returned `panel.html` from the API's own process.

`OPENFACTORY_DEFAULT_FRONT_END`, `on` by default so an upgrade keeps the panel. `off` serves the
API, its two streams, the sign-in and the previews, and no page: every page address answers 404 and
says why. The installer writes the line, and `docs/configuration.md` names it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SETTING = "OPENFACTORY_DEFAULT_FRONT_END"

#: Every address the page is served at: the floor, a project's board, card, pull request and
#: preview, the logs, and the product owner's surface.
PAGES = ("/", "/p/acme", "/p/acme/board", "/p/acme/card/7", "/p/acme/pr/3", "/p/acme/preview/7",
         "/logs", "/logs/acme", "/logs/acme/7", "/product/acme")

#: Not pages: the API, the sign-in, the API's own description and what a supervisor asks (#681)
#: answer the same either way.
NOT_PAGES = ("/api/whoami", "/api/actions", "/auth/login", "/openapi.json", "/healthz", "/readyz")


@pytest.fixture
def client(monkeypatch):
    for open_panel in ("OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PANEL_TOKENS",
                       "OPENFACTORY_PRODUCT_TOKEN", "OPENFACTORY_PRODUCT_TOKENS"):
        monkeypatch.delenv(open_panel, raising=False)
    monkeypatch.delenv(SETTING, raising=False)
    from openfactory.api.app import app

    return TestClient(app)


def test_on_by_default_every_page_address_serves_the_panel(client):
    for path in PAGES:
        answer = client.get(path)
        assert answer.status_code == 200, (path, answer.status_code)
        assert answer.text.startswith("<!doctype html>"), path


@pytest.mark.parametrize("off", ["off", "OFF", "false", "no", "0"])
def test_off_every_page_address_answers_404_and_says_why(client, monkeypatch, off):
    monkeypatch.setenv(SETTING, off)

    for path in PAGES:
        answer = client.get(path)
        assert answer.status_code == 404, (path, answer.status_code)
        assert f"{SETTING}=off" in answer.json()["detail"], (path, answer.text)
        assert "<!doctype html>" not in answer.text, path


def test_off_the_api_the_sign_in_and_the_api_s_description_answer_as_they_do_on(client,
                                                                               monkeypatch):
    on = {path: (client.get(path).status_code, client.get(path).text) for path in NOT_PAGES}

    monkeypatch.setenv(SETTING, "off")
    off = {path: (client.get(path).status_code, client.get(path).text) for path in NOT_PAGES}

    assert off == on


def test_a_value_that_is_neither_keeps_the_page_and_says_so(client, monkeypatch, caplog):
    from openfactory.api import app as api

    monkeypatch.setattr(api, "_SAID_NEITHER", set())
    monkeypatch.setenv(SETTING, "of")

    answer = client.get("/")

    assert answer.status_code == 200 and answer.text.startswith("<!doctype html>")
    assert f"{SETTING}='of' is neither on nor off" in caplog.text, caplog.text


def test_the_same_unreadable_value_is_said_once_not_on_every_page(client, monkeypatch, caplog):
    """Review of #611: asked on every page request, the warning buried the log it was in."""
    from openfactory.api import app as api

    monkeypatch.setattr(api, "_SAID_NEITHER", set())
    monkeypatch.setenv(SETTING, "of")
    for _ in range(3):
        assert client.get("/").status_code == 200
    monkeypatch.setenv(SETTING, "onn")
    client.get("/")

    assert caplog.text.count("is neither on nor off") == 2, caplog.text


def test_every_page_route_asks_the_setting(client, monkeypatch):
    """A PAGE ADDED LATER CANNOT SKIP THE QUESTION. Every GET route outside the API, the sign-in,
    the API's own description and the probes a supervisor asks (`health.PATHS`, #681) is walked,
    with its parameters filled, and must answer 404 with the setting off — so a new page that
    returns `panel.html` by itself fails here by name."""
    from openfactory.api.app import app
    from openfactory.observability import health

    monkeypatch.setenv(SETTING, "off")
    walked = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or "GET" not in (route.methods or set()):
            continue
        if route.path.startswith(("/api", "/auth")) or route.path in health.PATHS:
            continue
        path = re.sub(r"\{[^}]+\}", "7", route.path)
        walked.append(path)
        assert client.get(path).status_code == 404, f"{route.path} serves a page with it off"

    assert len(walked) >= len(PAGES), walked


@pytest.mark.parametrize("exposed", [False, True], ids=["a laptop", "an exposed panel"])
def test_the_installer_writes_the_line_and_the_configuration_names_it(exposed):
    from openfactory.onboarding.deployment import Answers, render

    written = render(Answers(panel_exposed=exposed)).text
    assert f"\n{SETTING}=on\n" in written, "the environment the installer writes has no setting"
    docs = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    assert f"**`{SETTING}`**" in docs, "docs/configuration.md does not name the setting"
