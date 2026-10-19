"""Every credential the core reads comes through the credential store — measured over the code (#742).

THE RULE, AND WHY IT IS A SWEEP. A store that most readers ask is a store a deployment cannot rely
on: a secret mounted as a file reaches the readers that ask the store and silently does not reach
the one that still reads its variable, and that one fails three layers away as a credential that
"is not configured". So the guard is not a list of the readers this change moved. It walks every
module of the package and finds every place that reads a CREDENTIAL from the process environment
by a name the code spells, and only the store may.

WHAT A CREDENTIAL IS comes from the rule `SECURITY.md`'s measured table already uses
(`_holds_a_credential`): the last words of a variable's name say what it holds. Shared, so the two
guards cannot disagree about what a secret is.

WHAT A READ IS, in every shape the package has used:

  · the environment itself: `os.environ.get("X")`, `os.environ["X"]`, `os.getenv("X")`, and the
    same keyed by a module-level name bound to the literal;
  · an ALIAS of it: a name or attribute assigned from an expression holding `os.environ` or
    another alias (`env = dict(os.environ)`, `self._env = dict(env)`), read with `.get` or `[]`;
  · a function HANDED it: `f(os.environ)` makes `f`'s parameter an alias inside `f`, which is how
    the harness's token pool was read (`_pool_in(os.environ)`);
  · a READER: a function that reads the environment (or an alias of it) by one of its own
    parameters, called with a credential's name;
  · a TABLE (review of #822): a read keyed by a loop over a table the code spells — a tuple or a
    list of names, a module constant bound to one, a slice or a union of those — is a read of
    every name in it (`for var in _AUTH_ENV_VARS: os.environ.get(var)`). A slice is read as its
    whole table, erring towards including, as the credential rule does;
  · and the environment HANDED TO A READER OF NAMES IT DOES NOT SPELL: a function that reads what
    it is handed by a key no table here resolves — an auth route's `requires`, read from an
    object — is said at the call that hands it the environment, because no name is visible at the
    read. That is how onboarding read the harness credential (`route.missing(dict(os.environ))`)
    while every reader around it asked the store.

What is NOT a read: a write (`env["GH_TOKEN"] = token` hands a subprocess its token), a `pop`
whose value nobody takes (that is a scrub), and a name nobody spells (a loop over `box.env`, whose
names are a deployment's) inside a function nobody hands the environment.
"""

from __future__ import annotations

import ast
import pathlib

from test_the_environment_carries_the_products_name import _holds_a_credential

from openfactory import environ

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "openfactory"
#: The one place the environment is read for a credential: the store, whose `env` kind and whose
#: `stored` ARE that read.
STORE = PACKAGE / "adapters" / "credential_store"


def _is_the_environment(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "environ"
            and isinstance(node.value, ast.Name) and node.value.id == "os")


def _callee(node: ast.Call) -> str:
    return getattr(node.func, "id", "") or getattr(node.func, "attr", "")


def _params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    return [a.arg for a in (*fn.args.posonlyargs, *fn.args.args)]


#: The methods a read through an alias goes by — read as such by `_key`, never as a reader's name.
_MAPPING = frozenset({"get", "pop", "setdefault"})


class _Module:
    """One module, walked once: its nodes, which of them hold `os.environ`, and its aliases."""

    def __init__(self, path: pathlib.Path) -> None:
        text = path.read_text(encoding="utf-8")
        self.path, self.tree = path, ast.parse(text)
        self.nodes = list(ast.walk(self.tree))
        self.holds: dict[int, bool] = {}
        #: node → the functions it sits in, innermost last: a parameter is an alias only there
        self.within: dict[int, tuple[int, ...]] = {}
        self._mark(self.tree, (), "environ" in text)
        self.discarded = {id(n.value) for n in self.nodes
                          if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)}
        #: assignment targets standing for the environment, module-wide (`self._env` crosses
        #: methods), and per function the parameters it is handed the environment through
        self.aliases: set[str] = set()
        self.params: dict[int, set[str]] = {}
        self.bound = {n.targets[0].id: environ._env_shaped(n.value) for n in self.tree.body
                      if isinstance(n, ast.Assign) and len(n.targets) == 1
                      and isinstance(n.targets[0], ast.Name) and environ._env_shaped(n.value)}
        #: module constants bound to a TABLE of names: `_AUTH_ENV_VARS = ("A", "B")`
        self.tables: dict[str, list[str]] = {}
        for n in self.tree.body:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                    and isinstance(n.targets[0], ast.Name) \
                    and (names := self.table(n.value)) is not None:
                self.tables[n.targets[0].id] = names
        self.parent = {id(child): node for node in self.nodes
                       for child in ast.iter_child_nodes(node)}

    def table(self, node: ast.AST) -> list[str] | None:
        """The names a table expression spells — a tuple, list or set of names (literals or module
        constants), a constant bound to one, a slice of one, or a union — or None when it is not
        one the code spells."""
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            names: list[str] = []
            for element in node.elts:
                inner = element.value if isinstance(element, ast.Starred) else element
                if isinstance(element, ast.Starred):
                    found = self.table(inner)
                    if found is None:
                        return None
                    names += found
                elif name := environ._key_of(inner, self.bound):
                    names.append(name)
                else:
                    return None
            return names
        if isinstance(node, ast.Name):
            return self.tables.get(node.id)
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            return self.table(node.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = self.table(node.left), self.table(node.right)
            return None if left is None or right is None else left + right
        return None

    def looped(self, read: ast.AST, key: ast.AST) -> list[ast.AST]:
        """The iterables the innermost loop binding `key`'s name walks, around `read` — `[]` when
        no loop around it binds that name."""
        if not isinstance(key, ast.Name):
            return []
        node = self.parent.get(id(read))
        while node is not None:
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name) \
                    and node.target.id == key.id:
                return [node.iter]
            if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                found = [g.iter for g in node.generators
                         if isinstance(g.target, ast.Name) and g.target.id == key.id]
                if found:
                    return found
            node = self.parent.get(id(node))
        return []

    def _mark(self, node: ast.AST, within: tuple[int, ...], look: bool) -> bool:
        self.within[id(node)] = within
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            within = (*within, id(node))
        hit = look and _is_the_environment(node)
        for child in ast.iter_child_nodes(node):
            hit = self._mark(child, within, look) or hit
        if look:
            self.holds[id(node)] = hit
        return hit

    def holds_the_environment(self, node: ast.AST) -> bool:
        return self.holds.get(id(node), False)

    def visible(self, node: ast.AST) -> set[str]:
        """The aliases a read at `node` may go through: the module's, and the parameters of every
        function it sits in."""
        out = set(self.aliases)
        for fn in self.within.get(id(node), ()):
            out |= self.params.get(fn, set())
        return out

    def alias(self, handed: set[tuple[str, object]]) -> None:
        """What stands for the environment here: the parameters of functions it is handed to,
        assignment targets, and — to a fixpoint — whatever is assigned from one of those
        (`env = dict(os.environ)`, then `self._env = dict(env)`)."""
        for node in self.nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = _params(node)
                # a method called on its class or instance: the first argument is the second param
                shift = 1 if params[:1] in (["self"], ["cls"]) else 0
                names = {name for i, name in enumerate(params)
                         if (node.name, i - shift) in handed or (node.name, name) in handed}
                names |= {kw.arg for kw in node.args.kwonlyargs if (node.name, kw.arg) in handed}
                if names:
                    self.params[id(node)] = names
        if not (self.holds or self.params):
            return
        assignments = [(n, [ast.unparse(t) for t in (n.targets if isinstance(n, ast.Assign)
                                                     else [n.target])],
                        self.holds_the_environment(n.value),
                        {ast.unparse(part) for part in ast.walk(n.value)
                         if isinstance(part, (ast.Name, ast.Attribute))})
                       for n in self.nodes
                       if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None]
        while True:
            grown = {t for n, targets, holds, parts in assignments for t in targets
                     if holds or parts & self.visible(n)} - self.aliases
            if not grown:
                return
            self.aliases |= grown

    def key(self, node: ast.AST) -> ast.AST | None:
        """The key expression when `node` reads the environment or an alias of it, else None."""
        if isinstance(node, ast.Call) and id(node) in self.discarded and _callee(node) == "pop":
            return None  # a scrub: the value is dropped, nothing is read
        if isinstance(node, ast.Subscript) and not isinstance(node.ctx, ast.Load):
            return None  # a write hands a value over; it reads nothing
        key = environ._reads_environ(node)
        if key is not None or not (self.aliases or self.params):
            return key
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args \
                and node.func.attr in _MAPPING \
                and ast.unparse(node.func.value) in self.visible(node):
            return node.args[0]
        if isinstance(node, ast.Subscript) and ast.unparse(node.value) in self.visible(node):
            return node.slice
        return None


def credential_reads(root: pathlib.Path = PACKAGE,
                     exempt: pathlib.Path | None = STORE) -> list[tuple[str, int, str]]:
    """`(path, line, name)` for every credential read from the environment by a spelled name,
    anywhere under `root` but `exempt`. See the module for the shapes."""
    modules = [_Module(p) for p in sorted(root.rglob("*.py"))]

    # every argument that carries the environment, by (function name, position or keyword)
    handed: set[tuple[str, object]] = set()
    for module in modules:
        if not module.holds:
            continue
        for node in module.nodes:
            if isinstance(node, ast.Call):
                for i, arg in enumerate(node.args):
                    if module.holds_the_environment(arg):
                        handed.add((_callee(node), i))
                for kw in node.keywords:
                    if kw.arg and module.holds_the_environment(kw.value):
                        handed.add((_callee(node), kw.arg))
    for module in modules:
        module.alias(handed)

    def outside(module: _Module) -> bool:
        return exempt is None or not module.path.is_relative_to(exempt)

    reads = {id(m): {id(n): (n, k) for n in m.nodes if (k := m.key(n)) is not None}
             for m in modules}

    # readers: functions that read the environment by one of their own parameters
    readers: set[str] = set()
    for module in modules:
        if not (outside(module) and reads[id(module)]):
            continue
        for fn in module.nodes:
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = set(_params(fn)) | {a.arg for a in fn.args.kwonlyargs}
                for node in ast.walk(fn):
                    read = reads[id(module)].get(id(node))
                    if read is not None and params & {n.id for n in ast.walk(read[1])
                                                      if isinstance(n, ast.Name)}:
                        readers.add(fn.name)

    # TABLE READERS: functions handed the environment that read it by a key no table resolves —
    # not a literal, not a loop over a spelled table, not one of their own parameters
    table_readers: set[str] = set()
    for module in filter(outside, modules):
        for fn in module.nodes:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    or id(fn) not in module.params:
                continue
            own = set(_params(fn)) | {a.arg for a in fn.args.kwonlyargs}
            for node in ast.walk(fn):
                read = reads[id(module)].get(id(node))
                if read is None:
                    continue
                key = read[1]
                if isinstance(key, (ast.Constant, ast.Slice)) or environ._key_of(key, module.bound):
                    continue
                if isinstance(key, ast.Name) and key.id in own:
                    continue  # a reader by its parameter, held where it is called
                walked = module.looped(node, key)
                if walked and all(module.table(i) is not None for i in walked):
                    continue  # a loop over a table this code spells, held below
                table_readers.add(fn.name)
                break

    found: list[tuple[str, int, str]] = []
    for module in filter(outside, modules):
        rel = module.path.relative_to(root.parent).as_posix()
        for node, key in reads[id(module)].values():
            name = environ._key_of(key, module.bound)
            if name and _holds_a_credential(name):
                found.append((rel, node.lineno, name))
            for walked in module.looped(node, key):
                for each in module.table(walked) or ():
                    if _holds_a_credential(each):
                        found.append((rel, node.lineno, each))
        for node in module.nodes:
            if isinstance(node, ast.Call) and _callee(node) in table_readers and any(
                    module.holds_the_environment(a)
                    for a in (*node.args, *(kw.value for kw in node.keywords))):
                found.append((rel, node.lineno,
                              f"the environment, handed to `{_callee(node)}`, which reads it by "
                              f"names this code does not spell"))
        for node in module.nodes:
            # A MAPPING'S OWN METHODS ARE NOT READERS BY NAME: `.get` on an alias is read above,
            # and a `get(name)` helper somewhere must not make every `.get` in the package one.
            if isinstance(node, ast.Call) and _callee(node) in readers and not (
                    isinstance(node.func, ast.Attribute) and node.func.attr in _MAPPING):
                for arg in node.args:
                    name = environ._key_of(arg, module.bound)
                    if name and _holds_a_credential(name):
                        found.append((rel, node.lineno, name))
    return sorted(set(found))


def test_no_module_but_the_store_reads_a_credential_from_the_environment():
    """The family's rule, over the whole package."""
    found = credential_reads()
    assert not found, (
        "these read a credential from the process environment instead of through the credential "
        "store (`adapters/credential_store/registry.py::stored`), so a secret the deployment "
        "mounts as a file never reaches them:\n  "
        + "\n  ".join(f"{path}:{line}: {name}" for path, line, name in found))


def test_the_sweep_covers_the_package_and_exempts_only_the_store():
    """The verifier of the exemption: it is one directory, it exists, and the sweep, pointed at
    the store itself, sees the store reading the environment — so an exemption that grew to
    swallow the package, or a walk that stopped walking, cannot pass as compliance."""
    assert STORE.is_dir() and STORE.parent.parent == PACKAGE
    assert len(list(PACKAGE.rglob("*.py"))) > 300
    inside = credential_reads(STORE, exempt=None)
    assert any(name == "OPENFACTORY_CREDENTIAL_DIR" for _, _, name in inside), inside


def test_the_sweep_SEES_every_shape_of_read_and_nothing_else(tmp_path):
    """Plant each shape the module names, and each thing it says is not a read."""
    pkg = tmp_path / "openfactory"
    pkg.mkdir()
    (pkg / "planted.py").write_text(
        "import os\n"
        "SECRET = 'ACME_SIGNING_SECRET'\n"
        "a = os.environ.get('ACME_DIRECT_TOKEN')\n"
        "b = os.environ['ACME_SUBSCRIPT_KEY']\n"
        "c = os.getenv('ACME_GETENV_PASSWORD')\n"
        "d = os.environ.get(SECRET)\n"
        "os.environ['ACME_EXPORTED_TOKEN'] = 'x'\n"
        "def aliased():\n"
        "    env = dict(os.environ)\n"
        "    env['ACME_WRITTEN_TOKEN'] = 'x'\n"
        "    return env.get('ACME_ALIAS_TOKEN')\n"
        "class Holder:\n"
        "    def __init__(self, env=None):\n"
        "        self._env = dict(env if env is not None else os.environ)\n"
        "    def token(self):\n"
        "        return self._env.get('ACME_ATTRIBUTE_TOKEN')\n"
        "def copied():\n"
        "    snapshot = dict(os.environ)\n"
        "    kept = dict(snapshot)\n"
        "    return kept['ACME_COPIED_TOKEN']\n"
        "def handed(settings):\n"
        "    return settings.get('ACME_HANDED_TOKENS')\n"
        "e = handed(os.environ)\n"
        "def given_a_mapping(settings):\n"
        "    return settings.get('ACME_A_MAPPING_TOKEN')\n"
        "def read(name):\n"
        "    return os.environ.get(name)\n"
        "f = read('ACME_READER_PAT')\n"
        "os.environ.pop('ACME_SCRUBBED_TOKEN', None)\n"
        "g = os.environ.get('ACME_REGION')\n"
        "for name in ('ACME_LOOPED_TOKEN',):\n"
        "    h = os.environ.get(name)\n"
        "TABLE = ('ACME_TABLED_TOKEN', 'ACME_TABLED_REGION')\n"
        "j = [os.environ.get(n) for n in TABLE[1:] + ('ACME_UNIONED_SECRET',)]\n"
        "def deployments(project):\n"
        "    return [os.environ.get(n) for n in project.box.env]\n"
        "class Route:\n"
        "    requires = ()\n"
        "    def missing(self, present):\n"
        "        env = present or {}\n"
        "        return [n for group in self.requires for n in group if not env.get(n)]\n"
        "k = Route().missing(dict(os.environ))\n"
        "def by_table(settings):\n"
        "    return [settings.get(k) for k in ('ACME_PROJECT', 'ACME_ISSUE')]\n"
        "m = by_table(dict(os.environ))\n"
    )
    (pkg / "elsewhere.py").write_text(
        "from openfactory.planted import read\n"
        "i = read('ACME_IMPORTED_CREDENTIALS')\n")

    found = sorted(name for _, _, name in credential_reads(pkg, exempt=None))

    assert found == ["ACME_ALIAS_TOKEN", "ACME_ATTRIBUTE_TOKEN", "ACME_COPIED_TOKEN",
                     "ACME_DIRECT_TOKEN",
                     "ACME_GETENV_PASSWORD", "ACME_HANDED_TOKENS", "ACME_IMPORTED_CREDENTIALS",
                     "ACME_LOOPED_TOKEN", "ACME_READER_PAT", "ACME_SIGNING_SECRET",
                     "ACME_SUBSCRIPT_KEY", "ACME_TABLED_TOKEN", "ACME_UNIONED_SECRET",
                     "the environment, handed to `missing`, which reads it by names this code "
                     "does not spell"], found


def test_a_read_through_the_store_is_not_a_read_of_the_environment(tmp_path):
    """The twin: the store's own readers, called from outside, are what the rule asks for."""
    pkg = tmp_path / "openfactory"
    (pkg / "adapters" / "credential_store").mkdir(parents=True)
    (pkg / "adapters" / "credential_store" / "registry.py").write_text(
        "import os\n"
        "def stored(name):\n"
        "    return os.environ.get(name) or None\n")
    (pkg / "user.py").write_text(
        "from openfactory.adapters.credential_store.registry import stored\n"
        "token = stored('ACME_STORED_TOKEN')\n")

    assert credential_reads(pkg, exempt=pkg / "adapters" / "credential_store") == []
    assert credential_reads(pkg, exempt=None) != []
