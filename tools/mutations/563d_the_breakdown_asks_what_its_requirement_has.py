"""A breakdown is handed the cards that already execute its requirement, and files each card
through the semaphore after asking again (#563, ADR-0051 D18 slice 18d; #567's last slice),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/563d_the_breakdown_asks_what_its_requirement_has.py

The claims, each a row:

  1. the decomposition is handed the cards that execute the requirement, open and closed, in their
     own words and in its own prompt — an older role is called as before — and a front a closed
     one carries is reused, with nothing noted on a card that already says it executes it;
  2. a card of the requirement that appeared since the breakdown began holds every front not yet
     filed, naming it;
  3. the breakdown's own cards are never strangers to the re-read;
  4. the re-read and the write run under the semaphore, the vet before it;
  5. a board that cannot be read files as before, and says so.
"""

TEST = "tests/test_the_breakdown_asks_what_its_requirement_has.py"
MODULE = "openfactory/product/module.py"
ROLE = "openfactory/product/role.py"
QUEUE = "openfactory/product/queue.py"

MUTATIONS = [
    # 1. what the decomposition is handed
    ("the decomposition is handed nothing", MODULE,
     'sources=self._sources(),\n            **({"carrying": carrying} if _takes(issues_for, '
     '"carrying") else {}))',
     "sources=self._sources())"),
    ("an older role is handed what it does not take", MODULE,
     '**({"carrying": carrying} if _takes(issues_for, "carrying") else {}))',
     '**({"carrying": carrying} if True else {}))'),
    ("a closed card of the requirement is not counted as carrying it", MODULE,
     '    return [t for t in tickets or [] if _cited_requirement(getattr(t, "body", "") or "") '
     "== number]",
     '    return [t for t in tickets or [] if getattr(t, "state", "") != "closed"\n'
     '            and _cited_requirement(getattr(t, "body", "") or "") == number]'),
    ("a front a closed carrier carries is filed again", MODULE,
     "            known_open = known_open | {t.number for t in carrying or []}",
     "            known_open = known_open"),
    ("a card that already executes the requirement is told so again", MODULE,
     "                getattr(self, \"_board_tickets\", None) or [], requirement.number)}:\n"
     "            return claimed\n",
     "                getattr(self, \"_board_tickets\", None) or [], requirement.number)}:\n"
     "            pass\n"),
    ("the prompt carries no card", ROLE,
     "            + carried\n            + \"## Source repositories for this product\\n\"",
     "            + \"## Source repositories for this product\\n\""),
    ("the prompt does not say what the cards mean", ROLE,
     "               \"delivered work twice.\" if carried else \"\"),",
     "               \"delivered work twice.\" if False else \"\"),"),
    ("a criterion is shown with its markdown checkbox", QUEUE,
     '    criteria = [_CHECKBOX.sub("", c.text).strip() for c in parsed.acceptance_criteria]',
     "    criteria = [c.text.strip() for c in parsed.acceptance_criteria]"),

    # 2. a card that appeared meanwhile
    ("TODAY'S RUN: a card filed by hand meanwhile stops nothing", MODULE,
     "        if not arrived:\n            return None\n",
     "        if True:\n            return None\n"),
    ("a stopped breakdown files the fronts it has not reached", MODULE,
     "            if fence.stopped is not None:\n",
     "            if False:\n"),

    # 3. its own cards
    ("its own cards are strangers to its re-read", MODULE,
     "                   if canonical_ref(t.number) not in self.known | self.own]",
     "                   if canonical_ref(t.number) not in self.known]"),
    ("the fence is never told what the breakdown filed", MODULE,
     "                fence.filed(filed[index])\n", ""),

    # 4. the lock
    ("the re-read and the write run outside the semaphore", MODULE,
     "            written = self._checked_write(\n"
     "                act=f\"file work: {title[:60]}\", kind=\"ticket\", text=title, seen=None,\n"
     "                write=_write, saved=_saved_on_the_board, against=_CARD_KINDS,\n"
     "                found=_the_card_just_asked_for)",
     "            written = _write()"),
    ("the vet, a model call, runs under the semaphore", MODULE,
     "            vetted, why = vet(draft)\n",
     "            from openfactory.product import semaphore as _semaphore\n"
     "            with _semaphore.held(self.project):\n"
     "                vetted, why = vet(draft)\n"),

    # 5. a board that cannot be read
    ("a board unread before a card is filed in silence", MODULE,
     "        if error:\n            log.warning(\"OPENFACTORY_PRODUCT_BREAKDOWN_UNFENCED",
     "        if False:\n            log.warning(\"OPENFACTORY_PRODUCT_BREAKDOWN_UNFENCED"),
    ("a board unread when it began is fenced against nothing it knows", MODULE,
     "        if self.known is None:\n            return None\n",
     "        if False:\n            return None\n"),
]
