"""A proposal tells each conflict as the kind the drafter recorded (#676), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/a_conflict_is_told_as_its_kind.py

The claims, each a row:
  1. each kind has its own words, and only a contradiction is called a change of mind;
  2. a proposal with several kinds says each under its own words;
  3. the engine hands the drafter's kind to the frame;
  4. an unknown kind and bare text are told as a contradiction.
"""

TEST = "tests/test_a_conflict_is_told_as_its_kind.py"
VOICE = "openfactory/product/voice.py"
ENGINE = "openfactory/product/engine.py"

MUTATIONS = [
    # 1. each kind its own words
    ("TODAY'S RUN: every kind is told as a contradiction", VOICE,
     "        grouped.setdefault(kind if kind in words else strongest, []).append(line)",
     "        grouped.setdefault(strongest, []).append(line)"),
    ("a narrowing is called a change of mind", VOICE,
     '                    "Ou seja, acrescenta ao que já existe sem desfazer nada."),',
     '                    "Ou seja, é uma mudança de ideia."),'),
    ("a dependency is told in a duplicate's words, in English", VOICE,
     '        "depends_on": ("this builds on something we already decided:",\n'
     '                       "So it only works together with what is already there — if that changes, "\n'
     '                       "this changes too."),',
     '        "depends_on": ("this repeats something we already decided:",\n'
     '                       "So it may already be promised — worth checking before writing it down "\n'
     '                       "again."),'),

    # 2. several kinds in one proposal
    ("several kinds are told under the first kind's words", VOICE,
     "    for kind in (k for k in words if k in grouped):\n",
     "    grouped = {next(iter(grouped)): [l for ls in grouped.values() for l in ls]}\n"
     "    for kind in (k for k in words if k in grouped):\n"),
    ("a kind's closing words are left out", VOICE,
     '        parts.append(f"{lead if not parts else lead[:1].upper() + lead[1:]}\\n{items}\\n\\n{coda}")',
     '        parts.append(f"{lead if not parts else lead[:1].upper() + lead[1:]}\\n{items}")'),

    # 3. the engine hands the kind on
    ("TODAY'S RUN: the engine drops the drafter's kind", ENGINE,
     "        conflicts=[(c.kind, _conflict_line(c, lang)) for c in draft.conflicts], language=lang))",
     "        conflicts=[_conflict_line(c, lang) for c in draft.conflicts], language=lang))"),

    # 4. what is not known is told as the strongest
    ("an unknown kind is told as the mildest", VOICE,
     "        grouped.setdefault(kind if kind in words else strongest, []).append(line)",
     '        grouped.setdefault(kind if kind in words else "narrows", []).append(line)'),
    ("bare text is told as the mildest", VOICE,
     "        kind, line = c if isinstance(c, tuple) else (strongest, c)",
     '        kind, line = c if isinstance(c, tuple) else ("narrows", c)'),
]
