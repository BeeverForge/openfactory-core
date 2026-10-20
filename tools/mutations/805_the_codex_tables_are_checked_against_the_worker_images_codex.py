"""#805: the Codex tables are checked against the worker image's codex in CI, and never skip there.

`test_the_tables_are_the_pinned_binarys_own_help` was the only check of `EXEC_TAKES` /
`EXEC_RESUME_TAKES` against codex itself, and it skipped on every CI run: CI had no codex and the
test ran in the unit shards. It now builds the worker image's `toolbox` stage and reads that
codex's help, runs in the integration job (`slow`), and fails rather than skips under
`TEST_REQUIRE_DOCKER`. The rows below claim:

1-5. the guard's routing, held by the unit module that drives the guard with a fake docker:
     selected by the integration run (1, 9), a docker that cannot answer fails under the switch
     (2), a codex on the runner's `PATH` does not count there (3), the image's version is the pin
     (4), and the build is the worker Dockerfile's `toolbox` stage (5);
6-8. the tables against the REAL image: the issue's own cut and two more. These rows need a
     daemon. Run the plan where `docker version` answers and with `TEST_REQUIRE_DOCKER` unset:
     without a daemon the guard skips, the row prints `!!GREEN!!`, and that is loud, never a
     false red. The baseline of that node must have PASSED (`pytest -rs`, no SKIPPED line),
     since a skip exits 0 just as a pass does.
9.   CI's integration step keeps `TEST_REQUIRE_DOCKER: "1"` (the `env:` line, not the comment).
"""

TEST = "tests/test_the_codex_tables_are_checked_against_the_worker_images_codex_in_ci.py"

_GUARD_FILE = "tests/test_a_resumed_codex_job_is_handed_only_flags_exec_resume_takes.py"
_GUARD = f"{_GUARD_FILE}::test_the_tables_are_the_pinned_binarys_own_help"

MUTATIONS = [
    ("the guard loses its `slow` mark, so the unit shards select it and skip it again",
     _GUARD_FILE, "@pytest.mark.slow\n", ""),

    ("under TEST_REQUIRE_DOCKER a docker that cannot answer skips instead of failing",
     _GUARD_FILE, "        pytest.fail(why)\n", "        pytest.skip(why)\n"),

    ("under TEST_REQUIRE_DOCKER a codex on the runner's PATH is consulted before the image",
     _GUARD_FILE,
     "    if _docker_is_required() or (not pinned_bin and _a_daemon_answers()):\n"
     "        codex, from_image = _the_worker_images_codex(), True\n"
     "    elif binary := pinned_bin or shutil.which(\"codex\"):\n"
     "        codex, from_image = _a_local_codex(binary, tmp_path), False\n",
     "    if binary := pinned_bin or shutil.which(\"codex\"):\n"
     "        codex, from_image = _a_local_codex(binary, tmp_path), False\n"
     "    elif _docker_is_required() or _a_daemon_answers():\n"
     "        codex, from_image = _the_worker_images_codex(), True\n"),

    ("the image's codex at another version skips instead of failing",
     _GUARD_FILE, "                pytest.fail(message)\n",
     "                pytest.skip(message)\n"),

    ("the build drops `--target toolbox`, so it builds the whole worker image, not the stage",
     _GUARD_FILE, "\"--target\", TOOLBOX_STAGE, ", ""),

    ("the issue's own cut: `exec resume` is said to take `-s`, which 0.146.0 refuses with exit 2",
     _GUARD_FILE, "EXEC_RESUME_TAKES = _GLOBAL | {\"--last\": False",
     "EXEC_RESUME_TAKES = _GLOBAL | {\"-s\": True, \"--last\": False", _GUARD),

    ("`exec` is said not to take `--color`, which the image's codex prints",
     _GUARD_FILE, "    \"--color\": True,\n", "", _GUARD),

    ("the help reader drops short options, so the tables are compared against long options only",
     _GUARD_FILE, "            if short:\n                found[short] = takes\n", "", _GUARD),

    ("CI's integration step stops requiring docker, so a lost daemon would skip the guard there",
     ".github/workflows/ci.yml", "          TEST_REQUIRE_DOCKER: \"1\"\n", ""),
]
