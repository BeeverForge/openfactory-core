"""Requirements written elsewhere, imported into a product under its corpus's rules (#993).

A PRODUCT'S CONTEXT CAN RECEIVE REQUIREMENTS WRITTEN SOMEWHERE ELSE — a later round of prototyping,
a second phase of a specification, a folder a person brings. Landing those files as they are is
wrong three ways: their numbers start at `0001` and collide with the product's own, their titles may
be promises the corpus already holds, and a new text for an `accepted` requirement would rewrite a
promise the factory defends. The rules that make it right already exist; this module applies them
to a set of files from outside, and writes nothing of its own judgement.

THE SAME SLUG IS THE SAME PROMISE. The slug comes from the title, so it is arithmetic, never a
judgement (`corpus._cross_check`'s `same-promise-twice`). For each requirement the folder brings,
against the LIVE requirements of the product carrying its slug:

    none                      NEW        minted after the highest number ever used
    the same text, word for   SAME       nothing new; its decision rows join the existing
    word                                 register, deduplicated by day and text
    a new text, nobody        REVISION   minted, `Supersedes:` the old one, which is marked
    agreed the old one                   `superseded-by` (`authoring._mark_superseded`)
    a new text, the old one   BESIDE     nothing is touched; the text is kept in the import's
    is `accepted`                        record as a proposal to change a promise
    (the folder's own dead    HISTORY    minted, landed with its status — so every reference
    ones)                                between the folder's requirements still resolves

AN IMPORT NEVER LANDS A PROMISE. A requirement the folder marks `accepted` lands `proposed`: the
promise is the product's to make, on a person's yes (ADR-0032), and a file copied from elsewhere is
not one. A reading of code (`observed`) stays `observed` — it is not a promise either.

ONE NUMBERING. The first number is `authoring.first_free` over the clone's corpus and the proposal
branches not yet landed — the formula a proposal from a conversation is re-minted with — and every
reference between the folder's requirements (`REQ-NNNN`, `Supersedes:`, `superseded-by`) is
renumbered with them.

WHAT ELSE A FOLDER BRINGS, and where it goes:

    domain/*.md               facts: a term the product already has is not rewritten; a new one
                              lands as `aprendido`, with its source (`authoring.fact_file`)
    every other file          a document, under `imported/` and its own path there; a different
                              file already at that path is kept beside it, the same bytes are
                              nothing new — so no import ever overwrites a document
    openfactory-import.yaml   where it came from, the order to review it in, where the design is,
                              the questions still open — carried into the record (#994 reads it)

NEVER LANDED, AND SAID: anything hidden (`.git/`, `.openfactory/`, `.okf/`), a link, a device;
`capabilities/` and `conversations/`, which only a person's confirmation and the distiller write;
a file in the requirements folder that is not `NNNN-slug.md`.

WHERE IT LANDS. Documents go under `imported/` rather than where the folder had them: the context
repository's base holds what a preview builds (`policy/context_writes.py`), and a folder from
outside must not be able to place a file anywhere a preview's shape could read it. The record goes
under `.openfactory/imports/<id>/` — the one path under the platform's directory a writer may land,
named by the policy (`context_writes.outside_an_import`).

PURE OVER FILES. `read` takes a folder or an archive into memory, never following a link and never
extracting to disk; `plan` reads a checkout of the product and decides; `land` writes the plan into
a checkout. The clone, the commit and the single push under the product's semaphore are
`ProductModule.import_requirements`'s, through `land_import` below.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import stat
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from openfactory.product.authoring import WriteResult
from openfactory.product.corpus import (
    _FIRST_SECTION_RE,
    _STATUS_RE,
    _SUPERSEDES_RE,
    _TITLE_RE,
    ACCEPTED,
    DECISIONS_HEADING,
    OBSERVED,
    PROPOSED,
    SUPERSEDED,
    Requirement,
    decision_cells,
    find_decisions_table,
    load_corpus,
)

log = logging.getLogger("openfactory.product.importing")

#: The kinds of a requirement's row in a plan — see the module's table.
NEW, SAME, REVISION, BESIDE, HISTORY = "new", "same", "revision", "beside", "history"
REQUIREMENT_KINDS = (NEW, SAME, REVISION, BESIDE, HISTORY)
#: The kinds of a fact's or a document's row: new; already there (a fact's term, a document's
#: bytes); a different document at its path, kept beside it.
KNOWN = "known"
PLACED_KINDS = (NEW, SAME, KNOWN, BESIDE)

#: The folder every imported document lands under, keeping its own path there.
IMPORTED_FOLDER = "imported"
#: The file in a folder that says where it came from and how to review it (#994).
MANIFEST = "openfactory-import.yaml"
#: Where a folder's facts are, as the product keeps its own (`loader.DOMAIN_DIRNAME`).
DOMAIN = "domain"
#: The record of one import, inside its directory under `.openfactory/imports/<id>/`.
RECORD_FILE = "record.json"
#: Where the record keeps a text it would not land over an accepted requirement.
PROPOSALS = "proposals"

#: How long reading the documents an import landed may take before the person is answered — the
#: same patience `product_ingest` has inside a request; what it did not reach, the next scheduled
#: pass reads.
INGEST_SECONDS = 90

#: How much one import may bring. Read into memory whole, so bounded: a folder past either is
#: refused, said with its limit, before anything is planned.
MAX_FILES = 2000
MAX_TOTAL_BYTES = 256 * 1024 * 1024

_ARCHIVES = (".zip", ".tar", ".tar.gz", ".tgz")
_REF = re.compile(r"\bREQ-(\d{4})\b")
_FILE = re.compile(r"^(?P<num>\d{4})-(?P<slug>[a-z0-9][a-z0-9-]*)\.md$")


class NotImportable(ValueError):
    """A folder that cannot be imported at all. `reason` is a key of `voice.import_said`, and
    `values` what it is said with — the caller says it in the product's language."""

    def __init__(self, reason: str, **values: object) -> None:
        self.reason, self.values = reason, values
        super().__init__(f"{reason}: {values}")


# ── what a folder brings ─────────────────────────────────────────────────────────────────────────

@dataclass
class Brought:
    """Everything a folder or an archive brings, in memory, and what was left out of it and why.

    `requirements` and `facts` are read by the corpus's and the domain's own readers; `documents`
    are bytes by their path in the folder; `refusals` are the folder's own requirement errors — a
    folder whose requirements contradict themselves is not planned."""

    name: str
    digest: str
    requirements: list[Requirement] = field(default_factory=list)
    facts: list = field(default_factory=list)
    documents: dict[str, bytes] = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)
    left_out: list[tuple[str, str]] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)


def is_archive(path: Path) -> bool:
    return str(path.name).lower().endswith(_ARCHIVES)


def read(source: Path, *, requirements_dir: str = "requirements") -> Brought:
    """What `source` — a folder, or an archive of one — brings. Raises `NotImportable`."""
    source = Path(source)
    try:
        info = source.lstat()
    except OSError:
        raise NotImportable("not_found", name=source.name) from None
    if stat.S_ISLNK(info.st_mode):
        raise NotImportable("a_link", name=source.name)
    if stat.S_ISDIR(info.st_mode):
        entries, left_out = _from_folder(source)
    elif stat.S_ISREG(info.st_mode) and is_archive(source):
        entries, left_out = _from_archive(source)
    else:
        raise NotImportable("not_a_folder", name=source.name)
    return _brought(source.name, entries, left_out, requirements_dir=requirements_dir)


def _safe_member(name: str) -> str:
    """A member's name as a plain relative path, or "" when it is absolute, climbs out, or names
    nothing — never trusted to be what an archive says it is."""
    raw = str(name or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return ""
    parts = [p for p in PurePosixPath(raw).parts if p not in ("", ".")]
    if not parts or ".." in parts:
        return ""
    return "/".join(parts)


def _hidden(path: str) -> bool:
    return any(part.startswith(".") for part in PurePosixPath(path).parts)


class _Budget:
    """The bounds of one import, counted as it is read."""

    def __init__(self, name: str) -> None:
        from openfactory.product.documents.ingest import max_bytes

        self.name, self.files, self.bytes, self.per_file = name, 0, 0, max_bytes()

    def take(self, size: int) -> None:
        self.files += 1
        self.bytes += max(0, int(size))
        if self.files > MAX_FILES:
            raise NotImportable("too_many", name=self.name, limit=MAX_FILES)
        if self.bytes > MAX_TOTAL_BYTES:
            raise NotImportable("too_large", name=self.name, limit=_size(MAX_TOTAL_BYTES))


def _size(n: int) -> str:
    return f"{n // (1024 * 1024)} MB"


def _from_folder(root: Path) -> tuple[dict[str, bytes], list[tuple[str, str]]]:
    """Every regular file under `root`, read with no link followed — a link, a device or a hidden
    path is left out and said."""
    entries: dict[str, bytes] = {}
    left_out: list[tuple[str, str]] = []
    budget = _Budget(root.name)
    for here, folders, files in os.walk(root, followlinks=False):
        rel = Path(here).relative_to(root)
        kept = []
        for folder in sorted(folders):
            path = (rel / folder).as_posix()
            if folder.startswith("."):
                left_out.append((path + "/", "hidden"))
            elif (Path(here) / folder).is_symlink():
                left_out.append((path, "a_link"))
            else:
                kept.append(folder)
        folders[:] = kept
        for name in sorted(files):
            path = (rel / name).as_posix()
            full = Path(here) / name
            if name.startswith("."):
                left_out.append((path, "hidden"))
                continue
            mode = full.lstat().st_mode
            if stat.S_ISLNK(mode):
                left_out.append((path, "a_link"))
                continue
            if not stat.S_ISREG(mode):
                left_out.append((path, "not_a_file"))
                continue
            size = full.lstat().st_size
            if size > budget.per_file:
                left_out.append((path, "too_large_a_file"))
                continue
            budget.take(size)
            fd = os.open(full, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as handle:
                entries[path] = handle.read(budget.per_file + 1)
    return entries, left_out


def _from_archive(path: Path) -> tuple[dict[str, bytes], list[tuple[str, str]]]:
    """Every regular member of a `.zip` or a tar, read into memory and never extracted: a member
    whose name is absolute or climbs out is refused, a link or a device is left out."""
    entries: dict[str, bytes] = {}
    left_out: list[tuple[str, str]] = []
    budget = _Budget(path.name)
    try:
        if path.name.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    name = _member(info.filename, left_out)
                    if not name:
                        continue
                    if stat.S_ISLNK(info.external_attr >> 16):
                        left_out.append((name, "a_link"))
                        continue
                    if info.file_size > budget.per_file:
                        left_out.append((name, "too_large_a_file"))
                        continue
                    # WHAT IS READ IS COUNTED, NOT WHAT THE ARCHIVE DECLARES: a member's size in a
                    # zip's directory is the archive's word, and a member that lies about it is
                    # read no further than the limit
                    with archive.open(info) as handle:
                        data = handle.read(budget.per_file + 1)
                    budget.take(len(data))
                    if len(data) > budget.per_file:
                        left_out.append((name, "too_large_a_file"))
                        continue
                    entries[name] = data
        else:
            with tarfile.open(path, "r:*") as archive:
                for member in archive:
                    if member.isdir():
                        continue
                    name = _member(member.name, left_out)
                    if not name:
                        continue
                    if member.issym() or member.islnk():
                        left_out.append((name, "a_link"))
                        continue
                    if not member.isfile():
                        left_out.append((name, "not_a_file"))
                        continue
                    if member.size > budget.per_file:
                        left_out.append((name, "too_large_a_file"))
                        continue
                    budget.take(member.size)
                    handle = archive.extractfile(member)
                    entries[name] = handle.read(budget.per_file + 1) if handle else b""
    except NotImportable:
        raise
    except (OSError, EOFError, zipfile.BadZipFile, tarfile.TarError, ValueError) as exc:
        log.warning("OPENFACTORY_PRODUCT_IMPORT_UNREADABLE archive=%s (%s)", path.name, exc)
        raise NotImportable("unreadable_archive", name=path.name) from None
    return entries, left_out


def _member(raw: str, left_out: list[tuple[str, str]]) -> str:
    name = _safe_member(raw)
    if not name:
        left_out.append((str(raw)[:200], "outside_the_folder"))
        return ""
    if _hidden(name):
        left_out.append((name, "hidden"))
        return ""
    return name


#: The folders of a context repository only one writer of the product writes — a confirmed
#: capability is a person's confirmation (`product_confirm_capability`), a distillate the
#: distiller's (`product/distil.py`). A file from outside landing there would be one of those
#: without anybody having made it.
def _reserved() -> tuple[str, ...]:
    from openfactory.product.capabilities import CAPABILITIES_DIR
    from openfactory.product.documents.record import DISTILLATES

    return (CAPABILITIES_DIR, DISTILLATES)


def _brought(name: str, entries: dict[str, bytes], left_out: list[tuple[str, str]], *,
             requirements_dir: str) -> Brought:
    """`entries` sorted into requirements, facts, documents and the manifest — the requirements
    and the facts read by the corpus's and the domain's own readers, over a scratch copy of only
    those files."""
    from openfactory.product.corpus import TEMPLATE_NUMBER
    from openfactory.product.domain import load_domain

    folder = requirements_dir.strip("/") or "requirements"
    if not any(p.startswith(f"{folder}/") for p in entries) and folder != "requirements":
        folder = "requirements"
    reserved = _reserved()
    digest = hashlib.sha256()
    for path in sorted(entries):
        digest.update(path.encode() + b"\0" + hashlib.sha256(entries[path]).digest())
    brought = Brought(name=name, digest=digest.hexdigest(), left_out=list(left_out))
    requirement_files: dict[str, str] = {}
    fact_files: dict[str, str] = {}
    for path, data in sorted(entries.items()):
        top = PurePosixPath(path).parts[0]
        parent = str(PurePosixPath(path).parent)
        if path == MANIFEST:
            brought.manifest = _manifest(data, brought.left_out)
        elif top in reserved:
            brought.left_out.append((path, "reserved"))
        elif parent == folder:
            matched = _FILE.match(PurePosixPath(path).name)
            if not matched:
                brought.left_out.append((path, "not_a_requirement"))
            elif int(matched.group("num")) == TEMPLATE_NUMBER:
                brought.left_out.append((path, "the_template"))
            else:
                requirement_files[PurePosixPath(path).name] = data.decode("utf-8", "replace")
        elif top == folder:
            brought.left_out.append((path, "inside_the_requirements"))
        elif parent == DOMAIN and path.endswith(".md"):
            fact_files[PurePosixPath(path).name] = data.decode("utf-8", "replace")
        else:
            brought.documents[path] = data
    with tempfile.TemporaryDirectory(prefix="openfactory-import-") as scratch:
        reqs, dom = Path(scratch) / "requirements", Path(scratch) / DOMAIN
        reqs.mkdir()
        dom.mkdir()
        for filename, text in requirement_files.items():
            (reqs / filename).write_text(text, encoding="utf-8")
        for filename, text in fact_files.items():
            (dom / filename).write_text(text, encoding="utf-8")
        corpus = load_corpus(reqs) if requirement_files else None
        domain = load_domain(dom)
    if corpus is not None:
        brought.requirements = sorted(corpus.requirements, key=lambda r: r.number)
        brought.refusals = [f"{f.path}: {f.message}" for f in corpus.errors]
    for filename in fact_files:
        if not any(f.path == filename for f in domain.facts):
            brought.left_out.append((f"{DOMAIN}/{filename}", "no_fact"))
    brought.facts = [f for f in domain.facts if f.live]
    brought.left_out += [(f"{DOMAIN}/{f.path}", "a_retired_fact")
                         for f in domain.facts if not f.live]
    return brought


def _manifest(data: bytes, left_out: list[tuple[str, str]]) -> dict:
    """The folder's own account of itself, read leniently — a field of the wrong shape is
    dropped, never guessed at; a file that is not YAML is said."""
    import yaml

    try:
        raw = yaml.safe_load(data.decode("utf-8", "replace")) or {}
    except yaml.YAMLError:
        left_out.append((MANIFEST, "unreadable_manifest"))
        return {}
    if not isinstance(raw, dict):
        left_out.append((MANIFEST, "unreadable_manifest"))
        return {}
    out: dict = {}
    if isinstance(raw.get("origin"), str) and raw["origin"].strip():
        out["origin"] = raw["origin"].strip()[:200]
    if isinstance(raw.get("design"), str) and raw["design"].strip():
        out["design"] = _safe_member(raw["design"])
    order = raw.get("order")
    if isinstance(order, list):
        out["order"] = [int(n) for n in order if isinstance(n, int) or str(n).isdigit()]
    questions = []
    for q in raw.get("questions") or []:
        if isinstance(q, str) and q.strip():
            questions.append({"text": q.strip()[:400]})
        elif isinstance(q, dict) and isinstance(q.get("text"), str) and q["text"].strip():
            row = {"text": q["text"].strip()[:400]}
            if isinstance(q.get("requirement"), int) or str(q.get("requirement", "")).isdigit():
                row["requirement"] = int(q["requirement"])
            if isinstance(q.get("ask"), str) and q["ask"].strip():
                row["ask"] = q["ask"].strip()[:120]
            questions.append(row)
    if questions:
        out["questions"] = questions
    return out


def inbox(project) -> Path:
    """The product's import inbox: where a folder or an archive is put for any caller but the
    command line to name — under the product's state directory, which every half of a deployment
    shares (`paths.product_state_dir`). A caller over the API names a folder by its name in here,
    and nothing outside it: a credential that reaches the API must not be able to read the
    server's own files into a context repository."""
    from openfactory.paths import product_state_dir
    from openfactory.product.semaphore import product_of

    return product_state_dir(product_of(project)) / "imports"


def import_id(brought: Brought, day: str) -> str:
    """The import's id: the day it is planned, and what it brought — so the same folder imported
    twice in one day is one import, and its record says so (`context_writes.import_record`)."""
    return f"{day}-{brought.digest[:10]}"


# ── the plan ─────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Row:
    """One requirement of the folder, and what the import does with it.

    `number` is where it is in the product after the import: minted (new, revision, history) or the
    live twin's (same, beside). `path` is the file it lands as, the twin's file its rows join, or
    the proposal the record keeps."""

    kind: str
    source: int
    slug: str
    title: str
    number: int
    status: str = ""
    replaces: tuple[int, ...] = ()
    rows: int = 0
    path: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "source": self.source, "slug": self.slug, "title": self.title,
                "number": self.number, "status": self.status, "replaces": list(self.replaces),
                "rows": self.rows, "path": self.path}


@dataclass(frozen=True)
class Placed:
    """One fact or document of the folder: `name` is its term or its path in the folder, `path`
    where it lands — "" when nothing lands (known, same)."""

    kind: str
    name: str
    path: str = ""
    beside: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "name": self.name, "path": self.path, "beside": self.beside}


@dataclass
class Plan:
    """What an import would do to a product, decided before anything is written."""

    id: str
    origin: str
    requirements: list[Row] = field(default_factory=list)
    facts: list[Placed] = field(default_factory=list)
    documents: list[Placed] = field(default_factory=list)
    left_out: list[tuple[str, str]] = field(default_factory=list)
    renumbered: dict[int, int] = field(default_factory=dict)
    order: list[int] = field(default_factory=list)
    design: str = ""
    questions: list[dict] = field(default_factory=list)

    def count(self, kind: str) -> int:
        return sum(1 for r in self.requirements if r.kind == kind)

    @property
    def lands_anything(self) -> bool:
        """Whether this plan writes a single file: a requirement, a decision row, a fact or a
        document. A folder the product already holds whole lands nothing — and records nothing."""
        return (any(r.kind != SAME or r.rows for r in self.requirements)
                or any(f.kind == NEW for f in self.facts)
                or any(d.kind in (NEW, BESIDE) for d in self.documents))

    def as_dict(self) -> dict:
        return {"id": self.id, "origin": self.origin,
                "requirements": [r.as_dict() for r in self.requirements],
                "facts": [f.as_dict() for f in self.facts],
                "documents": [d.as_dict() for d in self.documents],
                "left_out": [{"path": p, "why": w} for p, w in self.left_out],
                "renumbered": {str(k): v for k, v in sorted(self.renumbered.items())},
                "order": list(self.order), "design": self.design,
                "questions": list(self.questions),
                "counts": {k: self.count(k) for k in REQUIREMENT_KINDS}}

    @property
    def token(self) -> str:
        """The plan, digested: what a yes given to THIS plan carries back, so a product that moved
        between the plan and the yes is planned again instead of landed on a plan nobody saw."""
        core = {k: v for k, v in self.as_dict().items() if k != "counts"}
        return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()[:16]


def _fold(text: str) -> str:
    return " ".join(str(text or "").split())


def promise_of(text: str, renumbered: dict[int, int] | None) -> str:
    """What a requirement PROMISES, for "word for word": its title and its sections, without the
    header's fields (status, who asked, when — the record of a promise, not the promise) and
    without the decision register (what was decided while executing it, which joins instead).

    `renumbered` maps the folder's numbers to the product's; None masks every reference, which is
    how a first pass compares before any number is known."""
    title = _TITLE_RE.search(text)
    first = _FIRST_SECTION_RE.search(text)
    body = text[first.start():] if first else ""
    body = re.sub(rf"^##\s+{re.escape(DECISIONS_HEADING)}\s*$.*?(?=^##\s|\Z)", "", body,
                  flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    said = (title.group("title") if title else "") + "\n" + body
    if renumbered is None:
        said = _REF.sub("REQ-####", said)
    else:
        said = renumber(said, renumbered)
    return _fold(said)


def renumber(text: str, renumbered: dict[int, int]) -> str:
    """Every `REQ-NNNN` of the folder's numbering, in the product's. A number the folder does not
    carry is left as written — the plan says nothing it could not resolve was rewritten."""
    return _REF.sub(lambda m: f"REQ-{renumbered.get(int(m.group(1)), int(m.group(1))):04d}", text)


def plan(brought: Brought, *, root: Path, requirements_dir: str, first: int, ident: str,
         origin: str, existing_terms=None) -> Plan:
    """Decide what importing `brought` into the product checked out at `root` does.

    `first` is the first free number (`authoring.first_free` over this checkout and the unlanded
    proposal branches); `existing_terms` is the product's domain — read from `root` when None."""
    from openfactory.product.authoring import fact_file
    from openfactory.product.domain import load_domain

    folder = requirements_dir.strip("/") or "requirements"
    target = load_corpus(root / folder) if (root / folder).is_dir() else None
    targets = list(target.requirements) if target is not None else []
    out = Plan(id=ident, origin=origin, left_out=list(brought.left_out))

    live = [r for r in brought.requirements if r.is_live]
    twins = {r.number: sorted((t for t in targets if t.slug == r.slug and t.is_live),
                              key=lambda t: t.number) for r in live}
    # THE FOLDER'S HISTORY IS ITS OWN ONCE: a requirement the folder itself retired is the same as
    # any requirement of the product carrying its slug and its text, whatever that one's status —
    # so a folder imported a second time does not land its history a second time
    kin = {r.number: sorted((t for t in targets if t.slug == r.slug), key=lambda t: t.number)
           for r in brought.requirements if not r.is_live}
    # WORD FOR WORD, TO A FIXED POINT. Whether a text is the same may depend on what its references
    # become, and what a reference becomes depends on whether the requirement it names is the same:
    # a first pass compares with every reference masked, then each match is checked again with the
    # numbers it would land under, and one that no longer holds is a revision — until none moves.
    same: dict[int, Requirement] = {}
    for r in brought.requirements:
        for t in twins.get(r.number) or kin.get(r.number) or []:
            if promise_of(r.body, None) == promise_of(t.body, None):
                same[r.number] = t
                break
    while True:
        renumbered = _numbering(brought.requirements, same, twins, first)
        broken = [n for n, t in same.items()
                  if promise_of(_source(brought, n).body, renumbered) != promise_of(t.body, {})]
        if not broken:
            break
        for n in broken:
            del same[n]
    out.renumbered = renumbered

    for r in brought.requirements:
        number = renumbered[r.number]
        own = sorted(renumbered.get(n, n) for n in r.supersedes)
        if r.number in same:
            twin = same[r.number]
            # a retired text records no decision: its register is history too
            joining = len(_joining(r, twin)) if r.is_live and twin.is_live else 0
            if joining and find_decisions_table(twin.body) is None:
                # A REGISTER IS NEVER INVENTED (`authoring.add_decision_row`'s rule): the product's
                # file predates it, and the rows the folder brings are said, not written
                out.left_out.append((f"{folder}/{twin.path}", f"no_register:{joining}"))
                joining = 0
            out.requirements.append(Row(SAME, r.number, r.slug, r.title, twin.number,
                                        twin.status, rows=joining, path=f"{folder}/{twin.path}"))
        elif not r.is_live:
            status = (f"superseded-by {renumbered.get(r.superseded_by, r.superseded_by):04d}"
                      if r.status == SUPERSEDED and r.superseded_by else r.status)
            out.requirements.append(Row(HISTORY, r.number, r.slug, r.title, number, status,
                                        tuple(own), path=_path(folder, number, r.slug)))
        elif not twins[r.number]:
            out.requirements.append(Row(NEW, r.number, r.slug, r.title, number, _landing(r),
                                        tuple(own), path=_path(folder, number, r.slug)))
        elif any(t.status == ACCEPTED for t in twins[r.number]):
            agreed = next(t for t in twins[r.number] if t.status == ACCEPTED)
            out.requirements.append(Row(BESIDE, r.number, r.slug, r.title, agreed.number,
                                        agreed.status, path=_proposal(ident, agreed.number,
                                                                      r.slug)))
        else:
            replaced = tuple(sorted({*own, *(t.number for t in twins[r.number])}))
            out.requirements.append(Row(REVISION, r.number, r.slug, r.title, number,
                                        _landing(r), replaced,
                                        path=_path(folder, number, r.slug)))

    domain = existing_terms if existing_terms is not None else load_domain(root / DOMAIN)
    taken = set()
    for fact in brought.facts:
        if domain.get(fact.term) is not None or fact.term.strip().lower() in taken:
            out.facts.append(Placed(KNOWN, fact.term))
            continue
        taken.add(fact.term.strip().lower())
        path, _ = fact_file(_landed_fact(fact, ident, origin), said_by=fact.source or origin)
        path = _free(root, path, {f.path for f in out.facts})
        out.facts.append(Placed(NEW, fact.term, path))

    for name, data in sorted(brought.documents.items()):
        dest = f"{IMPORTED_FOLDER}/{name}"
        here = root / dest
        if not os.path.lexists(here):
            out.documents.append(Placed(NEW, name, dest))
            continue
        if here.is_file() and not here.is_symlink() and here.read_bytes() == data:
            out.documents.append(Placed(SAME, name, "", beside=dest))
            continue
        # SOMETHING IS ALREADY THERE — a different file, or a link: never written over, never
        # written through. The import's own copy goes beside it, named by the import.
        stem = PurePosixPath(dest)
        beside = _free(root, str(stem.with_name(f"{stem.stem}.{ident}{stem.suffix}")),
                       {d.path for d in out.documents})
        out.documents.append(Placed(BESIDE, name, beside, beside=dest))

    landed = {d.name: (d.path or d.beside) for d in out.documents}
    manifest = brought.manifest
    out.order = [renumbered[n] for n in manifest.get("order", []) if n in renumbered]
    out.design = landed.get(manifest.get("design", ""), "")
    for q in manifest.get("questions", []):
        row = {"text": renumber(q["text"], renumbered)}
        if q.get("requirement") in renumbered:
            row["requirement"] = renumbered[q["requirement"]]
        if q.get("ask"):
            row["ask"] = q["ask"]
        out.questions.append(row)
    return out


def _source(brought: Brought, number: int) -> Requirement:
    return next(r for r in brought.requirements if r.number == number)


def _numbering(requirements: list[Requirement], same: dict[int, Requirement],
               twins: dict[int, list[Requirement]], first: int) -> dict[int, int]:
    """The folder's numbers in the product's: a requirement the product already holds keeps the
    twin's number (the same promise, or the agreed one it would change), every other one is minted
    from `first`, in the folder's own order."""
    out: dict[int, int] = {}
    nxt = first
    for r in sorted(requirements, key=lambda x: x.number):
        if r.number in same:
            out[r.number] = same[r.number].number
        elif r.is_live and any(t.status == ACCEPTED for t in twins.get(r.number, [])):
            out[r.number] = next(t.number for t in twins[r.number] if t.status == ACCEPTED)
        else:
            out[r.number] = nxt
            nxt += 1
    return out


def _landing(r: Requirement) -> str:
    """The status a live requirement lands with: a reading of code stays one, everything else is
    `proposed` — whatever the folder said (an import never lands a promise)."""
    return OBSERVED if r.status == OBSERVED else PROPOSED


def _path(folder: str, number: int, slug: str) -> str:
    return f"{folder}/{number:04d}-{slug}.md"


def _proposal(ident: str, number: int, slug: str) -> str:
    from openfactory.policy.context_writes import import_record

    return f"{import_record(ident)}{PROPOSALS}/{number:04d}-{slug}.md"


def _free(root: Path, path: str, planned: set[str]) -> str:
    """`path`, or `-2`, `-3`… before its suffix when the product or this plan already has it."""
    candidate, n = path, 1
    while (root / candidate).exists() or candidate in planned:
        n += 1
        stem = PurePosixPath(path)
        candidate = str(stem.with_name(f"{stem.stem}-{n}{stem.suffix}"))
    return candidate


def _landed_fact(fact, ident: str, origin: str):
    """A fact of the folder as the product keeps one it was told: `aprendido`, attributed to its
    own source when it had one and to the import's origin otherwise, dated, and saying where."""
    from openfactory.product.domain import LEARNED, Fact

    # THE DAY IS A FILE NAME'S TOO (`authoring.fact_file`): a date the folder wrote in its own
    # words is kept only when it is a day, and the import's own day stands in otherwise
    day = fact.learned_on if re.fullmatch(r"\d{4}-\d{2}-\d{2}", fact.learned_on or "") \
        else ident[:10]
    return Fact(term=fact.term.strip(), body=fact.body.strip(), status=LEARNED,
                source=(fact.source or origin).strip(), where=f"import {ident} ({origin})",
                learned_on=day)


def _joining(source: Requirement, twin: Requirement) -> list[tuple[str, str, str]]:
    """The decision rows of `source` the twin's register does not hold — by day and text."""
    held = {(day.strip(), _fold(decided).lower())
            for day, decided, _ in decision_cells(twin.body)}
    return [(day, decided, who) for day, decided, who in decision_cells(source.body)
            if (day.strip(), _fold(decided).lower()) not in held]


# ── landing it ───────────────────────────────────────────────────────────────────────────────────

def relanded(text: str, *, number: int, title: str, status: str, supersedes: tuple[int, ...],
             renumbered: dict[int, int], source: str) -> str:
    """A requirement of the folder as the product keeps it: under its number, its references
    renumbered, with the status it lands with, what it supersedes, and where it came from."""
    lines = renumber(text, renumbered).splitlines()
    heading = f"# REQ-{number:04d} — {title}"
    # THE HEADING'S OWN LINE, found line by line: the corpus's pattern ends in `\s*$`, which on
    # the whole text reaches into the line after it
    at = next((i for i, line in enumerate(lines) if _TITLE_RE.fullmatch(line.rstrip())), None)
    if at is not None:
        lines[at] = heading
    else:
        lines[0:0] = [heading, ""]
    _set_field(lines, _STATUS_RE, "Status", status)
    _set_field(lines, _SUPERSEDES_RE, "Supersedes",
               ", ".join(f"REQ-{n:04d}" for n in supersedes) or "—")
    _set_field(lines, re.compile(r"^\s*[-*]\s*\**Source:?\**\s*:?\s*(?P<value>.*?)\s*$",
                                 re.IGNORECASE), "Source", source)
    return "\n".join(lines) + ("\n" if text.endswith("\n") or not text else "")


def _set_field(lines: list[str], pattern: re.Pattern[str], label: str, value: str) -> None:
    """The header's `- **label:** value`, replaced where the corpus's reader finds it, or added
    under the header's last field — never in the requirement's text below its first section."""
    end = next((i for i, line in enumerate(lines) if _FIRST_SECTION_RE.match(line)), len(lines))
    at = next((i for i in range(end) if pattern.match(lines[i])), None)
    line = f"- **{label}:** {value}"
    if at is not None:
        lines[at] = line
        return
    fields = [i for i in range(end) if re.match(r"^\s*[-*]\s*\**[A-Za-z][\w ]*:", lines[i])]
    if fields:
        lines.insert(fields[-1] + 1, line)
        return
    heading = next((i for i in range(end) if lines[i].startswith("# ")), -1)
    at = heading + 1
    block = ["", line]
    if at >= len(lines) or lines[at].strip():
        block.append("")
    lines[at:at] = block


@dataclass
class Landed:
    """What `land` wrote into a checkout: the paths to commit, and — when it could not write all
    of it — why, as a key of `voice.import_said` (nothing is committed then)."""

    paths: list[str] = field(default_factory=list)
    failed: str = ""
    record: dict = field(default_factory=dict)


def land(the_plan: Plan, brought: Brought, *, root: Path, requirements_dir: str, by: str,
         at: str, language: str | None = None) -> Landed:
    """Write `the_plan` into the checkout at `root` — every file it lands, the old side of every
    revision, the rows that join, and the record. Writes nothing it did not plan; a requirement it
    must mark replaced and cannot fails the whole of it (half a supersession is the two-live-
    versions state, committed on purpose)."""
    from openfactory.policy.context_writes import import_record
    from openfactory.product.authoring import _mark_superseded, add_decision_row, fact_file

    folder = requirements_dir.strip("/") or "requirements"
    done = Landed()
    origin = the_plan.origin
    by_source = {r.number: r for r in brought.requirements}
    minted = {r.number for r in the_plan.requirements if r.kind in (NEW, REVISION, HISTORY)}
    facts = {f.term: f for f in brought.facts}
    try:
        # EVERY FILE THE IMPORT MINTS FIRST, so a revision's own `Supersedes:` names files that
        # are there when the old side of it is marked
        for row in the_plan.requirements:
            source = by_source[row.source]
            line = (f"imported from {origin} (import {the_plan.id}), where it was "
                    f"REQ-{row.source:04d}")
            if row.kind in (NEW, REVISION, HISTORY, BESIDE):
                text = relanded(source.body, number=row.number, title=row.title or row.slug,
                                status=row.status if row.kind != BESIDE else PROPOSED,
                                supersedes=row.replaces if row.kind != BESIDE else (),
                                renumbered=the_plan.renumbered, source=line)
                _write(root, row.path, text.encode("utf-8"))
                done.paths.append(row.path)
        for row in the_plan.requirements:
            if row.kind == REVISION:
                # THE OLD SIDE, THROUGH THE WRITER THAT DOES IT TODAY — only the product's own
                # requirements this text replaces; the ones the folder retired itself landed
                # with their status already
                retired, failed = _mark_superseded(
                    root, folder, [n for n in row.replaces if n not in minted], by=row.number)
                if failed:
                    done.failed = "supersede_failed"
                    return done
                done.paths += retired
            elif row.kind == SAME and row.rows:
                twin = root / row.path
                text = twin.read_text(encoding="utf-8")
                for day, decided, who in _joining(by_source[row.source],
                                                  _as_requirement(twin, text)):
                    text, _outcome = add_decision_row(text, day=day, decision=decided, who=who,
                                                      where=f"import {the_plan.id}",
                                                      language=language)
                _write(root, row.path, text.encode("utf-8"))
                done.paths.append(row.path)
        for placed in the_plan.facts:
            if placed.kind != NEW:
                continue
            fact = _landed_fact(facts[placed.name], the_plan.id, origin)
            _, text = fact_file(fact, said_by=fact.source, language=language)
            _write(root, placed.path, text.encode("utf-8"))
            done.paths.append(placed.path)
        for placed in the_plan.documents:
            if placed.kind in (NEW, BESIDE):
                _write(root, placed.path, brought.documents[placed.name])
                done.paths.append(placed.path)
        done.record = {"version": 1, **the_plan.as_dict(), "brought": brought.name, "by": by,
                       "landed_at": at, "token": the_plan.token, "landed": list(done.paths)}
        record = f"{import_record(the_plan.id)}{RECORD_FILE}"
        _write(root, record,
               (json.dumps(done.record, indent=2, ensure_ascii=False) + "\n").encode())
        done.paths.append(record)
    except _Outside as exc:
        log.error("OPENFACTORY_PRODUCT_IMPORT_OUTSIDE path=%s — a file the import would write "
                  "is a link, or under one; nothing was committed", exc)
        done.failed = "outside"
    return done


class _Outside(OSError):
    """A path the import would write that is a link, or reaches out of the checkout through one."""


def _as_requirement(path: Path, text: str) -> Requirement:
    from openfactory.product.corpus import parse_requirement

    req, _ = parse_requirement(path, text)
    return req if req is not None else Requirement(number=0, slug="", path=path.name, body=text)


def _write(root: Path, rel: str, data: bytes) -> None:
    """`data` at `rel` in the checkout — NEVER THROUGH A LINK. A context repository may hold a
    committed link, and writing through one would put a file from outside wherever it points;
    the folder the file goes in must resolve inside the checkout, and the file itself must not
    be a link (`O_NOFOLLOW`)."""
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.parent.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise _Outside(rel)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(target, flags, 0o644), "wb") as handle:
        handle.write(data)


def record_of(root: Path, ident: str) -> dict | None:
    """The record of the import `ident` in the checkout at `root`, or None when there is none."""
    from openfactory.policy.context_writes import import_record

    where = import_record(ident)
    path = root / f"{where}{RECORD_FILE}" if where else None
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("the record of import %s could not be read", ident, exc_info=True)
        return None
    return data if isinstance(data, dict) else None


# ── said ─────────────────────────────────────────────────────────────────────────────────────────

def lines(the_plan: Plan, *, language: str | None = None) -> list[str]:
    """The plan as the lines a person reads before their yes — one per requirement, fact,
    document and file left out, each composed from `voice.import_said`."""
    from openfactory.product.voice import import_said

    minted = {r.number for r in the_plan.requirements if r.kind in (NEW, REVISION, HISTORY)}
    out: list[str] = []
    for r in the_plan.requirements:
        values = {"number": f"{r.number:04d}", "title": r.title or r.slug,
                  "source": f"{r.source:04d}", "status": r.status, "rows": "",
                  "replaces": ", ".join(f"REQ-{n:04d}" for n in r.replaces if n not in minted)}
        if r.kind == SAME and r.rows:
            values["rows"] = import_said("rows", language=language, rows=r.rows)
        out.append(import_said(r.kind, language=language, **values))
    for f in the_plan.facts:
        out.append(import_said("fact_new" if f.kind == NEW else "fact_known", language=language,
                               name=f.name, path=f.path))
    for d in the_plan.documents:
        out.append(import_said(f"document_{d.kind}", language=language, name=d.name,
                               path=d.path, beside=d.beside))
    for path, why in the_plan.left_out:
        reason = why.split(":", 1)
        said = (import_said(reason[0], language=language, rows=reason[1] if len(reason) > 1
                            else "")
                if reason[0] in _REASONS else why)
        out.append(import_said("left_out", language=language, name=path, why=said))
    return out


#: The reasons a file is left out that `voice.import_said` says — every one `_brought` and `plan`
#: can record.
_REASONS = frozenset({"hidden", "a_link", "not_a_file", "too_large_a_file", "outside_the_folder",
                      "reserved", "not_a_requirement", "the_template", "inside_the_requirements",
                      "no_fact", "a_retired_fact", "unreadable_manifest", "no_register"})


def said(the_plan: Plan, *, landed: bool, language: str | None = None) -> str:
    """The plan, or what landed, as a person reads it: a headline, the counts, every line."""
    from openfactory.product.voice import import_said

    head = import_said("landed" if landed else "plan", language=language,
                       origin=the_plan.origin)
    counted = import_said("counted", language=language, **{k: the_plan.count(k)
                                                             for k in (NEW, REVISION, BESIDE,
                                                                       SAME)})
    body = "\n".join(f"- {line}" for line in lines(the_plan, language=language))
    tail = "" if landed else "\n\n" + import_said("say_yes", language=language,
                                                   token=the_plan.token)
    return f"{head} {counted}\n\n{body}{tail}".rstrip()


# ── the clone, the commit, the one push ─────────────────────────────────────────────────────────

@dataclass
class Imported(WriteResult):
    """What one import did — a `WriteResult`, and the plan it acted on. `moved` is a yes that came
    back to a product that changed since the plan it was given; `plan` is then the plan as it
    stands now. `landed` is every path the one commit wrote."""

    moved: bool = False
    plan: Plan | None = None
    landed: list[str] = field(default_factory=list)


#: What an import may stage: requirements, facts, and the folder documents land under. Its record
#: is admitted by the policy alone (`context_writes.outside_an_import`), by the import's own id.
def allowed(requirements_dir: str) -> list[str]:
    from openfactory.policy.context_writes import FACTS

    return [requirements_dir.strip("/") or "requirements", *FACTS, f"{IMPORTED_FOLDER}/"]


def first_number(root: Path, requirements_dir: str, branches: list[tuple[int, str]]) -> int:
    """The first number this import mints: past everything the checkout ever numbered and every
    proposal branch not yet landed — `authoring.first_free`, the one formula."""
    from openfactory.product.authoring import _next_in, first_free

    return first_free(_next_in(root, requirements_dir), [n for n, _ in branches])


def land_import(*, docs_repo: str, clone_url: str, brought: Brought, forge,
                requirements_dir: str = "requirements", base: str = "main", by: str = "",
                origin: str = "", token: str = "", language: str | None = None,
                today: str | None = None) -> Imported:
    """Plan `brought` against the base as it is NOW, and land it: ONE commit, pushed ONCE.

    Runs under the product's semaphore (`ProductModule.import_requirements`), so the clone is the
    latest base and the numbers it mints nobody else is minting. `token` is the plan a person said
    yes to: when the plan made here is another one, nothing is written and the new plan is handed
    back. A push the context repository refuses is said, and never retried — the next attempt is a
    new plan from a new base, and its person's new yes."""
    import shutil
    from datetime import UTC, datetime

    from openfactory.policy.context_writes import import_record
    from openfactory.product.authoring import (
        _git,
        _requirement_branches,
        _scrub,
        _staged_outside,
        _w,
    )
    from openfactory.product.voice import import_said

    now = datetime.now(UTC)
    day = today or now.date().isoformat()
    ident = import_id(brought, day)
    origin = origin or brought.name
    branches = _requirement_branches(forge, docs_repo)
    if branches is None:
        log.error("OPENFACTORY_PRODUCT_BRANCHES_UNREADABLE repo=%s — the proposal branches could "
                  "not be listed, so nothing was minted and the import %s wrote nothing",
                  docs_repo, ident)
        return Imported(ok=False, detail=_w(language, "branches_unreadable"))
    tmp = Path(tempfile.mkdtemp(prefix="openfactory-import-"))
    try:
        rc, out = _git(["clone", "--no-local", "--depth", "1", "--branch", base, clone_url,
                        str(tmp)])
        if rc != 0:
            return Imported(ok=False, detail=f"could not clone {docs_repo}: {_scrub(out)[-200:]}")
        record = f"{import_record(ident)}{RECORD_FILE}"
        if record_of(tmp, ident) is not None:
            return Imported(ok=True, existed=True, ref=record,
                            detail=import_said("already", language=language, origin=origin,
                                               id=ident))
        the_plan = plan(brought, root=tmp, requirements_dir=requirements_dir,
                        first=first_number(tmp, requirements_dir, branches), ident=ident,
                        origin=origin)
        if token and token != the_plan.token:
            return Imported(ok=False, moved=True, plan=the_plan,
                            detail=import_said("moved", language=language) + "\n\n"
                            + said(the_plan, landed=False, language=language))
        if not the_plan.lands_anything:
            return Imported(ok=True, existed=True, plan=the_plan,
                            detail=import_said("nothing_new", language=language, origin=origin))
        done = land(the_plan, brought, root=tmp, requirements_dir=requirements_dir, by=by,
                    at=now.isoformat(timespec="seconds"), language=language)
        if done.failed:
            return Imported(ok=False, plan=the_plan,
                            detail=import_said(done.failed, language=language))
        for path in done.paths:
            _git(["add", "--", path], cwd=tmp)
        # AN IMPORT LANDS WHAT IT EXISTS TO LAND (#265 §6.4): requirements, facts, the documents'
        # folder, and its own record — asked of git after the add, so nothing reaches the base
        # by a route this function did not mean
        staged = _staged_outside(tmp, allowed(requirements_dir), import_id=ident)
        if staged:
            log.error("OPENFACTORY_PRODUCT_WRITE_OUTSIDE repo=%s writer=land_import staged=%s — "
                      "nothing was committed", docs_repo, staged)
            return Imported(ok=False, plan=the_plan,
                            detail=_w(language, "staged_outside", staged=", ".join(staged[:3])))
        message = import_said(
            "commit", language=language, id=ident, origin=origin, by=by or "—",
            counted=import_said("counted", language=language,
                                **{k: the_plan.count(k) for k in (NEW, REVISION, BESIDE, SAME)}))
        rc, out = _git(["commit", "-m", message], cwd=tmp)
        if rc != 0:
            return Imported(ok=False, plan=the_plan,
                            detail=f"nothing to commit: {_scrub(out)[-200:]}")
        rc, out = _git(["push", clone_url, f"HEAD:{base}"], cwd=tmp)
        if rc != 0:
            # SAID, NEVER RETRIED BLINDLY. Under the semaphore nothing of this product moved the
            # base; a refusal here is the repository's own (protected, or moved by somebody
            # outside the factory), and pushing again would land a plan made against a base that
            # is no longer there
            log.error("OPENFACTORY_PRODUCT_IMPORT_PUSH_REFUSED repo=%s base=%s import=%s — %s",
                      docs_repo, base, ident, _scrub(out)[-200:])
            return Imported(ok=False, plan=the_plan,
                            detail=import_said("push_refused", language=language))
        log.info("OPENFACTORY_PRODUCT_IMPORTED repo=%s base=%s import=%s requirements=%s",
                 docs_repo, base, ident,
                 {k: the_plan.count(k) for k in REQUIREMENT_KINDS})
        return Imported(ok=True, ref=record, merged=True, plan=the_plan, landed=done.paths,
                        number=the_plan.count(NEW) + the_plan.count(REVISION),
                        detail=said(the_plan, landed=True, language=language))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


__all__ = [
    "BESIDE",
    "Imported",
    "HISTORY",
    "IMPORTED_FOLDER",
    "KNOWN",
    "MANIFEST",
    "MAX_FILES",
    "MAX_TOTAL_BYTES",
    "NEW",
    "REVISION",
    "SAME",
    "Brought",
    "Landed",
    "NotImportable",
    "Placed",
    "Plan",
    "Row",
    "import_id",
    "land",
    "land_import",
    "lines",
    "plan",
    "promise_of",
    "read",
    "record_of",
    "relanded",
    "renumber",
    "said",
]
