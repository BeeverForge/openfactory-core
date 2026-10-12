"""A job that holds one of the deployment's slots is counted by every floor (#660).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640). One product of three projects on the
default single slot (`OPENFACTORY_MAX_CONCURRENT_JOBS=1`). A front on `reservas-web` ran, changed
nothing and parked "needs refinement". From then on:

  - **every other card, on every project, waited**: a hand-made card dragged to TO-DO started almost
    four hours later, behind that park and then a second one;
  - **`reservas-core`'s floor said "Armed — nothing is running — the next card in reservas-core's
    TO-DO will be picked up"** the whole time, because the ladder's rung 9 read only that project's
    jobs, while the poller counts every running job of the deployment and a park is a running job;
  - **the product role**, whose facts are those per-project verdicts, said "the queue should pick
    them up, but nothing is running — I cannot say why", and read the park's deadline as "the card
    wakes up by itself on 14/10" — an impediment's deadline SKIPS the card;
  - **the operator's `discard`** was refused with "it may have merged already, been closed, or never
    opened a PR", three guesses, none true, and not the verbs that answer a park.

THE RULE THIS FILE HOLDS: a floor never promises a card will be picked up while every slot of the
deployment is held — by this project's job, another project's, or another product's — and it says
the next card waits for a slot without naming the other job. What a live job costs the rest, and
what its deadline does, reach the role; a verb asked of a job at another gate names the verbs that
answer it. The slot holders, the slot counts and the scopes are combined, not hand-picked.
"""

from __future__ import annotations

import itertools
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from openfactory import actions, floor
from openfactory.floor import reading
from openfactory.product import model as product_model
from openfactory.runtime.temporal import workflow as wf

NOW = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
INTAKE = {"known": True, "on": True, "note": "", "every_s": 180, "fired_ago_s": 60,
          "next_in_s": 120, "num_actions": 100, "created_ago_s": 90000,
          "fired_at": "2026-10-11T23:59:00Z", "next_at": "2026-10-12T00:02:00Z", "watchers": {}}

#: Who is on the deployment: two projects of one product, and a project of another product.
PROJECTS = ("reservas-web", "reservas-core", "faturas")


def _park(project: str) -> dict:
    """A job parked for a person — a running workflow, holding its slot."""
    return {"project": project, "issue": "4", "status": "running", "state": "needs_refinement",
            "attention": True, "wedged": False, "title": "Filtrar por situação (API)",
            "action": {"kind": "impediment", "state": "needs_refinement", "note": "spec unclear",
                       "wakes_at": "2026-10-15T00:00:00+00:00", "at_deadline": "skip"}}


def _working(project: str) -> dict:
    return {"project": project, "issue": "9", "status": "running", "state": "running",
            "attention": False, "wedged": False, "title": "Exportar CSV", "action": None}


def _world(jobs: list[dict], slots: int | None) -> floor.FloorInputs:
    return floor.FloorInputs(
        jobs=jobs, intake=dict(INTAKE), connected=True, engine_address="engine:7233", now=NOW,
        projects=[{"name": n, "enabled": True, "box": {"state": "proven", "gate": ""}}
                  for n in PROJECTS],
        inbox=[{"project": j["project"], "issue": j["issue"], "kind": "impediment"}
               for j in jobs if j["attention"]],
        budget={"state": "ok"}, slots=slots)


#: (who holds a slot, what it is): this project's park, another project's park in the product,
#: another product's park, and another project's job at work.
HOLDERS = {
    "its own park": lambda: _park("reservas-core"),
    "another project's park": lambda: _park("reservas-web"),
    "another product's park": lambda: _park("faturas"),
    "another project's job at work": lambda: _working("reservas-web"),
}
CASES = list(itertools.product(sorted(HOLDERS), (1, 2)))


# ── 1. the floor ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("holder", "slots"), CASES, ids=[f"{h}, {n} slot(s)" for h, n in CASES])
def test_a_floor_is_Armed_only_while_a_slot_is_free(holder, slots):
    job = HOLDERS[holder]()
    got = floor.state(_world([job], slots), "reservas-core")
    free = slots > 1

    if job["project"] == "reservas-core":
        assert got.word == "Needs you", got.line          # its own park: the person is the blocker
    elif free:
        assert (got.word, got.cause) == ("Armed", "armed"), got.line
    else:
        assert got.word != "Armed", f"every slot is held and the floor says {got.line!r}"
        assert got.cause == "slots_held", got.line
        assert "the next card in reservas-core's TO-DO starts when one is free" in got.clause
        assert "(1 of 1)" in got.clause, got.clause


@pytest.mark.parametrize("holder", sorted(h for h in HOLDERS if "own" not in h))
def test_the_job_that_holds_the_slot_is_never_named_on_another_floor(holder):
    """It may be another product's: this scope is not where its people read."""
    job = HOLDERS[holder]()
    got = floor.state(_world([job], 1), "reservas-core")

    said = got.line + got.detail + str(got.also)
    assert job["project"] not in said and f"#{job['issue']}" not in said, said


def test_a_park_holding_the_slot_says_what_frees_it():
    got = floor.state(_world([_park("faturas")], 1), "reservas-core")

    assert "a job parked for a person's answer holds one" in got.clause, got.clause
    assert "when somebody answers it, or when its deadline sets it aside" in got.clause


def test_every_floor_of_the_deployment_counts_the_same_slots():
    """The census is the per-project verdicts, so it counts the waiting projects as waiting."""
    got = floor.state(_world([_park("reservas-web")], 1))

    per = got.per_project
    assert per["reservas-web"]["word"] == "Needs you"
    assert {per[n]["cause"] for n in ("reservas-core", "faturas")} == {"slots_held"}, per
    assert got.census["armed"] == 0 and got.census["clock"] == 2, got.census


def test_a_deployment_that_runs_no_job_at_once_says_no_card_will_be_picked_up():
    got = floor.state(_world([], 0), "reservas-core")

    assert (got.word, got.cause) == ("Stopped", "slots_held"), got.line
    assert "OPENFACTORY_MAX_CONCURRENT_JOBS=0" in got.clause


def test_a_caller_that_does_not_say_the_slots_is_judged_as_before():
    assert floor.state(_world([_park("reservas-web")], None), "reservas-core").word == "Armed"


async def test_the_floor_reads_the_slots_the_poller_counts_against(monkeypatch):
    monkeypatch.setenv("OPENFACTORY_MAX_CONCURRENT_JOBS", "3")

    async def _engine(client):
        return object(), True, "engine:7233", ""

    async def _jobs(_client):
        return [_park("reservas-web")]

    monkeypatch.setattr(reading, "_engine", _engine)
    monkeypatch.setattr(reading, "_jobs", _jobs)

    got = await reading.gather(want=("jobs",))

    assert got.slots == 3


# ── 2. the role is told what a live job costs, and what its deadline does ──────────────────────

def test_the_role_is_told_a_parked_job_holds_a_slot_and_the_cards_wait_behind_it(monkeypatch):
    monkeypatch.setenv("OPENFACTORY_MAX_CONCURRENT_JOBS", "1")

    said = "\n".join(product_model._render_job("reservas-web", _park("reservas-web"), live=True))

    assert "it holds one of this deployment's 1 job slot:" in said, said
    assert "no card on any project starts — the cards in TO-DO wait behind it" in said, said


def test_an_impediments_deadline_is_said_as_the_card_set_aside_not_a_wake_up():
    said = "\n".join(product_model._render_job("reservas-web", _park("reservas-web"), live=True))

    assert ("if nobody answers it by 2026-10-15T00:00:00+00:00, the platform sets the card aside "
            "then (`skip`) and frees its slot — it does not wake up and carry on by itself") in said


def test_a_rate_limit_park_still_resumes_by_itself():
    job = {**_park("reservas-web"), "action": {"kind": "rate_limit", "at_deadline": "resume",
                                               "wakes_at": "2026-10-12T00:30:00+00:00"}}
    said = "\n".join(product_model._render_job("reservas-web", job, live=True))

    assert "it resumes by itself at 2026-10-12T00:30:00+00:00" in said, said
    assert "sets the card aside" not in said


def test_a_finished_job_holds_nothing():
    job = {**_park("reservas-web"), "status": "closed"}
    said = "\n".join(product_model._render_job("reservas-web", job, live=True))

    assert "job slot" not in said, said


# ── 3. the park says what its deadline does ─────────────────────────────────────────────────────

@pytest.mark.parametrize(("kind", "timeout", "default", "at_deadline"), [
    ("impediment", timedelta(days=3), "skip", "skip"),
    ("rate_limit", timedelta(minutes=30), "resume", "resume"),
    ("impediment", timedelta(days=3650), "skip", None),   # a decision holds until answered
])
async def test_a_park_carries_what_its_deadline_does(monkeypatch, kind, timeout, default,
                                                      at_deadline):
    job = wf.JobWorkflow.__new__(wf.JobWorkflow)
    job._paused = job._action = job._choice = job._params = None
    seen: dict = {}

    async def _wait(_condition, timeout=None):
        seen.update(job._paused)
        raise TimeoutError

    monkeypatch.setattr(wf.workflow, "now", lambda: NOW)
    monkeypatch.setattr(wf.workflow, "wait_condition", _wait)
    monkeypatch.setattr(wf.workflow, "logger", logging.getLogger("test.the_park"))
    parked = SimpleNamespace(state=SimpleNamespace(value="needs_refinement"), note="spec unclear",
                             decision=None)

    act, _choice, answered = await job._wait_operator(kind, parked, timeout, default)

    assert seen["at_deadline"] == at_deadline, seen
    assert (act, answered) == (default, False)


# ── 4. a verb asked of a job at another gate names the verbs that answer it ────────────────────

class _ParkedJob:
    """A job parked for a person: `awaiting_action` answers, no gate does."""

    id = "openfactory-demo-7"

    async def query(self, name):
        return {"kind": "impediment", "note": "spec unclear"} if name == "awaiting_action" else None


class _Engine:
    def get_workflow_handle(self, *_a, **_k):
        return _ParkedJob()


@pytest.mark.parametrize("verb", ["merge", "adjust", "discard"])
async def test_a_merge_verb_asked_of_a_parked_job_names_resume_and_skip(monkeypatch, verb):
    from openfactory.actions import catalog
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.registry import ProjectRegistry

    demo = Project(name="demo", repo_path="/tmp/demo-repo",
                   tracker=ProviderRef(kind="github", repo="o/demo"))
    card = SimpleNamespace(get_ticket=lambda ref: SimpleNamespace(state="open", title="", raw=""),
                           set_state=lambda *a, **k: None, comment=lambda *a, **k: None)
    monkeypatch.setattr(ProjectRegistry, "get", lambda self, name: demo)
    monkeypatch.setattr(catalog, "_board_pair", lambda name: (demo, card, None, None))

    async def _connect(*_a, **_k):
        return _Engine()

    async def _not_at_the_gate(*_a, **_k):
        raise RuntimeError("this job is not waiting on a merge")

    monkeypatch.setattr("openfactory.runtime.temporal.view.connect", _connect)
    monkeypatch.setattr("openfactory.runtime.temporal.view.answer_merge_gate", _not_at_the_gate)
    params = {"instruction": "use the filter"} if verb == "adjust" else {}

    out = await actions.perform(verb, by=actions.SYSTEM, project="demo", issue="7", **params)

    assert out.code == actions.CONFLICT, out
    assert out.message == ("#7 is not waiting on a merge — it is waiting on a person's decision. "
                           "Answer it with `resume` or `skip`."), out.message
