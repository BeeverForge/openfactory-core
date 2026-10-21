"""Creating the board the platform itself holds — seven rows in `board.db` (ADR-0049 D1, D5).

WHAT "CREATING A BOARD" MEANS HERE. On a vendor's board it is an API call that mints an object and
hands back a coordinate; here it is the seven columns appearing in this project's rows, in board
order, with the platform's own names. There is no second object and therefore no coordinate: the
port's `create` answers `""` for the first half of its pair, and `init` writes nothing into the
registry, because there is nothing to point at.

IDEMPOTENT, AND SAYS SO THROUGH `attached`. `openfactory project init` promises whoever re-runs it
that the board step can be repeated, and this row keeps that promise twice over: it reports the
columns it already has, and the write itself only fills in what is missing — in board order,
renaming nothing. That is how a board made before #753 gets its "Needs Review" row: `init` calls
`create` on a board that is already attached, because this row says it may
(`completes_an_attached_board`).
"""

from __future__ import annotations

from openfactory.adapters.board.columns import BOARD_ORDER, CANONICAL_COLUMNS
from openfactory.adapters.board_db import connect


class LocalBoardSetup:
    """The platform's columns, for one project, in `board.db`."""

    #: `create` IS SAFE ON A BOARD THAT IS ALREADY ATTACHED, and adds the rows it lacks; `init`
    #: reads this to call it on a re-run. A row whose `create` mints a second board must not say so.
    completes_an_attached_board = True

    def attached(self, project) -> str:
        """A sentence naming the columns this project already has, or `""`."""
        names = self._existing(project)
        return f"{len(names)} columns ({', '.join(names)})" if names else ""

    def create(self, *, project, owner: str, title: str, token: str | None) -> tuple[str, str]:
        """Write the columns this project lacks, place every one in board order; answer
        `("", <the board's page>)`.

        `owner` and `token` ARE ACCEPTED AND UNUSED, which is the port's shape rather than an
        oversight: the caller resolves a credential on the tracker axis for every row and a row
        that refused the argument would fail on a deployment that has one. There is nobody to
        authenticate to — the file is this deployment's own."""
        from openfactory.adapters.board.factory import declared_columns
        from openfactory.adapters.tracker.local import panel_url

        name = _name_of(project)
        # THE CLIENT'S OWN WORDS, AS ON EVERY OTHER ROW (C-14, #231). This row wrote the platform's
        # six verbatim and ignored `columns:` — the option the other three boards take — so a local
        # deployment that declared `columns: '{"todo": "A Fazer"}'` got a board saying `TO-DO` and
        # an option that changed nothing. That mattered the moment the row became the one that
        # answers *which stage is this column* (`LocalBoard.stage_key`): the refusal for a column
        # nobody maps names this option as the repair, and a repair that does nothing is the
        # defect it was named after.
        named = declared_columns(project, (getattr(project.tracker, "options", None) or {})) or {}
        with connect(_db_of(project), write=True) as conn:
            for position, key in enumerate(BOARD_ORDER):
                # INSERT OR IGNORE, so a re-run adds what is missing and RENAMES NOTHING: a person
                # who renamed a column is entitled to keep the name (C-14), and an idempotent
                # command that quietly restored the platform's word would undo their edit.
                conn.execute(
                    "INSERT OR IGNORE INTO columns(project, key, name, position) VALUES (?,?,?,?)",
                    (name, key, named.get(key) or CANONICAL_COLUMNS[key], position))
                # AND EVERY ROW TAKES ITS PLACE IN BOARD ORDER, the existing ones included. A board
                # made before #753 holds six rows at 0-5; the seventh key is fifth in order, so the
                # INSERT above gives it 4, which Needs Action already holds — and a tie sorts by
                # insertion, so the board read "Needs Action, Needs Review" (measured 2026-10-21 on
                # a board written by 1be1835a's `project init`). Only the position is written.
                conn.execute("UPDATE columns SET position = ? WHERE project = ? AND key = ?",
                             (position, name, key))
        return "", f"{panel_url()}/p/{name}/board"

    def _existing(self, project) -> list[str]:
        with connect(_db_of(project)) as conn:
            rows = conn.execute("SELECT name FROM columns WHERE project = ? ORDER BY position ASC",
                                (_name_of(project),)).fetchall()
        return [r["name"] for r in rows]


def _name_of(project) -> str:
    """The project's own name — the key every row in this file is written under."""
    return (getattr(project, "name", "") or "").strip()


def _db_of(project):
    """The project's own `board_db` option, when it names one; otherwise the deployment's."""
    options = (getattr(getattr(project, "tracker", None), "options", None) or {})
    return options.get("board_db") or None
