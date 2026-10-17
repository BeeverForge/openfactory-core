"""A card the sizer splits keeps what its author wrote (#624).

Claims, each held by a test in TEST (or the provenance file, where named):

  · each child carries the parent's sections the sizer did not rewrite, under a heading that names
    the parent, one level down so the child's own sections stay its own — and no empty heading;
  · the parent's objective and criteria are left out, by what their headings MEAN;
  · the carried block is a field the job's brief (fenced, counted in its marker) and both
    reviewer prompts render;
  · the block is cut to the row's own `body_limit`, with an open fence closed and a line that
    says where the rest is, and the cut is logged.
"""

TEST = "tests/test_a_card_the_sizer_splits_keeps_what_its_author_wrote.py"
ACT = "openfactory/runtime/temporal/activities.py"
PARSE = "openfactory/adapters/tracker/parse.py"
BASE = "openfactory/adapters/agent/base.py"
HARNESS = "openfactory/adapters/reviewer/harness.py"
CLAUDE = "openfactory/adapters/reviewer/claude_code.py"
PROVENANCE = "tests/test_provenance_in_the_brief.py"

MUTATIONS = [
    # ── carried, under a heading that names the parent ───────────────────────────────────────────
    ("the split carries nothing of its parent again", ACT,
     "_child_body(child, parent_ref, i + 1, n, carried=carried,",
     "_child_body(child, parent_ref, i + 1, n, carried=('', []),"),

    ("the parent's objective is carried beside the sizer's", PARSE,
     '_REWRITTEN_BY_THE_SIZER = ("objective", "acceptance criteria")',
     '_REWRITTEN_BY_THE_SIZER = ("acceptance criteria",)'),

    ("the parent's criteria are carried beside the sizer's", PARSE,
     '_REWRITTEN_BY_THE_SIZER = ("objective", "acceptance criteria")',
     '_REWRITTEN_BY_THE_SIZER = ("objective",)'),

    ("the exclusion reads the heading as written, not by its meaning", PARSE,
     "            if _CANONICAL.get(norm, norm) not in _REWRITTEN_BY_THE_SIZER]",
     "            if written.lower() not in _REWRITTEN_BY_THE_SIZER]"),

    ("the carried sections are written at the child's own level", ACT,
     '*(f"### {heading}\\n{text}" for heading, text in sections if text)])',
     '*(f"## {heading}\\n{text}" for heading, text in sections if text)])'),

    ("the heading no longer names the parent", ACT,
     'lead = (f"\\n\\n## {FROM_THE_PARENT} ({parent_ref})\\n"',
     'lead = (f"\\n\\n## {FROM_THE_PARENT}\\n"'),

    ("the heading is written over an empty block", ACT,
     "    if not block:\n        return own + tail\n",
     "    if not block and False:\n        return own + tail\n"),

    # ── it reaches the job and the reviewer ──────────────────────────────────────────────────────
    ("the parser no longer fills the field", PARSE,
     "                          if norm.startswith(carried) and text), None),",
     "                          if False), None),"),

    ("the brief no longer renders it", BASE,
     "    if t.from_parent:\n        parts += [",
     "    if False:\n        parts += ["),

    ("the brief renders it outside its fence", BASE,
     '"criteria; this card delivers only its own"] + _fenced(nonce, t.from_parent)',
     '"criteria; this card delivers only its own", t.from_parent]',
     PROVENANCE),

    ("the brief's marker is drawn without looking at it", BASE,
     "*criteria, *t.out_of_scope, t.from_parent)",
     "*criteria, *t.out_of_scope)",
     PROVENANCE),

    ("the harness reviewer no longer sees it", HARNESS,
     '    if t.from_parent:\n        parts.append(f"\\n## From the parent card\\n{t.from_parent}")',
     '    if False:\n        parts.append(f"\\n## From the parent card\\n{t.from_parent}")'),

    ("the claude reviewer no longer sees it", CLAUDE,
     '        if t.from_parent:\n            parts.append(',
     '        if False:\n            parts.append('),

    # ── within the tracker's limit ───────────────────────────────────────────────────────────────
    ("the carried block is never cut", ACT,
     "    if len(own) + len(lead) + len(block) + len(tail) <= limit:",
     "    if True:"),

    ("the cut line no longer links the parent", ACT,
     'where = f"{parent_ref}: {parent_url}" if parent_url else parent_ref',
     "where = parent_ref"),

    # re-pinned 2026-10-17: the closer is the opener's own marker, `_open_fence` (review of 83256a1)
    ("a fence the cut left open is not closed", ACT,
     "        kept = \"\\n\".join([*lines, *([opener] if (opener := _open_fence(lines)) else [])])"
     ".rstrip()",
     "        kept = \"\\n\".join(lines).rstrip()"),

    ("the split ignores the row's own limit", ACT,
     'limit = getattr(tracker, "body_limit", None) or CARD_BODY_LIMIT',
     "limit = CARD_BODY_LIMIT"),

    # ── the edges of the bound (review of 83256a1) ───────────────────────────────────────────────
    ("a child with no room to carry is written over the limit anyway", ACT,
     "    if budget <= 0:\n        # NO ROOM",
     "    if False:\n        # NO ROOM"),

    ("any fence line closes the open fence, of either kind", ACT,
     "        elif marker[0] == opener[0] and len(marker) >= len(opener) and not rest.strip():",
     "        elif not rest.strip():"),

    ("a shorter fence closes a longer one", ACT,
     "        elif marker[0] == opener[0] and len(marker) >= len(opener) and not rest.strip():",
     "        elif marker[0] == opener[0] and not rest.strip():"),

    ("the closer may push the kept text over the budget", ACT,
     "        if len(kept) <= budget:\n            return kept\n        lines.pop()",
     "        return kept"),

    ("one line longer than the budget is cut mid-word", ACT,
     '                lines.append(head.rsplit(" ", 1)[0] if " " in head else head)',
     "                lines.append(head)"),

    ("the parent's front matter is carried as prose", PARSE,
     "    parser has a name for it, because the parent is closed and the child is all anybody "
     "reads.\"\"\"\n    _fm, md = _split_front_matter(body or \"\")",
     "    parser has a name for it, because the parent is closed and the child is all anybody "
     "reads.\"\"\"\n    md = body or \"\""),

    ("an empty parent section is carried as an empty heading", ACT,
     '*(f"### {heading}\\n{text}" for heading, text in sections if text)])',
     '*(f"### {heading}\\n{text}" for heading, text in sections)])'),

    ("the cut is not logged", ACT,
     '        "OPENFACTORY_SPLIT_CARRIED_CUT %s — kept %d of %d characters',
     '        "SPLIT_CARRIED %s — kept %d of %d characters'),

    # ── what the no-room branch and the fence rules promise (re-review of a3558546) ──────────────
    ("a child with no room to carry loses its Auto-split line", ACT,
     "        return own + tail\n    kept = _markdown_within(block, budget)",
     "        return own\n    kept = _markdown_within(block, budget)"),

    ("a child with no room to carry is cut without a word in the log", ACT,
     '            "OPENFACTORY_SPLIT_CARRIED_CUT %s — kept 0 of %d characters',
     '            "SPLIT_CARRIED %s — kept 0 of %d characters'),

    ("a fence line with text after it closes the fence", ACT,
     "        elif marker[0] == opener[0] and len(marker) >= len(opener) and not rest.strip():",
     "        elif marker[0] == opener[0] and len(marker) >= len(opener):"),

    ("an indented fence is not read as one", ACT,
     'found = _re_module.match(r" {0,3}(`{3,}|~{3,})(.*)$", line)',
     'found = _re_module.match(r"(`{3,}|~{3,})(.*)$", line)'),

    ("four spaces of indented code are read as a fence", ACT,
     'found = _re_module.match(r" {0,3}(`{3,}|~{3,})(.*)$", line)',
     'found = _re_module.match(r"\\s*(`{3,}|~{3,})(.*)$", line)'),
    # NOT A CUT: `budget <= 0` → `budget < 0` is an equivalent mutant — at a budget of 0
    # `_markdown_within` keeps "" and the body is exactly `limit` characters (re-review of a3558546)
]
