"""A card the factory took up and has not finished says why it offers no pass (#668), proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/a_card_that_offers_no_pass_says_why.py

The claims, each a row:
  1. every reason the gate gives is said on the card;
  2. a person who may not send the card back is told so;
  3. an engine error read as "no job ever ran" is said in the log.
"""

TEST = "tests/test_a_card_that_offers_no_pass_says_why.py"
MODULE = "openfactory/product/module.py"
ADJUST = "openfactory/product/adjust.py"

MUTATIONS = [
    # 1. every reason
    ("TODAY'S RUN: a gate that is not waiting is a bare refusal", MODULE,
     "        if not gate.open:\n"
     '            return {"offered": False, "note": adjust_said(gate.why, ref=number,\n',
     "        if gate.why in (adjust.NOT_WAITING, adjust.UNREACHABLE):\n"
     '            return {"offered": False}\n'
     "        if not gate.open:\n"
     '            return {"offered": False, "note": adjust_said(gate.why, ref=number,\n'),
    ("a gate that could not be read is a bare refusal", MODULE,
     "        if not gate.open:\n"
     '            return {"offered": False, "note": adjust_said(gate.why, ref=number,\n',
     "        if gate.why == adjust.UNREACHABLE:\n"
     '            return {"offered": False}\n'
     "        if not gate.open:\n"
     '            return {"offered": False, "note": adjust_said(gate.why, ref=number,\n'),
    ("the note is said in the platform's language, not the project's", MODULE,
     "                                                          passes=gate.passes, language=lang)}",
     "                                                          passes=gate.passes, language=None)}"),

    # 2. who may not send it back
    ("a person who may not send it back is shown nothing", MODULE,
     '            return {"offered": False, "note": adjust_said("not_yours", ref=number, '
     'language=lang)}',
     '            return {"offered": False}'),

    # 3. the log
    ("the no-job reading is silent", ADJUST,
     '            log.info("OPENFACTORY_ADJUST_GATE_NO_JOB project=%s card=#%s — the engine said %r, "\n'
     '                     "read as no job ever having run for the card", name, card, str(exc)[:200])\n',
     ""),
]
