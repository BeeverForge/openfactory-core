"""Every push onto a context repository's base branch holds the product's semaphore (#673).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640). A product of three registry projects
refreshes its knowledge on one clock, so at 00:00:00Z the three members published their module maps
within 120 ms of each other into the one context repository. The publish took no lock and retried
once: two maps landed, and the third was rejected twice, once by each, and dropped until the next
refresh three hours later. And the same publish could land between a person's clone and their push
— a requirement, a decision, a fact, each pushed once under the product's semaphore — and make
their save fail. The system layer's publish already held the semaphore for that reason; the module
map's did not.

THE RULE THIS FILE HOLDS:
  1. the members of one product publishing at the same moment all land, one after another;
  2. a publish never lands between a person's clone and their push;
  3. a publish that cannot have the semaphore in time publishes nothing, says so, and is `busy`;
  4. every push the code makes onto a context repository's base branch — found by reading the
     code, not listed — holds the product's semaphore: the push is inside a hold, or every call
     that reaches it is. The two that create the repository are declared, each with its reason.

HOW IT IS SEEN WITHOUT LUCK. The writers are real processes (`spawn`) on one bare repository, and
the moment that matters is pinned. In (1) every publisher waits, after its clone, for the others
to have cloned too, so on a publish that does not queue they all push from one tip; on one that
does, the first waits for nobody (its wait runs out) and the rest find the queue. In (2) the person
stops between their clone and their push until the publish has had its chance.
"""

from __future__ import annotations

import ast
import multiprocessing
import os
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from openfactory.knowledge import pipeline
from tests.the_tree_read_once import parsed

SPAWN = multiprocessing.get_context("spawn")
#: How long a pinned moment waits for the others. On a publish that does not queue they all
#: arrive within milliseconds; on one that does, only the first waits, and for this long.
TRY_SECONDS = 3
#: An upper bound on anything that should happen at once. Reached only when something is broken.
BOUND = 120
CONTEXT_REPO = "acme/reservas-context"
MEMBERS = ("acme/reservas-web", "acme/reservas-api", "acme/reservas-core")
ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout


@pytest.fixture
def context(tmp_path):
    """A real bare context repository with one commit on `main`."""
    work = tmp_path / "seed"
    work.mkdir()
    (work / "README.md").write_text("context\n")
    for args in (["init", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"], ["add", "-A"], ["commit", "-m", "seed"]):
        _git(*args, cwd=work)
    bare = tmp_path / "context.git"
    _git("clone", "--bare", str(work), str(bare))
    return bare


def _member(name: str) -> SimpleNamespace:
    """A registry project linked to the one context repository: a member of the product."""
    return SimpleNamespace(name=name.split("/")[-1], language="en",
                           product=SimpleNamespace(docs_repo=CONTEXT_REPO))


def _bundle(at: Path, repo: str) -> Path:
    at.mkdir(parents=True, exist_ok=True)
    (at / pipeline.MODULES_FILE).write_text(f"repo: {repo}\nmodules: []\n")
    (at / pipeline.MANIFEST_FILE).write_text(f"source: {repo}\n")
    return at


def _published(context: Path) -> list[str]:
    """The sources whose map is on the context repository's `main`."""
    listed = _git("--git-dir", str(context), "ls-tree", "--name-only", "main", ".okf/repos/")
    return sorted(Path(line).name for line in listed.splitlines())


# ── the processes ────────────────────────────────────────────────────────────────────────────────

def _publishing(context: str, bundle: str, repo: str, log_dir: str, first, second,
                said: str, ready=None) -> None:
    """One member publishing its map. After each clone it waits for the others: `first` after
    its first, `second` after its second (a retry's)."""
    from threading import BrokenBarrierError

    os.environ["OPENFACTORY_LOG_DIR"] = log_dir   # where the product's semaphore lives
    from openfactory.knowledge import pipeline as pub

    real, clones = pub._stage_bundle, [0]

    def _pinned(*args, **kwargs):
        got = real(*args, **kwargs)
        clones[0] += 1
        try:
            (first if clones[0] == 1 else second).wait(TRY_SECONDS)
        except BrokenBarrierError:
            pass
        return got

    pub._stage_bundle = _pinned
    if ready is not None:
        ready.set()
    ok = pub.publish_bundle(Path(bundle), context, project=_member(repo),
                            subpath=pub.okf_subpath(repo), source_commit="c1")
    Path(said).write_text("published" if ok else "not published")


def _a_person_saving(context: str, work: str, log_dir: str, cloned, release, said: str) -> None:
    """A person's write as the product role makes one: under the semaphore, clone, commit, and
    push ONCE — it does not retry. It stops between the clone and the push until released."""
    os.environ["OPENFACTORY_LOG_DIR"] = log_dir
    from openfactory.product import semaphore

    with semaphore.held(_member("acme/reservas-web"), timeout=BOUND):
        _git("clone", "-q", context, work)
        cloned.set()
        release.wait(BOUND)
        (Path(work) / "decisions.md").write_text("we export in CSV\n")
        _git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A", cwd=Path(work))
        _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "a decision",
             cwd=Path(work))
        pushed = subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work,
                                capture_output=True, text=True)
    Path(said).write_text("saved" if pushed.returncode == 0 else f"refused: {pushed.stderr}")


def _holding(log_dir: str, held, release) -> None:
    os.environ["OPENFACTORY_LOG_DIR"] = log_dir
    from openfactory.product import semaphore

    with semaphore.held(_member("acme/reservas-api"), timeout=BOUND):
        held.set()
        release.wait(BOUND)


# ── 1. the members of one product, at the same moment ─────────────────────────────────────────

def test_TODAYS_RUN_three_members_publishing_at_once_all_land(tmp_path, context):
    """The three refreshes of 00:00:00Z: every member's map is on the context repository after."""
    log_dir = str(tmp_path / "journal")
    first, second = SPAWN.Barrier(len(MEMBERS)), SPAWN.Barrier(len(MEMBERS) - 1)
    runs = []
    for repo in MEMBERS:
        said = tmp_path / f"{repo.split('/')[-1]}.said"
        bundle = _bundle(tmp_path / "bundles" / repo.split("/")[-1], repo)
        runs.append((repo, said, SPAWN.Process(target=_publishing, args=(
            str(context), str(bundle), repo, log_dir, first, second, str(said)))))
    for _, _, proc in runs:
        proc.start()
    for _, _, proc in runs:
        proc.join(BOUND)

    said = {repo: path.read_text() if path.exists() else "nothing" for repo, path, _ in runs}
    assert _published(context) == sorted(r.replace("/", "--") for r in MEMBERS), (
        f"a member's map was dropped: on main {_published(context)}; each said {said}")
    assert set(said.values()) == {"published"}, said


# ── 2. never between a person's clone and their push ─────────────────────────────────────────

def test_a_publish_never_lands_between_a_persons_clone_and_their_push(tmp_path, context):
    log_dir = str(tmp_path / "journal")
    cloned, release = SPAWN.Event(), SPAWN.Event()
    person_said = tmp_path / "person.said"
    person = SPAWN.Process(target=_a_person_saving, args=(
        str(context), str(tmp_path / "person"), log_dir, cloned, release, str(person_said)))
    person.start()
    assert cloned.wait(BOUND), "the person never cloned"

    never = SPAWN.Barrier(1)   # nobody else publishes: the publisher's pin lets it straight on
    map_said, ready = tmp_path / "map.said", SPAWN.Event()
    bundle = _bundle(tmp_path / "bundle", MEMBERS[1])
    publisher = SPAWN.Process(target=_publishing, args=(
        str(context), str(bundle), MEMBERS[1], log_dir, never, never, str(map_said), ready))
    publisher.start()
    assert ready.wait(BOUND), "the publisher never started"
    publisher.join(TRY_SECONDS)   # a publish that does not queue clones and pushes within this
    release.set()
    person.join(BOUND)
    publisher.join(BOUND)

    assert person_said.read_text() == "saved", (
        f"the person's save failed because a publish landed between their clone and their push: "
        f"{person_said.read_text()}")
    assert map_said.read_text() == "published", "the publish did not land after the person's save"
    assert _published(context) == [MEMBERS[1].replace("/", "--")]


# ── 3. a semaphore that cannot be had in time ─────────────────────────────────────────────────

def test_a_publish_that_cannot_have_the_semaphore_in_time_is_busy(tmp_path, context, caplog,
                                                                  monkeypatch):
    log_dir = str(tmp_path / "journal")
    monkeypatch.setenv("OPENFACTORY_LOG_DIR", log_dir)
    held, release = SPAWN.Event(), SPAWN.Event()
    holder = SPAWN.Process(target=_holding, args=(log_dir, held, release))
    holder.start()
    try:
        assert held.wait(BOUND)
        tip = _git("--git-dir", str(context), "rev-parse", "main")
        got = pipeline.publish_dir(_bundle(tmp_path / "bundle", MEMBERS[0]), str(context),
                                   project=_member(MEMBERS[0]),
                                   subpath=pipeline.okf_subpath(MEMBERS[0]), message="m",
                                   what="module map @ c1", timeout=0.5)
    finally:
        release.set()
        holder.join(BOUND)

    assert got == pipeline.BUSY, got
    assert _git("--git-dir", str(context), "rev-parse", "main") == tip, "it pushed anyway"
    assert "module map @ c1 not published" in caplog.text, caplog.text


def test_the_system_layer_holding_the_semaphore_is_not_held_up_by_its_own_publish(tmp_path,
                                                                                  context,
                                                                                  monkeypatch):
    """The system layer holds the semaphore around its two publishes; each publish takes it again,
    and must not wait for its own holder."""
    from openfactory.product import semaphore

    monkeypatch.setenv("OPENFACTORY_LOG_DIR", str(tmp_path / "journal"))
    member = _member(MEMBERS[0])
    done: list[str] = []

    def _refresh() -> None:
        with semaphore.held(member, timeout=BOUND):
            done.append(pipeline.publish_dir(
                _bundle(tmp_path / "bundle", MEMBERS[0]), str(context), project=member,
                subpath=pipeline.okf_subpath(MEMBERS[0]), message="m", what="system", timeout=1))

    worker = threading.Thread(target=_refresh)
    worker.start()
    worker.join(BOUND)
    assert done == [pipeline.PUBLISHED], done


# ── 4. every push onto a base branch, read from the code ──────────────────────────────────────

#: The pushes that CREATE the context repository: nothing else can have written to it yet, and
#: each fails rather than overwrite if something did (neither forces). Declared, with the reason;
#: a declaration whose function no longer pushes is reported, so this list cannot outlive its code.
BIRTHS = {
    ("openfactory/product/onboard.py", "seed_context_repository"):
        "`project init` and `product start` seeding the repository one of them has just "
        "created, before any role runs",
    ("openfactory/onboarding/onboard.py", "onboard_product_context"):
        "onboarding's first commit to a born-empty context repository (no base to propose to)",
}


class _Code:
    """Every module of the package, parsed once, with what this rule needs to read from it."""

    def __init__(self) -> None:
        self.trees: dict[str, ast.Module] = {}
        self._parents: dict[str, dict[ast.AST, ast.AST]] = {}
        #: every call in the package, by the name it calls
        self.calls: dict[str, list[tuple[str, ast.Call]]] = {}
        #: per module, what it imports: `(module, name) -> local name`, and modules by local name
        self.imported: dict[str, dict[tuple[str, str], str]] = {}
        self.modules: dict[str, dict[str, str]] = {}
        for path in sorted((ROOT / "openfactory").rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            tree = parsed(path)
            self.trees[rel] = tree
            self.imported[rel], self.modules[rel] = {}, {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    self.calls.setdefault(self.callee(node), []).append((rel, node))
                elif isinstance(node, ast.ImportFrom) and node.module:
                    for alias in node.names:
                        local = alias.asname or alias.name
                        self.imported[rel][(node.module, alias.name)] = local
                        self.modules[rel][local] = f"{node.module}.{alias.name}"
        self.wrappers = self._write_wrappers()

    def parents(self, rel: str) -> dict[ast.AST, ast.AST]:
        """Each node's parent in `rel`, worked out the first time a node there is asked about."""
        if rel not in self._parents:
            self._parents[rel] = {child: node for node in ast.walk(self.trees[rel])
                                  for child in ast.iter_child_nodes(node)}
        return self._parents[rel]

    @staticmethod
    def module_of(rel: str) -> str:
        return rel[:-3].replace("/", ".").removesuffix(".__init__")

    @staticmethod
    def callee(call: ast.Call) -> str:
        f = call.func
        return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""

    def enclosing(self, rel: str, node: ast.AST) -> ast.AST | None:
        par = self.parents(rel)
        while node in par:
            node = par[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node
        return None

    def base_pushes(self) -> list[tuple[str, int, str]]:
        """`(module, line, function)` of every git push onto a branch that is not a fresh one:
        a `push` whose target is not a proposal `branch` and that does not `--force`."""
        found = []
        for rel, tree in self.trees.items():
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Call, ast.List, ast.Tuple)):
                    continue
                parts = node.args if isinstance(node, ast.Call) else node.elts
                words = [p.value for p in parts if isinstance(p, ast.Constant)]
                if "push" not in words or "--force" in words:
                    continue
                if isinstance(node, ast.Call) and any(
                        isinstance(p, (ast.List, ast.Tuple)) for p in parts):
                    continue   # the list inside is the push, and is read on its own
                last = parts[-1] if parts else None
                if isinstance(last, ast.Name) and last.id == "branch":
                    continue   # a proposal branch of its own, for review: nobody else's base
                fn = self.enclosing(rel, node)
                found.append((rel, node.lineno, fn.name if fn else "<module>"))
        return found

    def _write_wrappers(self) -> set[str]:
        """The functions that hand their own `write` to `semaphore.check_and_write`, which runs it
        under the semaphore — asked of the code."""
        names = {"check_and_write"}
        for tree in self.trees.values():
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                params = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
                for call in ast.walk(fn):
                    if isinstance(call, ast.Call) and self.callee(call) == "check_and_write" and \
                            any(k.arg == "write" and isinstance(k.value, ast.Name)
                                and k.value.id in params for k in call.keywords):
                        names.add(fn.name)
        return names

    def held_at(self, rel: str, node: ast.AST) -> bool:
        """Inside `with ….held(<project>, …)` (the product's semaphore takes the project first; a
        bare file lock's `.held(timeout=…)` takes none), or inside the `write=` a wrapper runs."""
        par = self.parents(rel)
        child = node
        while child in par:
            up = par[child]
            if isinstance(up, (ast.With, ast.AsyncWith)) and child in up.body and any(
                    isinstance(i.context_expr, ast.Call) and self.callee(i.context_expr) == "held"
                    and i.context_expr.args for i in up.items):
                return True
            if isinstance(up, ast.keyword) and up.arg == "write":
                call = par.get(up)
                if isinstance(call, ast.Call) and self.callee(call) in self.wrappers:
                    return True
            if isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return False
            child = up
        return False

    def calls_of(self, rel: str, name: str) -> list[tuple[str, ast.Call]]:
        """Every call that reaches `name` defined in `rel`: by its name where it is defined or
        imported from there, or as an attribute of that module."""
        home = self.module_of(rel)
        found = []
        for other, call in self.calls.get(name, []):
            f = call.func
            if isinstance(f, ast.Name):
                if (other == rel and f.id == name) or \
                        self.imported[other].get((home, name)) == f.id:
                    found.append((other, call))
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and \
                    self.modules[other].get(f.value.id) == home:
                found.append((other, call))
        return found

    def holds(self, rel: str, fn: ast.AST, line: int, seen: tuple = ()) -> tuple[bool, str]:
        """Whether the push at `line` of `fn` always runs with the product's semaphore held."""
        site = next(n for n in ast.walk(fn) if getattr(n, "lineno", None) == line)
        if self.held_at(rel, site):
            return True, ""
        return self.reached_held(rel, fn.name, seen)

    def reached_held(self, rel: str, name: str, seen: tuple) -> tuple[bool, str]:
        if (rel, name) in seen:
            return False, f"{name} reaches itself"
        calls = self.calls_of(rel, name)
        if not calls:
            return False, f"{rel}::{name} is reached by no call that holds it"
        for other, call in calls:
            if self.held_at(other, call):
                continue
            up = self.enclosing(other, call)
            if up is None:
                return False, f"{other}:{call.lineno} calls {name} outside any function"
            ok, why = self.reached_held(other, up.name, (*seen, (rel, name)))
            if not ok:
                return False, f"{other}:{call.lineno} ({up.name}) → {why}"
        return True, ""


@pytest.fixture(scope="module")
def code() -> _Code:
    return _Code()


def test_every_push_onto_a_context_repositorys_base_holds_the_products_semaphore(code):
    pushes = code.base_pushes()
    assert any(rel == "openfactory/knowledge/pipeline.py" for rel, _line, _fn in pushes), (
        "the scan no longer finds the module map's own push — it reads nothing")

    unheld = []
    for rel, line, name in pushes:
        if (rel, name) in BIRTHS:
            continue
        fn = next(n for n in ast.walk(code.trees[rel])
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
        ok, why = code.holds(rel, fn, line)
        if not ok:
            unheld.append(f"{rel}:{line} ({name}): {why}")
    assert not unheld, ("pushes onto a context repository's base without the product's semaphore "
                        "— a person's save pushes once, and one of these landing between their "
                        "clone and their push makes it fail:\n" + "\n".join(unheld))

    stale = set(BIRTHS) - {(rel, name) for rel, _line, name in pushes}
    assert not stale, f"declared births that no longer push: {sorted(stale)}"


def test_every_publish_names_the_product_whose_semaphore_it_takes(code):
    """`project` is a required keyword, so a call without it fails — but only when it runs. A
    command nobody's test runs (`openfactory knowledge build`) is read here instead."""
    missing = []
    for name in ("publish_dir", "publish_bundle"):
        for rel, node in code.calls.get(name, []):
            given = {k.arg: k.value for k in node.keywords}
            if "project" not in given or (isinstance(given["project"], ast.Constant)
                                          and given["project"].value is None):
                missing.append(f"{rel}:{node.lineno}")
    assert not missing, f"publishes that name no product: {missing}"
