"""A product's own requirement template: the company's fields and sections (#1001, ADR-0058).

Every requirement has the core's shape — the header lines (`Status`, `Asked by`, `Date`,
`Supersedes`, `Source`) and the sections *Why*, *What must be true*, *Out of scope*, *Affects*,
*Open questions* and the decision register. A company has more: a business owner, its own priority
scheme, a regulatory-impact flag, a cost centre, a section its approval board reads. This is where
it says so, in the requirements directory it already keeps — `template.yaml` beside the
`NNNN-*.md` files, the way a product commits `cards/template.md` (ADR-0054 D7):

    fields:
      - name: Business owner          # the header line:  - **Business owner:** Ana Lima
        required: true
        listed: true                  # shown in the role's index of the corpus
      - name: Priority
        type: choice
        values: [Must, Should, Could]
      - name: Go-live
        type: date                    # YYYY-MM-DD
    sections:
      - name: Regulatory impact       # a section:  ## Regulatory impact
        required: true
        help: Which regulation applies, and who reviews it.

THE CORE'S OWN NEVER CHANGE. A field may not take the name of a header line the core reads, nor a
section the name of one it writes: the statuses, the provenance and the decision register are the
core's, and a template that could move them would make a requirement mean two things. Anything else
is the company's.

Like the rest of this package, nothing here raises on a file a person edited by hand: a template
that
cannot be used is refused by name and the core's own shape is used instead, and a requirement that
does not meet its template is a finding, never a crash (corpus.py's rule 1).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from openfactory.util import yaml_io

#: the product's template, inside the directory of the requirements it describes
TEMPLATE_FILE = "template.yaml"

#: the header lines the core reads and writes — a company's field may not be one of them
RESERVED_FIELDS = frozenset(
    {"status", "asked by", "date", "supersedes", "source", "evidence", "observed at commit"}
)
#: the sections the core writes — a company's section may not be one of them
RESERVED_SECTIONS = frozenset(
    {
        "why",
        "what must be true",
        "out of scope",
        "affects",
        "open questions",
        "conflicts raised while drafting",
        "decisions taken during execution",
    }
)

#: what a field with no value is written as, and read back as nothing
EMPTY = "—"

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 /&'().-]{0,58}[A-Za-z0-9)]$|^[A-Za-z0-9]$")

_STRICT = ConfigDict(extra="forbid")

#: WHAT A TEMPLATE MAY HOLD, beside the 60 characters of a name and the 30 fields and 20 sections
#: of the lists (review of #1014). A choice's values and every `help` had no end: a choice of
#: 200,000 values was accepted, and each requirement whose value missed it then carried a warning
#: of about 1.7 MB naming them all. Labels and a sentence of help, not documents: one past any bound
#: refuses the template by name, and the core's own shape applies (`load_template`).
MAX_VALUES = 50
MAX_VALUE = 60
MAX_HELP = 300


def _short_help(value: str) -> str:
    if len(value) > MAX_HELP:
        raise ValueError(
            f"is {len(value)} characters, and `help` is at most {MAX_HELP}: say in a sentence or "
            f"two what to write here"
        )
    return value


#: what a person reads beside a field or a section when they fill it in
Help = Annotated[str, AfterValidator(_short_help)]


class TemplateField(BaseModel):
    """A header line a requirement of this product carries: `- **Name:** value`."""

    model_config = _STRICT

    name: str
    type: Literal["text", "choice", "date"] = "text"
    #: the values a `choice` may take
    values: list[str] = Field(default_factory=list)
    required: bool = False
    #: shown in the role's index of the corpus
    listed: bool = False
    help: Help = ""

    @field_validator("name")
    @classmethod
    def _a_name_that_reads_as_a_label(cls, value: str) -> str:
        name = " ".join(value.split())
        if not _NAME.match(name):
            raise ValueError(
                "must be 1 to 60 letters, digits, spaces or / & ' ( ) . - — a label, not a sentence"
            )
        if name.lower() in RESERVED_FIELDS:
            raise ValueError(f"{name!r} is a header line the core reads and writes")
        return name

    @field_validator("values")
    @classmethod
    def _a_choice_a_person_reads_at_a_glance(cls, values: list[str]) -> list[str]:
        if len(values) > MAX_VALUES:
            raise ValueError(
                f"lists {len(values)} values, and a choice takes at most {MAX_VALUES}: keep the "
                f"ones a requirement may carry, or make the field `text`"
            )
        if (longest := max(values, key=len, default="")) and len(longest) > MAX_VALUE:
            raise ValueError(
                f"holds a value of {len(longest)} characters, and a value is at most {MAX_VALUE}: "
                f"write it as a label and say the rest in `help`"
            )
        return values

    def check(self, value: str) -> str:
        """Why `value` does not suit this field, or `""`."""
        if not value:
            return ""
        if self.type == "choice" and value not in self.values:
            return f"is {value!r}, not one of {', '.join(self.values)}"
        if self.type == "date" and not _DAY.match(value):
            return f"is {value!r}, not a date as YYYY-MM-DD"
        return ""


class TemplateSection(BaseModel):
    """A section a requirement of this product carries: `## Name`."""

    model_config = _STRICT

    name: str
    required: bool = False
    help: Help = ""

    @field_validator("name")
    @classmethod
    def _a_name_that_reads_as_a_heading(cls, value: str) -> str:
        name = " ".join(value.split())
        if not _NAME.match(name):
            raise ValueError("must be 1 to 60 letters, digits, spaces or / & ' ( ) . -")
        if name.lower() in RESERVED_SECTIONS:
            raise ValueError(f"{name!r} is a section the core writes")
        return name


class RequirementTemplate(BaseModel):
    model_config = _STRICT

    fields: list[TemplateField] = Field(default_factory=list, max_length=30)
    sections: list[TemplateSection] = Field(default_factory=list, max_length=20)

    def model_post_init(self, __context: object) -> None:
        for kind, items in (("field", self.fields), ("section", self.sections)):
            names = [i.name.lower() for i in items]
            twice = sorted({n for n in names if names.count(n) > 1})
            if twice:
                raise ValueError(f"{kind} names written more than once: {twice}")
        for f in self.fields:
            if f.type == "choice" and not f.values:
                raise ValueError(f"field {f.name!r} is a choice with no values")
            if f.type != "choice" and f.values:
                raise ValueError(f"field {f.name!r} lists values but is not a choice")

    @property
    def empty(self) -> bool:
        return not self.fields and not self.sections

    def listed(self) -> list[TemplateField]:
        return [f for f in self.fields if f.listed]

    def problems_of(self, values: dict[str, str], present: set[str]) -> list[tuple[str, str]]:
        """What a requirement does not meet: `(code, sentence)` per problem. `values` are its
        fields as written (`""` for none), `present` the lower-cased headings it has."""
        found: list[tuple[str, str]] = []
        for f in self.fields:
            value = values.get(f.name, "")
            if f.required and not value:
                found.append(
                    ("field-missing", f"the field {f.name!r} is required and has no value")
                )
            elif (why := f.check(value)):
                found.append(("field-value", f"the field {f.name!r} {why}"))
        for s in self.sections:
            if s.required and s.name.lower() not in present:
                found.append(("section-missing", f"the section {s.name!r} is required and missing"))
        return found


def read_template(text: str) -> RequirementTemplate:
    """The template in `text`; raises `ValueError` saying what is wrong."""
    try:
        raw = yaml_io.load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"cannot be read as YAML: {' '.join(str(error).split())[:160]}") from None
    if raw is None:
        return RequirementTemplate()
    if not isinstance(raw, dict):
        raise ValueError("must be a mapping with `fields` and `sections`")
    try:
        return RequirementTemplate.model_validate(raw)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "(the file)"
        raise ValueError(f"{where}: {first['msg'].removeprefix('Value error, ')}") from None


def load_template(requirements_dir: str | Path) -> tuple[RequirementTemplate | None, str]:
    """A product's template from its requirements directory: `(template, "")`; `(None, "")` when
    it has none; `(None, why)` when it has one that cannot be used — which the caller logs by name,
    and carries on with the core's own shape."""
    path = Path(requirements_dir) / TEMPLATE_FILE
    if not path.is_file():
        return None, ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return None, f"{TEMPLATE_FILE} cannot be read: {error}"
    try:
        found = read_template(text)
    except ValueError as error:
        return None, f"{TEMPLATE_FILE} is refused: {error}"
    return (None if found.empty else found), ""
