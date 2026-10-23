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

#813 widened the refusal to every way of writing it that still read twice: a `!`, `?` or `;`
after it, a space before the final mark, an advisory's id in another case, and the reference
without its parentheses ("Details in GHSA-…." in two of 0.7.0's fragments), in code marks too.
#659's rows were re-pinned on 2026-10-23 to the pattern that replaced its own, and the plan gained:

  the endings   each of those is refused, one row each
  the scope     a number that merely ends in the fragment's own, and another advisory's id, pass
"""

TEST = "tests/test_a_release_is_noted_by_its_pull_requests.py"
SCRIPT = "scripts/release_notes.py"

# `_ends_with_its_reference`: the marks around the reference, the reference itself (in its
# parentheses or not), what may close it, and the case it is matched in
MARKS = 'marks = r"[*_`]*"'
REFERENCE = r"\(?{re.escape(reference)}\)?"
ENDING = r'{marks}[\t ]*[.:!?;]?{marks}$"'
CASE = "re.IGNORECASE)"
CALL = "        if _ends_with_its_reference(text, fragment.reference):\n"

MUTATIONS = [
    ("THE DEFECT: a fragment that ends with its own reference is accepted, and reads twice", SCRIPT,
     CALL,
     "        if False:\n"),

    ("a final full stop after the reference is not seen", SCRIPT,
     ENDING,
     r'{marks}$"'),

    ("only the full-stop form is seen: a bare reference or a lead line's colon passes", SCRIPT,
     ENDING,
     r'{marks}[\t ]*\.{marks}$"'),

    ("the emphasis around a bold lead line hides the reference", SCRIPT,
     MARKS,
     'marks = r"[`]*"'),

    ("an advisory's id is never matched", SCRIPT,
     CALL,
     '        if _ends_with_its_reference(text, f"#{named[\'ref\']}"):\n'),

    ("the reference is refused anywhere in the text, not only at its end", SCRIPT,
     ENDING,
     r'{marks}[\t ]*[.:!?;]?{marks}"'),

    ("any reference at the end is refused, not only the fragment's own", SCRIPT,
     REFERENCE,
     r"\(?(?:#[0-9]+|GHSA(?:-[0-9a-z]{{4}}){{3}})\)?"),

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

    # #813: the endings #659's pattern let through, each printed with its reference twice
    ("a `!`, `?` or `;` after the reference hides it", SCRIPT,
     ENDING,
     r'{marks}[\t ]*[.:]?{marks}$"'),

    ("a space before the final mark hides the reference", SCRIPT,
     ENDING,
     r'{marks}[.:!?;]?{marks}$"'),

    ("an advisory's id written in another case is not matched", SCRIPT,
     CASE,
     "0)"),

    ("a reference without its parentheses passes, as 0.7.0's two advisories did", SCRIPT,
     REFERENCE,
     r"\({re.escape(reference)}\)"),

    ("code marks around the reference hide it", SCRIPT,
     MARKS,
     'marks = r"[*_]*"'),

    ("an issue's number is matched without its `#`, so #1654 is refused as #654", SCRIPT,
     CALL,
     "        if _ends_with_its_reference(text, fragment.ref):\n"),
]
