"""What a turn of the product role leaves on the worker's disk, turn after turn — and what it
costs in git (#369; ADR-0052 D16: "measured, not assumed").

`measure_the_mount.py` measures ONE turn against N sources. This measures the SAME product over
many turns, because what filled a worker's disk was never the size of a product: it was what each
turn left behind and nothing ever bounded. Every turn is a fresh `ProductModule` — the engine
makes one per message — with its context loaded through the documentation cache, `answer()` run
against a harness that only records the prompt, and the bytes under the repository cache counted
once per inode, in allocated blocks, the way `du` counts them.

Six regimes, each a real shape of a deployment:

  released        nothing moves upstream; the turn's view is released (the conversational path)
  window          as released, with the clock driven: every turn but the last inside one freshness
                  window (`OPENFACTORY_SOURCES_FRESH_SECONDS`), the last one after it (#369)
  leaked          nothing moves; the view is never released (the API paths, until the sweep)
  moving          a commit lands in every source AND in the context repository between turns —
                  the role writes to the context repository on every turn it records something
  nolink-moving   as moving, on a filesystem that cannot hardlink (`os.link` refused)
  nolink-leaked   as leaked, on such a filesystem

On the multi-repository fixture (one context repository, four sources) by default:

    .venv/bin/python tools/measure_a_turns_footprint.py                     # every regime, 25 turns
    .venv/bin/python tools/measure_a_turns_footprint.py moving --turns 40 --json out.json
    .venv/bin/python tools/measure_a_turns_footprint.py --tree /path/to/another/checkout
    .venv/bin/python tools/measure_a_turns_footprint.py window released --copies 10   # N = 40

`--tree` measures another checkout of this repository with the same bed, which is how a change
to the cache is compared with what it replaces. `--json` keeps every turn's numbers. `--copies K`
declares each of the fixture's four sources K times under new names, each with the module map the
fixture publishes for it, so the slope in N is measured and not argued. Every turn's seconds are
split into the three parts that grow with N: `sync` (bringing the sources up), `view` (composing
the workspace and linking the turn's own view of it) and `map` (checking each source's module map
against its code).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

REGIMES = ("released", "window", "leaked", "moving", "nolink-moving", "nolink-leaked")
#: Where the `window` regime's clock starts; every turn but the last is one second after the one
#: before it, and the last one an hour after the first.
T0 = 1_800_000_000.0

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "evaluation" / "harbourline"
FIXTURE_REPOS = {"harbourline": "source",
                 "harbourline-pricing": "sources/harbourline-pricing",
                 "harbourline-tracking": "sources/harbourline-tracking",
                 "harbourline-web": "sources/harbourline-web"}
#: One file per source that a move rewrites.
MOVES = {"harbourline": "harbourline/bookings.py",
         "harbourline-pricing": "pricing/freight.py",
         "harbourline-tracking": "tracking/eta.py",
         "harbourline-web": "src/quote.ts"}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})


def _repository(src: Path, dest: Path) -> Path:
    """`src` as a git repository at `dest`, one commit on `main`, serving partial clones."""
    shutil.copytree(src, dest)
    _git(dest, "init", "-q", "-b", "main")
    for key, value in (("user.name", "measure"), ("user.email", "measure@example.invalid"),
                       ("commit.gpgsign", "false"), ("uploadpack.allowFilter", "true"),
                       ("uploadpack.allowAnySHA1InWant", "true")):
        _git(dest, "config", key, value)
    _git(dest, "add", "-A")
    _git(dest, "commit", "-qm", "measure")
    return dest


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


def disk(root: Path) -> dict:
    """`unique` is allocated bytes with each inode counted once — what the disk really holds;
    `files` and `dirs` are entries, which cost directory blocks even when every file is a link."""
    unique = files = dirs = 0
    seen: set[tuple[int, int]] = set()
    for where, dnames, fnames in os.walk(root):
        dirs += len(dnames)
        for name in fnames:
            try:
                st = os.lstat(os.path.join(where, name))
            except OSError:
                continue
            files += 1
            if (st.st_dev, st.st_ino) not in seen:
                seen.add((st.st_dev, st.st_ino))
                unique += st.st_blocks * 512
    return {"unique": unique, "files": files, "dirs": dirs}


class _Checkouts:
    """The loader's cache, answering the context repository's key with the made-up one."""

    def __init__(self, context: Path) -> None:
        from openfactory.runtime.repo_cache import RepoCache

        self._cache, self._context = RepoCache(), context

    def sync(self, key: str, clone_url: str, base_branch: str = ""):
        from openfactory.product.loader import DOCS_CACHE_SUFFIX

        return self._cache.sync(key, str(self._context) if key.endswith(DOCS_CACHE_SUFFIX)
                                else clone_url, base_branch)


class _Recording:
    """A harness that only records the prompt."""

    name = "recording"

    def ask(self, *, sandbox, workspace, prompt, phase="ask"):
        from openfactory.contracts import AgentRunResult

        return AgentRunResult(ok=True, summary="ok")


def _count_git(counter: Counter):
    """`subprocess.run`, counting every git subcommand it starts."""
    real = subprocess.run

    def counting(args, *a, **kw):
        if isinstance(args, (list, tuple)) and args and Path(str(args[0])).name == "git":
            rest = [x for x in args[1:] if not str(x).startswith("-")]
            if len(args) > 1 and args[1] == "-C":
                rest = rest[1:]
            counter[rest[0] if rest else "?"] += 1
        return real(args, *a, **kw)

    return counting


def _copied(made: Path, context: Path, copies: int) -> dict[str, Path]:
    """Each fixture source declared `copies` times: the extra ones as `<name>-c<k>`, their own
    repositories, and the module map the fixture publishes for the original copied beside it."""
    extra: dict[str, Path] = {}
    for k in range(2, copies + 1):
        for name, rel in FIXTURE_REPOS.items():
            twin = f"{name}-c{k}"
            extra[twin] = _repository(FIXTURE / rel, made / twin)
            bundle = context / ".okf" / "repos" / name
            if bundle.is_dir():
                shutil.copytree(bundle, context / ".okf" / "repos" / twin)
    if extra:
        manifest = context / ".openfactory" / "product.yaml"
        manifest.write_text(manifest.read_text().rstrip("\n") + "\n"
                            + "".join(f"  - {twin}\n" for twin in extra))
        _commit(context, f"{len(extra)} more sources")
    return extra


#: The seconds of the current turn, by part. One dict for the process, because the wrappers are put
#: in once: a second regime in the same run would otherwise time every call twice.
SPENT = {"sync": 0.0, "view": 0.0, "map": 0.0}


def _timed(owner, attr: str, part: str) -> None:
    """`owner.attr`, adding the seconds each call spends to `SPENT[part]`."""
    real = getattr(owner, attr)
    if getattr(real, "_measured", False):
        return

    def timing(*a, **kw):
        began = time.monotonic()
        try:
            return real(*a, **kw)
        finally:
            SPENT[part] += time.monotonic() - began

    timing._measured = True
    setattr(owner, attr, timing)


def measure(regime: str, turns: int, copies: int = 1) -> list[dict]:
    """Each turn's seconds, git processes and bytes, for one regime, in a directory of its own."""
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.product import engine, workspace
    from openfactory.product import module as product_module
    from openfactory.product import sources as product_sources
    from openfactory.product.loader import load_product_context
    from openfactory.runtime import repo_cache

    work = Path(tempfile.mkdtemp(prefix=f"footprint-{regime}-"))
    cache = work / "cache"
    os.environ.update({"OPENFACTORY_REPO_CACHE": str(cache), "OPENFACTORY_METRICS_SINK": "null",
                       "OPENFACTORY_BOARD_DB": str(work / "board.db"),
                       "OPENFACTORY_REGISTRY": str(work / "registry.yaml"),
                       "OPENFACTORY_LOG_DIR": str(work / "logs")})
    made = work / "repositories"
    repos = {n: _repository(FIXTURE / rel, made / n) for n, rel in FIXTURE_REPOS.items()}
    context = _repository(FIXTURE / "context", made / "context")
    repos.update(_copied(made, context, copies))
    urls = {n: f"file://{p}" for n, p in repos.items()}
    local = {"kind": "local", "repo": "harbourline", "options": {}}
    project = Project(name="harbourline", repo_path=str(repos["harbourline"]),
                      tracker=ProviderRef(**local), forge=ProviderRef(**local),
                      ci=ProviderRef(kind="none", repo="harbourline", options={}),
                      product=ProductConfig(docs_repo="harbourline-context", admins=["ines"]))
    product_module.ProductModule._clone_url = lambda self, repo: urls[repo]
    product_module._the_read_model = lambda module, root: {}   # the read model is not the mount
    spent = SPENT
    _timed(product_module.ProductModule, "_source_checkouts", "sync")
    _timed(workspace, "compose", "view")
    _timed(workspace, "turn_view", "view")
    _timed(product_sources, "module_map", "map")    # not `mounts()`: it composes first
    clock = [T0]
    real_now = getattr(repo_cache, "_now", None)    # a tree without a window has none
    if regime == "window":
        repo_cache._now = lambda: clock[0]
    counter: Counter = Counter()
    subprocess.run = _count_git(counter)
    if regime.startswith("nolink"):
        def refused(*a, **kw):
            raise OSError(1, "Operation not permitted")
        os.link = refused
    rows = []
    try:
        for turn in range(1, turns + 1):
            if "moving" in regime:
                for name, path in repos.items():
                    file = path / MOVES[name]
                    file.write_text(file.read_text() + f"\n# turn {turn}\n")
                    _commit(path, f"turn {turn}")
                (context / "requirements" / "moving.md").write_text(f"# moving\n\nturn {turn}\n")
                _commit(context, f"turn {turn}")
            counter.clear()
            spent.update(sync=0.0, view=0.0, map=0.0)
            clock[0] = T0 + (turn - 1 if turn < turns else 3600)
            began = time.monotonic()
            ctx = load_product_context(project, cache=_Checkouts(context))
            module = product_module.ProductModule(project, context=ctx, agent=_Recording())
            result = module.answer("where is the freight price computed?")
            if "leaked" not in regime:
                engine.release(module)
            seconds = time.monotonic() - began
            row = {"turn": turn, "ok": bool(getattr(result, "ok", False)),
                   "seconds": round(seconds, 3), "git": dict(counter),
                   "sources": len(repos), "split": {k: round(v, 3) for k, v in spent.items()},
                   "git_total": sum(counter.values()),
                   "network": counter["ls-remote"] + counter["fetch"] + counter["clone"],
                   "cache": disk(cache),
                   "trash": disk(cache / ".trash"), "masters": disk(cache / ".masters"),
                   "views": len([p for p in (cache / "harbourline-turns").glob("turn-*")])
                   if (cache / "harbourline-turns").is_dir() else 0}
            rows.append(row)
            print(f"{regime:14s} turn {turn:3d}  {seconds:6.2f}s  (sync {spent['sync']:5.2f}  "
                  f"view {spent['view']:5.2f}  map {spent['map']:5.2f})  "
                  f"git {row['git_total']:3d}  "
                  f"network {row['network']:2d}  cache {row['cache']['unique'] / 1e6:8.2f} MB  "
                  f"trash {row['trash']['unique'] / 1e6:7.2f} MB  views {row['views']}",
                  flush=True)
    finally:
        if real_now is not None:
            repo_cache._now = real_now
        shutil.rmtree(work, ignore_errors=True)
    return rows


def _svg_lines(title: str, unit: str, series: dict[str, list[tuple[int, float]]],
               colours: dict[str, str]) -> str:
    """One line chart, hand-drawn SVG: turns along, `unit` up, one line per series."""
    w, h, left, top, right, bottom = 720, 360, 64, 36, 24, 44
    xs = [x for pts in series.values() for x, _ in pts]
    ys = [y for pts in series.values() for _, y in pts]
    x0, x1, y1 = min(xs), max(xs), max(ys) * 1.08 or 1.0

    def px(x: float) -> float:
        return left + (x - x0) / max(x1 - x0, 1) * (w - left - right)

    def py(y: float) -> float:
        return top + (h - top - bottom) - y / y1 * (h - top - bottom)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}" font-family="sans-serif" font-size="12">',
           f'<rect width="{w}" height="{h}" fill="white"/>',
           f'<text x="{left}" y="20" font-size="14" font-weight="bold">{title}</text>']
    for i in range(5):
        y = y1 * i / 4
        out.append(f'<line x1="{left}" y1="{py(y):.1f}" x2="{w - right}" y2="{py(y):.1f}" '
                   f'stroke="#ddd"/>')
        out.append(f'<text x="{left - 6}" y="{py(y) + 4:.1f}" text-anchor="end">{y:.1f}</text>')
    for x in range(x0, x1 + 1, max((x1 - x0) // 6, 1)):
        out.append(f'<text x="{px(x):.1f}" y="{h - bottom + 16}" text-anchor="middle">{x}</text>')
    out.append(f'<text x="{(left + w - right) / 2:.0f}" y="{h - 8}" text-anchor="middle">turn'
               f'</text>')
    out.append(f'<text x="14" y="{(top + h - bottom) / 2:.0f}" text-anchor="middle" '
               f'transform="rotate(-90 14 {(top + h - bottom) / 2:.0f})">{unit}</text>')
    legend_y = top + 8
    for name, pts in series.items():
        path = " ".join(f"{'M' if i == 0 else 'L'}{px(x):.1f},{py(y):.1f}"
                        for i, (x, y) in enumerate(pts))
        out.append(f'<path d="{path}" fill="none" stroke="{colours[name]}" stroke-width="2"/>')
        out.append(f'<line x1="{w - right - 190}" y1="{legend_y}" x2="{w - right - 170}" '
                   f'y2="{legend_y}" stroke="{colours[name]}" stroke-width="3"/>')
        out.append(f'<text x="{w - right - 164}" y="{legend_y + 4}">{name}</text>')
        legend_y += 16
    out.append("</svg>")
    return "\n".join(out)


def chart(before: dict, after: dict, into: Path) -> list[Path]:
    """The two runs side by side: bytes under the cache per turn for every regime, and what an
    unmoved turn costs in git. `before`/`after` are what `--json` wrote."""
    into.mkdir(parents=True, exist_ok=True)
    palette = {"released": "#2a9d8f", "window": "#264653", "leaked": "#e9c46a", "moving": "#e76f51",
               "nolink-moving": "#9b2226", "nolink-leaked": "#8a5a44"}
    written = []
    for label, run in (("before", before), ("after", after)):
        series = {r: [(row["turn"], row["cache"]["unique"] / 1e6) for row in rows]
                  for r, rows in run.items()}
        top = max(y for pts in series.values() for _, y in pts)
        path = into / f"disk-per-turn-{label}.svg"
        path.write_text(_svg_lines(f"Bytes under the repository cache, per turn — {label} "
                                   f"(peak {top:.1f} MB)", "MB on disk", series, palette))
        written.append(path)
    git_series = {}
    for label, run in (("before", before), ("after", after)):
        for regime in ("released", "moving"):
            rows = run.get(regime) or []
            git_series[f"{regime}, {label}"] = [(row["turn"], row["git_total"]) for row in rows]
    colours = {"released, before": "#e76f51", "released, after": "#2a9d8f",
               "moving, before": "#9b2226", "moving, after": "#264653"}
    path = into / "git-per-turn.svg"
    path.write_text(_svg_lines("git processes started per turn (four sources and the "
                               "documentation)", "processes", git_series, colours))
    written.append(path)
    return written


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("regimes", nargs="*", metavar="REGIME",
                        help=f"one or more of {', '.join(REGIMES)} (default: every one)")
    parser.add_argument("--turns", type=int, default=25)
    parser.add_argument("--json", metavar="FILE", help="keep every turn's numbers here")
    parser.add_argument("--copies", type=int, default=1, metavar="K",
                        help="declare each of the fixture's four sources K times (N = 4K)")
    parser.add_argument("--tree", metavar="DIR",
                        help="measure this checkout of the repository instead of this one")
    parser.add_argument("--chart", nargs=2, metavar=("BEFORE.json", "AFTER.json"),
                        help="draw two `--json` runs side by side instead of measuring")
    parser.add_argument("--into", metavar="DIR", default=".",
                        help="where `--chart` writes its SVG files")
    args = parser.parse_args(argv)
    if args.chart:
        before, after = (json.loads(Path(p).read_text()) for p in args.chart)
        for path in chart(before, after, Path(args.into)):
            print(f"wrote {path}")
        return 0
    unknown = [r for r in args.regimes if r not in REGIMES]
    if unknown:
        parser.error(f"not a regime: {', '.join(unknown)} — one of {', '.join(REGIMES)}")
    sys.path.insert(0, str(Path(args.tree).resolve() if args.tree else ROOT))
    out = {}
    for regime in args.regimes or list(REGIMES):
        rows = measure(regime, args.turns, args.copies)
        out[regime] = rows
        first, last = rows[0], rows[-1]
        grew = (last["cache"]["unique"] - first["cache"]["unique"]) / max(len(rows) - 1, 1)
        print(f"\n{regime}: {first['cache']['unique'] / 1e6:.2f} MB after the first turn, "
              f"{last['cache']['unique'] / 1e6:.2f} MB after turn {last['turn']} — "
              f"{grew / 1e3:.0f} KB per turn; an unmoved turn starts {last['git_total']} git "
              f"processes, {last['network']} of them to a forge\n")
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
