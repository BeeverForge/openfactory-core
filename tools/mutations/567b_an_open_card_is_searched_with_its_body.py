"""An open card is found by its words, with its body, as a closed one is (#567, second slice),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/567b_an_open_card_is_searched_with_its_body.py

The role judged two open cards' overlap from their titles: the product's memory indexed closed
cards only. The claims, each a row:

  1. an open card is an item, with its body, marked open, its origin saying so;
  2. a card that opens or closes since it was read is replaced, its state with it;
  3. the role is told an open card is open as last read, and that where it stands is the board's.
"""

TEST = "tests/test_an_open_card_is_searched_with_its_body.py"
ITEMS = "openfactory/product/index/items.py"
SYNC = "openfactory/product/index/sync.py"
RETRIEVAL = "openfactory/product/index/retrieval.py"

MUTATIONS = [
    # 1. the item
    ("TODAY'S RUN: an open card is left out of the index again", ITEMS,
     "    from openfactory.product.documents.record import requirements_cited\n\n"
     '    ref = str(getattr(card, "number", "") or "").strip()\n',
     "    from openfactory.product.documents.record import requirements_cited\n\n"
     '    if str(getattr(card, "state", "") or "").lower() != "closed":\n'
     "        return []\n"
     '    ref = str(getattr(card, "number", "") or "").strip()\n'),
    ("an open card is indexed as closed", ITEMS,
     "                 status=CLOSED if closed else OPEN,",
     "                 status=CLOSED,"),
    ("a card is indexed without its body", ITEMS,
     '                 text=f"{title}\\n\\n{body}".strip(), audience=CLIENT,\n',
     "                 text=title, audience=CLIENT,\n"),
    ("an open card's origin says it is closed", ITEMS,
     '        else "open when the index last read it")',
     '        else "closed (the tracker does not say why)")'),

    # 2. the sync
    ("a card that opens or closes is kept in the state it was first read in", SYNC,
     "            version = digest_of(made[0].text, made[0].origin, made[0].date)",
     "            version = digest_of(made[0].text, made[0].date)"),

    # 3. what the role is told
    ("an open card is shown as current evidence, its standing unsaid", RETRIEVAL,
     '    OPEN: "an open card, as the board showed it when last read — what it asks for and '
     'builds on "\n'
     '          "is in its words; where it stands now is on the board (`board.md`)",\n',
     ""),
]
