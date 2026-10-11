"""The product owner puts a card in the queue from their own page (#562), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
          tools/mutations/562c_the_product_owner_queues_a_card_from_their_page.py

The claims, each a row:

  1. the product card's read offers the queue only on an open card nobody started, and the module
     offers it only outside the queue, by the column's KEY, to a person `promote` would let start
     it — with the board's own name for the queue, in the project's language;
  2. a person who may not start work is told who can, in place of the button;
  3. the page draws only what the server offered, asks before it spends, sends the row with `yes`,
     and says the row's own sentence on the card; the floor's drawer does not draw it.
"""

TEST = "tests/test_the_product_owner_queues_a_card_from_their_page.py"
CATALOG = "openfactory/actions/catalog.py"
MODULE = "openfactory/product/module.py"
VOICE = "openfactory/product/voice.py"
PANEL = "openfactory/api/panel.html"

MUTATIONS = [
    # ── 1. the read offers it where the row would act ────────────────────────────────────────
    ("the product card's read never asks about the queue", CATALOG,
     '    if shown and shown.get("readable") and shown.get("open") and not shown.get("started"):\n'
     '        shown["queue"] = await asyncio.to_thread(\n',
     '    if False:\n'
     '        shown["queue"] = await asyncio.to_thread(\n'),
    ("a closed card is offered the queue", CATALOG,
     '    if shown and shown.get("readable") and shown.get("open") and not shown.get("started"):\n',
     '    if shown and shown.get("readable") and not shown.get("started"):\n'),
    ("a card the factory took up is offered the queue", CATALOG,
     '    if shown and shown.get("readable") and shown.get("open") and not shown.get("started"):\n',
     '    if shown and shown.get("readable") and shown.get("open"):\n'),
    ("a card already in the queue is offered it again", MODULE,
     "        if key == self.QUEUE_KEY or has_started(key):\n            return {\"offered\": False}\n",
     "        if has_started(key):\n            return {\"offered\": False}\n"),
    ("the queue is matched by the platform's name, not the key", MODULE,
     "        if key == self.QUEUE_KEY or has_started(key):\n",
     '        if column == "TO-DO" or has_started(key):\n'),
    ("the module offers it to a person who may not start work", MODULE,
     "        if not may_act(self.project, actor, via=self._via):\n"
     "            return {\"offered\": False,\n"
     "                    \"note\": card_queue_not_yours(",
     "        if False:\n"
     "            return {\"offered\": False,\n"
     "                    \"note\": card_queue_not_yours("),
    ("the queue is named by the platform, not the board", MODULE,
     "        queue = stage_column(board, self.QUEUE_KEY) if board is not None else \"\"\n",
     "        queue = \"TO-DO\"\n"),
    ("the words are English on every board", VOICE,
     "    said = _pick(_CARD_QUEUE, language)\n",
     '    said = _CARD_QUEUE["en"]\n'),
    ("the question before it spends says nothing of money", VOICE,
     '        "ask": ("Putting {ref} in {column} starts the work: the factory picks it up from there, "\n'
     '                "and from then on it spends money. Queue it?"),\n',
     '        "ask": "Queue {ref} in {column}?",\n'),

    # ── 2. who may not is told who can ───────────────────────────────────────────────────────
    ("a person who may not start work is told nothing", MODULE,
     "            return {\"offered\": False,\n"
     "                    \"note\": card_queue_not_yours(ref=number, column=queue, language=lang)}\n",
     "            return {\"offered\": False}\n"),

    # ── 3. the page ──────────────────────────────────────────────────────────────────────────
    ("the page draws the button whatever the server says", PANEL,
     '  if(!q.offered)return q.note?`<p class="pv-note" data-queue>${esc(q.note)}</p>`:"";\n',
     ""),
    ("the server's sentence for who may not is not drawn", PANEL,
     '  if(!q.offered)return q.note?`<p class="pv-note" data-queue>${esc(q.note)}</p>`:"";\n',
     '  if(!q.offered)return "";\n'),
    ("the product card draws no queue", PANEL,
     '${where === "product" ? pvQueueBlock(c) + pvAcceptBlock(c) + pvAdjustBlock(c) : ""}',
     '${where === "product" ? pvAcceptBlock(c) + pvAdjustBlock(c) : ""}'),
    ("the floor's drawer draws the queue too", PANEL,
     '${where === "product" ? pvQueueBlock(c) + pvAcceptBlock(c) + pvAdjustBlock(c) : ""}',
     '${pvQueueBlock(c)}${where === "product" ? pvAcceptBlock(c) + pvAdjustBlock(c) : ""}'),
    ("it spends without asking", PANEL,
     '  if(!confirm(w.ask||"Putting this card in To Do starts the work, and that spends money."))'
     'return;\n',
     ""),
    ("the question is the page's, not the server's", PANEL,
     '  if(!confirm(w.ask||"Putting this card in To Do starts the work, and that spends money."))',
     '  if(!confirm("Putting this card in To Do starts the work, and that spends money."))'),
    ("the row is sent without yes", PANEL,
     "    {project:_prod.project,numbers:[c.ref],yes:true}).catch(()=>null);\n",
     "    {project:_prod.project,numbers:[c.ref]}).catch(()=>null);\n"),
    ("a refusal is said as success", PANEL,
     '  _pv.said={ok:!!(out&&out.ok),how:"queue",',
     '  _pv.said={ok:true,how:"queue",'),
    ("the row's sentence is not said on the card", PANEL,
     '  _pv.said={ok:!!(out&&out.ok),how:"queue",message:(out&&out.message)||"I could not do that '
     'just now."};\n  await pvCardRead(c.ref);\n}\n',
     "  await pvCardRead(c.ref);\n}\n"),
    ("the card is not read again after the press", PANEL,
     '  _pv.said={ok:!!(out&&out.ok),how:"queue",message:(out&&out.message)||"I could not do that '
     'just now."};\n  await pvCardRead(c.ref);\n}\n',
     '  _pv.said={ok:!!(out&&out.ok),how:"queue",message:(out&&out.message)||"I could not do that '
     'just now."};\n  paintPvBoard();\n}\n'),
]
