"""A GitHub App key refused after the adapter was built is as final as one refused before (#742).

The refusal a GitHub adapter is handed is the store's answer at construction. The key a mint reads
is read at each mint, so it can be refused later — a file whose mode changed, a directory that
became shared — and the provider then answers nothing, with nothing refused on the adapter.
`credential_of` asks the key's refusal again then, so `gh` still never runs on the machine's own
login in its place (review of 256c5b0).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from openfactory import credentials
from openfactory.adapters import github_cli

REFUSED = "`file:OPENFACTORY_GH_APP_KEY_CONTENT` is refused: the file is writable by its group"


def _minting_adapter():
    """An adapter built with no token and nothing refused, whose mint answers nothing now."""
    return SimpleNamespace(_token_provider=lambda: None, _static_token=None, refused="")


def test_an_app_key_refused_after_the_adapter_was_built_runs_no_gh(monkeypatch):
    monkeypatch.setattr(credentials, "app_key_refusal", lambda: REFUSED)
    with pytest.raises(github_cli.LoginRefused, match="writable by its group"):
        github_cli.credential_of(_minting_adapter())


def test_a_mint_that_answers_nothing_with_nothing_refused_keeps_the_development_path(monkeypatch):
    """With no key refused, a mint that answers nothing is what it always was: `gh` on the
    machine's own login, the development path."""
    monkeypatch.setattr(credentials, "app_key_refusal", lambda: "")
    assert github_cli.credential_of(_minting_adapter()) is None


def test_an_adapter_that_mints_nothing_is_not_asked_the_keys_refusal(monkeypatch):
    """A static token, or none, mints nothing: the key is not its business."""
    monkeypatch.setattr(credentials, "app_key_refusal", lambda: REFUSED)
    assert github_cli.credential_of(
        SimpleNamespace(_token_provider=None, _static_token="fictitious-static-822e",
                        refused="")) == "fictitious-static-822e"
    assert github_cli.credential_of(
        SimpleNamespace(_token_provider=None, _static_token=None, refused="")) is None
