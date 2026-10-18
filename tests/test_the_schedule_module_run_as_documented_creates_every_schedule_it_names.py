"""Run as documented, the schedule module creates every schedule its `main()` names.

`docs/configuration.md` §6 tells a person to (re)create the schedules with
`python -m openfactory.runtime.temporal.schedule --every-minutes 3`. On c0a50f3 that command
created the poller and then died with `NameError: name 'ensure_techlead_watch' is not defined`:
the `if __name__ == "__main__"` block sat at line 300 of `schedule.py`, and ten top-level
statements came after it (`_product_schedule` first, `ensure_techlead_watch` last). Under `-m` a
module runs top to bottom, so `main()` reached a function whose `def` had not run yet. The
tech-lead's rounds, the product sweep, the knowledge refresh and the card-question sweep were never
created by the command documented to create them. The worker never showed it: it imports the
whole module before it calls `ensure_all` (reported by hermes-felipe, issue #744).

Nothing ran the module as a script before this file, although `test_schedules_are_reachable.py`
counted `main` as reachable "by the module being runnable". The test runs it the way `-m` does and
reads which schedules reached the engine.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

MODULE = "openfactory.runtime.temporal.schedule"
ROOT = Path(__file__).resolve().parents[1]

ENABLED, DISABLED = "acme-on", "acme-off"


class _AlreadyThere:
    """The update branch of a schedule that exists: `handle.update(fn)` is all `main()` calls."""

    def __init__(self, sid: str, updated: list[str]) -> None:
        self._sid, self._updated = sid, updated

    async def update(self, _fn) -> None:
        self._updated.append(self._sid)


class _Engine:
    """A client that records the schedule ids it was asked to create, and nothing else."""

    def __init__(self) -> None:
        self.created: list[str] = []
        self.updated: list[str] = []

    async def create_schedule(self, sid: str, _schedule) -> None:
        self.created.append(sid)

    def get_schedule_handle(self, sid: str) -> _AlreadyThere:
        return _AlreadyThere(sid, self.updated)


@pytest.fixture
def engine(tmp_path, monkeypatch) -> _Engine:
    """One enabled project with the product module, one disabled project without it, a fake engine
    behind `connection.connect`, and no `.env` read from wherever the checkout sits."""
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.registry import ProjectRegistry

    registry = ProjectRegistry()
    registry.add(Project(name=ENABLED, repo_path=str(tmp_path), language="en",
                         tracker=ProviderRef(kind="local", repo=ENABLED, options={}),
                         product=ProductConfig(docs_repo="acme/docs")))
    registry.add(Project(name=DISABLED, repo_path=str(tmp_path), language="en",
                         tracker=ProviderRef(kind="local", repo=DISABLED, options={}),
                         enabled=False))

    fake = _Engine()

    async def _connect(*_args, **_kwargs) -> _Engine:
        return fake

    # The re-executed module runs `from ...connection import connect` at exec time, so it binds
    # this one. `find_dotenv` walks up from schedule.py, so a `.env` at the checkout's root would
    # otherwise reach `main()` on a developer's machine and nowhere else.
    monkeypatch.setattr("openfactory.runtime.temporal.connection.connect", _connect)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *_a, **_k: False)
    monkeypatch.setattr(sys, "argv", ["schedule", "--every-minutes", "3"])
    # With the module already imported, runpy warns that it was "found in sys.modules ... prior to
    # execution" (measured 2026-10-18). monkeypatch puts the entry back, so a test that imported
    # the module earlier in this process still holds the same object.
    monkeypatch.delitem(sys.modules, MODULE, raising=False)
    return fake


def test_running_the_module_as_documented_creates_the_poller_and_every_per_project_schedule(
        engine):
    """C1: `python -m openfactory.runtime.temporal.schedule` creates the poller and, for each
    enabled project, the tech-lead watch, the product sweep, the knowledge refresh and the
    card-question sweep. On c0a50f3 it raised `NameError` after the poller, the only id created."""
    try:
        ran = runpy.run_module(MODULE, run_name="__main__")
    except NameError as exc:
        pytest.fail(f"the module run as a script stopped with NameError ({exc}) after creating "
                    f"only {engine.created}")

    # The ids come from the constants the module that ran exports, not from literal strings.
    # Importing the module here instead would put it back in sys.modules before runpy executes it.
    expected = {
        ran["SCHEDULE_ID"],
        f"{ran['WATCH_SCHEDULE_PREFIX']}-{ENABLED}",
        f"{ran['PRODUCT_SCHEDULE_PREFIX']}-{ENABLED}",
        f"{ran['OKF_SCHEDULE_PREFIX']}-{ENABLED}",
        f"{ran['CARD_QUESTION_SCHEDULE_PREFIX']}-{ENABLED}",
    }
    assert set(engine.created) == expected, (
        f"missing {sorted(expected - set(engine.created))}, "
        f"unexpected {sorted(set(engine.created) - expected)}")
    assert not [sid for sid in engine.created if DISABLED in sid], (
        f"a disabled project without the product module got a schedule: {engine.created}")

