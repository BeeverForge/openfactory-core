"""#161 (the negation half): the two lists are one mechanism, and `no` stays out.

SUPERSEDED BY `565b_closing_correcting_and_aligning_are_acts_the_role_proposes.py` (2026-10-11).
The negators and the bridge left `intents.py` with the last gesture that scanned a message for a
card (#565 slices b and c), and so did this plan's test: closing a card is an act the role
proposes, read by the model in whatever language the person writes. Its claim — a negation is
never obeyed as an order — is carried by that plan's row on the close marker's instruction ("a
card the person said NOT to close may be proposed for closing"). Kept as the point-in-time proof
it was.
"""

TEST = "tests/test_a_negation_the_bridge_carries_is_refused.py"
SUPERSEDED_BY = "565b_closing_correcting_and_aligning_are_acts_the_role_proposes.py"
INTENTS = "openfactory/product/intents.py"

MUTATIONS = [
    ("the matcher forgets every negator but Portuguese again", INTENTS,
     '_NOT_NEGATED = (r"(?<!n[ãa]o )(?<!nao )(?<!nunca )(?<!jamais )(?<!nem )"\n'
     "                r\"(?<!never )(?<!don't )(?<!dont )(?<!do not )\")",
     '_NOT_NEGATED = r"(?<!n[ãa]o )(?<!nao )(?<!nunca )(?<!jamais )"'),

    ("…and the reverse: it refuses everything, so the surface answers nobody", INTENTS,
     "                r\"(?<!never )(?<!don't )(?<!dont )(?<!do not )\")",
     '                r"(?<!never )(?<!don\'t )(?<!dont )(?<!do not )(?<!x)(?=$a)")'),

    ("the bridge stops carrying the new negators to the lookbehind", INTENTS,
     '           r"n[ãa]o|nunca|jamais|nem|never|don\'?t|do\\s+not|'
     'por\\s+favor|favor)[\\s,]+){0,2}"',
     '           r"n[ãa]o|nunca|jamais|por\\s+favor|favor)[\\s,]+){0,2}"'),

    ("`no` enters the negators — an ordinary instruction is refused", INTENTS,
     '_NOT_NEGATED = (r"(?<!n[ãa]o )(?<!nao )',
     '_NOT_NEGATED = (r"(?<!no )(?<!n[ãa]o )(?<!nao )'),

    ("…and it enters the bridge", INTENTS,
     '           r"n[ãa]o|nunca|jamais|nem|never',
     '           r"no|n[ãa]o|nunca|jamais|nem|never'),
]
