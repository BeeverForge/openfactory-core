"""Creating the board the platform itself holds — seven rows in `board.db` (ADR-0049 D1, D5).

WHAT "CREATING A BOARD" MEANS HERE. On a vendor's board it is an API call that mints an object and
hands back a coordinate; here it is the seven columns appearing in this project's rows, in board
order, with the platform's own names. There is no second object and therefore no coordinate: the
port's `create` answers `""` for the first half of its pair, and `init` writes nothing into the
registry, because there is nothing to point at.

IDEMPOTENT, AND SAYS SO THROUGH `attached`. `openfactory project init` promises whoever re-runs it
that the board step can be repeated, and this row keeps that promise twice over: it reports the
columns it already has, and the write itself only fills in what is missing — in board order,
renaming nothing, and moving nothing when nothing was missing. That is how a board made before
#753 gets its "Needs Review" row: `init` calls `create` on a board that is already attached,
because this row says it may (`completes_an_attached_board`). Unless another of its rows is
already called "Needs Review": that name is the other row's (`columns.carried_by`), no second
row of it is written, and `left_out` tells `init` which row carries it and how to opt in.
"""

from __future__ import annotations

from openfactory.adapters.board.columns import BOARD_ORDER, CANONICAL_COLUMNS, carried_by
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
        """Write the columns this project lacks and, when it wrote one, place every one in board
        order; answer `("", <the board's page>)`.

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
            had = _rows(conn, name)
            inserted = 0
            for position, key in enumerate(BOARD_ORDER):
                # A NAME ANOTHER ROW ALREADY CARRIES IS NOT `needs_review`'s TO TAKE, by the rule
                # reads and GitHub's write take (`columns.yields_its_name`). A board whose
                # `in_review` or `needs_action` row a person had called "Needs Review" got a second
                # row of that name on the re-run (PR #1040's review, measured 2026-10-22 on
                # 3cfca18d: `('in_review', 'Needs Review', 3), ('needs_review', 'Needs Review',
                # 4)`), the person-gated pull request went to the new row, and its name read back
                # as `in_review` — the factory's own review. `left_out` says so to `init`.
                if key not in had and carried_by(key, named.get(key), had, named):
                    continue
                # INSERT OR IGNORE, so a re-run adds what is missing and RENAMES NOTHING: a person
                # who renamed a column is entitled to keep the name (C-14), and an idempotent
                # command that quietly restored the platform's word would undo their edit.
                inserted += conn.execute(
                    "INSERT OR IGNORE INTO columns(project, key, name, position) VALUES (?,?,?,?)",
                    (name, key, named.get(key) or CANONICAL_COLUMNS[key], position)).rowcount
            # AND WHEN A ROW WAS ADDED, EVERY ROW TAKES ITS PLACE IN BOARD ORDER. A board made
            # before #753 holds six rows at 0-5; the seventh key is fifth in order, so the INSERT
            # gives it 4, which Needs Action already holds — and a tie sorts by insertion, so the
            # board read "Needs Action, Needs Review" (measured 2026-10-21 on a board written by
            # 1be1835a's `project init`). ONLY THEN: writing the order on every call undid a
            # person's own on a re-run that added nothing — Needs Action moved to position 99 by
            # hand came back before Done (PR #1040's review, @robertocsp, 2026-10-22, on
            # 3cfca18d). Only the position is written.
            if inserted:
                for position, key in enumerate(BOARD_ORDER):
                    conn.execute("UPDATE columns SET position = ? WHERE project = ? AND key = ?",
                                 (position, name, key))
        return "", f"{panel_url()}/p/{name}/board"

    def keys(self, project) -> frozenset[str]:
        """The keys of the columns this project has. `init` compares them before and after `create`
        to say whether it added any: `attached()` is ordered by position, so comparing it read a
        re-order as an addition (PR #1040's review, 2026-10-22)."""
        with connect(_db_of(project)) as conn:
            return frozenset(_rows(conn, _name_of(project)))

    def left_out(self, project) -> str:
        """Why `create` added no "Needs Review" column to this project's board, or `""`.

        A SENTENCE `init` PRINTS, because a re-run that quietly declined the opt-in the release note
        promised would look like a defect: it names the column that already carries the name and
        the one way in, a name of `needs_review`'s own under the tracker's `columns` option."""
        named = declared_columns_of(project)
        with connect(_db_of(project)) as conn:
            had = _rows(conn, _name_of(project))
        key = "needs_review"
        if key in had or not had:
            return ""
        carrier = carried_by(key, named.get(key), had, named)
        if not carrier:
            return ""
        return (f"no \"Needs Review\" column added: this board's '{carrier}' column is already "
                f"called \"{had[carrier]}\". To give pull requests waiting on a person's review a "
                f"column of their own, map needs_review to another name under the tracker's "
                f"`columns` option (e.g. '{{\"needs_review\": \"Awaiting Review\"}}') and re-run "
                f"`openfactory project init {_name_of(project)}`")

    def _existing(self, project) -> list[str]:
        with connect(_db_of(project)) as conn:
            rows = conn.execute("SELECT name FROM columns WHERE project = ? ORDER BY position ASC",
                                (_name_of(project),)).fetchall()
        return [r["name"] for r in rows]


def declared_columns_of(project) -> dict[str, str]:
    """The deployment's own column names for this project (`columns:`), or `{}`."""
    from openfactory.adapters.board.factory import declared_columns

    return declared_columns(project, (getattr(getattr(project, "tracker", None), "options", None)
                                      or {})) or {}


def _rows(conn, project: str) -> dict[str, str]:
    """This project's rows as they stand, `{key: name}`."""
    return {r["key"]: r["name"] for r in conn.execute(
        "SELECT key, name FROM columns WHERE project = ?", (project,)).fetchall()}


def _name_of(project) -> str:
    """The project's own name — the key every row in this file is written under."""
    return (getattr(project, "name", "") or "").strip()


def _db_of(project):
    """The project's own `board_db` option, when it names one; otherwise the deployment's."""
    options = (getattr(getattr(project, "tracker", None), "options", None) or {})
    return options.get("board_db") or None
