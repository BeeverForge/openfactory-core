"""No proposal is staged while what it would write waits on an answer (journey 0, #640, C-02;
#670), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/no_proposal_is_staged_while_its_text_waits_on_an_answer.py

The claims, each a row:
  1. a requirement whose drafter names what it cannot write without stages nothing, and what was
     on the table stays; the drafter's field decides, never the prose;
  2. the questions are listed under the role's reply unless that reply has just asked;
  3. a staged requirement says what it leaves open can be answered after it;
  4. the drafter is told what `ask_first` is for, the schema carries it, and the draft keeps it.
"""

TEST = "tests/test_no_proposal_is_staged_while_its_text_waits_on_an_answer.py"
ENGINE = "openfactory/product/engine.py"
ROLE = "openfactory/product/role.py"

MUTATIONS = [
    # 1. nothing staged
    ("TODAY'S RUN: a requirement that waits on an answer is proposed anyway", ENGINE,
     "    if first:\n        from openfactory.product.voice import asked_first\n",
     "    if False:\n        from openfactory.product.voice import asked_first\n"),
    ("the drafter's field is not read", ENGINE,
     '    first = [str(q).strip() for q in (getattr(draft, "ask_first", None) or []) '
     "if str(q).strip()]",
     "    first = []"),
    # 2. listed unless asked
    ("the questions are listed under a reply that has just asked them", ENGINE,
     'listed="?" not in preamble', "listed=True"),
    ("the questions are never listed", ENGINE, 'listed="?" not in preamble', "listed=False"),
    # 3. what is left open
    ("a staged requirement says nothing of what it leaves open", ENGINE,
     "        + still_open(questions=list(draft.questions or []), language=lang))",
     "        )"),
    # 4. the drafter
    ("the drafter is not told what ask_first is for", ROLE,
     "`ask_first` IS FOR WHAT YOU CANNOT WRITE WITHOUT. A question goes there",
     "A question goes there"),
    ("the schema does not carry ask_first", ROLE, '  "ask_first": [str],\n', ""),
    ("the draft does not keep ask_first", ROLE,
     "    ask_first: list[str] = Field(default_factory=list)\n", ""),
]
