"""The queue is proposed from what each candidate asks, in its own words, bounded (#567), proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/567c_the_queue_is_proposed_from_what_each_card_asks.py

The role was asked to hold back what depends on something not done, over a list of titles. The
claims, each a row:

  1. each candidate carries what it asks — its objective, or the opening of its body — the
     requirement it executes, and its first criteria;
  2. each card is bounded, and what the bound left out is said;
  3. the role is asked to read what a card builds on and to hold back what waits on something not
     delivered.
"""

TEST = "tests/test_the_queue_reads_what_each_card_asks.py"
QUEUE = "openfactory/product/queue.py"

MUTATIONS = [
    # 1. what each candidate carries
    ("TODAY'S RUN: the candidates are titles again", QUEUE,
     '        lines += [f"- #{t.number}: {t.title}", *what_it_asks(t)]',
     '        lines += [f"- #{t.number}: {t.title}"]'),
    ("the requirement a card executes is not said", QUEUE,
     "    if executes is not None:\n        lines.append(",
     "    if False:\n        lines.append("),
    ("the criteria are not given", QUEUE,
     '    lines += [f"  - criterion: {_cut(c, _CRITERION_CHARS)}" for c in '
     "criteria[:_CRITERIA_PER_CARD]]",
     "    lines += []"),
    ("a card with no objective section is read as its title", QUEUE,
     "    if not asks or asks == ticket.title.strip():\n        asks = _opening(body)",
     "    if not asks:\n        asks = _opening(body)"),

    # 2. the bound
    ("every criterion is given, however many", QUEUE,
     "for c in criteria[:_CRITERIA_PER_CARD]]",
     "for c in criteria]"),
    ("a long objective or criterion is given whole", QUEUE,
     '    return said if len(said) <= at else said[:at - 1].rstrip() + "…"',
     "    return said"),
    ("the criteria the bound left out are not said", QUEUE,
     "    if len(criteria) > _CRITERIA_PER_CARD:\n        lines.append(",
     "    if False:\n        lines.append("),

    # 3. the instruction
    ("the role is not asked to hold back what builds on something not delivered", QUEUE,
     '        "Read what each candidate builds on in its own words below — what it asks and its "\n'
     '        "criteria. A card that builds on something no card already done, being worked on, or "\n'
     '        "ahead of it in your order delivers is held back, saying what it waits for.",\n'
     '        "",\n',
     ""),
]
