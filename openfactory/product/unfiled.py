"""The fronts a requirement's breakdown did not file, kept where the requirement is shown (#564).

A breakdown answers with a sentence per front it could not file — the vet refused it, the clock
ran out, the tracker failed — and on the panel that sentence was a toast, gone in seconds, while
the requirement's row went on looking like everything had been filed. The fronts not filed are a
loop of the ledger (`ledger.UNFILED`): opened when a breakdown ends leaving some out, closed when
the requirement's next breakdown ends, whatever it filed. The requirements read carries them
(`catalog._product_requirements`), and the page shows them beside the retry.

NOBODY IS CHASED ABOUT THEM: the loop's owner is this module, not the product role, so no agenda,
sweep or reminder that reads the role's loops ever sees it.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

log = logging.getLogger(__name__)

#: The owner of these loops — nobody's agenda.
OWNER = "breakdown"
#: The outcome a loop closes with when the requirement's next breakdown ends.
BROKEN_DOWN_AGAIN = "broken_down_again"


def not_filed(results) -> list[str]:
    """The module's sentence for each front a breakdown did not file — never a card that landed,
    one that already existed, the module's verdict that nothing is to be built (#182), or that
    the product's code has not started (#992)."""
    return [str(getattr(r, "detail", "") or "").strip()
            for r in results or []
            if not getattr(r, "ok", False) and not getattr(r, "nothing_to_build", False)
            and not getattr(r, "waits_for_code", False)
            and str(getattr(r, "detail", "") or "").strip()]


def record(project, number: int, results, *, now: str | None = None) -> list[str]:
    """What the requirement's breakdown just left out, written over what the last one did: the
    open loop is closed, and a new one opened when fronts were left out again. Returns the fronts
    recorded. RAISES when the ledger cannot be written — the caller logs it; the cards stand."""
    from openfactory.memory import store as loop_store
    from openfactory.memory.ledger import UNFILED, close_by_observation, open_loop, waiting

    name = getattr(project, "name", "") or str(project)
    subject = str(int(number))
    ts = now or datetime.now(UTC).isoformat()
    rows = loop_store.read(name)
    # THIS REQUIREMENT'S, BY THE KEY: every other requirement's fronts stay as they were
    out = close_by_observation(waiting(rows, kind=UNFILED, owner=OWNER),
                               {(UNFILED, subject, ""): BROKEN_DOWN_AGAIN})
    fronts = not_filed(results)
    if fronts:
        out.append(open_loop(UNFILED, subject, owner=OWNER, ts=ts,
                             context={"fronts": json.dumps(fronts, ensure_ascii=False)}))
    if out:
        loop_store.write(name, out)
    return fronts


def open_fronts(project) -> dict[int, list[str]]:
    """Requirement number → the fronts its last breakdown did not file, for every requirement that
    has some. RAISES when the ledger cannot be read; the caller says so."""
    from openfactory.memory import store as loop_store
    from openfactory.memory.ledger import UNFILED, waiting

    out: dict[int, list[str]] = {}
    for loop in waiting(loop_store.read(getattr(project, "name", "") or str(project)),
                        kind=UNFILED, owner=OWNER):
        try:
            fronts = json.loads((loop.context or {}).get("fronts") or "[]")
            out[int(loop.subject)] = [str(f) for f in fronts if str(f).strip()]
        except (ValueError, TypeError):
            log.warning("an unreadable unfiled-fronts loop for requirement %r was skipped",
                        loop.subject)
    return out
