"""No test parses a source file on its own; every guard asks the one cache (#1068, criterion 2).

WHAT HAPPENED. The guards that read the package wrote `ast.parse(<path>.read_text())` inline, so
each xdist worker parsed the same unchanged files again for every guard that asked: parsing
`openfactory/` costs 1.24 s and `tests/` 3.94 s, reading them 0.04 s (measured 2026-10-22).
`tests/the_tree_read_once.parsed(path)` now serves one tree per content, and this file holds that
no test goes back to the inline shape.

WHY IT PARSES INSTEAD OF GREPPING. The prototype's guard was a one-line regex,
`ast\\.parse\\(\\s*[\\w.()/ ]+\\.read_text\\(`. It had no `"` in its class and read one line at a time,
so it passed over `ast.parse((ROOT / "openfactory/cli.py").read_text())` and over
`ast.parse(\\n    path.read_text(...))`: 43 lines in 29 files plus the wrapped one, all green on
the prototype's commit 3c7d126d. Parsing each test file finds the call wherever its argument is
written and however it is wrapped, and it does not see a comment or a docstring that quotes the old
shape (CONTRIBUTING, "A guard reads the THING").

This module does not import `tests.the_tree_read_once`: it must collect on a tree without the
helper, so that it is red there for the inline sites it lists, not for an ImportError.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

# The helper's module name. Imported bare, it is a second module object with a second, empty cache.
HELPER = "the_tree_read_once"

# Fewer files than this means the scan could not see the suite, not that the suite is clean
# (docs/engineering-lessons.md §2). On 923d7d0f, `tests/*.py` held 867 files.
FLOOR = 800


def inline_parses(source: str, filename: str = "<planted>") -> list[int]:
    """The line of every `ast.parse(<x>.read_text(...))` or `ast.parse(<x>.read_bytes(...))` in
    `source`, whatever `<x>` is and however the call is wrapped across lines."""
    found = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == "parse"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "ast"):
            continue
        given = node.args[:1] or [kw.value for kw in node.keywords if kw.arg == "source"]
        if (given and isinstance(given[0], ast.Call)
                and isinstance(given[0].func, ast.Attribute)
                and given[0].func.attr in ("read_text", "read_bytes")):
            found.append(node.lineno)
    return sorted(found)


def bare_helper_imports(source: str, filename: str = "<planted>") -> list[int]:
    """The line of every `import the_tree_read_once` or `from the_tree_read_once import ...`."""
    found = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.Import):
            if any(a.name == HELPER or a.name.startswith(HELPER + ".") for a in node.names):
                found.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            if node.module == HELPER or node.module.startswith(HELPER + "."):
                found.append(node.lineno)
    return found


def _sources(pattern: str) -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8") for p in sorted(TESTS.glob(pattern))}


def test_no_test_parses_a_source_file_inline():
    # This file reads each source into a name first and parses the name, so it holds itself to
    # its own rule and needs no exclusion: it cannot ask the cache it guards (see the docstring).
    scanned = _sources("*.py")
    assert len(scanned) > FLOOR, (
        f"the scan read {len(scanned)} files under {TESTS}; it could not see the suite"
    )
    assert TESTS / "test_schedules_are_reachable.py" in scanned, (
        "the scan did not read tests/test_schedules_are_reachable.py, a guard that read both trees"
    )

    offenders = [f"{path.relative_to(ROOT)}:{line}"
                 for path, text in scanned.items()
                 for line in inline_parses(text, filename=str(path))]
    files = {site.rsplit(":", 1)[0] for site in offenders}
    assert not offenders, (
        f"{len(offenders)} inline parses of a source file in {len(files)} files; "
        "use `parsed(path)` from tests.the_tree_read_once, which parses each content once per "
        "process:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_finds_every_shape_the_rewrite_replaced():
    replaced = [
        'ast.parse(path.read_text(encoding="utf-8"))',
        'ast.parse((ROOT / "openfactory/cli.py").read_text())',
        'ast.parse(\n    path.read_text(encoding="utf-8"))',
        'ast.parse(add_ons.source("x.py").read_text())',
        "ast.parse(p.read_text(), filename=str(p))",
    ]
    for shape in replaced:
        assert inline_parses(f"tree = {shape}\n") == [1], f"the guard does not see: {shape!r}"

    kept = [
        "tree = ast.parse(source)\n",
        "tree = parsed(path)\n",
        "# tree = ast.parse(path.read_text())\nx = 1\n",
        'def f():\n    """Was `ast.parse(path.read_text())`."""\n    return 1\n',
    ]
    for shape in kept:
        assert inline_parses(shape) == [], f"the guard flags code that does not parse a file: {shape!r}"


def test_every_guard_reaches_the_ONE_cache():
    """`tests/` is on `sys.path` in rootdir mode (there is no `tests/__init__.py`), so
    `import the_tree_read_once` would load a second module with its own empty cache, and every
    guard behind it would parse again."""
    scanned = _sources("**/*.py")
    assert len(scanned) > FLOOR, f"the scan read {len(scanned)} files under {TESTS}"
    assert bare_helper_imports(f"from {HELPER} import parsed\n") == [1]
    assert bare_helper_imports(f"import {HELPER}\n") == [1]
    assert bare_helper_imports(f"from tests.{HELPER} import parsed\n") == []

    offenders = [f"{path.relative_to(ROOT)}:{line}"
                 for path, text in scanned.items()
                 for line in bare_helper_imports(text, filename=str(path))]
    assert not offenders, (
        f"import it as `tests.{HELPER}`, never bare:\n  " + "\n  ".join(offenders)
    )
