"""#744: the schedule module, run as documented, creates every schedule `main()` names.

Two claims, each held by one test in the plan's `TEST` file:

  - C1. `python -m openfactory.runtime.temporal.schedule` creates the poller and, for each enabled
    project, the tech-lead watch, the product sweep, the knowledge refresh and the card-question
    sweep. Held by running the module under `run_name="__main__"` against a fake engine and
    comparing the created ids with the set the module's constants build, so a run that raises
    nothing but creates one schedule fewer is red too.
  - C2. Every `if __name__ == "__main__"` block in the package is its module's last top-level
    statement. Held by parsing each module, so it covers modules other than schedule.py.

The first cut is the defect as it was on c0a50f3, and it is run against each test on its own, so
the report shows that both see it.
"""

TEST = "tests/test_the_schedule_module_run_as_documented_creates_every_schedule_it_names.py"
SCHED = "openfactory/runtime/temporal/schedule.py"
STARTER = "openfactory/runtime/temporal/starter.py"
C1 = TEST + "::test_running_the_module_as_documented_creates_the_poller_and_every_per_project_schedule"
C2 = TEST + "::test_the_main_block_is_the_last_statement_of_every_module_that_has_one"

_BLOCK_ABOVE = ('\n\nif __name__ == "__main__":\n    asyncio.run(main())\n'
                "\n\ndef _product_schedule(")

MUTATIONS = [
    ("the __main__ block is back above the per-project functions: the run stops with NameError",
     SCHED, "\n\ndef _product_schedule(", _BLOCK_ABOVE, C1),

    ("the __main__ block is back above the per-project functions: it is no longer last",
     SCHED, "\n\ndef _product_schedule(", _BLOCK_ABOVE, C2),

    ("main() stops creating the card-question sweep, and raises nothing",
     SCHED,
     "                 + await ensure_okf_refresh() + await ensure_card_question_sweeps()):",
     "                 + await ensure_okf_refresh()):",
     C1),

    ("the __main__ block runs nothing", SCHED,
     "    asyncio.run(main())", "    pass", C1),

    ("another module gets a statement after its __main__ block", STARTER,
     'if __name__ == "__main__":\n    asyncio.run(main())\n',
     'if __name__ == "__main__":\n    asyncio.run(main())\n\n\ndef _late():\n    ...\n',
     C2),
]
