"""A product can start before its code (#992): a project with a context repository and no source.

THE RULE THIS FILE HOLDS. A project whose product started before its code — a context repository
and no code repository (`contracts.project.before_its_code`) — is a real state, never a project
registered by halves:

  1. the registry admits it, and still refuses a project with neither repository; `sources: []`
     is a product that has not started, and the declarations that must agree still agree;
  2. every catalogue row that needs the code — READ FROM THE CATALOGUE, not listed here — refuses
     such a project by name and before it runs, naming the first source; every row that does not
     need it runs; a project with code is never asked; and every product row that only writes
     the context repository — READ FROM THE CODE — is one that runs;
  3. what works and what waits, end to end on the runtime whose forge is this machine: the act
     that starts it, an acceptance that records the promise and says its breakdown waits, every
     door into a breakdown saying the same, and the doors that are not rows yet — pickup, a box,
     a job, the doctor, the knowledge refresh — refusing or skipping it by name;
  4. the first source: one act lists it in `sources:` and records it in the registry, in that
     order, once — and the breakdown then needs no other step.

WHAT IS DRIVEN. The real action layer, the real registry, the real product module over a real
context repository (a bare git repository the local forge owns), the real command line. The two
things that SPEND — the engine a breakdown is started on and the harness a role asks — are
doubled and counted, so a case can say NOT STARTED where the rule says nothing may start.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import functools
import inspect
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from openfactory import actions
from openfactory.actions import base, catalog
from openfactory.actions.base import Actor

sys.path.insert(0, "tests")
import one_machine as om  # noqa: E402

ADMIN = Actor(id="ana", display="ana", via="cli", admin=True)
CONTEXT = "myapp-context"


def _act(name: str, **params):
    return asyncio.run(actions.perform(name, by=ADMIN, **params))


def _git(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    """One machine and nothing registered: a registry, a board file and an operator home."""
    monkeypatch.setenv("HOME", str(tmp_path))
    om.a_deployment(tmp_path, monkeypatch=monkeypatch)
    for key, value in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@t"),
                       ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@t")):
        monkeypatch.setenv(key, value)
    return tmp_path


def _registry(root: Path) -> dict:
    return yaml.safe_load((root / "registry.yaml").read_text())["projects"]


def _context_path() -> str:
    from openfactory.adapters.forge.local import LocalForge

    return LocalForge("myapp", "").clone_url(CONTEXT)


def _context_file(root: Path, rel: str) -> str:
    """`rel` as the context repository's `main` holds it now."""
    return _git("--git-dir", _context_path(), "show", f"main:{rel}").stdout


@pytest.fixture
def started(deployment):
    """`myapp`, started before its code through the row, with `ana` its product owner."""
    out = _act("product_start", project="myapp", docs_repo=CONTEXT)
    assert out.ok, out.message
    path = deployment / "registry.yaml"
    data = yaml.safe_load(path.read_text())
    data["projects"]["myapp"]["product"]["admins"] = ["ana"]
    path.write_text(yaml.safe_dump(data))
    return deployment


def _write_requirement(root: Path, number: int = 1, *, accepted: bool = False) -> None:
    """A requirement in the context exactly as `render_requirement` writes one."""
    from openfactory.product.authoring import _set_status_accepted, render_requirement
    from openfactory.product.role import RequirementDraft

    work = root / f"work-{number}"
    _git("clone", "-q", _context_path(), str(work))
    text = render_requirement(RequirementDraft(title=f"Export {number}", why="the month closes",
                                               must_be_true=["it exports"]), number=number)
    if accepted:
        text, _ = _set_status_accepted(text, accepted_by="ana", day="2026-10-21")
    (work / "requirements" / f"{number:04d}-export.md").write_text(text)
    _git("add", "-A", cwd=work)
    _git("commit", "-qm", f"requirement {number}", cwd=work)
    _git("push", "-q", "origin", "HEAD:main", cwd=work)


@pytest.fixture
def engine(monkeypatch):
    """The engine a breakdown is started on, counted: every start is one entry."""
    started_: list[tuple] = []

    async def _on_the_worker(*, project, number, by, asked_for):
        started_.append((project, number, asked_for))
        return [{"ok": True, "ref": "#1", "detail": ""}]

    monkeypatch.setattr(catalog, "_broken_down_on_the_worker", _on_the_worker)
    return started_


def _codeless(**over):
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef

    row = {"name": "myapp", "repo_path": "", "tracker": ProviderRef(kind="github", repo=None),
           "product": ProductConfig(docs_repo="acme/myapp-context")}
    row.update(over)
    return Project(**row)


# ── 1. the state ────────────────────────────────────────────────────────────────────────────────

def test_a_project_with_no_code_repository_is_before_its_code():
    from openfactory.contracts.project import before_its_code

    assert before_its_code(_codeless())
    assert not before_its_code(_codeless(repo_path="/home/ana/myapp"))
    assert not before_its_code(_codeless(repo_path="https://github.com/acme/myapp.git"))
    # a stand-in that carries no such field is not judged — only a registry entry saying so is
    assert not before_its_code(SimpleNamespace(name="myapp"))


def test_the_registry_writes_the_contexts_name_as_the_codes_forge_addresses_it(deployment):
    from openfactory.contracts.product import ProductConfig
    from openfactory.registry import ProjectRegistry

    registry = ProjectRegistry()
    registry.add(_codeless())
    registry.set_code("myapp", _codeless(repo_path="https://github.com/acme/web.git",
                                         product=ProductConfig(docs_repo="Docs/myapp-context")))
    assert registry.get("myapp").product.docs_repo == "Docs/myapp-context"


def test_the_registry_admits_one_with_a_context_and_refuses_one_with_neither(deployment):
    from openfactory.registry import ProjectRegistry

    with pytest.raises(ValueError, match="neither a code repository nor a context repository"):
        ProjectRegistry().add(_codeless(product=None))
    ProjectRegistry().add(_codeless())
    assert ProjectRegistry().get("myapp").repo_path == ""


def test_sources_empty_is_a_product_that_has_not_started_not_an_error():
    from openfactory.contracts.product import ProductDocs
    from openfactory.product.config import resolve_product_link

    link = resolve_product_link(project=_codeless(),
                                docs=ProductDocs(product="myapp", sources=[]))

    assert (link.active, link.kind, link.warnings) == (True, "ok", [])
    assert "no code repository yet" in link.reason


def test_the_declarations_that_must_agree_still_agree_when_there_is_no_source():
    """The isolation stands with nothing listed: the context must name THIS product, since no code
    repository can admit it, and the registry still authorizes, so no claim can redirect it."""
    from openfactory.contracts.product import ProductDocs
    from openfactory.product.config import resolve_product_link

    other = resolve_product_link(project=_codeless(),
                                 docs=ProductDocs(product="another", sources=[]))
    assert (other.active, other.kind) == (False, "conflict")
    assert "no code repository yet" in other.reason

    # A LOCAL ROW NAMES ITS OWN NAME AS ITS `repo` — code or none — so a listing of that name must
    # not stand in for the product's: there is no code repository to be listed, and the first
    # fault said is the product it names
    from openfactory.contracts.project import ProviderRef

    local = _codeless(tracker=ProviderRef(kind="local", repo="myapp"),
                      forge=ProviderRef(kind="local", repo="myapp"))
    listed = resolve_product_link(project=local,
                                  docs=ProductDocs(product="another", sources=["myapp"]))
    assert (listed.active, listed.kind) == (False, "conflict")
    assert "requirements for product 'another'" in listed.reason, listed.reason

    claimed = resolve_product_link(project=_codeless(), manifest_docs_repo="evil/elsewhere",
                                   docs=ProductDocs(product="myapp", sources=[]))
    assert claimed.active and claimed.docs_repo == "acme/myapp-context"

    unreadable = resolve_product_link(project=_codeless(), docs=None, docs_error="gone")
    assert (unreadable.active, unreadable.kind) == (False, "config")


#: a project before its code as `product start` registers it, ONE PER BRANCH OF `context_axes`
#: (the function that writes its axes): the runtime whose forge is this machine, an Azure DevOps
#: context named by its clone URL, and a hosted `owner/name`
SHAPES = {"local": "myapp-context",
          "azure_devops": "https://dev.azure.com/acme/Books/_git/myapp-context",
          "github": "acme/myapp-context"}

#: what a context's `sources:` can hold beside nothing: another client's repository, the one its
#: own first source would be (a local row's name, a bare Azure name), and an entry nobody can read
LISTINGS = [["clienta/portal-web"], ["myapp"], ["not/a/repository/at/all"]]


def _shaped(kind: str):
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project
    from openfactory.product.before_code import context_axes

    docs, axes = context_axes("myapp", SHAPES[kind], kind)
    return Project(name="myapp", repo_path="", product=ProductConfig(docs_repo=docs), **axes)


@pytest.mark.parametrize("kind", list(SHAPES))
@pytest.mark.parametrize("sources", LISTINGS, ids=lambda s: s[0])
def test_a_project_with_no_code_links_only_to_a_product_that_lists_nothing(kind, sources):
    """It can vouch for nothing `sources:` lists (review of 9f18a788): let in on `product:` alone,
    the product role read another client's repositories as its own, and its first source was
    written into their list by the act that registers it."""
    from openfactory.contracts.product import ProductDocs
    from openfactory.product.config import resolve_product_link

    project = _shaped(kind)
    started_ = resolve_product_link(project=project,
                                    docs=ProductDocs(product="myapp", sources=[]))
    listed = resolve_product_link(project=project,
                                  docs=ProductDocs(product="myapp", sources=sources))

    assert started_.active, started_.reason
    assert (listed.active, listed.kind) == (False, "conflict")
    assert "can vouch for none of them" in listed.reason, listed.reason
    assert "openfactory product first-source myapp" in listed.reason, listed.reason


def test_the_code_of_a_project_before_it_is_never_the_current_directory():
    from openfactory.contracts.project import NoCodeYet
    from openfactory.factory import resolve_repo_path

    with pytest.raises(NoCodeYet, match="openfactory product first-source myapp"):
        resolve_repo_path(_codeless())


# ── 2. the family rule, read from the catalogue ─────────────────────────────────────────────────

#: every row `perform` refuses for a project before its code, and every row it runs for one —
#: READ FROM THE CATALOGUE: a row added later lands in one of the two by what it declares
WAITING = [n for n in actions.names() if actions.waits_for_code(actions.spec(n))]
WORKING = [n for n in actions.names()
           if "project" in actions.spec(n).parameters and not actions.spec(n).needs_code]


def _params(spec, project: str) -> dict:
    return {p: project if p == "project" else "1" if p in ("issue", "number") else "x"
            for p in spec.required}


@pytest.fixture
def spied(monkeypatch):
    """Each row's runner replaced by one that records it ran — the row's own work never runs."""
    ran: list[str] = []

    def _spy(name: str) -> None:
        async def run(**_params):
            ran.append(name)
            return base.done("ran")

        monkeypatch.setitem(catalog.CATALOG, name,
                            dataclasses.replace(catalog.CATALOG[name], run=run))

    return ran, _spy


def test_the_catalogue_has_rows_on_both_sides_of_the_rule():
    assert {"product_break_down", "scan", "start", "product_board"} <= set(WAITING)
    assert {"product_say", "product_accept", "product_propose", "product_start",
            "product_first_source"} <= set(WORKING)


@pytest.mark.parametrize("name", WAITING)
def test_every_row_that_needs_the_code_refuses_a_project_before_it_by_name(started, spied, name):
    ran, spy = spied
    spy(name)
    out = _act(name, **_params(catalog.CATALOG[name], "myapp"))

    assert (out.ok, out.code, out.data.get("reason")) == (False, base.CONFLICT, base.NO_CODE_YET)
    assert name in out.message and "openfactory product first-source myapp" in out.message
    assert ran == [], f"{name} ran on a project before its code"


@pytest.mark.parametrize("name", WORKING)
def test_every_row_that_does_not_need_the_code_runs_for_one(started, spied, name):
    ran, spy = spied
    spy(name)
    out = _act(name, **_params(catalog.CATALOG[name], "myapp"))

    assert out.ok and ran == [name], out.message


@pytest.mark.parametrize("name", WAITING)
def test_a_project_with_code_is_never_refused_for_it(deployment, spied, name):
    ran, spy = spied
    assert om.cli("project", "init", "myapp", str(om.a_repository(deployment)))[0] == 0
    spy(name)
    out = _act(name, **_params(catalog.CATALOG[name], "myapp"))

    assert out.data.get("reason") != base.NO_CODE_YET and ran == [name], out.message


@pytest.mark.parametrize("name", list(actions.names()))
def test_a_row_says_it_may_wait_for_the_code_exactly_when_it_does(name):
    assert (base.NO_CODE_YET in actions.reasons(name)) == actions.waits_for_code(
        actions.spec(name))


# ── the rows that only write the context, read from the code ────────────────────────────────────

def _source(fn) -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(fn)))


def _context_only_rows() -> list[str]:
    """Every product row that writes the context repository and reaches nothing of the code —
    READ FROM THE CODE, not from what the row declares (`product_import` was added waiting, #999):

    - a module method WRITES THE CONTEXT when it hands its write `_saved_in_the_repository`, the
      module's own name for what a write to the context repository saved;
    - it REACHES THE CODE when it, or a module method it calls on itself, builds the tracker or the
      board (`build_tracker`, `build_board`), files a card (`_saved_on_the_board`), resolves the
      code's checkout (`resolve_repo_path`) or reads the code's map (`openfactory.knowledge`);
    - a row ONLY WRITES THE CONTEXT when its runner calls a module method that writes it and none
      that reaches the code."""
    from openfactory.product.module import ProductModule

    methods = {n: f for n, f in vars(ProductModule).items() if inspect.isfunction(f)}
    trees = {n: _source(f) for n, f in methods.items()}

    # Memoised per method (#1069): `reaches` asks every method's whole reach, and without the
    # memo a method's tree was walked again for every method that reached it.
    @functools.cache
    def words(name: str) -> frozenset[str]:
        tree = trees[name]
        said = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                said |= {node.module or ""} | {a.name for a in node.names}
        return frozenset(said)

    @functools.cache
    def on_itself(name: str) -> frozenset[str]:
        return frozenset(
            n.attr for n in ast.walk(trees[name]) if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name) and n.value.id == "self" and n.attr in methods)

    @functools.cache
    def reached(name: str) -> frozenset[str]:
        seen, todo = set(), [name]
        while todo:
            if (one := todo.pop()) not in seen:
                seen.add(one)
                todo += on_itself(one)
        return frozenset(seen)

    code = {"build_tracker", "build_board", "_saved_on_the_board", "resolve_repo_path"}
    reaches = {m for m in methods if any(w in code or w.startswith("openfactory.knowledge")
                                         for r in reached(m) for w in words(r))}
    writes = {m for m in methods if "_saved_in_the_repository" in words(m)} - reaches

    rows = []
    for name in actions.names():
        row = actions.spec(name)
        if row.scope != actions.PRODUCT or "project" not in row.parameters:
            continue
        called = {n.attr for n in ast.walk(_source(row.run))
                  if isinstance(n, ast.Attribute) and n.attr in methods}
        if called & writes and not called & reaches:
            rows.append(name)
    return rows


CONTEXT_ONLY = _context_only_rows()


def test_the_rows_that_only_write_the_context_are_found_on_both_sides():
    assert {"product_import", "product_note_fact", "product_record_decision", "product_accept",
            "product_drop", "product_file_attachment"} <= set(CONTEXT_ONLY)
    # a card is filed on the board; a capability confirms what the code's map observed
    assert not {"product_file_defect", "product_file_ticket", "product_confirm_capability",
                "product_break_down"} & set(CONTEXT_ONLY)


@pytest.mark.parametrize("name", CONTEXT_ONLY)
def test_a_row_that_only_writes_the_context_does_not_wait_for_the_code(name):
    assert not actions.waits_for_code(actions.spec(name)), (
        f"{name} writes only the context repository and is refused before the code — it says "
        f"`needs_code=False` on its catalogue row")


def test_requirements_are_imported_into_a_product_before_its_code(started, monkeypatch):
    """The hand-over into a product with no code yet (#993 after #992): the plan is shown and
    nothing is written; with its yes and its token the requirements land in the context."""
    from openfactory.product.authoring import render_requirement
    from openfactory.product.documents import ingest
    from openfactory.product.role import RequirementDraft
    from tests.documents_bed import StubReader

    monkeypatch.setattr(ingest, "ModelReader", lambda **_kw: StubReader())
    folder = started / "brought"
    (folder / "requirements").mkdir(parents=True)
    (folder / "requirements" / "0001-export.md").write_text(render_requirement(
        RequirementDraft(title="Export", why="the month closes", must_be_true=["it exports"]),
        number=1))
    tip = _git("--git-dir", _context_path(), "rev-parse", "main").stdout

    shown = _act("product_import", project="myapp", source=str(folder))

    assert shown.data.get("reason") != base.NO_CODE_YET, shown.message
    assert shown.code == base.INVALID and shown.data["written"] is False, shown.message
    assert shown.data["plan"] and shown.data["token"], shown.data
    assert _git("--git-dir", _context_path(), "rev-parse", "main").stdout == tip

    landed = _act("product_import", project="myapp", source=str(folder), yes=True,
                  token=shown.data["token"])

    assert landed.ok, landed.message
    assert "Export" in _context_file(started, "requirements/0001-export.md")


# ── 3. what works and what waits ────────────────────────────────────────────────────────────────

def test_a_product_starts_with_its_context_and_no_code(deployment):
    out = _act("product_start", project="myapp", docs_repo=CONTEXT)

    assert out.ok and out.data["registered"] and out.data["created"], out.message
    assert out.data["reachable"] and out.data["active"], out.message
    row = _registry(deployment)["myapp"]
    assert row["repo_path"] == "" and row["product"]["docs_repo"] == CONTEXT
    assert {row[a]["kind"] for a in ("tracker", "forge")} == {"local"}
    declared = yaml.safe_load(_context_file(deployment, ".openfactory/product.yaml"))
    assert declared["product"] == "myapp" and declared["sources"] == []


def test_starting_it_again_finds_it_and_starting_one_with_code_is_refused(started):
    again = _act("product_start", project="myapp", docs_repo=CONTEXT)
    assert again.ok and not again.data["registered"], again.message

    elsewhere = _act("product_start", project="myapp", docs_repo="another-context")
    assert elsewhere.code == base.CONFLICT and "product declare" in elsewhere.message

    assert om.cli("project", "add", "theirs", str(om.a_repository(started / "c")))[0] == 0
    coded = _act("product_start", project="theirs", docs_repo="theirs-context")
    assert coded.code == base.CONFLICT and "already registered with its code" in coded.message


def _list_in_the_context(root: Path, entries: list[str]) -> str:
    """`sources:` of the context set to `entries` by whoever writes the context; its new tip."""
    work = root / f"lister-{len(list(root.glob('lister-*')))}"
    _git("clone", "-q", _context_path(), str(work))
    manifest = work / ".openfactory" / "product.yaml"
    declared = yaml.safe_load(manifest.read_text())
    manifest.write_text(yaml.safe_dump({**declared, "sources": entries}))
    _git("commit", "-qam", "the context's owner lists its sources", cwd=work)
    _git("push", "-q", "origin", "HEAD:main", cwd=work)
    return _git("--git-dir", _context_path(), "rev-parse", "main").stdout


def test_starting_on_a_context_that_lists_sources_says_the_role_is_off_and_why(started):
    """Its own words, not "write the declaration": a context that already lists repositories is a
    product that has started, and a declaration written into it would be the breach."""
    _list_in_the_context(started, ["clienta-web"])
    again = _act("product_start", project="myapp", docs_repo=CONTEXT)

    assert again.ok and not again.data["active"] and again.data["link"] == "conflict", again.data
    assert "can vouch for none of them" in again.message, again.message
    assert "product init" not in again.message, again.message


@pytest.mark.parametrize("ref,why", [
    ("myapp", "that name is the project's own code"),
    ("-upload-pack=x", "is named `owner/repo`"),
    ("https://gitlab.example.com/acme/ctx.git", "gitlab.example.com"),
])
def test_a_context_nobody_could_read_is_refused_before_anything_is_written(deployment, ref, why):
    out = _act("product_start", project="myapp", docs_repo=ref)

    assert out.code == base.INVALID and why in out.message, out.message
    assert not (deployment / "registry.yaml").exists() or "myapp" not in _registry(deployment)


def test_the_local_forge_never_makes_the_current_directory_a_context_repository(
        deployment, monkeypatch):
    """The cheapest layer of the rule above: a name that answers no path — the project's own,
    when it has no code — is refused by the forge itself, whichever door asked."""
    from openfactory.adapters.forge.local import LocalForge

    here = deployment / "where-the-process-stands"
    here.mkdir()
    monkeypatch.chdir(here)
    with pytest.raises(ValueError, match="needs a name of its own"):
        LocalForge("myapp", "").create_repository(name="myapp")
    assert list(here.iterdir()) == []


def test_a_hosted_context_names_no_code_repository_on_any_axis():
    from openfactory.product.before_code import Refused, context_axes, context_kind

    assert context_kind("acme/acme-context") == "github"
    docs, axes = context_axes("acme", "acme/acme-context", "github", token_env="ACME_TOKEN")
    assert docs == "acme/acme-context" and set(axes) == {"tracker"}
    assert axes["tracker"].repo is None and axes["tracker"].options == {"token_env": "ACME_TOKEN"}

    url = "https://dev.azure.com/acme-org/Books/_git/books-context"
    assert context_kind(url) == "azure_devops"
    docs, axes = context_axes("books", url, "azure_devops")
    assert docs == "books-context"
    assert axes["forge"].repo is None and axes["tracker"].repo is None
    assert axes["forge"].options == {"organization": "acme-org", "project": "Books"}

    with pytest.raises(Refused, match="clone URL"):
        context_axes("books", "books-context", "azure_devops")


def test_an_acceptance_records_the_promise_and_says_its_breakdown_waits(started, engine):
    from openfactory.product.voice import breakdown_waits_for_code

    _write_requirement(started, 1)
    out = _act("product_accept", project="myapp", number="1", yes=True)

    assert out.ok and out.data["waits_for_code"] and out.data["filed"] == [], out.message
    assert breakdown_waits_for_code(number=1) in out.message
    assert engine == [], "a breakdown was started for a product with no code"
    assert "**Status:** accepted" in _context_file(started, "requirements/0001-export.md")


def test_every_conversation_door_into_a_breakdown_says_the_wait(started, monkeypatch):
    """The person's own request and the acceptance's second act start the breakdown through
    `breaking.start`, which asks no engine; the conversation's just-written requirement stages
    its second yes on the requirement itself, with no card."""
    from openfactory.product import breaking, confirm, door
    from openfactory.product.authoring import WriteResult
    from openfactory.product.voice import breakdown_waits_for_code, written_before_code
    from openfactory.registry import ProjectRegistry

    async def _no_engine():
        raise AssertionError("the engine was asked about a product with no code")

    monkeypatch.setattr(door, "_engine", _no_engine)
    project = ProjectRegistry().get("myapp")
    waits = breakdown_waits_for_code(number=4)

    assert breaking.start_now(project, 4, actor="ana", asked_for=True) == breaking.WAITS
    assert confirm._confirm_breakdown(project, {"number": 4}, module=None, user="ana",
                                      lang="en") == waits
    assert confirm._also_broke_it_down(4, "ana", "Agreed.", "en", project) == f"Agreed.\n\n{waits}"

    def _propose(answer, **_kw):
        return WriteResult(ok=True, merged=True, number=4, url="u")

    entry = {"answer": SimpleNamespace(draft=SimpleNamespace(title="Export")), "asked_by": "ana"}
    said = confirm._confirm_draft(project, entry, module=SimpleNamespace(propose=_propose),
                                  user="ana", lang="en")
    assert said.endswith(written_before_code(number=4, language="en"))
    assert entry["next"]["kind"] == "accept" and entry["next"]["cards"] == []


def test_the_breakdown_itself_files_nothing_and_asks_no_model(started, monkeypatch):
    """The sink asks as well as the doors: a door nobody has written yet still gets the wait."""
    from openfactory.product import module as product_module
    from openfactory.product.module import ProductModule
    from openfactory.registry import ProjectRegistry

    _write_requirement(started, 1, accepted=True)
    monkeypatch.setattr(product_module.ProductModule, "_role", lambda self: (_ for _ in ()).throw(
        AssertionError("a model was asked to draft cards for a product with no code")))
    module = ProductModule(ProjectRegistry().get("myapp"), via="cli")
    results = module.break_down(1, actor="ana", asked_for=True)

    assert [(r.ok, r.waits_for_code) for r in results] == [(False, True)]


def test_the_worker_reports_the_wait_as_the_module_said_it_and_files_no_front_as_left_out():
    from openfactory.product import confirm, unfiled
    from openfactory.product.authoring import WriteResult

    waiting = [WriteResult(ok=False, waits_for_code=True, detail="it waits")]

    assert confirm.breakdown_told(_codeless(), 1, waiting, asked_for=False) == "it waits"
    assert unfiled.not_filed(waiting) == []


# ── the doors that are not rows yet ─────────────────────────────────────────────────────────────

def test_pickup_leaves_it_off_the_poll_list(started, caplog):
    import logging

    from openfactory.runtime.temporal import activities

    caplog.set_level(logging.INFO)
    assert om.cli("project", "init", "theirs", str(om.a_repository(started / "c")))[0] == 0
    polled = [row["project"] for row in asyncio.run(activities.scan_projects())]

    assert "myapp" not in polled and "theirs" in polled
    assert "OPENFACTORY_PICKUP_WAITS_FOR_CODE myapp" in caplog.text


@pytest.mark.parametrize("verb", [("box", "prove", "myapp"), ("run", "myapp", "1"),
                                  ("poll", "myapp"), ("project", "init", "myapp")])
def test_a_verb_that_reads_the_code_refuses_it_and_writes_nothing_where_it_stands(
        started, monkeypatch, verb):
    here = started / "where-the-command-stands"
    here.mkdir()
    monkeypatch.chdir(here)
    code, said = om.cli(*verb)

    assert code == 1 and "openfactory product first-source myapp" in said, said
    assert list(here.iterdir()) == [], "a verb wrote into the directory it was run from"


def test_the_knowledge_refresh_maps_no_code_and_clones_nothing(started, monkeypatch):
    from openfactory.adapters.forge import registry as forge_registry
    from openfactory.runtime.temporal import activities
    from openfactory.runtime.temporal.io import KnowledgeRefreshInput

    monkeypatch.setattr(forge_registry, "clone_url_for",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("cloned")))
    assert activities._do_refresh_knowledge(KnowledgeRefreshInput(project="myapp")) == "no-repo"


def test_the_doctor_says_the_state_once_instead_of_a_line_per_reader_of_the_code(started):
    from openfactory.doctor import NEEDS_THE_CODE

    _, said = om.cli("doctor", "myapp")
    lines = said.splitlines()
    code = [line for line in lines if line.split()[1:2] == ["code"]]

    assert code and "FAIL" in code[0] and "first-source myapp" in said, said
    assert not [line for line in lines if (line.split()[1:2] or [""])[0] in NEEDS_THE_CODE], said
    assert any("product_link" in line and "ok" in line for line in lines), said


def test_the_readiness_check_answers_for_it_and_holds_on_the_state_once(started):
    """The doctor's `code` line reaches the panel (review of 9f18a788): `env_check` — the row that
    composes the doctor — answers for a project before its code, NOT ready, held on one `code`
    line, with no line from a check that reads the code or its proof."""
    from openfactory import doctor
    from openfactory.contracts.project import no_code_yet
    from openfactory.onboarding import readiness

    out = _act("env_check", project="myapp")
    checks = [f["check"] for f in out.data.get("findings", [])]

    assert out.ok and out.data["ready"] is False, out.message
    assert out.data["holds"][0] == no_code_yet("myapp", "running a ticket"), out.data["holds"]
    assert checks.count("code") == 1, checks
    assert not set(checks) & (doctor.NEEDS_THE_CODE | readiness.NEEDS_THE_CODE), checks


# ── 4. the first source ─────────────────────────────────────────────────────────────────────────

def test_the_first_source_is_listed_and_recorded_and_the_breakdown_needs_no_other_step(
        started, engine):
    from openfactory.contracts.project import before_its_code
    from openfactory.product.loader import load_product_context
    from openfactory.registry import ProjectRegistry

    _write_requirement(started, 1)
    assert _act("product_accept", project="myapp", number="1", yes=True).ok
    repo = om.a_repository(started / "code")
    out = _act("product_first_source", project="myapp", repo_path=str(repo))

    assert out.ok and out.data["listed_now"] and out.data["waiting"] == [1], out.message
    declared = yaml.safe_load(_context_file(started, ".openfactory/product.yaml"))
    assert declared["sources"] == ["myapp"] and declared["product"] == "myapp"
    project = ProjectRegistry().get("myapp")
    assert project.repo_path == str(repo) and not before_its_code(project)
    link = load_product_context(project).link
    assert link.active and link.reason == "registry, source repo and documentation repo agree"

    broken = _act("product_break_down", project="myapp", number="1", yes=True)
    assert broken.data.get("reason") != base.NO_CODE_YET and engine == [("myapp", 1, True)], (
        broken.message)
    _write_requirement(started, 2)
    accepted = _act("product_accept", project="myapp", number="2", yes=True)
    assert accepted.ok and not accepted.data.get("waits_for_code")
    assert engine[-1] == ("myapp", 2, False), "an acceptance did not file its own cards"


def test_a_first_source_is_given_once(started):
    repo = om.a_repository(started / "code")
    assert _act("product_first_source", project="myapp", repo_path=str(repo)).ok
    tip = _git("--git-dir", _context_path(), "rev-parse", "main").stdout
    again = _act("product_first_source", project="myapp", repo_path=str(started / "other"))

    # REFUSED BEFORE THE CONTEXT IS TOUCHED, naming how another repository joins the product
    assert again.code == base.CONFLICT and "product init myapp --source" in again.message
    assert _git("--git-dir", _context_path(), "rev-parse", "main").stdout == tip
    assert _registry(started)["myapp"]["repo_path"] == str(repo)


def test_the_registry_gives_a_project_its_code_once(deployment):
    """The registry's own half of the rule, under its lock: the act's check runs before the
    context is written, and this one stops a second writer that passed it at the same moment."""
    from openfactory.registry import ProjectRegistry

    registry = ProjectRegistry()
    registry.add(_codeless())
    registry.set_code("myapp", _codeless(repo_path="https://github.com/acme/web.git"))
    assert registry.get("myapp").repo_path == "https://github.com/acme/web.git"
    with pytest.raises(ValueError, match="given once"):
        registry.set_code("myapp", _codeless(repo_path="https://github.com/acme/api.git"))
    with pytest.raises(KeyError):
        registry.set_code("nobody", _codeless(repo_path="/x"))
    # ASKED WITHOUT WRITING, by the same function: what `set_code` refuses, `check_code` refuses
    written = (deployment / "registry.yaml").read_text()
    with pytest.raises(ValueError, match="given once"):
        registry.check_code("myapp", _codeless(repo_path="https://github.com/acme/api.git"))
    with pytest.raises(KeyError):
        registry.check_code("nobody", _codeless(repo_path="/x"))
    assert (deployment / "registry.yaml").read_text() == written


def test_a_context_that_cannot_be_written_leaves_the_registry_as_it_was(started):
    """The context first, then the registry: a registry naming code its `sources:` does not list
    would turn the product role off as a membership conflict."""
    import shutil

    shutil.rmtree(_context_path())
    out = _act("product_first_source", project="myapp",
               repo_path=str(om.a_repository(started / "code")))

    assert out.code == base.UNAVAILABLE and "nothing was written" in out.message, out.message
    assert _registry(started)["myapp"]["repo_path"] == ""


def test_a_context_that_already_lists_it_is_not_written_again(started):
    """The scaffold's way: whatever made the repository listed it first — in its own spelling —
    and the act records it in the registry without a second commit."""
    work = started / "scaffold"
    _git("clone", "-q", _context_path(), str(work))
    manifest = work / ".openfactory" / "product.yaml"
    manifest.write_text(manifest.read_text().replace("sources: []", "sources:\n  - MyApp"))
    _git("commit", "-qam", "the scaffold lists its repository", cwd=work)
    _git("push", "-q", "origin", "HEAD:main", cwd=work)
    tip = _git("--git-dir", _context_path(), "rev-parse", "main").stdout

    out = _act("product_first_source", project="myapp",
               repo_path=str(om.a_repository(started / "code")))

    assert out.ok and not out.data["listed_now"], out.message
    assert _git("--git-dir", _context_path(), "rev-parse", "main").stdout == tip
    assert _registry(started)["myapp"]["repo_path"]


@pytest.mark.parametrize("others,found", [(["clienta-web"], False),
                                          (["clienta-web", "MyApp"], True)],
                         ids=["lists-others", "lists-others-and-it"])
def test_a_context_that_lists_other_sources_admits_the_first_source_only_when_it_lists_it(
        started, others, found):
    """One declaration per act (review of 9f18a788): a product that has sources admits another
    repository when its context lists it — written there by whoever writes the context — and is
    never given one by the act that also registers it. Until then the role stays off, since a
    project with no code can vouch for none of what is listed."""
    from openfactory.product.loader import load_product_context
    from openfactory.registry import ProjectRegistry

    tip = _list_in_the_context(started, others)
    before = load_product_context(ProjectRegistry().get("myapp")).link
    assert (before.active, before.kind) == (False, "conflict"), before.reason

    out = _act("product_first_source", project="myapp",
               repo_path=str(om.a_repository(started / "code")))

    assert _git("--git-dir", _context_path(), "rev-parse", "main").stdout == tip
    if found:
        assert out.ok and not out.data["listed_now"], out.message
        assert load_product_context(ProjectRegistry().get("myapp")).link.active
    else:
        assert out.code == base.CONFLICT and "already lists 'clienta-web'" in out.message, (
            out.message)
        assert "Nothing was written" in out.message
        assert _registry(started)["myapp"]["repo_path"] == ""


def _theirs():
    """A project of the deployment's own GitHub organisation, `acme`, with its code."""
    from openfactory.contracts.project import Project, ProviderRef

    return Project(name="theirs", repo_path="https://github.com/acme/theirs.git",
                   tracker=ProviderRef(kind="github", repo="acme/theirs"))


def test_a_first_source_the_registry_would_refuse_writes_nothing_to_the_context(
        deployment, monkeypatch):
    """The registry asked before the push (review of 9f18a788): a code repository in another
    organisation was refused by `set_code` only after `sources:` was pushed, leaving a source in
    the context that every later run was refused over again."""
    from openfactory.product import before_code
    from openfactory.registry import ProjectRegistry

    registry = ProjectRegistry()
    registry.add(_theirs())
    registry.add(_codeless())
    pushed: list[str] = []
    monkeypatch.setattr(before_code, "_list_in_context",
                        lambda project, would_be, entry: pushed.append(entry) or True)
    monkeypatch.setattr(before_code, "_waiting", lambda project: ())

    with pytest.raises(before_code.Refused, match="more than one GitHub organisation") as no:
        before_code.first_source("myapp", "https://github.com/other/myapp.git")
    assert no.value.kind == before_code.CONFLICT and "nothing was written" in no.value.message
    assert pushed == [] and registry.get("myapp").repo_path == ""

    before_code.first_source("myapp", "https://github.com/acme/myapp.git")
    assert pushed == ["acme/myapp"]
    assert registry.get("myapp").repo_path == "https://github.com/acme/myapp.git"


#: every address `context_kind` reads as a GitHub context — `owner/name` and both clone URLs
GITHUB_CONTEXTS = ["other/myapp-context", "https://github.com/other/myapp-context.git",
                   "git@github.com:other/myapp-context.git"]


@pytest.mark.parametrize("context", GITHUB_CONTEXTS)
def test_a_project_with_no_code_is_counted_in_its_contexts_organisation(deployment, context):
    """Its context is the one repository its work touches, with this deployment's credential, so
    the one-organisation rule sees it there (review of 9f18a788) — at `add`, through the act."""
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project
    from openfactory.product.before_code import context_axes, context_kind
    from openfactory.registry import ProjectRegistry, owners_by_project

    ProjectRegistry().add(_theirs())
    out = _act("product_start", project="myapp", docs_repo=context)

    assert out.code == base.CONFLICT and "more than one GitHub organisation" in out.message, (
        out.message)
    assert "myapp" not in _registry(deployment)
    # IN EVERY SPELLING A CONTEXT IS DECLARED IN: the act writes `owner/name`, and an entry a
    # later `product declare` or a hand wrote may carry the clone URL
    _, axes = context_axes("myapp", context, context_kind(context))
    codeless = Project(name="myapp", repo_path="", product=ProductConfig(docs_repo=context),
                       **axes)
    assert owners_by_project([codeless]) == {"other": ["myapp"]}


def test_a_code_repository_on_another_forge_is_refused(started):
    out = _act("product_first_source", project="myapp",
               repo_path="https://github.com/acme/myapp.git")

    assert out.code == base.INVALID and "same forge" in out.message, out.message
    assert _registry(started)["myapp"]["repo_path"] == ""


@pytest.mark.parametrize("theirs,code,expect", [
    ({"organization": "acme", "project": "Books"}, {"organization": "acme", "project": "Books"},
     "books-context"),
    ({"organization": "acme", "project": "Docs"}, {"organization": "acme", "project": "Books"},
     "Docs/books-context"),
    ({"organization": "acme", "project": "Docs"}, {"organization": "other", "project": "Books"},
     None),
])
def test_an_azure_code_repository_is_read_with_the_contexts_organisation(theirs, code, expect):
    from openfactory.contracts.project import ProviderRef
    from openfactory.product.before_code import Refused, _same_organisation

    project = _codeless(forge=ProviderRef(kind="azure_devops", repo=None, options=theirs))
    axes = {"forge": ProviderRef(kind="azure_devops", repo="books", options=code)}
    if expect is None:
        with pytest.raises(Refused, match="one organisation's credential"):
            _same_organisation(project, axes, "books-context")
    else:
        assert _same_organisation(project, axes, "books-context") == expect
