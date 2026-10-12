"""The shapes a product comes in, so that a test about a product holds for each of them.

A product is every registry project that points at one context repository: one product, one role,
one memory (`openfactory/product/key.py`, ADR-0051 D2). Every product the suite built was of ONE
project, and journey 0 (#640) found four defects that lived only in the other shape, a product of
several projects:
  - a member was refused its product link (#663);
  - a sibling's code was unreadable on the local forge (#664);
  - a card linked the context repository by a path on the machine (#662);
  - a front meant for one repository ran in another (#665).

A test about a product takes the `product_shape` fixture and holds for every shape here. A check
written tomorrow gets both shapes by taking the fixture, and one that cannot hold for a shape says
so in its own `pytest.skip`, where a reviewer reads it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from openfactory.contracts.product import ProductConfig, ProductDocs
from openfactory.contracts.project import Project


@dataclass(frozen=True)
class ProductShape:
    id: str
    #: the context repository's `product:`
    product: str
    #: the context repository, by name
    context: str
    #: the registry projects that point at it, the owner's page first
    members: tuple[str, ...]
    #: how this row writes a repository: `name` on the local row, `Owner/name` on a hosted one
    owner: str = ""

    def source(self, member: str) -> str:
        """The member's code repository, as its registry entry and `sources:` write it."""
        return f"{self.owner}/{member}" if self.owner else member

    @property
    def docs_repo(self) -> str:
        return self.source(self.context)

    def hosted(self) -> ProductShape:
        """The same product on a hosted row, where a repository is `Owner/name`."""
        return replace(self, id=f"{self.id}, hosted", owner="AcmeCorp")

    def docs(self, **kw) -> ProductDocs:
        """The context repository's `.openfactory/product.yaml`: this product, every member listed."""
        return ProductDocs(product=kw.pop("product", self.product),
                           sources=kw.pop("sources", [self.source(m) for m in self.members]), **kw)

    def project(self, member: str, **kw) -> Project:
        """`member`'s registry entry: its own code repository, this product's context."""
        ref = {"kind": "github" if self.owner else "local", "repo": self.source(member)}
        return Project(name=member, repo_path=kw.pop("repo_path", f"/work/{member}"),
                       tracker=kw.pop("tracker", ref), forge=kw.pop("forge", ref),
                       product=ProductConfig(docs_repo=self.docs_repo), **kw)


ONE = ProductShape("one project", product="books", context="books-context", members=("books",))
SEVERAL = ProductShape("three projects", product="reservas", context="reservas-context",
                       members=("reservas-web", "reservas-api", "reservas-core"))
SHAPES = (ONE, SEVERAL)


@pytest.fixture(params=SHAPES, ids=[s.id for s in SHAPES])
def product_shape(request) -> ProductShape:
    return request.param
