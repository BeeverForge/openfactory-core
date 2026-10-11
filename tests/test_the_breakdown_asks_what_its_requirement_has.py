"""A breakdown is handed the cards that already execute its requirement, and files each card
through the semaphore after asking again (#563, ADR-0051 D18 slice 18d; #567's last slice).

WHAT WAS MEASURED. On v0.5.0-rc.1 one requirement got three cards through three doors in seven
minutes. Inside a breakdown, the board was read once, before minutes of drafting, and each card's
only check was the decomposition's own `already_on_board` claim against that early read, then its
exact title — outside the semaphore. A card of the same requirement filed meanwhile, by hand or by
another surface, was invisible to it; and the decomposition judged the board by titles, which carry
neither what a card delivers nor what it builds on (#567).

THE RULE THIS FILE HOLDS (D18 item 4, and the reviews of #598 and #617):
  1. the decomposition is handed the cards that execute the requirement — read from their
     `## Source`, OPEN AND CLOSED, each in its own words, bounded — and a front it says one of them
     carries is reused, a closed one included: a delivered requirement does not file its work
     again;
  2. each card is filed through the product's semaphore, and just before it the board is read
     again: a card of the requirement that appeared since the breakdown began stops every front
     not yet filed, each said as held, naming that card;
  3. the breakdown's OWN cards are never strangers to that re-read: three fronts with nobody else
     filing file all three;
  4. the vet (a model call) runs before the lock is taken; the re-read and the write under it;
  5. a board that cannot be read files as before — a duplicate beats work silently dropped.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from openfactory.product import semaphore
from openfactory.product.role import IssueDraft, _carrying_section

STORAGE, HISTORY, EXPORT = ("Guardar cada versão entregue", "Mostrar o histórico de versões",
                            "Exportar a lista de clientes")


def _card(ref: str, *, executes: int | None = 66, state: str = "open", title: str = "",
          criterion: str = "o histórico mostra cada versão"):
    body = (f"## Objective\n\nalgo do REQ\n\n## Acceptance criteria\n\n- [ ] {criterion}\n\n"
            + (f"## Source\n\nExecutes REQ-{executes:04d}\n" if executes else ""))
    return SimpleNamespace(number=ref, title=title or f"card {ref}", body=body, state=state,
                           column="Backlog")


class _Board:
    """The client's board as the module reads it: what was on it, plus every card the tracker
    filed (with the body it was filed with), plus whatever a test puts there meanwhile."""

    def __init__(self, tracker, before=(), *, unreadable_at=()):
        self.tracker, self.before, self.meanwhile = tracker, list(before), []
        self.reads, self.under_lock, self.unreadable_at = 0, [], set(unreadable_at)

    def read(self, **_kw):
        self.reads += 1
        self.under_lock.append(semaphore.held_here())
        if self.reads in self.unreadable_at:
            return [], "the forge did not answer"
        filed = [SimpleNamespace(number=ref.lstrip("#"), title=title, body=body, state="open",
                                 column="Backlog")
                 for ref, title, body in self.tracker.filed]
        return [*self.before, *filed, *self.meanwhile], ""


class _Tracker:
    def __init__(self):
        self.filed: list[tuple[str, str, str]] = []
        self.commented: list[str] = []
        self.on_create = None

    @property
    def created(self) -> list[str]:
        return [title for _ref, title, _body in self.filed]

    def find_ticket(self, *, title: str):
        return None

    def create_ticket(self, *, title: str, body: str, **_kw) -> str:
        ref = f"#{1000000 + len(self.filed) + 1}"
        self.filed.append((ref, title, body))
        if self.on_create:
            self.on_create(len(self.filed))
        return ref

    def comment(self, ref, body):
        self.commented.append(ref)

    def ticket_url(self, ref: str) -> str:
        return f"https://forge/a/b/issues/{ref.lstrip('#')}"

    def get_ticket(self, ref: str):
        return SimpleNamespace(title="", state="open", raw="")


def _front(title: str, *, carried_by: str | None = None) -> IssueDraft:
    return IssueDraft(title=title, objective="o", acceptance_criteria=["um critério observável"],
                      cites=66, already_on_board=carried_by)


@pytest.fixture
def breakdown(tmp_path, monkeypatch):
    """`file_issues` over the test's fronts and board; what the decomposition was handed, and
    whether the vet ran under the semaphore, are recorded."""
    from openfactory.product import module as module_
    from tests.test_the_product_owner_opens_a_card_as_described import _module

    seen = SimpleNamespace(carrying=None, vet_under_lock=[])

    def run(fronts, *, before=(), meanwhile_after=None, meanwhile=(), unreadable_at=(),
            handed=True):
        tracker = _Tracker()
        mod = _module(tmp_path, tracker)
        board = _Board(tracker, before, unreadable_at=unreadable_at)
        requirement = SimpleNamespace(number=66, title="Versões entregues", body="b",
                                      asked_by="", path="0066.md", is_live=True, is_promise=True,
                                      came_from_the_code=False)
        drafts = SimpleNamespace(ok=True, issues=list(fronts))

        def issues_for(*, sandbox, workspace, requirement, sources, carrying=None):
            seen.carrying = carrying
            if meanwhile_after == 0:
                board.meanwhile.extend(meanwhile)   # filed by hand while the breakdown drafts
            return drafts

        def older_issues_for(*, sandbox, workspace, requirement, sources):
            return drafts

        if meanwhile_after:
            tracker.on_create = (lambda n: board.meanwhile.extend(meanwhile)
                                 if n == meanwhile_after else None)
        monkeypatch.setattr(mod, "_role", lambda **k: SimpleNamespace(
            issues_for=issues_for if handed else older_issues_for))
        monkeypatch.setattr(mod, "_workspace", lambda: (None, None))
        monkeypatch.setattr(mod, "_read_board", board.read)
        monkeypatch.setattr(mod, "context", lambda **k: SimpleNamespace(
            available=True, docs_path=str(tmp_path), link=SimpleNamespace(docs_repo="a/docs"),
            corpus=SimpleNamespace(by_number=lambda n: requirement), docs_commit="",
            requirements_dir="requirements"))
        monkeypatch.setattr(mod, "_open_delivery", lambda *a, **k: None)
        monkeypatch.setattr(mod, "_vetter", lambda req, tr: (
            lambda draft: (seen.vet_under_lock.append(semaphore.held_here()), (draft, ""))[1]))
        monkeypatch.setattr(module_, "may_act", lambda *a, **k: True)

        results = mod.file_issues(requirement, actor="<@U1>", tracker=tracker, board=None)
        return SimpleNamespace(results=results, tracker=tracker, board=board)

    run.seen = seen
    return run


# ── 2. the re-read, and a card that appeared meanwhile ──────────────────────────────────────────

def test_TODAYS_RUN_a_card_filed_by_hand_while_it_drafts_holds_every_front_naming_it(breakdown):
    got = breakdown([_front(STORAGE), _front(HISTORY), _front(EXPORT)],
                    meanwhile_after=0, meanwhile=[_card("1000077")])

    assert got.tracker.created == [], "a front was filed beside the card that appeared meanwhile"
    assert [r.ok for r in got.results] == [False, False, False]
    for result, title in zip(got.results, (STORAGE, HISTORY, EXPORT), strict=True):
        assert f"segurei a frente “{title}”" in result.detail and "#1000077" in result.detail, (
            result.detail)


def test_one_that_appears_after_the_first_card_holds_the_fronts_not_yet_filed(breakdown):
    got = breakdown([_front(STORAGE), _front(HISTORY), _front(EXPORT)],
                    meanwhile_after=1, meanwhile=[_card("1000077")])

    assert got.tracker.created == [STORAGE]
    assert [r.ok for r in got.results] == [True, False, False]
    assert "#1000077" in got.results[1].detail and "#1000077" in got.results[2].detail
    # ONCE STOPPED, A FRONT NOT REACHED COSTS NOTHING: no vet (a model call) and no re-read for the
    # third — only the first two were vetted, and the board read before drafting plus twice
    assert len(breakdown.seen.vet_under_lock) == 2 and got.board.reads == 3, (
        breakdown.seen.vet_under_lock, got.board.reads)


def test_its_own_cards_are_never_strangers_three_fronts_file_all_three(breakdown):
    """REVIEW OF #598. Every card a breakdown files executes its requirement (its `## Source`
    says so), and a re-read that counted them held the second front on the first."""
    got = breakdown([_front(STORAGE), _front(HISTORY), _front(EXPORT)])

    assert got.tracker.created == [STORAGE, HISTORY, EXPORT]
    assert all(r.ok for r in got.results), [r.detail for r in got.results]
    from openfactory.product.module import _cited_requirement

    assert all(_cited_requirement(body) == 66 for _ref, _title, body in got.tracker.filed), (
        "the cards filed do not cite the requirement, so this case proves nothing")


def test_a_card_of_another_requirement_filed_meanwhile_stops_nothing(breakdown):
    got = breakdown([_front(STORAGE), _front(HISTORY)], meanwhile_after=1,
                    meanwhile=[_card("1000077", executes=9), _card("1000078", executes=None)])

    assert got.tracker.created == [STORAGE, HISTORY]


# ── 4. the lock: the re-read and the write under it, the vet before it ──────────────────────────

def test_the_vet_runs_before_the_lock_and_the_re_read_under_it(breakdown):
    got = breakdown([_front(STORAGE), _front(HISTORY)])

    assert breakdown.seen.vet_under_lock == [False, False], "a model call ran under the semaphore"
    # the first read is the one before drafting; every later one is a card's re-read
    assert got.board.under_lock[0] is False and all(got.board.under_lock[1:]), (
        got.board.under_lock)
    assert got.board.reads == 3


# ── 5. a board that cannot be read ──────────────────────────────────────────────────────────────

def test_a_board_that_cannot_be_read_before_a_card_files_it_and_says_so(breakdown, caplog):
    with caplog.at_level(logging.WARNING):
        got = breakdown([_front(STORAGE)], unreadable_at={2})

    assert got.tracker.created == [STORAGE]
    assert "OPENFACTORY_PRODUCT_BREAKDOWN_UNFENCED" in caplog.text


def test_a_board_unread_when_it_began_cannot_tell_new_from_old_and_files_as_before(breakdown):
    got = breakdown([_front(STORAGE)], unreadable_at={1}, meanwhile_after=0,
                    meanwhile=[_card("1000077")])

    assert got.tracker.created == [STORAGE]


# ── 1. what the decomposition is handed, and the closed carrier ─────────────────────────────────

def test_the_decomposition_is_handed_the_cards_that_execute_it_open_and_closed(breakdown):
    before = [_card("41"), _card("42", state="closed"), _card("43", executes=9),
              _card("44", executes=None)]
    breakdown([_front(STORAGE)], before=before)

    assert [c.number for c in breakdown.seen.carrying] == ["41", "42"]


def test_a_front_a_closed_card_of_the_requirement_carries_is_not_filed_again(breakdown):
    """REVIEW OF #617. A breakdown of a requirement whose cards were all delivered filed its
    fronts again; a closed card that executed it delivered its part."""
    got = breakdown([_front(STORAGE, carried_by="42"), _front(EXPORT)],
                    before=[_card("42", state="closed")])

    assert got.tracker.created == [EXPORT]
    assert got.results[0].ok and got.results[0].existed and got.results[0].ref == "#42"
    assert got.tracker.commented == [], "a card that already says it executes the requirement " \
                                        "was told so again"


def test_a_role_that_takes_no_cards_is_called_as_before(breakdown):
    got = breakdown([_front(STORAGE)], before=[_card("41")], handed=False)

    assert got.tracker.created == [STORAGE]


def test_the_prompt_carries_each_card_in_its_own_words_bounded():
    requirement = SimpleNamespace(number=66)
    said = _carrying_section(requirement, [
        _card("41", title="Histórico", criterion="cada versão aparece com data"),
        _card("42", state="closed", title="Guardar versões")])

    assert said.startswith("## Cards that already execute REQ-0066"), said
    assert "#41 «Histórico» (open, Backlog)" in said and "#42 «Guardar versões» (closed)" in said
    assert "criterion: cada versão aparece com data" in said and "executes: REQ-0066" in said
    assert _carrying_section(requirement, []) == "" and _carrying_section(requirement, None) == ""


class _Asked(Exception):
    """Raised by the double the moment the prompt is handed over — the case asserts on it."""


def _prompt_of(carrying) -> str:
    from openfactory.product.role import ProductRole

    def _ask(_sandbox, _workspace, prompt, _phase):
        raise _Asked(prompt)

    role = SimpleNamespace(_prompt=lambda instruction, body, schema="": f"{instruction}\n{body}",
                           _ask=_ask)
    requirement = SimpleNamespace(number=66, title="Versões entregues", path="0066.md", body="b")
    with pytest.raises(_Asked) as asked:
        ProductRole.issues_for(role, sandbox=None, workspace=None, requirement=requirement,
                               sources=["a/app"], carrying=carrying)
    return str(asked.value)


def test_the_decomposition_reads_them_in_its_own_prompt_and_is_told_what_they_mean():
    said = _prompt_of([_card("41", title="Histórico"), _card("42", state="closed")])

    assert "## Cards that already execute REQ-0066" in said and "#41 «Histórico»" in said, said
    assert "Draft only the fronts they do not carry" in said and "a closed one delivered" in said
    assert "Cards that already execute" not in _prompt_of([]), "a section for nothing"
