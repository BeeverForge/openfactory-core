"""A guard that reads the whole package gets its trees from one cache, keyed on what it read.

`tests/the_tree_read_once.py` says why: measured on 923d7d0f (2026-10-22), 232 inline
`ast.parse(<path>.read_text(...))` calls in 142 test files parsed the package and the suite's own
files, and the suite paid that parse hundreds of times a run for trees that had not changed. The
cache is held to four properties here: the same bytes are one tree wherever they live; different
bytes at the same path are a different tree, with nothing stale served, even when the two texts
have the same length; a file that does not parse is raised and not cached; and the one guard that
edits a tree edits a copy, because the tree is now shared by every guard in the worker.

That no test goes back to the inline parse is held by
`tests/test_no_guard_parses_a_source_file_on_its_own.py`, which parses the test files rather than
grepping them.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

from tests.test_the_product_role_lives_outside_slack import _code_without_prose
from tests.the_tree_read_once import cached, parsed

ROOT = Path(__file__).resolve().parents[1]


def test_the_same_bytes_are_one_tree_wherever_they_live(tmp_path: Path) -> None:
    a, b = tmp_path / "a.py", tmp_path / "sub" / "b.py"
    b.parent.mkdir()
    # Bytes no other test in this worker parses: the cache is per process, so `x = 1\n` alone was
    # already cached whenever the same-length test below ran first, and `cached()` did not move
    # (3 of 3 random-order runs of this file red on 2026-10-22, `assert 5 == (5 + 1)`).
    text = f"x = 1  # {uuid.uuid4().hex}\n"
    a.write_text(text)
    b.write_text(text)
    before = cached()
    tree = parsed(a)
    assert parsed(a) is tree, "the second read of one file parsed again"
    assert parsed(b) is tree, "a copy of the file parsed again"
    assert cached() == before + 1
    assert isinstance(tree, ast.Module) and ast.unparse(tree) == "x = 1"


def test_different_bytes_at_the_same_path_are_a_different_tree(tmp_path: Path) -> None:
    f = tmp_path / "m.py"
    f.write_text("def planted(): ...\n")
    first = parsed(f)
    f.write_text("def planted(): ...\ndef writer(): ...\n")   # rewritten within the same tick
    second = parsed(f)
    assert second is not first
    assert [n.name for n in second.body] == ["planted", "writer"], "a stale tree was served"
    f.write_text("def planted(): ...\n")
    assert parsed(f) is first, "the earlier content came back and was parsed again"


def test_different_bytes_OF_THE_SAME_LENGTH_at_the_same_path_are_a_different_tree(
        tmp_path: Path) -> None:
    """The test above changes the length of the text as well as its bytes, so a cache keyed on
    `len(text)` would pass it. Here only one byte changes, and the length stays the same."""
    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    first = parsed(f)
    f.write_text("x = 2\n")
    second = parsed(f)
    assert second is not first, "the same length was taken for the same content"
    value = second.body[0].value
    assert isinstance(value, ast.Constant) and value.value == 2, "a stale tree was served"


def test_a_file_that_does_not_parse_is_raised_and_not_cached(tmp_path: Path) -> None:
    f = tmp_path / "broken.py"
    f.write_text("def (:\n")
    before = cached()
    with pytest.raises(SyntaxError):
        parsed(f)
    assert cached() == before
    with pytest.raises(FileNotFoundError):
        parsed(tmp_path / "gone.py")


def test_the_one_guard_that_edits_a_tree_edits_a_copy() -> None:
    """`_code_without_prose` removes docstrings from the function it is given. It is the one
    function under `tests/` that edits a tree (checked on 923d7d0f), and it deep-copies first.
    With a shared cache, an edit in place would remove the docstrings from every later reader of
    `catalog.py` in that worker, in some test orders only."""
    path = ROOT / "openfactory/actions/catalog.py"
    tree = parsed(path)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(n))
    docstring = ast.get_docstring(fn)
    before = ast.dump(tree)
    stripped = _code_without_prose(fn)
    assert docstring not in stripped, "the stripper did not strip; this test proves nothing"
    assert parsed(path) is tree
    assert ast.get_docstring(fn) == docstring, "the docstring is gone from the shared tree"
    # Compared into a bool: on failure pytest would otherwise difflib the two dumps of the whole
    # module, which ran for over two minutes on 2026-10-22 with the deep copy cut out.
    unchanged = ast.dump(parsed(path)) == before
    assert unchanged, "the shared tree was edited in place"
