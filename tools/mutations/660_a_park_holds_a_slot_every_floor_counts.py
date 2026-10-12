"""A job that holds one of the deployment's slots is counted by every floor (#660, journey 0),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/660_a_park_holds_a_slot_every_floor_counts.py

The claims, each a row:
  1. a floor is Armed only while a slot of the deployment is free — a park is a running job, and
     another project's or product's job holds a slot as this project's does; the other job is
     never named, and a park's way out is said;
  2. the floor is told the number of slots the poller counts against;
  3. the role is told a live job holds a slot, and what an impediment's deadline does;
  4. the park carries what its deadline does, and a decision park claims none;
  5. a merge verb asked of a parked job names the verbs that answer it.
"""

TEST = "tests/test_a_park_holds_a_slot_every_floor_counts.py"
LADDER = "openfactory/floor/ladder.py"
READING = "openfactory/floor/reading.py"
MODEL = "openfactory/product/model.py"
WORKFLOW = "openfactory/runtime/temporal/workflow.py"
CATALOG = "openfactory/actions/catalog.py"

MUTATIONS = [
    # 1. the ladder
    ("TODAY'S RUN: the rung counts only this project's jobs", LADDER,
     '    held = [j for j in (inputs.jobs or []) if j.get("status") == "running"]',
     '    held = [j for j in jobs if j.get("status") == "running"]'),
    ("a parked job is not counted as holding its slot", LADDER,
     '    held = [j for j in (inputs.jobs or []) if j.get("status") == "running"]',
     '    held = [j for j in (inputs.jobs or []) if j.get("status") == "running"\n'
     '            and not j.get("attention")]'),
    ("every slot held reads as one still free", LADDER,
     "    full = inputs.slots is not None and len(held) >= inputs.slots",
     "    full = inputs.slots is not None and len(held) > inputs.slots"),
    ("a caller that did not say the slots is read as zero of them", LADDER,
     "    full = inputs.slots is not None and len(held) >= inputs.slots",
     "    full = len(held) >= (inputs.slots or 0)"),
    ("the job that holds the slot is named on another project's floor", LADDER,
     '    said = (f"every job slot of this deployment is held ({len(held)} of {slots}) — the next "',
     '    said = (f"{held[0].get(\'project\')} #{held[0].get(\'issue\')}: every job slot of this '
     'deployment is held ({len(held)} of {slots}) — the next "'),
    ("a park holding the slot is not said with its way out", LADDER,
     "    if any(waits_on_a_person(j) for j in held):", "    if False:"),
    ("a deployment that runs no job at once is read as one whose slots are held", LADDER,
     "    if not slots:\n        return (", "    if False:\n        return ("),
    ("a floor waiting for a slot reads as stopped", LADDER,
     '                         kind="clock" if inputs.slots else "stopped"))',
     '                         kind="stopped"))'),

    # 2. the reading
    ("the floor is not told the slots the poller counts against", READING,
     "        got.slots = max_concurrent_jobs()\n", "        got.slots = None\n"),

    # 3. the role
    ("the role is not told a live job holds a slot", MODEL,
     "        lines += _holds_a_slot(job)\n", ""),
    ("a finished job is said to hold a slot", MODEL,
     '    if live and job.get("status") == "running":', "    if live:"),
    ("an impediment's deadline reaches the role as a bare date", MODEL,
     '    if act.get("wakes_at") and act.get("at_deadline") == "skip":', "    if False:"),

    # 4. the park
    ("the park says nothing of what its deadline does", WORKFLOW,
     '                        "at_deadline": default if timeout <= _HELD_UNTIL_ANSWERED else None,',
     '                        "at_deadline": None,'),
    ("a decision park, held until answered, claims a deadline", WORKFLOW,
     '                        "at_deadline": default if timeout <= _HELD_UNTIL_ANSWERED else None,',
     '                        "at_deadline": default,'),

    # 5. the refusal
    ("a merge verb asked of a parked job guesses instead of naming resume and skip", CATALOG,
     "        if waiting:\n            what, how = waiting",
     "        if False:\n            what, how = waiting"),
]
