"""A scanner parses only what its text can match, and its text filter can never hide a match (#1069).

WHAT HAPPENED. Three guards scan a whole tree at IMPORT, so every xdist worker paid for them while
collecting: `test_the_suite_cannot_reach_a_live_engine._marked_files` parsed every test module,
`test_a_stranger_can_add_an_adapter.registries` and `test_temporal_call_arity._call_sites` every
module of the package. Each now reads the text first and hands `parsed` only the files whose text
can satisfy its tree test. `test_a_product_can_start_before_its_code._context_only_rows` walked a
method's tree again for every method that reached it, and `test_ci_runs_what_we_run` collected the
whole suite four times; the walks are memoised and the collections run once per distinct
invocation.

THE CONTRACT IS NECESSITY. A filter that is cheaper but not implied by the tree test turns a guard
into one that silently checks less: `getattr(pytest.mark, "owns_" "its_engine")`, a line break
between the dot and `signal`, a refusal spelled `"kno" "wn:"` and an NFKC-equivalent identifier all
satisfy a tree test while missing the obvious word. So each filter is the words the tree test
itself requires, with an NFKC fallback (`could_say`), and every planted shape here is asked of both:
the scan finds it, and wherever the tree test holds, the filter held too.

The guard modules are imported bare, as pytest imports them in rootdir mode and as
`test_a_guard_that_asks_every_file_walks_each_tree_once` does.
"""

from __future__ import annotations

import ast
import inspect
import re
import subprocess
from pathlib import Path

import pytest
import test_a_product_can_start_before_its_code as product
import test_a_stranger_can_add_an_adapter as adapter
import test_ci_runs_what_we_run as ci
import test_temporal_call_arity as arity
import test_the_suite_cannot_reach_a_live_engine as engine

from tests import the_tree_read_once
from tests.the_tree_read_once import could_say, parsed


def _recording(monkeypatch: pytest.MonkeyPatch, owner: object) -> list[Path]:
    """Replace `owner.parsed` with a wrapper that records every path it is handed."""
    seen: list[Path] = []

    def recorded(path):
        seen.append(Path(path))
        return parsed(path)

    monkeypatch.setattr(owner, "parsed", recorded)
    return seen


def _plant(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


# ── the helper ──────────────────────────────────────────────────────────────────────────────────

def test_could_say_falls_back_to_nfkc_and_only_for_text_that_needs_it(
        monkeypatch: pytest.MonkeyPatch) -> None:
    assert could_say("pytestmark = 1", "pytestmark")
    assert could_say("ｐytestmark = 1", "pytestmark"), "a fullwidth identifier was missed"
    assert could_say("h.ｓignal()", re.compile(r"\.signal\b"))
    assert not could_say("café = 1", "pytestmark")

    real = the_tree_read_once.unicodedata.normalize
    normalised: list[str] = []

    def recorded(form, text):
        if form == "NFKC":
            normalised.append(text)
        return real(form, text)

    monkeypatch.setattr(the_tree_read_once.unicodedata, "normalize", recorded)
    assert not could_say("nothing to see", "pytestmark")
    assert not normalised, "ASCII text was normalised"


# ── the live-engine marker ──────────────────────────────────────────────────────────────────────

_MARKED = {
    "test_plain.py": "import pytest\npytestmark = pytest.mark.owns_its_engine\n",
    "test_concatenated.py": (
        'import pytest\npytestmark = getattr(pytest.mark, "owns_" "its_engine")\n'),
    "test_fullwidth.py": "import pytest\nｐytestmark = pytest.mark.owns_its_engine\n",
    "test_continued.py": "import pytest\npytestmark \\\n    = pytest.mark.owns_its_engine\n",
    "test_chained.py": "import pytest\nother = pytestmark = [pytest.mark.owns_its_engine]\n",
}
_UNMARKED = {
    "test_said_in_a_comment.py": "# pytestmark = pytest.mark.owns_its_engine\nx = 1\n",
    "test_other_mark.py": "import pytest\npytestmark = pytest.mark.slow\n",
}
_SILENT = {"test_silent.py": "import pytest\nmark = pytest.mark.owns_its_engine\n"}


def test_the_marker_filter_is_necessary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _plant(tmp_path / "tests", {**_MARKED, **_UNMARKED, **_SILENT})
    seen = _recording(monkeypatch, engine)

    found = {p.name for p in engine._marked_files(tmp_path)}

    assert found == set(_MARKED), found
    assert not {p.name for p in seen} & set(_SILENT), "a file that cannot say it was parsed"
    for name in [*_MARKED, *_UNMARKED, *_SILENT]:
        path = tmp_path / "tests" / name
        if engine._marks_itself(parsed(path)):
            assert engine._could_mark(path.read_text(encoding="utf-8")), (
                f"{name} lifts the barrier and the text filter would have skipped it")


# ── the registries ──────────────────────────────────────────────────────────────────────────────

_TABLE = 'WIDGETS: dict = {"acme": lambda **kw: None}\n'
_REGISTRIES = {
    "continued_def.py": _TABLE + "def\\\n build_widget(kind):\n    return WIDGETS[kind]\n",
    "fullwidth_def.py": _TABLE + "def ｂuild_widget(kind):\n    return WIDGETS[kind]\n",
    "asks_across_lines.py": (
        "from openfactory import plugins\n" + _TABLE
        + "def door(kind):\n    return (plugins\n            .builder('across', kind))\n"),
    "asks_in_fullwidth.py": (
        "from openfactory import plugins\n" + _TABLE
        + "def door(kind):\n    return plugins.ｂuilder('fullwidth', kind)\n"),
    "refuses.py": (
        _TABLE + "def door(kind):\n"
        '    raise ValueError(f"unknown widget {kind!r} — known: {sorted(WIDGETS)}")\n'),
    "split_refusal_with_a_door.py": (
        _TABLE + "def build_widget(kind):\n"
        '    raise ValueError(f"unknown widget {kind!r} — kno" "wn: ...")\n'),
}
_NOT_REGISTRIES = {
    "split_refusal.py": (
        _TABLE + "def door(kind):\n"
        '    raise ValueError(f"unknown widget {kind!r} — kno" "wn: ...")\n'),
    "escaped_refusal.py": (
        _TABLE + "def door(kind):\n"
        '    raise ValueError(f"unknown widget {kind!r} — \\x6bnown: ...")\n'),
}
_WORDLESS = {"table_only.py": _TABLE + "def door(kind):\n    return WIDGETS[kind]\n"}


def test_the_registry_filter_is_necessary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _plant(tmp_path / "openfactory", {**_REGISTRIES, **_NOT_REGISTRIES, **_WORDLESS})
    seen = _recording(monkeypatch, adapter)

    found = adapter.registries(tmp_path)

    assert found == {
        "openfactory/continued_def.py": set(),
        "openfactory/fullwidth_def.py": set(),
        "openfactory/asks_across_lines.py": {"across"},
        "openfactory/asks_in_fullwidth.py": {"fullwidth"},
        "openfactory/refuses.py": set(),
        "openfactory/split_refusal_with_a_door.py": set(),
    }, found
    assert not {p.name for p in seen} & set(_WORDLESS), "a module that cannot say it was parsed"
    for name in [*_REGISTRIES, *_NOT_REGISTRIES, *_WORDLESS]:
        path = tmp_path / "openfactory" / name
        text = path.read_text(encoding="utf-8")
        if adapter._is_a_registry(parsed(path), text):
            assert adapter._could_be_a_registry(text), (
                f"{name} is a registry and the text filter would have skipped it")


@pytest.mark.parametrize("name", sorted(_NOT_REGISTRIES))
def test_a_refusal_the_source_never_spells_is_no_refusal(name: str, tmp_path: Path) -> None:
    path = tmp_path / name
    path.write_text(_NOT_REGISTRIES[name], encoding="utf-8")
    text = path.read_text(encoding="utf-8")

    assert not adapter._refuses_a_kind(parsed(path), text)


# ── the Temporal call sites ─────────────────────────────────────────────────────────────────────

_CALLS = {
    "plain.py": 'h.signal("a")\n',
    "spaced.py": 'h. signal("a")\n',
    "continued.py": 'h.\\\n    signal("a")\n',
    "commented.py": 'x = (h.  # c\n     signal)("a")\n',
    "fullwidth.py": 'h.ｓignal("a")\n',
}
_UNCALLED = {"other.py": 'h.other("a")\nsignal = 1\n'}


def test_the_call_site_filter_is_necessary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "openfactory"
    _plant(root, {**_CALLS, **_UNCALLED})
    seen = _recording(monkeypatch, arity)

    sites = list(arity._call_sites(root))

    assert sorted(Path(s[0]).name for s in sites) == sorted(_CALLS), sites
    assert all(s[2] == "signal" for s in sites), sites
    assert not {p.name for p in seen} & set(_UNCALLED), "a module that cannot call was parsed"
    for name in [*_CALLS, *_UNCALLED]:
        path = root / name
        if list(arity._sites_in(parsed(path), path)):
            assert arity._could_call(path.read_text(encoding="utf-8")), (
                f"{name} calls a checked method and the text filter would have skipped it")


def test_the_call_site_filter_follows_the_checked_names(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "openfactory"
    _plant(root, {"planted.py": 'h.planted_call("a")\n'})
    monkeypatch.setitem(arity._CHECKED, "planted_call", lambda self, a: None)

    assert [s[2] for s in arity._call_sites(root)] == ["planted_call"]


# ── the product rows ────────────────────────────────────────────────────────────────────────────

def test_the_context_only_rows_walk_each_method_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from openfactory import actions
    from openfactory.product.module import ProductModule

    methods = [f for f in vars(ProductModule).values() if inspect.isfunction(f)]
    walks: list[ast.AST] = []
    real = ast.walk

    def counted(node):
        walks.append(node)
        return real(node)

    monkeypatch.setattr(ast, "walk", counted)

    rows = product._context_only_rows()

    assert rows == product.CONTEXT_ONLY
    bound = 3 * len(methods) + len(actions.names())
    assert len(walks) <= bound, f"{len(walks)} walks, more than {bound}: a method walked twice"


# ── one collection per distinct invocation ──────────────────────────────────────────────────────

def test_one_collection_per_distinct_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = ci._ENV
    runs: list[tuple] = []

    def fake(argv, **kwargs):
        runs.append((tuple(argv), kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="1 test collected", stderr="")

    monkeypatch.setattr(ci, "_RUNS", {})
    monkeypatch.setattr(ci.subprocess, "run", fake)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "planted after import")
    monkeypatch.setenv("HOME", "/planted/after/import")

    argv = ("pytest", "-q", "--collect-only")
    first = ci._collected(argv, ci._ENV)
    again = ci._collected(argv, ci._ENV)
    assert again is first
    assert len(runs) == 1, runs
    assert runs[0][1]["env"] == captured
    assert runs[0][1]["env"].get("PYTEST_CURRENT_TEST") != "planted after import"
    assert runs[0][1]["cwd"] == ci.ROOT and runs[0][1]["timeout"] == 300

    ci._collected(argv, {**ci._ENV, "X": "1"})
    assert len(runs) == 2, "a changed environment was answered from another run"
    ci._collected(("python", "-m", "pytest", "-q", "--collect-only"), ci._ENV)
    assert len(runs) == 3, "a different invocation was answered from another run"
