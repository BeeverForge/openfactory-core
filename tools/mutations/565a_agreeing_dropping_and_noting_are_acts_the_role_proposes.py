"""Agreeing to a requirement, dropping it, recording a decision in it and noting a fact are acts the
role proposes from what it understood (#565, first slice), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/565a_agreeing_dropping_and_noting_are_acts_the_role_proposes.py

On a live run "pode aceitar o 66" and "sim, concordo com o requisito 66" matched no pattern, and
the model that understood both had no act to hand them to. The claims, each a row:

  1. the role's parser reads each act's marker into the gesture the engine stages it through, with
     what it carries, its quotation taken off; one act per reply, the first in the table's order,
     and a change waiting on the person outranks it;
  2. the engine stages the act through the branch the pattern reached, the role's reply in front
     of the question and of a refusal;
  3. one way in: a sentence alone no longer acts, and every kind the confirmation executes is
     proposed by a marker or listed as still reached by a sentence;
  4. what the patterns guarded is written into the markers' instructions.
"""

TEST = "tests/test_the_role_proposes_what_a_requirement_needs.py"
ROLE = "openfactory/product/role.py"
ENGINE = "openfactory/product/engine.py"
INTENTS = "openfactory/product/intents.py"
PINNED = "tests/test_the_conversation_is_pinned.py"
CARDS = "tests/test_card_maintenance_channel.py"
DECISION = "tests/test_a_decision_is_written_down.py"

MUTATIONS = [
    # 1. the parser
    ("TODAY'S RUN: the agreement's marker is read as nothing", ROLE,
     '    (AGREE_MARKER, _AGREE_RE, "agree", "accept"),\n', ""),
    ("a drop is staged as an acceptance", ROLE,
     '    (DROP_MARKER, _DROP_RE, "drop", "drop"),',
     '    (DROP_MARKER, _DROP_RE, "drop", "accept"),'),
    ("the quotation the person's words arrived in is written on the record", ROLE,
     "    return value.strip().strip(_QUOTES_AROUND).strip()",
     "    return value.strip()", CARDS),
    ("a second act in one reply is staged over the first", ROLE,
     "    act = None if (adjusted or accepted) or not acts else acts[0]",
     "    act = None if (adjusted or accepted) or not acts else acts[-1]"),
    ("an act on a requirement is read beside a change waiting on the person", ROLE,
     "    act = None if (adjusted or accepted) or not acts else acts[0]",
     "    act = None if not acts else acts[0]"),

    # 2. the engine
    ("the engine ignores an act the role proposed", ENGINE,
     "    if intent:\n        proposed = _run_intent(project, intent,",
     "    if False:\n        proposed = _run_intent(project, intent,"),
    ("the act is staged without what its marker carried", ENGINE,
     '                               {**(getattr(answer, "gesture_args", None) or {}),\n',
     "                               {\n"),
    ("the role's reply is dropped from in front of the question", ENGINE,
     '                               {**(getattr(answer, "gesture_args", None) or {}),\n'
     '                                "preamble": f"{answer.text}\\n\\n" if answer.text else ""},',
     '                               {**(getattr(answer, "gesture_args", None) or {}),\n'
     '                                "preamble": ""},'),
    ("a refusal after a proposed act is said in the pattern's voice, the role's reply lost",
     ENGINE,
     "        if preamble:\n            return preamble + sentence",
     "        if False:\n            return preamble + sentence"),
    ("a requirement the base does not have is said without the role's reply", ENGINE,
     '                                                   "" if preamble else name, lang)\n'
     "        if instead:\n            return preamble + instead\n        if req.is_promise:",
     '                                                   "" if preamble else name, lang)\n'
     "        if instead:\n            return instead\n        if req.is_promise:", PINNED),

    # 3. one way in
    ("the sentence that read an acceptance comes back beside the marker", INTENTS,
     "    # RETIRED 2026-10-10 (#565): `accept`, `decision` and `drop` are acts the role proposes —\n",
     '    ("accept", re.compile(_NOT_NEGATED + r"\\b(?:aceit[ae])\\b[^\\d]{0,40}"\n'
     '                          + _requirement("number"), re.IGNORECASE)),\n'
     "    # RETIRED 2026-10-10 (#565): `accept`, `decision` and `drop` are acts the role proposes —\n"),
    ("a kind the confirmation executes is neither proposed nor listed", ROLE,
     '    (FACT_MARKER, _FACT_RE, "fact", "fact"),\n', ""),

    # 4. what the patterns guarded
    ("the decision's instruction stops ruling out one still being discussed", ROLE,
     '"them (that is [[DECISAO: …]]), nor for one still being discussed.\\n\\n"',
     '"them (that is [[DECISAO: …]]).\\n\\n"', DECISION),
]
