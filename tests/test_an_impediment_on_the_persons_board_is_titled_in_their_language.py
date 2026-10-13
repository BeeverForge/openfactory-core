"""An impediment the factory files on the person's own board is titled in the project's language
(#671).

WHAT WAS MEASURED (journey 0 against 0.6.0-rc.1, #640, row I-06). On a fresh product of three local
projects, all `pt-BR`, four impediment cards landed on the owner's own boards titled "[openfactory]
reservas-web: the product's requirements cannot be read" — English, beside the person's own cards,
over a body that opened in Portuguese.

The English title was deliberate: it is the dedup key, matched exactly, and a translated one would
make a deployment that changes its language re-file its open impediments. That argument was made for
a factory board of its own, read by a supervisor (ADR-0027). On the local row there is one board,
the person's, and the impediment is one of their cards.

THE RULE THIS FILE HOLDS, for every cause in the closed set and every language the factory's voice
speaks — both read from the code, so a cause or a language added later is held too:
  1. every cause has a title in every language;
  2. on the person's own board — the one the local row derives, or a declared factory board on the
     product's own tracker — the impediment is titled in the project's language; on a factory board
     of its own it keeps the one spelling a supervisor's board has always had;
  3. an impediment open under any spelling is found, so a change of language neither re-files it
     nor leaves it open when the capability works again.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from openfactory.contracts.project import FactoryBoard, Project, ProviderRef
from openfactory.ops import impediment
from openfactory.techlead import voice as tl_voice

CAUSES = sorted(impediment._TITLES)
LANGS = sorted(tl_voice.NARRATION["ops.impediment.body"])


class _Board:
    """The tracker the impediment is filed through: titles in, refs out."""

    def __init__(self, **open_titles):
        self.tickets = dict(open_titles)
        self.created: list[str] = []

    def find_ticket(self, *, title):
        return self.tickets.get(title)

    def create_ticket(self, *, title, body):
        ref = str(100 + len(self.created))
        self.created.append(title)
        self.tickets[title] = ref
        return ref

    def add_label(self, *_a, **_k):
        return None

    def set_assignees(self, *_a, **_k):
        return None


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(impediment, "_LAST", {})
    monkeypatch.setattr(impediment, "_born_in_the_queue", lambda project, trk: "")


def _local(language: str) -> Project:
    return Project(name="reservas-web", repo_path="/tmp/reservas-web", language=language,
                   tracker=ProviderRef(kind="local", repo="reservas-web"))


def _own_tracker_declared(language: str) -> Project:
    mine = ProviderRef(kind="github", repo="acme/reservas-web")
    return Project(name="reservas-web", repo_path="/tmp/reservas-web", language=language,
                   tracker=mine, factory_board=FactoryBoard(tracker=mine))


def _board_of_its_own(language: str) -> Project:
    return Project(name="reservas-web", repo_path="/tmp/reservas-web", language=language,
                   tracker=ProviderRef(kind="github", repo="acme/reservas-web"),
                   factory_board=FactoryBoard(tracker=ProviderRef(kind="github",
                                                                  repo="acme/factory")))


def test_the_causes_and_the_languages_are_read_from_the_code():
    assert len(CAUSES) >= 6 and {"en", "pt-BR"} <= set(LANGS), (CAUSES, LANGS)


# ── 1. every cause, every language ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGS)
def test_every_cause_has_a_title_in_every_language(lang):
    titles = {cause: impediment.title_on(_local(lang), cause) for cause in CAUSES}

    assert len(set(titles.values())) == len(CAUSES), f"two causes share a title in {lang}"
    for cause, title in titles.items():
        assert title.startswith("[openfactory] reservas-web: ") and cause not in title, title
        if lang != "en":
            assert title != impediment.title_for("reservas-web", cause), (
                f"{cause} has no title in {lang}: the English identity stands in for it")


# ── 2. the person's own board speaks their language ─────────────────────────────────────────────

@pytest.mark.parametrize("own", [_local, _own_tracker_declared], ids=["local-row", "own-tracker"])
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("cause", CAUSES)
def test_TODAYS_RUN_on_the_persons_own_board_it_is_titled_in_their_language(cause, lang, own):
    board = _Board()

    impediment.report(own(lang), cause, "the observed line", tracker=board)

    assert board.created == [impediment.title_on(own(lang), cause)], board.created
    if lang != "en":
        assert board.created != [impediment.title_for("reservas-web", cause)], (
            f"an English title on a {lang} board")


@pytest.mark.parametrize("lang", LANGS)
def test_on_a_factory_board_of_its_own_the_title_keeps_its_one_spelling(lang):
    board = _Board()

    impediment.report(_board_of_its_own(lang), CAUSES[0], "x", tracker=board)

    assert board.created == [impediment.title_for("reservas-web", CAUSES[0])], board.created


# ── 3. any spelling is the same impediment ──────────────────────────────────────────────────────

@pytest.mark.parametrize("filed_in", LANGS)
@pytest.mark.parametrize("now", LANGS)
def test_an_impediment_open_under_any_spelling_is_not_filed_again(filed_in, now):
    cause = CAUSES[0]
    board = _Board(**{impediment.title_on(_local(filed_in), cause): "7"})

    ref = impediment.report(_local(now), cause, "x", tracker=board)

    assert ref == "7" and board.created == [], (filed_in, now, board.created)


@pytest.mark.parametrize("filed_in", LANGS)
@pytest.mark.parametrize("now", LANGS)
def test_an_impediment_open_under_any_spelling_is_closed_when_it_works(filed_in, now,
                                                                       monkeypatch):
    import openfactory.lifecycle as lifecycle

    cause = CAUSES[0]
    board = _Board(**{impediment.title_on(_local(filed_in), cause): "7"})
    closed: list[str] = []

    def _close(project, ref, event, **_kw):
        closed.append(ref)
        return SimpleNamespace(refused="", outcome=lambda name: "closed")

    monkeypatch.setattr(lifecycle, "transition", _close)

    assert impediment.resolved(_local(now), cause, "it read", tracker=board) is True
    assert closed == ["7"], (filed_in, now, closed)
