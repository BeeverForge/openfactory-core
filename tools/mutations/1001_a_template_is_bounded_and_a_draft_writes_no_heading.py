"""#1001, the two points its review left open, proven by breaking them (review of PR #1014).

THE CLAIMS, each a rule a family test in the guard states over cases read from the code:

  1. **Everything a template holds has a ceiling, and one past it is refused naming it.** The
     guard reads every size a template can grow in from its models — how many fields, sections and
     choice values, how long each name, value and `help` is — finds where each is refused, and
     requires the refusal to name the largest size accepted. A choice's values and every `help`
     had none: 200,000 values were accepted, and each requirement that missed them then carried
     a warning of about 1.7 MB.
  2. **No text a draft carries writes a heading the reader takes for the document's own.** The
     guard reads every text slot from `RequirementDraft`, and writes into each the renderer's own
     heading lines — whole, as a bare marker, and indented as far as Markdown still shows one —
     after every line break a reader of the file may see. The file is read back through
     `load_corpus`: its headings, its title and its empty decision register must be the ones the
     renderer wrote. A template section holding `## Decisions taken during execution` used to write
     a register above the real one, which `find_decisions_table` then picked.

The guard under test is `tests/test_requirement_template.py`, whose template is read through the
YAML door and whose requirements are read from disk by the corpus.
"""

TEST = "tests/test_requirement_template.py"

TEMPLATE = "openfactory/product/template.py"
AUTHORING = "openfactory/product/authoring.py"

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
