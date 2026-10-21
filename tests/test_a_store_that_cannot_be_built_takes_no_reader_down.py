"""An installed credential store that cannot be built takes no reader down (review of bd178211 for
#822).

THE DEFECT. `held_values` builds every installed store kind, through `unusable` and `listed`, and
`build_store` handed on whatever a builder raised while every reader caught only `ValueError`. An
add-on's builder reads its own settings, and raises on a deployment that installed it and never set
it up (`RuntimeError("VAULT_ADDR is not set")`). The product's facts withhold through
`held_values` for every facts file and every briefing line, and so does the certify pack, so one
such add-on stopped every product turn and the pack — from a store nobody declared or named.

THE RULE, FOR THE WHOLE FAMILY: a store that cannot be built is one way only, `ValueError`, naming
the kind and the type of what its builder raised; and no reader that builds a store raises over
it, whether the store is declared or merely installed. Both tables are read from the code:

  · `registry_readers()`: every function of `registry.py` that reaches `build_store`, by the
    module's own calls. Each is called with its parameters filled by name (`ARGUMENTS`); a reader
    with a parameter this test cannot fill fails here by name;
  · `readers_elsewhere()`: every function outside the store that asks the registry about a store
    by its KIND rather than by a credential's reference — the registry readers that take a `kind`
    or walk `known()` — found by the calls in the package. Each names, in `ELSEWHERE`, how it is
    exercised and what it says instead.

A reader of a credential by its reference (`stored`, `look`, `chain`, …) outside the store is the
refused-credential family's (`tests/test_a_refused_credential_opens_no_door.py`), where a declared
store that cannot be built is one of the refusals every consumer keeps its door shut over.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from types import SimpleNamespace

import pytest

from openfactory.adapters.credential_store import registry
from openfactory.adapters.credential_store.registry import STORE_VAR, STORES

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "openfactory"
REGISTRY = pathlib.Path(registry.__file__)
MODULE = "openfactory.adapters.credential_store.registry"

#: The add-on's kind, installed for each case and declared in half of them.
KIND = "vaultx"
#: What its builder says — the add-on's words, which may carry a setting's value and are never
#: repeated in the sentence `build_store` says.
WORDS = "vaultx: VAULT_ADDR is not set"
#: What a builder may raise: anything, not one exception somebody thought of.
RAISED = (RuntimeError, OSError, ImportError, KeyError, TypeError, AttributeError, TimeoutError)
#: A deployment credential, held in the environment: what a scrub must still withhold.
ENV_NAME = "OPENFACTORY_TRACKER_TOKEN"
ENV_VALUE = "fictitious-env-value-822f"

#: A registry reader's parameters, filled by name.
ARGUMENTS = {
    "kind": KIND,
    "name": "ACME_TOKEN",
    "reference": f"{KIND}:acme",
    "names": (ENV_NAME, "OPENFACTORY_BOT_TOKEN"),
    "named": (f"{KIND}:acme",),
}

#: A reader whose own answer is an exception, and how that answer is told from a builder's.
ITS_OWN_ANSWER = {
    # a mapping's answer for a name nothing holds: the name asked, and nothing behind it
    "Stored.__getitem__": lambda exc: (isinstance(exc, KeyError) and exc.args == ("ACME_TOKEN",)
                                       and exc.__cause__ is None and exc.__context__ is None),
}


def _world(monkeypatch, raised: type[BaseException], *, declared: bool) -> None:
    """`KIND` installed with a builder that raises `raised`, declared as the deployment's store or
    not, and a deployment credential in the environment."""
    def cannot_be_built():
        raise raised(WORDS)

    monkeypatch.setitem(STORES, KIND, cannot_be_built)
    if declared:
        monkeypatch.setenv(STORE_VAR, KIND)
    else:
        monkeypatch.delenv(STORE_VAR, raising=False)
    monkeypatch.setenv(ENV_NAME, ENV_VALUE)


# ── the registry's readers, read from its calls ─────────────────────────────────────────────────

def _defined(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """`{name: node}` of every module-level function, and every method as `Class.method`."""
    out: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out[node.name] = node
        elif isinstance(node, ast.ClassDef):
            out.update({f"{node.name}.{item.name}": item for item in node.body
                        if isinstance(item, ast.FunctionDef)})
    return out


def _calls(qualified: str, node: ast.FunctionDef, defined: dict) -> set[str]:
    """What `node` calls of what the module defines: `f(…)`, and `self.m(…)` in its class."""
    owner = qualified.rpartition(".")[0]
    out = set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        f = call.func
        if isinstance(f, ast.Name) and f.id in defined:
            out.add(f.id)
        elif (owner and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
              and f.value.id == "self" and f"{owner}.{f.attr}" in defined):
            out.add(f"{owner}.{f.attr}")
    return out


def registry_readers() -> dict[str, set[str]]:
    """`{reader: what it calls}` for every function of `registry.py` that reaches `build_store`."""
    defined = _defined(ast.parse(REGISTRY.read_text(encoding="utf-8")))
    calls = {q: _calls(q, node, defined) for q, node in defined.items()}
    reaches = {"build_store"}
    while grown := {q for q, called in calls.items() if q not in reaches and called & reaches}:
        reaches |= grown
    return {q: calls[q] for q in reaches - {"build_store"}}


def _by_kind() -> set[str]:
    """The public registry readers that build a store chosen by its KIND — a `kind` parameter, or
    every installed one (`known()`) — rather than the store a credential's reference names."""
    out = set()
    for reader, called in registry_readers().items():
        if reader.startswith("_") or "." in reader:
            continue
        params = inspect.signature(getattr(registry, reader)).parameters
        if "kind" in params or "known" in called:
            out.add(reader)
    return out


def _call(reader: str):
    """Call `reader` with its parameters filled by name; a parameter with a default keeps it."""
    owner, _, attr = reader.rpartition(".")
    target = getattr(getattr(registry, owner)(), attr) if owner else getattr(registry, reader)
    params = inspect.signature(target).parameters.values()
    unfilled = [p.name for p in params if p.default is p.empty and p.name not in ARGUMENTS]
    assert not unfilled, (f"`{reader}` reaches `build_store` and takes {unfilled}, which this test "
                          f"cannot fill: name a value for each in ARGUMENTS")
    return target(**{p.name: ARGUMENTS[p.name] for p in params if p.default is p.empty})


def test_the_readers_are_read_from_the_registrys_calls():
    """The verifier of the table: the readers the AST finds are the ones the issue names, at
    least — the ones that walk installed stores and the ones a reference reaches."""
    found = registry_readers()
    assert {"held_values", "unusable", "listed", "describe", "_ask", "look", "lookup",
            "stored", "Stored.get"} <= set(found), sorted(found)
    assert {"held_values", "unusable", "listed"} <= _by_kind(), sorted(_by_kind())
    assert "deployment_store" not in found and "parse" not in found, "builds nothing"


@pytest.mark.parametrize("raised", RAISED, ids=lambda e: e.__name__)
def test_a_store_that_cannot_be_built_is_a_value_error_naming_its_kind(raised, monkeypatch):
    """Whatever the builder raises, `build_store` says one thing: the kind and the type of what
    was raised — not the add-on's words — chained to it, so a traceback still shows them."""
    _world(monkeypatch, raised, declared=False)
    with pytest.raises(ValueError) as said:
        registry.build_store(KIND)
    assert KIND in str(said.value) and raised.__name__ in str(said.value), str(said.value)
    assert WORDS not in str(said.value)
    assert isinstance(said.value.__cause__, raised)


def test_a_builders_own_value_error_is_said_as_itself(monkeypatch):
    """A builder that refuses with a `ValueError` already speaks the readers' language: its own
    sentence passes through unchanged."""
    own = ValueError("vaultx: VAULT_ADDR names no URL — set it to the vault's address")

    def refuses():
        raise own

    monkeypatch.setitem(STORES, KIND, refuses)
    with pytest.raises(ValueError) as said:
        registry.build_store(KIND)
    assert said.value is own


@pytest.mark.parametrize("declared", [True, False], ids=["declared", "installed"])
@pytest.mark.parametrize("reader", sorted(registry_readers()))
def test_no_registry_reader_raises_over_a_store_that_cannot_be_built(reader, declared,
                                                                        monkeypatch):
    for raised in RAISED:
        with monkeypatch.context() as mp:
            _world(mp, raised, declared=declared)
            try:
                _call(reader)
            except Exception as exc:  # noqa: BLE001 — what is caught is the finding
                own = ITS_OWN_ANSWER.get(reader)
                assert own is not None and own(exc), (
                    f"`{reader}` raised {type(exc).__name__}: {exc} — from a {raised.__name__} "
                    f"of an installed store's builder ({'declared' if declared else 'not declared'})")


# ── the readers outside the store that ask about a store by its kind ───────────────────────────

def _aliases(tree: ast.Module) -> tuple[set[str], dict[str, str]]:
    """`(names bound to the registry module, {local name: registry function})` in a module."""
    modules, functions = set(), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "openfactory.adapters.credential_store":
            modules |= {a.asname or a.name for a in node.names if a.name == "registry"}
        elif isinstance(node, ast.ImportFrom) and node.module == MODULE:
            functions.update({a.asname or a.name: a.name for a in node.names})
        elif isinstance(node, ast.Import):
            modules |= {a.asname for a in node.names if a.name == MODULE and a.asname}
    return modules, functions


def readers_elsewhere() -> set[tuple[str, str]]:
    """`(module, function)` of every function outside the store that calls a registry reader
    that builds a store by its kind — read from the calls in the package."""
    by_kind = _by_kind()
    found = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("openfactory/adapters/credential_store/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules, functions = _aliases(tree)
        if not modules and not functions:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for call in ast.walk(fn):
                if not isinstance(call, ast.Call):
                    continue
                f = call.func
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                    asked = f.attr if f.value.id in modules else ""
                else:
                    asked = functions.get(getattr(f, "id", ""), "")
                if asked in by_kind:
                    found.add((rel, fn.name))
    return found


def _facts(declared: bool) -> None:
    from openfactory.product import model

    assert (model.scrub_credentials(f"the key is {ENV_VALUE}")
            == f"the key is {model.WITHHELD_CREDENTIAL}"), "the environment's value is withheld"


def _pack(declared: bool) -> None:
    from openfactory.certify import pack

    assert pack._held_values({f"{KIND}:acme"}) == set()


def _doctor(declared: bool) -> None:
    from openfactory.contracts.project import Project
    from openfactory.doctor import credential_store_line

    ok, said, remedy = credential_store_line(Project(name="acme", repo_path="/tmp/acme"))
    if declared:
        assert not ok and KIND in said and "could not be built" in said, said
        assert WORDS not in said + remedy
    else:
        assert ok, said


def _certify(declared: bool) -> None:
    from openfactory.certify import controls

    answer = controls._panel_in_the_store(SimpleNamespace(env={STORE_VAR: KIND} if declared
                                                           else {}))
    if declared:
        assert answer is not None and answer[0] == controls.UNKNOWN, answer
    else:
        assert answer is None, answer


#: `(module, function)` → how it is exercised, and what it says in a store's place.
ELSEWHERE = {
    ("openfactory/product/model.py", "_secrets_of_this_process"): _facts,
    ("openfactory/certify/pack.py", "_held_values"): _pack,
    ("openfactory/doctor.py", "credential_store_line"): _doctor,
    ("openfactory/certify/controls.py", "_panel_in_the_store"): _certify,
}


def test_every_reader_elsewhere_that_builds_a_store_by_its_kind_is_a_case_here():
    """A new reader that asks the registry about a store by its kind joins `ELSEWHERE`, or fails
    here by name."""
    assert readers_elsewhere() == set(ELSEWHERE)


@pytest.mark.parametrize("declared", [True, False], ids=["declared", "installed"])
@pytest.mark.parametrize("reader", sorted(ELSEWHERE), ids=lambda r: r[1])
def test_no_reader_elsewhere_raises_over_a_store_that_cannot_be_built(reader, declared,
                                                                        monkeypatch):
    for raised in RAISED:
        with monkeypatch.context() as mp:
            _world(mp, raised, declared=declared)
            ELSEWHERE[reader](declared)
