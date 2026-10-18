"""A job's prompt is held to ONE budget over the whole declared section, not one cap per role
(#364, ADR-0056).

The bound is over everything the brief carries apart from the role prompt: every document tier, the
reference index, the card, the knowledge map, the planner's plan and a repair's failure log. It is
applied where every one of those meets — `ticket_brief`, at render time — because the plan is set
after `build_context` and the failure log arrives as `failures=`. #359, a cap per role, was closed
over exactly this: it counted characters against a byte limit, stopped at the first document that
did not fit, and dropped a document that landed exactly on the line. Each of those has a test here.

Every test builds a real `build_context` over a checkout in `tmp_path` and measures the prompt with
`budgeted_bytes`, which is held once, below, to be the bytes of the brief plus the plan, so the
number measured is the prompt's own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openfactory.adapters.agent.base import budgeted_bytes, fit_documents, ticket_brief
from openfactory.contracts import Manifest, Ticket
from openfactory.orchestrator import context as ctx


def _card(objective: str = "add a feature") -> Ticket:
    return Ticket(id="#41", title="feature", objective=objective, repo="o/app")


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def _build(root: Path, manifest: Manifest, *, budget: int | None, card: Ticket | None = None,
           knowledge_map: str = ""):
    built = ctx.build_context(manifest, root, card or _card(), knowledge_map=knowledge_map)
    built.prompt_budget = budget
    return built


def _kept_paths(context, failures: str = "") -> list[str]:
    return [d.path for d in fit_documents(context, failures=failures).kept]


def _left_out_paths(context, failures: str = "") -> list[str]:
    return [d.path for d in fit_documents(context, failures=failures).left_out]


def test_the_measure_is_the_brief_and_the_plan_in_bytes(tmp_path):
    _write(tmp_path, {"adr/0001-a.md": "Money is Decimal → always.\n"})
    built = _build(tmp_path, Manifest(docs={"constraints": "adr/*.md"}), budget=None)
    built.plan = "1. write the test — then the code\n"

    for failures in ("", "FAILED tests/test_x.py::test_y — assert 1 == 2"):
        brief = ticket_brief(built, failures=failures)
        assert budgeted_bytes(built, failures=failures) == (
            len(brief.encode("utf-8")) + len(built.plan.encode("utf-8")))


def test_the_whole_declared_section_fits_the_budget_not_each_role(tmp_path):
    """Ten decision records and three guidelines of 7,000 bytes each, under a budget that holds
    about half of them. A cap per role would let each role reach the budget on its own; one budget
    holds their sum, and the project's guidelines are kept before the records."""
    files = {f"adr/{i:04d}-r.md": f"# ADR {i}\n" + "c" * 7_000 for i in range(10)}
    files |= {f"rules/g{i}.md": f"# Rule {i}\n" + "g" * 7_000 for i in range(3)}
    _write(tmp_path, files)
    manifest = Manifest(docs={"constraints": "adr/*.md",
                              "guidelines": [f"rules/g{i}.md" for i in range(3)]})
    budget = 50_000
    built = _build(tmp_path, manifest, budget=budget)

    assert budgeted_bytes(built) <= budget
    kept = _kept_paths(built)
    assert all(f"rules/g{i}.md" in kept for i in range(3)), kept
    assert any(p.startswith("adr/") for p in _left_out_paths(built)), "nothing was left out"


#: How much each part grows by in the test below: two documents' worth.
_GROWTH = 15_000


def _grown(part: str, root: Path):
    """The same project with one part of the prompt grown by `_GROWTH` bytes, and the failure log
    that pass carries."""
    manifest = Manifest(docs={"constraints": "adr/*.md", "architecture": "arch/*.md"})
    card, knowledge_map, failures = _card(), "", ""
    if part == "card":
        card = _card("o" * _GROWTH)
    if part == "doc_index":
        _write(root, {f"arch/{i}.md": f"---\nsummary: {'s' * (_GROWTH // 5)}\n---\n# A\n"
                      for i in range(5)})
    if part == "knowledge_map":
        knowledge_map = "k" * _GROWTH
    built = _build(root, manifest, budget=None, card=card, knowledge_map=knowledge_map)
    if part == "plan":
        built.plan = "p" * _GROWTH
    if part == "failure_log":
        failures = "f" * _GROWTH
    return built, failures


@pytest.mark.parametrize("part", ["card", "doc_index", "knowledge_map", "plan", "failure_log"])
def test_each_part_beside_the_documents_is_counted(tmp_path, part):
    """Growing any one part of the prompt by two documents' worth leaves more documents out, and
    the whole stays within the budget."""
    _write(tmp_path, {f"adr/{i:04d}-r.md": f"# ADR {i}\n" + "c" * 7_000 for i in range(12)})
    _write(tmp_path, {"arch/0.md": "# Arch\n"})
    budget = 60_000

    before, _ = _grown("nothing", tmp_path)
    before.prompt_budget = budget
    after, failures = _grown(part, tmp_path)
    after.prompt_budget = budget

    assert budgeted_bytes(after, failures=failures) <= budget
    assert len(_kept_paths(after, failures)) < len(_kept_paths(before)), (
        f"growing the {part} by {_GROWTH:,} bytes left the same documents in")


def test_the_count_is_bytes_not_characters(tmp_path):
    """Two documents of 3,000 `é` — 3,000 characters and 6,000 bytes each — under a budget that
    holds both counted in characters and only one counted in bytes."""
    _write(tmp_path, {"adr/0001-a.md": "é" * 3_000, "adr/0002-b.md": "é" * 3_000})
    manifest = Manifest(docs={"constraints": "adr/*.md"})
    whole = budgeted_bytes(_build(tmp_path, manifest, budget=None))

    built = _build(tmp_path, manifest, budget=whole - 1)

    records = [p for p in _kept_paths(built) if p.startswith("adr/")]
    assert len(records) == 1, "both were kept: the fit counted characters"
    assert budgeted_bytes(built) <= whole - 1


def test_a_document_past_the_budget_does_not_stop_a_smaller_one_after_it(tmp_path):
    """The fill tries the large guideline first (the last declared), cannot fit it, and goes on:
    the small one after it fits and is kept, and the large one is named."""
    _write(tmp_path, {"rules/small.md": "Reads go through the cache.\n",
                      "rules/large.md": "L" * 7_000})
    manifest = Manifest(docs={"guidelines": ["rules/small.md", "rules/large.md"]})
    whole = budgeted_bytes(_build(tmp_path, manifest, budget=None))

    built = _build(tmp_path, manifest, budget=whole - 1)

    assert _kept_paths(built)[-1:] == ["rules/small.md"], _kept_paths(built)
    assert _left_out_paths(built) == ["rules/large.md"]


def test_a_document_that_lands_exactly_on_the_budget_is_kept(tmp_path):
    _write(tmp_path, {"adr/0001-a.md": "x" * 5_000})
    manifest = Manifest(docs={"constraints": "adr/*.md"})
    whole = budgeted_bytes(_build(tmp_path, manifest, budget=None))

    built = _build(tmp_path, manifest, budget=whole)

    assert "adr/0001-a.md" in _kept_paths(built)
    assert budgeted_bytes(built) == whole


def test_what_the_agent_cannot_open_is_never_left_out(tmp_path):
    """Under a budget smaller than the framework baseline alone, every framework text is still in
    the brief — it lives in the installed package and no path in the box reaches it — and every
    document named as left out is one the agent can open in its checkout."""
    _write(tmp_path, {"adr/0001-a.md": "a" * 3_000, "rules/house.md": "h" * 3_000})
    manifest = Manifest(docs={"constraints": "adr/*.md", "guidelines": ["rules/house.md"]})
    built = _build(tmp_path, manifest, budget=1_000)

    brief = ticket_brief(built)
    for doc in sorted(ctx.ORG_DEFAULTS_DIR.glob("*.md")):
        assert doc.read_text()[:ctx._MAX_DOC_CHARS] in brief, f"{doc.name} was left out"
    left_out = fit_documents(built).left_out
    assert sorted(d.path for d in left_out) == ["adr/0001-a.md", "rules/house.md"]
    assert all(d.open_at and (tmp_path / d.open_at).is_file() for d in left_out)
