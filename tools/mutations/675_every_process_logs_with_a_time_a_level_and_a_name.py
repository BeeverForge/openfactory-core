"""Every process the deployment starts logs with a time, a level and a name, and keeps INFO
(#675, journey 0), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/675_every_process_logs_with_a_time_a_level_and_a_name.py

The claims, each a row:
  1. both entry points set the log up: the worker's door and `serve`, and uvicorn writes through
     the same handler;
  2. the line carries a UTC time, the level and the logger's name;
  3. the platform's INFO is kept, uvicorn's request lines too, and the libraries stay at WARNING;
  4. the level is a setting, and a value that is no level keeps INFO;
  5. a process that already set its log up keeps it.
"""

TEST = "tests/test_every_process_the_deployment_starts_logs_with_a_time_a_level_and_a_name.py"
LOGS = "openfactory/observability/logs.py"
WORKER = "openfactory/runtime/temporal/worker.py"
CLI = "openfactory/cli.py"

MUTATIONS = [
    # 1. both entry points
    ("the worker's door does not set the log up", WORKER,
     "    logs.configure()\n    try:\n        await main()", "    try:\n        await main()"),
    ("serve does not set the log up", CLI,
     # RE-PINNED 2026-10-18 (#681): the panel's first line is announced once the log is set up,
     # so the line after `logs.configure()` is that announcement's comment. Same cut.
     "    logs.configure()\n    # Printed for a person, as it always was",
     "    # Printed for a person, as it always was"),
    ("uvicorn sets up a format of its own", CLI,
     "timeout_graceful_shutdown=5,\n                log_config=None)",
     "timeout_graceful_shutdown=5)"),

    # 2. the line
    ("the line has no time", LOGS,
     'FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"',
     'FORMAT = "%(levelname)s %(name)s: %(message)s"'),
    ("the line has no level", LOGS,
     'FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"',
     'FORMAT = "%(asctime)s %(name)s: %(message)s"'),
    ("the line has no logger's name", LOGS,
     'FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"',
     'FORMAT = "%(asctime)s %(levelname)s %(message)s"'),
    ("the time is the machine's zone, not UTC", LOGS,
     "time.gmtime(record.created)", "time.localtime(record.created)"),

    # 3. the levels
    ("the platform's INFO is dropped", LOGS,
     "    for name in OURS:\n        logging.getLogger(name).setLevel(level())\n", ""),
    ("uvicorn's request lines are dropped", LOGS,
     'OURS = ("openfactory", "uvicorn")', 'OURS = ("openfactory",)'),
    ("the libraries' INFO comes through", LOGS,
     "    root.setLevel(logging.WARNING)\n", "    root.setLevel(logging.INFO)\n"),

    # 4. the setting
    ("the level is not a setting", LOGS,
     '    named = logging.getLevelName((os.environ.get(LEVEL_VARIABLE) or "INFO").strip().upper())',
     "    named = logging.INFO"),
    ("a value that is no level is used as one", LOGS,
     "    return named if isinstance(named, int) else logging.INFO", "    return named"),

    # 5. an existing configuration
    ("a process that set its log up has it replaced", LOGS,
     "    if root.handlers:\n        return False\n", ""),
]
