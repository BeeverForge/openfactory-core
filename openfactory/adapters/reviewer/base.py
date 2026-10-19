"""ReviewerAdapter — the independent reviewer (ADR-0001 D-5).

A separate context whose value is *context independence*: it receives only the
spec, the diff, and the validation results — never the executor's conversation. Its
job is to find evidence the solution is wrong or incomplete and emit structured
findings, so the human reads a report instead of the raw diff. Same engine as the
executor (Claude), different role — so it is its own adapter, not a method on the
coding agent.

What the implementing agent SAYS it did goes on the pull request, for the person deciding — never
here (#627, D-5): `ReviewInput` carries no field for it, and a criterion that asks for a written
answer is left `unknown` for that person by `WRITTEN_ANSWER_RULE` (D-11: the platform does not
believe the agent).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from openfactory.adapters.sandbox.base import SandboxAdapter, Workspace
from openfactory.contracts import ReviewResult, Ticket, ValidationResult
from openfactory.contracts.run import AGENT_ACCOUNT_HEADING

#: HOW A CRITERION IS PASSED, said to every reviewer the same way (#447). The platform checks the
#: citation against the gates that ran (`review/evidence.py`) — so the rule the model is given and
#: the rule the code applies are one rule, and a verdict means the same whichever harness wrote it.
EVIDENCE_RULE = (
    "A criterion is `passed` only on evidence a gate listed under the platform's validation "
    "results EXECUTED: cite that gate in `evidence` as `gate:<name>` (for example `gate:test — "
    "tests/test_x.py::test_y covers it`). Reading the diff is not execution, and neither is a test "
    "that no listed gate runs — for those, the status is `unknown`, and if a test or command in "
    "the repository WOULD verify the criterion, name it in `would_verify` (for example `npm run "
    "test:e2e — frontend/e2e/home.spec.ts`). The platform confirms every `gate:` citation against "
    "the gates that actually ran; a criterion it cannot confirm is reported as not verified, "
    "whatever the decision says."
)

#: WHERE A WRITTEN ANSWER IS, said to every reviewer the same way (#627). A criterion that asks the
#: implementing agent to REPORT something — "say which root causes you found" — is answered in the
#: agent's final message, which the pull request publishes under `AGENT_ACCOUNT_HEADING` and which
#: this reviewer is deliberately not shown (ADR-0001 D-5). Judged against the diff, such a criterion
#: was marked failed because the diff lacked the answer, and could never be satisfied. It follows
#: `EVIDENCE_RULE`'s path instead: `unknown`, and the change reads NOT VERIFIED, so a person reads
#: the answer at the merge. The rule carries no agent text.
WRITTEN_ANSWER_RULE = (
    "You judge the change, not the implementing agent's account of it. A criterion that asks the "
    "agent to report, state or explain something in writing is answered in the pull request under "
    f"`{AGENT_ACCOUNT_HEADING}`, which you are not shown: mark it `unknown`, say in `evidence` "
    f"that it is answered under `{AGENT_ACCOUNT_HEADING}` for a person to read, leave "
    "`would_verify` empty, and never `failed` because the diff does not contain the answer."
)

#: The acceptance entry every reviewer returns, with the field the rule above asks for.
ACCEPTANCE_SHAPE = ('  "acceptance": [{"criterion": str, "status": "passed"|"failed"|"unknown", '
                    '"evidence": str|null, "would_verify": str|null}],')


class ReviewInput(BaseModel):
    ticket: Ticket
    # the code change, as text — the reviewer never sees how it was made, nor what the agent says
    # it did: that is the pull request's, for the person (#627)
    diff: str
    validations: list[ValidationResult] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)  # ADRs it must check against


@runtime_checkable
class ReviewerAdapter(Protocol):
    def review(
        self, *, sandbox: SandboxAdapter, workspace: Workspace, review_input: ReviewInput
    ) -> ReviewResult:
        """Judge the change against the spec and emit a structured verdict."""
        ...
