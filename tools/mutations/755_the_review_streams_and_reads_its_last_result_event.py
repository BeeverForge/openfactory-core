"""The review streams its events, and is read from the last result event of its stream (#755).

Run:  .venv/bin/python tools/mutate.py tools/mutations/755_the_review_streams_and_reads_its_last_result_event.py

The claims, each a row:

  * the review asks `claude` for `--output-format stream-json --verbose`, so a wrapper in front of
    it sees the review's `rate_limit_event` (row 1 is the defect itself); and `--verbose` with it,
    because the pinned 2.1.219 refuses `stream-json` under `-p` without it (row 2: the stand-in in
    test A refuses as the CLI does, measured 2026-10-19);
  * the verdict is the LAST `type == "result"` event (row 3), not the init event `json_envelope`
    returns first (row 5), not whatever object closes the output (row 6), and not a verdict the
    reviewer read in a tool's output (row 10);
  * a single envelope without a `type` still reads through `json_envelope` (row 4);
  * the cost, turns and tokens come from that event (row 7);
  * a failed result is still a REJECTION (row 8), and "not found" in a tool result is not a review
    that never ran (row 9);
  * every door of every Claude role streams, the shared builder's included (row 11, review of #922:
    with `ClaudeCodeAdapter._cli`'s flag cut to `json`, 63 modules and 1746 tests stayed green on
    82c8e6d; the sweep in `ROLES` turns the executor, product and techlead doors red);
  * the shell's own `not found` says the reviewer never ran whatever the exit code, not on 127 alone
    (row 12, #919: with the clause dropped, 183 tests of 10 reviewer modules stayed green on 82c8e6d).

TWO TESTS ARE HELD BY ANOTHER ROW THAN THE ONE THAT NAMES THEM. The 2.1.219 `json` envelope carries
`type: "result"`, so `result_event` reads it without the fallback: dropping the fallback (row 4)
leaves `test_the_envelope_the_pinned_cli_prints_for_json_is_still_read` green, and row 7 is what
turns it red. And the result event comes after the tool result in a stream, so neither first-wins
(row 3) nor "last object of any type" (row 6) reaches the quoted verdict; on the dry run only row 5
did. Row 10 is aimed at it: it reads the verdict as the first reply text that looks like one,
through `base.reply_texts` — the house's own "every string that is a model reply", which walks a
`content` key and so takes a `tool_result`'s content for a reply. That is a real way to write this
reader, and the test is what refuses it.
"""

TEST = "tests/test_the_review_is_read_from_the_last_result_event_of_its_stream.py"
STREAMS = "tests/test_the_review_streams_its_events_like_every_other_claude_role.py"
ROLES = "tests/test_a_role_reaches_only_the_tools_it_is_given.py"
AGENT = "openfactory/adapters/agent/claude_code.py"
REVIEWER = "openfactory/adapters/reviewer/claude_code.py"
BASE = "openfactory/adapters/agent/base.py"

MUTATIONS = [
    ("THE DEFECT: the review asks the CLI for one envelope at the end, and a wrapper in front of "
     "`claude` never sees its rate_limit_event", REVIEWER,
     '"--output-format", "stream-json", "--verbose",', '"--output-format", "json",', STREAMS),
    ("`--verbose` dropped: 2.1.219 refuses stream-json under -p, and every review is unread",
     REVIEWER, '"stream-json", "--verbose", "--permission-mode"', '"stream-json", "--permission-mode"',
     STREAMS),
    ("first wins: the first result event of a stream is the review", BASE,
     "            found = obj\n    return found", "            return obj\n    return None"),
    ("the fallback dropped: a single envelope without a `type` is no longer read", REVIEWER,
     "envelope = result_event(out) or json_envelope(out)", "envelope = result_event(out)"),
    ("the reader reverted: the stream is read through `json_envelope`, which returns its init event",
     REVIEWER, "envelope = result_event(out) or json_envelope(out)",
     "envelope = json_envelope(out)"),
    ("the type filter dropped: the last object of any type closes the review", BASE,
     '        if obj.get("type") == "result":\n            found = obj',
     "        if obj:\n            found = obj"),
    ("the review's cost is lost: the PR's Cost: line is the executor's alone again", REVIEWER,
     '"cost_usd": envelope.get("total_cost_usd"),', '"cost_usd": None,'),
    ("the refusal softened: an unread review is approved", REVIEWER,
     'return ReviewResult(decision="rejected", score=0, summary=summary)',
     'return ReviewResult(decision="approved", score=0, summary=summary)'),
    ("the never-ran test reads the raw stream: a 404 the reviewer read says the reviewer never ran",
     REVIEWER, '"not found" in prose_only(out).lower()', '"not found" in (out or "").lower()'),
    ("the verdict is the first reply text that looks like one: a verdict quoted in a tool's output "
     "is taken for the review", REVIEWER,
     'json.loads(_extract_json(str(envelope.get("result", ""))))',
     "json.loads(_extract_json(next((t for t in __import__('openfactory.adapters.agent.base', "
     "fromlist=['reply_texts']).reply_texts(out) if '\"decision\"' in t), "
     "str(envelope.get('result', '')))))"),
    ("the shared builder asks for one envelope: no executor, tech lead or product door streams, and "
     "a wrapper sees none of their events until the run ends", AGENT,
     '            "--output-format", "stream-json", "--verbose",\n            "--permission-mode", "acceptEdits",',
     '            "--output-format", "json",\n            "--permission-mode", "acceptEdits",', ROLES),
    ("the never-ran test reads the exit code alone: a CLI missing from the box under any exit but 127 "
     "is told as an unreadable review", REVIEWER,
     'never_ran = rc == 127 or "not found" in prose_only(out).lower()', "never_ran = rc == 127"),
]
