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
  8. **An import never changes an agreed requirement** (review of PR #999): a text whose slug or
     own history reaches an accepted one is kept beside it; the folder's dead texts touch nothing;
     a text nobody agreed that the folder's history replaced is retired, never left standing.
  9. **What `land` leaves is checked before the commit**: no error the base did not hold, no
     agreed requirement retired — or nothing is committed, the findings named.
 10. **Nothing is made or read through a link of the product**, and **what is left out counts
     toward the bound**, its paths cut to a length.

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
    # RE-PINNED 2026-10-21 (review of PR #999): the accepted twin is found with every other agreed
    # requirement a text would change, in `_agreed`, instead of inline in `plan`'s rows
    ("a new text for an ACCEPTED requirement revises it — a promise retired by a file from "
     "outside", IMPORTING,
     "        if kept is not None:\n            out[r.number] = kept",
     "        if False:\n            out[r.number] = kept"),

    # ── 2b. an import never changes an agreed requirement (review of PR #999) ──────────────────
    ("a text whose own history reaches an accepted requirement is not kept beside it — its "
     "successor retires the promise (the review's REQ-0007)", IMPORTING,
     "                     if t.is_promise), None)\n        if kept is not None:",
     "                     if t.is_promise), None)\n"
     "        kept = next((t for t in twins.get(r.number, []) if t.is_promise), None)\n"
     "        if kept is not None:"),

    ("the folder's history is followed one step only, so a chain's live text never meets the "
     "promise its first text holds", IMPORTING,
     "        elif n in folder and not folder[n].is_live:\n"
     "            todo += folder[n].supersedes",
     "        elif False:\n            todo += folder[n].supersedes"),

    ("a folder's dead text claims what its `Supersedes:` names in the product, so a retired twin "
     "of a promise lands a supersession nobody marked", IMPORTING,
     "        own = sorted({renumbered[n] for n in r.supersedes\n"
     "                      if n in renumbered and renumbered[n] in minted})",
     "        own = sorted({renumbered[n] for n in r.supersedes if n in renumbered})"),

    ("a live text the folder's history makes a successor of a text nobody agreed leaves it "
     "standing — two versions live", IMPORTING,
     "            retired = {t.number for t in [*twins[r.number], *_lineage(r, brought, same)]\n"
     "                       if t.is_live and not t.is_promise}",
     "            retired = {t.number for t in twins[r.number]\n"
     "                       if t.is_live and not t.is_promise}"),

    # ── 2c. the landing is checked before the commit ───────────────────────────────────────────
    ("a landing that breaks the corpus — or retires an agreed requirement — is committed",
     IMPORTING,
     "        done.broken = _broken(before, load_corpus(root / folder), folder)\n"
     "        if done.broken:",
     "        done.broken = []\n        if done.broken:"),

    ("the check counts the corpus's errors and never an agreed requirement retired with a valid "
     "supersession", IMPORTING,
     "            out.append(f\"{folder}/{was.path}: agreed-changed\")",
     "            pass"),

    # ── 2d. nothing through a link ─────────────────────────────────────────────────────────────
    ("the import's writer makes every folder on the way before it asks whether one is a link",
     IMPORTING,
     "    here = Path(root)\n    for part in parts[:-1]:\n        here = here / part\n",
     "    target.parent.mkdir(parents=True, exist_ok=True)\n    here = Path(root)\n"
     "    for part in parts[:-1]:\n        here = here / part\n"),

    ("the plan reads a document already in the product through a link on its way", IMPORTING,
     "        if _linked(root, str(PurePosixPath(dest).parent)):",
     "        if False:"),

    # ── 2e. the bound counts what is left out ──────────────────────────────────────────────────
    ("what is left out is listed without a bound, and the record with it", IMPORTING,
     "        self.take(0)\n        left_out.append((_said_path(path), why))",
     "        left_out.append((_said_path(path), why))"),

    ("a member's name is said whole, however long the archive made it", IMPORTING,
     "    return text if len(text) <= MAX_PATH_CHARS else text[:MAX_PATH_CHARS - 1] + \"…\"",
     "    return text"),

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
