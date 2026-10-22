"""#1068, proven by breaking it — the guards that read the whole package parse each content once.

THE CLAIMS:

  1. **`parsed(path)` serves one tree per content.** The same bytes at two paths are one object;
     different bytes at one path are a new tree, even at the same length; a file that does not
     parse is raised and leaves nothing behind.
  2. **Nobody edits the shared tree.** The one guard that strips docstrings from a function
     (`_code_without_prose`) deep-copies it first; without the copy, every later reader of
     `openfactory/actions/catalog.py` would see a tree with no docstrings, in some orders only.
  3. **No test parses a source file inline any more, and the guard that says so can see.** It
     parses each test file (a regex missed the quoted-path and multi-line shapes: 40 sites in 29
     files on the prototype, 2026-10-22), it refuses a bare `the_tree_read_once` import (a second
     module, a second empty cache), and it fails when it reads fewer than 800 files.
  4. **The two quadratic guards walk each tree once per process.** On 923d7d0f the schedule guard
     re-walked 1309 modules for a second `ensure_*` name, and the ledger re-walked `cli.py` for a
     second question; the memos are keyed by the tree, and the ledger hands each caller a fresh set.

Each row names its guard: the cache's (`TEST`), the adoption guard, or the walk counter.
"""

TEST = "tests/test_the_tree_is_parsed_once_per_content.py"

HELPER = "tests/the_tree_read_once.py"
STRIPPER = "tests/test_the_product_role_lives_outside_slack.py"
SCHEDULES = "tests/test_schedules_are_reachable.py"
LEDGER = "tests/test_the_core_addon_ledger.py"

ADOPTION = "tests/test_no_guard_parses_a_source_file_on_its_own.py"
WALKS = "tests/test_a_guard_that_asks_every_file_walks_each_tree_once.py"

KEY = "    key = hashlib.blake2b(text.encode(encoding), digest_size=16).digest()\n"

MUTATIONS = [
    # ── 1. one tree per content ────────────────────────────────────────────────────────────────
    ("the cache is keyed on the path, so a rewritten file is served stale",
     HELPER, KEY, "    key = os.fspath(path).encode()\n"),

    ("the cache is keyed on the length of the text, so a same-length edit is served stale",
     HELPER, KEY, '    key = len(text).to_bytes(8, "big")\n'),

    ("nothing is cached: every call parses again",
     HELPER, "    tree = _trees.get(key)\n", "    tree = None\n"),

    ("a file that does not parse leaves an entry behind",
     HELPER,
     "        tree = ast.parse(text, filename=os.fspath(path))\n",
     "        _trees[key] = None\n        tree = ast.parse(text, filename=os.fspath(path))\n"),

    # ── 2. nobody edits the shared tree ────────────────────────────────────────────────────────
    ("the docstring stripper edits the shared tree in place",
     STRIPPER, "    cleaned = copy.deepcopy(fn)\n", "    cleaned = fn\n"),

    # ── 3. no inline parse, and a guard that can see ───────────────────────────────────────────
    ("a guard goes back to the quoted-path inline parse",
     SCHEDULES, "",
     '\n\ndef _planted():\n    return ast.parse((Path("openfactory") / "cli.py").read_text())\n',
     ADOPTION),

    ("a guard goes back to the inline parse, wrapped across lines",
     SCHEDULES, "",
     "\n\ndef _planted_wrapped(p):\n"
     '    return ast.parse(\n        p.read_text(encoding="utf-8"))\n',
     ADOPTION),

    ("a guard imports the helper bare and reaches a second, empty cache",
     LEDGER, "",
     "\nfrom the_tree_read_once import parsed as _second  # noqa: E402,F401\n",
     ADOPTION),

    ("the scan reads nothing, and an empty suite would read as a clean one",
     ADOPTION,
     '    scanned = _sources("*.py")\n',
     '    scanned = _sources("no_file_is_named_like_this_*.py")\n',
     ADOPTION),

    # ── 4. each tree walked once ───────────────────────────────────────────────────────────────
    ("the schedule walk is not memoised: a second name walks every module again",
     SCHEDULES,
     "@functools.cache\ndef _calls_in_the_module(",
     "def _calls_in_the_module(",
     WALKS),

    ("the ledger walk is not memoised: a second question walks the file again",
     LEDGER,
     "@functools.cache\ndef _imports_resolved_against(",
     "def _imports_resolved_against(",
     WALKS),

    ("the ledger hands out its cached set, so one caller's edit reaches the next",
     LEDGER,
     "    return set(_imports_resolved_against(parsed(path), package))\n",
     "    return _imports_resolved_against(parsed(path), package)\n",
     WALKS),
]
