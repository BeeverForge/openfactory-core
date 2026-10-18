"""The operator sets the prompt budget, the default is the one the documents say, and a value
nobody can read is refused by name before a pass (#364, ADR-0056).

Until #364 nothing decided how large a job's prompt may be: measured on this repository at d29b94a,
a blank card's brief carried 477,369 bytes, 398,127 of them decision records, under a configuration
guide that said "full text, every prompt" over 35 records `_MAX_DOC_CHARS` had already cut. The
product owner decided on 2026-10-18 that a bound exists. These tests hold where it is set (the
worker's environment, `OPENFACTORY_PROMPT_BUDGET`), what it defaults to (the number the code
exports, compared against the decision record, the reference and the configuration guide, each
parsed rather than grepped), and that a malformed value stops a job with one sentence instead of
being read as the default in silence.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import test_walking_skeleton as spine

from openfactory.contracts import AcceptanceCriterion, JobState, Manifest, Ticket
from openfactory.orchestrator import context as ctx

ROOT = Path(__file__).resolve().parents[1]
repo = spine.repo
VARIABLE = "OPENFACTORY_PROMPT_BUDGET"


def _card() -> Ticket:
    return Ticket(id="#41", title="feature", objective="add a feature", repo="o/app",
                  acceptance_criteria=[AcceptanceCriterion(text="feature.py exists")])


# ── where it is set ──────────────────────────────────────────────────────────────────────────────

def test_the_environment_sets_the_budget(monkeypatch, tmp_path):
    """A number of bytes in the worker's environment is the budget a job's context carries."""
    monkeypatch.setenv(VARIABLE, "96000")

    assert ctx.prompt_budget() == 96_000
    built = ctx.build_context(Manifest(), tmp_path, _card(), knowledge_map="")
    assert built.prompt_budget == 96_000


def test_unset_is_the_default_the_code_has(monkeypatch, tmp_path):
    monkeypatch.delenv(VARIABLE, raising=False)

    assert ctx.prompt_budget() == ctx.DEFAULT_PROMPT_BUDGET
    assert ctx.build_context(Manifest(), tmp_path, _card(),
                             knowledge_map="").prompt_budget == ctx.DEFAULT_PROMPT_BUDGET


def test_off_inlines_everything(monkeypatch, tmp_path):
    """`off` is the "keep everything inlined" escape hatch the decision keeps for an operator who
    chooses to pay it: no budget, every document inlined, nothing named as left out."""
    from openfactory.adapters.agent.base import fit_documents

    monkeypatch.setenv(VARIABLE, "off")
    (tmp_path / "adr").mkdir()
    for i in range(40):
        (tmp_path / "adr" / f"{i:04d}-x.md").write_text(f"# ADR {i}\n" + "a" * 7_000)

    built = ctx.build_context(Manifest(docs={"constraints": "adr/*.md"}), tmp_path, _card(),
                              knowledge_map="")
    fit = fit_documents(built)

    assert ctx.prompt_budget() is None and built.prompt_budget is None
    assert fit.left_out == []
    assert len(fit.kept) == len(built.documents) and len(built.documents) >= 40


# ── a value nobody can read is refused by name, before a pass ───────────────────────────────────

@pytest.mark.parametrize("value", ["160kb", "-5", "0", "1.5e5", "unlimited", "²", "١٦٠٠٠٠"])
def test_a_malformed_budget_is_refused_by_name(monkeypatch, value):
    """Never the default in silence: an operator who wrote `160kb` believes a budget is set. A
    digit that is not ASCII (`²`, Arabic-Indic numerals) is refused the same way: `str.isdigit`
    says yes to it and `int()` raises a bare `ValueError` on `²`."""
    monkeypatch.setenv(VARIABLE, value)

    with pytest.raises(ctx.PromptBudgetError) as raised:
        ctx.prompt_budget()

    said = str(raised.value)
    assert VARIABLE in said and repr(value) in said, said
    assert "off" in said and "bytes" in said, f"the sentence does not say what is accepted: {said}"
    assert "\n" not in said, "one sentence, not a block"


def test_a_malformed_budget_fails_the_doctors_documents_line(monkeypatch):
    from openfactory import doctor
    from tests.pinned_probes import a_fully_pinned_probe_set

    monkeypatch.setenv(VARIABLE, "160kb")

    report = doctor.diagnose(a_fully_pinned_probe_set())
    line = next(f for f in report.findings if f.check == "documents")

    assert not line.ok, "a budget nobody can read is reported as fine"
    assert VARIABLE in line.message and "'160kb'" in line.message, line.message


def test_a_malformed_budget_holds_the_job_before_any_pass(monkeypatch, repo, tmp_path):
    """The job holds with the sentence, beside the profile hold, before a token is spent."""
    class _NeverCalled:
        def execute(self, **_kw):
            raise AssertionError("a pass ran under a budget nobody could read")

        def repair(self, **_kw):
            raise AssertionError("a pass ran under a budget nobody could read")

    monkeypatch.setenv(VARIABLE, "160kb")
    tracker = spine.FakeTracker(_card())
    runner = spine._runner(repo, tracker, Manifest(validate={"test": "true"}), tmp_path,
                           agent=_NeverCalled())

    result = runner.run("#41")

    assert result.state is JobState.ON_HOLD
    assert VARIABLE in (result.note or "") and "'160kb'" in (result.note or ""), result.note


# ── the default the documents state is the default the code has ─────────────────────────────────

def _bytes(number: str) -> int:
    return int(number.replace(",", ""))


def test_the_decision_record_names_the_variable_and_the_default_the_code_has():
    adr = next((ROOT / "docs" / "adr").glob("0056-*.md")).read_text(encoding="utf-8")

    found = re.findall(r"^Default: ([\d,]+) bytes \((\w+)\)$", adr, flags=re.MULTILINE)

    assert len(found) == 1, "ADR-0056 states its default on exactly one `Default:` line"
    number, variable = found[0]
    assert variable == VARIABLE
    assert _bytes(number) == ctx.DEFAULT_PROMPT_BUDGET


def _table_row(page: Path, first_cell: str) -> list[str]:
    """The cells of the one markdown table row whose first cell is `first_cell`."""
    rows = [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in page.read_text(encoding="utf-8").splitlines()
            if line.lstrip().startswith("|")]
    matches = [r for r in rows if r and r[0] == first_cell]
    assert len(matches) == 1, f"{page.name} has {len(matches)} rows starting {first_cell!r}"
    return matches[0]


def test_the_reference_documents_the_default_the_code_has():
    cells = _table_row(ROOT / "docs" / "reference" / "configuration.md", f"`{VARIABLE}`")
    said = " ".join(cells[1:])

    numbers = {_bytes(n) for n in re.findall(r"\b\d{1,3}(?:,\d{3})+\b", said)}
    assert numbers == {ctx.DEFAULT_PROMPT_BUDGET}, (
        f"the reference names {sorted(numbers)} and the code defaults to "
        f"{ctx.DEFAULT_PROMPT_BUDGET:,}")
    assert "`off`" in said and "bytes" in said


def test_the_configuration_guide_states_the_truncation_and_the_budget_the_code_has():
    """The tier table's constraints row said "full text, every prompt" while `_MAX_DOC_CHARS` cut
    35 of this repository's 56 records. It now says what is true, in the numbers the code has."""
    cells = _table_row(ROOT / "docs" / "configuration.md", "**constraints**")
    how = cells[2]

    assert "full text, every prompt" not in how
    assert f"{ctx._MAX_DOC_CHARS:,}" in how, f"the row does not state the truncation: {how!r}"
    assert VARIABLE in how and f"{ctx.DEFAULT_PROMPT_BUDGET:,}" in how, how


@pytest.mark.parametrize("language", ["en", "pt-BR"])
def test_explain_refuses_a_malformed_budget_in_one_sentence(monkeypatch, tmp_path, language):
    """`explain` runs the job's own `build_context`, so it meets the same refusal — said in the
    reader's language, never as a traceback."""
    from openfactory.orchestrator import explain as ex

    (tmp_path / ".openfactory").mkdir()
    (tmp_path / ".openfactory" / "project.yaml").write_text("version: 1\n")
    monkeypatch.setenv(VARIABLE, "160kb")

    with pytest.raises(ex.Refused) as refused:
        ex.explain(str(tmp_path), language=language)

    said = str(refused.value)
    assert VARIABLE in said and "'160kb'" in said and "\n" not in said, said
