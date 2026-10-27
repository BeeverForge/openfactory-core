"""No test and no mutation plan reads a release-note fragment (docs/RELEASING.md §5).

The final's commit removes every fragment it assembles, so a reader of one turns red on the
final's pull request and nowhere before it: 0.7.0's did (#1149, 5 failed across unit 1, 3 and 4).
This finds the reader on the pull request that adds it (review of #1151). Parsed, not grepped: a
docstring or a comment that NAMES a fragment is history and reads nothing, so only string values
the code evaluates count, and only those naming a fragment that is in the tree (the release-note
tests build their fragments in `tmp_path`, under names no real one carries). Right after a final
`changes/` is empty, so the first test checks nothing until the next fragment lands; the second
always applies.
"""

from __future__ import annotations

import ast
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAGMENTS = {p.relative_to(ROOT).as_posix() for p in (ROOT / "changes").glob("*.md")}


def _docstrings(tree: ast.AST) -> set[int]:
    owners = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return {id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node, owners) and node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)}


def _fragments_named(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstrings(tree)
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in skip and node.value.strip() in FRAGMENTS]


def test_no_test_or_plan_names_a_fragment_in_its_code():
    sources = (sorted((ROOT / "tests").rglob("*.py"))
               + sorted((ROOT / "tools" / "mutations").glob("*.py")))
    readers = {p.relative_to(ROOT).as_posix(): named for p in sources
               if (named := _fragments_named(p))}
    assert not readers, (f"these read a release-note fragment, which the final's commit removes: "
                         f"{readers}; read the document the text lives in for good")


def test_no_plan_cuts_a_fragment():
    cutting = {}
    for plan in sorted((ROOT / "tools" / "mutations").glob("*.py")):
        rows = runpy.run_path(str(plan)).get("MUTATIONS", [])
        files = [row[1] for row in rows if str(row[1]).startswith("changes/")]
        if files:
            cutting[plan.name] = files
    assert not cutting, f"these plans cut a release-note fragment: {cutting}"
