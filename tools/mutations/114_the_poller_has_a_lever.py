"""#114: the poller can be held, and the hold says what it does NOT do.

The reverses are the dangerous half here. A pause that reports "drained" interrupts the very work
it was pulled to protect; a warning printed when nothing is running trains the reader to ignore
it; and an unreadable schedule flattened to ON is the same lie `view.intake` refuses one layer
down.
"""

TEST = "tests/test_the_poller_has_a_lever.py"
CLI = "openfactory/cli.py"
CATALOG = "openfactory/actions/catalog.py"
SCHED = "openfactory/runtime/temporal/schedule.py"
ROWS = "tests/test_the_installation_is_changed_through_its_rows.py"

MUTATIONS = [
    ("pausing what is already paused acts anyway, and overwrites the note explaining the hold",
     SCHED,
     '    if was_on == on:\n        return {"changed": False, "was_on": was_on, "note": str(desc.schedule.state.note or "")}\n',
     ""),

    ("the no-op reports the new note instead of the one that explains the hold", SCHED,
     '        return {"changed": False, "was_on": was_on, "note": str(desc.schedule.state.note or "")}',
     '        return {"changed": False, "was_on": was_on, "note": note}'),

    ("pause and resume are swapped", SCHED,
     "    if on:\n        await handle.unpause(note=note)\n    else:\n        await handle.pause(note=note)",
     "    if on:\n        await handle.pause(note=note)\n    else:\n        await handle.unpause(note=note)"),

    ("a pause stops saying that a running job is still running", CLI,
     '        typer.echo("  the pause holds NEW pickups only — these are already running. Wait for "\n'
     '                   "them before rolling the deployment.")',
     "        pass"),

    ("…and the reverse: the warning is printed when nothing is running", CLI,
     '    running = _in_flight(jobs)\n    if not running:\n        typer.echo("in flight: nothing")\n        return',
     '    running = _in_flight(jobs)\n    if not running:\n        typer.echo("in flight: nothing")'),

    # RE-PINNED 2026-10-20 (#741): the pause's filter moved into the `_poller_hold` row, and the
    # CLI's `_in_flight` now re-filters a list the row already filtered — so cutting the CLI alone
    # survives. The cut that matters is the row's own, read by a front end as `data.in_flight`,
    # and the new module is where a finished job beside a running one is asserted dropped.
    ("a closed job is counted as in flight (the row's answer a front end reads)", CATALOG,
     '    running = None if jobs is None else [j for j in jobs if j.get("status") == "running"]\n',
     "    running = None if jobs is None else list(jobs)\n",
     ROWS),

    ("a schedule that could not be read is reported as ON", CLI,
     '    if not intake.get("known"):\n'
     '        typer.echo("poller: UNKNOWN — the schedule could not be read (is the engine reachable?)")\n'
     "        return\n",
     ""),

    ("an unexplained hold stops saying what it cannot be told apart from", CLI,
     '                  "\\n  note: (none — nothing records why, so the next reader cannot tell this "\n'
     '                  "from an outage)"))',
     '                  ""))'),

    # RE-PINNED (#741): the hold moved into the `poller_pause`/`poller_resume` rows, and the
    # refusal by name with it — the command maps onto the row. Re-raised here, the failure reaches
    # `perform`'s catch-all, which names the row and not the poller nor where to look.
    # RE-PINNED 2026-10-20: the line before the refusal logs at INFO now, so the shell says the
    # failure once; the claim is unchanged.
    ("an unreachable engine raises instead of refusing by name", CATALOG,
     '        log.info("could not %s the poller for %s: %s", verb, by, exc)\n',
     "        raise\n"),

    ("the note stops naming who pulled the lever", CLI,
     # RE-PINNED (#741): the shell's login is read through `_shell_user` now.
     '    reason = note or f"paused by {_shell_user()} via `openfactory poller pause`"',
     '    reason = note or ""'),
]
