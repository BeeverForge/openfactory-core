"""Every path the product role writes for a person cites the file as its repository reads it.

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640 row I-01, #672). #653 found the role citing
files as its view reads them (`src/<name>/…`), and #654 fixed it on the cards. The same paths still
reached a person and the context repository:
  - a REPLY in the multi-repository week: "o texto do botão já é "Exportar CSV"
    (`src/reservas-web/reservas_web/pages.py:7`)", where `reservas-web` has no `src/`;
  - REQUIREMENTS of the single-repository run: "Repositório jornada, src/jornada/tasks/store.py: a
    classe Task …", committed to the context repository, where `jornada` has `tasks/store.py`.

THE RULE THIS FILE HOLDS:
  1. what the role says to a person, and what it drafts for the product's record, cites each file
     from the root of its repository. In a product of one repository that is the path alone. In a
     product of several, each path names its repository (`<repo>:<path>`), because a requirement
     belongs to the whole product and a reply speaks for all of it;
  2. what the platform itself reads in the reply (the code the reply says it opened, mapped back to
     the view it opened it in) keeps the view's path;
  3. every model call the product role makes over its VIEW, whose answer a person reads, passes its
     answer through the rewrite in the function that makes the call. The calls are found in the
     code, not listed: a role method or `ask_json` call on the view's workspace, with a phase a
     person reads (`roles.MACHINE_PHASES` aside). One exception is named, with the function that
     carries it, and checked. Calls over a checkout of the source itself, or in a room with no
     view, read no view path to rewrite.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from openfactory.adapters.agent.roles import MACHINE_PHASES
from openfactory.product.module import ProductModule
from tests.test_product_module import _module

PRODUCT = Path("openfactory/product")
WEB, API = "acme/reservas-web", "acme/reservas-api"
TODAYS_REPLY = ("Abri a tela agora e o texto do botão já é \"Exportar CSV\" "
                "(`src/reservas-web/reservas_web/pages.py:7`). A API lê o filtro em "
                "src/reservas-api/reservas_api/service.py.")


def _over_a_view(mod, view: Path, placed: dict[str, str]):
    """The module as a turn leaves it once `_workspace` composed its view: each source placed at
    `src/<name>/` of the view."""
    for name in placed.values():
        (view / "src" / name).mkdir(parents=True, exist_ok=True)
    mod._combined = str(view)
    mod._mounted_sources = {repo: str(view / "src" / name) for repo, name in placed.items()}
    return mod


# ── 1. a reply ─────────────────────────────────────────────────────────────────────────────────

def test_TODAYS_RUN_a_reply_in_a_product_of_several_repositories_names_each_files_repository(
        tmp_path):
    mod, _ = _module(tmp_path, answer=TODAYS_REPLY)
    _over_a_view(mod, tmp_path / "view", {WEB: "reservas-web", API: "reservas-api"})

    said = mod.answer("o botão ainda diz Baixar").text

    assert "src/reservas-" not in said, said
    assert f"`{WEB}:reservas_web/pages.py:7`" in said, said
    assert f"{API}:reservas_api/service.py" in said, said


def test_TODAYS_RUN_a_reply_in_a_product_of_one_repository_cites_the_path_from_its_root(tmp_path):
    mod, _ = _module(tmp_path, answer="uma tarefa tem só título (`src/jornada/tasks/store.py`)")
    _over_a_view(mod, tmp_path / "view", {"acme/jornada": "jornada"})

    said = mod.answer("o que é uma tarefa hoje?").text

    assert said == "uma tarefa tem só título (`tasks/store.py`)", said


def test_what_the_platform_reads_in_the_reply_keeps_the_views_path(tmp_path):
    """The code the reply says it opened is mapped back to the source it lies in, through the view
    (`sight.where_read`): rewritten, it would map to nothing."""
    mod, _ = _module(tmp_path, answer=(
        "Está em src/jornada/tasks/store.py.\n"
        "[[EVIDENCIA: src/jornada/tasks/store.py]]"))
    _over_a_view(mod, tmp_path / "view", {"acme/jornada": "jornada"})

    answer = mod.answer("onde fica a tarefa?")

    assert answer.text == "Está em tasks/store.py.", answer.text
    assert answer.reading.code == ["src/jornada/tasks/store.py"], answer.reading.code


# ── 2. a requirement ───────────────────────────────────────────────────────────────────────────

def _drafted(**fields) -> str:
    return json.dumps({"title": "Marcar tarefa como urgente", "why": "", "must_be_true": [],
                       "out_of_scope": [], "affects": [], "questions": [], "conflicts": [],
                       **fields})


def test_TODAYS_RUN_a_requirement_cites_the_file_from_its_repositorys_root(tmp_path):
    mod, _ = _module(tmp_path, answer=_drafted(
        why="Repositório jornada, src/jornada/tasks/store.py: a classe Task tem só título.",
        must_be_true=["Testes em src/jornada/tests/test_store.py cobrem a urgência."],
        conflicts=[{"requirement": 1, "kind": "narrows",
                    "explanation": "O requisito 1 descreve src/jornada/tasks/store.py."}]))
    _over_a_view(mod, tmp_path / "view", {"acme/jornada": "jornada"})

    draft = mod.draft("marcar tarefa como urgente").draft

    written = draft.model_dump_json()
    assert "src/jornada/" not in written, written
    assert "Repositório jornada, tasks/store.py: a classe Task" in draft.why
    assert draft.must_be_true == ["Testes em tests/test_store.py cobrem a urgência."]
    assert draft.conflicts[0].explanation == "O requisito 1 descreve tasks/store.py."


def test_a_requirement_of_a_product_of_several_repositories_names_each_files_repository(tmp_path):
    mod, _ = _module(tmp_path, answer=_drafted(
        must_be_true=["O botão em src/reservas-web/reservas_web/pages.py baixa o CSV.",
                      "O filtro roda em src/reservas-api/reservas_api/service.py."]))
    _over_a_view(mod, tmp_path / "view", {WEB: "reservas-web", API: "reservas-api"})

    draft = mod.draft("exportar as reservas em CSV").draft

    assert draft.must_be_true == [f"O botão em {WEB}:reservas_web/pages.py baixa o CSV.",
                                  f"O filtro roda em {API}:reservas_api/service.py."]


# ── 3. every model call over the view, found in the code ──────────────────────────────────────

#: A call whose answer is rewritten later, by the function named, which this file checks does so.
REWRITTEN_DOWNSTREAM = {
    # each front is rewritten where it is filed, against the repository it is filed in (#654)
    ("module.py", "file_issues"): "_file_one",
}


def _role_phases() -> dict[str, str]:
    """`ProductRole`'s methods → the phase each asks the model under, read from `role.py`."""
    tree = ast.parse((PRODUCT / "role.py").read_text())
    [cls] = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ProductRole"]
    phases = {}
    for fn in cls.body:
        if not isinstance(fn, ast.FunctionDef) or fn.name.startswith("_"):
            continue
        for call in ast.walk(fn):
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "_ask"):
                # `_ask(sandbox, workspace, prompt, phase)`, the phase by keyword or by place
                given = [k.value for k in call.keywords if k.arg == "phase"] + call.args[3:4]
                for v in given:
                    if isinstance(v, ast.Constant):
                        phases[fn.name] = v.value
    return phases


def _over_the_view(fn: ast.FunctionDef) -> set[str]:
    """The names a function binds to its view's workspace: `sandbox, ws = self._workspace()`."""
    names = set()
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "_workspace"
                and isinstance(node.targets[0], ast.Tuple)):
            names |= {e.id for e in node.targets[0].elts if isinstance(e, ast.Name)}
    return names


def _calls_the_model_over_the_view(fn: ast.FunctionDef, person_methods: set[str]) -> list[str]:
    """The person-read model calls `fn` makes on its view's workspace: what each asks for."""
    view = _over_the_view(fn)
    bound = {}  # a name bound to a role method: `issues_for = self._role().issues_for`
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute)
                and node.value.attr in person_methods and isinstance(node.targets[0], ast.Name)):
            bound[node.targets[0].id] = node.value.attr
    found = []
    for call in ast.walk(fn):
        if not isinstance(call, ast.Call):
            continue
        kw = {k.arg: k.value for k in call.keywords}
        on_the_view = isinstance(kw.get("workspace"), ast.Name) and kw["workspace"].id in view
        if not on_the_view:
            continue
        what = (call.func.attr if isinstance(call.func, ast.Attribute)
                else bound.get(call.func.id, "") if isinstance(call.func, ast.Name) else "")
        if what in person_methods:
            found.append(what)
        elif what == "ask_json":
            phase = kw.get("phase")
            if isinstance(phase, ast.Constant) and phase.value not in MACHINE_PHASES:
                found.append(f"ask_json:{phase.value}")
    return found


def _rewrites(fn: ast.FunctionDef) -> bool:
    return any(isinstance(c, ast.Call) and getattr(c.func, "id", getattr(c.func, "attr", ""))
               == "_in_repository_terms" for c in ast.walk(fn))


def _functions():
    for path in sorted(PRODUCT.glob("*.py")):
        if path.name == "role.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef):
                yield path.name, node


def test_the_role_methods_a_person_reads_are_the_ones_this_sweep_looks_for():
    """ASSERT THE SCOPE, so the sweep below cannot pass by looking for nothing."""
    person = {m for m, phase in _role_phases().items() if phase not in MACHINE_PHASES}

    assert {"answer", "draft", "issues_for"} <= person, person
    assert not person & {"judge_confirmation", "judge_acceptance", "judge_same"}, person


def test_every_model_call_over_the_view_whose_answer_a_person_reads_is_rewritten():
    person = {m for m, phase in _role_phases().items() if phase not in MACHINE_PHASES}
    functions = dict(((name, fn.name), fn) for name, fn in _functions())
    seen, unrewritten = [], []
    for (name, fn_name), fn in functions.items():
        calls = _calls_the_model_over_the_view(fn, person)
        if not calls:
            continue
        seen.append((fn_name, calls))
        downstream = REWRITTEN_DOWNSTREAM.get((name, fn_name))
        if downstream:
            assert _rewrites(functions[(name, downstream)]), (
                f"{fn_name}'s answer is said to be rewritten by {downstream}, which does not")
        elif not _rewrites(fn):
            unrewritten.append(f"{name}::{fn_name} {calls}")

    assert len(seen) >= 5, f"the sweep found too few calls to be looking: {seen}"
    assert not unrewritten, f"the role's view paths reach a person from: {unrewritten}"


@pytest.mark.parametrize("method", ["answer", "draft", "review_needs_action",
                                    "propose_queue"])
def test_the_sweep_sees_the_calls_this_issue_is_about(method):
    person = {m for m, phase in _role_phases().items() if phase not in MACHINE_PHASES}
    fn = dict((f.name, f) for name, f in _functions() if name == "module.py")[method]

    assert _calls_the_model_over_the_view(fn, person), f"{method} is not seen by the sweep"


def test_ProductModule_has_the_methods_the_sweep_names():
    for method in ("answer", "draft", "review_needs_action", "propose_queue", "file_issues"):
        assert hasattr(ProductModule, method), method
