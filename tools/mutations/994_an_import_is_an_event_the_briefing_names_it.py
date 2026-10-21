"""#994, proven by breaking it — the product owner says where its requirements came from.

THE CLAIMS, each a rule the guard states over cases read from the code:

  1. **An import is one event, told to the room**, naming the origin and no person.
  2. **The briefing names where the requirements came from** while the import is a review to hold.
  3. **What is open is read, never stored**: a question closes when its requirement stops waiting
     for its yes, a text kept beside an agreed one when that one stops being the promise.
  4. **Who should answer is "you" to that person and nobody's name to anyone else** — on the agenda
     and in the pack.
  5. **The Pending tab and the role's instructions carry it.**

The guard under test is `tests/test_an_import_is_an_event_the_briefing_names_it.py`, whose bed is
the battery's `saltmarsh` fixture — exactly what the core's import writes.
"""

TEST = "tests/test_an_import_is_an_event_the_briefing_names_it.py"

EVENTS = "openfactory/product/events.py"
IMPORTING = "openfactory/product/importing.py"
AGENDA = "openfactory/product/agenda.py"
MODEL = "openfactory/product/model.py"
BRIEFING = "openfactory/product/briefing.py"
CATALOG = "openfactory/actions/catalog.py"
ROLE = "openfactory/org_defaults/roles/product.md"

MUTATIONS = [
    # ── 1. one event, to the room ──────────────────────────────────────────────────────────────
    ("one import is told again on every telling, so the room hears the same arrival twice",
     EVENTS,
     "    return _once(project, _event_id(IMPORTED, project, ident), lambda: (",
     "    return _once(project, _event_id(IMPORTED, project, ident, str(time.time())), lambda: ("),

    ("the arrival is said in the conversation of whoever imported it, not to the product's room",
     EVENTS,
     "    return _once(project, _event_id(IMPORTED, project, ident), lambda: (\n"
     "        room_of(project),",
     "    return _once(project, _event_id(IMPORTED, project, ident), lambda: (\n"
     "        \"person:somebody\","),

    # ── 2. the briefing ────────────────────────────────────────────────────────────────────────
    ("the briefing forgets the import a week after it landed, while it is still a review to hold",
     BRIEFING,
     "    if not imported.get(\"under_review\") and not recent:",
     "    if not recent:"),

    # ── 3. what is open is read ────────────────────────────────────────────────────────────────
    ("a question stays on the agenda after its requirement was agreed, dropped or replaced",
     IMPORTING,
     "        return r is not None and r.is_live and not r.is_promise",
     "        return r is not None"),

    ("a text kept beside an agreed requirement stays open after a person replaced that one",
     IMPORTING,
     "        if (r := by_number.get(n)) is not None and r.is_promise:\n"
     "            out.append(Open(CHANGE,",
     "        if (r := by_number.get(n)) is not None:\n"
     "            out.append(Open(CHANGE,"),

    # ── 4. nobody named ────────────────────────────────────────────────────────────────────────
    ("the agenda tells the room who the import says should answer", AGENDA,
     "                        what=item.text.strip()[:_WHAT_CHARS], since=review.landed_at, "
     "chased=\"\",",
     "                        what=f\"{item.ask}: {item.text.strip()}\"[:_WHAT_CHARS], "
     "since=review.landed_at, chased=\"\","),

    ("an item is everybody's to answer, whoever the record names", AGENDA,
     "        yours = bool(item.ask) and bool(viewer.person) and \\\n"
     "            _sealed(viewer.person) == _sealed(item.ask)",
     "        yours = bool(viewer.person)"),

    ("the pack names who should answer, in a file a room's turn reads", MODEL,
     "            mine = \" — yours to answer\" if speaker and item.get(\"ask\") and \\\n"
     "                sealed(item[\"ask\"]) == speaker else \"\"",
     "            mine = f\" — for {item.get('ask')}\" if item.get(\"ask\") else \"\""),

    # ── 5. the Pending tab, and the role ───────────────────────────────────────────────────────
    ("the Pending tab leaves out what the import left open", CATALOG,
     "             *agenda.from_the_import(review, viewer, language=language)]",
     "             ]"),

    ("the role is no longer told that an import is a review, not a backlog", ROLE,
     "An import is **a review to hold with the person who asked, not a backlog to execute**.",
     "An import is a set of requirements to work on."),
]
