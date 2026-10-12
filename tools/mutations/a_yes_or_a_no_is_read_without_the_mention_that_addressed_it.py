"""A yes or a no is read without the mention that addressed it to the role — and only that one
(journey 0, #640, C-13; #667 and its review), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/a_yes_or_a_no_is_read_without_the_mention_that_addressed_it.py

The claims, each a row:
  1. every assent and every rejection opener is read the same with every mention of the role the
     panel can produce, before or after, with or without a vocative comma;
  2. a word joined to an `@` is an address, not a mention; the rejections the sweep reads are the
     ones the pattern reads;
  3. only the role's address is read past: a person's mention stays, the role's name is its
     address where the project names it, accents and case aside;
  4. a late answer addressed to the role, by a handle or by its name, hears its proposal expired.
"""

TEST = "tests/test_a_yes_or_a_no_is_read_without_the_mention_that_addressed_it.py"
ADDRESSING = "openfactory/product/addressing.py"
STAGING = "openfactory/product/staging.py"
ENGINE = "openfactory/product/engine.py"

MUTATIONS = [
    # 1. addressed
    ("TODAY'S RUN: a yes reads the role's address as a word of it", STAGING,
     "    return assent.asserts_assent(without_the_roles_address(text, project))",
     "    return assent.asserts_assent(text)"),
    ("a no reads the role's address as a word of it", STAGING,
     "    return bool(_NO.match(without_the_roles_address(text, project)))",
     '    return bool(_NO.match(text or ""))'),
    ("a vocative comma after the mention is left in front of the yes", ADDRESSING,
     '@([\\w.-]+)[,:;]?")', '@([\\w.-]+)")'),
    ("a comma before a trailing mention is left behind the yes", ADDRESSING,
     'r"[,;:]?\\s*(?<![\\w@])@(', 'r"\\s*(?<![\\w@])@('),
    # 2. what a mention is, and what a no is
    ("an address is read as a mention", ADDRESSING,
     'r"[,;:]?\\s*(?<![\\w@])@(', 'r"[,;:]?\\s*@('),
    ("the rejections the pattern reads are not the table's", STAGING,
     '"|".join(map(re.escape, NO_OPENERS))', '"n[ãa]o|nao"'),
    # 3. only the role's address
    ("REVIEW OF #667: a person's mention is read past as the role's address", ADDRESSING,
     '        lambda m: " " if _flat(m.group(1).rstrip(".-")) in names else m.group(0), text or "")',
     '        lambda m: " ", text or "")'),
    ("the role's name is not its address", ADDRESSING,
     "    names = {*HANDLES, *((_flat(name), _flat(name.split()[0])) if name else ())}",
     "    names = {*HANDLES}"),
    ("the role's name with an accent is somebody else", ADDRESSING,
     '" " if _flat(m.group(1).rstrip(".-")) in names else',
     '" " if m.group(1).rstrip(".-").lower() in names else'),
    # 4. through the turn
    ("a late answer is not told its proposal expired", ENGINE,
     "            and _expired_recently(thread, channel, project=project)):",
     "            and False):"),
    ("a late answer to the role's name is read without the role", ENGINE,
     "    if (not waiting and (is_yes(text, project=project) or is_no(text, project=project))",
     "    if (not waiting and (is_yes(text) or is_no(text))"),
]
