"""A yes or a no is read without the mention that addressed it (journey 0, #640, C-13; #667), proven
by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/a_yes_or_a_no_is_read_without_the_mention_that_addressed_it.py

The claims, each a row:
  1. every assent and every rejection opener is read the same with every mention the panel can
     produce, before or after, with or without a vocative comma;
  2. a word joined to an `@` is an address, not a mention; the rejections the sweep reads are the
     ones the pattern reads;
  3. a late answer addressed to the role hears that its proposal expired.
"""

TEST = "tests/test_a_yes_or_a_no_is_read_without_the_mention_that_addressed_it.py"
ASSENT = "openfactory/language/assent.py"
STAGING = "openfactory/product/staging.py"
ENGINE = "openfactory/product/engine.py"

MUTATIONS = [
    # 1. addressed
    ("TODAY'S RUN: a yes reads the mention as a word of it", ASSENT,
     "    body = unaddressed(text)\n", '    body = text or ""\n'),
    ("a no reads the mention as a word of it", STAGING,
     "    return bool(_NO.match(assent.unaddressed(text)))",
     '    return bool(_NO.match(text or ""))'),
    ("a vocative comma after the mention is left in front of the yes", ASSENT,
     '@[\\w.-]+[,:;]?")', '@[\\w.-]+")'),
    ("a comma before a trailing mention is left behind the yes", ASSENT,
     'r"[,;:]?\\s*(?<![\\w@])@', 'r"\\s*(?<![\\w@])@'),
    # 2. what a mention is, and what a no is
    ("an address is read as a mention", ASSENT,
     'r"[,;:]?\\s*(?<![\\w@])@', 'r"[,;:]?\\s*@'),
    ("the rejections the pattern reads are not the table's", STAGING,
     '"|".join(map(re.escape, NO_OPENERS))', '"n[ãa]o|nao"'),
    # 3. through the turn
    ("a late answer is not told its proposal expired", ENGINE,
     "    if not waiting and (is_yes(text) or is_no(text)) and _expired_recently(",
     "    if not waiting and False and _expired_recently("),
]
