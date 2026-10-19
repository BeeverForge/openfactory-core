"""A running deployment says whether it is alive, whether it can work and which version it runs,
and its logs can be JSON lines that say the project (#681), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/681_a_running_deployment_says_whether_it_is_alive_ready_and_which_version.py

The claims, each a row:
  1. liveness reads nothing;
  2. readiness answers 503 naming each failing check, with a sentence and never the cause, and
     needs no credential;
  3. readiness is bounded by a deadline that follows the engine's own, keeps every check's answer
     for its window — no longer, and not an answer whose question lost its slot — and shares one
     question per check between callers;
  3b. readiness costs nobody else anything (review of #818): no check takes a thread of the
     default executor the gate uses, none blocks the event loop, none is blamed for another, and a
     check's own thread never holds a process open;
  3c. every layer between a check and a supervisor outlasts the deadline (second review): the
     probe's timeout and the worker listener's bound;
  4. each check fails for its own dependency: a pooled client is not an engine that answers, an
     undeclared engine and a missing client library are said as such, the registry is read, and
     the identity check is the gate's own decision;
  5. the worker answers the same on its own port, only when asked, on loopback unless the
     deployment says otherwise, echoing nothing it was sent, only once a request has been read to
     its end, and opens it once its boot's own steps are done and before it waits for the engine;
  6. every process the compose file starts is health-checked by `/readyz` on its own port, and the
     probe fails on anything but a 200;
  7. the version route answers the package's version, the image, the engine's address kind and
     every add-on row, unloaded, behind the floor's credential;
  8. JSON lines: chosen only by the setting, with the four fields, a traceback on one line, the
     letters kept, the deployment named, and the project and product a record concerns — from
     every panel route and every worker activity that names one; the lines a process prints for a
     person and the sentence it ends with follow the format; a failure's cause is logged once;
     a stack asked for is kept; a stream's body says its project;
  9. the product costs nobody anything (second review of #818): a line reads it from memory; the
     registry is read once per window, one read at a time, quietly, on a daemon thread of its own;
     only work the gate admitted asks for it — never a route the gate leaves open — and neither a
     route nor an activity takes a thread of the default executor for it; the copy holds the
     registry's projects only, a failed read keeps the last one, and a read forgotten lands nowhere;
  10. with JSON lines, every engine client is made on a runtime of its own whose core writes
     through the log at the library's default filter — so a client dropped never silences another
     (third review) — and without them the library's default is left alone;
  11. the probe's own guards (third review): liveness takes no pooled thread, neither answer is
     cached, each sentence is its own, the probe gives up on a port that never answers, it
     imports no engine client, and the healthcheck's timeout outlasts the probe's wait;
  12. with JSON lines nothing a process writes by itself is a plain line (fourth review): every
     write to stdout or stderr in the package goes through `logs.announce` or sits where no
     deployment process runs it, a line for a person follows what this process's log is, and
     Python's own warning, uncaught exception (in any thread) and unraisable one are JSON lines;
     a poll that gives up on a hung check keeps its one question and still says why once; and the
     probe says an answer that is not HTTP in one line;
  13. what JSON lines cost and say (fifth review, and the review requesting changes on d2ef6149):
     a connect the engine refuses keeps no runtime alive; the panel sets up its log before it says
     anything; a line that must never be silent is a WARNING; a thread that exits says nothing;
     and every variable the log and the probes read has its row in the configuration reference;
  14. a process holds one engine client (sixth review): every caller, from any loop, gets the
     client the process holds — so the worker's readiness asks the worker's own client and no read
     drops one — a target that changes gets its own and the old one's runtime goes at once; the
     worker binds loopback by default; a line carries the documented fields and no others, and is
     one line for every reader.
"""

READY = "tests/test_a_running_deployment_says_whether_it_is_alive_and_ready.py"
VERSION = "tests/test_a_running_deployment_says_which_version_it_runs.py"
LOGS = "tests/test_the_logs_can_be_json_lines_that_say_the_project.py"

TEST = READY

HEALTH = "openfactory/observability/health.py"
LOGGING = "openfactory/observability/logs.py"
VIEW = "openfactory/runtime/temporal/view.py"
PLUGINS = "openfactory/plugins.py"
APP = "openfactory/api/app.py"
ROUTE = "openfactory/api/project_route.py"
REGISTRY = "openfactory/registry.py"
CONNECTION = "openfactory/runtime/temporal/connection.py"
INTERCEPTORS = "openfactory/runtime/temporal/interceptors.py"
WORKER = "openfactory/runtime/temporal/worker.py"
COMPOSE = "docker-compose.yml"
CONFIGURATION = "docs/reference/configuration.md"
DEADLINES = "openfactory/runtime/temporal/deadlines.py"
ACTIVITIES = "openfactory/runtime/temporal/activities.py"
EVENTS = "openfactory/observability/events.py"

MUTATIONS = [
    # 1. liveness reads nothing
    ("liveness asks every check before it answers", HEALTH,
     "    if path == LIVE_PATH:\n        return 200, alive()",
     "    if path == LIVE_PATH:\n        await ready()\n        return 200, alive()"),

    # 2. the 503, and what it says
    ("a failing check is not named", HEALTH,
     '    failing = [name for name, verdict in checks.items() if not verdict["ok"]]',
     "    failing = []"),
    ("a deployment that is not ready answers 200", HEALTH,
     '        return (200 if said["ready"] else 503), said',
     "        return 200, said"),
    ("the body carries the cause instead of the check's sentence", HEALTH,
     "            said, cause = exc.said or SAID[name], exc.cause",
     "            said, cause = exc.cause, exc.cause"),
    ("readiness is moved under the gate", HEALTH,
     'READY_PATH = "/readyz"', 'READY_PATH = "/api/readyz"'),

    # 3. bounded, kept for the window, one question at a time
    ("a check that hangs holds the answer", HEALTH,
     "        _when, said, cause = await asyncio.wait_for(_SLOTS[name].kept_or_asked(name), bound)",
     "        _when, said, cause = await _SLOTS[name].kept_or_asked(name)"),
    ("the deadline ignores the engine's own", HEALTH,
     "    return 2 * read_deadline() + 1.0", "    return 5.0"),
    ("every check is asked on every call", HEALTH,
     "        if kept is not None and _clock() - kept[0] < WINDOW_S:\n            return kept",
     "        if False:\n            return kept"),
    ("a check's answer is kept past its window", HEALTH,
     "        if kept is not None and _clock() - kept[0] < WINDOW_S:",
     "        if kept is not None and _clock() - kept[0] < WINDOW_S * 1000:"),
    ("callers that ask together each ask every dependency", HEALTH,
     "        return await self.read.shared(lambda flight: self._ask(name, flight))",
     "        return await self._ask(name, None)"),
    ("an answer whose question lost its slot is kept", HEALTH,
     "        if self.read.holds(flight):\n            self.kept = answer",
     "        if True:\n            self.kept = answer"),

    # 3b. readiness costs nobody else anything (review of #818)
    ("the registry check takes a thread of the gate's executor", HEALTH,
     "    await _off_the_loop(_registry_reads)", "    await asyncio.to_thread(_registry_reads)"),
    ("the identity check takes a thread of the gate's executor", HEALTH,
     "    await _off_the_loop(_identity_admits)", "    await asyncio.to_thread(_identity_admits)"),
    ("the registry is read on the event loop", HEALTH,
     "    await _off_the_loop(_registry_reads)", "    _registry_reads()"),
    ("the identity provider is asked on the event loop", HEALTH,
     "    await _off_the_loop(_identity_admits)", "    _identity_admits()"),
    ("a check's thread holds a process that is exiting", HEALTH,
     "                     daemon=True).start()", "                     daemon=False).start()"),

    # 3c. every layer outlasts the deadline (second review of #818)
    ("the probe gives up before the readiness deadline", HEALTH,
     "timeout=probe_timeout() if timeout is None else timeout)",
     "timeout=1.0 if timeout is None else timeout)"),
    ("the worker's listener gives up before the readiness deadline", HEALTH,
     "_read_and_answer(reader), _READ_S + deadline())", "_read_and_answer(reader), _READ_S)"),

    # 4. each check, against its own dependency
    ("a pooled client is taken for an engine that answers", HEALTH,
     "        answered = await view.check_health(await view.connect())",
     "        answered = bool(await view.connect())"),
    ("an engine nobody declared is said to have not answered", HEALTH,
     '        raise NotReady("no engine address is declared", said=ENGINE_UNDECLARED)',
     '        raise NotReady("no engine address is declared")'),
    ("a missing client library is not said as an install", HEALTH,
     '        raise NotReady(why, said=CLIENT_MISSING if why == CLIENT_MISSING else "") from exc',
     "        raise NotReady(why) from exc"),
    ("the engine check warns on every poll, as the floor's probe does", HEALTH,
     '        raise NotReady(f"{type(exc).__name__}: {str(exc)[:200]}") from exc',
     '        log.warning("the engine did not answer (%s)", exc)\n'
     '        raise NotReady(f"{type(exc).__name__}: {str(exc)[:200]}") from exc'),
    ("the cause is logged on every poll", HEALTH,
     "    elif not ok and before is not False:", "    elif not ok:"),
    ("the engine's health check is not bounded", VIEW,
     '@_bounded_read("a health check")\n', ""),
    ("the registry is opened and never read", HEALTH,
     "    ProjectRegistry().list()", "    ProjectRegistry()"),
    ("the identity check never reads the store the local row depends on", HEALTH,
     '    if getattr(provider, "open_to_everyone", lambda: False)():\n        return\n', ""),
    ("a provider that cannot check anybody is ready", HEALTH,
     "    if isinstance(why, str) and why.strip():", "    if False:"),

    # 5. the worker
    ("the worker's listener ignores a query string", HEALTH,
     '    return await answer(target.split("?", 1)[0])', "    return await answer(target)"),
    ("the worker opens a port nobody asked for", HEALTH,
     "    port = port if port is not None else port_asked()",
     "    port = port if port is not None else 0"),
    ("a port that is not a port is used", HEALTH,
     "    if not 0 < port < 65536:", "    if port < 0:"),
    ("the worker never opens its listener", WORKER,
     "    _health = await health.listen()  # noqa: F841 — held: it serves for as long as the worker"
     " runs\n", ""),
    ("the worker opens its listener before its boot's own steps", WORKER,
     "    load_dotenv()  # bot credentials + Claude token for the activities\n",
     "    load_dotenv()  # bot credentials + Claude token for the activities\n"
     "    from openfactory.observability import health as _early\n"
     "    _first = await _early.listen()  # noqa: F841\n"),
    ("the worker answers every interface unless told otherwise", HEALTH,
     '    return (os.environ.get(HOST_VARIABLE) or "").strip() or LOOPBACK',
     '    return (os.environ.get(HOST_VARIABLE) or "").strip() or "0.0.0.0"'),
    ("the deployment's host is ignored", HEALTH,
     "    host = host or host_asked()", "    host = host or LOOPBACK"),
    ("the worker answers before it has read the request's headers", HEALTH,
     "    for _ in range(_MOST_HEADERS):\n"
     "        header = await asyncio.wait_for(reader.readline(), _READ_S)\n"
     "        if header in (b\"\\r\\n\", b\"\\n\", b\"\"):\n            break\n"
     "    else:\n        raise ValueError(\"too many header lines\")\n", ""),
    ("the worker's 404 echoes what it was sent", HEALTH,
     """    return 404, {"detail": f"only {' and '.join(PATHS)} are answered here"}""",
     """    return 404, {"detail": f"nothing is served at {path}"}"""),

    # 6. the healthchecks
    ("the worker's healthcheck asks another port than it answers on", COMPOSE,
     '      test: ["CMD", "python", "-m", "openfactory.observability.health", "--port", "8788"]',
     '      test: ["CMD", "python", "-m", "openfactory.observability.health", "--port", "8787"]'),
    ("the panel's healthcheck asks liveness, not readiness", COMPOSE,
     '      test: ["CMD", "python", "-m", "openfactory.observability.health", "--port", "8787"]',
     '      test: ["CMD", "python", "-m", "openfactory.observability.health", "--port", "8787",'
     ' "--path", "/healthz"]'),
    ("the worker is not told where to answer", COMPOSE,
     '      OPENFACTORY_HEALTH_PORT: "8788"\n', ""),
    ("the probe passes on any answer", HEALTH,
     "    if response.status == 200:\n        return 0", "    if response.status < 600:\n"
     "        return 0"),

    # 7. the version
    ("the version is not the package's", HEALTH,
     '    return {"version": __version__, "image": _image(),',
     '    return {"version": "0.0.0", "image": _image(),', VERSION),
    ("outside an image, an image is invented", HEALTH,
     "    if not (code or digest):\n        return None\n", "", VERSION),
    ("the digest the deployment names is dropped", HEALTH,
     '    return {"digest": digest or None,', '    return {"digest": None,', VERSION),
    ("a cloud engine reads as a remote one", VIEW,
     '    if any(host in declared for host in _CLOUD_HOSTS):\n        return "cloud"\n', "",
     VERSION),
    ("every engine on a host reads as this machine", VIEW,
     '    return "remote" if ENGINE.elsewhere(declared) else "local"', '    return "local"',
     VERSION),
    ("an add-on row is listed without its distribution", PLUGINS,
     '        rows.append({"distribution": str(getattr(dist, "name", "") or ""),',
     '        rows.append({"distribution": "",', VERSION),
    ("an add-on is loaded to be listed", PLUGINS,
     '        dist = getattr(point, "dist", None)\n',
     '        point.load()\n        dist = getattr(point, "dist", None)\n', VERSION),
    ("a name that is no row is listed", PLUGINS,
     "            continue\n        dist = getattr(point,",
     "            pass\n        dist = getattr(point,",
     VERSION),
    ("the version leaves the gate", HEALTH,
     'VERSION_PATH = "/api/v1/version"', 'VERSION_PATH = "/v1/version"', VERSION),

    # 8. the JSON lines
    # RE-PINNED 2026-10-19 (fourth review): `configure` reads the setting once, as `in_json`.
    ("the setting never makes a line JSON", LOGGING,
     "                         if in_json else _UTC(FORMAT))",
     "                         if False else _UTC(FORMAT))", LOGS),
    ("any value of the setting makes the lines JSON", LOGGING,
     '    return (os.environ.get(FORMAT_VARIABLE) or "").strip().lower() == "json"',
     '    return bool((os.environ.get(FORMAT_VARIABLE) or "").strip())', LOGS),
    ("a JSON line has no time", LOGGING,
     '        line: dict[str, str] = {"ts": _utc(record), "level": record.levelname,',
     '        line: dict[str, str] = {"level": record.levelname,', LOGS),
    ("a traceback is dropped from its line", LOGGING,
     "            line[\"exception\"] = self.formatException(record.exc_info)",
     "            pass", LOGS),
    ("the letters of a message are escaped", LOGGING,
     "ensure_ascii=False", "ensure_ascii=True", LOGS),
    ("the deployment is never named", LOGGING,
     '            line["deployment"] = self._deployment', "            pass", LOGS),
    ("what the work is about never reaches the line", LOGGING,
     '    project = str(own or about.get("project") or "")', '    project = str(own or "")', LOGS),
    ("a record that names its own project borrows the block's product", LOGGING,
     '("" if own else about.get("product"))', 'about.get("product")', LOGS),
    ("a stack asked for is dropped from its line", LOGGING,
     '            line["stack"] = self.formatStack(record.stack_info)', "            pass", LOGS),
    ("what a block was about outlives the block", LOGGING,
     "        _ABOUT.reset(token)", "        pass", LOGS),
    ("the product is never read from the registry", LOGGING,
     "            known: dict[str, str] | None = _products_in_the_registry()",
     "            known = {}", LOGS),
    ("the readable line pays for the registry", LOGGING,
     "    if structured():\n        _PRODUCTS.freshen()",
     "    if True:\n        _PRODUCTS.freshen()", LOGS),
    ("the panel's routes are built without the class", APP,
     "app.router.route_class = AboutItsProject.gated_by(lambda path: _gated(path))\n", "", LOGS),
    ("a stream's body says no project", ROUTE,
     "            if isinstance(response, StreamingResponse):", "            if False:", LOGS),
    ("a route about a project does not say it", ROUTE,
     '        if "project" not in self.param_convertors:', "        if True:", LOGS),
    ("an activity whose project is one model down does not say it", INTERCEPTORS,
     "    if not project and depth > 1 and isinstance(fields, dict):", "    if False:", LOGS),
    ("an activity that takes its project bare does not say it", INTERCEPTORS,
     '        if parameter in PROJECT_PARAMETERS and isinstance(value, str) and value:\n'
     '            return value, ""\n', "", LOGS),
    ("the product an activity carries is ignored", INTERCEPTORS,
     '    product = getattr(value, "product", None)', "    product = None", LOGS),
    ("the worker is built without its interceptor", WORKER,
     "        interceptors=[AboutItsProject()],\n", "", LOGS),
    # RE-PINNED 2026-10-19 (fourth review): `announce` asks what this process's log is, and logs
    # at the line's own level.
    ("a line for a person is printed past the format", LOGGING,
     "    if writes_json():\n        logger.log(level, line)",
     "    if False:\n        logger.log(level, line)", LOGS),
    ("the worker prints its line itself again", WORKER,
     '    logs.announce(log, f"openfactory worker up · {address()} · ns={namespace()} · "\n',
     '    print(f"openfactory worker up · {address()} · ns={namespace()} · "\n', LOGS),
    ("serve echoes its line itself again", "openfactory/cli.py",
     '    logs.announce(log, f"panel: http://{host}:{port}")',
     '    typer.echo(f"panel: http://{host}:{port}")', LOGS),
    # RE-PINNED 2026-10-19 (fourth review): the same question as `announce`.
    ("a worker that cannot start ends in a plain line", LOGGING,
     "    if writes_json():\n        logger.error(sentence)",
     "    if False:\n        logger.error(sentence)", LOGS),

    # 9. the product costs nobody anything (second review of #818)
    ("every panel request about a project reads the product on the gate's executor", ROUTE,
     "            with logs.about(project=project):\n"
     "                response = await handler(request)",
     "            with logs.about(project=project, product=(await __import__(\"asyncio\")"
     ".to_thread(logs._products_in_the_registry)).get(project, \"\")):\n"
     "                response = await handler(request)", LOGS),
    ("a route the gate leaves open asks for the products", ROUTE,
     "            if gated(request.url.path):\n                logs.freshen_products()",
     "            if True:\n                logs.freshen_products()", LOGS),
    ("the route class is not handed the gate's rule", APP,
     "AboutItsProject.gated_by(lambda path: _gated(path))", "AboutItsProject", LOGS),
    ("a route behind the gate never asks for the products", ROUTE,
     "            if gated(request.url.path):\n                logs.freshen_products()",
     "            if False:\n                logs.freshen_products()", LOGS),
    ("every activity reads the product on the default executor first", INTERCEPTORS,
     "        if not product:\n            logs.freshen_products()\n"
     "        with logs.about(project=project, product=product):",
     "        with logs.about(project=project, product=product or (await __import__(\"asyncio\")"
     ".to_thread(logs._products_in_the_registry)).get(project, \"\")):", LOGS),
    ("an activity never asks for the products", INTERCEPTORS,
     "        if not product:\n            logs.freshen_products()\n", "", LOGS),
    ("the products are read on the default executor", LOGGING,
     "        threading.Thread(target=self._read, args=(flight,), "
     "name=\"openfactory-log-products\",\n"
     "                         daemon=True).start()",
     "        __import__(\"asyncio\").get_running_loop().run_in_executor(None, self._read, flight)",
     LOGS),
    ("the products' read holds a process that is exiting", LOGGING,
     "                         daemon=True).start()",
     "                         daemon=False).start()", LOGS),
    ("every ask reads the registry again, however many are in flight", LOGGING,
     "            if self._flight is not None or (", "            if False and (", LOGS),
    ("the products are read again on every ask, whatever the window", LOGGING,
     "_clock() - self._began < PRODUCTS_WINDOW_S):", "_clock() - self._began < 0):", LOGS),
    ("the copy keeps every name a line asks about", LOGGING,
     '        return self._known.get(project, "")',
     '        return self._known.setdefault(project, "")', LOGS),
    ("a read that failed empties the copy", LOGGING,
     "            if known is not None:\n                self._known = known",
     "            self._known = known or {}", LOGS),
    ("a read begun before `forget` lands after it", LOGGING,
     "            if self._flight is not flight:\n                return",
     "            if False:\n                return", LOGS),
    ("one entry that does not build loses every product", REGISTRY,
     "                continue  # said by `list`, by name, on every load", "                raise",
     LOGS),

    # 10. the engine client's own core
    # RETIRED 2026-10-19: "a client is made before its core is told" and "a runtime somebody set
    # is replaced" — the third review measured one shared default runtime going silent once any
    # client of it is dropped, so no default runtime is set any more; each client gets its own.
    ("every client shares one runtime, so one dropped silences the rest", CONNECTION,
     "    return Runtime(telemetry=core_telemetry())\n",
     "    global _SHARED\n    if globals().get(\"_SHARED\") is None:\n"
     "        _SHARED = Runtime(telemetry=core_telemetry())\n    return _SHARED\n", LOGS),
    ("a client is made on the library's default runtime", CONNECTION,
     '        **({"runtime": runtime} if runtime is not None else {}), **_auth()',
     "        **_auth()", LOGS),
    ("the core writes its own lines", CONNECTION,
     "        forwarding=LogForwardingConfig(logger=logging.getLogger(CORE_LOGGER))))",
     "        forwarding=None))", LOGS),
    ("the core is asked for more than it says by default", CONNECTION,
     "        filter=LoggingConfig.default.filter,", '        filter="TRACE",', LOGS),
    ("the core's lines are routed without JSON", CONNECTION,
     "    if not logs.structured():\n        return None\n    return Runtime(",
     "    return Runtime(", LOGS),

    # 11. the probe's own guards (third review)
    ("liveness is a sync handler, waiting for a pooled thread", APP,
     "async def healthz() -> JSONResponse:", "def healthz() -> JSONResponse:"),
    ("readiness's answer may be cached", APP,
     "    status, body = await health.answer(health.READY_PATH)\n"
     "    return JSONResponse(body, status_code=status, headers=_NO_CACHE)",
     "    status, body = await health.answer(health.READY_PATH)\n"
     "    return JSONResponse(body, status_code=status)"),
    ("an engine nobody declared is said as the engine that did not answer", HEALTH,
     'ENGINE_UNDECLARED = "this deployment does not say where its durable engine is"',
     'ENGINE_UNDECLARED = "the durable engine did not answer"'),
    ("the probe waits for ever on a port that never answers", HEALTH,
     "timeout=probe_timeout() if timeout is None else timeout)", "timeout=None)"),
    ("the probe reads the deadline through the engine's client", HEALTH,
     "    from openfactory.runtime.temporal.deadlines import read_deadline\n",
     "    from openfactory.runtime.temporal.view import read_deadline\n"),
    ("the worker's healthcheck gives up before the probe does", COMPOSE,
     "      timeout: 10s\n      retries: 3\n      start_period: 5m\n",
     "      timeout: 8s\n      retries: 3\n      start_period: 5m\n"),

    # 12. with JSON lines nothing a process writes by itself is a plain line (fourth review)
    ("an activity prints a plain line", ACTIVITIES,
     "    v0 advisory — returns {summary, recommend, rationale, watch_outs} (or {} if it can't "
     "opine).\"\"\"\n",
     "    v0 advisory — returns {summary, recommend, rationale, watch_outs} (or {} if it can't "
     "opine).\"\"\"\n    print(f\"a plain line from an activity for {item.project}\", flush=True)\n",
     LOGS),
    ("the coordinator prints its line itself again", ACTIVITIES,
     '        logs.announce(activity.logger, f"OPENFACTORY_COORDINATOR: no parseable advice for "\n'
     '                                       f"{item.project}#{item.issue}", logging.WARNING)\n',
     '        print(f"OPENFACTORY_COORDINATOR: no parseable advice for "\n'
     '              f"{item.project}#{item.issue}", flush=True)\n', LOGS),
    ("the live feed prints its envelope past the format", EVENTS,
     "        logs.announce(log, self.prefix + event.model_dump_json())",
     "        print(self.prefix + event.model_dump_json(), flush=True)", LOGS),
    ("a line for a person follows the variable, not this process's log", LOGGING,
     "    return any(isinstance(handler.formatter, _JSON) for handler in "
     "logging.getLogger().handlers)",
     "    return structured()", LOGS),
    ("Python's warnings bypass the log", LOGGING,
     "    logging.captureWarnings(True)\n", "", LOGS),
    ("an exception nobody caught prints its traceback", LOGGING,
     "    sys.excepthook = _uncaught\n", "", LOGS),
    ("an exception that ends a thread prints its traceback", LOGGING,
     "    threading.excepthook = _uncaught_in_a_thread\n", "", LOGS),
    ("an exception nobody could raise prints its traceback", LOGGING,
     "    sys.unraisablehook = _unraisable\n", "", LOGS),
    ("Python's own lines go to the log in the readable format too", LOGGING,
     "    if in_json:\n        _pythons_own_lines_through_the_log()",
     "    if True:\n        _pythons_own_lines_through_the_log()", LOGS),
    ("a poll that gives up drops its question from the slot", HEALTH,
     "    except TimeoutError:\n        said, cause",
     "    except TimeoutError:\n        _SLOTS[name].read.forget()\n        said, cause"),
    ("a poll that gives up never says why", HEALTH,
     '        said, cause = f"{SAID[name]} within {bound:g}s", f"no answer within {bound:g}s"\n'
     "    if not said:",
     '        return {"ok": False, "detail": f"{SAID[name]} within {bound:g}s"}\n'
     "    if not said:"),
    ("the probe ends on a traceback when the answer is not HTTP", HEALTH,
     "    except http.client.HTTPException as exc:", "    except ArithmeticError as exc:"),

    # 13. what JSON lines cost and say (fifth review, and the review on d2ef6149)
    ("a failed connect keeps its runtime", CONNECTION,
     "            gc.collect()\n", "            pass\n", LOGS),
    ("the panel says something before its log is set up", "openfactory/cli.py",
     "    logs.configure()\n    # SAY WHICH BUILD SERVES THIS PAGE",
     "    from openfactory import namespace as _early\n\n"
     "    _early.announce_build(PANEL_ROLE)\n"
     "    logs.configure()\n    # SAY WHICH BUILD SERVES THIS PAGE", LOGS),
    ("the degraded pre-flight is said at INFO", ACTIVITIES,
     '                                           f"{inp.project}#{inp.issue} — {reason}",\n'
     "                          logging.WARNING)",
     '                                           f"{inp.project}#{inp.issue} — {reason}",\n'
     "                          logging.INFO)", LOGS),
    ("a thread that exits is logged as an exception nobody caught", LOGGING,
     "    if said.exc_type is SystemExit:\n        return\n",
     "    if False:\n        return\n", LOGS),
    ("the deployment's variable is documented under another name", CONFIGURATION,
     "| `OPENFACTORY_DEPLOYMENT` |", "| `OPENFACTORY_DEPLOYMENT_NAME` |", LOGS),

    # 14. a process holds one engine client (sixth review)
    ("every caller is given a client of its own again", CONNECTION,
     "            held = _HELD.get(key)\n", "            held = None\n", LOGS),
    ("a target that changed is served the old target's client", CONNECTION,
     "            held = _HELD.get(key)\n", "            held = next(iter(_HELD.values()), None)\n",
     LOGS),
    ("a client a changed target lets go of keeps its runtime", CONNECTION,
     "        del let_go\n        gc.collect()\n", "        del let_go\n", LOGS),
    ("the worker answers beyond this machine by default", HEALTH,
     'LOOPBACK = "127.0.0.1"', 'LOOPBACK = "0.0.0.0"'),
    ("a line carries every extra a record was given", LOGGING,
     "        line.update(_concerns(record))\n",
     "        line.update(_concerns(record))\n"
     "        line.update({k: str(v) for k, v in vars(record).items()\n"
     "                     if k not in vars(logging.makeLogRecord({})) and k != \"message\"})\n",
     LOGS),
    ("a line boundary is written raw", LOGGING,
     "default=str).translate(_STILL_LINE_BREAKS)", "default=str)", LOGS),
]
