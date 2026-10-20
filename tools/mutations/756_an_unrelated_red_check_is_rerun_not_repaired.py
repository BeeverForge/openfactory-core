"""#756, proven by breaking it — a red check the change does not touch is re-run, not repaired.

A blocking check that failed for a reason no changed file touches (a flaky integration test, a
busy shared environment) was handed to a paid agent pass that had nothing to change; the next
attempt failed the same way, and `_CI_REPAIR_MAX` parked the card after two agent passes spent on
a re-run's worth of trouble.

SIX CLAIMS:

  1. **The first attempt re-runs instead of paying an agent** when the failing log the #184 gate
     decided from names no file the pull request changes (full path, or basename with its
     extension; never the stem, never a suffix of another name; a colour code is not a word),
     on either door, and says so on the pull request AFTER the forge answered, naming what it
     re-ran (A, lesson §9). The
     changed files are read off git's own `diff -M`: both sides of a rename, quoted UTF-8 names,
     names with spaces, and never a list a header's missing rename lines left short.
  2. **"Could not see" is never "unrelated"**: a diff that could not be read, or one that was cut,
     launches the agent; so does any later attempt on the head (PO answer Q1: once per head), and
     a forge without the capability is not even asked for its diff (lesson §2). A diff read
     that raises is caught and launches the agent; `[]` from the forge is not a re-run.
  3. **#184 still decides first** (F): an empty log is held for a person before the rule is
     weighed, and the agent is handed the log the decision was made from, read once — also after
     a refused re-run, which falls through to the agent and is said (Q3). No clock of its own (E).
  4. **A pass that changed nothing re-runs once** (B), and only that: not a pass that pushed, not
     one whose change could not be measured, not a hold, not a person's adjust; said on the pull
     request (Q4).
  5. **The seam is a row capability that cannot be faked** (D): a test double's answer is not a
     list of names, and a refusal is a value carrying the forge's words, never `[]`.
  6. **The GitHub row re-runs exactly the runs the log was read from**: blocking `code` rows of
     the pull request's own repository; one run refused of two, and checks it could not read,
     are refusals, never a success or `[]`; and generic code never reaches a forge CLI. Both
     moves are reached from the registered `repair_ci` activity, and a forge that cannot be
     built after a pass returns the pass.

The guards are `tests/test_a_red_check_the_diff_does_not_touch_is_rerun_before_an_agent_is_paid.py`
(A, C, E, F), `tests/test_a_repair_pass_that_changed_nothing_reruns_the_failed_jobs_once.py` (B)
and `tests/test_rerunning_failed_jobs_is_a_capability_a_forge_declares.py` (D, reachability).
"""

TEST = "tests/test_a_red_check_the_diff_does_not_touch_is_rerun_before_an_agent_is_paid.py"
AFTER_A_PASS = "tests/test_a_repair_pass_that_changed_nothing_reruns_the_failed_jobs_once.py"
CAPABILITY = "tests/test_rerunning_failed_jobs_is_a_capability_a_forge_declares.py"

ACTIVITIES = "openfactory/runtime/temporal/activities.py"
REPAIRABLE = "openfactory/runtime/repairable.py"
BASE = "openfactory/adapters/forge/base.py"
GITHUB = "openfactory/adapters/forge/github.py"

MUTATIONS = [
    # ── claim 1: the first attempt re-runs, and says what the forge re-ran ────────────────────
    ("THE DEFECT ITSELF: the pre-launch re-run is never taken, and the agent is paid as before",
     ACTIVITIES,
     '    if not callable(getattr(forge, "rerun_failed", None)) or inp.attempt != 1:\n',
     "    if True:\n"),

    ("every log reads as unrelated: a failure in a changed file is re-run, not repaired",
     REPAIRABLE,
     "                return True\n    return False\n",
     "                return False\n    return False\n"),

    ("the stem is matched instead of the basename: `invoice` in prose reads as `invoice.py`",
     REPAIRABLE,
     "        for name in {path, posixpath.basename(path)} - {\"\"}:\n",
     "        for name in {path, posixpath.splitext(posixpath.basename(path))[0]} - {\"\"}:\n"),

    # Review round 1, measured on jest's run 39405383814 (gh 2.102.0): the `m` closing a colour
    # code stood left of the name jest coloured, and its own failure read as unrelated.
    ("colour codes are read as words: a changed file a tool colours is read as not named",
     REPAIRABLE,
     '    text = _COLOUR.sub("", log).replace("\\\\", "/")\n',
     '    text = log.replace("\\\\", "/")\n'),

    # The changed files, read off git's own `diff --cached -M` (review round 1: these four
    # survived the first 59 rows; `test_changed_paths_reads_what_git_itself_writes` holds them).
    ("the `rename`/`copy` lines are ignored: a rename's sides that the header cannot split are lost",
     REPAIRABLE,
     "        elif line.startswith(_NAMING):\n",
     "        elif line.startswith((\"\\0never\",)):\n"),

    ("git's octal escapes are decoded per character, not as the bytes of a UTF-8 name",
     REPAIRABLE,
     "            out.append(int(text[i + 1:i + 4], 8) & 0xFF)\n",
     "            out += chr(int(text[i + 1:i + 4], 8)).encode()\n"),

    ("a quoted header is not parsed: a diff that changes a non-ASCII name reads as unseen",
     REPAIRABLE,
     "    if rest.startswith('\"'):\n        got = _unquote(rest)\n        if got is None:\n"
     "            return None\n",
     "    if rest.startswith('\"'):\n        return None\n"),

    ("a same-name header with spaces is read as ambiguous, owing rename lines it never gets",
     REPAIRABLE,
     "        same = [c for c in cuts if rest[2:c] == rest[c + 3:]]\n",
     "        same = []\n"),

    ("a header owed its rename lines is let past the next header, whose pair settles the debt",
     REPAIRABLE,
     "            if owed:\n                return None\n            headers += 1\n",
     "            headers += 1\n"),

    ("the pull request is never told which jobs were re-run", ACTIVITIES,
     '    _say_on_the_pull_request(forge, inp.pr_url, (\n'
     '        f"Re-ran the failed jobs of {names}: no file this pull request changes appears in'
     ' their "\n'
     '        "failing log, so no agent was launched for it. The checks are read again once they "\n'
     '        "finish."))\n',
     ""),

    ("the comment is posted BEFORE the re-run, naming the red checks it predicts", ACTIVITIES,
     "    reran = rerun_failed_of(forge, inp.pr_url)\n"
     "    if isinstance(reran, RerunRefused):\n"
     '        activity.logger.warning("not every failed job of %s could be re-run, so an agent'
     ' repairs "\n',
     '    _say_on_the_pull_request(forge, inp.pr_url, "Re-ran the failed jobs of " + ", ".join(\n'
     "        f\"`{c['name']}`\" for c in forge.pr_checks(pr=inp.pr_url)) + \": no file this pull"
     ' request "\n'
     '        "changes appears in their failing log.")\n'
     "    reran = rerun_failed_of(forge, inp.pr_url)\n"
     "    if isinstance(reran, RerunRefused):\n"
     '        activity.logger.warning("not every failed job of %s could be re-run, so an agent'
     ' repairs "\n'),

    # ── claim 2: "could not see" is never "unrelated" ─────────────────────────────────────────
    ("a diff that could not be read answers `[]`, a change of nothing, so the log reads unrelated",
     REPAIRABLE,
     "    if diff is None or DIFF_CUT_MARKER in diff:\n        return None\n",
     "    if diff is None:\n        return []\n    if DIFF_CUT_MARKER in diff:\n        return None\n"),

    ("a cut diff is read as the whole change: the files past the cut are not in it", REPAIRABLE,
     "    if diff is None or DIFF_CUT_MARKER in diff:\n        return None\n",
     "    if diff is None:\n        return None\n"),

    ("a diff read that raises is not caught: it escapes the repair activity", ACTIVITIES,
     "    except Exception as exc:  # noqa: BLE001 — an unread diff is \"could not see\": the agent"
     " runs\n",
     "    except ZeroDivisionError as exc:  # noqa: BLE001\n"),

    ("the once-per-head bound is removed: every attempt re-runs, and a real regression in another "
     "file never reaches an agent", ACTIVITIES,
     '    if not callable(getattr(forge, "rerun_failed", None)) or inp.attempt != 1:\n',
     '    if not callable(getattr(forge, "rerun_failed", None)):\n'),

    ("the diff is read before the capability is asked: a forge that cannot re-run pays for it",
     ACTIVITIES,
     '    if not callable(getattr(forge, "rerun_failed", None)) or inp.attempt != 1:\n'
     "        return None\n"
     "    try:\n"
     "        diff = forge.pr_diff(pr=inp.pr_url, repo=repo)\n",
     "    early = forge.pr_diff(pr=inp.pr_url, repo=repo)\n"
     '    if not callable(getattr(forge, "rerun_failed", None)) or inp.attempt != 1:\n'
     "        return None\n"
     "    try:\n"
     "        diff = early\n",
     CAPABILITY),

    # ── claim 3: #184 decides first; the agent gets the log the decision was made from ────────
    # The rule asked before the gate's hold, on no evidence: an empty log names no changed file.
    ("the rule is asked before the #184 gate: an empty log reads as unrelated and is re-run",
     ACTIVITIES,
     "        if held is not None:\n"
     "            return held\n"
     "        # A THIRD MOVE, BETWEEN THE HOLD AND THE AGENT (#756)",
     "        early = _rerun_what_the_change_does_not_touch(project, inp, repo, \"\")\n"
     "        if early is not None:\n"
     "            return early\n"
     "        if held is not None:\n"
     "            return held\n"
     "        # A THIRD MOVE, BETWEEN THE HOLD AND THE AGENT (#756)"),

    ("`[]` (nothing re-runnable) is taken as a re-run: no agent, and a comment naming nothing",
     ACTIVITIES,
     "    if not reran:\n        activity.logger.warning(\"the forge found no failed job of %s to"
     " re-run, so an agent \"\n",
     "    if False:\n        activity.logger.warning(\"the forge found no failed job of %s to"
     " re-run, so an agent \"\n"),

    # Review round 1: a refusal can be partial, and "were not re-run" was false for what re-ran.
    ("a partial refusal before launch is told as if no failed job was re-run", ACTIVITIES,
     '            f"Not every failed job could be re-run: {str(reran)[:300]}. No file this pull'
     ' request "\n',
     '            f"The failed jobs were not re-run: {str(reran)[:300]}. No file this pull'
     ' request "\n'),

    ("the agent is handed a second read of the log, not the one the decision was made from",
     ACTIVITIES,
     "            ci_log = evidence\n",
     "            ci_log = str(_forge_for(project).failed_ci_logs(pr=inp.pr_url) or evidence)\n"),

    ("the re-run waits on a clock of its own before it returns", ACTIVITIES,
     "    # `code_changed=False`: nothing was pushed, so the reviewer's verdict on the head still"
     " stands\n",
     # One second, not sixty: the guard patches both sleeps to raise, so any length is red, and
     # sixty made the engine row of this file wait eight minutes of wall clock (measured).
     "    time.sleep(1)\n"
     "    # `code_changed=False`: nothing was pushed, so the reviewer's verdict on the head still"
     " stands\n"),

    # ── claim 4: only a pass that changed nothing re-runs ─────────────────────────────────────
    ("a pass whose change could not be measured (`None`) is read as one that changed nothing",
     ACTIVITIES,
     "    if human or result.state is not JobState.PR_OPEN or result.code_changed is not False:\n",
     "    if human or result.state is not JobState.PR_OPEN or result.code_changed is True:\n",
     AFTER_A_PASS),

    ("a person's adjust pass re-runs CI as if it had repaired a red build", ACTIVITIES,
     "    if human or result.state is not JobState.PR_OPEN or result.code_changed is not False:\n",
     "    if result.state is not JobState.PR_OPEN or result.code_changed is not False:\n",
     AFTER_A_PASS),

    ("a held, paused or failed pass re-runs the failed jobs", ACTIVITIES,
     "    if human or result.state is not JobState.PR_OPEN or result.code_changed is not False:\n",
     "    if human or result.code_changed is not False:\n",
     AFTER_A_PASS),

    ("a forge that cannot be built after a pass raises out of the activity, losing the pass",
     ACTIVITIES,
     "        forge = forge_of()\n    except Exception as exc:  # noqa: BLE001 — the pass is done",
     "        forge = forge_of()\n    except ZeroDivisionError as exc:  # noqa: BLE001 — the pass"
     " is done",
     AFTER_A_PASS),

    ("a partial refusal after a pass is told as if no failed job was re-run", ACTIVITIES,
     '            f"Not every failed job could be re-run after a repair pass that changed'
     ' nothing: "\n',
     '            f"The failed jobs were not re-run after a repair pass that changed nothing: "\n',
     AFTER_A_PASS),

    ("the pull request is never told the jobs were re-run after a pass that changed nothing",
     ACTIVITIES,
     '        _say_on_the_pull_request(forge, inp.pr_url, (\n'
     '            f"Re-ran the failed jobs of {names}: a repair pass changed nothing in this pull "\n'
     '            "request, so its checks are run once more. They are read again once they'
     ' finish."))\n',
     "",
     AFTER_A_PASS),

    # ── claim 5: the seam cannot be faked, and a refusal is a value ───────────────────────────
    ("any answer is taken for the names of re-run checks: a test double claims a re-run", BASE,
     "    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):\n",
     "    if False:\n",
     CAPABILITY),

    ("a refusal the row names is swallowed into `[]`, \"nothing to re-run\"", BASE,
     "    except RerunRefused as said:\n"
     '        log.info("%s refused to re-run the failed jobs of %s: %s", type(forge).__name__, pr,\n'
     "                 str(said)[:300])\n        return said\n",
     "    except RerunRefused as said:\n"
     '        log.info("%s refused to re-run the failed jobs of %s: %s", type(forge).__name__, pr,\n'
     "                 str(said)[:300])\n        return []\n",
     CAPABILITY),

    ("any other exception is swallowed into `[]`: the refusal is never said", BASE,
     '        return RerunRefused(f"{display_name(forge)} could not re-run the failed jobs "\n'
     '                            f"({str(exc)[:300]})")\n',
     "        return []\n",
     CAPABILITY),

    # ── claim 6: the GitHub row, the vendor boundary, the reachability ────────────────────────
    ("GitHub: a red required check that is not about the code has its run re-run", GITHUB,
     '            if not (row["blocking"] and row["kind"] == "code"\n',
     '            if not (row["blocking"]\n',
     CAPABILITY),

    ("GitHub: a run of another repository is re-run (C-18)", GITHUB,
     "            if named and named.group(1).lower() == repo.lower():\n",
     "            if named:\n",
     CAPABILITY),

    ("GitHub: a partial refusal is answered as a success, and the refused run is never said",
     GITHUB,
     "        if refusals:\n            done",
     "        if refusals and not rerun:\n            done",
     CAPABILITY),

    ("GitHub: checks it could not read answer `[]`, \"nothing to re-run\", not a refusal", GITHUB,
     "            raise RerunRefused(f\"the checks of this pull request could not be read \"\n"
     "                               f\"({str(exc)[:160]})\") from exc\n",
     "            return []\n",
     CAPABILITY),

    ("generic code calls the forge's CLI directly in the re-run helper", ACTIVITIES,
     "    paths = changed_paths(diff if isinstance(diff, str) else None)\n",
     '    forge._gh(["run", "rerun", "1", "--failed"])\n'
     "    paths = changed_paths(diff if isinstance(diff, str) else None)\n",
     CAPABILITY),

    ("the repair activity never reaches the pre-launch move", ACTIVITIES,
     "        rerun = _rerun_what_the_change_does_not_touch(project, inp, repo, evidence)\n",
     "        rerun = None\n",
     CAPABILITY),

    # `reran = rerun_failed_of(forge, inp.pr_url)` is in both moves; the next line is the post-pass one.
    ("the post-pass move never asks the forge to re-run anything", ACTIVITIES,
     "    reran = rerun_failed_of(forge, inp.pr_url)\n    if reran is None:\n",
     "    reran = []\n    if reran is None:\n",
     CAPABILITY),
]
