"""What the product's writes to its docs repository say is in the project's language (#535).

FOUND: every sentence `product/authoring.py` answered with was a Portuguese literal welded into the
write — an `en` project read "não encontrei o requisito 9 para aceitar" when a requirement was
missing — and its docs repository took commits titled "requisito 0002: abandonado por …" and pull
requests titled "Levantamento inicial: …". The sweep's exemption list carried 106 of them.

THE RULE THIS FILE HOLDS: each of them lives in one catalogue (`authoring._WRITES`), with `en`
beside `pt-BR`; every write takes the project's language and the module hands it on; and an `en`
project's docs repository — its commits, its files, the sentences its writes return — holds no
Portuguese. A `pt-BR` project reads exactly what it read before.
"""

from __future__ import annotations

import ast
import string
from pathlib import Path

import pytest

from openfactory.product import authoring
from openfactory.product.authoring import (
    _WRITES,
    _w,
    accept_requirement,
    drop_requirement,
    record_decision,
    record_fact,
)
from tests.test_no_portuguese_is_welded_into_the_core import fragments, is_portuguese
from tests.test_requirement_can_be_dropped import _git, _rendered
from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parent.parent
PATH = "requirements/0002-pacote-de-fecho.md"


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    for key, value in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@t"),
                       ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@t")):
        monkeypatch.setenv(key, value)


@pytest.fixture()
def origin(tmp_path):
    src = tmp_path / "docs-origin"
    src.mkdir()
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"),
                 ("config", "user.name", "t"), ("config", "receive.denyCurrentBranch", "ignore")):
        _git(*args, cwd=src)
    (src / "requirements").mkdir()
    (src / PATH).write_text(_rendered(status="accepted"))
    _git("add", "-A", cwd=src)
    _git("commit", "-qm", "seed", cwd=src)
    return src


def _english(text: str) -> None:
    portuguese = [f for f in fragments(text) if is_portuguese(f)]
    assert not portuguese, (portuguese, text)


def _subject(origin) -> str:
    return _git("log", "-1", "--format=%B", "main", cwd=origin).stdout


# ── one catalogue, both languages ───────────────────────────────────────────────────────────────

def _fields(text: str) -> set[str]:
    return {name for _lit, name, _spec, _conv in string.Formatter().parse(text) if name}


def test_every_sentence_has_its_english_with_the_same_blanks():
    assert set(_WRITES["pt-BR"]) == set(_WRITES["en"])
    for key, pt in _WRITES["pt-BR"].items():
        assert _fields(pt) == _fields(_WRITES["en"][key]), key
        _english(_WRITES["en"][key])


def test_a_pt_br_project_reads_what_it_read_before():
    assert _w("pt-BR", "accept_not_found", number=9) == "não encontrei o requisito 9 para aceitar"
    assert _w("pt-BR", "drop_commit", number=2, by="<@UADM>") == (
        "requisito 0002: abandonado por <@UADM>")


# ── an `en` project's docs repository ───────────────────────────────────────────────────────────

def test_an_en_projects_drop_is_committed_in_english(origin):
    res = drop_requirement(docs_repo="a/b", clone_url=str(origin), path=PATH, number=2,
                           dropped_by="<@UADM>", reason="the client gave it up",
                           today="2026-10-11", language="en")

    assert res.ok, res.detail
    assert _subject(origin).startswith("requirement 0002: dropped by <@UADM>"), _subject(origin)
    _english(_subject(origin))


def test_an_en_projects_decision_is_committed_in_english_and_its_refusals_said_in_it(origin):
    said = record_decision(docs_repo="a/b", clone_url=str(origin), path=PATH, number=2,
                           decision="the cut-off is the 25th", decided_by="<@UADM>",
                           today="2026-10-11", language="en")
    assert said.ok, said.detail
    _english(_subject(origin))
    again = record_decision(docs_repo="a/b", clone_url=str(origin), path=PATH, number=2,
                            decision="the cut-off is the 25th", decided_by="<@UADM>",
                            today="2026-10-11", language="en")
    missing = record_decision(docs_repo="a/b", clone_url=str(origin),
                              path="requirements/0009-x.md", number=9, decision="x is y",
                              decided_by="<@UADM>", today="2026-10-11", language="en")

    assert again.existed and again.detail == "that decision was already recorded today"
    assert missing.detail == "I did not find requirement 9 to record the decision in"


def test_an_en_projects_acceptance_refusals_are_said_in_english(origin):
    already = accept_requirement(docs_repo="a/b", clone_url=str(origin), path=PATH, number=2,
                                 accepted_by="<@UADM>", today="2026-10-11", language="en")
    missing = accept_requirement(docs_repo="a/b", clone_url=str(origin),
                                 path="requirements/0009-x.md", number=9, accepted_by="<@UADM>",
                                 today="2026-10-11", language="en")

    assert already.existed and already.detail == "this requirement was already agreed"
    assert missing.detail == "I did not find requirement 9 to accept"
    for outcome in ("dropped", "superseded", "unreadable"):
        _english(authoring._accept_refusal(2, outcome, "en"))
    for outcome in ("superseded", "unreadable"):
        _english(authoring._drop_refusal(2, outcome, "en"))


def test_an_en_projects_fact_is_a_file_and_a_commit_in_english(origin):
    res = record_fact(docs_repo="a/b", clone_url=str(origin), term="close", body="always the 5th",
                      said_by="<@UADM>", where="the room", today="2026-10-11", language="en")

    assert res.ok, res.detail
    assert _subject(origin).startswith("fact: close\n\nSaid by <@UADM> in the room."), (
        _subject(origin))
    written = _git("show", f"main:{res.ref}", cwd=origin).stdout
    assert "Fact: close" in written and "Noted in a conversation with <@UADM>." in written
    assert "- **Where:** the room" in written, written
    _english(written)


@pytest.mark.parametrize("language", ["en", "pt-BR"])
def test_a_fact_file_reads_back_whichever_language_wrote_it(language):
    """The labels follow the project's language (`Source`/`Fonte`, `Where`/`Onde`, `Date`/`Data`),
    and the reader takes either: a fact written in one is never a fact with no source in the other."""
    from openfactory.product.domain import Fact, parse_facts, render_file

    fact = Fact(term="close", body="always the 5th", source="<@UADM>", where="the room",
                learned_on="2026-10-11")
    [back], findings = parse_facts(render_file([fact], title="t", language=language))

    assert (back.source, back.where, back.learned_on, back.body) == (
        "<@UADM>", "the room", "2026-10-11", "always the 5th"), back
    assert findings == [], findings


# ── the module hands the project's language on ──────────────────────────────────────────────────

_WRITERS = {"propose_requirement", "accept_requirement", "drop_requirement", "record_decision",
            "record_fact", "propose_baseline"}


def test_every_write_the_module_makes_is_handed_the_projects_language():
    tree = parsed(ROOT / "openfactory/product/module.py")
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id in _WRITERS]

    assert {c.func.id for c in calls} == _WRITERS, "a write moved, and this guard went blind"
    for call in calls:
        assert any(k.arg == "language" for k in call.keywords), (
            f"module.py:{call.lineno} calls {call.func.id} without the project's language")


def test_the_sweep_that_rescues_a_proposal_hands_it_the_projects_language():
    source = (ROOT / "openfactory/runtime/temporal/activities.py").read_text(encoding="utf-8")
    start = source.index("rescued = land_open_proposals(")

    assert 'language=getattr(project, "language", None)' in source[start:start + 1200]
