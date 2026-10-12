"""CI runs the suite as parallel jobs, and proves that every collected test ran exactly once.

WHY. One job running all ~17,400 tests took 22–26 minutes on every pull request. The jobs that
replace it (`.github/workflows/ci.yml`) are cut by marker and by slice, and that is exactly where a
test slips through: a marker expression one job reads and the other does not, or a slice rule that
two processes compute differently. A test no job selected would leave the gate green over nothing.

THE RULES THIS FILE HOLDS:
  1. the slices of one selection (`--shard I/N`) hold every test exactly once, whatever process
     computes them, and an xdist run writes each test it started once (`--record-ids`);
  2. the proof (`scripts/every_test_ran_once.py`) fails on a test missing, doubled or unknown, and
     names it;
  3. CI wires it: the `test` job needs every other job and runs the proof; the unit job's slices
     are the matrix's; the unit, integration and alone runs select markers that split the suite
     without overlap;
  4. a test that asserts its own CPU time is marked `alone`, so CI runs it with no neighbours on
     its cores.

Driven as real pytest runs over a probe outside the tree, with this suite's conftest copied beside
it, as `test_the_suite_cannot_reach_a_live_engine.py` does: only pytest applies the hooks.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
import textwrap
from collections import Counter
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
SLICES = 3

PROBE = textwrap.dedent("""\
    import pytest


    @pytest.mark.parametrize("n", range(30))
    def test_one_of_many(n):
        assert n >= 0


    @pytest.mark.skip(reason="a skipped test still counts as started")
    def test_skipped():
        pass
""")


def _the_proof():
    spec = importlib.util.spec_from_file_location("every_test_ran_once",
                                                  ROOT / "scripts" / "every_test_ran_once.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ids(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    where = tmp_path_factory.mktemp("ci-slices")
    assert ROOT not in where.resolve().parents, "the probe is inside the tree under test"
    (where / "test_probe.py").write_text(PROBE, encoding="utf-8")
    (where / "conftest.py").write_text(
        (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"), encoding="utf-8")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "pytest", str(where / "test_probe.py"),
             "-c", str(ROOT / "pyproject.toml"), "-q", "-p", "no:cacheprovider", "--no-header",
             *args],
            capture_output=True, text=True, cwd=str(ROOT), timeout=300)

    run.dir = where
    return run


@pytest.fixture(scope="module")
def sliced(probe):
    collected = probe.dir / "collected.txt"
    done = probe("--collect-only", f"--record-ids={collected}")
    assert done.returncode == 0, done.stdout[-1500:]
    ran = []
    for index in range(1, SLICES + 1):
        path = probe.dir / f"ran-{index}.txt"
        done = probe(f"--shard={index}/{SLICES}", f"--record-ids={path}")
        assert done.returncode == 0, done.stdout[-1500:]
        ran.append(path)
    return collected, ran


# ── 1. the slices ───────────────────────────────────────────────────────────────────────────────

def test_the_slices_hold_every_collected_test_exactly_once(sliced):
    collected, ran = sliced
    every = [nodeid for path in ran for nodeid in _ids(path)]

    assert len(_ids(collected)) == 31, _ids(collected)
    assert Counter(every) == Counter(_ids(collected)), "a test fell between the slices, or in two"
    assert all(_ids(path) for path in ran), "a slice is empty: the rule does not spread the tests"


def test_a_skipped_test_counts_as_started(sliced):
    _, ran = sliced

    assert any(nodeid.endswith("::test_skipped") for path in ran for nodeid in _ids(path))


@pytest.mark.skipif(importlib.util.find_spec("xdist") is None, reason="pytest-xdist not installed")
def test_under_xdist_each_started_test_is_written_once(probe):
    """The workers run the hooks too: a recorder registered on them would write every test twice,
    and a slice rule salted per process would make the workers collect different suites."""
    path = probe.dir / "ran-xdist.txt"
    done = probe("-n", "2", f"--shard=1/{SLICES}", f"--record-ids={path}")
    assert done.returncode == 0, done.stdout[-1500:]
    alone = probe.dir / "ran-alone.txt"
    assert probe(f"--shard=1/{SLICES}", f"--record-ids={alone}").returncode == 0

    assert sorted(_ids(path)) == sorted(_ids(alone)), "xdist and one process ran different tests"
    assert len(_ids(path)) == len(set(_ids(path))), "a test was written twice under xdist"


def test_a_slice_that_does_not_exist_is_refused(probe):
    done = probe(f"--shard={SLICES + 1}/{SLICES}")

    assert done.returncode != 0
    assert "expected I/N" in done.stdout + done.stderr


# ── 2. the proof ────────────────────────────────────────────────────────────────────────────────

def test_the_proof_passes_the_slices_and_fails_what_is_missing_doubled_or_unknown(sliced, tmp_path,
                                                                                 capsys):
    collected, ran = sliced
    proof = _the_proof()
    assert proof.main([str(collected), *map(str, ran)]) == 0

    every = [nodeid for path in ran for nodeid in _ids(path)]
    for kind, lines in (("MISSING", every[1:]),
                        ("DOUBLED", [*every, every[0]]),
                        ("UNKNOWN", [*every, "tests/test_gone.py::test_not_collected"])):
        broken = tmp_path / f"{kind}.txt"
        broken.write_text("\n".join(lines) + "\n", encoding="utf-8")
        capsys.readouterr()

        assert proof.main([str(collected), str(broken)]) == 1, kind
        said = capsys.readouterr().err
        assert kind in said, said


def test_an_empty_collection_is_a_failure_not_a_pass(tmp_path):
    empty = tmp_path / "collected.txt"
    empty.write_text("", encoding="utf-8")

    assert _the_proof().main([str(empty), str(empty)]) == 1


# ── 3. CI wires it ──────────────────────────────────────────────────────────────────────────────

def _jobs() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]


def _runs(job: dict) -> list[str]:
    return [step.get("run", "") for step in job.get("steps", [])]


def _env_of(job: dict, command: str) -> dict:
    return next(step.get("env") or {} for step in job["steps"] if step.get("run") == command)


def test_the_job_named_test_needs_every_other_job_and_runs_the_proof():
    jobs = _jobs()

    assert set(jobs["test"]["needs"]) == set(jobs) - {"test"}, jobs["test"]["needs"]
    assert jobs["test"].get("if") == "always()", "a failed job would skip the proof"
    assert "make test-ran-once" in _runs(jobs["test"])
    assert "make test-collect" in _runs(jobs["lint"])
    assert _env_of(jobs["lint"], "make test-collect")["TEST_IDS"].endswith("/collected.txt")


def test_the_unit_slices_are_the_matrixs_and_each_job_records_what_it_ran():
    jobs = _jobs()
    unit = _env_of(jobs["unit"], "make test-unit")

    assert jobs["unit"]["strategy"]["matrix"]["shard"] == list(range(1, int(unit["TEST_SHARDS"]) + 1))
    assert jobs["unit"]["strategy"]["fail-fast"] is False
    for name, command in (("unit", "make test-unit"), ("integration", "make test-integration"),
                          ("integration", "make test-alone")):
        assert re.fullmatch(r"test-ids/ran-[\w${}. -]+\.txt", _env_of(jobs[name], command)["TEST_IDS"])


def _make_n(target: str) -> str:
    return subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True, text=True,
                          timeout=60).stdout


def test_the_unit_integration_and_alone_runs_split_the_suite_without_overlap():
    """One marker list per run, read by the others: a marker added to one side only would drop
    its tests from every job, or run them twice."""
    def expression(target: str) -> str:
        return re.search(r'-m "([^"]+)"', _make_n(target)).group(1)

    integration, unit = expression("test-integration"), expression("test-unit")
    alone = re.fullmatch(r"(\w+) and not \((.+)\)", expression("test-alone"))

    assert alone and alone.group(2) == integration, expression("test-alone")
    assert unit == f"not ({integration} or {alone.group(1)})", (unit, integration)
    assert "-p no:xdist" in _make_n("test-alone"), "the alone run has neighbours on its cores"


# ── 4. a test that asserts its own CPU time runs alone ─────────────────────────────────────────

#: The calls that read a process's own CPU time. Neighbours on the same cores inflate all of them.
CPU_CLOCKS = {("os", "times"), ("time", "process_time"), ("time", "thread_time"),
              ("resource", "getrusage")}


def _reads_cpu_time(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and isinstance(n.func.value, ast.Name)
               and (n.func.value.id, n.func.attr) in CPU_CLOCKS for n in ast.walk(node))


def _marked_alone(decorators: list[ast.expr]) -> bool:
    return any("alone" in ast.unparse(d) for d in decorators)


def test_every_test_that_asserts_its_own_cpu_time_is_marked_alone():
    unmarked = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_alone = any(isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets)
            and "alone" in ast.unparse(n.value) for n in tree.body)
        for node in tree.body:
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name.startswith("test_") and _reads_cpu_time(node)
                    and not (module_alone or _marked_alone(node.decorator_list))):
                unmarked.append(f"{path.relative_to(ROOT)}::{node.name}")

    assert not unmarked, (f"{unmarked} read their own CPU time beside xdist neighbours, where it "
                          f"is inflated: mark them `alone`")


def test_the_reader_sees_a_cpu_clock_and_a_mark():
    """Verify the verifier on the one test that carries both today."""
    tree = ast.parse((ROOT / "tests" / "test_knowledge_derived_not_cached.py").read_text())
    [timed] = [n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == "test_generating_is_fast_enough_to_do_every_time"]

    assert _reads_cpu_time(timed) and _marked_alone(timed.decorator_list)
