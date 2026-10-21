"""#993, proven by breaking it — requirements imported into a product under its corpus's rules.

THE CLAIMS, each a rule a family test in the guard states over cases read from the code:

  1. **One numbering.** An import mints after the highest number the product ever used and after
     every proposal branch still on its way — the formula a proposal re-mints with.
  2. **The same slug is the same promise.** An accepted twin is never revised; a twin nobody agreed
     is retired through the writer that does it today; the register is joined by day AND text.
  3. **References travel with their numbers**, and **an import never lands a promise.**
  4. **Nothing is written over what exists** — a known term, a document — and the record is the
     one path under `.openfactory/` admitted, by its own id.
  5. **Only the command line names any path**; every other caller, the product's import inbox.
  6. **A yes lands the plan it was given, and a refused push is said once.**
  7. **The next search finds what landed.**

The guard under test is `tests/test_requirements_are_imported_under_the_corpus_rules.py`, whose git,
corpus, semaphore, documents' pass and index are real.
"""

TEST = "tests/test_requirements_are_imported_under_the_corpus_rules.py"

IMPORTING = "openfactory/product/importing.py"
AUTHORING = "openfactory/product/authoring.py"
POLICY = "openfactory/policy/context_writes.py"
CATALOG = "openfactory/actions/catalog.py"
MODULE = "openfactory/product/module.py"

MUTATIONS = [
    # ── 1. one numbering ───────────────────────────────────────────────────────────────────────
    ("the first free number forgets the proposal branches still on their way, so an import files "
     "a second REQ-N beside a proposal that lands after it", AUTHORING,
     "    return max(int(base_next), max(unlanded, default=0) + 1)",
     "    return int(base_next)"),

    ("the import mints from the folder's own numbers, colliding with the product's", IMPORTING,
     "            out[r.number] = nxt\n            nxt += 1",
     "            out[r.number] = r.number"),

    # ── 2. the same slug is the same promise ───────────────────────────────────────────────────
    ("a new text for an ACCEPTED requirement revises it — a promise retired by a file from "
     "outside", IMPORTING,
     "        elif any(t.status == ACCEPTED for t in twins[r.number]):\n"
     "            agreed = next(",
     "        elif False:\n            agreed = next("),

    ("a revision lands beside the text it replaces and never marks it, so one promise stands "
     "under two numbers", IMPORTING,
     "                    root, folder, [n for n in row.replaces if n not in minted], "
     "by=row.number)",
     "                    root, folder, [], by=row.number)"),

    ("the same text word for word is minted again", IMPORTING,
     "            if promise_of(r.body, None) == promise_of(t.body, None):",
     "            if False:"),

    ("the register is joined by text alone, so the same decision on another day is lost",
     IMPORTING,
     "            if (day.strip(), _fold(decided).lower()) not in held]",
     "            if _fold(decided).lower() not in {t for _d, t in held}]"),

    # ── 3. references, and promises ────────────────────────────────────────────────────────────
    ("references stay in the folder's numbering, pointing at the product's unrelated "
     "requirements", IMPORTING,
     "    return _REF.sub(lambda m: f\"REQ-{renumbered.get(int(m.group(1)), "
     "int(m.group(1))):04d}\", text)",
     "    return text"),

    ("a file the folder marks accepted lands as a promise nobody here made", IMPORTING,
     "    return OBSERVED if r.status == OBSERVED else PROPOSED",
     "    return r.status"),

    # ── 4. nothing written over what exists ────────────────────────────────────────────────────
    ("a known term is rewritten by the folder's version of it", IMPORTING,
     "        if domain.get(fact.term) is not None or fact.term.strip().lower() in taken:",
     "        if fact.term.strip().lower() in taken:"),

    ("a document is written over — or through — the file already at its path", IMPORTING,
     "        if not os.path.lexists(here):\n            out.documents.append(Placed(NEW, name, "
     "dest))",
     "        if True:\n            out.documents.append(Placed(NEW, name, dest))"),

    ("the import's exception admits anything under the platform's directory, the preview's "
     "shape included", POLICY,
     "    rest = [p for p in paths if not (record and _clean(p).startswith(record))]",
     "    rest = [p for p in paths if not _clean(p).startswith(IMPORTS)]"),

    # ── 5. where a folder may come from ────────────────────────────────────────────────────────
    ("any caller of the API names any path on the server, and its files reach a context "
     "repository", CATALOG,
     "    if getattr(by, \"via\", \"\") == \"cli\":\n        return Path(raw).expanduser(), None",
     "    if True:\n        return Path(raw).expanduser(), None"),

    ("the folder is read, and its plan shown, before the person's right to import is asked",
     CATALOG,
     "    if not await asyncio.to_thread(lambda: may_act(proj, by.id, via=by.via or \"api\")):\n"
     "        if not _said_yes(yes):",
     "    if False:\n        if not _said_yes(yes):"),

    # ── 6. the plan said yes to, and one push ──────────────────────────────────────────────────
    ("a yes lands whatever the plan has become since it was shown", IMPORTING,
     "        if token and token != the_plan.token:",
     "        if False:"),

    ("a refused push is tried again blindly", IMPORTING,
     "        rc, out = _git([\"push\", clone_url, f\"HEAD:{base}\"], cwd=tmp)\n        if rc != 0:\n"
     "            # SAID, NEVER RETRIED BLINDLY.",
     "        rc, out = _git([\"push\", clone_url, f\"HEAD:{base}\"], cwd=tmp)\n        if rc != 0:\n"
     "            rc, out = _git([\"push\", clone_url, f\"HEAD:{base}\"], cwd=tmp)\n"
     "        if rc != 0:\n"
     "            # SAID, NEVER RETRIED BLINDLY."),

    # ── 7. the next search ─────────────────────────────────────────────────────────────────────
    ("the product's index is never brought up to what the import landed", MODULE,
     "        if result.ok and not result.existed:\n"
     "            self._refresh_after_import(list(getattr(result, \"landed\", []) or []))",
     "        if False:\n"
     "            self._refresh_after_import(list(getattr(result, \"landed\", []) or []))"),
]
