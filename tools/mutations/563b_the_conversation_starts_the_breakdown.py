"""The conversation starts a requirement's breakdown on the worker, as every other door does, and is
told what it filed when it ends (#563, ADR-0051 D18, slice 18b), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/563b_the_conversation_starts_the_breakdown.py

The claims, each a row:

  1. one execution per requirement, whichever door: the conversation's start shares the panel's
     id, and one already running is said as running;
  2. the breakdown on the worker tells the conversation that started it what it filed, or that it
     failed, in that conversation's language, and tells nobody when no conversation started it; a
     failed breakdown still fails, and a telling that failed never costs the cards;
  3. each conversation door starts it with where it was asked, says so, says one already running
     as news, and says an engine that did not answer — the acceptance with the agreement first;
  4. what the conversation is told: an acceptance that filed nothing says the agreement holds.
"""

TEST = "tests/test_the_conversation_starts_the_breakdown.py"
BREAKING = "openfactory/product/breaking.py"
ENGINE = "openfactory/product/engine.py"
CONFIRM = "openfactory/product/confirm.py"
ACTIVITIES = "openfactory/runtime/temporal/activities.py"
WORKFLOW = "openfactory/runtime/temporal/workflow.py"

MUTATIONS = [
    # 1. one execution
    ("TODAY'S RUN: the conversation's breakdown is a second execution beside the panel's",
     BREAKING, "            id=breakdown_workflow_id(name, number), task_queue=TASK_QUEUE)",
     '            id=breakdown_workflow_id(name, number) + "-asked", task_queue=TASK_QUEUE)'),
    ("a breakdown already running is told as one this door started", BREAKING,
     "        return RUNNING\n", "        return STARTED\n"),

    # 2. the telling
    ("the conversation that started it is never told", ACTIVITIES,
     "    if not inp.conversation:\n        return\n    from openfactory.product.confirm",
     "    return\n    from openfactory.product.confirm"),
    ("a breakdown no conversation started is told to nobody's conversation", ACTIVITIES,
     "    if not inp.conversation:\n        return\n    from openfactory.product.confirm",
     "    if False:\n        return\n    from openfactory.product.confirm"),
    # RE-PINNED 2026-10-11 (review of #616): the workflow tells a breakdown that did not finish
    ("a breakdown that did not finish is not told", WORKFLOW,
     "            if inp.conversation:\n                with contextlib.suppress(ActivityError):",
     "            if False:\n                with contextlib.suppress(ActivityError):"),
    ("a breakdown no conversation started is told to nobody's conversation", WORKFLOW,
     "            if inp.conversation:\n                with contextlib.suppress(ActivityError):",
     "            if True:\n                with contextlib.suppress(ActivityError):"),
    ("a breakdown that did not finish is told and then reported as done", WORKFLOW,
     "                        retry_policy=RetryPolicy(maximum_attempts=3),\n"
     "                    )\n            raise\n",
     "                        retry_policy=RetryPolicy(maximum_attempts=3),\n"
     "                    )\n            return []\n"),
    ("the telling of an unfinished breakdown tells what it filed", ACTIVITIES,
     "    project = ProjectRegistry().get(inp.project)\n"
     "    await _tell_the_breakdown(project, inp, None)\n    return True\n",
     "    project = ProjectRegistry().get(inp.project)\n"
     "    await _tell_the_breakdown(project, inp, [])\n    return True\n"),
    ("a telling that failed costs the cards", ACTIVITIES,
     "    except Exception:  # noqa: BLE001 — the cards stand; only the telling failed, and says so",
     "    except ArithmeticError:  # noqa: BLE001"),
    ("the conversation's language is lost on the way to the worker", ACTIVITIES,
     "asked_for=inp.asked_for, language=inp.language or None)",
     "asked_for=inp.asked_for, language=None)"),
    ("the delivery loop is not told where the breakdown was asked", ACTIVITIES,
     "                                   conversation=inp.conversation, requester=inp.requester)",
     "                                   )"),

    # 3. the doors
    ("the gesture starts it without where it was asked", ENGINE,
     "                                     conversation=conversation, room=channel, requester=user,",
     '                                     conversation="", room="", requester="",'),
    ("a breakdown already running is said as started", ENGINE,
     "            sentence = breakdown_begun(number=number, running=how == breaking.RUNNING,",
     "            sentence = breakdown_begun(number=number, running=False,"),
    ("an engine that does not answer the gesture is a crash", ENGINE,
     "        except Exception:  # noqa: BLE001 — an engine that does not answer is a sentence",
     "        except ArithmeticError:  # noqa: BLE001"),
    ("the acceptance starts it without where it was asked", CONFIRM,
     '                                 conversation=conversation, room=str(entry.get("channel") or ""),',
     '                                 conversation="", room="",'),
    ("an acceptance whose breakdown could not start says nothing about it", CONFIRM,
     "        return (f\"{head}\\n\\n{said['no_breakdown']}{said['no_breakdown_now']}\"\n"
     "                f\"{said['agreement_holds']}\")",
     "        return head"),

    # 4. what the conversation is told
    ("an acceptance that filed nothing is told the breakdown sentence", CONFIRM,
     '    if results is not None and (asked_for or any(getattr(r, "ok", False) for r in results)):',
     "    if results is not None:"),
    ("the conversation is told in the project's language, not its own", CONFIRM,
     '    lang = language or getattr(project, "language", None)\n'
     "    if results is not None and any(",
     '    lang = getattr(project, "language", None)\n'
     "    if results is not None and any("),
]
