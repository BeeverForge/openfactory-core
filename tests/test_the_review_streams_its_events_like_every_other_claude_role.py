"""The review streams its events like every other Claude role, so a wrapper in front of `claude` sees them.

Criterion (derived from the issue's Proposal): "Run the review as `stream-json --verbose` too." The
executor, the planner, chat, the smoke call and the model probe all ask `claude` for
`--output-format stream-json --verbose`; the native reviewer asked for `--output-format json`, so the
CLI printed one envelope when the review ended and nothing while it ran. A wrapper standing in front
of `claude` — rotating accounts, benching one a quota exhausted, auditing calls — never saw a
review's `rate_limit_event`, and could not bench an account a review used up (reported by a
downstream deployment, v0.6.0-rc.2).

THE STAND-IN IS 2.1.219, AS MEASURED, AND NOTHING MORE (2026-10-19, the pinned CLI, no credential;
`tests/fixtures/claude_cli/2.1.219/README.md`): asked `json` it prints one envelope; asked
`stream-json` without `--verbose` it refuses on stderr and exits 1 — the pin's own sentence, so a
change that drops `--verbose` turns every review unreadable here as it would on a box; asked
`stream-json --verbose` it prints init, a `rate_limit_event` (the shape the binary declares; no
credentialed call was available to observe one), an assistant message and the result event. It runs
under the REAL worktree box, through a real `/bin/sh`, in a home of the test's own, and writes down
the argv its process was handed: the guard reads that argv, not the command string.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from openfactory.adapters.agent.base import json_objects
from openfactory.adapters.agent.claude_code import NO_MCP_SERVERS
from openfactory.adapters.reviewer.base import ReviewInput
from openfactory.adapters.reviewer.claude_code import ClaudeCodeReviewer
from openfactory.adapters.sandbox.base import Workspace
from openfactory.adapters.sandbox.worktree import WorktreeSandbox
from openfactory.contracts import AcceptanceCriterion, Ticket
from tests import claude_cli_output as cli

#: The refusal 2.1.219 prints on stderr for `stream-json` without `--verbose`, measured.
NEEDS_VERBOSE = "Error: When using --print, --output-format=stream-json requires --verbose"

_STAND_IN = '''\
#!{interpreter}
"""Stands in for `claude` 2.1.219 as measured: writes down its argv, then answers by format."""
import json, sys
from pathlib import Path

args = sys.argv[1:]
with open({calls!r}, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(args) + "\\n")
# `claude -p` with no prompt argument reads the prompt from stdin (the staged route)
after_p = args[args.index("-p") + 1] if "-p" in args and args.index("-p") + 1 < len(args) else "-"
if after_p.startswith("-"):
    sys.stdin.read()
fmt = args[args.index("--output-format") + 1] if "--output-format" in args else "text"
if fmt == "stream-json" and "--verbose" not in args:
    print({needs_verbose!r}, file=sys.stderr)
    sys.exit(1)
sys.stdout.write(Path({answers!r}, fmt + ".out").read_text(encoding="utf-8"))
'''

APPROVAL = cli.verdict("approved", 87, "every criterion has evidence in the diff")
COST, TURNS, TOKENS = 0.4213, 6, (5120, 870)


@pytest.fixture
def box(tmp_path, monkeypatch):
    """The REAL worktree box whose `claude` is the stand-in, in a home of the test's own; `run` is
    wrapped so the test keeps the `(rc, out)` the box handed the reviewer."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    answers = tmp_path / "answers"
    answers.mkdir()
    (answers / "json.out").write_text(
        cli.stdout(cli.envelope(APPROVAL, cost=COST, turns=TURNS, tokens=TOKENS)), encoding="utf-8")
    (answers / "stream-json.out").write_text(cli.stdout(
        cli.init_event(),
        cli.rate_limit_event(status="allowed_warning", rate_limit_type="five_hour",
                             utilization=0.91),
        cli.assistant_event(APPROVAL, tokens=(11, 22)),
        cli.result_event(APPROVAL, cost=COST, turns=TURNS, tokens=TOKENS),
    ), encoding="utf-8")
    calls = tmp_path / "calls.jsonl"
    stand_in = tmp_path / "bin" / "claude"
    stand_in.parent.mkdir()
    stand_in.write_text(_STAND_IN.format(interpreter=sys.executable, calls=str(calls),
                                         needs_verbose=NEEDS_VERBOSE, answers=str(answers)))
    stand_in.chmod(0o755)

    sandbox = WorktreeSandbox(root=tmp_path / "worktrees")
    ws = Workspace(path=tmp_path / "worktrees" / "job", branch="openfactory/review",
                   base_branch="main")
    ws.path.mkdir(parents=True)
    monkeypatch.setattr(sandbox, "harness_path", lambda name: str(stand_in))
    ran: list[tuple[int, str]] = []
    real_run = sandbox.run

    def _run(**kw):
        rc, out = real_run(**kw)
        ran.append((rc, out))
        return rc, out

    monkeypatch.setattr(sandbox, "run", _run)
    yield sandbox, ws, calls, ran
    sandbox.cleanup(workspace=ws)


def _review(sandbox, ws):
    ticket = Ticket(id="1", title="Add /health", objective="Answer 200 on /health", repo="o/r",
                    acceptance_criteria=[AcceptanceCriterion(text="GET /health answers 200")])
    return ClaudeCodeReviewer().review(
        sandbox=sandbox, workspace=ws,
        review_input=ReviewInput(ticket=ticket, diff="- a\n+ b", validations=[]))


def _argv(calls: Path) -> list[list[str]]:
    return [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]


def _stands_together(argv: list[str], words: tuple[str, ...]) -> bool:
    return any(tuple(argv[i:i + len(words)]) == words for i in range(len(argv)))


def test_the_review_asks_the_cli_for_stream_json_and_verbose_on_both_prompt_routes(
        box, monkeypatch):
    """Both ways the prompt reaches `claude`: staged and piped on stdin (`cat <path> | claude -p …`),
    and as the argument after `-p` when the box offers no staging channel. On main the argv the
    process was handed said `--output-format json`, with no `--verbose`."""
    sandbox, ws, calls, _ = box
    _review(sandbox, ws)                                    # the box stages: `cat <path> |`
    monkeypatch.setattr(sandbox, "stage_input", None)       # a box with no channel: on argv
    _review(sandbox, ws)

    staged, on_argv = _argv(calls)
    assert staged[1].startswith("-") and not on_argv[1].startswith("-"), (
        f"the two runs did not take the two routes: {staged[:2]} / {on_argv[:2]}")
    for route, argv in (("staged", staged), ("on argv", on_argv)):
        fmt = argv[argv.index("--output-format") + 1]
        assert fmt == "stream-json", f"{route}: the review asked the CLI for {fmt!r}: {argv}"
        assert "--verbose" in argv, (
            f"{route}: stream-json without --verbose is refused by the CLI (rc 1): {argv}")
        assert _stands_together(argv, ("--permission-mode", "plan")), f"{route}: {argv}"
        assert _stands_together(argv, NO_MCP_SERVERS), f"{route}: {argv}"


def test_a_rate_limit_event_the_cli_emits_during_a_review_reaches_the_output_and_the_review_still_reads(
        box):
    """What a wrapper in front of `claude` sees is what the CLI writes to stdout, and the box hands
    that same output to the reviewer. On main the stand-in, asked for `json`, printed only the final
    envelope — as 2.1.219 does — so no `rate_limit_event` was there to see."""
    sandbox, ws, _, ran = box

    review = _review(sandbox, ws)

    [(rc, out)] = ran
    events = [o for o in json_objects(out) if o.get("type") == "rate_limit_event"]
    assert events, f"no rate_limit_event in what the CLI printed for the review (rc={rc}): {out!r}"
    assert events[0]["rate_limit_info"]["status"] == "allowed_warning"
    assert (review.decision, review.score) == ("approved", 87), review.summary
    assert review.cost_usd == COST, review
