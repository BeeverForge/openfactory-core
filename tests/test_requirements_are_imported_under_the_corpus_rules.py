"""Requirements written elsewhere are imported into a product under its corpus's rules (#993).

A folder brought from outside — a later round of prototyping, a second phase of a specification —
lands in a product's context repository numbered after every number the corpus ever used, never
writing a promise the corpus already holds a second time, and touching nothing accepted.

EACH TEST STATES ONE FAMILY'S RULE, WITH ITS CASES READ FROM THE CODE: every status the corpus
knows (`corpus._KNOWN_STATUS`), the kinds a plan can say (`importing.REQUIREMENT_KINDS`), the
archives the reader takes (`importing._ARCHIVES`), the folders only one writer writes
(`importing._reserved`), the reasons a file is left out (`importing._REASONS`) — and both
transports, through the action layer they reach (`openfactory act`, `POST /api/act/{name}`).

WHAT IS REAL. git, the bare context repository, the corpus's and the domain's readers and
writers, the product's semaphore, the documents' pass, the product's index. What is stood in for
is the checkout's network (`clone_url_for` names the bare repository), the forge's list of proposal
branches, and the model that summarises a document.
"""

from __future__ import annotations

import getpass
import io
import json
import os
import subprocess
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from openfactory import actions
from openfactory.product import importing
from openfactory.product.authoring import add_decision_row, render_requirement, slugify
from openfactory.product.corpus import (
    _KNOWN_STATUS,
    ACCEPTED,
    DROPPED,
    OBSERVED,
    PROPOSED,
    SUPERSEDED,
    Requirement,
    decision_cells,
    load_corpus,
)
from openfactory.product.role import RequirementDraft

NAME = "lark"
DOCS = "lark/context"
ADMIN = "ana"
DAY = "2026-10-21"

#: the statuses a requirement can carry, read from the corpus — and which of them are live
STATUSES = sorted(_KNOWN_STATUS)
LIVE = sorted(s for s in STATUSES if Requirement(number=1, slug="x", path="x", status=s).is_live)


# ── requirements, folders, repositories ─────────────────────────────────────────────────────────

def _requirement(number: int, title: str, *, status: str = PROPOSED, why: str = "the client asked",
                 supersedes=(), rows=()) -> str:
    """A requirement exactly as the product's writer renders one, with `status` on its status
    line and `rows` — `(day, decision, who)` — in its register, through the register's writer."""
    text = render_requirement(RequirementDraft(title=title, why=why, must_be_true=["it holds"],
                                               supersedes=list(supersedes)), number=number)
    if status == SUPERSEDED:
        status = "superseded-by 0001"
    text = text.replace(f"- **Status:** {PROPOSED}", f"- **Status:** {status}")
    for day, decision, who in rows:
        text, _ = add_decision_row(text, day=day, decision=decision, who=who)
    return text


def _file(number: int, title: str) -> str:
    return f"requirements/{number:04d}-{slugify(title)}.md"


def _tree(root: Path, files: dict[str, str | bytes]) -> Path:
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            target.write_bytes(data)
        else:
            target.write_text(data, encoding="utf-8")
    return root


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def _bare(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    """A bare context repository whose `main` holds the product's declaration and `files`."""
    seed = _tree(tmp_path / "seed", {".openfactory/product.yaml":
                                     f"product: {NAME}\nsources: [lark/{NAME}]\n", **files})
    _git("init", "-q", "-b", "main", cwd=seed)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A", cwd=seed)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed", cwd=seed)
    bare = tmp_path / "context.git"
    _git("clone", "-q", "--bare", "--no-local", str(seed), str(bare))
    return bare


def _main(bare: Path, path: str) -> str:
    return _git("--git-dir", str(bare), "show", f"main:{path}")


def _commits(bare: Path) -> int:
    return int(_git("--git-dir", str(bare), "rev-list", "--count", "main").strip())


def _checkout(bare: Path, where: Path) -> Path:
    _git("clone", "-q", "--no-local", str(bare), str(where))
    return where


# ── the deployment ──────────────────────────────────────────────────────────────────────────────

class _Forge:
    """The forge's one answer an import needs: the proposal branches not yet landed."""

    def __init__(self) -> None:
        self.branches: list[str] | None = []

    def list_branches(self, repo="", *, prefix=""):
        return None if self.branches is None else [b for b in self.branches
                                                   if b.startswith(prefix)]


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    """One product, `lark`, registered on a deployment of its own: its context repository a real
    bare repository, `ana` and the shell's own login on its `admins`."""
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.product import module as product_module
    from openfactory.product.config import ProductLink
    from openfactory.product.documents import ingest as ingest_module
    from openfactory.product.domain import load_domain
    from openfactory.product.loader import ProductContext
    from openfactory.registry import ProjectRegistry
    from tests.documents_bed import StubReader

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENFACTORY_LOG_DIR", str(tmp_path / "journal"))
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_BOT_NAME", "The Factory")
    monkeypatch.setenv("OPENFACTORY_BOT_EMAIL", "factory@example.invalid")
    for env in ("OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_PRODUCT_TOKEN"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("OPENFACTORY_PRODUCT_TOKENS", f"ana-token:{ADMIN}:Ana,bia-token:bia:Bia")

    state = SimpleNamespace(bare=None, forge=_Forge(), tmp=tmp_path, reads=0)
    project = Project(name=NAME, repo_path=str(tmp_path / NAME),
                      tracker=ProviderRef(kind="github", repo=f"lark/{NAME}"),
                      forge=ProviderRef(kind="github", repo=f"lark/{NAME}"),
                      product=ProductConfig(docs_repo=DOCS, admins=[ADMIN, getpass.getuser()]))
    ProjectRegistry().add(project)

    def _context(project, *, token=None, **_kw):
        """The product's checkout of its context repository, read as the loader reads one: a
        fresh copy of `main` every time it is asked."""
        state.reads += 1
        where = _checkout(state.bare, tmp_path / f"read-{state.reads}")
        return ProductContext(link=ProductLink(active=True, docs_repo=DOCS, kind="ok",
                                               reason="ok"),
                              corpus=load_corpus(where / "requirements"),
                              domain=load_domain(where / "domain"), docs_path=str(where),
                              docs_commit=_git("rev-parse", "HEAD", cwd=where).strip(),
                              requirements_dir="requirements")

    monkeypatch.setattr(product_module, "load_product_context", _context)
    monkeypatch.setattr("openfactory.adapters.forge.registry.clone_url_for",
                        lambda project, repo="", *, token=None: str(state.bare))
    monkeypatch.setattr(product_module.ProductModule, "_forge", lambda self: state.forge)
    monkeypatch.setattr(ingest_module, "ModelReader", lambda **_kw: StubReader())
    state.project = project
    return state


def _act(**params) -> actions.Outcome:
    import asyncio

    by = actions.Actor(id=ADMIN, display="Ana", via="cli", admin=True)
    return asyncio.run(actions.perform("product_import", by=by, project=NAME, **params))


def _cli(*params: str):
    from typer.testing import CliRunner

    from openfactory.cli import app

    argv = ["act", "product_import", "--param", f"project={NAME}"]
    for p in params:
        argv += ["--param", p]
    return CliRunner().invoke(app, argv)


# ── 1. the number: after every number ever used, and every proposal on its way ──────────────────

@pytest.mark.parametrize("highest", STATUSES)
@pytest.mark.parametrize("gap", [False, True], ids=["dense", "with a gap"])
@pytest.mark.parametrize("unlanded", [(), (17,)], ids=["no branch", "an unlanded branch"])
def test_a_requirement_is_minted_after_the_highest_number_ever_used(tmp_path, highest, gap,
                                                                    unlanded):
    """Whatever the highest requirement's status — a superseded or dropped one included — and
    whatever the corpus skipped, the first number minted is one past the highest the corpus ever
    used, or past a proposal branch still on its way when that is higher."""
    top = 9 if gap else 3
    root = _tree(tmp_path / "product", {
        _file(1, "Login"): _requirement(1, "Login"),
        _file(2, "Export"): _requirement(2, "Export"),
        _file(top, "Retired thing"): _requirement(top, "Retired thing", status=highest)})
    folder = _tree(tmp_path / "folder", {_file(1, "Totals"): _requirement(1, "Totals"),
                                         _file(2, "Invoices"): _requirement(2, "Invoices")})
    brought = importing.read(folder)
    branches = [(n, "rival") for n in unlanded]

    the_plan = importing.plan(brought, root=root, requirements_dir="requirements",
                              first=importing.first_number(root, "requirements", branches),
                              ident=importing.import_id(brought, DAY), origin="round two")

    first = max([top, *unlanded]) + 1
    assert [(r.kind, r.number) for r in the_plan.requirements] == [
        (importing.NEW, first), (importing.NEW, first + 1)], the_plan.as_dict()


def test_the_import_and_a_proposal_mint_with_one_formula():
    """`first_free` is the one numbering: the proposal's re-mint and the import's first number
    both answer from it, so neither can forget the branches the other remembers."""
    import inspect

    from openfactory.product import authoring

    assert "first_free(fresh, rivals)" in inspect.getsource(authoring.propose_requirement)
    assert "first_free(" in inspect.getsource(importing.first_number)
    assert authoring.first_free(4, [9]) == 10 and authoring.first_free(12, [9]) == 12


# ── 2. the same slug is the same promise ────────────────────────────────────────────────────────

def _expected(status: str, same_text: bool) -> str:
    """The module's table, as a rule over the twin's status — read from the corpus's own words."""
    twin = Requirement(number=1, slug="x", path="x", status=status)
    if not twin.is_live:
        return importing.NEW
    if same_text:
        return importing.SAME
    return importing.BESIDE if twin.is_promise else importing.REVISION


@pytest.mark.parametrize("status", STATUSES)
@pytest.mark.parametrize("same_text", [True, False], ids=["word for word", "a new text"])
def test_the_same_slug_is_the_same_promise(tmp_path, status, same_text):
    """Against the product's requirement carrying the same slug, in every status the corpus knows:
    the same text is nothing new, a new text revises what nobody agreed and is kept beside what
    was agreed — and a twin that no longer stands is no twin at all."""
    successor = {_file(9, "What replaced it"): _requirement(9, "What replaced it")} \
        if status == SUPERSEDED else {}
    twin = _requirement(4, "Monthly close", why="close the month",
                        status="superseded-by 0009" if status == SUPERSEDED else status)
    root = _tree(tmp_path / "product", {_file(4, "Monthly close"): twin, **successor})
    folder = _tree(tmp_path / "folder", {_file(1, "Monthly close"): _requirement(
        1, "Monthly close", why="close the month" if same_text else "close it every week")})
    brought = importing.read(folder)
    ident = importing.import_id(brought, DAY)
    the_plan = importing.plan(brought, root=root, requirements_dir="requirements",
                              first=importing.first_number(root, "requirements", []), ident=ident,
                              origin="round two")
    before = {p.name for p in (root / "requirements").iterdir()}

    done = importing.land(the_plan, brought, root=root, requirements_dir="requirements",
                          by=ADMIN, at=DAY)

    kind = the_plan.requirements[0].kind
    assert kind == _expected(status, same_text), the_plan.as_dict()
    assert not done.failed
    after = load_corpus(root / "requirements")
    assert not after.errors, [f.message for f in after.errors]
    old = (root / _file(4, "Monthly close")).read_text()
    if kind in (importing.SAME, importing.BESIDE, importing.NEW):
        assert old == twin, "the product's own requirement was changed"
    if kind == importing.SAME:
        assert {p.name for p in (root / "requirements").iterdir()} == before
    if kind == importing.REVISION:
        landed = after.by_number(the_plan.requirements[0].number)
        assert landed.supersedes == [4] and after.by_number(4).superseded_by == landed.number
    if kind == importing.BESIDE:
        kept = root / the_plan.requirements[0].path
        assert kept.is_file() and "close it every week" in kept.read_text()
        assert {p.name for p in (root / "requirements").iterdir()} == before


# ── 3. the decisions of the same promise join its register, by day and text ────────────────────

def test_the_same_promise_brings_only_the_decisions_its_register_lacks(tmp_path):
    """The register's rows are compared by day and text: who recorded it does not make a decision
    twice, and the same decision on another day is another decision."""
    held = [("2026-09-01", "export in CSV", "ana — the room")]
    brought_rows = [("2026-09-01", "export in CSV", "bia — elsewhere"),     # the same: day, text
                    ("2026-09-01", "totals per branch", "bia — elsewhere"),  # another text
                    ("2026-09-02", "export in CSV", "bia — elsewhere")]      # another day
    root = _tree(tmp_path / "product", {_file(4, "Monthly close"): _requirement(
        4, "Monthly close", status=ACCEPTED, rows=held)})
    folder = _tree(tmp_path / "folder", {_file(1, "Monthly close"): _requirement(
        1, "Monthly close", rows=brought_rows)})
    brought = importing.read(folder)
    the_plan = importing.plan(brought, root=root, requirements_dir="requirements", first=5,
                              ident=importing.import_id(brought, DAY), origin="round two")

    importing.land(the_plan, brought, root=root, requirements_dir="requirements", by=ADMIN,
                   at=DAY)

    rows = [(d, t) for d, t, _ in decision_cells((root / _file(4, "Monthly close")).read_text())]
    assert rows == [("2026-09-01", "export in CSV"), ("2026-09-01", "totals per branch"),
                    ("2026-09-02", "export in CSV")], rows
    again = importing.plan(brought, root=root, requirements_dir="requirements", first=5,
                           ident="x", origin="round two")
    assert again.requirements[0].rows == 0 and not again.lands_anything


def test_a_register_is_never_invented_for_the_rows_that_would_join(tmp_path):
    bare_text = _requirement(4, "Monthly close").split("## Decisions taken during execution")[0]
    root = _tree(tmp_path / "product", {_file(4, "Monthly close"): bare_text})
    folder = _tree(tmp_path / "folder", {_file(1, "Monthly close"): _requirement(
        1, "Monthly close", rows=[("2026-09-01", "export in CSV", "bia")])})
    brought = importing.read(folder)
    the_plan = importing.plan(brought, root=root, requirements_dir="requirements", first=5,
                              ident="x", origin="round two")

    assert the_plan.requirements[0].kind == importing.SAME
    assert the_plan.requirements[0].rows == 0
    assert (f"requirements/{Path(_file(4, 'Monthly close')).name}", "no_register:1") in \
        the_plan.left_out


# ── 4. references are renumbered with what they name ────────────────────────────────────────────

def test_references_between_imported_requirements_are_renumbered_with_them(tmp_path):
    """Every `REQ-NNNN` of the folder's numbering, its `Supersedes:` and its `superseded-by`, in
    the product's: the folder's own retired requirement lands as history so its successor's claim
    still holds, and a reference to a promise the product already has names the product's
    number."""
    root = _tree(tmp_path / "product", {_file(n, t): _requirement(n, t) for n, t in (
        (1, "Login"), (2, "Monthly close"), (3, "Export"))})
    folder = _tree(tmp_path / "folder", {
        _file(1, "Old totals"): _requirement(1, "Old totals", status="superseded-by 0002"),
        _file(2, "Totals"): _requirement(2, "Totals", supersedes=[1],
                                         why="totals, as REQ-0003 and REQ-0004 need them"),
        _file(3, "Invoices"): _requirement(3, "Invoices", why="after REQ-0002"),
        _file(4, "Monthly close"): _requirement(4, "Monthly close")})
    brought = importing.read(folder)
    the_plan = importing.plan(brought, root=root, requirements_dir="requirements",
                              first=importing.first_number(root, "requirements", []), ident="x",
                              origin="round two")

    importing.land(the_plan, brought, root=root, requirements_dir="requirements", by=ADMIN,
                   at=DAY)

    assert the_plan.renumbered == {1: 4, 2: 5, 3: 6, 4: 2}, the_plan.renumbered
    after = load_corpus(root / "requirements")
    assert not after.errors, [f.message for f in after.errors]
    assert after.by_number(4).superseded_by == 5 and after.by_number(5).supersedes == [4]
    assert "as REQ-0006 and REQ-0002 need them" in after.by_number(5).body
    assert "after REQ-0005" in after.by_number(6).body
    # and the same folder brought again is nothing new — its history included
    again = importing.plan(brought, root=root, requirements_dir="requirements",
                           first=importing.first_number(root, "requirements", []), ident="y",
                           origin="round two")
    assert {r.kind for r in again.requirements} == {importing.SAME}, again.as_dict()
    assert not again.lands_anything


# ── 5. an import never lands a promise ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", STATUSES)
def test_an_import_never_lands_a_promise(tmp_path, status):
    """Whatever status the folder's file claims, what lands is not a promise: a live requirement
    lands `proposed`, a reading of code `observed`, and one the folder retired keeps its status
    as history."""
    root = _tree(tmp_path / "product", {_file(1, "Login"): _requirement(1, "Login")})
    files = {_file(2, "Totals"): _requirement(2, "Totals", status=status)}
    if status == SUPERSEDED:
        files[_file(1, "New totals")] = _requirement(1, "New totals", supersedes=[2])
        files[_file(2, "Totals")] = _requirement(2, "Totals", status="superseded-by 0001")
    brought = importing.read(_tree(tmp_path / "folder", files))
    the_plan = importing.plan(brought, root=root, requirements_dir="requirements",
                              first=importing.first_number(root, "requirements", []), ident="x",
                              origin="round two")

    importing.land(the_plan, brought, root=root, requirements_dir="requirements", by=ADMIN,
                   at=DAY)

    after = load_corpus(root / "requirements")
    landed = {r.number: r for r in after.requirements if r.number != 1}
    assert landed and not [r for r in landed.values() if r.is_promise], landed
    mine = next(r for r in landed.values() if r.slug == "totals")
    expected = {OBSERVED: OBSERVED, DROPPED: DROPPED, SUPERSEDED: SUPERSEDED}.get(status,
                                                                                  PROPOSED)
    assert mine.status == expected


# ── 6. a fact is never rewritten ────────────────────────────────────────────────────────────────

def test_a_known_term_is_never_rewritten_and_a_new_one_lands_learned_with_its_source(tmp_path):
    from openfactory.product.domain import LEARNED, load_domain

    held = ("### Ledger\n\n- **Status:** aprendido\n- **Source:** ana\n- **Date:** 2026-01-01\n\n"
            "the book of accounts\n")
    root = _tree(tmp_path / "product", {"domain/2026-01-01-ledger.md": held})
    folder = _tree(tmp_path / "folder", {"domain/terms.md": (
        "### LEDGER\n\n- **Status:** confirmado\n- **Source:** bia\n\nsomething else\n\n"
        "### Close\n\n- **Status:** confirmado\n- **Source:** bia\n- **Date:** 2026-09-01\n\n"
        "the month is closed\n")})
    brought = importing.read(folder)
    the_plan = importing.plan(brought, root=root, requirements_dir="requirements", first=1,
                              ident=f"{DAY}-0123456789", origin="round two")

    importing.land(the_plan, brought, root=root, requirements_dir="requirements", by=ADMIN,
                   at=DAY)

    assert [(f.kind, f.name) for f in the_plan.facts] == [(importing.KNOWN, "LEDGER"),
                                                          (importing.NEW, "Close")]
    assert (root / "domain/2026-01-01-ledger.md").read_text() == held
    domain = load_domain(root / "domain")
    assert not domain.findings, domain.findings
    close = domain.get("close")
    assert close.status == LEARNED and close.source == "bia" and close.learned_on == "2026-09-01"


def test_a_facts_date_that_is_not_a_day_never_becomes_its_file_name(tmp_path):
    folder = _tree(tmp_path / "folder", {"domain/terms.md": (
        "### Close\n\n- **Source:** bia\n- **Date:** early September\n\nthe month is closed\n")})
    brought = importing.read(folder)

    the_plan = importing.plan(brought, root=tmp_path / "product", requirements_dir="requirements",
                              first=1, ident=f"{DAY}-0123456789", origin="round two")

    assert [f.path for f in the_plan.facts] == [f"domain/{DAY}-close.md"]


# ── 7. a document never overwrites one that exists ──────────────────────────────────────────────

@pytest.mark.parametrize("already,kind", [
    ("nothing", importing.NEW), ("the same bytes", importing.SAME),
    ("other bytes", importing.BESIDE), ("a link", importing.BESIDE)])
def test_a_document_never_overwrites_one_that_exists(tmp_path, already, kind):
    outside = tmp_path / "outside.txt"
    outside.write_text("the server's own file\n")
    root = tmp_path / "product"
    (root / "imported/design").mkdir(parents=True)
    held = root / "imported/design/flow.md"
    if already == "the same bytes":
        held.write_text("the flow\n")
    elif already == "other bytes":
        held.write_text("an older flow\n")
    elif already == "a link":
        held.symlink_to(outside)
    folder = _tree(tmp_path / "folder", {"design/flow.md": "the flow\n"})
    brought = importing.read(folder)
    the_plan = importing.plan(brought, root=root, requirements_dir="requirements", first=1,
                              ident=f"{DAY}-0123456789", origin="round two")

    done = importing.land(the_plan, brought, root=root, requirements_dir="requirements",
                          by=ADMIN, at=DAY)

    assert [d.kind for d in the_plan.documents] == [kind]
    assert not done.failed
    assert outside.read_text() == "the server's own file\n", "written through a link"
    if already == "other bytes":
        assert held.read_text() == "an older flow\n"
    if kind == importing.BESIDE:
        beside = root / the_plan.documents[0].path
        assert beside.read_text() == "the flow\n" and beside != held


# ── 8. what a folder brings, and what it never lands ────────────────────────────────────────────

def _left_out_cases() -> list[tuple[str, str]]:
    reserved = [(f"{folder}/x.md", "reserved") for folder in importing._reserved()]
    return [(".git/config", "hidden"), (".openfactory/product.yaml", "hidden"),
            ("requirements/README.md", "not_a_requirement"),
            ("requirements/0000-template.md", "the_template"),
            ("requirements/old/0001-x.md", "inside_the_requirements"),
            ("domain/empty.md", "no_fact"), *reserved]


def test_every_reason_a_file_is_left_out_is_one_the_plan_can_say():
    cases = {why for _path, why in _left_out_cases()}
    assert cases | {"a_link", "not_a_file", "too_large_a_file", "outside_the_folder",
                    "a_retired_fact", "unreadable_manifest", "no_register"} == importing._REASONS


@pytest.mark.parametrize("path,why", _left_out_cases())
def test_a_file_only_another_writer_writes_never_lands(tmp_path, path, why):
    folder = _tree(tmp_path / "folder", {path: "### nothing here\n" if why != "no_fact" else
                                         "no heading\n",
                                         "design/flow.md": "the flow\n"})
    brought = importing.read(folder)

    left = dict(brought.left_out)
    shown = path if why != "hidden" else next(p for p in left if path.startswith(p.rstrip("/")))
    assert left.get(shown) == why, brought.left_out
    assert path not in brought.documents and list(brought.documents) == ["design/flow.md"]


def test_a_link_in_the_folder_is_left_out_and_never_followed(tmp_path):
    secret = tmp_path / "secret.env"
    secret.write_text("KEY=1\n")
    folder = _tree(tmp_path / "folder", {"design/flow.md": "the flow\n"})
    (folder / "design/key.env").symlink_to(secret)
    (folder / "linked").symlink_to(tmp_path)

    brought = importing.read(folder)

    assert ("design/key.env", "a_link") in brought.left_out
    assert ("linked", "a_link") in brought.left_out
    assert list(brought.documents) == ["design/flow.md"]


def _archive(folder: Path, kind: str, tmp_path: Path) -> Path:
    out = tmp_path / f"bundle{kind}"
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    if kind == ".zip":
        with zipfile.ZipFile(out, "w") as z:
            for p in files:
                z.write(p, p.relative_to(folder).as_posix())
    else:
        mode = {".tar": "w", ".tar.gz": "w:gz", ".tgz": "w:gz"}[kind]
        with tarfile.open(out, mode) as t:
            for p in files:
                t.add(p, p.relative_to(folder).as_posix())
    return out


@pytest.mark.parametrize("kind", importing._ARCHIVES)
def test_an_archive_brings_exactly_what_its_folder_brings(tmp_path, kind):
    folder = _tree(tmp_path / "folder", {_file(1, "Totals"): _requirement(1, "Totals"),
                                         "domain/terms.md": "### Close\n\n- **Source:** bia\n\nx\n",
                                         "design/flow.png": b"\x89PNG..."})
    loose, packed = importing.read(folder), importing.read(_archive(folder, kind, tmp_path))

    assert packed.digest == loose.digest
    assert [r.number for r in packed.requirements] == [1]
    assert [f.term for f in packed.facts] == ["Close"]
    assert packed.documents == loose.documents


def test_an_archive_member_that_leads_out_or_links_is_never_read(tmp_path):
    out = tmp_path / "evil.tar"
    with tarfile.open(out, "w") as t:
        for name, data in (("../escape.md", b"x"), ("/etc/abs.md", b"x"), ("ok/fine.md", b"ok")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("ok/key")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        t.addfile(link)

    brought = importing.read(out)

    assert list(brought.documents) == ["ok/fine.md"]
    assert {why for _p, why in brought.left_out} == {"outside_the_folder", "a_link"}


def test_a_folder_past_its_bounds_is_refused_before_anything_is_planned(tmp_path, monkeypatch):
    folder = _tree(tmp_path / "folder", {f"design/{n}.md": "x" * 10 for n in range(5)})
    monkeypatch.setattr(importing, "MAX_FILES", 3)
    with pytest.raises(importing.NotImportable) as files:
        importing.read(folder)
    monkeypatch.setattr(importing, "MAX_FILES", 100)
    monkeypatch.setattr(importing, "MAX_TOTAL_BYTES", 20)
    with pytest.raises(importing.NotImportable) as size:
        importing.read(folder)

    assert files.value.reason == "too_many" and size.value.reason == "too_large"


def test_a_folder_whose_requirements_contradict_themselves_is_not_planned(deployment):
    deployment.bare = _bare(deployment.tmp, {})
    folder = _tree(deployment.tmp / "folder", {
        _file(1, "Totals"): _requirement(1, "Totals"),
        "requirements/0002-totals.md": _requirement(2, "Totals", why="another")})

    said = _act(source=str(folder), yes=True)

    assert not said.ok and "contradict themselves" in said.message, said
    assert _commits(deployment.bare) == 1


# ── 9. one commit, under the semaphore, pushed once ─────────────────────────────────────────────

def _a_round(tmp: Path) -> Path:
    return _tree(tmp / "round-two", {
        _file(1, "Totals"): _requirement(1, "Totals", why="see REQ-0002"),
        _file(2, "Monthly close"): _requirement(2, "Monthly close", why="weekly now"),
        "domain/terms.md": "### Close\n\n- **Source:** bia\n\nthe month is closed\n",
        "design/flow.md": "# The flow\n\nThe monthly close, as the person saw it.\n",
        importing.MANIFEST: "origin: the second prototyping round\norder: [2, 1]\n"
                            "design: design/flow.md\n"})


def _seeded(deployment) -> None:
    deployment.bare = _bare(deployment.tmp, {
        _file(1, "Login"): _requirement(1, "Login"),
        _file(2, "Monthly close"): _requirement(2, "Monthly close", why="monthly")})


def test_the_cli_shows_the_plan_and_lands_it_on_yes_in_one_commit(deployment):
    """The command line, as a person runs it: the plan and its token, nothing written; then the
    yes with that token, and ONE commit on the context repository's base."""
    _seeded(deployment)
    folder = _a_round(deployment.tmp)

    shown = _cli(f"source={folder}")
    assert shown.exit_code == 1 and "nothing is written before your yes" in shown.output
    assert _commits(deployment.bare) == 1
    token = shown.output.rsplit("token ", 1)[1].split()[0]

    landed = _cli(f"source={folder}", "yes=true", f"token={token}")

    assert landed.exit_code == 0, landed.output
    assert _commits(deployment.bare) == 2
    corpus = load_corpus(_checkout(deployment.bare, deployment.tmp / "after") / "requirements")
    assert not corpus.errors, [f.message for f in corpus.errors]
    assert [(r.number, r.slug, r.status) for r in corpus.requirements] == [
        (1, "login", PROPOSED), (2, "monthly-close", "superseded"), (3, "totals", PROPOSED),
        (4, "monthly-close", PROPOSED)]
    assert "see REQ-0004" in corpus.by_number(3).body


def test_the_panel_names_only_a_folder_in_the_products_inbox(deployment):
    """The API, as any client reaches it: an absolute path, a path that climbs out, a link out of
    the inbox — each refused before anything is read; the inbox's own folder planned and landed."""
    from fastapi.testclient import TestClient

    from openfactory.api.app import app

    _seeded(deployment)
    inbox = importing.inbox(deployment.project)
    inbox.mkdir(parents=True)
    folder = _a_round(inbox)
    (inbox / "out").symlink_to(deployment.tmp)
    client = TestClient(app)
    as_ana = {"authorization": "Bearer ana-token"}

    for source in (str(folder), "../journal", "out/round-two"):
        refused = client.post("/api/act/product_import", headers=as_ana,
                              json={"params": {"project": NAME, "source": source}})
        assert refused.status_code == 403, (source, refused.text)
        assert refused.json()["data"]["reason"] == actions.DENIED
    shown = client.post("/api/act/product_import", headers=as_ana,
                        json={"params": {"project": NAME, "source": folder.name}})
    assert shown.status_code == 400 and shown.json()["data"]["written"] is False, shown.text
    token = shown.json()["data"]["token"]
    landed = client.post("/api/act/product_import", headers=as_ana, json={"params": {
        "project": NAME, "source": folder.name, "yes": True, "token": token}})

    assert landed.status_code == 200, landed.text
    assert _commits(deployment.bare) == 2


def test_only_a_person_whose_yes_writes_may_import_and_the_folder_is_not_read_first(deployment):
    from fastapi.testclient import TestClient

    from openfactory.api.app import app

    _seeded(deployment)
    said = TestClient(app).post("/api/act/product_import",
                                headers={"authorization": "Bearer bia-token"},
                                json={"params": {"project": NAME, "source": "no-such-thing",
                                                 "yes": True}})

    assert said.status_code == 403 and said.json()["data"]["reason"] == actions.DENIED
    assert "no-such-thing" not in said.text
    # and without the yes, the missing yes — with no plan shown
    shown = TestClient(app).post("/api/act/product_import",
                                 headers={"authorization": "Bearer bia-token"},
                                 json={"params": {"project": NAME, "source": "no-such-thing"}})
    assert shown.status_code == 400 and "plan" not in shown.json()["data"], shown.text


def test_the_push_happens_under_the_products_semaphore(deployment, monkeypatch):
    from openfactory.product import authoring, semaphore

    _seeded(deployment)
    held: list[bool] = []
    real = authoring._git

    def _watched(args, cwd=None):
        if args[:1] == ["push"]:
            held.append(semaphore.held_here(deployment.project))
        return real(args, cwd=cwd)

    monkeypatch.setattr(authoring, "_git", _watched)
    assert _act(source=str(_a_round(deployment.tmp)), yes=True).ok

    assert held == [True]


def test_a_refused_push_is_said_and_never_retried(deployment):
    _seeded(deployment)
    hook = deployment.bare / "hooks" / "pre-receive"
    tries = deployment.tmp / "tries"
    hook.write_text(f"#!/bin/sh\necho try >> {tries}\necho 'protected' >&2\nexit 1\n")
    hook.chmod(0o755)

    said = _act(source=str(_a_round(deployment.tmp)), yes=True)

    assert not said.ok and said.code == actions.FAILED
    assert "refused the import's commit, so nothing landed" in said.message
    assert tries.read_text().count("try") == 1, "the push was tried more than once"
    assert _commits(deployment.bare) == 1


def test_a_yes_to_a_plan_the_product_moved_past_writes_nothing(deployment):
    """A requirement landed between the plan and the yes: the yes carries the plan it was given,
    the import is planned again, and the new plan comes back — nothing is written."""
    _seeded(deployment)
    folder = _a_round(deployment.tmp)
    token = _act(source=str(folder)).data["token"]
    work = _checkout(deployment.bare, deployment.tmp / "meanwhile")
    _tree(work, {_file(3, "Refunds"): _requirement(3, "Refunds")})
    _git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A", cwd=work)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "meanwhile", cwd=work)
    _git("push", "-q", "origin", "HEAD:main", cwd=work)

    said = _act(source=str(folder), yes=True, token=token)

    assert said.code == actions.CONFLICT and said.data["token"] != token, said
    assert _commits(deployment.bare) == 2


def test_an_import_mints_past_a_proposal_still_on_its_way(deployment):
    _seeded(deployment)
    deployment.forge.branches = ["req/0007-a-proposal-on-its-way"]

    assert _act(source=str(_a_round(deployment.tmp)), yes=True).ok

    corpus = load_corpus(_checkout(deployment.bare, deployment.tmp / "after") / "requirements")
    assert [r.number for r in corpus.requirements] == [1, 2, 8, 9]


def test_branches_that_cannot_be_listed_mint_nothing(deployment):
    _seeded(deployment)
    deployment.forge.branches = None

    said = _act(source=str(_a_round(deployment.tmp)), yes=True)

    assert not said.ok and _commits(deployment.bare) == 1


def test_the_same_folder_imported_twice_is_one_import(deployment):
    _seeded(deployment)
    folder = _a_round(deployment.tmp)
    assert _act(source=str(folder), yes=True).ok

    again = _act(source=str(folder), yes=True)

    assert again.ok and again.data["existed"] and _commits(deployment.bare) == 2


# ── 10. the record, and the knowledge brought up to it ──────────────────────────────────────────

def test_the_record_says_where_it_came_from_the_plan_and_what_landed(deployment):
    _seeded(deployment)
    said = _act(source=str(_a_round(deployment.tmp)), yes=True)

    record = json.loads(_main(deployment.bare, said.data["ref"]))
    assert said.data["ref"].startswith(".openfactory/imports/") and record["origin"] == \
        "the second prototyping round"
    assert record["by"] == ADMIN and record["order"] == [4, 3]
    assert record["design"] == "imported/design/flow.md"
    assert {r["kind"] for r in record["requirements"]} == {importing.NEW, importing.REVISION}
    for path in record["landed"]:
        assert _main(deployment.bare, path), path


@pytest.mark.parametrize("path,admitted", [
    (".openfactory/imports/2026-10-21-0123456789/record.json", True),
    (".openfactory/imports/2026-10-21-0123456789/proposals/0002-x.md", True),
    (".openfactory/imports/2026-10-21-9999999999/record.json", False),
    (".openfactory/imports/2026-10-21-0123456789/../../product.yaml", False),
    (".openfactory/product.yaml", False), (".openfactory/preview.compose.yml", False),
    ("requirements/0001-x.md", True), ("domain/2026-10-21-x.md", True),
    ("imported/design/flow.md", True), ("design/flow.md", False)])
def test_an_import_lands_only_its_own_paths_and_one_record_under_the_platforms_directory(
        path, admitted):
    from openfactory.policy.context_writes import outside, outside_an_import

    refused = outside_an_import([path], importing.allowed("requirements"),
                                import_id="2026-10-21-0123456789")
    assert (refused == []) is admitted, refused
    # and no other writer gains anything: the same paths, through the rule every writer keeps
    if path.startswith(".openfactory/"):
        assert outside([path], [".openfactory", "requirements"]) == [path]


def test_the_next_search_finds_what_the_import_landed(deployment):
    from openfactory.product.documents.store import Store
    from openfactory.product.index import retrieval
    from openfactory.product.key import product_key

    _seeded(deployment)
    assert _act(source=str(_a_round(deployment.tmp)), yes=True).ok

    found = retrieval.done_before(deployment.project, "Totals")
    assert 3 in [h.number for h in found.hits], [(h.kind, h.title) for h in found.hits]
    records = Store(product_key(deployment.project)).index()["paths"]
    assert "imported/design/flow.md" in records


# ── 11. the row on the catalogue ────────────────────────────────────────────────────────────────

def test_the_row_is_a_product_row_whose_yes_is_the_products():
    row = actions.CATALOG["product_import"]

    assert row.scope == actions.PRODUCT and row.needs_admin
    assert set(row.required) == {"project", "source"} and "yes" in row.optional
    assert os.path.basename(importing.__file__) == "importing.py"
