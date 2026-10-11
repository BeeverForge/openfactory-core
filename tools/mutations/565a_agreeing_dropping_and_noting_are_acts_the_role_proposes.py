"""Agreeing to a requirement, dropping it, recording a decision in it and noting a fact are acts the
role proposes from what it understood (#565, first slice), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/565a_agreeing_dropping_and_noting_are_acts_the_role_proposes.py

On a live run "pode aceitar o 66" and "sim, concordo com o requisito 66" matched no pattern, and
the model that understood both had no act to hand them to. The claims, each a row:

  1. the role's parser reads each act's marker into the gesture the engine stages it through, with
     what it carries, a quotation around the whole of it taken off and none inside it; a reply
     that is only the act is an answer; one act per reply, the first in the table's order, the
     rest counted, and a change waiting on the person outranks it; an act that did not parse is
     lost loudly;
  2. the engine stages the act through the branch the pattern reached, the role's reply in front
     of the question and of a refusal; a second act is said to wait, in front of a question only;
     a drop's question shows the reason that will be written;
  3. one way in: a sentence alone no longer acts, and every kind the confirmation executes is
     proposed by a marker or listed as still reached by a sentence;
  4. what the patterns guarded is written into the markers' instructions, with one act per reply,
     and the alignment that waits on an agreement says that agreement is asked first.
"""

TEST = "tests/test_the_role_proposes_what_a_requirement_needs.py"
ROLE = "openfactory/product/role.py"
ENGINE = "openfactory/product/engine.py"
VOICE = "openfactory/product/voice.py"
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
     "    while (len(value) >= 2 and _QUOTE_PAIRS.get(value[0]) == value[-1]",
     "    while (False and _QUOTE_PAIRS.get(value[0]) == value[-1]", CARDS),
    ("a mark inside the reason is taken for the quotation around it", ROLE,
     "           and value[0] not in value[1:-1] and value[-1] not in value[1:-1]):",
     "           ):"),
    ("any quotation mark at either end comes off, paired or not", ROLE,
     "    while (len(value) >= 2 and _QUOTE_PAIRS.get(value[0]) == value[-1]\n"
     "           and value[0] not in value[1:-1] and value[-1] not in value[1:-1]):\n"
     "        value = value[1:-1].strip()",
     "    value = value.strip(\"\".join(_QUOTE_PAIRS) + \"\".join(_QUOTE_PAIRS.values())).strip()"),
    ("a reply that is only the act is told as a harness that returned nothing", ROLE,
     "    return ProductAnswer(ok=bool(text) or act is not None, text=text, raw=raw,",
     "    return ProductAnswer(ok=bool(text), text=text, raw=raw,"),
    ("a second act in one reply is staged over the first", ROLE,
     "    act = None if (adjusted or accepted) or not acts else acts[0]",
     "    act = None if (adjusted or accepted) or not acts else acts[-1]"),
    ("the acts a reply carried past the first are not counted", ROLE,
     "                         acts_not_staged=len(acts) - 1 if act else 0,",
     "                         acts_not_staged=0,"),
    ("an act on a requirement is read beside a change waiting on the person", ROLE,
     "    act = None if (adjusted or accepted) or not acts else acts[0]",
     "    act = None if not acts else acts[0]"),
    ("an act that did not parse is dropped in silence", ROLE,
     "    lost = [x for x in markers if _ACT_SHAPED_RE.match(x)]",
     "    lost = []"),
    ("an act left open is dropped in silence", ROLE,
     "        _say_lost_acts(unclosed)\n", ""),

    # 2. the engine
    ("the engine ignores an act the role proposed", ENGINE,
     '    intent = GESTURE_INTENT.get(getattr(answer, "gesture", ""))',
     "    intent = None"),
    ("the act is staged without what its marker carried", ENGINE,
     '                               {**(getattr(answer, "gesture_args", None) or {}),\n',
     "                               {\n"),
    ("the role's reply is dropped from in front of the question", ENGINE,
     '                                "preamble": f"{answer.text}\\n\\n" if answer.text else "",\n'
     '                                "later": later},',
     '                                "preamble": "",\n'
     '                                "later": later},'),
    ("a second act is left unstaged without a word to the person", ENGINE,
     '                 if getattr(answer, "acts_not_staged", 0) else "")',
     '                 if False else "")'),
    ("the second act is said to wait where nothing was staged", ENGINE,
     '                                "preamble": f"{answer.text}\\n\\n" if answer.text else "",\n'
     '                                "later": later},',
     '                                "preamble": (f"{answer.text}\\n\\n" if answer.text else "")'
     ' + later,\n'
     '                                "later": ""},'),
    ("the second act's wait is never said", ENGINE,
     '    asking = preamble + captures.get("later", "")',
     "    asking = preamble"),
    ("a refusal after a proposed act is said in the pattern's voice, the role's reply lost",
     ENGINE,
     "        if preamble:\n            return preamble + sentence",
     "        if False:\n            return preamble + sentence"),
    ("a requirement the base does not have is said without the role's reply", ENGINE,
     '                                                   "" if preamble else name, lang)\n'
     "        if instead:\n            return preamble + instead\n        if req.is_promise:",
     '                                                   "" if preamble else name, lang)\n'
     "        if instead:\n            return instead\n        if req.is_promise:", PINNED),
    ("a drop's question hides the reason that will be written", ENGINE,
     "                                was_a_promise=was_a_promise, reason=reason, language=lang)",
     "                                was_a_promise=was_a_promise, language=lang)"),
    ("the reason is left out of the drop's question", VOICE,
     "    if not reason.strip():\n        return text\n",
     "    if True:\n        return text\n"),

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
    ("the prompt stops asking for one act per reply", ROLE,
     ' ONE ACT PER REPLY: when they ask "\n'
     '            "for two at once, end with the first and say in your reply that the other'
     ' comes after "\n'
     '            "they answer this one.\\n\\n"',
     '\\n\\n"'),
    ("the alignment sends the person on before the agreement is answered", VOICE,
     "está acordado e confirme quando eu perguntar; depois, «alinha",
     "está acordado, e depois «alinha", CARDS),
]
