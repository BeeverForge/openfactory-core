# ADR 0058 — A product owns its requirement template

- **Status:** Accepted (implemented with #1001)
- **Date:** 2026-10-21
- **Implements:** #1001.
- **Relates to:** ADR-0054 D7, which put a product's card template and rubric in its context
  repository; ADR-0019, whose rule that parsing never raises this keeps.

## Context

Every requirement has the core's shape: the header lines `Status`, `Asked by`, `Date`, `Supersedes`
(and `Source`), and the sections *Why*, *What must be true*, *Out of scope*, *Affects*, *Open
questions* and the decision register. A company that runs the factory has more it must record — a
business owner, its own priority scheme, a regulatory-impact flag, a section its approval board
reads — and it had two bad choices: put it in the free text, where nothing reads or checks it, or
fork the format.

The Prototype Builder met this first: a company's template had to reach the requirements it hands
off. Writing a second copy of the format there was refused; the format is the core's.

## Decision

**D1. The template is a file in the requirements directory: `template.yaml`**, beside the
`NNNN-*.md` files it describes, committed by the product like `cards/template.md` (ADR-0054 D7). It
has two lists:

- `fields`: `name`, `type` (`text`, `choice` with `values`, or `date` as `YYYY-MM-DD`), `required`,
  `listed`, `help`. A field is a header line, `- **Name:** value`, written after the core's own.
- `sections`: `name`, `required`, `help`. A section is `## Name`, written after *Open questions* and
  before the decision register.

**D2. The core's own never change.** A field may not take the name of a header line the core reads
(`Status`, `Asked by`, `Date`, `Supersedes`, `Source`, `Evidence`, `Observed at commit`) nor a
section the name of one it writes. Statuses, provenance and the decisions register stay the core's;
a template that could move them would make a requirement mean two things. Unknown keys, repeated
names and a `choice` with no values are refused, by name.

**D3. A template that cannot be used is a finding, and the core's shape applies.** `template-refused`
(warn) names why. A requirement that does not meet its template is a `warn` — `field-missing`,
`field-value`, `section-missing` — never an error: a requirement written before the template is
still a requirement.

**D4. The reader and the writer share it.** `load_corpus` reads `template.yaml` from the directory it
loads; `Requirement.fields` and `.sections` hold what the file carries; `Corpus.template` holds the
template. `render_requirement(template=)` writes `RequirementDraft.fields`/`.sections`, `—` for a
field with no value and `(not stated)` for a section, so the file says what is missing and nothing
is invented. `propose_requirement` reads the template from the clone it writes into, so what is
written is what the corpus reads back. Names the template does not declare are ignored.

**D5. `listed` fields join the role's index** as columns after the core's own. Without a template the
index is what it was.

**D6. The field matcher ends where the label ends.** `_field_re` matched a name as a prefix, so
`- **Date of go-live:**` above `- **Date:**` was read as the date. A label now ends at a colon or at
the closing bold marker.

## Consequences

- A company's fields are checked and visible to the role; the Prototype Builder writes and validates
  its handoff with these same writers and readers.
- No new status, no new kind of file, no migration: a product with no `template.yaml` is unchanged.
- Not here: the role's drafting prompt does not yet ask for a template's fields (a follow-up); a
  caller that builds a `RequirementDraft` fills them.
