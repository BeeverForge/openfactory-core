"""The review is read from the last `type == "result"` event of its stream, and a single envelope still reads.

Criteria (derived from the issue's Proposal): "read the terminal `type == "result"` event (last one
wins)", "falling back to `json_envelope` for single-envelope output (older CLI, test doubles)", and
"cost and usage are read from the same event, so the PR's cost line is unchanged".

WHY THE READER HAS TO CHANGE WITH THE FLAG. `json_envelope` returns the FIRST object in the output.
For `--output-format json` that is the envelope; for `--output-format stream-json --verbose` it is
`{"type":"system","subtype":"init",…}`, which carries no `result` — measured on the pinned 2.1.219
(2026-10-19, no credential): init first, the result event last, and that result event the same
object, with the same keys, as the json envelope. So a review that streams but is still read through
`json_envelope` comes back `rejected / 0 / "reviewer output could not be parsed (rc=0)"` on every
diff, and its cost is lost with it.

Every stream here starts from 2.1.219's own lines (`tests/fixtures/claude_cli/2.1.219/`), with only
the values a review is read from changed. The box is a double that hands back `(rc, out)`, as
`test_the_REVIEWER_uses_it` (`tests/test_a_banner_line_does_not_kill_the_review.py`) does.
"""

from __future__ import annotations

import json

import pytest

from openfactory.adapters.reviewer.base import ReviewInput
from openfactory.adapters.reviewer.claude_code import ClaudeCodeReviewer
from openfactory.contracts import AcceptanceCriterion, Ticket
from tests import claude_cli_output as cli
from tests.test_a_banner_line_does_not_kill_the_review import REAL_BANNER


class _Box:
    """A box that ran the reviewer's command and got `out` back, with exit code `rc`."""

    def __init__(self, out: str, rc: int = 0):
        self._rc, self._out = rc, out

    def harness_path(self, name: str) -> str:
        return f"/toolbox/{name}"

    def run(self, *, workspace, command, timeout, **_):
        return self._rc, self._out


def _review(out: str, rc: int = 0):
    ticket = Ticket(id="1", title="Add /health", objective="Answer 200 on /health", repo="o/r",
                    acceptance_criteria=[AcceptanceCriterion(text="GET /health answers 200")])
    return ClaudeCodeReviewer().review(
        sandbox=_Box(out, rc), workspace=None,
        review_input=ReviewInput(ticket=ticket, diff="- a\n+ b", validations=[]))


APPROVAL = cli.verdict("approved", 88, "every criterion has evidence in the diff")


# ── the stream: read from its terminal result event ──────────────────────────────────────────────


def test_a_streamed_review_is_read_from_its_result_event_not_its_init_event():
    """On main `json_envelope` returned the init event, which has no `result`:
    `rejected / 0 / "reviewer output could not be parsed (rc=0)"`."""
    out = cli.stdout(cli.init_event(), cli.assistant_event(APPROVAL), cli.result_event(APPROVAL))

    review = _review(out)

    assert (review.decision, review.score) == ("approved", 88), review.summary
    assert review.summary == "every criterion has evidence in the diff"


def test_when_a_stream_carries_two_result_events_the_last_one_is_the_review():
    """Last one wins. The stream opens on a result event here, not on init, so that what main does
    with it is exactly first-wins: it read the first object, `rejected / 40`, and returned that."""
    out = cli.stdout(
        cli.result_event(cli.verdict("rejected", 40, "the first answer")),
        cli.assistant_event("looking again"),
        cli.result_event(cli.verdict("approved", 90, "the last answer")),
    )

    review = _review(out)

    assert (review.decision, review.score, review.summary) == (
        "approved", 90, "the last answer"), (review.decision, review.score, review.summary)


def test_an_event_after_the_result_event_does_not_replace_it():
    """The terminal event is the last `type == "result"`, not the last line: a `rate_limit_event`
    and a `system` event (2.1.219's own init line) printed after it leave the verdict where it was.
    On main the stream opened with init: could not be parsed."""
    out = cli.stdout(cli.init_event(), cli.assistant_event(APPROVAL), cli.result_event(APPROVAL),
                     cli.rate_limit_event(status="allowed"), cli.init_event())

    review = _review(out)

    assert (review.decision, review.score) == ("approved", 88), review.summary


def test_a_verdict_quoted_inside_a_tool_result_is_not_the_review():
    """A stream carries what the reviewer READ: a tool's output can hold an approving verdict (a
    fixture in the client's repository, a previous review's JSON). The review is the result event,
    which rejects here. On main the stream opened with init: could not be parsed."""
    out = cli.stdout(
        cli.init_event(),
        cli.assistant_event("reading the fixture"),
        cli.tool_result_event(cli.verdict("approved", 95, "a verdict the reviewer read in a file")),
        cli.result_event(cli.verdict("rejected", 30, "GET /health answers 500")),
    )

    review = _review(out)

    assert (review.decision, review.summary) == ("rejected", "GET /health answers 500"), (
        review.decision, review.summary)
    assert review.score == 30


def test_cost_turns_and_tokens_come_from_the_result_event_not_from_an_assistant_message():
    """Each assistant message carries its own `message.usage`; the result event carries the run's
    totals. Those are read, and nothing is summed. On main the stream would not parse, and
    `cost_usd` was None."""
    out = cli.stdout(
        cli.init_event(),
        cli.assistant_event("first look", tokens=(100, 200)),
        cli.assistant_event(APPROVAL, tokens=(300, 400)),
        cli.result_event(APPROVAL, cost=0.37, turns=4, tokens=(5000, 600)),
    )

    review = _review(out)

    assert (review.cost_usd, review.num_turns, review.input_tokens, review.output_tokens) == (
        0.37, 4, 5000, 600), review


@pytest.mark.parametrize("shape", ["json envelope", "stream-json --verbose"])
def test_the_same_run_streamed_or_enveloped_reports_the_same_cost_turns_and_tokens(shape):
    """The PR's `Cost:` line reads `review.cost_usd` (`orchestrator/machine.py`, held by
    `tests/test_the_review_is_charged_on_every_surface.py`), so one run must report the same four
    numbers whichever of 2.1.219's two outputs it came as. On main the stream arm's were None."""
    numbers = {"cost": 0.2591, "turns": 7, "tokens": (8123, 1456)}
    out = (cli.stdout(cli.envelope(APPROVAL, **numbers)) if shape == "json envelope" else
           cli.stdout(cli.init_event(), cli.assistant_event(APPROVAL, tokens=(1, 2)),
                      cli.result_event(APPROVAL, **numbers)))

    review = _review(out)

    assert (review.cost_usd, review.num_turns, review.input_tokens, review.output_tokens) == (
        0.2591, 7, 8123, 1456), (shape, review)


# ── what must survive: a single envelope, and a failed run's refusal ─────────────────────────────
# Green on main BY DESIGN: this is main's behaviour, and the change must not lose it. A red run
# cannot prove these; the mutation plan for this issue does
# (`tools/mutations/755_the_review_streams_and_reads_its_last_result_event.py`).


def test_a_single_envelope_without_a_type_is_still_read_through_json_envelope():
    """The shape every existing test double prints, and an older CLI's: one envelope with no `type`
    key, with a banner above it. No result event is in it, so only the fallback to `json_envelope`
    reads it. Green on main; turned red by the cut that drops the fallback (cut 4)."""
    out = REAL_BANNER + "\n" + json.dumps({
        "is_error": False, "num_turns": 3, "total_cost_usd": 0.12, "result": APPROVAL,
        "usage": {"input_tokens": 10, "output_tokens": 20}})

    review = _review(out)

    assert (review.decision, review.score) == ("approved", 88), review.summary
    assert (review.cost_usd, review.num_turns) == (0.12, 3), review


def test_the_envelope_the_pinned_cli_prints_for_json_is_still_read():
    """2.1.219's `--output-format json` output, verbatim but for an approving `result` and its cost.
    It carries `type: "result"`, so the result-event reader and the fallback both read it. Green on
    main; its cost assertion is turned red by the cut that stops reading `total_cost_usd` (cut 7)."""
    review = _review(cli.stdout(cli.envelope(APPROVAL, cost=0.05, turns=2, tokens=(40, 9))))

    assert (review.decision, review.score) == ("approved", 88), review.summary
    assert (review.cost_usd, review.num_turns, review.input_tokens, review.output_tokens) == (
        0.05, 2, 40, 9), review


def test_a_failed_result_event_is_still_a_rejection_that_says_it_could_not_be_read():
    """2.1.219's stream with no credential, verbatim, exit 1: its result event is
    `is_error: true`, `"Not logged in · Please run /login"` — prose, not a verdict. That stays a
    REJECTION (an unread review never proceeds as reviewed) whose sentence says it could not be
    read, not that the reviewer never ran. Green on main (it said "could not be parsed (rc=1)" too,
    from the init event); turned red by the cut that softens the refusal to an approval (cut 8)."""
    out = (cli.FIXTURES / "stream-json-verbose.stdout.jsonl").read_text(encoding="utf-8")

    review = _review(out, rc=1)

    assert (review.decision, review.score) == ("rejected", 0), review
    assert review.summary == "reviewer output could not be parsed (rc=1)", review.summary
    assert "never ran" not in review.summary
