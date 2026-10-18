# What a turn costs at N sources, before and after the freshness window (#369)

Measured with [`tools/measure_a_turns_footprint.py`](../../../tools/measure_a_turns_footprint.py)
on the four-source fixture (`tests/fixtures/evaluation/harbourline`), at N = 4 and at N = 40
(`--copies 10`: each source declared ten times under new names, each copy with the module map the
fixture publishes for the original), 10 turns per regime. Nothing moves upstream between turns.
In the `window` regime the clock is driven: turns 1 to 9 are one second apart, inside one window,
and turn 10 is an hour after turn 1. The runs:

- *before*: `main` at `d29b94a`;
- *after*: this branch with `OPENFACTORY_SOURCES_FRESH_SECONDS` unset (60 s);
- *after, `=0`*: this branch with the window turned off.

git 2.43.0, Linux, sources served over `file://` with filters allowed (so the clones are partial,
as against a real forge). The machine's load average was 8 to 13 during the runs, because another
suite was running on it. The seconds are medians of turns 2 to 9, and they are noisy at the
millisecond scale. The counts of git processes are exact.

    .venv/bin/python tools/measure_a_turns_footprint.py window released --turns 10 --copies 1  \
        --tree <main checkout> --json before-n4.json
    .venv/bin/python tools/measure_a_turns_footprint.py window released --turns 10 --copies 10 \
        --json after-n40.json
    OPENFACTORY_SOURCES_FRESH_SECONDS=0 .venv/bin/python tools/measure_a_turns_footprint.py \
        window released --turns 10 --copies 10 --json after-off-n40.json

The `--json` files beside this page hold every turn's numbers.

## A turn inside the window, nothing moved

| | N = 4 before | N = 4 after | N = 40 before | N = 40 after |
|---|---:|---:|---:|---:|
| git processes started | 52 | **20** | 439 | **119** |
| round trips to a forge (`ls-remote` + `fetch` + `clone`) | 6 | **2** | 42 | **2** |
| of which `ls-remote` to a source | 4 | **0** | 40 | **0** |
| seconds bringing the sources up (`sync`) | 0.013 | 0.002 | 0.099 | 0.009 |
| seconds composing and linking the turn's view (`view`) | 0.016 | 0.015 | 0.136 | 0.132 |
| seconds checking the module maps (`map`) | 0.009 | 0.009 | 0.090 | 0.089 |
| seconds per turn, the whole `answer()` with a stub model | 0.07 | 0.06 | 0.40 | 0.30 |

The two round trips left are the context repository's (`RepoCache`, one key per product). It is
not windowed, because the role's own writes land there and must be read back on the next turn.

With the window off (`=0`), and on the first turn after the window, the branch is the same as
main: 52 processes and 6 round trips at N = 4, 439 and 42 at N = 40. The first turn of all clones
every source in both trees: 49 processes and 10 round trips at N = 4, 463 and 82 at N = 40.

## What the window does not bound

Inside the window, these still grow with N on every turn:

- **The view** (`workspace.compose` and `workspace.turn_view`): 0.132 s at N = 40, 3.3 ms per
  source. Compose runs `rev-parse` on every source (83 at N = 40 against 11 at N = 4) and
  `status` on most (31 against 4). `turn_view` hard-links every file of every source into the
  turn's own view.
- **The map check** (`sources.module_map`, which calls `is_trustworthy`): 0.089 s at N = 40,
  2.2 ms per source. It reads every file each map was drawn from.

Over `file://` a round trip costs almost nothing, so here the window saves 0.09 s of a 0.40 s turn
at N = 40. Against a real forge each `ls-remote` is a network round trip, eight at a time, and that
was not measured here. The count it removes is exact: N per turn becomes N per window.
