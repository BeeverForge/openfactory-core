"""A front the breakdown meant for another repository of the product never runs in this project's
(journey 0, #640, #665), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/a_front_runs_only_in_its_repository.py

The claims, each a row:
  1. a front filed outside its repository records where it belongs, on the card and for a person;
  2. the card's door does not queue it, and says where it belongs;
  3. the pickup takes it out of the queue and starts no job;
  4. pre-flight does not size a job started on it.
"""

TEST = "tests/test_a_front_runs_only_in_its_repository.py"
MOD = "openfactory/product/module.py"
AUTH = "openfactory/product/authoring.py"
PARSE = "openfactory/adapters/tracker/parse.py"
DOOR = "openfactory/lifecycle/card.py"
PORTS = "openfactory/lifecycle/ports.py"
REPO = "openfactory/runtime/card_repo.py"
ACTS = "openfactory/runtime/temporal/activities.py"

MUTATIONS = [
    # 1. the record
    ("TODAY'S RUN: the card does not record where it belongs", MOD,
     '                                belongs_to="" if where else self._home_of(draft))\n',
     '                                belongs_to="")\n'),
    ("the front matter leaves the repository out", AUTH,
     '        [f"belongs_to: {json.dumps(belongs_to, ensure_ascii=False)}"] if belongs_to else [])\n',
     "        [])\n"),
    ("the card's own repository is recorded as elsewhere", MOD,
     '        if not target or (default and repo_match(target, default)):\n'
     '            return ""\n'
     '        return next((s for s in self._sources() if s and repo_match(target, s)), "")',
     '        if not target:\n'
     '            return ""\n'
     '        return next((s for s in self._sources() if s and repo_match(target, s)), "")'),
    ("the record is not read back", PARSE,
     '        belongs_to=str(fm.get("belongs_to") or "").strip() or None,\n', ""),
    ("the person reading the card is not told", AUTH,
     '          if (belongs_to or "").strip() else []),\n', "          if False else []),\n"),

    # 2. the door
    ("TODAY'S RUN: a card of another repository is queued", DOOR,
     "            if home:\n                return Transition(card=card, event=event, before=seen.state,",
     "            if False:\n                return Transition(card=card, event=event, before=seen.state,"),
    ("the door reads no repository from the card", PORTS,
     '        belongs_to = str(getattr(ticket, "belongs_to", "") or "")\n',
     '        belongs_to = ""\n'),
    ("a card naming this project's own repository reads as elsewhere", REPO,
     '        return "" if _is_default_repo(project, repo) else repo\n',
     "        return repo\n"),

    # 3. the pickup
    ("a card of another repository in the queue is started", ACTS,
     "        if await asyncio.to_thread(_taken_out_for_its_repository, project, tracker, board, ref):\n"
     "            continue\n", ""),
    ("the pickup takes it out without saying where it belongs", ACTS,
     '    note = card_belongs_elsewhere("pickup", ref=ref, home=home, here=_here(project),\n'
     '                                  language=getattr(project, "language", None))\n',
     '    note = "not here"\n'),

    # 4. pre-flight
    ("a job on a card of another repository is sized", ACTS,
     "    if elsewhere:\n"
     "        return PreflightVerdict(verdict=\"unclear\", questions=[elsewhere], reasons=elsewhere)\n",
     ""),
]
