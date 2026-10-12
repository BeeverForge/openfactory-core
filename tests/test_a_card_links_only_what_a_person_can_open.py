"""A card links the context repository only by an address a person can open, never by a path on
this machine.

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, #662). On the local row, every card the
product role filed from a requirement ended its `## Source` with

    Executes **REQ-0004** in [reservas-context](<home>/.openfactory/context/reservas-context) — …

The link's target was the context repository's directory on the operator's machine. Nobody reading
the board can open it, and it writes the operator's home directory, account name included, into the
body of every card. `_docs_url` turned the forge's clone URL into the link, and the local forge's
clone URL is a path.

THE RULE THIS FILE HOLDS, for a product of one project and a product of several, on every row:
  1. a card links its context repository only by an `http://` or `https://` address. Anything
     else a forge answers is not linked, whether a path, `file://` or an ssh address, and the
     card names the repository as plain text;
  2. on a hosted row the link is the forge's own address, as before;
  3. the card never carries a path of this machine.
"""

from __future__ import annotations

import pytest

from openfactory import namespace
from openfactory.product.authoring import issue_body
from openfactory.product.config import ProductLink
from openfactory.product.loader import ProductContext
from openfactory.product.module import ProductModule
from openfactory.product.role import IssueDraft
from tests.product_shapes import ProductShape
from tests.product_shapes import product_shape as product_shape  # noqa: F401 — the fixture


def _module(shape: ProductShape, member: str, tmp_path) -> ProductModule:
    project = shape.project(member, repo_path=str(tmp_path / member))
    link = ProductLink(active=True, docs_repo=shape.docs_repo, kind="ok")
    return ProductModule(project, token="", context=ProductContext(link=link))


def _source(shape: ProductShape, url: str) -> str:
    body = issue_body(IssueDraft(title="t", objective="o", cites=4),
                      requirement_path="requirements/0004-x.md", docs_repo=shape.docs_repo,
                      docs_url=url)
    return body.split("## Source", 1)[1]


# ── 1. the local row ────────────────────────────────────────────────────────────────────────────

def test_TODAYS_RUN_every_card_on_the_local_row_names_the_context_without_a_path(product_shape,
                                                                              tmp_path):
    home = str(namespace.operator_path(""))
    for member in product_shape.members:
        url = _module(product_shape, member, tmp_path)._docs_url()
        source = _source(product_shape, url)

        assert url == "", (member, url)
        assert f"`{product_shape.docs_repo}`" in source, source
        assert home not in source and str(tmp_path) not in source, source


# ── 2. a hosted row keeps its link ──────────────────────────────────────────────────────────────

def test_on_a_hosted_row_every_card_links_the_forges_own_address(product_shape, tmp_path):
    shape = product_shape.hosted()
    for member in shape.members:
        url = _module(shape, member, tmp_path)._docs_url()

        assert url == f"https://github.com/{shape.docs_repo}", (member, url)
        assert f"[{shape.docs_repo}]({url})" in _source(shape, url)


# ── 3. whatever a forge answers ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("answered, linked", [
    ("/home/operator/.openfactory/context/ctx.git", ""),
    ("relative/ctx.git", ""),
    ("file:///home/operator/.openfactory/context/ctx.git", ""),
    ("git@github.com:AcmeCorp/ctx.git", ""),
    ("ssh://git@github.com/AcmeCorp/ctx.git", ""),
    ("https://forge.example.com/AcmeCorp/ctx.git", "https://forge.example.com/AcmeCorp/ctx"),
    ("http://forge.internal/AcmeCorp/ctx.git", "http://forge.internal/AcmeCorp/ctx"),
])
def test_only_an_address_a_person_can_open_becomes_a_link(answered, linked, monkeypatch,
                                                          product_shape, tmp_path):
    class _Forge:
        def clone_url(self, repo, *, token=None):
            return answered

    monkeypatch.setattr("openfactory.adapters.forge.registry.build_forge",
                        lambda project, **_k: _Forge())

    for member in product_shape.members:
        assert _module(product_shape, member, tmp_path)._docs_url() == linked, (member, answered)
