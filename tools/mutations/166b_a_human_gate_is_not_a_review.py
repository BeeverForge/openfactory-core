"""#166 (the `pr_open` half): a human merge gate is not a review."""

TEST = "tests/test_a_human_gate_is_not_a_review.py"
BASE = "openfactory/adapters/tracker/base.py"
MACHINE = "openfactory/orchestrator/machine.py"
GH = "openfactory/adapters/tracker/github.py"
GHP = "openfactory/adapters/tracker/github_project.py"
JIRA = "openfactory/adapters/tracker/jira.py"
NEUTRAL = "tests/test_tracker_is_vendor_neutral.py"

MUTATIONS = [
    # re-pinned 2026-10-21: the human gate answers `needs_review` on the line above the `_REVIEW`
    # branch (#753), so cutting that branch alone no longer reached `pr_open` (it survived); the
    # cut now takes both, which is the gate going back to the review column
    ("the human gate goes back to the review column", BASE,
     '    if needs_person and state is JobState.PR_OPEN:\n        return "needs_review"\n'
     '    if needs_person and state in _REVIEW:\n        return "needs_action"',
     "    pass"),

    ("…and the reverse: every review lands on a person, armed auto-merge included", BASE,
     '    if needs_person and state in _REVIEW:\n        return "needs_action"',
     '    if state in _REVIEW:\n        return "needs_action"'),

    ("a caller can talk a parked ticket out of needing anybody", BASE,
     "    if needs_person and state in _REVIEW:",
     "    if needs_person is False:\n        return \"in_review\"\n"
     "    if needs_person and state in _REVIEW:"),

    ("the default stops meaning what it meant", BASE,
     "    return STATE_KEYS.get(state)", '    return "in_review"'),

    # ── the engine's three sites ────────────────────────────────────────────────────────────────
    ("the human gate stops claiming a person", MACHINE,
     "                self._set_state(ticket, JobState.PR_OPEN, needs_person=True)",
     "                self._set_state(ticket, JobState.PR_OPEN)"),

    ("…and the armed auto-merge claims one", MACHINE,
     "        self._set_state(ticket, JobState.PR_OPEN, needs_person=False)\n        return None",
     "        self._set_state(ticket, JobState.PR_OPEN, needs_person=True)\n        return None"),

    ("the machine takes the distinction and drops it", MACHINE,
     # re-pinned 2026-10-04: a pull request is an outcome the box hands back, with who the blocker is, and
     # the worker applies it through the card's door (#414)
     "                HandedBack(state=state, needs_person=needs_person, reason=reason or \"\"))",
     "                HandedBack(state=state, reason=reason or \"\"))"),

    # ── the vendors ─────────────────────────────────────────────────────────────────────────────
    ("the GitHub tracker stops handing it to its board", GH,
     "            moved = self.board.set_status(\n                needs_person=needs_person,",
     "            moved = self.board.set_status("),

    # re-pinned 2026-10-21: the row tries `column_keys` in order, the resolver's key and then its
    # fallback (#753); the cut still swaps the resolver for the bare table
    # re-pinned 2026-10-21: `set_status` asks `yields_its_name` of each candidate (PR #1040's
    # review), so the list it builds moved; the cut still puts the table in place of the resolver
    ("the GitHub board reads the table around the resolver", GHP,
     "        from openfactory.adapters.tracker.base import column_keys\n\n"
     "        # `_columns` merges the defaults",
     "        from openfactory.adapters.tracker.base import STATE_KEYS\n\n"
     "        def column_keys(state, needs_person=None):\n"
     "            return (STATE_KEYS.get(state) or \"\",)\n\n"
     "        # `_columns` merges the defaults"),

    # re-pinned 2026-10-21: `_column_keys`, the resolver's key then its fallback (#753)
    ("Jira does", JIRA,
     "            keys = _column_keys(state, needs_person=needs_person)",
     "            from openfactory.adapters.tracker.base import STATE_KEYS\n\n"
     "            keys = (STATE_KEYS.get(state),)", NEUTRAL),
]
