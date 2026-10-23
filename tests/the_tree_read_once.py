"""The source tree, parsed ONCE per content — for the guards that read the whole package.

MEASURED BEFORE IT WAS WRITTEN (2026-10-22, one process, no neighbours): `ast.parse` over the 399
files of `openfactory/` takes 1.24 s and over the 908 files of `tests/` 3.94 s; READING all 1,307
files takes 0.04 s. On 923d7d0f, 232 calls in 142 files under `tests/` parsed a source file
inline (`ast.parse(<path>.read_text())`, counted by parsing every test file, not by a grep:
`test_no_guard_parses_a_source_file_on_its_own`), most of them once per test function and two of
them once per item they check (`test_schedules_are_reachable` re-parsed both trees eight times,
`test_the_public_cut_is_written_down` the package once per vendor entry), so a suite run paid the
parse hundreds of times for a tree that did not change. CI's slowest-15 tables were that family at
9 to 58 s a test. One home for the tree, then, for the reason `conftest.code_only` is one home:
the hand-written copies all paid the same cost the same way.

KEYED ON THE CONTENT, NOT THE PATH OR ITS MTIME. The read is free, so every call re-reads the file
and hashes the text; a cached tree is served only for the exact bytes read this time. That makes
the cache stale-proof against a test that plants a writer in the package and removes it (the same
path, different bytes, a different tree), and it makes a tree COPIED under `tmp_path` — which a
dozen guards do before taking a module out of it — a hit rather than a second parse. It also
bounds the cache by distinct contents rather than by distinct paths, so a worker that parses
twenty copies of the package holds one.

THE TREE IS SHARED, SO NOBODY MUTATES IT. `ast.walk`, `ast.unparse`, `ast.get_docstring` and the
visitors read; the one guard that strips docstrings in place deep-copies first
(`test_the_product_role_lives_outside_slack._code_without_prose`). A caller that wants to edit a
tree copies it, as that one does.

READ AS UTF-8, WHATEVER THE LOCALE. `parsed` passes `encoding="utf-8"` where most inline sites
called a bare `read_text()`, which uses the locale's encoding. On a UTF-8 locale (pt_BR.UTF-8 where it
was measured, and CI) the text is the same; on a non-UTF-8 locale the old read could mis-decode a
source file Python itself reads as UTF-8 (PEP 3120), so this is the stricter and the right read.
No inline site on 923d7d0f read with another encoding. The encoding is fixed, not a parameter: the
key is a digest of the encoded text, so two codecs could give two texts one key, and no caller
asked for another (0 of 250 calls passed one, 2026-10-22). NO TEST HOLDS "WHATEVER THE LOCALE":
under `LC_ALL=C` Python 3.12 turns on its UTF-8 mode (PEP 538/540; `sys.flags.utf8_mode` is 1), so
a bare `read_text()` reads UTF-8 there too, and a cut that drops `encoding="utf-8"` passed this
helper's three test files under pt_BR.UTF-8 and under `LC_ALL=C` alike (13 passed, 2026-10-22).

WHAT IT COSTS: the package's trees are ~260 MB of Python objects in the worker that first asked;
the suite's own trees another ~450 MB in a worker that runs one of the two guards that read
`tests/` too. Measured 2026-10-22 against the sizes above; a worker already holds 300–500 MB.

AND THE COLLECTOR NEVER WALKS THEM. Every AST node is tracked by the cyclic GC, so a worker holding
both trees (~3.9 M objects) paid 1.1 s for every full collection, measured 2026-10-22 on an idle
box (1.115 s for 3,919,209 objects); the touched files' run on 5a3cccd8 paused over 1.0 s 67 times
against main's 1, and one pause outlasted the engine probe's 1.0 s and read as
`EngineNotListening`. With the freeze, 0 pauses over 0.5 s in two runs (main: 11 and 14). `parsed` calls `gc.freeze()` after each
insert, which moves every object alive at that moment into the permanent generation. The price:
cyclic garbage alive at the instant of a freeze is never collected (+24 MB peak RSS in one
process over the 142 touched files: 1,533,600 KB without the freeze, 1,558,312 KB with it).

READ THE TEXT BEFORE ASKING FOR THE TREE (#1069). A guard that scans a tree at import runs in every
xdist worker's collection, so it asks `could_say(text, pattern)` first and parses only a file whose
text can satisfy its tree test. The pattern must be NECESSARY for that test — the words the tree
itself requires — never merely likely. Python NFKC-normalises identifiers (`pytestmark` spelled
with a fullwidth `p` names `pytestmark`), so text that is not ASCII is searched again in NFKC.
"""

from __future__ import annotations

import ast
import gc
import hashlib
import os
import re
import unicodedata
from pathlib import Path

_trees: dict[bytes, ast.Module] = {}


def parsed(path: str | os.PathLike[str]) -> ast.Module:
    """`ast.parse(path.read_text())`, served from the cache when these bytes were parsed before.

    Raises what `read_text` raises — a file listed by a walk and gone by the read is the caller's
    case to tolerate, exactly as it was with the inline parse. A `SyntaxError` is raised, not
    cached: the next read of a file somebody is mid-way through editing parses again.
    """
    text = Path(path).read_text(encoding="utf-8")
    key = hashlib.blake2b(text.encode("utf-8"), digest_size=16).digest()
    tree = _trees.get(key)
    if tree is None:
        tree = ast.parse(text, filename=os.fspath(path))
        _trees[key] = tree
        # Out of the collector: a full collection walking the ~3.9 M nodes of both trees took 1.1 s
        # on an idle box, over the engine probe's 1.0 s (2026-10-22); freezing took 2 µs.
        gc.freeze()
    return tree


def cached() -> int:
    """How many distinct contents the cache holds — for the guard, and for a reader measuring."""
    return len(_trees)


def could_say(text: str, pattern: str | re.Pattern[str]) -> bool:
    """Whether `text` can spell what `pattern` matches, as written or as Python reads identifiers.

    The raw search first; text that is not ASCII is searched again after NFKC, the normalisation
    the tokenizer applies to every identifier (PEP 3131). ASCII text is never normalised."""
    if re.search(pattern, text):
        return True
    return not text.isascii() and re.search(
        pattern, unicodedata.normalize("NFKC", text)) is not None
