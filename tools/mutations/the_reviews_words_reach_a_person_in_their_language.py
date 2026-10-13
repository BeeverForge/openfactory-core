"""What the automatic review found reaches a person in their own language (#677), proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/the_reviews_words_reach_a_person_in_their_language.py

The claims, each a row:
  1. every problem the floor raises has a sentence for a person in every language;
  2. a breakdown's card the floor refuses is told in the person's language;
  3. a card the judge refuses is told in the judge's words for the person, asked of it in their
     language, or in the language's own sentence;
  4. a card shown while disputed carries the person's words;
  5. the redraft keeps the findings.
"""

TEST = "tests/test_the_reviews_words_reach_a_person_in_their_language.py"
CARDS = "openfactory/product/cards.py"
ENGINE = "openfactory/product/engine.py"

MUTATIONS = [
    # 1. every problem, every language
    ("a problem has no sentence for a person in Portuguese", CARDS,
     '        "wrong_language": "o cartão não está escrito na língua da conversa",\n', ""),
    ("a problem's fields are not filled in", CARDS,
     "    told = [by_kind[p.kind].format(**p.fields) for p in feedback[:3]",
     "    told = [by_kind[p.kind] for p in feedback[:3]"),

    # 2. the floor's refusal
    ("TODAY'S RUN: the floor's refusal is told as the redraft's instruction", CARDS,
     '    return None, "; ".join(review_said(feedback, said, language))',
     '    return None, "; ".join(feedback[:3]) or "it did not pass the review"'),
    ("the floor's refusal is told in the platform's language", CARDS,
     "    by_kind = _pick(_FLOOR_SAID, language)", '    by_kind = _pick(_FLOOR_SAID, "en")'),

    # 3. the judge's refusal
    ("TODAY'S RUN: the judge's findings are told to the person", CARDS,
     "    if said is not None and said.told:\n        return list(said.told[:3])",
     "    if said is not None and said.findings:\n        return list(said.findings[:3])"),
    ("the judge's words for the person are not read", CARDS,
     "                  passed=not because, because=tuple(because), told=told)",
     "                  passed=not because, because=tuple(because))"),
    ("the judge is not told the person's language", CARDS,
     "                                             source_note=REQUIREMENT_NOTE, language=language)),",
     "                                             source_note=REQUIREMENT_NOTE)),"),
    ("the judge is not asked for the person's words", CARDS,
     '"findings": [str], "told": [str], "ask": str}\\n\'',
     '"findings": [str], "ask": str}\\n\''),
    ("a judge that said nothing for the person is told nothing at all", CARDS,
     "    return told or [_pick(_REVIEW_UNSAID, language)]", "    return told"),

    # 4. the card shown while disputed
    ("TODAY'S RUN: a disputed card quotes the findings", ENGINE,
     "    disputed = (tuple(cards.review_said([], composed.ruling, lang))\n",
     "    disputed = (tuple(composed.ruling.findings)\n"),

    # 5. the redraft
    ("the redraft reads the person's words instead of the findings", CARDS,
     "            feedback = list(said.findings) or list(said.because)\n        if attempt == ATTEMPTS",
     "            feedback = list(said.told) or list(said.because)\n        if attempt == ATTEMPTS"),
]
