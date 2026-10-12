"""Closing, correcting and aligning a card are acts the role proposes, and a breakdown and a refine
wait for a yes like every other write (#565, slices b and c), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/565b_closing_correcting_and_aligning_are_acts_the_role_proposes.py

On a live run "pode fechar o final 9" matched no pattern and the role that understood it had no
act to hand it to; "ok, pode escrever o card e colocar no backlog" filed a free-standing card
beside the breakdown already running, because the breakdown was the one write that ran on a
matched sentence alone. The claims, each a row:

  1. the role's parser reads each card act — close with its survivor in either language and its
     reason, correct, retitle, align, refine — and the breakdown, each card as the board spells
     it;
  2. the engine stages each through the branch the pattern reached, with what its marker carries;
     the breakdown checks the requirement before it asks, and neither the breakdown nor the refine
     writes before the yes;
  3. the yes executes each, and the requester's own yes does not stand in for an admin's;
  4. one way in: no sentence reaches these acts again;
  5. what the patterns guarded is written into the markers' instructions: a negation does not
     close a card (#161's claim, which this plan carries — `161b` is superseded by it), and the
     breakdown's instruction says the platform asks after the reply;
  6. no question nobody can answer: off the admin list, where no admin's yes counts for the
     requester, a breakdown and a refine are refused at once; where the admins' yes counts, they
     are staged for them (review of #634).
"""

TEST = "tests/test_closing_correcting_and_aligning_are_acts_the_role_proposes.py"
SUPERSEDES = ("161b_the_negators_move_together.py",)
ROLE = "openfactory/product/role.py"
ENGINE = "openfactory/product/engine.py"
CONFIRM = "openfactory/product/confirm.py"
INTENTS = "openfactory/product/intents.py"
PINNED = "tests/test_the_conversation_is_pinned.py"
DOORS = "tests/test_the_conversation_starts_the_breakdown.py"
FRAME = "tests/test_the_frame_and_the_prose_agree_on_the_next_step.py"
TAUGHT = "tests/test_product_intents.py"

MUTATIONS = [
    # ── 1. the role's parser ────────────────────────────────────────────────────────────────────
    ("a close is never read from the role's reply", ROLE,
     '    (CLOSE_MARKER, _CLOSE_RE, "close", "close"),\n', ""),
    ("an alignment is never read from the role's reply", ROLE,
     '    (ALIGN_MARKER, _ALIGN_RE, "align", "align"),\n', ""),
    ("a refine is never read from the role's reply", ROLE,
     '    (REFINE_MARKER, _REFINE_RE, "refine", "refine"),\n', ""),
    ("a breakdown is never read from the role's reply", ROLE,
     '    (BREAKDOWN_MARKER, _BREAKDOWN_RE, "breakdown", "breakdown"),\n', ""),
    ("a card is read by its digits, as a requirement is", ROLE,
     "_CARD = REF_AS_WRITTEN", '_CARD = r"#?\\d{1,12}"'),
    ("the survivor is named in Portuguese only", ROLE,
     "|in\\s+favou?r\\s+of)", ")", TAUGHT),

    # ── 2. staged through the branch the pattern reached ───────────────────────────────────────
    ("a close stages no survivor", ENGINE,
     '        in_favour_of = canonical_ref(captures.get("in_favour_of")) or None',
     "        in_favour_of = None"),
    ("a close stages no reason", ENGINE,
     '        in_favour_of = canonical_ref(captures.get("in_favour_of")) or None\n'
     '        reason = (captures.get("reason") or "").strip()[:300]',
     '        in_favour_of = canonical_ref(captures.get("in_favour_of")) or None\n'
     '        reason = ""'),
    ("a new title alone stages nothing", ENGINE,
     '        new_title = (captures.get("title") or "").strip()[:200]', '        new_title = ""'),
    ("a breakdown of a requirement not agreed is staged anyway", ENGINE,
     "        if not req.is_promise:\n"
     "            from openfactory.product.module import _not_a_promise",
     "        if False:\n"
     "            from openfactory.product.module import _not_a_promise"),
    ("a breakdown of a requirement the base does not have breaks the turn", ENGINE,
     "        if instead:\n            return preamble + instead\n"
     "        if not req.is_promise:\n"
     "            from openfactory.product.module import _not_a_promise",
     "        if not req.is_promise:\n"
     "            from openfactory.product.module import _not_a_promise"),
    ("a breakdown starts on the proposal, before the yes", ENGINE,
     "        ask = breakdown_confirmation(number=number, title=req.title or req.slug, "
     "language=lang)\n",
     "        from openfactory.product.confirm import _confirm_breakdown\n"
     "        return _confirm_breakdown(project, {\"number\": number, \"channel\": channel},\n"
     "                                  module=module, user=user, lang=lang)\n"),
    ("a refine writes on the proposal, before the yes", ENGINE,
     "        ask = refine_confirmation(number=number, language=lang)\n",
     "        from openfactory.product.confirm import _confirm_refine\n"
     "        return _confirm_refine(project, {\"number\": number}, module=module, user=user,\n"
     "                               lang=lang)\n"),

    # ── 3. the yes executes each ────────────────────────────────────────────────────────────────
    ("the breakdown's yes executes nothing it was asked for", CONFIRM,
     '    "breakdown": _confirm_breakdown,\n', ""),
    ("the refine's yes executes nothing it was asked for", CONFIRM,
     '    "refine": _confirm_refine,\n', ""),
    ("the requester's own yes starts their breakdown", CONFIRM,
     '_THE_REQUESTERS_OWN = frozenset({"adjust", "accept_change"})\n',
     '_THE_REQUESTERS_OWN = frozenset({"adjust", "accept_change", "breakdown"})\n', PINNED),
    ("the breakdown starts without where it was asked", CONFIRM,
     '                                 conversation=str(entry.get("conversation") or ""),\n',
     '                                 conversation="",\n', DOORS),

    # ── 4. one way in ───────────────────────────────────────────────────────────────────────────
    ("a sentence closes a card again", INTENTS,
     "_INTENTS: tuple[tuple[str, re.Pattern[str]], ...] = _PATTERNS",
     '_PATTERNS = _PATTERNS + (("close", re.compile(r"^\\s*fecha\\s+o\\s+#(?P<number>\\d+)", '
     're.I)),)\n\n_INTENTS: tuple[tuple[str, re.Pattern[str]], ...] = _PATTERNS'),
    ("a sentence breaks a requirement down again", INTENTS,
     "_INTENTS: tuple[tuple[str, re.Pattern[str]], ...] = _PATTERNS",
     '_PATTERNS = _PATTERNS + (("breakdown", re.compile(r"^\\s*quebra\\s+o\\s+requisito\\s+'
     '(?P<number>\\d+)", re.I)),)\n\n_INTENTS: tuple[tuple[str, re.Pattern[str]], ...] = _PATTERNS'),

    # ── 5. what the patterns guarded, in the instructions ──────────────────────────────────────
    ("a card the person said NOT to close may be proposed for closing", ROLE,
     '"[[DESCARTE: …]]), for a question about a card, nor for one they say NOT to close "',
     '"[[DESCARTE: …]]), nor for a question about a card. "'),
    ("the breakdown's instruction stops saying the platform asks after the reply", ROLE,
     'f"its own line. {STAGED_AFTER_YOUR_REPLY} It files the requirement\'s cards where new "',
     'f"its own line. It files the requirement\'s cards where new "', FRAME),
    # 6. no question nobody can answer (review of #634)
    # RE-PINNED 2026-10-12 (#667): one guard for every act, read off `role.ACTS`, at the top of
    # `_run_intent`; the breakdown and the refine are cut out of the acts it reads
    ("REVIEW OF #634: a breakdown nobody can say yes to waits for that yes", ENGINE,
     "    return frozenset(GESTURE_INTENT.values())\n",
     "    return frozenset(GESTURE_INTENT.values()) - {\"breakdown\"}\n"),
    ("a refine nobody can say yes to waits for that yes", ENGINE,
     "    return frozenset(GESTURE_INTENT.values())\n",
     "    return frozenset(GESTURE_INTENT.values()) - {\"refine\"}\n"),
    ("a breakdown the admins could confirm is refused at once", ENGINE,
     "            and not _admin_mentions(project)):\n        return said(unauthorized_message(",
     "            ):\n        return said(unauthorized_message("),
]
