"""A running deployment says whether it is alive, whether it can work and which version it runs,
and its logs can be JSON lines that say the project (#681), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/681_a_running_deployment_says_whether_it_is_alive_ready_and_which_version.py

The claims, each a row:
  1. liveness reads nothing;
  2. readiness answers 503 naming each failing check, with a sentence and never the cause, and
     needs no credential;
  3. readiness is bounded, keeps the engine's answer for its window — no longer — and shares one
     check between callers;
  4. each check fails for its own dependency: a pooled client is not an engine that answers, an
     undeclared engine and a missing client library are said as such, the registry is read, and
     the identity check is the gate's own decision;
  5. the worker answers the same on its own port, only when asked, and opens it before it waits;
  6. every process the compose file starts is health-checked by `/readyz` on its own port, and the
     probe fails on anything but a 200;
  7. the version route answers the package's version, the image, the engine's address kind and
     every add-on row, unloaded, behind the floor's credential;
  8. JSON lines: chosen only by the setting, with the four fields, a traceback on one line, the
     letters kept, the deployment named, and the project and product a record concerns — from
     every panel route and every worker activity that names one.
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
INTERCEPTORS = "openfactory/runtime/temporal/interceptors.py"
WORKER = "openfactory/runtime/temporal/worker.py"
COMPOSE = "docker-compose.yml"

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
     "        said, cause = exc.said or SAID[name], exc.cause",
     "        said, cause = exc.cause, exc.cause"),
    ("readiness is moved under the gate", HEALTH,
     'READY_PATH = "/readyz"', 'READY_PATH = "/api/readyz"'),

    # 3. bounded, kind to the engine
    ("a check that hangs holds the answer", HEALTH,
     "        await asyncio.wait_for(CHECKS[name](), DEADLINE_S)",
     "        await CHECKS[name]()"),
    ("the engine is asked on every call", HEALTH,
     "    if memo is None or _clock() - memo[0] >= ENGINE_TTL_S:",
     "    if True:"),
    ("the engine's answer is kept past its window", HEALTH,
     "    if memo is None or _clock() - memo[0] >= ENGINE_TTL_S:",
     "    if memo is None or _clock() - memo[0] >= ENGINE_TTL_S * 1000:"),
    ("callers that ask together each ask the engine", HEALTH,
     "        memo = await _engine_read.shared(_ask_the_engine)",
     "        memo = await _ask_the_engine(None)"),

    # 4. each check, against its own dependency
    ("a pooled client is taken for an engine that answers", HEALTH,
     '        if await view.check_health(client):\n            return "", ""\n',
     '        return "", ""\n'),
    ("an engine nobody declared is said to have not answered", HEALTH,
     '        return (SAID["engine"] if ENGINE.declared() else ENGINE_UNDECLARED), error',
     '        return SAID["engine"], error'),
    ("a missing client library is not said as an install", HEALTH,
     "        if error == CLIENT_MISSING:\n            return CLIENT_MISSING, error\n", ""),
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
    ("the setting never makes a line JSON", LOGGING,
     "                         if structured() else _UTC(FORMAT))",
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
     "            said = getattr(record, tag, None) or about.get(tag)",
     "            said = getattr(record, tag, None)", LOGS),
    ("what a block was about outlives the block", LOGGING,
     "        _ABOUT.reset(token)", "        pass", LOGS),
    ("the product is never read from the registry", LOGGING,
     "        product = product_key(ProjectRegistry().get(project))", '        product = ""', LOGS),
    ("the readable line pays for the registry", LOGGING,
     "    if product or not structured():\n        return {\"project\": project,",
     "    if product:\n        return {\"project\": project,", LOGS),
    ("the panel's routes are built without the class", APP,
     "app.router.route_class = AboutItsProject\n", "", LOGS),
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
]
