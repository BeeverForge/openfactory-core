"""The panel's board screen has a meaning for every column the platform creates (#753).

WHAT IS PROVEN HERE:

  · `_BCOL` in `openfactory/api/panel.html` — the table that gives each of the platform's columns
    its tone and its one-line meaning — names every column `column_names()` writes onto a new
    board. A column the platform creates and the panel does not describe is drawn with no tone and
    no note, so a person reading the board cannot tell "waiting on a reviewer" from "stuck".

The table is PARSED out of the page, comments stripped, and its rows read as data: the comment
above `_BCOL` that explains the columns would otherwise satisfy a text search for a name.
"""

from __future__ import annotations

import json
import pathlib
import re

PANEL = (pathlib.Path(__file__).resolve().parent.parent
         / "openfactory" / "api" / "panel.html")


def _bcol_rows(page: str) -> list[dict]:
    """The rows of `const _BCOL = [...]`, as dicts, read from the page with comments stripped."""
    start = page.index("const _BCOL = [")
    end = page.index("];", start)
    literal = page[start + len("const _BCOL = "):end + 1]
    literal = re.sub(r"/\*.*?\*/", "", literal, flags=re.S)
    literal = re.sub(r"(?m)^\s*//.*$", "", literal)
    # The rows are JS object literals with bare keys and a trailing comma; quoting the keys and
    # dropping the trailing commas makes them JSON, so the names are read as values, not text.
    literal = re.sub(r"([{,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', literal)
    literal = re.sub(r",(\s*[}\]])", r"\1", literal)
    return json.loads(literal)


def test_the_panel_has_a_meaning_for_every_column_the_platform_creates():
    """#753 AC4: `needs_review` is a seventh canonical column ("Needs Review"), and the panel's
    `_BCOL` held the six of main (1be1835a), so the seventh column was drawn with no tone and no
    note — the one column whose whole point is to say "not stuck" said nothing."""
    from openfactory.adapters.board.columns import column_names

    rows = _bcol_rows(PANEL.read_text(encoding="utf-8"))
    described = [row["name"] for row in rows]
    missing = [name for name in column_names() if name not in described]
    assert not missing, f"the panel's _BCOL gives no meaning to {missing}; it names {described}"
