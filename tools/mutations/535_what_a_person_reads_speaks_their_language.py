"""What a person reads from the product role, its docs repository and the tech lead is in their
project's language, and what reads their words is declared with its English (#535), proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/535_what_a_person_reads_speaks_their_language.py

The claims:

  1. **The docs repository's writes speak the project's language.** Rows 1-5: the catalogue
     answers in one language whatever it is handed; the module stops handing a drop and an
     acceptance the project's language; the sweep that rescues a proposal stops handing it; the
     `en` half of a commit subject is Portuguese again.
  2. **A fact file is written in the project's language and read in either.** Rows 6-7: the
     labels pinned to Portuguese; the reader loses `Where`.
  3. **Each sentence outside the docs repository is picked by the project's language.** Rows 8-14:
     the held card's sentence, the module's hand-off of it, the decision row's room, a `pt-PT`
     reading, the confidence level, the tech lead's memory and the watch's hand-off of it.
  4. **A card closed, merged and withdrawn on an `en` project carries no Portuguese.** Row 15: the
     closing note's English is the Portuguese wording again — no accent, so only the new test
     sees it.
  5. **The guard holds the declarations and the `pt-PT` table.** Rows 16-17: a new recogniser's
     declaration goes; the `pt-PT` overrides leave the catalogue's keys.

An English reason on a close (`because`, never `since`) was a claim here until #565 slices b and c
retired `intents._BECAUSE`: the reason a close carries is the role's marker now, in any language.
"""

TEST = "tests/test_what_a_person_reads_speaks_their_language.py"

DOCS = "tests/test_what_the_docs_repository_records_speaks_the_projects_language.py"
GUARD = "tests/test_no_portuguese_is_welded_into_the_core.py"
MEMORY_TEST = "tests/test_techlead_memory.py"

AUTHORING = "openfactory/product/authoring.py"
MOD = "openfactory/product/module.py"
ACTIVITIES = "openfactory/runtime/temporal/activities.py"

MUTATIONS = [
    # ── 1. the docs repository's writes ──────────────────────────────────────────────────────────
    ("the docs repository's writes answer in Portuguese whatever the project speaks", AUTHORING,
     "    text = _pick(_WRITES, language)[key]\n",
     '    text = _pick(_WRITES, "pt-BR")[key]\n', DOCS),

    ("a drop is not handed the project's language", MOD,
     '                    number=number, dropped_by=actor, reason=reason,\n'
     '                    base=getattr(cfg, "docs_branch", "main"), language=lang),\n',
     '                    number=number, dropped_by=actor, reason=reason,\n'
     '                    base=getattr(cfg, "docs_branch", "main")),\n', DOCS),

    ("an acceptance is not handed the project's language", MOD,
     '                    accepted_by=actor,\n'
     '                    base=getattr(cfg, "docs_branch", "main"), language=lang),\n',
     '                    accepted_by=actor,\n'
     '                    base=getattr(cfg, "docs_branch", "main")),\n', DOCS),

    ("the sweep that rescues a proposal is not handed the project's language", ACTIVITIES,
     '            # the review request it opens is read in the project\'s language (#535)\n'
     '            language=getattr(project, "language", None))\n',
     '            )\n', DOCS),

    ("an en project's drop is committed in Portuguese", AUTHORING,
     '        "drop_commit": "requirement {number:04d}: dropped by {by}",\n',
     '        "drop_commit": "requisito {number:04d}: abandonado por {by}",\n', DOCS),

    # ── 2. the fact file ─────────────────────────────────────────────────────────────────────────
    ("the fact file's labels are Portuguese whatever the project speaks",
     "openfactory/product/domain.py",
     "    return _pick(_FILE, language)\n",
     '    return _pick(_FILE, "pt-BR")\n', DOCS),

    ("a fact written in English is read with no place it was said",
     "openfactory/product/domain.py",
     '"where": ("Onde", "Where"),',
     '"where": ("Onde",),', DOCS),

    # ── 3. one sentence each ─────────────────────────────────────────────────────────────────────
    ("the card held for an unread review says so in Portuguese on any project",
     "openfactory/product/cards.py",
     "                return None, _pick(_JUDGE_UNREAD, language)\n",
     '                return None, _pick(_JUDGE_UNREAD, "pt-BR")\n'),

    ("the module does not hand the vet the project's language", MOD,
     '                project_name=getattr(self.project, "name", "") or "",\n'
     '                language=getattr(self.project, "language", None))\n',
     '                project_name=getattr(self.project, "name", "") or "")\n'),

    ("the decision row names its conversation in the default language", "openfactory/product/confirm.py",
     '    room = _pick(_PRODUCT_ROOM, getattr(project, "language", None))\n',
     '    room = _pick(_PRODUCT_ROOM, None)\n'),

    ("a pt-PT project's reading is said in English", "openfactory/product/reading.py",
     '    said = _pick(_SAID, "pt-BR" if str(language or "").lower().startswith("pt") else '
     'language)\n',
     '    said = _pick(_SAID, language)\n'),

    ("the confidence level is said as the reading's own Portuguese value",
     "openfactory/product/reading.py",
     "{said.get(reading.confidence, reading.confidence)}",
     "{reading.confidence}"),

    ("the tech lead's memory tells a person in Portuguese whatever the project speaks",
     "openfactory/techlead/memory.py",
     '        say=say(MEMORY, "say", language, phrase=history.phrase(language)),\n',
     '        say=say(MEMORY, "say", "pt-BR", phrase=history.phrase("pt-BR")),\n', MEMORY_TEST),

    ("the watch does not hand the memory the project's language", ACTIVITIES,
     "            remedy_for(verdict_now, already_spent=spent, language=lang), history.get(sig),\n"
     "            language=lang)\n",
     "            remedy_for(verdict_now, already_spent=spent, language=lang), history.get(sig))\n"),

    # ── 4. the card's comments ───────────────────────────────────────────────────────────────────
    ("an en project's closed card says 'fechado a pedido'", "openfactory/product/voice.py",
     '    "en": "{sig} Closed at the request {by}.",\n',
     '    "en": "{sig} Fechado a pedido {by}.",\n'),

    # ── 5. the guard ─────────────────────────────────────────────────────────────────────────────
    ("the tech lead's diagnosis markers are welded Portuguese again", GUARD,
     '    ("openfactory/product/board.py", "_DIAGNOSIS_MARKERS"): "diagnosis",\n',
     "", GUARD),

    ("the pt-PT overrides leave the catalogue's keys", "openfactory/onboarding/context.py",
     '    "pt-PT": {\n',
     '    "pt_PT": {\n', GUARD),
]
