"""A card links the context repository only by an address a person can open, never by a path on
this machine (journey 0, #640, #662), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/a_card_links_only_what_a_person_can_open.py

The claims, each a row:
  1. on the local row, every card names its context repository as plain text, with no path;
  2. only an `http://` or `https://` address becomes a link; a path, `file://` or an ssh address
     does not;
  3. on a hosted row the link is the forge's own address, as before.
"""

TEST = "tests/test_a_card_links_only_what_a_person_can_open.py"
MOD = "openfactory/product/module.py"

MUTATIONS = [
    ("TODAY'S RUN: any clone URL becomes the card's link", MOD,
     '        if not _re.match(r"https?://", url):\n',
     "        if False:\n"),
    ("a `file://` address is a link", MOD,
     '        if not _re.match(r"https?://", url):\n',
     '        if not _re.match(r"(https?|file)://", url):\n'),
    ("a bare path is a link, as long as it is not relative", MOD,
     '        if not _re.match(r"https?://", url):\n',
     '        if not _re.match(r"(https?://|/)", url):\n'),
    ("a plain http address is not a link", MOD,
     '        if not _re.match(r"https?://", url):\n',
     '        if not _re.match(r"https://", url):\n'),
    ("a hosted row loses its link", MOD,
     '        return _re.sub(r"\\.git$", "", url)\n',
     '        return ""\n'),
]
