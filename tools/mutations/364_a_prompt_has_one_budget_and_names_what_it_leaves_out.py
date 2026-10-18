"""A job's prompt has one budget, filled project-first, and names every document it leaves out (#364).

Nothing decided how large a job's prompt could be. Measured on this repository at d29b94a, a blank
card's brief carried 477,369 bytes: 398,127 of them were decision records, and 35 of the 56
records had already been cut at 8,000 characters with nothing in the prompt saying so. ADR-0056
bounds the whole declared section with one budget (`OPENFACTORY_PROMPT_BUDGET`, default 160,000
bytes). The project's own guidelines are filled first, then the records newest first, and every
document left out or cut is named by path inside the prompt.

The cuts fall into five groups:

  * THE FIT: bytes, drop-and-continue and the exact boundary (the three cuts that survived #359's
    review), the priority order, newest first, the per-role cap again, and a pinned document made
    droppable;
  * WHAT IS COUNTED: the plan, the failure log, the knowledge map, the card and the index, each
    left out of the measure in turn;
  * THE NOTICE: not rendered, naming a document by its first line, a cut left unsaid, and the
    kept documents rendered in the order they were added;
  * THE SETTING: the variable ignored, a malformed value read as the default, the default moved
    away from what the documents state, and the job and the doctor no longer refusing a malformed
    value, and onboarding's first round blaming the harness for it;
  * THE SURFACES: `explain` saying "inlined in full" again, `doctor` and `box prove` dropping the
    budget from their line, and the job runner, `box prove`'s fit, `explain` and `doctor` not
    asking the box the job builds where the operator tier opens, and the helpers they share
    mounting a directory that is not there or raising on a box this machine cannot build.
"""

TEST = "tests/test_a_jobs_prompt_is_held_to_one_budget.py"
BASE = "openfactory/adapters/agent/base.py"
CONTEXT = "openfactory/orchestrator/context.py"
EXPLAIN = "openfactory/orchestrator/explain.py"
DOCTOR = "openfactory/doctor.py"
BOX_PROVE = "openfactory/box_prove.py"
MACHINE = "openfactory/orchestrator/machine.py"
OPERATOR = "openfactory/orchestrator/operator_guidelines.py"

SETTING = "tests/test_the_operator_sets_the_prompt_budget.py"
PRIORITY = "tests/test_the_projects_own_rules_are_the_last_left_out.py"
NAMED = "tests/test_a_document_left_out_is_named_in_the_prompt.py"
REPORTED = "tests/test_the_inlined_document_bytes_are_reported.py"

_MEASURE = "        brief = _render(context, inlined, named, failures=failures, this_pass=this_pass,\n"

MUTATIONS = [
    # ── the fit ───────────────────────────────────────────────────────────────────────────────────
    ("the fit counts characters, not bytes — #359's survivor: two records of 3,000 `é` both fit",
     BASE,
     '    return len(text.encode("utf-8"))\n',
     "    return len(text)\n"),

    ("the first document that does not fit stops the fill — #359's survivor: the small guideline "
     "after the large one is never tried",
     BASE,
     "                kept.discard(i)\n                continue\n",
     "                kept.discard(i)\n                break\n"),

    ("a document that lands exactly on the budget is left out — #359's survivor",
     BASE,
     "            if trial > budget:\n",
     "            if trial >= budget:\n"),

    ("the fill runs in the cascade's order instead of the priority: the operator tier is filled "
     "before the project's own guidelines, which #359 measured being left out",
     BASE,
     "    return sorted(droppable, key=lambda i: (_fill_rank(documents[i].source), -i))\n",
     "    return droppable\n",
     PRIORITY),

    ("within one source the fill runs in glob order: ADR-0007 is kept and ADR-0010, which amends "
     "it, is left out",
     BASE,
     "    return sorted(droppable, key=lambda i: (_fill_rank(documents[i].source), -i))\n",
     "    return sorted(droppable, key=lambda i: (_fill_rank(documents[i].source), i))\n",
     PRIORITY),

    ("a running total per source — the per-role cap again: each role may reach the budget alone",
     BASE,
     "            trial = measure()\n",
     "            trial = _size(''.join(documents[j].text for j in kept\n"
     "                                  if documents[j].source == documents[i].source))\n"),

    ("a pinned document starts out droppable and is never tried: the framework baseline, which no "
     "path in the box reaches, is left out",
     BASE,
     "        kept = {i for i, d in enumerate(documents) if d.pinned}\n",
     "        kept = set()\n"),

    # ── what is counted ───────────────────────────────────────────────────────────────────────────
    ("the plan is not counted: the planner's plan arrives after `build_context` and takes no room",
     BASE,
     "        return _size(brief) + _size(context.plan)\n",
     "        return _size(brief)\n"),

    ("a repair's failure log is not counted",
     BASE, _MEASURE,
     '        brief = _render(context, inlined, named, failures="", this_pass=this_pass,\n'),

    ("the knowledge map is not counted",
     BASE, _MEASURE,
     '        brief = _render(context.model_copy(update={"knowledge_map": ""}), inlined, named, '
     'failures=failures, this_pass=this_pass,\n'),

    ("the card is not counted",
     BASE, _MEASURE,
     '        brief = _render(context.model_copy(update={"ticket": context.ticket.model_copy('
     'update={"objective": ""})}), inlined, named, failures=failures, this_pass=this_pass,\n'),

    ("the reference index is not counted",
     BASE, _MEASURE,
     '        brief = _render(context.model_copy(update={"doc_index": ""}), inlined, named, '
     'failures=failures, this_pass=this_pass,\n'),

    # ── the notice ────────────────────────────────────────────────────────────────────────────────
    ("the notice is not rendered: a document left out is a document the agent never hears of",
     BASE,
     "    declared += _notice(kept, left_out, context.prompt_budget)\n",
     "",
     NAMED),

    ("a left-out document is named by its first line, not by the path the agent can open",
     BASE,
     '        lines.append(f"- `{_one_line(d.open_at, 400)}` — left out',
     '        lines.append(f"- `{_one_line(d.text.splitlines()[0], 400)}` — left out',
     NAMED),

    ("a cut is not recorded: the document's length on disk is its inlined length, so an "
     "8,000-character slice reads as the whole record again",
     CONTEXT,
     "                           text=full[:_MAX_DOC_CHARS], chars_on_disk=len(full))\n",
     "                           text=full[:_MAX_DOC_CHARS], chars_on_disk=len(full[:_MAX_DOC_CHARS]))\n",
     NAMED),

    ("the kept guidelines are rendered in the order the budget added them, so the project no "
     "longer has the last word",
     BASE,
     "    guidelines = [d.text for d in kept if d.source != CONSTRAINTS] + list(context.guidelines)\n",
     "    guidelines = [d.text for d in sorted(kept, key=lambda d: _fill_rank(d.source))\n"
     "                  if d.source != CONSTRAINTS] + list(context.guidelines)\n",
     PRIORITY),

    # ── the setting ───────────────────────────────────────────────────────────────────────────────
    ("the variable is ignored: every deployment runs on the default",
     CONTEXT,
     '    raw = ((env if env is not None else os.environ).get(ENV_VAR_PROMPT_BUDGET) or "").strip()\n',
     '    raw = ""\n',
     SETTING),

    ("a malformed value is read as the default, in silence",
     CONTEXT,
     "    raise PromptBudgetError(\n",
     "    return DEFAULT_PROMPT_BUDGET\n    raise PromptBudgetError(\n",
     SETTING),

    ("the default moves away from the one the decision record, the reference and the guide state",
     CONTEXT,
     "DEFAULT_PROMPT_BUDGET = 160_000\n",
     "DEFAULT_PROMPT_BUDGET = 120_000\n",
     SETTING),

    ("the job runs its passes under a value nobody can read instead of holding",
     MACHINE,
     "        except PromptBudgetError as exc:\n"
     "            self._emit(ticket, \"note\", f\"⚠️ prompt budget: {exc}\")\n"
     "            return self._hold(ticket, owner, str(exc), JobState.ON_HOLD)\n",
     "        except PromptBudgetError:\n            pass\n",
     SETTING),

    ("doctor's documents line stays ok over a value nobody can read",
     DOCTOR,
     "    try:\n        prompt_budget()\n    except PromptBudgetError as exc:\n"
     "        return Finding(\"documents\", False, str(exc),\n",
     "    try:\n        prompt_budget()\n    except PromptBudgetError as exc:\n"
     "        return Finding(\"documents\", True, str(exc),\n",
     SETTING),

    ("onboarding's first round blames the harness for a budget nobody can read",
     "openfactory/onboarding/firstrun.py",
     "        except PromptBudgetError as exc:\n",
     "        except ZeroDivisionError as exc:\n",
     "tests/test_onboarding_firstrun.py"),

    # ── the surfaces ──────────────────────────────────────────────────────────────────────────────
    ("explain prints the trace's own fate over a cut or a left-out record — 'inlined in full'",
     EXPLAIN,
     "            fate = _budget_fate(next(inlined), fit, language) or fate\n",
     "            next(inlined)\n",
     NAMED),

    ("doctor's line drops what the budget makes of a blank card",
     DOCTOR,
     "    return Finding(\"documents\", True, inlined_document_summary(per_role, fit), note=note)\n",
     "    return Finding(\"documents\", True, inlined_document_summary(per_role), note=note)\n",
     REPORTED),

    ("box prove's line drops what the budget makes of a blank card",
     BOX_PROVE,
     "        message = inlined_document_summary(per_role, fit)\n",
     "        message = inlined_document_summary(per_role)\n",
     REPORTED),

    ("the job runner does not ask its box where the operator tier opens: those documents are "
     "pinned, and the project's own guidelines are left out in the six-document case",
     MACHINE,
     "                            operator_root=self._operator_guidelines_root(),\n",
     "",
     PRIORITY),

    # ── review of 3cd65e4: the surfaces ask the job's box, the whole project tier is first, and
    # the details the first plan left unheld ─────────────────────────────────────────────────────
    ("explain pins the operator tier: with the job leaving operator standards out, explain names "
     "the project's own guideline as left out",
     EXPLAIN,
     "                                        operator_root=deployment_root(default_sandbox()))",
     "                                        operator_root=None)",
     PRIORITY),

    ("doctor builds a bare box, which on the container box answers no mount and pins the tier",
     OPERATOR,
     "        box = build_sandbox(kind, **box_knobs())\n",
     "        box = build_sandbox(kind)\n",
     PRIORITY),

    ("doctor does not ask the box at all",
     DOCTOR,
     "    return deployment_root(kind)\n",
     "    return None\n",
     PRIORITY),

    ("box prove builds its proof box without the operator directory the job's box mounts",
     BOX_PROVE,
     "    knobs.update(operator_guidelines.box_knobs())\n",
     "",
     PRIORITY),

    ("the job's own box is built without the operator directory",
     "openfactory/factory.py",
     "    knobs.update(operator_guidelines.box_knobs())\n",
     "",
     PRIORITY),

    ("a component's guidelines are filled after the operator tier: the #359 inversion for the "
     "other half of the project tier",
     BASE,
     '    if source == "docs.guidelines" or source.startswith("components."):\n',
     '    if source == "docs.guidelines":\n',
     PRIORITY),

    ("a profile's additions are filled before the operator tier",
     BASE,
     '    return {CONSTRAINTS: 1, "operator": 2, "profile": 3}.get(source, 4)\n',
     '    return {CONSTRAINTS: 1, "operator": 3, "profile": 2}.get(source, 4)\n',
     PRIORITY),

    ("a digit that is not ASCII reaches `int()`: `²` raises a bare ValueError, not the sentence",
     CONTEXT,
     "    if raw.isascii() and raw.isdigit() and int(raw) > 0:\n",
     "    if raw.isdigit() and int(raw) > 0:\n",
     SETTING),

    ("a framework document a profile replaces becomes droppable, as if it were the project's",
     CONTEXT,
     "                at = None if layer == FRAMEWORK else substitute\n",
     "                at = substitute\n"),

    ("the one log line per brief that leaves documents out is gone",
     BASE,
     "    if fit.left_out:\n",
     "    if False:\n"),

    ("a cut line no longer says where the rest is: an operator document, named by a bare "
     "filename, opens nowhere",
     BASE,
     '        rest = f"; the rest is at `{_one_line(d.open_at, 400)}`" if d.open_at else ""\n',
     '        rest = ""\n',
     NAMED),

    ("explain names a left-out document by the name its tier gives it, not where it opens",
     EXPLAIN,
     '                    path=f"`{doc.open_at}`")',
     '                    path=f"`{doc.path}`")',
     PRIORITY),

    ("box prove's fit never asks its box where the operator directory opens: the tier is pinned",
     BOX_PROVE,
     "                                 operator_root=guidelines_root(box, gather()))",
     "                                 operator_root=None)",
     PRIORITY),

    ("a configured directory that is not on disk is handed to the box as its knob",
     OPERATOR,
     '    return {"guidelines": str(directory)} if directory is not None and directory.is_dir() else {}\n',
     '    return {"guidelines": str(directory)} if directory is not None else {}\n',
     PRIORITY),

    ("a box this machine cannot build raises out of `deployment_root` instead of pinning the tier",
     OPERATOR,
     '        _log.debug("could not build the %r box to ask where it opens %s (%s)", kind, tier.dir, exc)\n'
     "        return None\n",
     '        _log.debug("could not build the %r box to ask where it opens %s (%s)", kind, tier.dir, exc)\n'
     "        raise\n",
     PRIORITY),

    ("explain asks the worktree box, not the deployment's default box, where the operator tier opens",
     EXPLAIN,
     "operator_root=deployment_root(default_sandbox()))",
     'operator_root=deployment_root("worktree"))',
     PRIORITY),
]
