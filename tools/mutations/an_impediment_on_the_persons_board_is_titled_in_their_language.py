"""An impediment the factory files on the person's own board is titled in the project's language
(#671), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/an_impediment_on_the_persons_board_is_titled_in_their_language.py

The claims, each a row:
  1. every cause has a title in every language;
  2. on the person's own board the title is the project's language's, and on a factory board of
     its own it keeps its one spelling;
  3. an impediment open under any spelling is found: not filed again, and closed when it works.
"""

TEST = "tests/test_an_impediment_on_the_persons_board_is_titled_in_their_language.py"
IMP = "openfactory/ops/impediment.py"

MUTATIONS = [
    # 1. every cause, every language
    ("a cause has no title in Portuguese", IMP,
     '    GATE_CANNOT_RUN: {"en": "a gate this project declares cannot run in the box",\n'
     '                      "pt-BR": "uma verificação que este projeto declara não consegue rodar no "\n'
     '                               "box"},\n',
     '    GATE_CANNOT_RUN: {"en": "a gate this project declares cannot run in the box"},\n'),
    ("the identity is not the English spelling", IMP,
     '_TITLES = {cause: said["en"] for cause, said in _TITLES_SAID.items()}',
     '_TITLES = {cause: said.get("pt-BR", said["en"]) for cause, said in _TITLES_SAID.items()}'),

    # 2. the person's own board
    ("TODAY'S RUN: the impediment is filed under the English identity", IMP,
     "            title=title_on(project, cause),", "            title=title_for(name, cause),"),
    ("a factory board of its own is titled in the project's language", IMP,
     "        return getattr(declared, \"tracker\", None) == getattr(project, \"tracker\", None)",
     "        return True"),
    ("a declared factory board on the product's own tracker keeps English", IMP,
     "        return getattr(declared, \"tracker\", None) == getattr(project, \"tracker\", None)",
     "        return False"),
    ("the local row keeps English", IMP,
     '    return (getattr(tracker, "kind", "") or "").strip().lower() == "local"\n\n\ndef _board',
     "    return False\n\n\ndef _board"),

    # 3. any spelling
    ("only the identity is looked up", IMP,
     "    return [title_for(name, cause), *said]", "    return [title_for(name, cause)]"),
    ("only the translated spellings are looked up", IMP,
     "    return [title_for(name, cause), *said]", "    return said"),
    ("a filing looks up only the title it would write", IMP,
     "        existing = _open(trk, name, cause)\n        if existing:",
     "        existing = trk.find_ticket(title=title_on(project, cause))\n        if existing:"),
    ("a close looks up only the identity", IMP,
     "        existing = _open(trk, name, cause)\n        if not existing:",
     "        existing = trk.find_ticket(title=title_for(name, cause))\n        if not existing:"),
]
