"""A guard that asks every file the same question walks each tree once (#1068, criterion 3).

WHAT HAPPENED. Two guards walked the whole package once per question. `_callers_of` in
`test_schedules_are_reachable` read, parsed and walked every module of `openfactory/` and `tests/`
once per `ensure_*` name (58 s of one test in CI). `_imported_modules` in
`test_the_core_addon_ledger` re-parsed and re-walked a core file every time
`test_the_public_cut_is_written_down` asked for it, once per vendor entry (46 s in CI, 2026-10-21).
Both walks are now memoised per tree, and the trees come from `tests.the_tree_read_once`, one
object per content.

Measured on 923d7d0f, before the memo, from this file (2026-10-22): the second `_callers_of(name)`
walked 1,309 whole modules again, every file of both trees but schedule.py (red), and the second
`_imported_modules(cli.py)` called `ast.walk` once more (red). `test_a_file_that_changed_is_walked_again` PASSES on that commit, because nothing is
memoised there and every answer is fresh: it guards the memo's KEY (a changed file must not be
answered from the old tree), not the memo's existence.

The guard modules are imported bare (`test_schedules_are_reachable`, not `tests.…`), as pytest
imports them in rootdir mode (there is no `tests/__init__.py`) and as
`test_the_public_cut_is_written_down` does. A patch on the bare module is a patch on the module the
guard runs in.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import test_schedules_are_reachable as schedules
import test_the_core_addon_ledger as ledger

from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parents[1]


def _counting(monkeypatch: pytest.MonkeyPatch, owner: object, name: str) -> list[ast.AST]:
    """Replace `owner.name` with a wrapper that records its first argument; returns the record."""
    real = getattr(owner, name)
    seen: list[ast.AST] = []

    def counted(node, *args, **kwargs):
        seen.append(node)
        return real(node, *args, **kwargs)

    monkeypatch.setattr(owner, name, counted)
    return seen


def test_the_schedule_guard_walks_no_file_twice_for_a_second_name(
        monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = sorted(schedules._ensure_functions())[:2]
    walks = _counting(monkeypatch, schedules, "_calls_in")
    schedules._callers_of(first)
    walks.clear()

    schedules._callers_of(second)

    whole_modules = [n for n in walks if isinstance(n, ast.Module)]
    assert not whole_modules, (
        f"asking for {second!r} after {first!r} walked {len(whole_modules)} whole modules again"
    )
    # What remains is schedule.py's own per-function check, one entry point at a time.
    functions = [n for n in parsed(schedules.SCHEDULE).body
                 if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef)]
    assert len(walks) <= len(functions), (
        f"{len(walks)} walks for a second name, more than schedule.py's {len(functions)} functions"
    )


def test_the_ledger_walks_no_file_twice_for_a_second_question(
        monkeypatch: pytest.MonkeyPatch) -> None:
    path, rel = ROOT / "openfactory/cli.py", "openfactory/cli.py"
    walks = _counting(monkeypatch, ast, "walk")
    answer = ledger._imported_modules(path, rel)
    walks.clear()

    again = ledger._imported_modules(path, rel)

    assert not walks, f"the second question about {rel} walked its tree again ({len(walks)} walks)"
    assert again == answer
    assert type(again) is set, f"the ledger handed out its {type(again).__name__}, not a fresh set"
    again.add("planted.by.a.caller")
    assert "planted.by.a.caller" not in ledger._imported_modules(path, rel), (
        "the ledger handed out the set it keeps: a caller's edit reached the next answer"
    )


def test_a_file_that_changed_is_walked_again(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each rewrite keeps the length of the text, so a memo keyed on the path or on the length
    serves the old answer and goes red here; only a key that follows the content stays green."""
    # `_callers_of` lists `openfactory/` and `tests/` relative to the working directory.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "openfactory").mkdir()
    (tmp_path / "tests").mkdir()
    caller = tmp_path / "openfactory" / "caller.py"

    caller.write_text("def f():\n    ensure_planted()\n", encoding="utf-8")
    assert schedules._callers_of("ensure_planted") == ["openfactory/caller.py"]
    caller.write_text("def f():\n    ensure_plantex()\n", encoding="utf-8")
    assert schedules._callers_of("ensure_planted") == [], "a stale tree answered the schedule guard"
    assert schedules._callers_of("ensure_plantex") == ["openfactory/caller.py"]

    module = tmp_path / "openfactory" / "m.py"
    module.write_text("import json\n", encoding="utf-8")
    assert ledger._imported_modules(module, "openfactory/m.py") == {"json"}
    module.write_text("import yaml\n", encoding="utf-8")
    assert ledger._imported_modules(module, "openfactory/m.py") == {"yaml"}, (
        "a stale tree answered the ledger"
    )
