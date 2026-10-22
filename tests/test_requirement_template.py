"""A product's own requirement template: fields, sections, reading, writing, the index (#1001)."""

from __future__ import annotations

from pathlib import Path

import pytest

from openfactory.product.authoring import render_requirement
from openfactory.product.corpus import _field_re, load_corpus, parse_requirement
from openfactory.product.role import RequirementDraft, requirement_index
from openfactory.product.template import load_template, read_template

TEMPLATE = """\
fields:
  - name: Business owner
    required: true
    listed: true
  - name: Priority
    type: choice
    values: [Must, Should, Could]
    listed: true
  - name: Go-live
    type: date
sections:
  - name: Regulatory impact
    required: true
"""


def _write(root: Path, template: str | None = TEMPLATE) -> Path:
    req = root / "requirements"
    req.mkdir()
    if template is not None:
        (req / "template.yaml").write_text(template, encoding="utf-8")
    return req


def test_a_label_ends_where_the_label_ends() -> None:
    text = "- **Date of go-live:** 2027-03-01\n- **Date:** 2026-10-21\n"
    assert _field_re("Date").search(text).group("value") == "2026-10-21"  # type: ignore[union-attr]
    assert _field_re("Date").search("- Date: 2026-01-02").group("value") == "2026-01-02"  # type: ignore[union-attr]
    assert _field_re("Date").search("- Dates: nothing") is None


def test_the_core_names_cannot_be_taken() -> None:
    with pytest.raises(ValueError, match="header line the core"):
        read_template("fields:\n  - name: Status\n")
    with pytest.raises(ValueError, match="section the core writes"):
        read_template("sections:\n  - name: Why\n")


@pytest.mark.parametrize(
    "text, why",
    [
        ("fields:\n  - name: A\n  - name: a\n", "more than once"),
        ("fields:\n  - name: A\n    type: choice\n", "no values"),
        ("fields:\n  - name: A\n    values: [x]\n", "not a choice"),
        ("fields:\n  - name: A\n    surprise: 1\n", "surprise"),
        ("- just\n- a list\n", "mapping"),
    ],
)
def test_a_template_that_cannot_be_used_says_why(text: str, why: str) -> None:
    with pytest.raises(ValueError, match=why):
        read_template(text)


def test_no_template_is_not_a_problem(tmp_path: Path) -> None:
    assert load_template(_write(tmp_path, None)) == (None, "")


def test_a_refused_template_is_a_finding_and_the_core_shape_applies(tmp_path: Path) -> None:
    req = _write(tmp_path, "fields: [not a field]\n")
    (req / "0001-x.md").write_text("# REQ-0001 — x\n\n- **Status:** proposed\n", encoding="utf-8")
    corpus = load_corpus(req)
    assert corpus.template is None
    assert [f.code for f in corpus.findings] == ["template-refused"]
    assert len(corpus.requirements) == 1


def test_a_requirement_is_read_with_its_own_fields_and_sections(tmp_path: Path) -> None:
    req = _write(tmp_path)
    (req / "0001-x.md").write_text(
        "# REQ-0001 — x\n\n- **Status:** proposed\n- **Business owner:** Ana Lima\n"
        "- **Priority:** Must\n- **Go-live:** —\n\n## Why\n\nBecause.\n\n"
        "## Regulatory impact\n\nNone.\n",
        encoding="utf-8",
    )
    corpus = load_corpus(req)
    one = corpus.requirements[0]
    assert one.fields == {"Business owner": "Ana Lima", "Priority": "Must", "Go-live": ""}
    assert one.sections == {"Regulatory impact": "None."}
    assert corpus.findings == []


def test_what_a_requirement_does_not_meet_is_a_warning(tmp_path: Path) -> None:
    req = _write(tmp_path)
    (req / "0001-x.md").write_text(
        "# REQ-0001 — x\n\n- **Status:** proposed\n- **Priority:** Urgent\n- **Go-live:** soon\n",
        encoding="utf-8",
    )
    found = {f.code: f for f in load_corpus(req).findings}
    assert set(found) == {"field-missing", "field-value", "section-missing"}
    assert {f.level for f in found.values()} == {"warn"}


def test_without_a_template_the_fields_are_not_read(tmp_path: Path) -> None:
    one, findings = parse_requirement(
        tmp_path / "0001-x.md", "# REQ-0001 — x\n\n- **Status:** proposed\n- **Business owner:** Ana\n"
    )
    assert one is not None and one.fields == {} and findings == []


def test_the_writer_writes_what_the_reader_reads(tmp_path: Path) -> None:
    req = _write(tmp_path)
    template = read_template(TEMPLATE)
    draft = RequirementDraft(
        title="Approve invoices",
        why="Because.",
        fields={"Business owner": "Ana Lima", "Priority": "Should", "Unknown": "ignored"},
        sections={"Regulatory impact": "Reviewed by compliance."},
    )
    text = render_requirement(draft, number=1, template=template)
    assert "- **Business owner:** Ana Lima" in text and "Unknown" not in text
    assert "- **Go-live:** —" in text
    assert text.index("## Regulatory impact") < text.index("## Decisions taken")
    (req / "0001-approve-invoices.md").write_text(text, encoding="utf-8")
    corpus = load_corpus(req)
    assert corpus.requirements[0].fields["Priority"] == "Should"
    assert corpus.requirements[0].sections["Regulatory impact"] == "Reviewed by compliance."
    assert corpus.findings == []


def test_the_writer_without_a_template_is_what_it_was() -> None:
    draft = RequirementDraft(title="x", fields={"Business owner": "Ana"}, sections={"A": "b"})
    assert render_requirement(draft, number=1) == render_requirement(
        RequirementDraft(title="x"), number=1
    )


def test_the_index_lists_the_fields_the_template_lists(tmp_path: Path) -> None:
    req = _write(tmp_path)
    (req / "0001-x.md").write_text(
        "# REQ-0001 — x\n\n- **Status:** proposed\n- **Business owner:** Ana Lima\n",
        encoding="utf-8",
    )
    lines = requirement_index(load_corpus(req)).splitlines()
    assert lines[0] == "| req | status | title | affects | file | Business owner | Priority |"
    assert lines[1] == "|---|---|---|---|---|---|---|"
    assert lines[2].endswith("| Ana Lima | — |")
