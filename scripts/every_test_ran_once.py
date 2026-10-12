"""Every test the suite collects was started exactly once across CI's parallel jobs.

    python scripts/every_test_ran_once.py <collected ids> <ran ids>...

CI runs the suite as jobs side by side (`.github/workflows/ci.yml`): the tests that start their
own durable engine or need Docker, and the rest in slices (`make test-integration`,
`make test-unit`). A test that no job selected would leave the gate green over nothing, and a
marker expression or a slice rule is exactly where one slips through. So the lint job writes the
whole collection (`make test-collect`), every test job writes the node ids it started
(`--record-ids`, one line per setup report), and this compares them:

- MISSING: collected, and started by no job;
- DOUBLED: started by more than one job, or twice in one;
- UNKNOWN: started, and not in the collection, so the jobs did not collect the same suite.

Any of the three exits 1 and names the tests. Stdlib only: the job that runs this installs nothing.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

#: How many of each kind are named; the count is always given whole.
SHOWN = 20


def _ids(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def compare(collected: list[str], ran: list[str]) -> dict[str, list[str]]:
    """The tests missing, doubled and unknown, each sorted; all three empty when every collected
    test ran exactly once."""
    wanted = set(collected)
    counts = Counter(ran)
    return {
        "missing": sorted(wanted - counts.keys()),
        "doubled": sorted(nodeid for nodeid, n in counts.items() if n > 1),
        "unknown": sorted(counts.keys() - wanted),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    collected = _ids(Path(argv[0]))
    ran = [nodeid for path in argv[1:] for nodeid in _ids(Path(path))]
    if not collected:
        print(f"{argv[0]} names no test: the collection was not written", file=sys.stderr)
        return 1
    found = compare(collected, ran)
    if not any(found.values()):
        print(f"every one of the {len(collected)} collected tests ran exactly once, "
              f"across {len(argv) - 1} job(s)")
        return 0
    for kind, ids in found.items():
        if ids:
            print(f"{kind.upper()}: {len(ids)} test(s)", file=sys.stderr)
            for nodeid in ids[:SHOWN]:
                print(f"  {nodeid}", file=sys.stderr)
            if len(ids) > SHOWN:
                print(f"  … and {len(ids) - SHOWN} more", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
