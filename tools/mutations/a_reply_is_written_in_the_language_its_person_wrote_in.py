"""A reply is written in the language the person wrote in, whatever the project's language is
(journey 0, #640 row C-11, #655), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/a_reply_is_written_in_the_language_its_person_wrote_in.py

The claims, each a row:
  1. every language rule a conversation's prompt carries says to answer in the writer's language,
     before the dialect rule, for every language and for one the platform has no rules for;
  2. every harness prepends the same clause to every phase a person reads, a new one included;
  3. no prompt writes a language section of its own;
  4. a card drafted in a named language keeps its dialect rule and gets no mirror clause.
"""

TEST = "tests/test_a_reply_is_written_in_the_language_its_person_wrote_in.py"
VOICE = "openfactory/product/voice.py"
ROLE = "openfactory/product/role.py"
ROLES = "openfactory/adapters/agent/roles.py"

MUTATIONS = [
    # 1. the product role's conversation
    ("TODAY'S RUN: the conversation's rule is the dialect rule alone", ROLE,
     "            rules = language_rules(self.language, replying=True)\n",
     "            rules = language_rules(self.language)\n"),
    ("the reply clause leaves the conversation's rule", VOICE,
     '    said = ["# Language", "", REPLY_CLAUSE]\n', '    said = ["# Language", ""]\n'),
    ("the dialect rule comes before the clause that bounds it", VOICE,
     '    said = ["# Language", "", REPLY_CLAUSE]\n',
     '    said = ["# Language", "", rule.removeprefix("# Language\\n\\n"), "", REPLY_CLAUSE]\n'),
    ("the dialect rule is lost on a reply", VOICE,
     "    if dialect:\n        said += [", "    if False:\n        said += ["),
    ("the rule says who the reader is again", VOICE,
     "nicety: a Brazilian reader reads pt-PT as a message meant for somebody ",
     "nicety: the reader is Brazilian, and pt-PT reads as a message meant for somebody "),
    ("a language with no rules gets no clause on a reply", VOICE,
     "    if not replying:\n        return rule\n",
     "    if not replying or not rule:\n        return rule\n"),
    ("the role says the clause twice", ROLE,
     '            rules = language_rules(self.language, replying=True)\n            if rules:\n'
     '                parts += ["", rules]\n',
     '            rules = language_rules(self.language, replying=True)\n            if rules:\n'
     '                parts += ["", rules, "", rules]\n'),

    # 2. every harness, every phase a person reads
    ("the harnesses' directive drops the clause", ROLES,
     '        f"{REPLY_CLAUSE}\\n\\n"\n', ""),
    ("one harness stops localising the phases a person reads",
     "openfactory/adapters/agent/codex.py",
     "        if not needs_language_directive(phase):\n            return prompt\n",
     "        if True:\n            return prompt\n"),
    ("a phase nobody listed is not localised", ROLES,
     "    return spec is None or spec.human_facing",
     "    return spec is not None and spec.human_facing"),

    # 3. no prompt writes its own language section
    ("a module writes a language section of its own", "openfactory/product/engine.py", "",
     '\n_HARD_RULE = "# Language\\n\\nWrite in Portuguese."\n'),

    # 4. a document in a named language is not a reply
    ("a card is told to mirror the writer", "openfactory/product/cards.py",
     '    rules = language_rules(language) if language else ""',
     '    rules = language_rules(language, replying=True) if language else ""'),
]
