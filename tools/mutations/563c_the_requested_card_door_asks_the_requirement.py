"""The requested-card door asks the requirement a card names before it files it (#563, ADR-0051
D18, slice 18c), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/563c_the_requested_card_door_asks_the_requirement.py

The claims, each a row:

  1. a requested card naming an accepted requirement, in its title or its body, is never filed;
  2. what is said is what the requirement has: a breakdown running, the open cards that execute it
     (and only those), or neither, and then the breakdown is offered in the words that start it;
  3. a card naming no requirement, or one that is not a promise, is filed as before, and the
     engine is not asked about it;
  4. an engine that cannot be asked holds the card all the same.
"""

TEST = "tests/test_the_requested_card_door_asks_the_requirement.py"
MODULE = "openfactory/product/module.py"
VOICE = "openfactory/product/voice.py"

MUTATIONS = [
    # 1. never filed
    ("TODAY'S RUN: the requested card is filed beside the breakdown's", MODULE,
     "        held = self._held_for_its_requirement(f\"{name}\\n{described}\", ctx)\n"
     "        if held is not None:\n            return held\n", ""),
    ("only the title is read for the requirement", MODULE,
     "        held = self._held_for_its_requirement(f\"{name}\\n{described}\", ctx)",
     "        held = self._held_for_its_requirement(name, ctx)"),
    ("a requirement is named only as REQ-NNNN, four digits", MODULE,
     '_REQUIREMENT_NAMED_RE = re.compile(r"\\bREQ[- ]?#?(\\d{1,6})\\b", re.IGNORECASE)',
     '_REQUIREMENT_NAMED_RE = re.compile(r"\\bREQ-(\\d{4})\\b")'),

    # 2. what is said
    ("a breakdown running is not asked about", MODULE,
     "            running = self._breakdown_running(number)\n",
     "            running = False\n"),
    ("the cards that execute it are not listed", MODULE,
     "            cards = [] if running else self._cards_executing(number)\n",
     "            cards = []\n"),
    ("a closed card is listed as carrying the work", MODULE,
     "                if str(getattr(t, \"state\", \"\") or \"open\") != \"closed\"\n"
     "                and _cited_requirement",
     "                if True\n                and _cited_requirement"),
    ("every card is listed, whatever requirement it executes", MODULE,
     "                and _cited_requirement(getattr(t, \"body\", \"\") or \"\") == number]",
     "                and True]"),
    ("the breakdown is offered in words that start nothing", VOICE,
     "«quebra o requisito {number} em tarefas»", "«pode quebrar o {number}»"),

    # 3. filed as before
    ("a requirement that is not a promise holds the card", MODULE,
     "            if requirement is None or not requirement.is_promise:\n                continue\n",
     "            if requirement is None:\n                continue\n"),

    # 4. an engine that cannot be asked
    ("an engine that cannot be asked fails the card", MODULE,
     "        except Exception:  # noqa: BLE001 — the card is held either way; only the sentence "
     "differs",
     "        except ArithmeticError:  # noqa: BLE001"),
]
