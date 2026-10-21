"""A YAML file a repository holds is read without expanding aliases, and within bounds (#1005).

WHAT WAS WRONG: every reader called `yaml.safe_load`, or a `SafeLoader` of its own, on text a
repository holds. The safe loader refuses a tag that builds a Python object and nothing else. It
keeps anchors and aliases, so a small file parses to a value that shares itself many times over,
and the first walk of it — a model validating it, `str()`, a dump, a comparison — writes every
repetition out (#824: 3.5 GB and 52 seconds for the title of a 600-byte front matter). Nesting was
not bounded either: a file a thousand levels deep raised `RecursionError` out of every reader of
`product.yaml` (#842).

WHAT IS HELD HERE, READ FROM THE CODE:

1. ONE DOOR. Every module of `openfactory/` is read by its syntax tree, and the `yaml` module may
   be named outside `openfactory/util/yaml_io.py` only for its errors and its node classes:
   reading, scanning, composing, writing, a loader or a dumper — by attribute, by `from yaml
   import`, through a submodule, or another YAML library — is a failure naming the line.
   `OUTSIDE_THE_DOOR` is where a parse would be let through with its reason; it is empty, because
   the files the package ships go through the door too (a test below reads each of them).
2. EVERY READER. The functions that read through the door are listed from the same trees, and each
   has a row in `READERS` saying how a document reaches it and how it answers a file it cannot
   read — so a new reader is red until it has one. An aliased document, one long value repeated
   by aliases, a deeply nested one and an oversized one are fed to every row, and each must be refused by name, inside the reader's own
   contract (a sentence, a finding, a refusal it raises — or its absent value, with the refusal in
   the log), in under a second. The aliased document is the same for every reader and answered two
   ways, which holds which loader each reader uses: a reader of the core's own files names the
   anchor, a reader of a compose file or a CI pipeline (formats whose specification has anchors)
   names the size its aliases come to.
3. THE DOOR ITSELF: each bound at its limit and on either side, the sentences word for word, an
   alias counted at the size, the depth and the bytes of what it repeats, a value that contains
   itself.
4. THE WRITER: what the core writes carries no alias, so it reads back through the door.
"""

from __future__ import annotations

import ast
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from openfactory import namespace
from openfactory.adapters.extract.text import front_matter
from openfactory.adapters.preview import compose as preview_compose
from openfactory.adapters.tracker.parse import _split_front_matter
from openfactory.certify.verify import ThresholdsError, load_thresholds
from openfactory.cli import _builds_from_this_checkout
from openfactory.knowledge import bundle, okf
from openfactory.knowledge.flows import FLOWS_FILE, read_flows
from openfactory.knowledge.system import tree
from openfactory.knowledge.system.render import SYSTEM_DIRNAME, SYSTEM_FILE, read_derived_key
from openfactory.knowledge.system.text import load_yaml
from openfactory.loader import load_manifest
from openfactory.onboarding import preview_infer, preview_propose
from openfactory.onboarding.infer import _load_yaml as _load_pipeline
from openfactory.orchestrator import context, explain
from openfactory.orchestrator.machine import JobRunner
from openfactory.policy import profiles
from openfactory.preflight import _probe_sandbox_image
from openfactory.preview.product import _declares_preview, read_docs
from openfactory.preview.read import prescan
from openfactory.product import onboard as product_onboard
from openfactory.product.capabilities import parse_capability
from openfactory.product.cards import Rubric
from openfactory.product.evaluation.battery import BatteryRefused, load_battery
from openfactory.product.evaluation.run import FixtureRefused, fixture_name
from openfactory.product.loader import DOCS_MANIFEST, _read_docs_manifest, parse_docs_manifest
from openfactory.product.role import ProductRole
from openfactory.product.sight import look, system_or_why
from openfactory.registry import ProjectRegistry, seed_registry
from openfactory.util import yaml_io

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "openfactory"
DOOR = "openfactory/util/yaml_io.py"

# ── 1. one door ─────────────────────────────────────────────────────────────────────────────────

#: what a module other than the door may name of the `yaml` module: the errors a reader catches,
#: and the node classes a constructor of one of the door's loaders is handed. None of them reads
#: or writes anything.
NAMED = frozenset({"YAMLError", "MarkedYAMLError", "Node", "ScalarNode", "SequenceNode",
                   "MappingNode"})

#: the other YAML libraries for Python; none is a dependency, and one arriving is a second door
OTHER_LIBRARIES = frozenset({"ruamel", "ruyaml", "oyaml", "strictyaml", "yamlcore"})

#: `path → why` for a module that may parse YAML outside the door. EMPTY: the package's own files
#: — `org_defaults/floor.yaml`, the presets, the shipped profiles, rubric and thresholds — are read
#: through the door like any other, which costs nothing (`test_every_yaml_file_the_package_ships_
#: reads_through_the_door`). An entry here must name a file the package ships and say why the door
#: cannot read it.
OUTSIDE_THE_DOOR: dict[str, str] = {}


def _ways_in(source: str, where: str) -> list[str]:
    """`file:line: what` for every use of a YAML library in `source` other than `NAMED`."""
    tree_ = ast.parse(source)
    parents = {child: node for node in ast.walk(tree_) for child in ast.iter_child_nodes(node)}
    bound: set[str] = set()
    found: list[str] = []
    for node in ast.walk(tree_):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if alias.name == "yaml":
                    bound.add(alias.asname or "yaml")
                elif top == "yaml" or top in OTHER_LIBRARIES:
                    found.append(f"{where}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if node.module == "yaml":
                found += [f"{where}:{node.lineno}: from yaml import {a.name}"
                          for a in node.names if a.name not in NAMED]
            elif top == "yaml" or top in OTHER_LIBRARIES:
                found.append(f"{where}:{node.lineno}: from {node.module} import …")
        elif (isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
              and (node.func.id if isinstance(node.func, ast.Name) else node.func.attr)
              in ("import_module", "__import__")
              and any(isinstance(a, ast.Constant) and str(a.value).split(".")[0] in
                      {"yaml", *OTHER_LIBRARIES} for a in node.args)):
            found.append(f"{where}:{node.lineno}: a YAML library imported by name")
    for node in ast.walk(tree_):
        if not (isinstance(node, ast.Name) and node.id in bound):
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Attribute) and parent.value is node:
            if parent.attr not in NAMED:
                found.append(f"{where}:{node.lineno}: yaml.{parent.attr}")
        elif not isinstance(parent, ast.alias):
            found.append(f"{where}:{node.lineno}: the yaml module handed on as a value")
    return found


def _modules() -> dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(PACKAGE.rglob("*.py"))}


def test_no_module_but_the_door_reads_or_writes_yaml():
    found = [line for rel, source in _modules().items()
             if rel != DOOR and rel not in OUTSIDE_THE_DOOR for line in _ways_in(source, rel)]
    assert found == [], (
        "YAML is read and written only through `openfactory/util/yaml_io.py` — `yaml_io.load` "
        "(with `loader=yaml_io.CountingLoader` for a format whose specification has anchors), "
        "`yaml_io.tokens` and `yaml_io.dump`. Outside it the yaml module names only its errors and "
        "its node classes:\n  " + "\n  ".join(found))


def test_every_module_let_outside_the_door_says_why_and_still_reads_yaml():
    for rel, why in OUTSIDE_THE_DOOR.items():
        assert len(why.split()) >= 8, f"{rel}: say why the door cannot read what it reads"
        assert _ways_in((ROOT / rel).read_text(encoding="utf-8"), rel), f"{rel} parses nothing now"


@pytest.mark.parametrize("source", [
    "import yaml\nyaml.safe_load(text)\n",
    "import yaml as y\ny.load(text, Loader=y.SafeLoader)\n",
    "import yaml\nfor t in yaml.scan(text): pass\n",
    "import yaml\nclass L(yaml.SafeLoader):\n    pass\n",
    "import yaml\nyaml.safe_dump(data)\n",
    "import yaml\nf = getattr(yaml, 'safe_load')\n",
    "from yaml import safe_load\n",
    "from yaml import CSafeLoader as L\n",
    "import yaml.composer\n",
    "from yaml.constructor import SafeConstructor\n",
    "from ruamel.yaml import YAML\n",
    "import importlib\nimportlib.import_module('yaml')\n",
])
def test_the_reader_of_the_trees_catches_each_way_in(source):
    assert _ways_in(source, "m.py")


@pytest.mark.parametrize("source", [
    "import yaml\ntry:\n    pass\nexcept yaml.YAMLError:\n    pass\n",
    "import yaml\ndef c(loader, node: yaml.Node):\n    return isinstance(node, yaml.MappingNode)\n",
    "from yaml import YAMLError\n",
    "from openfactory.util import yaml_io\nyaml_io.load(text)\n",
])
def test_the_reader_of_the_trees_lets_the_names_through(source):
    assert _ways_in(source, "m.py") == []


# ── 2. every reader ─────────────────────────────────────────────────────────────────────────────

#: what the door's functions are called by a reader: a read, a scan, a loader started by hand
_READS = {"load", "tokens", "Loader", "CountingLoader"}


def _readers_in(source: str, where: str) -> set[str]:
    """`path::qualname` of every function in `source` that reads through the door."""
    tree_ = ast.parse(source)
    door: set[str] = set()      # names the door module is bound to
    direct: set[str] = set()    # names a reading function of the door is bound to
    for node in ast.walk(tree_):
        if isinstance(node, ast.ImportFrom) and node.module == "openfactory.util":
            door |= {a.asname or a.name for a in node.names if a.name == "yaml_io"}
        if isinstance(node, ast.ImportFrom) and node.module == "openfactory.util.yaml_io":
            direct |= {a.asname or a.name for a in node.names if a.name in _READS}
    found: set[str] = set()

    def walk(node: ast.AST, path: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                walk(child, [*path, child.name])
                continue
            if isinstance(child, ast.Call):
                f = child.func
                if ((isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                     and f.value.id in door and f.attr in _READS)
                        or (isinstance(f, ast.Name) and f.id in direct)):
                    found.add(f"{where}::{'.'.join(path) or '<module>'}")
            walk(child, path)

    walk(tree_, [])
    return found


def _every_reader() -> set[str]:
    return set().union(*(_readers_in(source, rel) for rel, source in _modules().items()
                         if rel != DOOR))


#: what a document of each kind is refused with, by the loader a reader uses: the refusing one
#: (the core's own files) and the counting one (a format whose specification has anchors)
SAID = {
    "aliased": {"own": "an anchor (`&a`, line ",
                "counting": "values once `*"},
    "repeated": {"own": "an anchor (`&s`, line ", "counting": "bytes of values once `*s`"},
    "deep": {"own": "nested deeper than 100 levels", "counting": "nested deeper than 100 levels"},
    "oversized": {"own": "-byte ceiling a YAML file is read to",
                  "counting": "-byte ceiling a YAML file is read to"},
}

#: nine values, each level nine aliases of the one before: 531,441 values once walked, refused at
#: the anchor by the core's own reader and past 200,000 by the counting one
ALIASED = ("a: &a [x, x, x, x, x, x, x, x, x]\n"
           + "".join(f"{b}: &{b} [{', '.join(['*' + a] * 9)}]\n" for a, b in zip("abcde", "bcdef", strict=True)))
#: one value of 100,000 bytes, repeated by 120 aliases: a 100 KB file whose values come to 12 MB
#: once walked, refused at the anchor by the core's own reader and past 10 MB by the counting one
#: (the shape of the review of #1012, a size smaller)
REPEATED = "s: &s " + "a" * 100_000 + "\nl: [" + ", ".join(["*s"] * 120) + "]\n"
DEEP = "deep: " + "[" * 150 + "]" * 150 + "\n"
OVERSIZED = 'big: "' + "a" * yaml_io.MAX_BYTES + '"\n'
DOCUMENTS = {"aliased": ALIASED, "repeated": REPEATED, "deep": DEEP, "oversized": OVERSIZED}
#: what `knowledge/system/tree.read_text` says of a file past its byte ceiling, before the door
TREE_SAID = "-byte ceiling this layer reads"

#: a reader that answers with what was refused, in its own words around the door's sentence
SAYS = object()


@dataclass(frozen=True)
class Reader:
    """How a document reaches one reader, and how the reader answers a file it cannot read.

    `drive(tmp, text, monkeypatch)` puts `text` where the reader looks and returns its answer: the string (or
    strings) it says for a SAYS reader, the value itself otherwise. `absent` is SAYS, or the value
    the reader answers for a file it treats as absent — then the door's log names the refusal.
    `ceiling` is set where the reader reads through `knowledge/system/tree.read_text`, whose own
    byte ceiling refuses an oversized file before the door sees it."""

    drive: Callable[[Path, str, pytest.MonkeyPatch], object]
    absent: object = SAYS
    loader: str = "own"
    ceiling: bool = False


def _put(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fenced(text: str, body: str = "the body\n") -> str:
    return f"---\n{text.rstrip(chr(10))}\n---\n{body}"


def _raised(call: Callable[[], object], kind: type[BaseException]) -> str:
    try:
        call()
    except kind as exc:
        return str(exc)
    raise AssertionError(f"{call} answered instead of raising {kind.__name__}")


class _Project:
    name = "acme"
    manifest_path = namespace.MANIFEST


def _down(tmp: Path, text: str, monkeypatch) -> object:
    """The images `_down` would remove as built from the preview's own `compose.yml` — none, for a
    file it cannot read. Nothing reaches a daemon: every command is recorded and answered 1."""
    unit = f"{preview_compose.PREFIX}unit"
    _put(tmp / unit / "compose.yml", text)
    asked: list[list[str]] = []
    monkeypatch.setattr(preview_compose, "workdir_is_ours", lambda path: True)
    monkeypatch.setattr(preview_compose, "work_root", lambda: str(tmp))
    monkeypatch.setattr(preview_compose, "_remove_workdir", lambda path: [])
    monkeypatch.setattr(preview_compose, "_host", lambda argv, **k: (
        asked.append(list(argv)), preview_compose.Ran(rc=1, out="", err=""))[1])
    preview_compose.ComposeRuntime._down(SimpleNamespace(panel_container=""), unit,
                                         str(tmp / unit))
    return [argv[3:] for argv in asked if argv[:3] == ["docker", "image", "rm"]]


def _sandbox_image(tmp: Path, text: str, monkeypatch) -> object:
    _put(tmp / "docker-compose.yml", text)
    monkeypatch.chdir(tmp)
    monkeypatch.delenv("OPENFACTORY_SANDBOX_IMAGE", raising=False)
    return _probe_sandbox_image()


def _bundle(tmp: Path, text: str, mp) -> object:
    _put(tmp / bundle.MODULES_FILE, text)
    _put(tmp / bundle.MANIFEST_FILE, text)
    return bundle.read_bundle_dir(tmp)


def _seed(tmp: Path, text: str, mp) -> object:
    return seed_registry(seed=_put(tmp / "seed.yaml", text), live=tmp / "live" / "projects.yaml")


#: `path::qualname` of a reader → how it is driven. EVERY function that reads through the door is
#: here or in `NOT_A_FILE`, read from the code by `_every_reader`.
READERS: dict[str, Reader] = {
    "openfactory/adapters/extract/text.py::front_matter":
        Reader(lambda tmp, t, mp: front_matter(_fenced(t))[2]),
    "openfactory/adapters/preview/compose.py::ComposeRuntime._down":
        Reader(lambda tmp, t, mp: _down(tmp, t, mp), absent=[], loader="counting"),
    "openfactory/adapters/tracker/parse.py::_split_front_matter":
        Reader(lambda tmp, t, mp: _split_front_matter(_fenced(t))[0], absent={}),
    "openfactory/certify/verify.py::load_thresholds":
        Reader(lambda tmp, t, mp: _raised(lambda: load_thresholds(_put(tmp / "t.yaml", t)),
                                      ThresholdsError)),
    "openfactory/cli.py::_builds_from_this_checkout":
        Reader(lambda tmp, t, mp: (_put(tmp / "docker-compose.yml", t),
                               _builds_from_this_checkout(tmp))[1],
               absent=False, loader="counting"),
    "openfactory/knowledge/bundle.py::read_bundle_dir": Reader(_bundle, absent=None),
    "openfactory/knowledge/flows.py::read_flows":
        Reader(lambda tmp, t, mp: read_flows(_put(tmp / FLOWS_FILE, t).parent), absent=None,
               ceiling=True),
    "openfactory/knowledge/okf.py::parse_concept":
        Reader(lambda tmp, t, mp: okf.parse_concept(_fenced(t)), absent=None),
    "openfactory/knowledge/okf.py::parse_manifest":
        Reader(lambda tmp, t, mp: okf.parse_manifest(t), absent=None),
    "openfactory/knowledge/system/render.py::read_derived_key":
        Reader(lambda tmp, t, mp: read_derived_key(_put(tmp / SYSTEM_FILE, t).parent, SYSTEM_FILE),
               absent="", ceiling=True),
    "openfactory/knowledge/system/text.py::load_yaml":
        Reader(lambda tmp, t, mp: _raised(lambda: load_yaml(t), yaml.YAMLError), loader="counting"),
    "openfactory/loader.py::load_manifest":
        Reader(lambda tmp, t, mp: _raised(
            lambda: load_manifest(_Project(), repo_root=_put(tmp / namespace.MANIFEST, t)
                                  .parent.parent), ValueError)),
    "openfactory/onboarding/infer.py::_load_yaml":
        Reader(lambda tmp, t, mp: _load_pipeline(_put(tmp / ".gitlab-ci.yml", t)), absent=None,
               loader="counting"),
    "openfactory/onboarding/preview_infer.py::_declared":
        Reader(lambda tmp, t, mp: preview_infer._declared(_put(tmp / namespace.MANIFEST, t)
                                                      .parent.parent), absent=(None, None)),
    "openfactory/onboarding/preview_infer.py::_from_compose":
        Reader(lambda tmp, t, mp: preview_infer.infer_preview(
            _put(tmp / "compose.yaml", t).parent).compose.note, loader="counting"),
    "openfactory/onboarding/preview_infer.py::_manifest_setup":
        Reader(lambda tmp, t, mp: preview_infer._manifest_setup(_put(tmp / namespace.MANIFEST, t)
                                                            .parent.parent), absent=None),
    "openfactory/onboarding/preview_propose.py::_base_branch":
        Reader(lambda tmp, t, mp: preview_propose._base_branch(t), absent="main"),
    "openfactory/onboarding/preview_propose.py::merge_field":
        Reader(lambda tmp, t, mp: preview_propose.merge_field(t, "preview", {"compose": []}).refusal),
    "openfactory/orchestrator/context.py::_doc_summary":
        Reader(lambda tmp, t, mp: context._doc_summary(_put(tmp / "doc.md",
                                                        _fenced(t, "# The heading\n"))),
               absent="The heading"),
    "openfactory/orchestrator/explain.py::_manifest":
        Reader(lambda tmp, t, mp: _raised(lambda: explain._manifest(
            _put(tmp / "acme" / namespace.MANIFEST, t).parent.parent, "acme", "en"),
            explain.Refused)),
    "openfactory/orchestrator/machine.py::JobRunner._preview_shape":
        Reader(lambda tmp, t, mp: JobRunner._preview_shape(
            SimpleNamespace(_protected=(namespace.MANIFEST,), _SHAPE_NAMES=JobRunner._SHAPE_NAMES),
            SimpleNamespace(path=_put(tmp / namespace.MANIFEST, t).parent.parent)), absent=[]),
    "openfactory/policy/profiles.py::_read":
        Reader(lambda tmp, t, mp: _raised(lambda: profiles._read(_put(tmp / "bank.yaml", t)),
                                      profiles.ProfileError)),
    "openfactory/preflight.py::_probe_sandbox_image":
        Reader(lambda tmp, t, mp: _sandbox_image(tmp, t, mp), absent=None,
               loader="counting"),
    "openfactory/preview/product.py::_declares_preview":
        Reader(lambda tmp, t, mp: (_put(tmp / namespace.MANIFEST, t),
                               _declares_preview(str(tmp), namespace.MANIFEST))[1], absent=False),
    "openfactory/preview/read.py::prescan":
        Reader(lambda tmp, t, mp: prescan({"app/docker-compose.yml": t}).refused[0],
               loader="counting"),
    "openfactory/product/capabilities.py::parse_capability":
        Reader(lambda tmp, t, mp: parse_capability(_fenced(t), path="c/a.md")[1][0].message),
    "openfactory/product/cards.py::Rubric.parse":
        Reader(lambda tmp, t, mp: _raised(lambda: Rubric.parse(t), yaml.YAMLError)),
    "openfactory/product/evaluation/battery.py::load_battery":
        Reader(lambda tmp, t, mp: _raised(lambda: load_battery(_put(tmp / "b.yaml", t)),
                                      BatteryRefused)),
    "openfactory/product/evaluation/run.py::fixture_name":
        Reader(lambda tmp, t, mp: _raised(lambda: fixture_name(
            _put(tmp / "context" / DOCS_MANIFEST, t).parent.parent.parent), FixtureRefused)),
    # both readers of `product.yaml` reach it: the product module's, and the preview's
    "openfactory/product/loader.py::_safe_load":
        Reader(lambda tmp, t, mp: (_put(tmp / DOCS_MANIFEST, t),
                               _read_docs_manifest(tmp)[1], read_docs(str(tmp))[1])[1:]),
    "openfactory/product/onboard.py::_existing":
        Reader(lambda tmp, t, mp: product_onboard._existing(_put(tmp / DOCS_MANIFEST, t)), absent={}),
    "openfactory/product/sight.py::system_or_why":
        Reader(lambda tmp, t, mp: system_or_why(_put(tmp / okf.OKF_DIRNAME / SYSTEM_DIRNAME
                                                     / SYSTEM_FILE, t).parent.parent.parent)[1],
               ceiling=True),
    "openfactory/registry.py::ProjectRegistry._load_raw":
        Reader(lambda tmp, t, mp: _raised(lambda: ProjectRegistry(_put(tmp / "p.yaml", t))._load_raw(),
                                      ValueError)),
    "openfactory/registry.py::seed_registry": Reader(_seed, absent=False),
}

#: `path::qualname → why` for a function that reads through the door and is handed no file a
#: repository or a person holds. Each is still bounded by the door; it is not driven here.
NOT_A_FILE: dict[str, str] = {
    "openfactory/policy/presets.py::load_preset":
        "reads `openfactory/presets/<stack>.yaml`, a file the package ships, by a name the "
        "manifest's stack picks among the shipped ones",
    "openfactory/policy/presets.py::floor_document":
        "reads `openfactory/org_defaults/floor.yaml`, the floor every deployment inherits, which "
        "ships inside the package",
    "openfactory/onboarding/preview_propose.py::_scalar":
        "reads back a plain scalar it is about to write, to know whether it needs quotes; the "
        "text is one token of letters, digits and `_./@:+-`",
    "openfactory/product/loader.py::_as_written":
        "scans a text `_safe_load` has already read through the door, to spell a key as written",
}


def test_every_reader_through_the_door_is_driven_or_says_why_not():
    found = _every_reader()
    listed = set(READERS) | set(NOT_A_FILE)
    assert found - listed == set(), (
        f"read through the door with no row in READERS: {sorted(found - listed)} — say how a "
        f"document reaches it and how it answers one it cannot read")
    assert listed - found == set(), f"rows for readers that are gone: {sorted(listed - found)}"
    assert set(READERS).isdisjoint(NOT_A_FILE)
    for why in NOT_A_FILE.values():
        assert len(why.split()) >= 10, why


def test_the_reader_finder_reads_every_way_a_function_calls_the_door():
    source = ("from openfactory.util import yaml_io\n"
              "from openfactory.util.yaml_io import load as read\n"
              "def a(t):\n    return yaml_io.load(t)\n"
              "class K:\n    def b(self, t):\n        return yaml_io.Loader(t)\n"
              "def c(t):\n    return read(t)\n"
              "def d(t):\n    return list(yaml_io.tokens(t))\n"
              "def e(t):\n    return yaml_io.dump(t)\n")
    assert _readers_in(source, "m.py") == {"m.py::a", "m.py::K.b", "m.py::c", "m.py::d"}


def _text(answer: object) -> tuple[str, ...]:
    return tuple(str(a) for a in answer) if isinstance(answer, tuple) else (str(answer),)


@pytest.mark.parametrize("kind", DOCUMENTS)
@pytest.mark.parametrize("name", sorted(READERS))
def test_every_reader_refuses_by_name_and_in_under_a_second(name, kind, tmp_path, monkeypatch,
                                                            caplog):
    reader = READERS[name]
    tmp = tmp_path / "t"
    tmp.mkdir()
    said = (TREE_SAID if kind == "oversized" and reader.ceiling else SAID[kind][reader.loader])
    caplog.set_level(logging.WARNING, logger=yaml_io.log.name)
    started = time.perf_counter()
    answer = reader.drive(tmp, DOCUMENTS[kind], monkeypatch)
    took = time.perf_counter() - started
    assert took < 1.0, f"{name} took {took:.2f} s over a {kind} document"
    if reader.absent is SAYS:
        for text in _text(answer):
            assert said in text, f"{name} answered {text[:300]!r} for a {kind} document"
        return
    assert answer == reader.absent, f"{name} answered {answer!r} for a {kind} document"
    if kind == "oversized" and reader.ceiling:
        return  # refused by the tree's own byte ceiling, before the door was asked
    logged = [r.getMessage() for r in caplog.records if r.name == yaml_io.log.name]
    assert any(said in line for line in logged), (
        f"{name} answered its absent value for a {kind} document and nothing said why: {logged}")


#: the readers whose format has anchors: what a fragment of a compose file looks like, read whole
FRAGMENT = ("x-restart: &restart\n  restart: unless-stopped\n"
            "services:\n  web:\n    <<: *restart\n    image: nginx\n")


def test_a_reader_of_a_format_with_anchors_reads_a_fragment_and_one_of_the_cores_refuses_it():
    assert load_yaml(FRAGMENT)["services"]["web"] == {"restart": "unless-stopped",
                                                      "image": "nginx"}
    assert prescan({"app/docker-compose.yml": FRAGMENT}).refused == ()
    docs, error = parse_docs_manifest(FRAGMENT)
    assert docs is None and "an anchor (`&restart`, line 1): this file is read without" in error


#: the depth the door reads to, and either side of it (#842), as `product.yaml` writes it
@pytest.mark.parametrize("levels", [yaml_io.MAX_DEPTH - 1, yaml_io.MAX_DEPTH,
                                    yaml_io.MAX_DEPTH + 1, 1_000, 5_000])
def test_product_yaml_is_read_to_the_depth_limit_through_both_readers(levels, tmp_path):
    # the root mapping is one level and `x`'s value the second, so the innermost scalar sits at
    # `levels`: `x:` takes `levels - 2` brackets
    text = "product: books\nx: " + "[" * (levels - 2) + "1" + "]" * (levels - 2) + "\n"
    _put(tmp_path / DOCS_MANIFEST, text)
    for docs, error in (_read_docs_manifest(tmp_path), read_docs(str(tmp_path))):
        if levels <= yaml_io.MAX_DEPTH:
            assert "nested deeper" not in error
        else:
            assert docs is None
            assert error == (f"{DOCS_MANIFEST} is not valid YAML: nested deeper than "
                             f"{yaml_io.MAX_DEPTH} levels (line 2): a YAML file is read to "
                             f"{yaml_io.MAX_DEPTH} levels")


def test_an_unreadable_system_map_is_a_blind_spot_the_role_is_told(tmp_path):
    """Read as absent, a refused map said nothing to the role: it is a named line of the turn's
    blind spots, which is what the role reads as "where the map is thin"."""
    _put(tmp_path / okf.OKF_DIRNAME / SYSTEM_DIRNAME / SYSTEM_FILE, "a: &a [1]\nb: *a\n")
    sight = look(docs_root=tmp_path, root=tmp_path, mounts=[])
    rel = f"{okf.OKF_DIRNAME}/{SYSTEM_DIRNAME}/{SYSTEM_FILE}"
    said = (f"the system map could not be read this turn: `{rel}` is not valid YAML: an anchor "
            f"(`&a`, line 1): this file is read without anchors or aliases — write the value out "
            f"where it is used — nothing it maps is known")
    assert sight.system is None
    assert any(line.startswith(said) for line in sight.blind), sight.blind
    briefed = ProductRole._blind_spots_section(SimpleNamespace(sight=sight))
    assert any(line.startswith(f"- {said}") for line in briefed), briefed


def test_a_system_map_that_is_not_published_is_no_blind_spot(tmp_path):
    assert system_or_why(tmp_path) == (None, "")
    sight = look(docs_root=tmp_path, root=tmp_path, mounts=[])
    assert not any("system map could not be read" in line for line in sight.blind)


# ── 3. the door itself ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("text", "said"), [
    ("a: &x 1\n", "an anchor (`&x`, line 1)"),
    ("a: 1\nb: &x [1]\n", "an anchor (`&x`, line 2)"),
    ("a: &x {b: 1}\n", "an anchor (`&x`, line 1)"),
    ("a: *x\n", "an alias (`*x`, line 1)"),
])
def test_the_refusing_loader_names_the_anchor_or_the_alias_and_the_line(text, said):
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load(text)
    assert str(refused.value) == (f"{said}: this file is read without anchors or aliases — write "
                                  f"the value out where it is used")
    assert isinstance(refused.value, yaml.YAMLError) and refused.value.problem == str(refused.value)


def test_the_counting_loader_reads_an_alias_as_the_value_it_repeats():
    data = yaml_io.load("a: &x [1, 2]\nb: *x\nc: {<<: {d: 1}}\n", loader=yaml_io.CountingLoader)
    assert data == {"a": [1, 2], "b": [1, 2], "c": {"d": 1}}


def test_an_alias_inside_the_value_it_repeats_is_refused():
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load("a: &x [1, *x]\n", loader=yaml_io.CountingLoader)
    assert str(refused.value) == ("an alias inside the value it repeats (`*x`, line 1): a value "
                                  "that contains itself cannot be read")


@pytest.mark.parametrize("loader", [yaml_io.Loader, yaml_io.CountingLoader])
def test_the_depth_limit_holds_at_the_limit_and_on_either_side(loader):
    def nested(levels: int) -> str:
        return "[" * (levels - 1) + "1" + "]" * (levels - 1)

    yaml_io.load(nested(yaml_io.MAX_DEPTH), loader=loader)
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load(nested(yaml_io.MAX_DEPTH + 1), loader=loader)
    assert str(refused.value) == (f"nested deeper than {yaml_io.MAX_DEPTH} levels (line 1): a "
                                  f"YAML file is read to {yaml_io.MAX_DEPTH} levels")
    started = time.perf_counter()
    with pytest.raises(yaml_io.YamlRefused):
        yaml_io.load(nested(1_000), loader=loader)
    # about 0.1 s on an idle machine: PyYAML's scanner looks up to 1,024 characters ahead at every
    # unclosed bracket on a line, and the composer stops at level 101
    assert time.perf_counter() - started < 1.0
    with pytest.raises(yaml_io.YamlRefused):  # refused, never `RecursionError`
        yaml_io.load(nested(5_000), loader=loader)


def test_an_alias_counts_at_the_depth_of_what_it_repeats():
    # each anchor one level deeper than the one before: 1 + 2 + … levels once walked
    chain = "".join(f"k{i}: &k{i} [{f'*k{i - 1}' if i else 1}]\n" for i in range(110))
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load(chain, loader=yaml_io.CountingLoader)
    assert str(refused.value).startswith(
        f"nested deeper than {yaml_io.MAX_DEPTH} levels once `*k")
    assert "is counted at the depth of what it repeats" in str(refused.value)


@pytest.mark.parametrize("loader", [yaml_io.Loader, yaml_io.CountingLoader])
def test_the_value_limit_holds_at_the_limit_and_one_past_it(loader, monkeypatch):
    monkeypatch.setattr(yaml_io, "MAX_NODES", 10)
    assert yaml_io.load("[" + ", ".join("1" * 9) + "]", loader=loader) == [1] * 9  # 10 values
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load("[" + ", ".join("1" * 10) + "]", loader=loader)
    assert str(refused.value) == "more than 10 values (line 1): a YAML file is read to 10 values"


def test_an_alias_counts_at_the_size_of_what_it_repeats(monkeypatch):
    monkeypatch.setattr(yaml_io, "MAX_NODES", 12)
    # root, a, its list and three items (6), b and its list (8), and *x at its four: 12
    assert yaml_io.load("a: &x [1, 2, 3]\nb: [*x]\n", loader=yaml_io.CountingLoader)
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load("a: &x [1, 2, 3]\nb: [*x, 4]\n", loader=yaml_io.CountingLoader)
    assert str(refused.value) == "more than 12 values (line 2): a YAML file is read to 12 values"
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load("a: &x [1, 2, 3]\nb: [4, *x]\n", loader=yaml_io.CountingLoader)
    assert str(refused.value) == ("more than 12 values once `*x` is counted at the size of what it "
                                  "repeats (line 2): a YAML file is read to 12 values")


#: the shape of the review of #1012, whole: one value of 900 KB, repeated by 30,000 aliases, in a
#: file under the byte ceiling — 27 GB once walked
LONG = "s: &s " + "a" * 900_000 + "\nl: [" + ",".join(["*s"] * 30_000) + "]\n"


def test_a_long_value_repeated_by_aliases_is_refused_by_the_bytes_it_comes_to():
    assert len(LONG.encode()) < yaml_io.MAX_BYTES
    started = time.perf_counter()
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load(LONG, loader=yaml_io.CountingLoader)
    # the scanner reads the 900 KB string once; the refusal comes at the twelfth alias of 30,000
    assert time.perf_counter() - started < 2.0
    assert str(refused.value) == (
        "more than 10,000,000 bytes of values once `*s` is counted at the size of what it repeats "
        "(line 2): a YAML file is read to 10,000,000 bytes of values")
    with pytest.raises(yaml_io.YamlRefused, match=r"^an anchor \(`&s`, line 1\)"):
        yaml_io.load(LONG)


def test_the_bytes_of_the_values_hold_at_the_limit_and_one_past_it(monkeypatch):
    monkeypatch.setattr(yaml_io, "MAX_EXPANDED_BYTES", 14)
    # `s` 1, `aaaa` 4, `l` 1, and each `*s` the 4 it repeats: 14
    assert yaml_io.load("s: &s aaaa\nl: [*s, *s]\n", loader=yaml_io.CountingLoader) == {
        "s": "aaaa", "l": ["aaaa", "aaaa"]}
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load("s: &s aaaa\nl: [*s, *s, *s]\n", loader=yaml_io.CountingLoader)
    assert str(refused.value) == ("more than 14 bytes of values once `*s` is counted at the size "
                                  "of what it repeats (line 2): a YAML file is read to 14 bytes "
                                  "of values")
    # no alias: the text itself, counted in bytes, not characters (`é` is two)
    assert yaml_io.load("s: aaaa\nl: [éé, éé]\n") == {"s": "aaaa", "l": ["éé", "éé"]}
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load("s: aaaa\nl: [éé, éé, x]\n")
    assert str(refused.value) == ("more than 14 bytes of values (line 2): a YAML file is read to "
                                  "14 bytes of values")


def test_the_byte_ceiling_holds_at_the_limit_and_one_past_it(monkeypatch):
    monkeypatch.setattr(yaml_io, "MAX_BYTES", 20)
    assert yaml_io.load("a: " + "é" * 8 + "\n") == {"a": "é" * 8}       # 3 + 16 + 1 = 20 bytes
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load("a: " + "é" * 8 + "x\n")                             # 21 bytes, 13 characters
    assert str(refused.value) == ("21 bytes, over the 20-byte ceiling a YAML file is read to — "
                                  "split it or leave it out")
    with pytest.raises(yaml_io.YamlRefused):
        yaml_io.load(b"a: " + b"x" * 18)


def test_the_ceilings_admit_what_the_readers_admit_and_stay_inside_the_interpreter():
    # the system layer reads a file to its own ceiling, and the door must not refuse it for size
    assert yaml_io.MAX_BYTES >= tree.READ_CEILING
    # a document with no alias is never longer than its own values, so this bound is the aliases'
    assert yaml_io.MAX_EXPANDED_BYTES >= yaml_io.MAX_BYTES
    # three frames a level while composing; a reader is never 600 frames deep already
    import sys
    assert 3 * yaml_io.MAX_DEPTH + 600 < sys.getrecursionlimit()


def test_a_refusal_is_logged_where_it_is_made(caplog):
    caplog.set_level(logging.WARNING, logger=yaml_io.log.name)
    with pytest.raises(yaml_io.YamlRefused):
        yaml_io.load("a: *x\n")
    assert any(r.getMessage().startswith("OPENFACTORY_YAML_REFUSED ") and "`*x`" in r.getMessage()
               for r in caplog.records)


def test_the_door_reads_only_with_its_own_loaders():
    with pytest.raises(TypeError):
        yaml_io.load("a: 1\n", loader=yaml.SafeLoader)  # type: ignore[arg-type]
    with pytest.raises(yaml.YAMLError):
        yaml_io.load("a: 1\n---\nb: 2\n")
    assert yaml_io.load("# nothing\n") is None


def test_every_yaml_file_the_package_ships_reads_through_the_door():
    shipped = sorted(p for p in PACKAGE.rglob("*") if p.suffix in (".yaml", ".yml"))
    assert shipped, "the package ships YAML files, and none was found"
    for path in shipped:
        yaml_io.load(path.read_text(encoding="utf-8"))


# ── 4. the writer ───────────────────────────────────────────────────────────────────────────────


def test_what_the_core_writes_carries_no_alias_and_reads_back_through_the_door():
    shared = ["a", "b"]
    data = {"one": shared, "two": shared, "three": {"x": shared}}
    assert "&id" in yaml.safe_dump(data)  # what PyYAML writes for a value met twice
    written = yaml_io.dump(data, sort_keys=True)
    assert "&" not in written and "*" not in written
    assert yaml_io.load(written) == data
