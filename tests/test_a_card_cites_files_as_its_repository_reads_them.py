"""A card the product role writes cites each file as the repository it lands in reads it.

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640). The role reads the product's code in a view
that places each source at `src/<name>/` (`workspace.compose`), and wrote its paths that way. A
breakdown filed in `jornada` said "today Task has id, title and done (src/jornada/tasks/store.py)"
and asked for "tests in src/jornada/tests/test_store.py". The repository has `tasks/store.py`. The
review could not check the criterion that named the path, and parked the job for a person.

THE RULE THIS FILE HOLDS:
  1. the repository's own `src/<name>/` goes, and another source's becomes `<owner/name>:`;
  2. a path that is already the repository's own (a package laid out as `src/<name>/` inside a
     repository of that name) is left alone when the view shows it;
  3. every writer of the role's words onto a card rewrites them: a breakdown's fronts, a card a
     person asked for, a defect, and the criteria refine, correct and align write;
  4. a rewrite that cannot be made files the card as the role wrote it, and says so in the log.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from openfactory.product.module import ProductModule
from openfactory.product.workspace import as_the_repository_reads
from tests.test_card_maintenance import ADMIN, _asked
from tests.test_card_maintenance import world as world  # noqa: F401 — the fixture, reused
from tests.test_the_breakdown_asks_what_its_requirement_has import _front
from tests.test_the_breakdown_asks_what_its_requirement_has import (
    breakdown as breakdown,  # noqa: F401 — the fixture, reused
)
from tests.test_the_product_owner_opens_a_card_as_described import _Board, _module, _Tracker

TODAYS_CARD = ("Hoje Task tem apenas id, title e done (src/jornada/tasks/store.py). Testes em "
               "`src/jornada/tests/test_store.py` cobrem cada um dos comportamentos acima.")
ONE = {"jornada": "jornada"}
THREE = {"acme/reservas-web": "reservas-web", "acme/reservas-api": "reservas-api",
         "acme/reservas-core": "reservas-core"}


# ── 1. the paths ────────────────────────────────────────────────────────────────────────────────

def test_TODAYS_RUN_the_repositorys_own_prefix_goes():
    got = as_the_repository_reads(TODAYS_CARD, home="jornada", placed=ONE)

    assert got == ("Hoje Task tem apenas id, title e done (tasks/store.py). Testes em "
                   "`tests/test_store.py` cobrem cada um dos comportamentos acima."), got


def test_another_sources_path_names_its_repository():
    got = as_the_repository_reads(
        "the endpoint in src/reservas-api/app/export.py, the button in src/reservas-web/ui/x.ts",
        home="acme/reservas-web", placed=THREE)

    assert got == ("the endpoint in acme/reservas-api:app/export.py, the button in ui/x.ts"), got


def test_only_a_path_that_starts_at_the_view_is_rewritten():
    text = "mysrc/jornada/x, ./src/jornada/y and a sentence about src/elsewhere/z"

    assert (as_the_repository_reads(text, home="jornada", placed=ONE)
            == "mysrc/jornada/x, y and a sentence about src/elsewhere/z")


def test_a_path_already_the_repositorys_own_is_left_alone(tmp_path):
    """A package laid out as `src/jornada/` in the repository `jornada`: in the view it sits at
    `src/jornada/src/jornada/`. The role that cited the repository's own path is not cut short."""
    (tmp_path / "src/jornada/src/jornada").mkdir(parents=True)
    (tmp_path / "src/jornada/src/jornada/store.py").write_text("x")
    (tmp_path / "src/jornada/tasks").mkdir(parents=True)
    (tmp_path / "src/jornada/tasks/store.py").write_text("x")

    assert as_the_repository_reads("src/jornada/store.py", home="jornada", placed=ONE,
                                   view=tmp_path) == "src/jornada/store.py"
    assert as_the_repository_reads("src/jornada/tasks/store.py", home="jornada", placed=ONE,
                                   view=tmp_path) == "tasks/store.py"
    # a file to be made exists nowhere yet: read as the view, which is where the role stood
    assert as_the_repository_reads("src/jornada/tasks/new.py", home="jornada", placed=ONE,
                                   view=tmp_path) == "tasks/new.py"


def test_nothing_placed_or_nothing_cited_is_the_text_as_it_was():
    assert as_the_repository_reads(TODAYS_CARD, home="jornada", placed={}) == TODAYS_CARD
    assert as_the_repository_reads("no path here", home="jornada", placed=ONE) == "no path here"


# ── 2. every writer ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _the_product_repository(monkeypatch):
    """The fixtures' product names no forge; here it is `AcmeCorp/openfactory`, at `src/openfactory/`
    in the role's view."""
    monkeypatch.setattr(ProductModule, "_source_repo", lambda self: "AcmeCorp/openfactory")


def test_TODAYS_RUN_a_breakdowns_front_is_filed_with_the_repositorys_paths(breakdown):
    front = _front("Marcar tarefa como urgente").model_copy(update={
        "objective": "Hoje Task tem id, title e done (src/openfactory/tasks/store.py).",
        "acceptance_criteria": ["Testes em src/openfactory/tests/test_store.py cobrem isso."]})

    got = breakdown([front])

    [(_ref, _title, body)] = got.tracker.filed
    assert "src/openfactory/" not in body, body
    assert "(tasks/store.py)" in body and "Testes em tests/test_store.py" in body, body


def test_a_card_a_person_asked_for_is_filed_with_the_repositorys_paths(tmp_path):
    tracker = _Tracker()

    _module(tmp_path, tracker).file_ticket(
        title="Botão de exportar", described="o botão em src/openfactory/ui/export.ts some",
        reported_by="<@U1>", tracker=tracker, board=_Board())

    [(_title, body)] = tracker.created
    assert "o botão em ui/export.ts some" in body and "src/openfactory/" not in body, body


def test_the_view_this_turn_composed_decides_the_placement(tmp_path):
    """The placements `compose` made this turn, not a guess from the declaration."""
    mod = _module(tmp_path, _Tracker())
    mod._mounted_sources = {"AcmeCorp/openfactory": str(tmp_path / "src" / "openfactory--core")}
    mod._combined = str(tmp_path)

    assert mod._in_repository_terms("see src/openfactory--core/a.py") == "see a.py"


def test_a_defect_is_filed_with_the_repositorys_paths(tmp_path):
    tracker = _Tracker()

    _module(tmp_path, tracker).file_defect(
        restated="o total em src/openfactory/app/total.py duplica o último lançamento",
        reported_by="<@U1>", violates=None, tracker=tracker, board=None)

    [(title, body)] = tracker.created
    assert "app/total.py duplica" in body and "src/openfactory/" not in body + title, body


def test_the_criteria_refine_writes_cite_the_repositorys_paths(world):
    mod, _ = world('{"criteria": ["src/openfactory/app/lote.py fecha sem sobra"], '
                   '"out_of_scope": [], "questions": []}')

    mod.refine(288, actor=ADMIN)

    [(_ref, body)] = world.tracker.bodies
    assert "- [ ] app/lote.py fecha sem sobra" in body and "src/openfactory/" not in body, body


def test_the_criteria_an_alignment_writes_cite_the_repositorys_paths(world):
    mod, _ = world('{"criteria": ["src/openfactory/app/aviso.py diz o que fazer a seguir"], '
                   '"out_of_scope": ["src/openfactory/app/assinatura.py"], "questions": []}')

    mod.align_card(288, requirement=6, actor=ADMIN)

    _ref, body = world.tracker.bodies[0]
    assert "app/aviso.py diz o que fazer a seguir" in body and "app/assinatura.py" in body
    assert "src/openfactory/" not in body, body


def test_a_correction_cites_the_repositorys_paths(world):
    world.board._add(701, "Relatório de vendas", _asked())
    mod, _ = world()

    mod.correct_card(701, actor=ADMIN, text="o relatório de src/openfactory/app/vendas.py, semanal")

    [(_ref, body)] = world.tracker.bodies
    assert "o relatório de app/vendas.py, semanal" in body and "src/openfactory/" not in body, body


def test_the_helper_takes_a_list_an_answer_and_a_draft(tmp_path):
    """Each writer hands its words to the same rewrite, as a list or as the model's answer."""
    mod = _module(tmp_path, _Tracker())

    assert mod._in_repository_terms({"criteria": ["src/openfactory/a.py exists"],
                                     "out_of_scope": ["src/openfactory/b.py"], "n": 3}) == {
        "criteria": ["a.py exists"], "out_of_scope": ["b.py"], "n": 3}
    assert mod._in_repository_terms(["src/openfactory/a.py", "x"]) == ["a.py", "x"]
    draft = SimpleNamespace(title="t src/openfactory/a.py", objective="o", other="kept")
    rewritten = mod._in_repository_terms(draft)
    assert rewritten.title == "t a.py" and rewritten.other == "kept" and draft.title.endswith(
        "src/openfactory/a.py"), "the draft handed in was changed in place"


def test_a_rewrite_that_cannot_be_made_files_the_card_as_written(tmp_path, monkeypatch, caplog):
    mod = _module(tmp_path, _Tracker())

    def _down(**_k):
        raise OSError("the context checkout is gone")

    monkeypatch.setattr(mod, "context", _down)
    with caplog.at_level(logging.WARNING):
        assert mod._in_repository_terms(TODAYS_CARD) == TODAYS_CARD
    assert "OPENFACTORY_PRODUCT_PATHS_NOT_REWRITTEN" in caplog.text
