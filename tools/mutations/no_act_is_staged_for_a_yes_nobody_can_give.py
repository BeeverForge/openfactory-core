"""No act the role proposes is staged for a yes nobody can give (journey 0, #640, C-13; #667 and
#638), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/no_act_is_staged_for_a_yes_nobody_can_give.py

The claims, each a row:
  1. off the admin list, where no admin's yes counts, every act of `role.ACTS` is refused at once,
     the rule read off the table and not a list of its own;
  2. where an admin's yes counts, the act is staged for them, every act naming them, the agreement
     included;
  3. somebody who may act is asked as before.
"""

TEST = "tests/test_no_act_is_staged_for_a_yes_nobody_can_give.py"
ENGINE = "openfactory/product/engine.py"

MUTATIONS = [
    # 1. refused at once
    ("TODAY'S RUN: no act is refused before it is staged", ENGINE,
     "    if (intent in _acts_staged_for_a_yes() and not may_act(project, user)",
     "    if (intent in () and not may_act(project, user)"),
    ("the rule reads a list of its own, the two acts #634 named", ENGINE,
     "    return frozenset(GESTURE_INTENT.values())\n",
     '    return frozenset({"breakdown", "refine"})\n'),
    # 2. staged for the admins
    ("an act the admins could confirm is refused at once", ENGINE,
     "            and not _admin_mentions(project)):\n        return said(unauthorized_message(",
     "            ):\n        return said(unauthorized_message("),
    ("the agreement names nobody under it", ENGINE,
     '                ask += admins_must_confirm(admins, "agreement", language=lang)\n',
     "                pass\n"),
    # 3. as before
    ("somebody who may act is refused too", ENGINE,
     "    if (intent in _acts_staged_for_a_yes() and not may_act(project, user)",
     "    if (intent in _acts_staged_for_a_yes() and True"),
]
