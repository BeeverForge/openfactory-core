"""`registry.yaml.example` documented a default the code does not have (#160).

    # language: pt-BR (default)      ← the example
    DEFAULT_LANGUAGE = "en"          ← the code

It was true of nothing. A reader of the example, a reader of the code, and a reader of the actual
CHANNEL each got a different answer — the channel's being Brazilian Portuguese because the
composers ignored the setting altogether.

That is the shape this codebase pays for repeatedly: a fact spelled in two places, drifting, with
the copy a human reads being the wrong one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from openfactory.product.voice import DEFAULT_LANGUAGE

EXAMPLE = Path(__file__).parent.parent / "deploy" / "registry.yaml.example"


def test_the_example_documents_the_default_the_CODE_has():
    """Read from the code, never re-typed here: a literal in this test is a third copy of the same
    fact, and the next drift would be between the guard and both of them."""
    said = re.search(r"^# language: (\S+) \(default\)", EXAMPLE.read_text(), re.M)

    assert said, "the example no longer documents the language default at all"
    assert said.group(1) == DEFAULT_LANGUAGE, (
        f"the example tells an operator the default is {said.group(1)!r} and the code answers "
        f"{DEFAULT_LANGUAGE!r} — whichever they believe, one of them is lying to them")


def test_and_the_guard_can_SEE_a_drift():
    """Verify the verifier: fed the exact line that was live in the tree."""
    stale = "# language: pt-BR (default) — the tech-lead's and product role's DEFAULT language"

    found = re.search(r"^# language: (\S+) \(default\)", stale, re.M)

    assert found and found.group(1) == "pt-BR" and found.group(1) != DEFAULT_LANGUAGE


def test_the_example_still_SHOWS_a_named_language():
    """The field exists so a client who speaks something else is named rather than assumed. An
    example that only documents the default teaches nobody to set it."""
    text = EXAMPLE.read_text()

    assert re.search(r"^\s+language: \S+", text, re.M), (
        "no example project declares a language — the one thing this field is for")


# ── the configuration reference documents the box default the CODE has ──────────────────────────
#
# The reference is the only door a hand-rolled cloud deployment has. On 2026-08-26 its
# `OPENFACTORY_SANDBOX` row still read "Unset → `fargate` if `OPENFACTORY_FARGATE_CLUSTER` is
# set" — an inference the code had removed — so a second deployment written from it set the
# cluster variable alone and got `container` on a task with no docker daemon: the failure the
# terraform guard closed, reached through the document instead of the .tf. And the variable that
# replaced the token-pool inference (`OPENFACTORY_TOKEN_POOL_SOURCE`) appeared nowhere.

REFERENCE = Path(__file__).parent.parent / "docs" / "reference" / "configuration.md"
ONBOARDING = Path(__file__).parent.parent / "docs" / "ONBOARDING.md"

#: How the reference states a default: "Unset → `<kind>`", with NO condition after the kind.
#: The stale row's condition was spelled "if `<VARIABLE>`", and that is what group 2 catches.
UNSET_ARROW = re.compile(r"Unset → `(\w+)`( if `[A-Z_]+`)?")


def env_row(text: str, name: str) -> str | None:
    """The right-hand cell of the reference's row for one variable, or None when it has none."""
    found = re.search(rf"^\| `{re.escape(name)}` \| (.*) \|$", text, re.M)
    return found.group(1) if found else None


def documented_default(cell: str) -> tuple[str | None, bool]:
    """(the default the row states, whether it is conditioned on another variable)."""
    found = UNSET_ARROW.search(cell)
    return (found.group(1), found.group(2) is not None) if found else (None, False)


@pytest.mark.parametrize("name,code_default", [
    ("OPENFACTORY_SANDBOX", "openfactory.runtime.temporal.io:DEFAULT_SANDBOX"),
    ("OPENFACTORY_TOKEN_POOL_SOURCE", "openfactory.adapters.agent.token_pool:DEFAULT_SOURCE"),
])
def test_the_reference_documents_the_declared_default_the_CODE_has(name, code_default):
    """Read from the code, never re-typed here. The row exists, states the code's default, and
    conditions it on nothing — a deployment DECLARES the other kinds."""
    import importlib

    module, _, attr = code_default.partition(":")
    real = getattr(importlib.import_module(module), attr)
    cell = env_row(REFERENCE.read_text(), name)

    assert cell is not None, f"docs/reference/configuration.md has no row for {name}"
    said, conditioned = documented_default(cell)
    assert said == real, (
        f"the reference tells an operator {name} unset means {said!r} and the code answers "
        f"{real!r} — whichever they believe, one of them is lying to them")
    assert not conditioned, (
        f"the reference conditions {name}'s default on another variable — the code infers nothing; "
        f"a cloud deployment declares the kind")


def test_the_reference_and_the_front_door_show_the_cloud_DECLARING_its_box(monkeypatch):
    """The positive half: both documents show a cloud deployment naming its box in
    `OPENFACTORY_SANDBOX=<kind>`, and the kind they show is one the installed table answers
    `remote` for with the platform's own add-ons in view — never a cluster coordinate alone."""
    from vendor_addons import install

    from openfactory.adapters.sandbox.registry import installed_box_traits

    install(monkeypatch)
    for doc, text in ((REFERENCE, env_row(REFERENCE.read_text(), "OPENFACTORY_SANDBOX") or ""),
                      (ONBOARDING, re.search(r"^\| \*\*where the work runs\*\* \|.*\| (.*) \|$",
                                             ONBOARDING.read_text(), re.M).group(1))):
        shown = re.findall(r"OPENFACTORY_SANDBOX=`?(\w+)", text)
        assert shown, f"{doc.name} no longer shows a cloud deployment declaring its box"
        assert all(installed_box_traits(kind).remote for kind in shown), (doc.name, shown)


def test_and_the_reference_guard_can_SEE_the_stale_row():
    """Verify the verifier: fed the exact row that was live in the reference on 2026-08-26, and a
    reference with the token-pool row missing."""
    stale = ("| `OPENFACTORY_SANDBOX` | `worktree` \\| `container`. Unset → `fargate` if "
             "`OPENFACTORY_FARGATE_CLUSTER` is set, else `container` |\n")

    assert documented_default(env_row(stale, "OPENFACTORY_SANDBOX")) == ("fargate", True)
    assert env_row(stale, "OPENFACTORY_TOKEN_POOL_SOURCE") is None
    assert documented_default("Unset → `container`. Never inferred") == ("container", False)


# ── what bounds a turn at N sources is written down, in the names the code reads (#369) ─────────
#
# ADR-0052 D16 justified mounting every declared source in bytes per source only. What bounds the
# round trips of a turn at N sources is two operator settings, and a document that names a
# variable the code no longer reads tells an operator to turn a knob that is not there.

ADR_0052 = Path(__file__).parent.parent / "docs" / "adr" / "0052-the-owners-view.md"
SOURCES_SETTINGS = ("OPENFACTORY_SOURCES_PARALLEL", "OPENFACTORY_SOURCES_FRESH_SECONDS")
DEFERRAL = re.compile(r"^\*\*A relevance filter or a declared working set:\*\*\s+\**(\w+)", re.M)


def d16_amendment(text: str) -> str | None:
    """The dated #369 note under D16 of ADR-0052, comments taken out: from the note to the end of
    the section, or None when D16 carries none."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    section = re.search(r"^### D16\b.*?(?=^### |\Z)", text, re.M | re.S)
    if section is None:
        return None
    note = re.search(r"^\*\*Amended \(2026-\d\d-\d\d, #369\):\*\*.*", section.group(0),
                     re.M | re.S)
    return note.group(0) if note else None


def test_adr_0052_names_what_bounds_a_turn_and_the_code_reads_every_variable_it_names():
    from openfactory import environ

    note = d16_amendment(ADR_0052.read_text(encoding="utf-8"))

    assert note is not None, "ADR-0052 D16 has no dated #369 note saying what bounds a turn"
    named = set(re.findall(r"OPENFACTORY_[A-Z0-9_]+", note))
    assert set(SOURCES_SETTINGS) <= named, named
    assert not named - environ.names_read(), (
        f"the note names {sorted(named - environ.names_read())}, which the code does not read")
    decided = DEFERRAL.search(note)
    assert decided, "the note does not record the decision on a relevance filter or working set"
    assert decided.group(1).lower() in {"done", "deferred", "rejected"}, decided.group(1)


def test_and_the_adr_guard_can_SEE_a_d16_without_its_note():
    """Verify the verifier: D16 as it stood on main, and a note hidden in a comment."""
    bare = "### D16 — Every declared source is mounted\n\nText.\n\n### D17 — Next\n"
    hidden = bare.replace("Text.", "<!-- **Amended (2026-10-18, #369):** x -->")
    later = bare + "**Amended (2026-10-18, #369):** under D17, not D16\n"

    assert d16_amendment(bare) is None
    assert d16_amendment(hidden) is None
    assert d16_amendment(later) is None


@pytest.mark.parametrize("name,code_default", [
    ("OPENFACTORY_SOURCES_PARALLEL", "DEFAULT_PARALLEL"),
    ("OPENFACTORY_SOURCES_FRESH_SECONDS", "DEFAULT_FRESH_SECONDS"),
])
def test_the_configuration_reference_documents_the_sources_defaults_the_code_has(name,
                                                                                 code_default):
    from openfactory.product import sources

    real = getattr(sources, code_default)
    cell = env_row(REFERENCE.read_text(), name)

    assert cell is not None, f"docs/reference/configuration.md has no row for {name}"
    said, conditioned = documented_default(cell)
    assert said is not None and int(said) == real, (
        f"the reference tells an operator {name} unset means {said!r} and the code answers "
        f"{real!r}")
    assert not conditioned
