"""CI runs the suite as parallel jobs and proves that every collected test ran exactly once,
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/ci_runs_every_test_exactly_once.py

The claims, each a row:
  1. the slices of one selection hold every test exactly once, whatever process computes them,
     and an xdist run writes each test it started once, a skipped one included;
  2. the proof fails on a test missing, doubled or unknown, and on an empty collection;
  3. CI wires it: the `test` job needs every job and runs the proof, the slices are the matrix's,
     the three runs' markers split the suite without overlap, and the guard on CI's pytest follows
     the Makefile;
  4. a test that asserts its own CPU time is marked `alone` and runs with no xdist neighbours;
  5. the real-daemon tests are in the `docker` group, and the integration run distributes by it.
"""

TEST = "tests/test_ci_runs_every_test_exactly_once.py"
CONF = "tests/conftest.py"
PROOF = "scripts/every_test_ran_once.py"
CI = ".github/workflows/ci.yml"
GUARD = "tests/test_ci_runs_what_we_run.py"

MUTATIONS = [
    # 1. the slices, and what a run records
    ("a slice keeps every test", CONF,
     "        items[:] = kept\n", ""),
    ("the slice rule is salted per process", CONF,
     "    return zlib.crc32(nodeid.encode()) % count == index - 1",
     "    return hash(nodeid) % count == index - 1"),
    ("a slice that does not exist is accepted", CONF,
     "    if not (index.isdigit() and count.isdigit() and 1 <= int(index) <= int(count)):",
     "    if not (index.isdigit() and count.isdigit()):"),
    ("an xdist worker records too, so every test is written twice", CONF,
     '    if record and not hasattr(config, "workerinput"):', "    if record:"),
    ("a test is recorded when it is called, so a skipped one is missing", CONF,
     '        if report.when == "setup":', '        if report.when == "call":'),
    ("the ids may be written inside the tree, where a scan reads them mid-run", CONF,
     "        if config.rootpath.resolve() in Path(record).resolve().parents:", "        if False:"),
    ("the collection is never written", CONF,
     "        if session.config.option.collectonly:", "        if False:"),

    # 2. the proof
    ("a missing test passes the proof", PROOF,
     '        "missing": sorted(wanted - counts.keys()),', '        "missing": [],'),
    ("a doubled test passes the proof", PROOF,
     '        "doubled": sorted(nodeid for nodeid, n in counts.items() if n > 1),',
     '        "doubled": [],'),
    ("an unknown test passes the proof", PROOF,
     '        "unknown": sorted(counts.keys() - wanted),', '        "unknown": [],'),
    ("an empty collection passes the proof", PROOF,
     "    if not collected:", "    if False:"),

    # 3. CI wires it
    ("the test job does not wait for the integration job", CI,
     "    needs: [lint, unit, integration]", "    needs: [lint, unit]"),
    ("the test job never runs the proof", CI,
     "        run: make test-ran-once", "        run: echo the proof was skipped"),
    ("the unit job cuts fewer slices than its matrix runs", CI,
     "          TEST_SHARDS: 4", "          TEST_SHARDS: 3"),
    ("the unit job forgets one of the integration markers", "Makefile",
     '	python -m pytest -q -n auto -m "not ($(INTEGRATION_TESTS) or $(ALONE_TESTS))" --durations=15',
     '	python -m pytest -q -n auto -m "not (owns_its_engine or $(ALONE_TESTS))" --durations=15'),
    ("the unit job runs the alone tests too", "Makefile",
     '	python -m pytest -q -n auto -m "not ($(INTEGRATION_TESTS) or $(ALONE_TESTS))" --durations=15',
     '	python -m pytest -q -n auto -m "not ($(INTEGRATION_TESTS))" --durations=15'),
    ("the alone run has xdist neighbours", "Makefile",
     '	python -m pytest -q -p no:xdist -m "$(ALONE_TESTS) and not ($(INTEGRATION_TESTS))"',
     '	python -m pytest -q -n auto -m "$(ALONE_TESTS) and not ($(INTEGRATION_TESTS))"'),
    ("CI never runs the alone tests", CI,
     "      - run: make test-alone\n        env:\n"
     "          TEST_IDS: ${{ runner.temp }}/openfactory-test-ids/ran-alone.txt\n", ""),
    # 4. a test that asserts its own CPU time runs alone
    ("the map's timing test loses its mark", "tests/test_knowledge_derived_not_cached.py",
     "@pytest.mark.alone\ndef test_generating_is_fast_enough_to_do_every_time():",
     "def test_generating_is_fast_enough_to_do_every_time():"),
    ("the sweep does not see os.times()", TEST,
     'CPU_CLOCKS = {("os", "times"), ', "CPU_CLOCKS = {"),

    # 5. the real-daemon tests run one at a time
    ("a real-daemon module leaves the docker group", "tests/test_a_preview_runs_on_a_real_daemon.py",
     '    pytest.mark.xdist_group("docker"),\n', ""),
    ("the one real-daemon function leaves the docker group",
     "tests/test_a_preview_reaches_nothing_of_the_host.py",
     '@pytest.mark.xdist_group("docker")\ndef test_on_a_real_engine', "def test_on_a_real_engine"),
    ("the integration run ignores the groups", "Makefile",
     "	python -m pytest -q -n auto --dist loadgroup -m", "	python -m pytest -q -n auto -m"),
    ("the reader misses a gate on a single function", TEST,
     "                every = [*marks, *node.decorator_list]", "                every = marks"),

    ("the guard on CI's pytest stops following the Makefile", GUARD,
     "            lines += shown.stdout.splitlines()", "            pass",
     f"{GUARD}::test_ci_still_runs_the_command_this_guard_protects"),
]
