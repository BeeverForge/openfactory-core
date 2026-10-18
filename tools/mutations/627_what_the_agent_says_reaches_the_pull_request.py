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
     # re-pinned after the fitting (decision 5) moved the section into `_fit_to_forge`
     '        return "\\n".join(_fit_to_forge([*lines, ""], _account_of(result), cost,\n'
     '                                        description_ceiling(getattr(self, "forge", None))))\n',
     '        return "\\n".join([*lines, *cost])\n'),
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
    # re-pinned after review round 1 (9882b73) replaced the paragraph model with escaping
    # re-pinned after review round 3 (be48a54) split bare links out first
    ("a `#N` the agent writes stays a forge item", MACHINE,
     '_MARKUP.sub(r"\\\\\\1", without_mentions(piece))',
     '_MARKUP.sub(r"\\\\\\1", piece)'),
    ("an `@name` the agent writes is left to notify", MACHINE,
     '    text = "".join(f"`{piece}`" if k % 2 else _A_HANDLE.sub(\n',
     '    text = "".join(f"`{piece}`" if k % 2 else (lambda f, t: t)(\n'),
    # ── review round 1 on 9882b73: the shapes GitHub linked, and what fuzzing found next ─────
    ("`_@name_` is skipped by a word-character look-behind", MACHINE,
     '_A_HANDLE = re.compile(r"(?<![A-Za-z0-9])@',
     '_A_HANDLE = re.compile(r"(?<!\\w)@'),
    ("the agent's backticks pair with the wrapping (its markup is not escaped)", MACHINE,
     '_MARKUP.sub(r"\\\\\\1", without_mentions(piece))',
     "without_mentions(piece)"),
    # re-pinned after review round 2 (35a1cc0) added the emphasis markers
    ("an HTML block or a backslash the agent writes is left to unwrap the name", MACHINE,
     '_MARKUP = re.compile(r"([\\\\`<&*_~])")\n',
     '_MARKUP = re.compile(r"([`*_~])")\n'),
    ("wrapping the first of `@x@name` exposes the second", MACHINE,
     '@([A-Za-z0-9](?:[\\w.@-]*\\w)?)")',
     '@([A-Za-z0-9](?:[\\w.-]*\\w)?)")'),
    ("a line of the agent's renders as a heading", MACHINE,
     '    return _A_HEADING.sub(r"\\1\\\\\\2", text)\n',
     "    return text\n"),
    ("a cut may split a wrapped name's span open", MACHINE,
     "            if start < cut < end:\n                cut = start\n",
     "            if False:\n                cut = start\n"),
    # ── review round 2 on 35a1cc0: identifiers read as written, and the guards that survived ─
    ("the agent's `__init__` and `*.py` render as emphasis", MACHINE,
     '_MARKUP = re.compile(r"([\\\\`<&*_~])")\n',
     '_MARKUP = re.compile(r"([\\\\`<&])")\n'),
    ("an entity the agent writes decodes to a name", MACHINE,
     '_MARKUP = re.compile(r"([\\\\`<&*_~])")\n',
     '_MARKUP = re.compile(r"([\\\\`<*_~])")\n'),
    ("a heading after a list marker or the agent's `>` renders", MACHINE,
     r'(?:(?:[-+]|\d{1,9}[.)])\s+|>\s*)*)(#|>|',
     r')(#|>|'),
    ("an indented heading renders", MACHINE,
     r'_A_HEADING = re.compile(r"^([ \t]*(?:',
     r'_A_HEADING = re.compile(r"^((?:'),
    # ── review round 3 on be48a54: bare links, nested headings, the cut line's numbers ──────────
    ("a heading nested in the agent's list item renders", MACHINE,
     r'_A_HEADING = re.compile(r"^([ \t]*(?:',
     r'_A_HEADING = re.compile(r"^(\s{0,3}(?:'),
    ("a cut row under the agent's list item may underline it", MACHINE,
     r'_AN_UNDERLINE = re.compile(r"[ \t]*[=-]',
     r'_AN_UNDERLINE = re.compile(r"\s{0,3}[=-]'),
    ("a bare link is escaped like the rest, and goes somewhere else", MACHINE,
     "    pieces = _A_URL.split(text)\n",
     "    pieces = [text]\n"),
    ("a `#N` in a bare link is rewritten, and the link breaks", MACHINE,
     "    pieces = _A_URL.split(text)\n",
     "    pieces = _A_URL.split(without_mentions(text))\n"),
    ("a markdown link's destination is wrapped, and stops linking", MACHINE,
     r'_A_URL = re.compile(r"(?<!\]\()(?<![\w/])',
     r'_A_URL = re.compile(r"(?<![\w/])'),
    ("a bare link is left raw, and a name in it is read", MACHINE,
     '    text = "".join(f"`{piece}`" if k % 2 else',
     '    text = "".join(piece if k % 2 else'),
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
