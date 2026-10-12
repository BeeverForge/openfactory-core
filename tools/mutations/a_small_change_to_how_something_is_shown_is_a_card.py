"""A small change to how something already built is shown or worded is a card the person asked for
(journey 0, #640 row C-01, #669), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/a_small_change_to_how_something_is_shown_is_a_card.py

The claims, each a row:
  1. the line is drawn once: the card instruction takes the change, the requirement instruction
     leaves it out and points at the card, no other instruction draws it, and it stays narrow;
  2. the platform stages what the markers say: a card the person asked for is staged as a card and
     filed on one yes, and a reply with both a request and a card stages the card.
"""

TEST = "tests/test_a_small_change_to_how_something_is_shown_is_a_card.py"
ROLE = "openfactory/product/role.py"

MUTATIONS = [
    # 1. the line
    ("TODAY'S RUN: the card instruction does not take the change", ROLE,
     '            "product and the problem — never cut, never the request itself. The same marker "\n'
     '            f"when they ask to change {SHOWN_OR_WORDED} (\\"dá pra corrigir?\\"). "\n',
     '            "product and the problem — never cut, never the request itself. "\n'),
    ("the requirement instruction takes every change again", ROLE,
     '            f"marker {REQUEST_MARKER} on its own line — NOT for a change to {SHOWN_OR_WORDED}: "\n'
     '            f"that is a card they asked for, below. {STAGED_AFTER_YOUR_REPLY} If they "\n',
     '            f"marker {REQUEST_MARKER} on its own line. {STAGED_AFTER_YOUR_REPLY} If they "\n'),
    ("the requirement instruction leaves it out without saying where it goes", ROLE,
     'f"that is a card they asked for, below. {STAGED_AFTER_YOUR_REPLY} If they "',
     'f"that is not a requirement. {STAGED_AFTER_YOUR_REPLY} If they "'),
    ("another instruction draws the line again", ROLE,
     '            f"design. {STAGED_AFTER_YOUR_REPLY}\\n\\n"\n',
     '            f"design. Nor {SHOWN_OR_WORDED}. {STAGED_AFTER_YOUR_REPLY}\\n\\n"\n'),
    ("the line widens to any change, whatever it contradicts", ROLE,
     '"label, a message\'s wording, the order of a list — when the change is small and contradicts "\n'
     '    "no agreed requirement")',
     '"label, a message\'s wording, the order of a list — whatever the change")'),
    ("the line forgets that the thing is already built", ROLE,
     '    "how something the product already does is SHOWN or WORDED',
     '    "how something the product does is SHOWN or WORDED'),

    # 2. the platform
    ("a reply with a request and a card stages the requirement", "openfactory/product/engine.py",
     '    if getattr(answer, "is_ticket", False):',
     '    if getattr(answer, "is_ticket", False) and not answer.is_request:'),
    ("the parser stops reading a card the person asked for", ROLE,
     "is_ticket=ticket is not None", "is_ticket=False"),
]
