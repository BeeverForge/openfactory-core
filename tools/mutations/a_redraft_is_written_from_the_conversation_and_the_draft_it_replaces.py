"""A redraft is written from the conversation and the draft it replaces, never from the adjustment
alone (journey 0, #640, C-03; #661), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/a_redraft_is_written_from_the_conversation_and_the_draft_it_replaces.py

The claims, each a row:
  1. every drafter a turn reaches — the requirement, the requested card, the defect — receives the
     conversation, the role's reply and the draft it replaces, whether the adjustment left that
     draft on the table or a "no" took it off; the requirement it replaces reaches it whole;
  2. each drafter's prompt carries the three, and the rule to keep what was not changed only when
     there is a draft to keep.
"""

TEST = "tests/test_a_redraft_is_written_from_the_conversation_and_the_draft_it_replaces.py"
ENGINE = "openfactory/product/engine.py"
MODULE = "openfactory/product/module.py"
ROLE = "openfactory/product/role.py"
CARDS = "openfactory/product/cards.py"

MUTATIONS = [
    # 1. what each drafter receives
    ("TODAY'S RUN: the requirement is drafted from the adjustment alone", ENGINE,
     '                              asked_by=user or "", source=ex.source or "",\n'
     '                              conversation=ex.conversation, reply=answer.text or "",\n'
     "                              replacing=the_draft_it_replaces(ex.replacing))",
     '                              asked_by=user or "", source=ex.source or "")'),
    ("the requirement's drafter is not handed the role's reply", ENGINE,
     'conversation=ex.conversation, reply=answer.text or "",\n'
     "                              replacing=the_draft_it_replaces",
     'conversation=ex.conversation, reply="",\n'
     "                              replacing=the_draft_it_replaces"),
    ("the requested card is not shown the draft it replaces", ENGINE,
     "                           language=ex.lang, **_replacing(ex, compose))\n"
     "        return _offer_card(ex, composed, request=text, preamble=preamble)",
     "                           language=ex.lang)\n"
     "        return _offer_card(ex, composed, request=text, preamble=preamble)"),
    ("the defect is not shown the draft it replaces", ENGINE,
     "                               language=ex.lang, **_replacing(ex, compose))",
     "                               language=ex.lang)"),
    ("a draft a no took off the table is not what the redraft is written from", ENGINE,
     "    ex.replacing = waiting or settled.rejected\n", "    ex.replacing = waiting\n"),
    ("a draft still on the table is not what the redraft is written from", ENGINE,
     "    ex.replacing = waiting or settled.rejected\n", "    ex.replacing = settled.rejected\n"),
    ("a no does not carry the draft it took off the table", ENGINE,
     "    return Settled(None, waiting, rejected=rejected)", "    return Settled(None, waiting)"),
    ("the requirement it replaces reaches the drafter as its title alone", ENGINE,
     '        kept = {k: v for k, v in fields.items() if k not in ("conflicts", "supersedes") and v}',
     '        kept = {"title": fields.get("title")}'),
    ("the module drops what the draft is written from", MODULE,
     '                          **({"asked": section} if section else {}), **written_from)',
     '                          **({"asked": section} if section else {}))'),
    ("the module drops the draft it replaces from the card", MODULE,
     "            language=lang, replacing=replacing)", "            language=lang)"),
    ("the card loop drops the draft it replaces", CARDS,
     "            template=template, feedback=feedback, kind=kind, language=language,\n"
     "            replacing=replacing)))",
     "            template=template, feedback=feedback, kind=kind, language=language)))"),

    # 2. what reaches the model
    ("the requirement's prompt leaves the conversation out", ROLE,
     '            (f"## The conversation (oldest first)\\n{conversation.strip()}\\n\\n"\n'
     '             if conversation.strip() else "")\n'
     '            + f"## The request\\n{request}"',
     '            f"## The request\\n{request}"'),
    ("the requirement's prompt leaves the draft it replaces out", ROLE,
     '            + (f"\\n\\n## {REPLACING_HEADING}\\n{REPLACING_RULE}\\n\\n{replacing.strip()}"\n'
     '               if replacing.strip() else "")\n',
     ""),
    ("the requirement's prompt states the rule with nothing to replace", ROLE,
     '{REPLACING_RULE}\\n\\n{replacing.strip()}"\n               if replacing.strip() else "")',
     '{REPLACING_RULE}\\n\\n{replacing.strip()}")'),
    ("the card's prompt leaves the draft it replaces out", CARDS,
     '        + (f"\\n\\n## {REPLACING_HEADING}\\n\\n{REPLACING_RULE}\\n\\n{replacing.strip()}"\n'
     '           if replacing else "")\n',
     ""),
]
