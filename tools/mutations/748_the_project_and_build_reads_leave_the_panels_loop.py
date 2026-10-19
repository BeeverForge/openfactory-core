"""The floor's project and build reads leave the loop that awaits them, and still answer (#748).

`gather` called `_projects()` and `_build()` bare, and `_projects` runs `box_prove.health` once per
registered project: git through the repo cache, then `docker image inspect` or `<harness>
--version`. Measured 2026-10-18 with 19 projects whose box read was doubled by a 30 ms sleep, a
10 ms heartbeat on the same loop waited 588 ms on main and 11-15 ms with both reads behind
`asyncio.to_thread`.

The rows are: each read put back on the loop's own thread (the defect, once per field); the cure
there and its answer dropped; and an unreadable registry read as a deployment with no projects
(engineering-lessons §2), which must still hold once the read runs in a thread.
"""

TEST = "tests/test_the_project_and_build_reads_leave_the_panels_loop.py"
READING = "openfactory/floor/reading.py"

MUTATIONS = [
    ("the box read runs git on the loop's own thread again — the defect", READING,
     "got.projects = await asyncio.to_thread(_projects)",
     "got.projects = _projects()"),

    ("the build stamps are read on the loop's own thread again", READING,
     "got.build = await asyncio.to_thread(_build)",
     "got.build = _build()"),

    ("the read leaves the loop but its answer is dropped", READING,
     "got.projects = await asyncio.to_thread(_projects)",
     "got.projects = await asyncio.to_thread(lambda: None)"),

    ("an unreadable registry reads as no projects", READING,
     '        log.warning("floor: could not read the project list (%s)", str(exc)[:160])\n'
     "        return None",
     '        log.warning("floor: could not read the project list (%s)", str(exc)[:160])\n'
     "        return []"),
]
