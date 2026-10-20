"""Askers that arrive together share one job list (#754, criterion 4: "Let askers that arrive
together share one scan").

`list_jobs` was asked by eight call sites (the floor, the inbox, the decisions route, the jobs
route, every browser's stream tick, the tech-lead's standing loop, the action catalog twice), and
each one paid the whole scan: one `list_workflows`, then a describe and up to three worker queries
per running row. A downstream deployment (one host, ~19 projects) reported the floor and the
stream overrunning `OPENFACTORY_ENGINE_DEADLINE` together; nothing shared the work, so six readers
at one instant cost six scans of the same engine for the same answer.

The share is `floor/reading.py`'s single flight (#165, #166), so each claim below is one it already
holds for the schedule read, restated for this read:

- ONE SCAN, HOWEVER MANY ARRIVE (`scans == 1` for six).
- A FAILURE IS SHARED, NOT QUEUED: six askers behind a refusal all get THAT refusal, as the
  engine's own error (a refusal is an answer, not `EngineUnreachable`, #159), from one scan.
- ONE ASKER GOING AWAY (a browser closed) DOES NOT CANCEL THE SCAN under the others.
- A DIFFERENT QUESTION NEVER JOINS: the scan is shared only by askers who would have read the same
  thing (engineering-lessons §11, "what a cache is keyed on has to be what the work it skips would
  have read") — the namespace, the limit and the query — and NEVER ACROSS ENGINES: two clients
  asking the same question are two scans.
- EACH ASKER IS HANDED A LIST OF ITS OWN (#165): a caller that edits its rows edits nobody else's.

The first three are red on `main` (6, 6 and 2 scans). The last three pass there — nothing is
shared, so nothing can be shared wrongly — and are what the mutation plan's "the key forgets the
question / the client" and "hand out one object between them" cuts turn red
(`tools/mutations/754_the_job_list_is_asked_side_by_side_and_shared.py`).
"""

from __future__ import annotations

import asyncio

import pytest

from openfactory.runtime.temporal import view as tv
from openfactory.runtime.temporal.vocabulary import EngineUnreachable
from tests.job_list_scans import PROJECT, RECENT, CountedEngine, forget, scans_of


@pytest.fixture(autouse=True)
def _nothing_remembered_between_tests(monkeypatch):
    """A clean engine memory, no registry, and a UI address, so each row's link names the
    namespace it was read in."""
    monkeypatch.setenv("OPENFACTORY_ENGINE_DEADLINE", "10")
    monkeypatch.setattr(tv, "_registered_projects", lambda: [PROJECT])
    monkeypatch.setattr(tv, "ui_base", lambda: "http://engine-ui.example")
    tv.reset_clients()
    forget()
    yield
    forget()
    tv.reset_clients()


async def test_six_askers_arriving_together_cost_one_scan():
    """Criterion 4. Six `list_jobs` at one instant on one client, for one question: one scan, and
    six equal answers. On `main`: six scans."""
    engine = CountedEngine()

    answers = await asyncio.gather(*(tv.list_jobs(engine, "default") for _ in range(6)))

    assert engine.scans == 1, f"six askers together cost {engine.scans} scans of the engine"
    assert all(rows == answers[0] for rows in answers)
    assert len(answers[0]) == 8


async def test_askers_queued_behind_a_failing_scan_share_its_failure():
    """Criterion 4, the failure side. The listing is refused after 50 ms: all six get the engine's
    own `RuntimeError` from the one scan that failed, not a queue of six refusals one after
    another, and not `EngineUnreachable` (a fast refusal is an answer, #159). On `main`: six
    scans."""
    engine = CountedEngine(failing=6)

    answers = await asyncio.gather(*(tv.list_jobs(engine, "default") for _ in range(6)),
                                   return_exceptions=True)

    assert all(isinstance(a, RuntimeError) and not isinstance(a, EngineUnreachable)
               for a in answers), answers
    assert all("the engine refused the listing" in str(a) for a in answers)
    assert engine.scans == 1, f"six askers behind a refusal cost {engine.scans} scans"


async def test_an_asker_that_goes_away_does_not_take_the_scan_from_the_others():
    """Criterion 4. Two askers; the first is cancelled once the scan is under way (a browser that
    closed its tab). The second is answered by that same scan. On `main`: each asker ran its own,
    two scans."""
    engine = CountedEngine()

    first = asyncio.create_task(tv.list_jobs(engine, "default"))
    second = asyncio.create_task(tv.list_jobs(engine, "default"))
    while engine.scans == 0:
        await asyncio.sleep(0)
    first.cancel()

    rows = await second

    assert first.cancelled()
    assert len(rows) == 8
    assert engine.scans == 1, f"two askers, one gone, cost {engine.scans} scans"


async def test_askers_with_a_different_question_do_not_share_a_scan():
    """Criterion 4, the key. Four askers together, each asking something the others did not: two
    namespaces, two limits, and a start-time filter. Four scans, each answer the one its question
    has. Passes on `main` (nothing is shared); red under the cuts that drop the namespace, the
    limit or the query from what a joining asker must match."""
    engine = CountedEngine()

    in_a, in_b, five, recent = await asyncio.gather(
        tv.list_jobs(engine, "a", limit=50),
        tv.list_jobs(engine, "b", limit=50),
        tv.list_jobs(engine, "a", limit=5),
        tv.list_jobs(engine, "a", query=RECENT),
    )

    assert engine.scans == 4, f"four different questions were answered by {engine.scans} scans"
    assert sum(RECENT in q for q in engine.seen_query) == 1, engine.seen_query
    assert all("/namespaces/a/" in r["temporal_url"] for r in in_a + five + recent)
    assert all("/namespaces/b/" in r["temporal_url"] for r in in_b)
    assert (len(in_a), len(in_b), len(five), len(recent)) == (8, 8, 5, 2)
    assert len(scans_of(in_a + in_b + five + recent)) == 4


async def test_askers_on_two_engines_together_are_each_scanned():
    """Criterion 4, the key's client: two engines are two floors. Askers on two clients at one
    instant, asking the same question on one loop: each engine is scanned once and each asker reads
    its own engine's rows. Passes on HEAD; red under the cut that leaves the client out of what a
    joining asker must match (the second engine is never asked, and its asker reads eight rows of
    the first's)."""
    one, other = CountedEngine(), CountedEngine(issues=3)

    from_one, from_other = await asyncio.gather(tv.list_jobs(one, "default"),
                                                tv.list_jobs(other, "default"))

    assert (one.scans, other.scans) == (1, 1)
    assert (len(from_one), len(from_other)) == (8, 3)


async def test_every_asker_is_handed_a_list_of_its_own():
    """Criterion 4, the copy (#165: a shared answer handed out by reference is one any caller can
    rewrite for every other). The first asker edits its first row; the asker beside it and the one
    right after both read the row as the engine gave it. Passes on `main`; red under the cut that
    hands out the stored object."""
    engine = CountedEngine()

    mine, theirs = await asyncio.gather(tv.list_jobs(engine, "default"),
                                        tv.list_jobs(engine, "default"))
    as_given = theirs[0]["state"]
    mine[0]["state"] = "edited by one caller"
    mine.pop()
    later = await tv.list_jobs(engine, "default")

    assert theirs[0]["state"] == as_given == "running"
    assert later[0]["state"] == as_given
    assert len(theirs) == len(later) == 8
