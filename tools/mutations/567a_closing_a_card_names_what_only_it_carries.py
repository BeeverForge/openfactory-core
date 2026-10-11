"""A close in favour of another card asks the yes on what the closed card carries and the survivor
does not (#567), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/567a_closing_a_card_names_what_only_it_carries.py

The role offered to close one card "or" another as equals, and the one closed was the only card
carrying a requirement's first front; the confirmation claimed the two "ask for the same thing".
The claims, each a row:

  1. the comparison lists the criteria only the closed card states — in any case or punctuation —
     and the requirement only it executes, bounded;
  2. the module reads both off the board, and a card it cannot read is "could not compare", never
     "nothing is lost";
  3. the conversation asks for the comparison before staging a close in favour of a card, and the
     question lists what is lost and never claims the two are the same; an unread pair is said.
"""

TEST = "tests/test_closing_a_card_names_what_only_it_carries.py"
MODULE = "openfactory/product/module.py"
VOICE = "openfactory/product/voice.py"
ENGINE = "openfactory/product/engine.py"

MUTATIONS = [
    # 1. the comparison
    ("TODAY'S RUN: every criterion of the closed card is taken as stated on the survivor", MODULE,
     "                               if _plain(c) not in stated))[:at_most]",
     "                               if False))[:at_most]"),
    ("a criterion differs by its case and punctuation", MODULE,
     "    stated = {_plain(c) for c in criteria(staying)}",
     "    stated = set(criteria(staying))"),
    ("the requirement the closed card executes is never carried", MODULE,
     "                   executes=executes if executes != _cited_requirement(staying) else None)",
     "                   executes=None)"),
    ("the list is not bounded", MODULE,
     "                               if _plain(c) not in stated))[:at_most]",
     "                               if _plain(c) not in stated))"),

    # 2. the module's read
    ("a survivor not on the board compares as nothing lost", MODULE,
     "        if closing is None or staying is None:\n            return None\n",
     "        if closing is None and staying is None:\n            return None\n"),
    ("an unreadable board compares as nothing lost", MODULE,
     "        tickets, error = self._read_board()\n        if error:\n            return None\n"
     "        bodies = {",
     "        tickets, error = self._read_board()\n        if error:\n            return Carried()\n"
     "        bodies = {"),

    # 3. the question
    ("the conversation stages the close without comparing", ENGINE,
     "        if in_favour_of and compare is not None:\n",
     "        if False:\n"),
    ("the question claims the two cards ask for the same thing again", VOICE,
     "    if in_favour_of and carried:\n",
     "    if False:\n"),
    ("the requirement only the closed card executes is not listed", VOICE,
     "        if carried.executes is not None:\n            items.append(",
     "        if False:\n            items.append("),
    ("two cards that could not be compared are not said", VOICE,
     "        if in_favour_of and unread:\n",
     "        if False:\n"),
]
