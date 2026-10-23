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
counted `main` as reachable "by the module being runnable". The first test runs it the way `-m`
does and reads which schedules reached the engine; the second parses every module in the package
and holds each `__main__` block as its module's last statement.
"""

from __future__ import annotations

import ast
import runpy
import sys
from pathlib import Path

import pytest

from tests.the_tree_read_once import parsed

MODULE = "openfactory.runtime.temporal.schedule"
ROOT = Path(__file__).resolve().parents[1]

ENABLED, DISABLED = "acme-on", "acme-off"


class _Engine:
    """A client on which no schedule exists yet: it records the ids it was asked to create. The
    test of a second run replaces both methods, so that every schedule already exists."""

    def __init__(self) -> None:
        self.created: list[str] = []

    async def create_schedule(self, sid: str, _schedule) -> None:
        self.created.append(sid)


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


def test_running_the_module_again_updates_every_schedule_it_created_at_the_interval_asked(
        engine, monkeypatch):
    """C1, run a second time: when every schedule already exists, the same command updates each
    one, the poller to the `--every-minutes` it was given, and creates none (the module docstring's
    "create/refresh"). Until review round 1 of #744 no test reached this branch: replacing the
    poller's `handle.update(...)` with `pass`, or hard-coding `_schedule(5, ...)`, left the suite
    green (measured 2026-10-18). Until review round 2 it asked for 3, the parser's default, so a
    `main()` that ignored the flag and built `_schedule(3, ...)` stayed green too."""
    from datetime import timedelta

    from temporalio.client import ScheduleAlreadyRunningError

    seen: dict[str, object] = {}

    async def _exists(_sid, _schedule):
        raise ScheduleAlreadyRunningError()

    class _Handle:
        def __init__(self, sid):
            self._sid = sid

        async def update(self, fn):
            seen[self._sid] = fn(None).schedule

    engine.create_schedule = _exists
    engine.get_schedule_handle = _Handle
    # Not the parser's default of 3: a main() that ignores the flag must not pass by coincidence.
    monkeypatch.setattr(sys, "argv", ["schedule", "--every-minutes", "7"])
    ran = runpy.run_module(MODULE, run_name="__main__")

    expected = {
        ran["SCHEDULE_ID"],
        f"{ran['WATCH_SCHEDULE_PREFIX']}-{ENABLED}",
        f"{ran['PRODUCT_SCHEDULE_PREFIX']}-{ENABLED}",
        f"{ran['OKF_SCHEDULE_PREFIX']}-{ENABLED}",
        f"{ran['CARD_QUESTION_SCHEDULE_PREFIX']}-{ENABLED}",
    }
    assert set(seen) == expected, sorted(set(seen) ^ expected)
    assert seen[ran["SCHEDULE_ID"]].spec.intervals[0].every == timedelta(minutes=7)


def _is_main_guard(node: ast.stmt) -> bool:
    """`if __name__ == "__main__":`, read from the parsed test, in either operand order, alone or
    as one operand of an `and` (`host.py` gates its reaper with
    `if __name__ == "__main__" and len(sys.argv) >= 4 and ...`; with the bare comparison only,
    a statement after that block stayed green)."""
    if not isinstance(node, ast.If):
        return False
    if isinstance(node.test, ast.BoolOp) and isinstance(node.test.op, ast.And):
        return any(_is_main_test(operand) for operand in node.test.values)
    return _is_main_test(node.test)


def _is_main_test(test: ast.expr) -> bool:
    """`__name__ == "__main__"`, in either operand order."""
    if not isinstance(test, ast.Compare):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    sides = [test.left, *test.comparators]
    return (any(isinstance(s, ast.Name) and s.id == "__name__" for s in sides)
            and any(isinstance(s, ast.Constant) and s.value == "__main__" for s in sides))


def _defined_by(node: ast.stmt) -> str:
    """The name a top-level statement binds, for the failure message; else its kind."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return node.name
    if isinstance(node, ast.Assign | ast.AnnAssign):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return ", ".join(ast.unparse(t) for t in targets)
    return type(node).__name__


def _sources() -> list[Path]:
    files = sorted((ROOT / "openfactory").rglob("*.py"))
    addons = ROOT / "addons"
    if addons.is_dir():
        files += sorted(addons.glob("*/**/*.py"))
    return files


def test_the_main_block_is_the_last_statement_of_every_module_that_has_one():
    """C2: a `__main__` block is its module's last top-level statement, so `python -m` runs it
    after every `def` it may call. On c0a50f3 `schedule.py`'s block was at line 300 with ten
    statements after it, and the documented command died with `NameError`."""
    found, late = 0, []
    for path in _sources():
        tree = parsed(path)
        for index, node in enumerate(tree.body):
            if not _is_main_guard(node):
                continue
            found += 1
            after = tree.body[index + 1:]
            if after:
                late.append(f"{path.relative_to(ROOT)}: line {node.lineno}, followed by "
                            + ", ".join(_defined_by(n) for n in after))
    assert found, "no `if __name__ == \"__main__\"` block found: the walk read nothing"
    assert not late, "a __main__ block runs before the rest of its module is defined:\n" + \
        "\n".join(late)
