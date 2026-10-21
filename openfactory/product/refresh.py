"""A product's knowledge brought up to date: its documents read, and its search index brought up to
them, to its requirements and to its boards — on the schedule, or now, when somebody asks (#1004).

ONE PASS, TWO CALLERS. The knowledge pipeline's schedule (`activities._do_ingest_documents`, on
`KnowledgeRefreshWorkflow`'s tick) and the `product_refresh` row
(`ProductKnowledgeRefreshWorkflow`, on the worker) both run `documents_and_index`. It reads nothing
and indexes nothing itself: the documents are read by the documents' own pass
(`documents/ingest.py`), exactly as the schedule always read them, and the index is brought up by
the one indexer (`index/retrieval.refresh` → `index/sync.sync`), which a turn calls too. So what the
schedule hands the index, an asked pass hands it as well, and a second indexer never exists.

AN ASKED PASS ALSO READS THE BOARDS — of every registry project of the product (`model.members`),
each as the role sees it (`ProductModule._board_cards`). The schedule never has: a board read is a
tracker call that opens an impediment when it fails, and a turn reads its own board before it
searches. A client that asks for the knowledge to be brought up now asks for the cards too, since
its next read of the product's knowledge (`GET /api/product/{project}/knowledge`) searches them.

WHAT IS LEFT OUT, AND WHY (`NOT_REFRESHED`): a conversation's lines. They are not knowledge the
product publishes — a client's read never returns them (`items.PUBLISHED_KINDS`) — and the turn
that searches them brings them up from its own recall a moment before.

WHAT A PASS LEAVES BEHIND, FOR A READ. Every pass, scheduled or asked, writes how it went to
`<product_state_dir>/knowledge-refresh.json` — when it started and finished, what it brought the
index up to, and each thing it did not, in a sentence — and a running pass is listed there while it
runs. `state` is the read: `product_status` answers it as `knowledge`. A pass that fails says so
there; one whose worker died is said to have stopped once it outlived its own ceiling
(`STOPPED_AFTER`); a record that cannot be read is said to be unknown, never "never refreshed".
"""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

log = logging.getLogger("openfactory.product.refresh")

#: Who ran a pass: the knowledge pipeline's schedule, or somebody who asked (`product_refresh`).
SCHEDULE, ASKED = "schedule", "asked"

#: How a pass ended. REFRESHED: every source was read and the index brought up to it. DEGRADED: the
#: pass ended and something was not brought up — each said in `degraded`. FAILED: the documents
#: could not be read at all, or the pass never finished. NO_CONTEXT: there is no checkout of the
#: context repository, so there was nothing to read.
REFRESHED, DEGRADED, FAILED, NO_CONTEXT = "refreshed", "degraded", "failed", "no-context"
OUTCOMES = (REFRESHED, DEGRADED, FAILED, NO_CONTEXT)

#: What the `product_refresh` row answers about the pass it asked for: one was started, or one
#: already running for the product was joined — never a second one beside it.
STARTED, JOINED = "started", "joined"

#: The sources of the index (`sync.sync`'s) an asked pass does not hand it, each with why.
NOT_REFRESHED = {
    "said": "a conversation's lines are not knowledge the product publishes, and the turn that "
            "searches them brings them up from its own recall before it does",
}

#: The ceiling of one asked pass on the worker — its activity's `start_to_close_timeout`. The
#: documents' own budget (`activities.DOCUMENT_PASS_SECONDS`) ends inside it, as on the schedule.
PASS_CEILING = timedelta(minutes=10)
#: How long the worker may go without saying the pass is alive before the engine calls it lost.
PASS_HEARTBEAT = timedelta(minutes=1)
#: The whole flight — the workflow's execution timeout: the pass, with room for a busy queue.
FLIGHT_CEILING = timedelta(minutes=15)
#: How long a pass may be listed as running before a read says it stopped: a pass that outlived
#: the ceilings above is one whose worker died before it could say how it ended.
STOPPED_AFTER = FLIGHT_CEILING

RECORD_FILE = "knowledge-refresh.json"
#: How long a pass waits for another one's write of the record before it gives the write up.
RECORD_WAIT_SECONDS = 10.0


def _now() -> str:
    """To the microsecond: a pass that starts the second another ends is still after it."""
    return datetime.now(UTC).isoformat()


@dataclass
class Refreshed:
    """How one pass went — what it returns, and what the record keeps of it."""

    by: str
    outcome: str = REFRESHED
    started_at: str = ""
    finished_at: str = ""
    #: the documents' pass's sentence (`ingest.Report.sentence`), and the index's (`Synced`)
    documents: str = ""
    index: str = ""
    #: what the index was brought up to: `documents`, `requirements`, `board:<registry project>`
    sources: list[str] = field(default_factory=list)
    #: each thing this pass did not bring up, and why, in a sentence that names no path or secret
    degraded: list[str] = field(default_factory=list)
    #: why some items have no vector yet — they are searchable by their words, not their meaning.
    #: Not a degradation of the pass: the knowledge is as fresh, its search is narrower.
    semantic: str = ""

    def sentence(self) -> str:
        said = [self.outcome]
        if self.documents:
            said.append(f"documents: {self.documents}")
        if self.index:
            said.append(f"index: {self.index}")
        said += self.degraded
        return "; ".join(said)


def workflow_id(project) -> str:
    """THE ONE FLIGHT OF A PRODUCT: the id the `product_refresh` row starts its workflow under.
    Keyed by the PRODUCT (`product_key`), never by the registry project it was asked through — two
    registry projects of one context repository are one product, with one set of documents and one
    index, and an ask through either joins the pass the other started."""
    from openfactory.product.key import product_key, product_slug

    return f"openfactory-product-refresh-{product_slug(product_key(project))}"


def documents_and_index(project, *, by: str, budget_seconds: float,
                        boards: bool = False) -> Refreshed:
    """Read the documents of `project`'s context repository that changed since the last pass, and
    bring the product's index up to them, to the requirements and — with `boards` — to the board of
    every registry project of the product. Raises only what is not an `Exception` — a stop — and
    records it first: how it went is the answer, and the record."""
    done = Refreshed(by=by, started_at=_now())
    flight = _began(project, done)
    try:
        _run(project, done, budget_seconds=budget_seconds, boards=boards)
    except Exception:  # noqa: BLE001 — the pass ends with a word, never with a traceback
        log.warning("the knowledge refresh of %s failed", getattr(project, "name", "?"),
                    exc_info=True)
        done.outcome = FAILED
        done.degraded.append("the pass failed (the reason is in the platform's log)")
    except BaseException:
        # STOPPED, NOT REFRESHED: the record is written below whatever ended the pass, and a pass
        # interrupted half-way must never be recorded under the outcome's default
        done.outcome = FAILED
        done.degraded.append("the pass was stopped before it ended")
        raise
    finally:
        done.finished_at = _now()
        _ended(project, flight, done)
    return done


def _run(project, done: Refreshed, *, budget_seconds: float, boards: bool) -> None:
    from openfactory.product.documents.ingest import ingest
    from openfactory.product.module import ProductModule

    name = str(getattr(project, "name", "") or "")
    try:
        module = ProductModule(project, via="api")
        ctx = module.context()
        if not ctx.docs_path:
            done.outcome = NO_CONTEXT
            done.degraded.append("the context repository could not be checked out, so nothing "
                                 "was read — the index keeps what it had")
            return
        terms = [fact.term for fact in ctx.domain.live()]
        report = ingest(project, root=Path(ctx.docs_path), commit=ctx.docs_commit, terms=terms,
                        budget_seconds=budget_seconds)
    except Exception:  # noqa: BLE001 — a pass that failed is read again at the next one
        log.warning("the documents of %s could not be ingested", name, exc_info=True)
        done.outcome = FAILED
        done.degraded.append("the documents could not be read (the reason is in the platform's "
                             "log) — the index keeps what it had")
        return
    done.documents = report.sentence()
    done.sources.append("documents")
    if report.left:
        done.degraded.append(f"{report.left} document(s) were not reached inside the pass's time "
                             f"budget — the next pass reads them")
    if report.busy:
        done.degraded.append(f"{len(report.busy)} document(s) were being read by another pass")
    # THE CORPUS ONLY WHEN IT WAS READ, as a turn hands it: an unavailable context carries an EMPTY
    # corpus, and an empty corpus handed to the index takes every requirement out of it
    corpus = getattr(ctx, "corpus", None) if getattr(ctx, "available", True) else None
    if corpus is None:
        done.degraded.append("the requirements could not be read — the index keeps the "
                             "requirements it had")
    read = _boards(project, module, done) if boards else {}
    _index(project, done, corpus=corpus,
           requirements_dir=getattr(ctx, "requirements_dir", "requirements"), boards=read)
    if done.degraded and done.outcome == REFRESHED:
        done.outcome = DEGRADED


def _boards(project, module, done: Refreshed) -> dict[str, tuple[object, list]]:
    """`{registry project: (project, cards)}` — the board of every registry project of the
    product, as the role sees it. A board that cannot be read is said, and the index keeps the
    cards it had of it: a board unread is never a board emptied."""
    from openfactory.product.model import members
    from openfactory.product.module import ProductModule

    read: dict[str, tuple[object, list]] = {}
    for member in members(project):
        name = str(getattr(member, "name", "") or "")
        try:
            reader = module if name == getattr(project, "name", None) else ProductModule(
                member, via="api")
            cards = reader._board_cards()
        except Exception:  # noqa: BLE001 — one board's trouble costs that board only
            log.warning("the board of %s could not be read for its product's index", name,
                        exc_info=True)
            cards = None
        if cards is None:
            done.degraded.append(f"the board of {name} could not be read — the index keeps the "
                                 f"cards it had of it")
            continue
        read[name] = (member, cards)
    return read


def _index(project, done: Refreshed, *, corpus, requirements_dir: str,
           boards: dict[str, tuple[object, list]]) -> None:
    """THE ONE INDEXER, handed every source this pass read: the document records always, the
    corpus when it was read, each board read — the asking project's with the corpus, every other
    member's under its own name, which is how the index keeps each board's cards apart."""
    name = str(getattr(project, "name", "") or "")
    try:
        from openfactory.product.index.retrieval import refresh

        own = boards.get(name)
        synced = refresh(project, corpus=corpus, requirements_dir=requirements_dir,
                         cards=own[1] if own else None, embed_limit=None)
        others = [refresh(member, cards=cards, embed_limit=None)
                  for member_name, (member, cards) in boards.items() if member_name != name]
    except Exception:  # noqa: BLE001 — the records are written; the index catches up at a turn
        log.warning("the index of %s could not be brought up to its documents", name,
                    exc_info=True)
        done.degraded.append("the index could not be brought up to date (the reason is in the "
                             "platform's log) — a search reads it as it was")
        return
    done.index = synced.sentence()
    for one in (synced, *others):
        if one.busy:
            done.degraded.append("another sync of this product held the index, so this pass did "
                                 "not bring it up — a search reads it as it was")
            return
        if one.documents_unread:
            done.degraded.append("the document records could not be read by the index — it keeps "
                                 "the documents it had")
        done.semantic = done.semantic or one.degraded
    if corpus is not None:
        done.sources.append("requirements")
    done.sources += [f"board:{member_name}" for member_name in boards]


# ── what a pass leaves behind ───────────────────────────────────────────────────────────────────

def record_path(project) -> Path:
    from openfactory.paths import product_state_dir
    from openfactory.product.key import product_key

    return product_state_dir(product_key(project)) / RECORD_FILE


def _read(path: Path) -> dict:
    """The record as it stands — `{}` when no pass ever wrote it. Raises `OSError`/`ValueError` when
    it exists and cannot be read: "unknown" and "never" are two different answers."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    held = json.loads(text)
    if not isinstance(held, dict):
        raise ValueError("the record is not an object")
    return held


def _update(project, change: Callable[[dict], None]) -> None:
    """Read, change and write the record under its lock. A record that cannot be written costs the
    record, never the pass — and says so in the log."""
    from openfactory.util.filelock import lock_beside, replace_atomically

    path = record_path(project)
    try:
        with lock_beside(path).held(timeout=RECORD_WAIT_SECONDS):
            try:
                held = _read(path)
            except (OSError, ValueError) as exc:
                log.warning("the knowledge refresh record of %s could not be read (%s) — it is "
                            "written again", getattr(project, "name", "?"), exc)
                held = {}
            change(held)
            replace_atomically(path, json.dumps(held, indent=2, sort_keys=True))
    except Exception:  # noqa: BLE001 — the pass's outcome stands; only its record is lost
        log.warning("the knowledge refresh record of %s could not be written",
                    getattr(project, "name", "?"), exc_info=True)


def _stale(started_at: str, now: datetime) -> bool:
    try:
        then = datetime.fromisoformat(str(started_at))
    except ValueError:
        return True
    return now - then > STOPPED_AFTER


def _began(project, done: Refreshed) -> str:
    """The pass, listed as running from now — and any listed pass that outlived its ceiling, taken
    off the list (its worker died; `state` said so while it was the newest thing to say)."""
    flight = secrets.token_hex(6)

    def change(held: dict) -> None:
        running = held.setdefault("running", {})
        now = datetime.now(UTC)
        for gone in [k for k, v in running.items() if _stale((v or {}).get("started_at"), now)]:
            log.warning("a knowledge refresh of %s started at %s never finished",
                        getattr(project, "name", "?"), running[gone].get("started_at"))
            running.pop(gone)
        running[flight] = {"by": done.by, "started_at": done.started_at,
                           "project": str(getattr(project, "name", "") or "")}

    _update(project, change)
    return flight


def _ended(project, flight: str, done: Refreshed) -> None:
    def change(held: dict) -> None:
        (held.get("running") or {}).pop(flight, None)
        held["last"] = {**asdict(done), "project": str(getattr(project, "name", "") or "")}
        if done.outcome in (REFRESHED, DEGRADED):
            held["refreshed_at"] = done.finished_at

    _update(project, change)


def state(project, *, now: datetime | None = None) -> dict:
    """What a read says of the product's knowledge (`product_status`'s `knowledge`):

      - `refreshed_at`: when a pass last brought the index up, fully or in part — None if none has;
      - `outcome`, `by`, `finished_at`, `sources`, `documents`, `index`, `degraded`, `semantic`: the
        last pass, however it ended — `degraded` is every thing it did not bring up, in a sentence;
      - `running_since`: when the pass running now started, None when none is.

    A pass listed as running past `STOPPED_AFTER` is the newest thing to say when it started after
    the last one ended: `outcome` is then `failed`, with why. Never raises."""
    now = now or datetime.now(UTC)
    out: dict = {"refreshed_at": None, "outcome": None, "by": None, "finished_at": None,
                 "sources": [], "documents": "", "index": "", "degraded": [], "semantic": "",
                 "running_since": None}
    try:
        held = _read(record_path(project))
    except Exception as exc:  # noqa: BLE001 — "could not be read" is an answer too
        log.warning("the knowledge refresh record of %s could not be read (%s)",
                    getattr(project, "name", "?"), exc)
        out["degraded"] = ["the record of the product's knowledge refreshes could not be read — "
                           "when it was last brought up to date is unknown, not never"]
        return out
    last = held.get("last") if isinstance(held.get("last"), dict) else {}
    out["refreshed_at"] = held.get("refreshed_at") or None
    for key in ("outcome", "by", "finished_at"):
        out[key] = last.get(key) or None
    for key in ("documents", "index", "semantic"):
        out[key] = str(last.get(key) or "")
    out["sources"] = [str(s) for s in last.get("sources") or []]
    out["degraded"] = [str(s) for s in last.get("degraded") or []]
    running = [v for v in (held.get("running") or {}).values() if isinstance(v, dict)]
    live = sorted(str(v.get("started_at")) for v in running
                  if not _stale(v.get("started_at"), now))
    out["running_since"] = live[0] if live else None
    ended = str(last.get("finished_at") or "")
    stopped = sorted((v for v in running if _stale(v.get("started_at"), now)
                      and str(v.get("started_at") or "") > ended),
                     key=lambda v: str(v.get("started_at") or ""))
    if stopped:
        newest = stopped[-1]
        out.update(outcome=FAILED, by=newest.get("by") or None, sources=[], documents="",
                   index="", semantic="",
                   degraded=[f"a refresh started at {newest.get('started_at')} never finished — "
                             f"the worker running it stopped before it ended; ask again"])
    return out


def sentence_for(project_name: str, flight: str) -> str:
    """The `product_refresh` row's sentence for what it did with the ask."""
    if flight == JOINED:
        return (f"{project_name}'s knowledge was already being brought up to date; this ask joined "
                f"that pass. product_status says when it finished and how.")
    return (f"{project_name}'s knowledge is being brought up to date now: its documents, its "
            f"requirements and its board. product_status says when it finished and how.")


__all__ = [
    "ASKED", "DEGRADED", "FAILED", "FLIGHT_CEILING", "JOINED", "NOT_REFRESHED", "NO_CONTEXT",
    "OUTCOMES", "PASS_CEILING", "PASS_HEARTBEAT", "REFRESHED", "SCHEDULE", "STARTED",
    "STOPPED_AFTER", "Refreshed", "documents_and_index", "record_path", "sentence_for", "state",
    "workflow_id",
]
