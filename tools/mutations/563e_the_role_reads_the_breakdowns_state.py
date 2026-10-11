"""The role reads each agreed requirement's breakdown, and a breakdown the panel started is told
where the requirement was written (#563, ADR-0051 D18, slice 18e), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/563e_the_role_reads_the_breakdowns_state.py

The claims, each a row:

  1. the index's breakdown column: running now, the cards that execute the requirement, read as
     the breakdown reads them and each said open, delivered or cancelled, none filed — and
     unknown, never "not running", when the engine cannot be asked;
     it is explained beside the index, and the card marker is kept off an agreed requirement;
  2. the module asks the engine, and one that cannot be asked is unknown;
  3. the engine is listed once for this project alone;
  4. a breakdown the panel starts is told to the conversation the requirement's delivery loop
     names — the latest — in its room when that is the room, and to nobody new otherwise.
"""

TEST = "tests/test_the_role_reads_the_breakdowns_state.py"
ROLE = "openfactory/product/role.py"
MODULE = "openfactory/product/module.py"
BREAKING = "openfactory/product/breaking.py"
CATALOG = "openfactory/actions/catalog.py"

MUTATIONS = [
    # 1. the column
    ("TODAY'S RUN: the role is never told a breakdown is running", ROLE,
     "            if running is not None and r.number in running:",
     "            if False:"),
    ("a closed card is read as open work", ROLE,
     '                state = ("cards" if str(getattr(card, "state", "") or "open") != "closed"',
     '                state = ("cards" if True'),
    ("a cancelled card is said delivered", ROLE,
     '                         else "delivered" if getattr(card, "delivered", False) else "cancelled")',
     '                         else "delivered")'),
    ("REVIEW OF #629: a delivered requirement reads none filed", ROLE,
     "            for card in _executing(self.cards, r.number):",
     "            for card in [c for c in _executing(self.cards, r.number)\n"
     "                         if str(getattr(c, \"state\", \"\") or \"open\") != \"closed\"]:"),
    ("the column is shown without what delivered and cancelled mean", ROLE,
     '    "the closed ones that `delivered` their part, the `cancelled` ones, which carry nothing, "\n',
     ""),
    ("an unknown engine is read as nothing running", ROLE,
     "            if running is None:\n                said.append(\"whether one is running is unknown\")\n",
     ""),
    ("an unknown engine is said as none filed", ROLE,
     '                said.append("none filed" if running is not None else "no open cards")',
     '                said.append("none filed")'),
    ("the column is computed and never shown", ROLE,
     "                 requirement_index(self.corpus, breakdowns=column)]",
     "                 requirement_index(self.corpus)]"),
    ("the column is shown without what it means", ROLE,
     "        if column is not None:\n            parts += [\"\", _BREAKDOWN_COLUMN]\n", ""),
    ("the card marker is offered for an agreed requirement's work", ROLE,
     '"you should argue into a requirement, nor for a broken promise, NOR FOR THE WORK OF "\n'
     '            "AN AGREED REQUIREMENT, which its breakdown files',
     '"you should argue into a requirement, nor for a broken promise, NOR FOR THE "\n'
     '            "ANY REQUIREMENT, which its breakdown files'),
    ("a card about a requirement need not name it", ROLE,
     '"tasks\\"). A card you draft about any requirement names it as REQ-NNNN in its title or "',
     '"tasks\\"). "'),

    # 2. the module
    ("the module never asks the engine", MODULE,
     "                           breakdowns=_breakdowns_of(self.project),\n", ""),
    ("an engine that cannot be asked is read as nothing running", MODULE,
     "        return Breakdowns(running=None)", "        return Breakdowns(running=frozenset())"),

    # 3. one listing, this project
    ("another project's breakdowns are read as this one's", BREAKING,
     "        tail = str(wf.id)[len(prefix):] if str(wf.id).startswith(prefix) else \"\"",
     "        tail = str(wf.id).rsplit(\"-\", 1)[-1]"),

    # 4. told where it was written
    ("TODAY'S RUN: the panel's breakdown is told to nobody", CATALOG,
     "                                  asked_for=asked_for, conversation=conversation, room=room),",
     "                                  asked_for=asked_for),"),
    ("the oldest conversation wins", BREAKING,
     "    for loop in sorted(loops, key=lambda x: x.ts, reverse=True):",
     "    for loop in sorted(loops, key=lambda x: x.ts):"),
    ("another requirement's conversation is told", BREAKING,
     "             if x.kind == DELIVERY and x.owner == OWNER and x.subject == subject]",
     "             if x.kind == DELIVERY and x.owner == OWNER]"),
    ("the room is never named", CATALOG,
     '    return where, (where if where and where == room_of(proj) else "")',
     '    return where, ""'),
    ("a ledger that cannot be read costs the breakdown", CATALOG,
     "    except Exception:  # noqa: BLE001 — the breakdown runs anyway; only the telling is lost",
     "    except ArithmeticError:  # noqa: BLE001"),
]
