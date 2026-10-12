"""No route of the panel, and no action, answers 500 because the engine did not answer (#674,
journey 0), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/674_no_route_answers_500_when_the_engine_does_not_answer.py

The claims, each a row:
  1. one handler answers the engine's silence for every route: a 503, with the read's own
     sentence, and one line in the log without a traceback;
  2. the action layer answers it UNAVAILABLE, not FAILED;
  3. the exception the reads raise is the one the panel and the actions catch.
"""

TEST = "tests/test_no_route_answers_500_when_the_engine_does_not_answer.py"
APP = "openfactory/api/app.py"
ACTIONS = "openfactory/actions/__init__.py"
VIEW = "openfactory/runtime/temporal/view.py"

MUTATIONS = [
    # 1. the handler
    ("TODAY'S RUN: no handler, so the bounded read escapes the route as a 500", APP,
     "@app.exception_handler(EngineUnreachable)\nasync def _the_engine_did_not_answer",
     "async def _the_engine_did_not_answer"),
    ("the engine's silence is answered with a 500", APP,
     '    return JSONResponse({"detail": f"durable engine unreachable: {str(exc)[:150]}"},\n'
     "                        status_code=503)",
     '    return JSONResponse({"detail": f"durable engine unreachable: {str(exc)[:150]}"},\n'
     "                        status_code=500)"),
    ("the 503 loses the read's own sentence", APP,
     '{"detail": f"durable engine unreachable: {str(exc)[:150]}"}',
     '{"detail": "durable engine unreachable"}'),
    ("the log carries the route's traceback", APP,
     '    log.warning("%s %s: durable engine unreachable: %s", request.method, request.url.path, exc)',
     '    log.exception("%s %s: durable engine unreachable: %s", request.method, request.url.path,'
     " exc)"),
    ("the log says nothing", APP,
     '    log.warning("%s %s: durable engine unreachable: %s", request.method, request.url.path, exc)',
     "    pass"),

    # 2. the action layer
    ("an action reads the engine's silence as its own failure", ACTIONS,
     "    except EngineUnreachable as exc:\n", "    except ZeroDivisionError as exc:\n"),
    ("the action's refusal is FAILED, a 500", ACTIONS,
     '        return refused(UNAVAILABLE, f"could not {key}: {exc}")',
     '        return refused(FAILED, f"could not {key}: {exc}")'),

    # 3. one exception
    ("the reads raise an exception of their own that nobody catches", VIEW,
     "from openfactory.runtime.temporal.vocabulary import ATTENTION_STATES, MERGE_WAIT, "
     "EngineUnreachable\n",
     "from openfactory.runtime.temporal.vocabulary import ATTENTION_STATES, MERGE_WAIT\n\n\n"
     "class EngineUnreachable(RuntimeError):\n    pass\n\n\n"),
]
