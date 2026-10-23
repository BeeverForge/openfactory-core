"""#1001, the two points its review left open, proven by breaking them (review of PR #1014).

THE CLAIMS, each a rule a family test in the guard states over cases read from the code:

  1. **Everything a template holds has a ceiling, and one past it is refused naming it.** The
     guard reads every size a template can grow in from its models — how many fields, sections and
     choice values, how long each name, value and `help` is — finds where each is refused, and
     requires the refusal to name the largest size accepted. A choice's values and every `help`
     had none: 200,000 values were accepted, and each requirement that missed them then carried
     a warning of about 1.7 MB.
  1b. **…and each ceiling is the number ADR-0058 promises** (review of PR #1086). The guard reads
     the numbers from the ADR's amendment and holds every size of claim 1 at its own: accepted at
     it, and one past it refused naming it. Claim 1's test finds a ceiling and its name, not which
     one: with three of them raised at runtime (500 values, 600 characters, 3,000 of `help`) it
     stayed green. Every row of 1b is aimed at this test alone; the last moves the ADR's number and
     not the code's.
  2. **No text the renderer is handed writes a heading the reader takes for the document's own.**
     The guard reads every text slot from `RequirementDraft`, and every text `render_requirement`
     takes beside the draft from its signature (`asked_by`, `date`, `source`: header lines the
     platform fills, review of PR #1086), and writes into each the renderer's own heading lines —
     whole, as a bare marker, and indented as far as Markdown still shows one — after every line
     break a reader of the file may see. The file is read back through `load_corpus`: its
     headings, its title and its empty decision register must be the ones the renderer wrote. A
     template section holding `## Decisions taken during execution` used to write a register above
     the real one, which `find_decisions_table` then picked.

The guard under test is `tests/test_requirement_template.py`, whose template is read through the
YAML door and whose requirements are read from disk by the corpus.
"""

TEST = "tests/test_requirement_template.py"
PROMISES = f"{TEST}::test_a_template_holds_what_adr_0058_promises_and_one_more_is_refused_naming_it"

TEMPLATE = "openfactory/product/template.py"
AUTHORING = "openfactory/product/authoring.py"
ADR = "docs/adr/0058-a-product-owns-its-requirement-template.md"

MUTATIONS = [
    # ── 1. what a template holds is bounded ────────────────────────────────────────────────────
    ("a choice takes any number of values, and a requirement that misses them carries all of them "
     "in its warning", TEMPLATE,
     "        if len(values) > MAX_VALUES:\n",
     "        if False:\n"),

    ("a choice's value is as long as it likes", TEMPLATE,
     '        if (longest := max(values, key=len, default="")) and len(longest) > MAX_VALUE:\n',
     "        if False:\n"),

    ("`help` has no end, for a field and for a section", TEMPLATE,
     "    if len(value) > MAX_HELP:\n",
     "    if False:\n"),

    ("a field's `help` is a plain string again, past the bound", TEMPLATE,
     '    listed: bool = False\n    help: Help = ""\n',
     '    listed: bool = False\n    help: str = ""\n'),

    ("a section's `help` is a plain string again, past the bound", TEMPLATE,
     '    required: bool = False\n    help: Help = ""\n',
     '    required: bool = False\n    help: str = ""\n'),

    # ── 1b. …at the numbers ADR-0058 promises ──────────────────────────────────────────────────
    ("a choice takes 500 values, where ADR-0058 promises 50", TEMPLATE,
     "MAX_VALUES = 50\n", "MAX_VALUES = 500\n", PROMISES),

    ("a choice's value runs to 600 characters, where ADR-0058 promises 60", TEMPLATE,
     "MAX_VALUE = 60\n", "MAX_VALUE = 600\n", PROMISES),

    ("`help` runs to 3,000 characters, where ADR-0058 promises 300", TEMPLATE,
     "MAX_HELP = 300\n", "MAX_HELP = 3000\n", PROMISES),

    ("a template holds 300 fields, where ADR-0058 promises 30", TEMPLATE,
     "Field(default_factory=list, max_length=30)", "Field(default_factory=list, max_length=300)",
     PROMISES),

    ("a template holds 200 sections, where ADR-0058 promises 20", TEMPLATE,
     "Field(default_factory=list, max_length=20)", "Field(default_factory=list, max_length=200)",
     PROMISES),

    ("a name runs to 100 characters, where ADR-0058 promises 60", TEMPLATE,
     "[A-Za-z0-9 /&'().-]{0,58}", "[A-Za-z0-9 /&'().-]{0,98}", PROMISES),

    ("a choice takes 49 values, one fewer than ADR-0058 promises", TEMPLATE,
     "MAX_VALUES = 50\n", "MAX_VALUES = 49\n", PROMISES),

    ("ADR-0058 promises 40 values to a choice, and the code keeps 50", ADR,
     "50 values of 60 characters to a choice", "40 values of 60 characters to a choice",
     PROMISES),

    # ── 2. a draft's text is written as text ───────────────────────────────────────────────────
    ("the title is written as it came, and a line break in it opens a heading under the title",
     AUTHORING,
     '        f"# REQ-{number:04d} — {_one_line(draft.title)}",\n',
     '        f"# REQ-{number:04d} — {draft.title}",\n'),

    ("a template field's value is written as it came, so a line break in it ends the header",
     AUTHORING,
     '            value = _one_line(draft.fields.get(f.name, "")) or EMPTY\n',
     '            value = draft.fields.get(f.name, "").strip() or EMPTY\n'),

    ("*Why* is written as it came (the review: `draft.why` already has the same flaw)", AUTHORING,
     '_as_text(draft.why) or "(not stated)"',
     'draft.why.strip() or "(not stated)"'),

    ("a template section's text is written as it came — the review's fake register", AUTHORING,
     '            text = _as_text(draft.sections.get(sec.name, "")) or "(not stated)"\n',
     '            text = draft.sections.get(sec.name, "").strip() or "(not stated)"\n'),

    ("a criterion is written as it came", AUTHORING,
     '    lines += [f"- [ ] {_one_line(c)}" for c in draft.must_be_true]',
     '    lines += [f"- [ ] {c}" for c in draft.must_be_true]'),

    ("an out-of-scope line is written as it came", AUTHORING,
     '    lines += [f"- {_one_line(c)}" for c in draft.out_of_scope]',
     '    lines += [f"- {c}" for c in draft.out_of_scope]'),

    ("an affected path is written as it came", AUTHORING,
     '    lines += [f"- `{_one_line(c)}`" for c in draft.affects]',
     '    lines += [f"- `{c}`" for c in draft.affects]'),

    ("an open question is written as it came", AUTHORING,
     '        lines += [f"- {_one_line(q)}" for q in draft.questions]\n',
     '        lines += [f"- {q}" for q in draft.questions]\n'),

    ("a conflict's explanation is written as it came", AUTHORING,
     "{ref} — {_one_line(c.explanation)}",
     "{ref} — {c.explanation}"),

    ("a conflict's kind is written as it came", AUTHORING,
     '- **{_one_line(c.kind)}** {ref}',
     '- **{c.kind}** {ref}'),

    ("who asked is written as it came, and a line break in a name ends the header", AUTHORING,
     '        f"- **Asked by:** {_one_line(asked_by) or UNRECORDED}",\n',
     '        f"- **Asked by:** {asked_by or UNRECORDED}",\n'),

    ("the date is written as it came", AUTHORING,
     '        f"- **Date:** {_one_line(date) or UNRECORDED}",\n',
     '        f"- **Date:** {date or UNRECORDED}",\n'),

    ("the source is written as it came", AUTHORING,
     "    if source := _one_line(source):\n",
     "    if source:\n"),

    ("one line keeps its line breaks", AUTHORING,
     '    return " ".join((text or "").split())\n',
     '    return (text or "").strip()\n'),

    ("a section's text keeps a line that opens a heading", AUTHORING,
     '    return "\\n".join(_OPENS_A_HEADING.sub(r"\\1\\\\", line)\n',
     '    return "\\n".join(line\n'),

    ("a section's text is split at `\\n` alone, so a lone `\\r` — which `read_text` turns into "
     "`\\n` — carries a heading past the escape", AUTHORING,
     '                     for line in (text or "").strip().splitlines())\n',
     '                     for line in (text or "").strip().split("\\n"))\n'),

    ("an indented heading is not escaped — the reader skips it, a person reading the file sees it",
     AUTHORING,
     '_OPENS_A_HEADING = re.compile(r"^([ \\t]*)(?=#+(?:\\s|$))")\n',
     '_OPENS_A_HEADING = re.compile(r"^()(?=#+(?:\\s|$))")\n'),

    ("a bare `##` is not escaped, and `_HEADING_RE` reads the line below it as a heading",
     AUTHORING,
     '_OPENS_A_HEADING = re.compile(r"^([ \\t]*)(?=#+(?:\\s|$))")\n',
     '_OPENS_A_HEADING = re.compile(r"^([ \\t]*)(?=#+\\s)")\n'),
]
