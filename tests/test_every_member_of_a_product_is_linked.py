"""Every project of a product is linked to its context repository, however many projects it has.

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, #663). Three local projects, `reservas-web`,
`reservas-api` and `reservas-core`, pointed at one context repository that listed all three in
`sources:`. By `product/key.py` they are one product. `doctor` refused `product_link` on every
project but one:

    reservas-context holds requirements for product 'reservas-web', but this project is
    'reservas-api'. Refusing: writing one client's requirements into another's repository is an
    isolation breach, not a typo to work around.

With `product: reservas`, the owner's own project was refused too. The check compared the context's
`product:` with each project's name, which only a product of one project can satisfy.

THE RULE THIS FILE HOLDS, for a product of one project and a product of several:
  1. every project the context lists in `sources:` is linked, whatever the product is called;
  2. a project the context does not list is refused, whatever it is called. That is the isolation
     the check exists for;
  3. the product's name admits a project alone only when it is the project's own name. A listing
     made on the repository's name alone does not stand in for it.
"""

from __future__ import annotations

import pytest

from openfactory.product import resolve_product_link
from tests.product_shapes import ProductShape
from tests.product_shapes import product_shape as product_shape  # noqa: F401 — the fixture


def _rows(shape: ProductShape) -> list[ProductShape]:
    return [shape, shape.hosted()]


# ── 1. every member ─────────────────────────────────────────────────────────────────────────────

def test_TODAYS_RUN_every_member_of_the_product_is_linked(product_shape):
    for shape in _rows(product_shape):
        for member in shape.members:
            link = resolve_product_link(project=shape.project(member), docs=shape.docs())

            assert link.active and link.kind == "ok", (shape.id, member, link.reason)


def test_TODAYS_RUN_a_product_named_after_one_member_links_the_others(product_shape):
    """The week's second sitting: `product: reservas-web`, and the api and the core refused."""
    for shape in _rows(product_shape):
        docs = shape.docs(product=shape.members[0])
        for member in shape.members:
            link = resolve_product_link(project=shape.project(member), docs=docs)

            assert link.active, (shape.id, member, link.reason)


# ── 2. the isolation stays whole ────────────────────────────────────────────────────────────────

def test_a_project_the_context_does_not_list_is_refused_whatever_it_is_called(product_shape):
    for shape in _rows(product_shape):
        for name in ("intruder", shape.product, shape.members[0]):
            outsider = shape.project(name, tracker={"kind": "github", "repo": "Other/intruder"},
                                     forge={"kind": "github", "repo": "Other/intruder"})

            link = resolve_product_link(project=outsider, docs=shape.docs())

            assert not link.active and link.kind == "conflict", (shape.id, name, link.reason)


def test_a_context_that_lists_nobody_links_nobody(product_shape):
    for shape in _rows(product_shape):
        for member in shape.members:
            link = resolve_product_link(project=shape.project(member), docs=shape.docs(sources=[]))

            assert not link.active, (shape.id, member)


def test_the_refusal_says_the_project_is_not_listed_and_names_what_to_fix(product_shape):
    shape = product_shape.hosted()
    outsider = shape.project("intruder", tracker={"kind": "github", "repo": "Other/intruder"},
                             forge={"kind": "github", "repo": "Other/intruder"})

    reason = resolve_product_link(project=outsider, docs=shape.docs()).reason

    assert shape.product in reason and "intruder" in reason, reason
    assert "sources:" in reason and "isolation" in reason, reason


# ── 3. what the name alone admits ───────────────────────────────────────────────────────────────

def test_a_project_that_declares_no_code_repository_is_admitted_only_by_its_own_name(
        product_shape):
    """Nothing is listed to check, so the product's name is the one declaration left."""
    shape = product_shape
    for member in shape.members:
        bare = shape.project(member, tracker={"kind": "local"}, forge=None)

        link = resolve_product_link(project=bare, docs=shape.docs())

        assert link.active is (member == shape.product), (shape.id, member, link.reason)


def test_a_listing_on_the_repositorys_name_alone_does_not_admit_another_products_project(
        product_shape):
    """`sources:` written bare, the project hosted: the same NAME, on less evidence. It admits the
    project only when the product carries its name too, and is said as a warning there."""
    shape = product_shape
    for member in shape.members:
        hosted = shape.project(member, tracker={"kind": "github", "repo": f"Other/{member}"},
                               forge={"kind": "github", "repo": f"Other/{member}"})

        link = resolve_product_link(project=hosted, docs=shape.docs())

        assert link.active is (member == shape.product), (shape.id, member, link.reason)
        if link.active:
            assert any("NAME" in w for w in link.warnings), link.warnings


@pytest.mark.parametrize("spelled", [" Reservas-Web ", "RESERVAS-WEB"])
def test_the_name_still_reads_case_and_padding_as_the_same(spelled):
    from tests.product_shapes import SEVERAL

    bare = SEVERAL.project("reservas-web", tracker={"kind": "local"}, forge=None)

    assert resolve_product_link(project=bare, docs=SEVERAL.docs(product=spelled)).active
