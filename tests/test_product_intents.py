

from openfactory.product.intents import match_intent

# ── the English half of the taught sentences (#24 item 5) ───────────────────────────────────────
#
# Every instruction this surface gives has an `en` catalogue entry — "say \"accept requirement
# {N}\"", "align #{number} to requirement N", "close #N as a duplicate of #M" — and the grammar
# only knew Portuguese: an English deployment's own taught sentence parsed as conversation. Half
# the surface was dead for exactly the client (Deskline) that speaks English.

# RETIRED 2026-10-10 (#565): the two tests of the English `accept` pattern. Agreeing to a
# requirement is an act the role proposes (`[[ACORDO: REQ-N]]`), so "accept requirement 6" — and
# "I accept that requirement 3 is unclear", which is not an agreement — are read by the model; what
# the pattern's adjacency guarded is in that marker's instruction
# (`tests/test_the_role_proposes_what_a_requirement_needs.py`).


def test_the_taught_english_align_parses_with_both_numbers():
    got = match_intent("align #288 to requirement 6")
    assert got is not None and got[0] == "align"
    assert got[1]["number"] == "288" and got[1]["requirement"] == "6"
    assert match_intent("realign the #288 with requirement 6")[0] == "align"


def test_english_align_requires_the_preposition():
    """"align" floats free in English prose; the taught sentence always carries to/with/against."""
    assert match_intent("we should align the roadmap with requirement 4 someday?") is None


def test_the_taught_english_close_carries_its_survivor():
    """"as a duplicate OF #288" used to stop at "of": the survivor fell to the ask-which-card
    path, and the taught sentence ended in a question round-trip instead of the act it states."""
    got = match_intent("close #511 as a duplicate of #288")
    assert got is not None and got[0] == "close"
    assert got[1]["in_favour_of"] == "288", "the stated survivor was dropped to the unclear path"

    got = match_intent("close #511 in favour of #288")
    assert got[1]["in_favour_of"] == "288"


def test_the_portuguese_grammar_did_not_move():
    """The bridge gained English connectors; the Portuguese sentences must parse exactly as
    before — this file's own earlier cases re-asserted beside the new ones."""
    assert match_intent("fecha o #511 como duplicado do #288")[1]["in_favour_of"] == "288"
    assert match_intent("alinha o #288 ao requisito 6")[1]["requirement"] == "6"
