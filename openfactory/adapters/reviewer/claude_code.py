"""ClaudeCodeReviewer — the independent reviewer over `claude -p` (read-only).

Runs in plan mode (no mutations) with a prompt that contains ONLY spec + diff +
validation results, and is asked to emit a ReviewResult JSON. Same engine as the
executor, fresh context — so it does not defend the executor's original decision.

It streams like the executor (`--output-format stream-json --verbose`), so a wrapper in
front of `claude` sees the review's events, its `rate_limit_event` included; the verdict,
its cost, turns and tokens are read from the stream's terminal result event.
"""

from __future__ import annotations

import json
import shlex

from openfactory.adapters.agent.base import (
    PromptTooLarge,
    json_envelope,
    prose_only,
    result_event,
    stage_prompt,
)
from openfactory.adapters.agent.claude_code import NO_MCP_SERVERS
from openfactory.adapters.reviewer.base import (
    ACCEPTANCE_SHAPE,
    EVIDENCE_RULE,
    WRITTEN_ANSWER_RULE,
    ReviewerAdapter,
    ReviewInput,
)
from openfactory.adapters.sandbox.base import SandboxAdapter, Workspace
from openfactory.contracts import ReviewResult

_TIMEOUT = 1200

_SCHEMA = """\
Return ONLY a JSON object (no prose, no code fences) with this shape:
{
  "decision": "approved" | "approved_with_findings" | "rejected",
  "score": 0-100,
__ACCEPTANCE__
  "findings": [{"severity": "low"|"medium"|"high"|"critical", "description": str,
                "file": str|null, "line": int|null, "criterion": str|null}],
  "summary": str
}""".replace("__ACCEPTANCE__", ACCEPTANCE_SHAPE)


def _extract_json(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    return t[start : end + 1] if start != -1 and end != -1 else t


class ClaudeCodeReviewer(ReviewerAdapter):
    #: which harness produced a verdict. Every reviewer carries this so a review can be ATTRIBUTED:
    #: with the harness configurable per project, "the reviewer rejected it" is only half an answer,
    #: and comparing harnesses honestly needs to know which one spoke.
    name = "claude_code"

    def __init__(self, *, model: str | None = None) -> None:
        self.model = model

    def review(
        self, *, sandbox: SandboxAdapter, workspace: Workspace, review_input: ReviewInput
    ) -> ReviewResult:
        # OFF THE COMMAND LINE (#5): a review's prompt carries the whole diff, which is exactly
        # the value that grows without bound, so it is staged rather than interpolated — a large
        # diff no longer raises `OSError: Argument list too long` out of Popen. A box that cannot
        # stage AND a prompt past the argv ceiling is refused BY NAME, never a raw crash and never
        # a silent approval (the reviewer's asymmetry: unreadable rejects).
        try:
            prompt_path = stage_prompt(sandbox, workspace, self._prompt(review_input),
                                       phase="review", project=review_input.ticket.repo)
        except PromptTooLarge as exc:
            return ReviewResult(decision="rejected", score=0, summary=str(exc))
        rc, out = sandbox.run(
            workspace=workspace,
            # THROUGH THE BOX'S SEAM, like the executor. `harness_path` (ADR-0037 D2a) exists
            # because PATH cannot be relied on inside a CLIENT's image — and this reviewer had
            # the sandbox in its hand and asked it nothing, emitting a bare `claude`.
            #
            # FOUND LIVE on fx-dotnet (`mcr.microsoft.com/dotnet/sdk:8.0`, 2026-08-05): the CLI
            # exited 127, the envelope would not parse, and the review came back
            # `rejected / score 0 / "reviewer output could not be parsed"`. The INDEPENDENT
            # REVIEW — one of this platform's three product claims — silently does not run on
            # any client image, and reports itself as a rejection rather than as absent.
            command=self._cli(self._prompt(review_input),
                              harness=sandbox.harness_path("claude"), prompt_path=prompt_path),
            timeout=_TIMEOUT,
        )
        try:
            # THE STREAM'S LAST RESULT EVENT, then the single envelope. The review streams so a
            # wrapper in front of `claude` (account rotation, quota benching, auditing) sees its
            # `rate_limit_event`s as it sees the executor's; the stream opens with an init event,
            # which `json_envelope` would return, so the terminal `type == "result"` is read
            # instead. A CLI that answers with one envelope without a `type` (every test double,
            # an older CLI) still reads through `json_envelope`, which skips the diagnostics a CLI
            # prints above it — a bare `json.loads` dies on character one of a banner.
            envelope = result_event(out) or json_envelope(out)
            if envelope is None:
                raise ValueError("no JSON envelope in the reviewer's output")
            review = ReviewResult(**json.loads(_extract_json(str(envelope.get("result", "")))))
            # WHAT IT COST. The CLI reports it in the object this already parses — the stream's
            # result event carries the same keys as the `--output-format json` envelope
            # (`total_cost_usd`, `num_turns`, `usage`; measured on 2.1.219, 2026-10-19), so the
            # PR's `Cost:` line reads the same value either way; nothing is summed over the
            # assistant messages' own `usage`. `usage` is the CLI's own shape; absent keys stay
            # None, because unknown must not become zero (a free-looking harness wins every
            # comparison).
            usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
            return review.model_copy(update={
                "cost_usd": envelope.get("total_cost_usd"),
                "num_turns": envelope.get("num_turns"),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "model": self.model, "harness": "claude_code",
            })
        except (json.JSONDecodeError, ValueError, TypeError):
            # A REVIEW THAT COULD NOT RUN IS NOT A REJECTION, and the two used to read the same.
            # `rejected / score 0 / "could not be parsed"` sends somebody to look for what is
            # wrong with the code when nothing reviewed it at all. The DECISION stays rejected —
            # refusing to proceed as if reviewed is the safe default and must not soften — but
            # the sentence now names which of the two happened, because they need opposite
            # actions: fix the diff, or fix the box.
            # Over PROSE, not the stream: the stream now carries the reviewer's tool output, and a
            # page or log it read ("404 Not Found", "file not found") would call an
            # unreadable review one that never ran — the text match over a raw stream that
            # `prose_only` documents. A CLI missing from the box prints `sh: 1: claude: not found`
            # on a line of its own, which `prose_only` keeps.
            never_ran = rc == 127 or "not found" in prose_only(out).lower()
            summary = (
                f"the reviewer never ran: its harness exited {rc} inside the box, so this diff "
                "has NOT been reviewed. Nothing here is a judgement about the code — check the "
                "box's toolbox mount (`openfactory box prove <project>`)."
                if never_ran else
                f"reviewer output could not be parsed (rc={rc})"
            )
            return ReviewResult(decision="rejected", score=0, summary=summary)

    def _prompt(self, ri: ReviewInput) -> str:
        t = ri.ticket
        crits = "\n".join(c.bullet() for c in t.acceptance_criteria) or "(none stated)"
        # See `harness.build_review_prompt`: an unrunnable gate reported as FAIL tells the one
        # reader whose whole job is independence that the code broke something nobody checked.
        vals = "\n".join(
            f"- {v.name}: "
            f"{'PASS' if v.passed else ('COULD NOT RUN' if v.unrunnable else 'FAIL')} "
            f"(exit {v.exit_code})"
            + (f" — {v.unrunnable}; nothing was checked" if v.unrunnable else "")
            for v in ri.validations
        ) or "(none)"
        parts = [
            "You are an INDEPENDENT reviewer. You did NOT write this code. You are given "
            "only the specification, the diff, and the platform's validation results. Do "
            "not modify anything. Your job is to find evidence the change is wrong or "
            "incomplete: map each acceptance criterion to concrete evidence, hunt for "
            "regressions and unrequested scope, and check the constraints are not violated. "
            + EVIDENCE_RULE + " " + WRITTEN_ANSWER_RULE,
            f"\n# Ticket {t.id}: {t.title}\n## Objective\n{t.objective}",
            f"\n## Acceptance criteria\n{crits}",
        ]
        # See `harness.build_review_prompt`: a split child's parent is closed, and its Scope
        # reaches the reviewer only here (#624).
        if t.from_parent:
            parts.append(f"\n## From the parent card\n{t.from_parent}")
        parts.append(f"\n## Platform validation results\n{vals}")
        if ri.constraints:
            parts.append("\n## Constraints (ADRs)\n" + "\n\n".join(ri.constraints))
        parts.append("\n## Diff\n```diff\n" + ri.diff + "\n```")
        parts.append("\n" + _SCHEMA)
        return "\n".join(parts)

    def _cli(self, prompt: str, harness: str = "claude", prompt_path: str | None = None) -> str:
        # `claude -p` reads its prompt from stdin when given no argument, so
        # `cat <path> | claude -p …` keeps the command line bounded whatever the diff's size (#5).
        # `prompt_path` is None only when the box offers no staging channel and the prompt is
        # small enough for an argument.
        head = ([f"cat {shlex.quote(prompt_path)} |", harness, "-p"] if prompt_path
                else [harness, "-p", shlex.quote(prompt)])
        # `--verbose` is not optional: 2.1.219 refuses `stream-json` under `-p` without it
        # (`... requires --verbose`, exit 1), which would turn every review into "could not be
        # parsed". The prompt stays on stdin or right after `-p`: `--mcp-config` is variadic and
        # would take a word after it as a config path.
        cmd = [*head, "--output-format", "stream-json", "--verbose", "--permission-mode", "plan",
               # NO MCP SERVER OF THE ACCOUNT: the reviewer builds its own command, and was the one
               # Claude role still started with every server the account running the CLI reaches.
               *(shlex.quote(a) for a in NO_MCP_SERVERS)]
        if self.model:
            cmd += ["--model", shlex.quote(self.model)]
        return " ".join(cmd)
