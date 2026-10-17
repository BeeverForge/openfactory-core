"""What the implementing agent says it did reaches the pull request, quoted as its claim, bounded,
and never the reviewer (#627, criteria 1, 2 and 5).

Claims:
  - the body carries the executor's whole final message under `AGENT_ACCOUNT_HEADING`, after the
    gates and the review and before the `Cost:` line;
  - every agent row is quoted, an empty one as `>`, and a blank row separates the quote from the
    platform row after it, so nothing the agent writes can pose as a row the body is parsed by;
  - `#N` is `card N` and `@name` notifies nobody;
  - the block is bounded as rendered, a cut says so, and "wrote nothing" is said in words;
  - the journal note keeps its 200-character cut;
  - the reviewer is never handed the account, `ReviewInput` declares nothing new, and nothing the
    agent says moves the merge.
"""

TEST = "tests/test_what_the_agent_says_it_did_reaches_the_pull_request.py"
REVIEWER_TEST = "tests/test_the_reviewer_is_never_handed_what_the_agent_says_it_did.py"
MACHINE = "openfactory/orchestrator/machine.py"
REVIEWER = "openfactory/adapters/reviewer/base.py"
POLICY = "openfactory/orchestrator/merge_policy.py"

MUTATIONS = [
    # ── the section reaches the body, in its place ─────────────────────────────────────────────
    ("the body carries no account of what the agent did", MACHINE,
     '        lines += ["", *_account_lines(_account_of(result))]\n',
     "        pass\n"),
    ("the account is written before the review", MACHINE,
     '        if result.review is not None:\n            lines += ["", *_review_lines(result.review)]\n',
     '        lines += ["", *_account_lines(_account_of(result))]\n'
     '        if result.review is not None:\n            lines += ["", *_review_lines(result.review)]\n'),
    ("the account is the capped summary, not the whole final message", MACHINE,
     "            account = final_text(agent_result)\n",
     "            account = agent_result.summary\n"),
    # ── nothing the agent writes poses as the platform ─────────────────────────────────────────
    ("agent rows are written unquoted", MACHINE,
     '    return [f"> {_neutralised(line)}" if line.strip() else ">" for line in text.splitlines()]\n',
     '    return [_neutralised(line) if line.strip() else ">" for line in text.splitlines()]\n'),
    ("an empty agent line ends the quote", MACHINE,
     '    return [f"> {_neutralised(line)}" if line.strip() else ">" for line in text.splitlines()]\n',
     '    return [f"> {_neutralised(line)}" if line.strip() else "" for line in text.splitlines()]\n'),
    ("the cut line follows the quote with no blank row", MACHINE,
     '            out += [*([""] if kept else []),\n',
     "            out += [*([] if kept else []),\n"),
    ("the passes label follows the quote with no blank row", MACHINE,
     '        out += ["", _PASSES_LABEL, ""]\n',
     '        out += [_PASSES_LABEL, ""]\n'),
    ("a `#N` the agent writes stays a forge item", MACHINE,
     "    line = without_mentions(line)\n    spans = _spans(line)\n",
     "    spans = _spans(line)\n"),
    ("an `@name` the agent writes is left to notify", MACHINE,
     "    if not found:\n        return line\n",
     "    if True:\n        return line\n"),
    # ── bounded, and the cut says so ───────────────────────────────────────────────────────────
    ("the bound is measured on the text before quoting", MACHINE,
     "        if used + 1 + len(row) <= room:\n            kept.append(row)\n"
     "            used += 1 + len(row)\n",
     "        if used + 1 + len(row) - 2 <= room:\n            kept.append(row)\n"
     "            used += 1 + len(row) - 2\n"),
    ("the account is not bounded", MACHINE,
     "        kept = _cut_quote(account.quote, room)\n",
     "        kept = list(account.quote)\n"),
    ("a cut account says nothing about the cut", MACHINE,
     "        if shown < account.total:\n",
     "        if False:\n"),
    ("an agent that wrote nothing gets an empty section", MACHINE,
     "        out.append(_WROTE_NOTHING)\n",
     "        pass\n"),
    ("the journal note carries 2000 characters", MACHINE,
     'f"agent finished: {agent_result.summary[:200]}"',
     'f"agent finished: {agent_result.summary[:2000]}"'),
    # ── never the reviewer, and never the merge ────────────────────────────────────────────────
    ("the first review is handed the agent's account", MACHINE,
     "                    review_input=ReviewInput(\n"
     "                        ticket=ticket, diff=diff, validations=result.validations\n"
     "                    ),\n"
     "                )\n"
     "                self._count_review(result.review)\n"
     "                advisory",
     "                    review_input=ReviewInput(\n"
     "                        ticket=ticket.model_copy(update={\"context\": account}), diff=diff,\n"
     "                        validations=result.validations\n"
     "                    ),\n"
     "                )\n"
     "                self._count_review(result.review)\n"
     "                advisory",
     REVIEWER_TEST),
    ("ReviewInput gains a field for the account", REVIEWER,
     "    constraints: list[str] = Field(default_factory=list)  # ADRs it must check against\n",
     "    constraints: list[str] = Field(default_factory=list)  # ADRs it must check against\n"
     '    account: str = ""\n',
     REVIEWER_TEST),
    ("what the agent says decides the merge", POLICY,
     '    if manifest.merge_policy != "auto":\n        return False\n    if not result.all_passed:\n',
     '    if manifest.merge_policy != "auto":\n        return False\n'
     "    if not result.agent_account:\n        return False\n    if not result.all_passed:\n",
     REVIEWER_TEST),
]
