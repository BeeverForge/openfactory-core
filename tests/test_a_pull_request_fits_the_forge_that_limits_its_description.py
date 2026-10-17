"""A pull request fits the forge that limits its description, and gives up the oldest pass lines
first (#627, decision 5).

Azure Repos refuses a description over 4,000 UTF-16 code units (`azure_devops.py`, #433), and its
adapter cuts an over-long one FROM THE END as a last resort — which removes the `Cost:` line first,
then the newest pass, then the review. #627's section can reach about 4,850 characters on its own,
so on that forge the body is now fitted by its one writer, from a limit the forge DECLARES
(`description_limit`, `description_length`): the oldest pass lines are folded into the count first,
then the executor's quoted block is cut from its end with its cut line saying so. The `Cost:` line,
the review and the newest pass line always survive when the body without the section fits; where
even that is too long, the section shrinks to its heading, claim, cut line and newest pass, the
machine says so by name, and the adapter's cut remains the backstop.

A forge that declares nothing has no limit: every decided line stands.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import test_the_pull_request_says_what_the_card_says as card_says
import test_walking_skeleton as spine

from openfactory.adapters.forge import azure_devops
from openfactory.adapters.forge import base as forge_base
from openfactory.adapters.forge.azure_devops import AzureReposForge
from openfactory.adapters.forge.local import LocalForge
from openfactory.contracts import (
    AcceptanceCriterion,
    AgentRunResult,
    Finding,
    Manifest,
    ReviewResult,
    RunResult,
    Ticket,
    ValidationResult,
)
from openfactory.contracts import run as run_contract
from openfactory.contracts.run import KnowledgeVerdict
from openfactory.orchestrator.machine import _COST_LINE, _REVIEW_HEADING, JobRunner

repo = spine.repo

HEADING = getattr(run_contract, "AGENT_ACCOUNT_HEADING", "## What the agent says it did")
# Azure's own values, read from the adapter — never retyped here
LIMIT = getattr(AzureReposForge, "description_limit", AzureReposForge._DESCRIPTION_MAX)
MEASURE = getattr(AzureReposForge, "description_length", azure_devops._vendor_length)
PassAccount = getattr(run_contract, "PassAccount", None)
NEWEST = "NEWEST-PASS-SENTINEL"


class _Limited:
    """A forge declaring Azure Repos' limit, in its unit."""

    description_limit = LIMIT
    description_length = staticmethod(MEASURE)


class _LimitedFake(spine.FakeForge):
    description_limit = LIMIT
    description_length = staticmethod(MEASURE)

    def __init__(self) -> None:
        super().__init__()
        self.handed: list[str] = []

    def set_pr_body(self, *, pr: str, body: str, repo: str = "") -> bool:
        self.handed.append(body)
        return super().set_pr_body(pr=pr, body=body, repo=repo)


def _card82(objective: str = "") -> Ticket:
    return Ticket(
        id="#82", title="fix the flicker on level reload", repo="o/game",
        objective=objective or (
            "The screen flickers for two or three frames every time a level is reloaded, and on "
            "slower machines the player falls through the floor once. Find out why, fix it, and "
            "say in the card result which root causes you found, so the next card can address "
            "whatever is left. " * 3),
        acceptance_criteria=[AcceptanceCriterion(text="the flicker is gone"),
                             AcceptanceCriterion(text="Say which root causes you found")])


def _passes(n: int = 12, words: str = "") -> list:
    assert PassAccount is not None, "there is no pass line to fit"
    out = [PassAccount(kind=f"gate repair {i}", head=f"{i:012x}" + "0" * 28,
                       words=(words or ("repaired the gate 🟢 " * 20))[:200] + "…")
           for i in range(1, n + 1)]
    out[-1] = out[-1].model_copy(update={"words": f"{NEWEST} " + out[-1].words})
    return out


def _result(message: str, passes: list | None = None, **extra) -> RunResult:
    validations = [ValidationResult(name=n, command=f"make {n}", exit_code=0, passed=True)
                   for n in ("test", "lint", "types", "security", "e2e")]
    review = ReviewResult(
        decision="approved_with_findings", score=81,
        summary="The reload path is fixed and the atlas is loaded once; three smaller points.",
        findings=[Finding(severity=s, description=f"{s} point about the reload path " * 3,
                          file="src/level.py", line=40 + i)
                  for i, s in enumerate(("medium", "low", "low"))])
    return RunResult(
        ticket_id="#82", state="validating", branch="openfactory/82", validations=validations,
        review=review, total_cost_usd=1.2345, touched_components=["engine", "levels"],
        knowledge_stance="amber", knowledge_note="the module map is a day old",
        knowledge_verdicts=[KnowledgeVerdict(path=f"src/level{i}.py", verdict="green",
                                             reason="described") for i in range(4)],
        agent_account=message, agent_account_chars=len(message),
        agent_passes=passes if passes is not None else _passes(), **extra)


def _body(forge, result: RunResult, ticket: Ticket | None = None) -> str:
    holder = SimpleNamespace(manifest=Manifest(validate={"test": "true"}), _profile=None,
                             forge=forge)
    return JobRunner._pr_body(holder, ticket or _card82(), result)


EMOJI_MESSAGE = ("Root causes: 🟢 the atlas loaded twice; 🟡 stale grid cells. " * 40)[:2000]


def _rows_of(body: str) -> list[str]:
    rows = body.splitlines()
    assert HEADING in rows, "the pull request carries no account of what the agent did"
    return rows[rows.index(HEADING):]


def _pass_rows(body: str) -> list[str]:
    return [r for r in _rows_of(body) if r.startswith("> - ")]


def _earlier(body: str) -> int:
    found = [int(m.group(1)) for r in _rows_of(body)
             if (m := re.match(r"^(\d+) earlier pass", r))]
    return found[0] if found else 0


def _quote(body: str) -> list[str]:
    rows = _rows_of(body)
    label = next((i for i, r in enumerate(rows) if r.startswith("Later passes")), len(rows))
    return [r for r in rows[:label] if r.startswith(">")]


def _cut_line(body: str) -> str | None:
    return next((r for r in _rows_of(body) if "characters; the first" in r), None)


# ── the worst case on Azure Repos ────────────────────────────────────────────────────────────────

def test_a_worst_case_body_with_emoji_on_azure_keeps_the_cost_line_the_review_and_the_newest_pass():
    body = _body(_Limited(), _result(EMOJI_MESSAGE))

    assert MEASURE(body) <= LIMIT, f"{MEASURE(body)} units on a forge that refuses over {LIMIT}"
    assert f"{_COST_LINE}1.2345" in body.splitlines()
    assert any(r.startswith(_REVIEW_HEADING) for r in body.splitlines())
    rows = _pass_rows(body)
    assert rows and NEWEST in rows[-1], "the newest pass was shed"
    assert _earlier(body) + len(rows) == 12, "a shed pass was neither shown nor counted"
    assert AzureReposForge._fit_description(body) == body


def test_the_oldest_pass_lines_go_first_and_are_counted():
    full = [p.words for p in _passes()]
    body = _body(_Limited(), _result(EMOJI_MESSAGE))

    shown = [r.split(" — ", 1)[1] for r in _pass_rows(body)]
    assert shown == full[len(full) - len(shown):], "the shown passes are not the newest ones"
    assert len(shown) + _earlier(body) == len(full)


def test_the_executors_account_is_cut_only_after_the_older_passes_are_gone():
    message = ("the root cause was the cache key. " * 59)[:1990]  # no emoji
    # case A: shedding older passes is enough — the account stands whole
    shorter = message[:1400]
    fits = _body(_Limited(), _result(shorter))
    assert MEASURE(fits) <= LIMIT
    assert len(_pass_rows(fits)) < 12, "nothing was shed — this case measures nothing"
    assert _cut_line(fits) is None, "the account was cut while older passes could still go"
    assert _quote(fits) == [f"> {shorter}"]

    # case B: even one pass does not fit — exactly the newest remains, and the account is cut
    long = _card82(objective="The level reload flickers. " * 70)
    tight = _body(_Limited(), _result(message), long)
    assert MEASURE(tight) <= LIMIT
    rows = _pass_rows(tight)
    assert len(rows) == 1 and NEWEST in rows[0], rows
    cut = _cut_line(tight)
    assert cut and f"was {len(message)} characters" in cut, cut


def test_the_limit_is_counted_in_the_forges_own_unit():
    message = "😀" * 900
    result = _result(message, passes=_passes(1, words="ok"))
    ticket = _card82(objective="flicker " * 150)
    unlimited = _body(None, result, ticket)
    assert len(unlimited) <= LIMIT < MEASURE(unlimited), (
        "this body does not separate the two units — the case measures nothing",
        len(unlimited), MEASURE(unlimited))

    fitted = _body(_Limited(), result, ticket)
    assert MEASURE(fitted) <= LIMIT, MEASURE(fitted)


def test_a_fitted_body_is_never_cut_again_by_the_forge():
    shapes = [_result(EMOJI_MESSAGE), _result("short"), _result("x" * 5000, passes=[]),
              _result("😀" * 900, passes=_passes(1, words="ok"))]
    for result in shapes:
        body = _body(_Limited(), result)
        assert AzureReposForge._fit_description(body) == body
        assert "[cut to fit" not in body


def test_an_adjust_on_a_limited_forge_republishes_a_fitted_body(repo: Path, tmp_path: Path):
    card_says._pr_branch(repo)
    before = _body(_Limited(), _result(EMOJI_MESSAGE))
    forge = _LimitedFake()
    forge.opened = {"body": before}
    runner = spine._runner(repo, spine.FakeTracker(spine._sizing_ticket_id("#9")),
                           Manifest(validate={"test": "true"}), tmp_path, agent=_Adjusts(),
                           forge=forge)

    runner.repair_ci("#9", "make the button blue", pr_url="https://forge/pr/1", human=True)

    assert forge.handed, "the adjust's line was never written"
    after = forge.handed[-1]
    assert MEASURE(after) <= LIMIT, MEASURE(after)
    assert any(r.startswith(_COST_LINE) for r in after.splitlines())
    assert any(r.startswith(_REVIEW_HEADING) for r in after.splitlines())
    assert _pass_rows(after)[-1].startswith("> - adjust · `"), _pass_rows(after)[-1:]
    assert "\n".join(_quote(before)).startswith("\n".join(_quote(after))), (
        "the executor rows kept are not the ones that stood")


class _Adjusts:
    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        return AgentRunResult(ok=True)

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        (workspace.path / "blue.py").write_text("COLOUR = 'blue'\n")
        return AgentRunResult(ok=True, summary="made the button blue 🟦", cost_usd=0.01)


def test_a_forge_without_a_limit_keeps_every_decided_line():
    for forge in (spine.FakeForge(), LocalForge):
        body = _body(forge, _result(EMOJI_MESSAGE))
        assert len(_pass_rows(body)) == 10 and _earlier(body) == 2, type(forge).__name__
        # the decided bound, 2000 characters as rendered, and nothing below it
        assert 1990 < len("\n".join(_quote(body))) <= 2000


def test_a_body_too_long_without_the_account_is_said_by_name(caplog):
    caplog.set_level(logging.WARNING)
    ticket = _card82(objective="the objective alone is longer than the forge takes. " * 100)
    body = _body(_Limited(), _result(EMOJI_MESSAGE), ticket)

    section = _rows_of(body)
    section = section[:next(i for i, r in enumerate(section) if r.startswith(_COST_LINE))]
    # heading, claim, cut line, and the newest pass under its label and the count of the rest
    assert [r for r in section if r.strip()] == [
        section[0], section[1], _cut_line(body), section[section.index(_cut_line(body)) + 2],
        "11 earlier passes are not shown.", _pass_rows(body)[0]], section
    assert "first 0 are shown" in _cut_line(body)
    assert NEWEST in _pass_rows(body)[0]
    assert any("OPENFACTORY_PR_BODY_OVER_LIMIT" in r.getMessage() for r in caplog.records)
    assert MEASURE(body) > LIMIT, "the machine cut the objective — that is the adapter's backstop"
    assert AzureReposForge._fit_description(body) != body


def test_every_forge_that_cuts_its_description_declares_the_limit_it_cuts_at():
    from openfactory.adapters.forge.registry import FORGES

    ceiling = getattr(forge_base, "description_ceiling", None)
    assert ceiling is not None, "no forge can declare the limit it cuts a description at"
    for kind, builder in FORGES.items():
        found = re.search(r"from (openfactory\.adapters\.forge\.\w+) import (\w+)",
                          inspect.getsource(builder))
        assert found, f"cannot tell which adapter the {kind!r} row builds"
        cls = getattr(importlib.import_module(found.group(1)), found.group(2))
        said = ceiling(cls)
        assert said is None or (isinstance(said[0], int) and callable(said[1])), (kind, said)
    limit, measure = ceiling(AzureReposForge)
    assert limit == AzureReposForge._DESCRIPTION_MAX and measure("😀") == 2
    assert ceiling(MagicMock()) is None
    assert ceiling(SimpleNamespace(description_limit="4000")) is None
