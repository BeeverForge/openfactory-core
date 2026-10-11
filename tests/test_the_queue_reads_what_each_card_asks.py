"""The queue is proposed from what each candidate asks, in its own words, bounded (#567).

THE RUN (v0.5.0-rc.1). The role was asked to order the backlog and to hold back what "depends on
something not done" — over a list of titles: "the bodies would cost more than they add". On the
same afternoon it advised closing the only card carrying a requirement's first front, and proposed
an order that started with the card building on it. That card's body opened with "building on the
per-version storage introduced for REQ-0066"; its first criterion began "given the per-version rows
introduced by the persistence change". A title carries neither.

Now each candidate is given with what it asks, the requirement it executes and its first criteria,
bounded per card — the size the old comment worried about is met by the bound.
"""

from __future__ import annotations

from openfactory.product.queue import Readiness, proposal_prompt, what_it_asks
from openfactory.product.triage import Ticket

BUILDS_ON = Ticket(
    number="1000010", title="Listar, abrir e baixar versões passadas",
    body="## Objective\n\nBuilding on the per-version storage introduced for REQ-0066, list, "
         "open and download past versions.\n\n## Acceptance criteria\n\n"
         "- Given the per-version rows introduced by the persistence change, past versions are "
         "listed newest first\n- A past version can be opened and downloaded\n\n## Source\n\n"
         "Executes **REQ-0066** in docs — #66.\n")


def _prompt(*candidates: Ticket) -> str:
    return proposal_prompt(readiness=Readiness(todo=[], ready=[c.number for c in candidates],
                                               in_progress=0),
                           candidates=list(candidates), limit=5)


def test_TODAYS_RUN_the_card_that_builds_on_another_says_so_in_the_prompt():
    prompt = _prompt(BUILDS_ON)

    assert "Building on the per-version storage introduced for REQ-0066" in prompt, prompt
    assert "executes: REQ-0066" in prompt, prompt
    assert "Given the per-version rows introduced by the persistence change" in prompt, prompt


def test_the_role_is_asked_to_hold_back_what_builds_on_something_not_delivered():
    prompt = _prompt(BUILDS_ON)

    assert "builds on something no card already done, being worked on, or ahead of it" in prompt
    assert "held back, saying what it waits for" in prompt


def test_a_card_without_an_objective_section_is_read_from_the_opening_of_its_body():
    plain = Ticket(number="7", title="Restaurar uma versão",
                   body="Building on the version list, restore one as current.\n\n"
                        "## Acceptance criteria\n\n- A past version can be restored\n")

    assert what_it_asks(plain)[0] == (
        "  - asks: Building on the version list, restore one as current.")


def test_each_card_is_bounded_and_says_what_it_left_out():
    long = Ticket(number="8", title="t", body="## Objective\n\n" + "palavra " * 200 +
                  "\n\n## Acceptance criteria\n\n" +
                  "".join(f"- criterion {n} " + "x" * 300 + "\n" for n in range(10)))

    lines = what_it_asks(long)

    assert len(lines) == 1 + 4 + 1, lines
    assert all(len(line) <= len("  - criterion: ") + 160 for line in lines[1:5]), lines
    assert len(lines[0]) <= len("  - asks: ") + 240 and lines[0].endswith("…"), lines[0]
    assert lines[-1] == "  - (+6 more criteria not shown)", lines[-1]


def test_a_card_with_no_body_is_its_title_alone():
    assert what_it_asks(Ticket(number="9", title="Só o título")) == []
    assert "- #9: Só o título\n" in _prompt(Ticket(number="9", title="Só o título")) + "\n"
