"""A release note names its reference once (#659), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/659_a_fragment_names_its_reference_once.py

The assembly closes each fragment's first line with `(#<ref>)` from the file name, so a fragment
whose text already ends with it read twice: 0.6.0's notes said "(#654) (#654)". `read_fragments`
now refuses one, and every command, the pull request's CI step among them, reads fragments
through it. The claims, each put back the way it could break:

  the refusal   a fragment that ends with its own reference is refused, with or without a final
                full stop, an issue's number or an advisory's id, and the fix is named
  the line      the first line is checked, since that is the one the reference closes, trailing
                spaces and all; a final colon and the emphasis around the full stop are where it
                would close too
  the page      a candidate's page leaves such a fragment out rather than print it twice
  the scope     another number, or its own number before the end, still passes
"""

TEST = "tests/test_a_release_is_noted_by_its_pull_requests.py"
SCRIPT = "scripts/release_notes.py"

CLOSING = r'closing = re.compile(rf"\({re.escape(reference)}\)[*_]*[.:]?[*_]*$")'

MUTATIONS = [
    ("THE DEFECT: a fragment that ends with its own reference is accepted, and reads twice", SCRIPT,
     "        if _ends_with_its_reference(text, fragment.reference):\n",
     "        if False:\n"),

    ("a final full stop after the reference is not seen", SCRIPT,
     CLOSING,
     r'closing = re.compile(rf"\({re.escape(reference)}\)[*_]*$")'),

    ("only the full-stop form is seen: a bare reference or a lead line's colon passes", SCRIPT,
     CLOSING,
     r'closing = re.compile(rf"\({re.escape(reference)}\)[*_]*\.[*_]*$")'),

    ("the emphasis around a bold lead line hides the reference", SCRIPT,
     CLOSING,
     r'closing = re.compile(rf"\({re.escape(reference)}\)[.:]?$")'),

    ("an advisory's id is never matched", SCRIPT,
     "        if _ends_with_its_reference(text, fragment.reference):\n",
     '        if _ends_with_its_reference(text, f"#{named[\'ref\']}"):\n'),

    ("the reference is refused anywhere in the text, not only at its end", SCRIPT,
     CLOSING,
     r'closing = re.compile(rf"\({re.escape(reference)}\)[*_]*[.:]?[*_]*")'),

    ("any number at the end is refused, not only the fragment's own", SCRIPT,
     CLOSING,
     r'closing = re.compile(rf"\(#[0-9]+\)[*_]*[.:]?[*_]*$")'),

    ("only the end of the whole text is checked, not the first line the reference closes", SCRIPT,
     "for line in (text.splitlines()[0].rstrip(), text.rstrip()))",
     "for line in (text.rstrip(),))"),

    ("trailing spaces after a lead line hide its reference", SCRIPT,
     "for line in (text.splitlines()[0].rstrip(), text.rstrip()))",
     "for line in (text.splitlines()[0], text.rstrip()))"),

    ("a refused fragment is kept anyway, and a candidate's page reads its number twice", SCRIPT,
     '                            f"file name")\n            continue\n',
     '                            f"file name")\n'),

    ("the refusal does not say how to fix it", SCRIPT,
     '`({fragment.reference})`; drop it, the assembly adds it from the "\n'
     '                            f"file name")',
     '`({fragment.reference})`")'),
]
