from openfactory.product.intents import match_intent
from openfactory.product.role import read_answer

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

# RETIRED 2026-10-11 (#565 slice b): the four tests of the `align` and `close` patterns. Both are
# acts the role proposes (`[[ALINHAR: #N; REQ-M]]`, `[[FECHAR: #N; em favor de #M]]`), so "align
# #288 to requirement 6" and "close #511 as a duplicate of #288" are read by the model in whatever
# language the person writes. What the English bridge carried — the survivor named after "of" —
# is a connector of the close marker now, in both languages, and is held below.


def test_the_taught_sentences_reach_no_pattern():
    for sentence in ("align #288 to requirement 6", "close #511 as a duplicate of #288",
                     "alinha o #288 ao requisito 6", "fecha o #511 como duplicado do #288"):
        assert match_intent(sentence) is None, (sentence, match_intent(sentence))


def test_the_close_marker_carries_its_survivor_in_either_language():
    """"as a duplicate OF #288" used to stop at "of" and the survivor fell to the ask-which-card
    path; the marker names it with either connector, in either spelling."""
    for written in ("[[FECHAR: #511; em favor de #288]]", "[[FECHAR: #511; em favor do #288]]",
                    "[[FECHAR: #511; in favour of #288]]", "[[FECHAR: #511; in favor of #288]]"):
        answer = read_answer(f"Entendi.\n{written}")
        assert answer.gesture == "close", (written, answer.gesture)
        assert answer.gesture_args["number"] == "#511", (written, answer.gesture_args)
        assert answer.gesture_args["in_favour_of"] == "#288", (written, answer.gesture_args)


def test_the_align_marker_carries_both_numbers():
    for written in ("[[ALINHAR: #288; REQ-0006]]", "[[ALINHAR: #288; 6]]"):
        answer = read_answer(f"Entendi.\n{written}")
        assert answer.gesture == "align", (written, answer.gesture)
        assert answer.gesture_args["number"] == "#288", (written, answer.gesture_args)
        assert int(answer.gesture_args["requirement"]) == 6, (written, answer.gesture_args)
