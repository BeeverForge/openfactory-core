"""A later pass adds its own line under what the agent says it did, once; the reviewer and every
pass are told where a written answer is; and a forge that limits a description gives up the oldest
pass lines first (#627, criteria 3 and 4, decision 5).

Claims:
  - each later pass that pushed adds one line — kind, head, its own words on one line cut at 200 —
    and the same pass twice adds it once; a pass that pushed nothing adds none;
  - the executor's account is carried over byte for byte, never replaced by a pass's;
  - one heading, ever: a body opened before the section gains exactly one;
  - every in-run pass (recovery, gate, suppression and review repair) and every gate repair after
    an adjust has its line, in order;
  - the latest ten are listed and the rest counted, the count accumulating across republishes;
  - the section's heading ends the review's span, so a dated review never stamps it;
  - it all moves in the one write the review and the `Cost:` line share;
  - both reviewer prompts carry the written-answer rule, which names the heading; the executor and
    the recovery roles name it;
  - on a declared limit the oldest pass lines go first and are counted, the executor's block is cut
    only after them, the limit is counted in the forge's unit, the republish is fitted too, no
    limit is applied where none is declared, Azure declares its own, a non-int is no declaration,
    and a body too long without the section is said by name.
"""

TEST = "tests/test_a_later_pass_adds_its_line_to_what_the_agent_says_it_did.py"
CRITERION_4 = "tests/test_a_criterion_that_asks_for_a_written_answer_is_answered_in_the_pull_request.py"
FITS = "tests/test_a_pull_request_fits_the_forge_that_limits_its_description.py"
MACHINE = "openfactory/orchestrator/machine.py"
CONTRACT = "openfactory/contracts/run.py"
REVIEWER = "openfactory/adapters/reviewer/base.py"
HARNESS = "openfactory/adapters/reviewer/harness.py"
CLAUDE = "openfactory/adapters/reviewer/claude_code.py"
EXECUTOR_ROLE = "openfactory/org_defaults/roles/executor.md"
RECOVERY_ROLE = "openfactory/org_defaults/roles/recovery.md"
FORGE_BASE = "openfactory/adapters/forge/base.py"
AZURE = "openfactory/adapters/forge/azure_devops.py"

MUTATIONS = [
    # ── one line per pushed pass, once, under one heading ──────────────────────────────────────
    ("the same pass republished twice adds its line twice", MACHINE,
     "        if (p.kind, p.head[:12]) not in known:\n",
     "        if True:\n"),
    ("the executor's rows are re-rendered from the pass", MACHINE,
     "    account.passes += new\n",
     "    account.passes += new\n    account.quote = _quoted(new[-1].words)\n"),
    ("a later pass replaces the section with its own account", MACHINE,
     "    account.passes += new\n",
     "    account.quote, account.total, account.passes = (\n"
     "        _quoted(new[-1].words), len(new[-1].words), [])\n"),
    ("an in-run repair replaces the executor's account", MACHINE,
     '                passes.append(PassAccount(kind=f"gate repair {attempts}", '
     "words=_pass_words(rep),\n",
     "                account = final_text(rep)\n"
     '                passes.append(PassAccount(kind=f"gate repair {attempts}", '
     "words=_pass_words(rep),\n",
     CRITERION_4),
    ("a second section is written instead of the splice", MACHINE,
     "    return rows[:start] + section + rows[end:]\n",
     '    return rows[:end] + [""] + section + rows[end:]\n'),
    ("a pass that pushed nothing adds its line", MACHINE,
     "                                       account_passes=passes if pushed else ())\n",
     "                                       account_passes=passes)\n"),
    ("the gate repairs after an adjust add no line", MACHINE,
     "                passes += fixes\n",
     "                fixes = fixes\n"),
    ("a recovery adds no line", MACHINE,
     '                passes.append(PassAccount(kind=f"recovery {rec}",\n'
     "                                          words=_pass_words(agent_result)))\n",
     "                pass\n"),
    ("a gate repair adds no line", MACHINE,
     '                passes.append(PassAccount(kind=f"gate repair {attempts}", '
     "words=_pass_words(rep),\n"
     "                                          head=self._head(ws)))\n",
     "                pass\n"),
    ("a suppression repair adds no line", MACHINE,
     "                result.agent_passes.append(PassAccount(\n"
     '                    kind=f"suppression repair {supp_attempts}", words=_pass_words(rep),\n'
     "                    head=self._head(ws)))\n",
     "                pass\n"),
    ("a review repair adds no line", MACHINE,
     "                    result.agent_passes.append(PassAccount(\n"
     '                        kind=f"review repair {rev_attempts}", words=_pass_words(rep),\n'
     "                        head=self._head(ws)))\n",
     "                    pass\n"),
    ("a pass line keeps its newlines", MACHINE,
     '    words = " ".join(final_text(res).split())\n',
     "    words = final_text(res).strip()\n"),
    ("a pass line is cut at 2000 characters", MACHINE,
     "    cut = words[:AGENT_PASS_WORDS_MAX]\n",
     "    cut = words[:2000]\n"),
    ("every pass line is listed", MACHINE,
     "        shown_passes = account.passes[-AGENT_PASSES_SHOWN:]\n",
     "        shown_passes = account.passes\n"),
    ("the count of earlier passes starts again on every republish", MACHINE,
     "            account.earlier = int(m.group(1))\n",
     "            account.earlier = 0\n"),
    ("the section's heading does not end the review's span", CONTRACT,
     'AGENT_ACCOUNT_HEADING = "## What the agent says it did"\n',
     'AGENT_ACCOUNT_HEADING = "What the agent says it did"\n'),
    ("a body opened before the section gains none", MACHINE,
     "    if read is None:\n        cost_at = next(",
     "    if read is None:\n        return rows\n        cost_at = next("),
    ("the pass line is a second write", MACHINE,
     "        took = self.forge.set_pr_body(pr=pr_url, body=updated)\n",
     "        self.forge.set_pr_body(pr=pr_url, body=updated)\n"
     "        took = self.forge.set_pr_body(pr=pr_url, body=updated)\n"),
    # ── the reviewer and every pass are told where the answer is ───────────────────────────────
    ("the harness reviewer is not told where a written answer is", HARNESS,
     '        _INSTRUCTIONS + " " + EVIDENCE_RULE + " " + WRITTEN_ANSWER_RULE,\n',
     '        _INSTRUCTIONS + " " + EVIDENCE_RULE,\n',
     CRITERION_4),
    ("Claude Code's reviewer is not told where a written answer is", CLAUDE,
     '            + EVIDENCE_RULE + " " + WRITTEN_ANSWER_RULE,\n',
     "            + EVIDENCE_RULE,\n",
     CRITERION_4),
    ("the written-answer rule does not name the heading", REVIEWER,
     "from openfactory.contracts.run import AGENT_ACCOUNT_HEADING\n",
     "AGENT_ACCOUNT_HEADING = \"the agent's account\"\n",
     CRITERION_4),
    ("the executor is not told where its message is published", EXECUTOR_ROLE,
     "- **Your final message is published on the pull request**, under\n"
     "  `## What the agent says it did`, as your own account",
     "- **Your final message is published on the pull request**, under\n"
     "  its own heading, as your own account",
     CRITERION_4),
    ("the recovery agent is not told where its message is published", RECOVERY_ROLE,
     "  about the CODE, never about pushing or credentials. It is published as one line under\n"
     "  `## What the agent says it did` on the pull request",
     "  about the CODE, never about pushing or credentials. It is published as one line\n"
     "  on the pull request",
     CRITERION_4),
    # ── a forge that limits its description ────────────────────────────────────────────────────
    ("the newest pass line is shed first", MACHINE,
     "                acct.passes, acct.earlier = acct.passes[1:], acct.earlier + 1\n",
     "                acct.passes, acct.earlier = acct.passes[:-1], acct.earlier + 1\n",
     FITS),
    ("a shed pass line is not counted", MACHINE,
     "                acct.passes, acct.earlier = acct.passes[1:], acct.earlier + 1\n",
     "                acct.passes, acct.earlier = acct.passes[1:], acct.earlier\n",
     FITS),
    ("the executor's account is cut before older passes are shed", MACHINE,
     "            while len(acct.passes) > 1 and not fits(rows):\n",
     "            while False:\n",
     FITS),
    ("the limit is counted in code points", MACHINE,
     '            return measure("\\n".join(r)) <= limit\n',
     '            return len("\\n".join(r)) <= limit\n',
     FITS),
    ("a later pass's republish is not fitted", MACHINE,
     '        if ceiling is not None and ceiling[1]("\\n".join(rows)) > ceiling[0]:\n',
     "        if False:\n",
     FITS),
    ("a limit is applied where the forge declares none", MACHINE,
     '                                        description_ceiling(getattr(self, "forge", None))))\n',
     '                                        description_ceiling(getattr(self, "forge", None))\n'
     "                                        or (4000, len)))\n",
     FITS),
    ("Azure Repos declares no limit", AZURE,
     "    description_limit = _DESCRIPTION_MAX\n",
     "    no_limit_declared = _DESCRIPTION_MAX\n",
     FITS),
    ("a non-int is taken as a declared limit", FORGE_BASE,
     "    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:\n",
     "    if limit is None:\n",
     FITS),
    # review round 1 on 9882b73: this cut survived every test
    ("a limited forge keeps no executor text where some would fit", MACHINE,
     "                    rows = composed(acct, lo)\n",
     "                    rows = composed(acct, 0)\n",
     FITS),
    ("a body too long without the section is not said by name", MACHINE,
     "                    log.warning(\n"
     '                        "OPENFACTORY_PR_BODY_OVER_LIMIT',
     "                    log.info(\n"
     '                        "OPENFACTORY_PR_BODY_OVER_LIMIT',
     FITS),
]
