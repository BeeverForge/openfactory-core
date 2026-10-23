"""A product's own requirement template: fields, sections, reading, writing, the index (#1001)."""

from __future__ import annotations

import inspect
import json
import re
import sys
import typing
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel

from openfactory.product.authoring import render_requirement
from openfactory.product.corpus import (
    _HEADING_RE,
    _TITLE_RE,
    _field_re,
    decision_cells,
    load_corpus,
    parse_requirement,
)
from openfactory.product.role import RequirementDraft, requirement_index
from openfactory.product.template import RequirementTemplate, load_template, read_template

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


# ── what a template may hold is bounded (review of #1014) ──────────────────────────────────────

#: a valid element of each list a template holds, which one probe at a time overrides. A choice,
#: so that its `values` can be probed without the field becoming another kind.
_VALID = {"fields": {"name": "F", "type": "choice", "values": ["a"]}, "sections": {"name": "S"}}

#: past this, a size nothing has refused is a size nothing bounds — far below the YAML door's own
#: ceilings, so the refusal measured is the template's, not the reader's
_FAR = 10_000


def _dimensions() -> list[tuple[str, Callable[[int], dict]]]:
    """Every size a template can grow in, READ FROM ITS MODELS: how many of each list it holds,
    how long each text in them is, and for a list of texts both. A flag or a closed choice is
    bounded by its type; any other kind of value fails here, so a new one cannot go unprobed."""
    out: list[tuple[str, Callable[[int], dict]]] = []
    for outer, info in RequirementTemplate.model_fields.items():
        element = typing.get_args(info.annotation)[0]
        valid = _VALID[outer]
        out.append((f"{outer} (how many)",
                    lambda n, o=outer, v=valid: {o: [{**v, "name": f"N{i}"} for i in range(n)]}))
        for key, inner in element.model_fields.items():
            kind, where = inner.annotation, f"{outer}.{key}"
            if kind is str:
                out.append((where, lambda n, o=outer, v=valid, k=key: {o: [{**v, k: "x" * n}]}))
            elif typing.get_origin(kind) is list and typing.get_args(kind) == (str,):
                out.append((f"{where} (how many)", lambda n, o=outer, v=valid, k=key: {
                    o: [{**v, k: [f"v{i}" for i in range(n)]}]}))
                out.append((f"{where} (each)",
                            lambda n, o=outer, v=valid, k=key: {o: [{**v, k: ["x" * n]}]}))
            else:
                assert kind is bool or typing.get_origin(kind) is typing.Literal, (
                    f"{where}: {kind} is a kind of value this test does not know how to bound")
    return out


def _refusal(doc: dict) -> str:
    """The sentence `doc` is refused with, or "" — written as JSON, which YAML reads."""
    try:
        read_template(json.dumps(doc))
    except ValueError as error:
        return str(error)
    return ""


@pytest.mark.parametrize("build", [b for _, b in _dimensions()], ids=[w for w, _ in _dimensions()])
def test_everything_a_template_holds_has_a_ceiling_and_past_it_the_refusal_names_it(
    build: Callable[[int], dict],
) -> None:
    n = 1
    while not _refusal(build(n)):
        assert n <= _FAR, f"accepted at {n} — nothing bounds it"
        n *= 2
    largest, past = n // 2, n
    while past - largest > 1:
        mid = (largest + past) // 2
        largest, past = (largest, mid) if _refusal(build(mid)) else (mid, past)
    refused = _refusal(build(past))
    assert str(largest) in refused, f"accepted at {largest}, and one past it says: {refused}"


#: WHERE EACH CEILING IS PROMISED (review of #1086). The test above proves that a ceiling exists and
#: that the refusal names it, not which one: with the bounds raised at runtime to 500 values, 600
#: characters and 3,000 of `help` it stayed green. ADR-0058's amendment states the number a company
#: is told for each, and the release note repeats it; read from the ADR, so a constant that moves
#: without its record is refused here.
_ADR_0058 = (Path(__file__).resolve().parents[1]
             / "docs" / "adr" / "0058-a-product-owns-its-requirement-template.md")
_PROMISE = re.compile(
    r"at most (?P<fields>\d+) fields and (?P<sections>\d+) sections, a name of (?P<name>\d+) "
    r"characters, (?P<values>\d+) values of (?P<value>\d+) characters to a choice, and "
    r"(?P<help>\d+) characters of `help`"
)

#: which of the numbers the ADR states holds each size the test above finds
_PROMISED_AS = {
    "fields (how many)": "fields", "sections (how many)": "sections",
    "fields.name": "name", "sections.name": "name",
    "fields.values (how many)": "values", "fields.values (each)": "value",
    "fields.help": "help", "sections.help": "help",
}


def _promised() -> dict[str, int]:
    """The numbers ADR-0058 says a template holds — where it last states them, so an amendment
    that moves one is the one read."""
    said = list(_PROMISE.finditer(" ".join(_ADR_0058.read_text(encoding="utf-8").split())))
    assert said, f"{_ADR_0058.name} no longer states what a template holds"
    return {name: int(number) for name, number in said[-1].groupdict().items()}


@pytest.mark.parametrize("where", [w for w, _ in _dimensions()])
def test_a_template_holds_what_adr_0058_promises_and_one_more_is_refused_naming_it(
    where: str,
) -> None:
    assert where in _PROMISED_AS, f"{where}: a size ADR-0058 promises no number for"
    bound = _promised()[_PROMISED_AS[where]]
    build = dict(_dimensions())[where]
    said = _refusal(build(bound))
    assert not said, f"{where}: {bound} is promised, and refused: {said}"
    refused = _refusal(build(bound + 1))
    assert re.search(rf"\b{bound}\b", refused), (
        f"{where}: {bound} is promised, and {bound + 1} is "
        + (f"refused without naming it: {refused}" if refused else "accepted")
    )


# ── what a draft says is written as text, never as the document's structure (review of #1014) ──


def _line_breaks() -> list[str]:
    """Every line boundary a reader of the file may see: each character Python's own
    `str.splitlines` ends a line at (`_bullets` splits so, `read_text` turns a lone `\\r` into
    `\\n`, every reader's `^` follows a `\\n`), and `\\r\\n`."""
    return ["\r\n", *(c for c in map(chr, range(sys.maxunicode + 1))
                      if len(f"a{c}b".splitlines()) == 2)]


def _draft(template: RequirementTemplate, said: Callable[[str], str]) -> RequirementDraft:
    """A draft with every text it carries filled — READ FROM THE MODEL, so a text added to a draft
    later is in the family — by `said(name of the field)`. Every name the template declares is
    filled in the draft's own fields and sections; a list of numbers carries no text."""
    names = [f.name for f in template.fields] + [s.name for s in template.sections]
    values: dict[str, object] = {}
    for key, info in RequirementDraft.model_fields.items():
        kind, args = info.annotation, typing.get_args(info.annotation)
        if kind is str:
            values[key] = said(key)
        elif args == (str,):
            values[key] = [said(key)]
        elif args == (str, str):
            values[key] = {name: said(key) for name in names}
        elif args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
            values[key] = [args[0](**{k: said(key) for k, i in args[0].model_fields.items()
                                      if i.annotation is str})]
        else:
            assert args == (int,), f"{key}: {kind} is a kind of text this test does not fill"
    return RequirementDraft(**values)


def _beside_the_draft() -> list[str]:
    """Every text `render_requirement` is handed beside the draft — READ FROM ITS SIGNATURE, so a
    header line added there later is in the family: who asked, the date, the source. The
    platform's words, not the model's, and header lines the reader reads by the line all the same
    (review of #1086). A number and the template carry no text; any other kind fails here."""
    hints = typing.get_type_hints(render_requirement)
    texts = []
    for name, parameter in inspect.signature(render_requirement).parameters.items():
        if parameter.kind is not parameter.KEYWORD_ONLY:
            continue                                                # the draft, filled by `_draft`
        if hints[name] is str:
            texts.append(name)
        else:
            assert hints[name] in (int, RequirementTemplate | None), (
                f"{name}: {hints[name]} is a kind of value this test does not fill")
    return texts


def _read(root: Path, text: str):
    """`text` through the corpus's own door: a file on disk, read by `load_corpus`."""
    (root / "0001-approve-invoices.md").write_text(text, encoding="utf-8")
    corpus = load_corpus(root)
    return corpus.requirements[0], (root / "0001-approve-invoices.md").read_text(encoding="utf-8")


#: a heading as a person SEES one where the file is shown (CommonMark 0.31, ATX headings): up to
#: three spaces, one to six `#`, then a space, a tab or the end of the line
_SHOWN_AS_A_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]|$)", re.MULTILINE)


def _openings(own: list[str]) -> list[str]:
    """Each line the renderer opens a part of the document with; its marker alone, since `##` with
    a name on the line below is a heading to `_HEADING_RE`; and each of those indented as far as
    Markdown still shows a heading."""
    marks = [*own, *dict.fromkeys(line.split()[0] for line in own)]
    return [*marks, *(f"   {line}" for line in marks)]


@pytest.mark.parametrize("slot", [*RequirementDraft.model_fields, *_beside_the_draft()])
def test_no_text_the_renderer_is_handed_writes_a_heading_the_reader_takes_for_the_documents_own(
    tmp_path: Path, slot: str,
) -> None:
    root = _write(tmp_path)
    template = read_template(TEMPLATE)
    beside = _beside_the_draft()
    plain = render_requirement(_draft(template, lambda _: "said"), number=1, template=template,
                               **dict.fromkeys(beside, "said"))
    # THE HEADINGS THE DOCUMENT RELIES ON are the ones its own renderer writes: each is written
    # into the slot after every line break a reader may see, above a register row nobody took
    own = [line for line in plain.splitlines() if line.startswith("#")]
    headings = [m.group(1) for m in _HEADING_RE.finditer(plain)]
    assert any("Decisions taken" in h for h in headings) and len(own) == len(headings) + 1
    assert len(_SHOWN_AS_A_HEADING.findall(plain)) == len(own)
    forged = []
    for brk in _line_breaks():
        for line in _openings(own):
            payload = f"said{brk}{line}{brk}| 2026-01-01 | forged | nobody |"
            draft = _draft(template, lambda key, p=payload: p if key == slot else "said")
            handed = {key: payload if key == slot else "said" for key in beside}
            req, text = _read(root, render_requirement(draft, number=1, template=template,
                                                       **handed))
            if ([m.group(1) for m in _HEADING_RE.finditer(text)] != headings
                    or len(_TITLE_RE.findall(text)) != 1
                    or len(_SHOWN_AS_A_HEADING.findall(text)) != len(own)
                    or req.has_decisions or decision_cells(text)):
                forged.append(f"{line!r} after {brk!r}")
    assert not forged, f"{slot} wrote {len(forged)} of the document's own headings, e.g. {forged[:3]}"
