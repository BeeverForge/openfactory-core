"""RepoCache — the worker's per-project read-only checkout (ADR-0013 D6).

The long-lived worker keeps ONE cached clone per project for cheap read-only work (the
pre-flight sizing gate's code layer). Clone on first touch; per use `fetch` + `reset --hard
origin/<base>` + `clean -fdx` — reset, never pull: a cache must be IDENTICAL to base, not
merged into. A corrupt cache is deleted and recloned; a reclone failure returns None so the
caller degrades (text-only gate) instead of blocking. The executor's fresh isolated clone in
Fargate is untouched. Callers read the served tree — except the worktree box, which adds a job's
worktree to it (below).

THE SERVED TREE IS NEVER MUTATED IN PLACE. The per-key lock covers sync-vs-sync, but a READER
(the baseline survey, a conversational agent behind the view symlink) holds the returned path for
minutes, and callers have no way to say "still reading". Resetting or recloning the served path
under such a reader handed it a torn half-old/half-new tree — a survey describing code that never
existed in any commit — or vanishing files mid-`rmtree`. So all git mutation happens on a hidden
MASTER checkout, and the path callers receive is a hardlink snapshot of it, republished by atomic
rename only when the master's commit moved (or the snapshot was dirtied/corrupted). A displaced
snapshot is parked for a grace period before deletion, so a reader that anchored itself (open fd,
cwd) keeps a complete, self-consistent tree for the whole window; a reader resolving by name flips
between complete trees, never through a mid-mutation state.

A JOB'S WORKTREE LIVES IN THE SERVED `.git`, SO A SWAP WAITS FOR IT (#747). On the worktree box a
project registered by clone URL gets this served checkout as its repository, and `prepare` runs
`git worktree add` in it: the job's admin directory is `<served>/.git/worktrees/<name>`. A swap
moved that into the trash, and every git command in the job then exited 128, `fatal: not a git
repository: <root>/<key>/.git/worktrees/<name>`, its push included (82500f9, git 2.43.0). So the
box marks the worktree it adds (`gitworktrees.mark_as_job`), and a sync that would replace the
served tree keeps it as it is while a marked worktree still stands on disk, saying so as
`OPENFACTORY_CACHE_HELD`. Git deletes the marker with the admin directory on `worktree remove` and
`prune`, and a marker older than a day (`gitworktrees.JOB_MARKER_MAX_AGE`) stops holding, said as
`OPENFACTORY_CACHE_HOLD_EXPIRED`. A held key is served at its old commit until then.

THE CREDENTIAL NEVER RESTS IN THE CHECKOUT. `git clone <url-with-token>` persists that URL in
`.git/config`, and agents DO run over this cache — the pre-flight sizer explores it. A sizer reads
ticket text, which anyone able to file an issue can write, so a ticket instructing it to read
`.git/config` and repeat what it finds would exfiltrate a live App token into a public comment. So
`origin` is rewritten to the tokenless URL immediately after cloning, and every later fetch passes
the credentialed URL as an argument instead — which git does not persist. (The Slack bot already
scrubbed for exactly this reason; the cache had not.) Snapshots hardlink the master's config, so
they inherit the scrubbed remote.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from openfactory.adapters import gitworktrees
from openfactory.util.filelock import FileLock

#: WARNINGS, NOT `print`. These two lines are the cache degrading, and they used to go to
#: stdout — so they landed ABOVE `openfactory doctor`'s table, in the middle of a command
#: whose whole contract is one line per check with its remedy, and no logger setting could
#: quiet them (pilot, 2026-08-14). Through logging they stay visible in the worker (an
#: unconfigured logger still prints WARNING to stderr) and obey the diagnostic that owns
#: the screen.
log = logging.getLogger("openfactory.repo_cache")

#: Where checkouts live. `/tmp` was the original and it is the wrong default for a container: the
#: tree is lost on every restart, so a deploy costs a full re-clone of every client repository.
#: `OPENFACTORY_REPO_CACHE` lets a deployment put it on the volume that survives, beside the
#: registry.
#: Where checkouts live when a caller does not say. READ AT CALL TIME, never frozen at import
#: (#185) — this module-level `Path(os.environ.get(...))` was evaluated once, when the module was
#: first imported, so a deployment that sets `OPENFACTORY_REPO_CACHE` after that point silently
#: got the default. It is the shape `box_prove.PROOF_DIR` is filed under in #163's notes, and
#: this codebase names it a defect in its own words.
#:
#: MEASURED COST, and it is not hypothetical config hygiene. Every caller that constructs
#: `RepoCache()` without a root shares ONE directory, so a parallel test run has several workers
#: syncing different repositories into the same tree, swapping it under each other. The failure
#: surfaces as `pre-flight did not size (clone: could not reach the repo…) — proceeding UNSIZED`
#: in whichever test lost the race, which is indistinguishable from the live #37 bug the offline
#: harness exists to catch. It cost most of a day of intermittency wearing two different masks.
_FALLBACK_ROOT = "/tmp/openfactory-repo-cache"


def default_root() -> Path:
    """The cache root this process should use, asked now rather than at import."""
    return Path(os.environ.get("OPENFACTORY_REPO_CACHE") or _FALLBACK_ROOT)
_GIT_TIMEOUT = 300

#: How long a displaced snapshot stays on disk after being swapped out. This is the window a
#: reader has to finish with a tree it was handed before a newer sync replaced it. Longer than
#: any survey the product role runs; short enough that the parked trees (hardlinks — metadata,
#: not content) never pile up. Bounded by upstream commit rate times this window.
_TRASH_GRACE_SECONDS = 30 * 60

#: How many displaced snapshots of ONE key may wait out their grace at once — the newest ones; an
#: older one goes the moment a newer is parked. The grace bounds the trash by TIME, and time is no
#: bound at all for a key that moves faster than the grace passes: a product's context repository
#: moves on every turn the role writes to, and each of N sources moves on its own. Measured on the
#: four-source fixture with every source moving once per turn (#369): 195 parked trees after 40
#: turns, 432 KB per turn with hardlinks and 2.8 MB per turn without — on a 1.3 MB working set.
#: Two, not one: a reader on a snapshot loses it only when the key moves twice more inside its
#: window, which is the same promise the grace makes for a key that moves twice in half an hour.
_KEEP_DISPLACED = 2
#: What separates a key from its slot's suffix in the trash. Not `-`: a key ends in a repository's
#: name, which may itself end in eight hex characters, and the bound above counts by key.
_SLOT_SEP = "~"
#: The roots this process has already said cannot hardlink, so the warning is one line per root.
_LINKLESS_ROOTS: set[str] = set()
#: Where a sparse master remembers what its cone left out, so an unmoved turn can say it without
#: listing the tree again.
_LEFT_OUT_FILE = "openfactory-left-out"

_MASTERS_DIRNAME = ".masters"
_STAGING_DIRNAME = ".staging"
_TRASH_DIRNAME = ".trash"
_LOCKS_DIRNAME = ".locks"
#: Where a sparse key remembers when it was last brought up, for which branch and over which
#: commit: the freshness window of `SparseRepoCache` (#369). Beside the locks, so every process on
#: the root reads it.
_FRESH_DIRNAME = ".fresh"


def _now() -> float:
    """The clock the freshness window reads. The WALL clock, not a monotonic one: the stamp is read
    by other processes on the same root and outlives a restart, and a monotonic reading means
    nothing outside the process that took it."""
    return time.time()

#: How long a sync waits for a key another thread or process is changing. A holder's git commands
#: are each bounded by `_GIT_TIMEOUT`, and a holder that dies lets go with it (the kernel releases
#: a `flock`), so this is reached only behind a holder that hung outside git. The caller then
#: degrades, as for any sync that returns None, instead of waiting for ever.
_LOCK_WAIT_SECONDS = 30 * 60


def _key_lock(root: Path, key: str) -> FileLock:
    """The lock on one key of one cache root, held by every thread and every PROCESS changing it.

    IT WAS A `threading.Lock`, written for "one worker process owns the cache dir" (#656). On one
    machine the panel and the worker are two processes that fall back to the same root, and
    journey 0 measured them syncing one key at once: one `rmtree`-ed and re-cloned the master the
    other was resetting, git said "already exists and is not an empty directory", and every fresh
    project got an impediment card. A `flock` on a file beside the checkouts is held across
    processes, and across the containers that share the volume; the thread lock in front of it
    still queues one process's threads (`util/filelock.py`). Per key, so a product's sources still
    sync at once."""
    return FileLock(Path(root) / _LOCKS_DIRNAME / f"{key}.lock")


def _scrub(text: str) -> str:
    """A token must never reach a log line — the whole point of an error string is to be pasted
    somewhere."""
    return re.sub(r"(https://)[^@/\s]+@", r"\1***@", text or "")


def _scrub_remote(path: Path, clone_url: str) -> None:
    """Rewrite `origin` to the tokenless URL. Idempotent and best-effort: failing to scrub leaves a
    short-lived repo-scoped token on the worker's disk, which is bad, but failing the sync over it
    would take the sizing gate down, which is worse."""
    public = re.sub(r"(https://)[^@/\s]+@", r"\1", clone_url or "")
    if public and public != clone_url:
        _git(["remote", "set-url", "origin", public], cwd=path)


def _git(args: list[str], cwd: Path | None = None,
         env: dict[str, str] | None = None) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       timeout=_GIT_TIMEOUT, env={**os.environ, **env} if env else None)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _head(path: Path) -> str:
    rc, out = _git(["rev-parse", "HEAD"], cwd=path)
    return out.strip() if rc == 0 else ""


def _head_as_file(path: Path) -> str:
    """The commit `path`'s HEAD stands on, read from `.git` as files — no git process — or `""`
    when it cannot be read that way (no checkout, a ref format this does not know). `""` is never
    a commit, so a caller comparing two of them never matches on it.

    One symbolic level, as `checkout -B` and `clone --branch` leave HEAD: `ref: refs/heads/<b>`,
    the ref loose under `.git/` or listed in `packed-refs`."""
    git_dir = path / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head if _is_object_name(head) else ""
        ref = head[len("ref: "):].strip()
        if not ref.startswith("refs/") or ".." in ref.split("/"):
            return ""
        try:
            loose = (git_dir / ref).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            loose = ""
        if loose:
            return loose if _is_object_name(loose) else ""
        for line in (git_dir / "packed-refs").read_text(encoding="utf-8").splitlines():
            name, _, listed = line.partition(" ")
            if listed.strip() == ref and _is_object_name(name):
                return name
    except OSError:
        pass
    return ""


def _is_object_name(text: str) -> bool:
    return len(text) in (40, 64) and all(c in "0123456789abcdef" for c in text)


def _worktree_dirty(path: Path) -> bool:
    rc, out = _git(["status", "--porcelain"], cwd=path)
    return rc != 0 or bool(out.strip())


def remote_default_branch(clone_url: str) -> str:
    """Which branch the REMOTE points HEAD at, or `""` — asked without cloning anything.

    `git ls-remote --symref <url> HEAD` transfers no objects: it is a ref advertisement, so this
    costs a round trip and nothing else. That matters because it runs on the hot path — the
    preflight asks per ticket.

    IT EXISTS BECAUSE THE CACHE IS NOT THE REPOSITORY. `sync("")` used to resolve "nobody said"
    against the EXISTING checkout, so the promise its callers were written against — "let the
    clone land where the repository points" — held only on the very first clone. Afterwards a
    long-lived worker pinned whatever it had happened to land on, and a client who moved their
    default from `main` to `develop` was served the abandoned branch for ever, silently, with the
    tree looking perfectly healthy. Found by adversarial review, 2026-08-20.

    `""` ON ANY TROUBLE, and the caller falls back to what it already has: an unreachable remote
    must not be the reason a working checkout is thrown away.
    """
    rc, out = _git(["ls-remote", "--symref", clone_url, "HEAD"])
    if rc != 0:
        return ""
    return _symref_branch(out)


def _symref_branch(out: str) -> str:
    """The branch a `ls-remote --symref … HEAD` answer names, or `""`."""
    for line in (out or "").splitlines():
        # `ref: refs/heads/develop\tHEAD`
        if line.startswith("ref:") and "refs/heads/" in line:
            return line.split("refs/heads/", 1)[1].split()[0].strip()
    return ""


def current_branch(checkout) -> str:
    """The branch a checkout is on, or `""` — never a guess.

    `""` for an absent tree, a corrupt one, and for a detached HEAD, which git reports as the
    literal string `HEAD`. Returning that would build the refspec `refs/heads/HEAD`, which fetches
    nothing and resets to nothing.
    """
    at = Path(checkout)          # a caller may hold a str — this is asked of paths from four
    if not (at / ".git").exists():   # modules and one of them stores them as text
        return ""
    rc, out = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=at)
    named = (out or "").strip().splitlines()[0].strip() if out else ""
    return named if (rc == 0 and named and named != "HEAD") else ""


def _one_reason(exc: OSError) -> str:
    """ONE reason a hardlink failed, for a log line. `copytree` raises `shutil.Error` carrying one
    `(src, dst, reason)` per file it could not link and no `strerror`, so `str(exc)` grew with the
    tree — 783,486 characters for 2,000 files, once, when the log most needs to be readable
    (review of #372). The first reason, and how many more there were."""
    failures = exc.args[0] if isinstance(exc, shutil.Error) and exc.args else None
    if isinstance(failures, list) and failures:
        first = failures[0]
        reason = first[2] if isinstance(first, tuple) and len(first) > 2 else first
        more = f", and {len(failures) - 1} more like it" if len(failures) > 1 else ""
        return f"{str(reason)[:200]}{more}"
    return str(getattr(exc, "strerror", None) or exc)[:200]


class RepoCache:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else default_root()
        #: whether the last `_needs_publish` kept the served tree for a running job's worktree
        self.held = False

    def sync(self, project: str, clone_url: str, base_branch: str = "") -> Path | None:
        """Return a checkout of `project` reset hard to origin/<base>, or None when the repo
        can't be made available (caller degrades to text-only). Never raises.

        `base_branch=""` MEANS "WHATEVER THIS REPOSITORY'S DEFAULT IS" — which is what a caller
        that does not know should ask for, and what neither of this method's callers could ask
        before. Both passed the literal `main`: a client on `master`, `develop` or `trunk` got a
        `--branch main` that names nothing, the clone failed, and the caller degraded with a
        message about reachability. `clone_for_proposal` already had this parameter and says the
        same thing; the cache did not, so the two answers to one question disagreed.

        The returned path is STABLE across syncs, and its content is only ever replaced by an
        atomic swap — a caller still reading the tree a previous sync returned is never reset,
        cleaned, or deleted underneath. And no swap happens while a running job's worktree stands
        on the served tree (`_needs_publish`): the tree is then returned at its old commit.

        `project` is only a cache key, so one project may keep several checkouts under distinct
        keys (its code, its documentation repo) without them colliding."""
        try:
            with _key_lock(self.root, project).held(timeout=_LOCK_WAIT_SECONDS):
                try:
                    return self._sync(project, clone_url, base_branch)
                finally:
                    # WHETHER OR NOT THIS SYNC SUCCEEDED. The purge used to run after a successful
                    # publish only, so a forge that stopped answering — or a disk that had filled
                    # with the very trees this purges — stopped every purge with it: the cache
                    # could fill and then could not empty (#369).
                    self._purge_displaced()
        except Exception as exc:  # noqa: BLE001 — cache trouble must never block the pipeline
            log.warning("OPENFACTORY_CACHE: sync failed for %s (%s)",
                        project, _scrub(str(exc))[:160])
            return None

    def _sync(self, project: str, clone_url: str, base_branch: str) -> Path | None:
        served = self.root / project
        master = self.root / _MASTERS_DIRNAME / project
        # UNNAMED IS ASKED OF THE REMOTE, not of the checkout. `_reset` needs a name for its
        # refspec, and taking that name from the existing tree made "the repository's own default"
        # mean "whatever this cache landed on once" — so a client who moved their default branch
        # was served the abandoned one for ever. The remote is the only thing that knows; the tree
        # is the fallback for when it cannot be reached, because an unreachable remote must not
        # throw away a working checkout.
        wanted = base_branch or remote_default_branch(clone_url) or current_branch(master)
        if not (wanted and (master / ".git").exists()
                and self._reset(master, wanted, clone_url)):
            # missing or corrupt → drop and reclone (the degrade ladder's middle rung).
            # Only the hidden master is dropped; the served tree stays whole throughout.
            shutil.rmtree(master, ignore_errors=True)
            master.parent.mkdir(parents=True, exist_ok=True)
            # THE CALLER'S OWN ANSWER DECIDES HERE, not `wanted`: `wanted` may have been inferred
            # from the checkout this line has just deleted, and cloning
            # `--branch <name-from-a-tree-we-judged-unusable>` fails on a name nobody asked for.
            # An empty ask lets git pick, which is what it means. `--no-local`, like every clone
            # the platform runs (#594): a path is read through the pack protocol, never copied
            # file by file while the source's own maintenance repacks it.
            rc, out = _git(["clone", "--no-local",
                            *(["--branch", base_branch] if base_branch else []),
                            clone_url, str(master)])
            if rc != 0:
                # GIT'S WHOLE SENTENCE (#592): the last 160 characters cut inside the object's path,
                # and the words before it, what git was doing when the file was not there, were
                # the only clue to which race it was
                log.warning("OPENFACTORY_CACHE: clone failed for %s (%s)",
                            project, _scrub(out).strip()[-2000:])
                return None
            _scrub_remote(master, clone_url)
        if self._needs_publish(served, master):
            self._publish(project, served, master)
        return served

    def _needs_publish(self, served: Path, master: Path) -> bool:
        """Whether the served snapshot must be replaced: absent, corrupt, behind the master's
        commit, or dirtied by a scribbler (a cache must be IDENTICAL to base, never merged into).
        When none of that holds the snapshot is left completely untouched, so the routine
        no-change sync costs a fetch and two reads — and churns nothing under a reader.

        THE FOURTH ANSWER IS "HELD" (#747): corrupt, behind or dirty, but a running job's worktree
        stands on it, so it stays as it is and `OPENFACTORY_CACHE_HELD` says why. The decision
        is taken here, the one place both `RepoCache._sync` and `SparseRepoCache._sync_sparse`
        ask, before `_publish` stages, links or renames anything. The marks are read only when a
        publish would otherwise happen, so the unmoved sync costs what it did. `self.held` says
        which answer a False was, for the sparse cache's freshness window."""
        self.held = False
        if not (served / ".git").exists():
            return True     # nothing can be marked in a tree that has no `.git`
        head = _head(served)
        if not head:
            why = "its HEAD cannot be read"
        else:
            base = _head(master)
            if head != base:
                why = f"it is at {head[:12]} and the base is at {base[:12]}"
            elif _worktree_dirty(served):
                why = "something was written into it"
            else:
                return False
        self.held = RepoCache._held_by_a_job(served, why)
        return not self.held

    @staticmethod
    def _held_by_a_job(served: Path, why: str) -> bool:
        """Whether a running job's worktree stands on `served`, said when it does.

        A JOB ON THE WORKTREE BOX LIVES IN THIS TREE'S `.git` (#747). For a project registered by
        clone URL the box runs `git worktree add` in the served checkout, so the job's admin
        directory is `<served>/.git/worktrees/<name>`. Swapping the tree moved it into the trash,
        and every git command in the job then exited 128, `fatal: not a git repository:
        <root>/<key>/.git/worktrees/<name>`, its push included (82500f9, git 2.43.0). The box
        marks the worktree it adds (`gitworktrees.mark_as_job`); git deletes the marker with the
        admin directory on `worktree remove` and `prune`; a marker older than a day stops holding.

        UNREADABLE HOLDS (engineering lessons §2): a `.git/worktrees` that cannot be listed may
        hold a job, and the destructive act is the one that waits."""
        marks = gitworktrees.live_job_marks(served)
        if marks is None:
            log.warning("OPENFACTORY_CACHE_HELD %s would be replaced (%s), but the job worktrees "
                        "registered in it could not be read, so it is kept as it is — a running "
                        "job may stand on it. Check the permissions of %s.",
                        served, why, served / ".git" / "worktrees")
            return True
        for stale in marks.stale:
            log.warning("OPENFACTORY_CACHE_HOLD_EXPIRED the job worktree %s was marked %d h ago, "
                        "past the %d h a job may hold %s, so it no longer holds it — a job that "
                        "ended without removing its worktree left it there",
                        stale.worktree, stale.age // 3600,
                        gitworktrees.JOB_MARKER_MAX_AGE // 3600, served)
        if not marks.live:
            return False
        holders = "; ".join(f"{m.worktree} (marked {int(m.age // 60)} min ago)"
                            for m in marks.live)
        log.warning("OPENFACTORY_CACHE_HELD %s would be replaced (%s), but a running job's "
                    "worktree stands on it: %s. It is kept as it is until that worktree is "
                    "removed, for at most %d h after it was marked.",
                    served, why, holders, gitworktrees.JOB_MARKER_MAX_AGE // 3600)
        return True

    def _publish(self, project: str, served: Path, master: Path) -> None:
        """Swap a fresh snapshot of the master into the served path.

        Hardlinks, not copies: git never modifies a working-tree or object file in place (it
        unlinks and recreates), so a snapshot stays frozen while the master moves on, at the cost
        of directory metadata only. The displaced tree is parked under the grace window rather
        than deleted, because a reader may still hold it. The swap itself is two renames — a
        name-based reader can catch a sub-millisecond gap between them and degrade exactly as it
        already must for any sync that returns None."""
        staging_root = self.root / _STAGING_DIRNAME
        staging_root.mkdir(parents=True, exist_ok=True)
        stage = staging_root / f"{project}{_SLOT_SEP}{uuid.uuid4().hex[:8]}"
        try:
            shutil.copytree(master, stage, symlinks=True, copy_function=os.link)
        except OSError as exc:
            # A FILESYSTEM WITHOUT HARDLINKS STILL GETS A CORRECT SNAPSHOT, AND IS TOLD WHAT IT
            # COSTS. This fallback was silent, and every sentence above about "metadata, not
            # content" was false on such a root without anything saying so: each snapshot a whole
            # copy of its master, each displaced one as much again for its grace (#369).
            shutil.rmtree(stage, ignore_errors=True)
            self._say_linkless(exc)
            shutil.copytree(master, stage, symlinks=True)
        if os.path.lexists(served):
            trash_root = self.root / _TRASH_DIRNAME
            trash_root.mkdir(parents=True, exist_ok=True)
            slot = trash_root / f"{project}{_SLOT_SEP}{uuid.uuid4().hex[:8]}"
            os.rename(served, slot)
            os.utime(slot)  # rename keeps the dir's old mtime; purge ages by arrival, not creation
            self._bound_displaced(project, trash_root)
        os.rename(stage, served)

    def _say_linkless(self, exc: OSError) -> None:
        root = str(self.root)
        if root in _LINKLESS_ROOTS:
            return
        _LINKLESS_ROOTS.add(root)
        log.warning("OPENFACTORY_CACHE_NO_HARDLINKS root=%s (%s) — this filesystem does not "
                    "hardlink, so every snapshot this cache serves is a whole COPY of its master "
                    "and every displaced one costs as much again until it is purged. Point "
                    "OPENFACTORY_REPO_CACHE at a filesystem that hardlinks.",
                    root, _one_reason(exc))

    @staticmethod
    def _bound_displaced(project: str, trash_root: Path) -> None:
        """Of one key's displaced trees, only the newest `_KEEP_DISPLACED` wait out their grace;
        the rest go now. Best-effort, like the purge."""
        mine: list[tuple[float, Path]] = []
        for entry in trash_root.iterdir():
            if not entry.name.startswith(f"{project}{_SLOT_SEP}"):
                continue
            try:
                mine.append((entry.stat().st_mtime, entry))
            except OSError:
                continue
        for _, entry in sorted(mine, key=lambda pair: pair[0], reverse=True)[_KEEP_DISPLACED:]:
            shutil.rmtree(entry, ignore_errors=True)

    def _purge_displaced(self) -> None:
        """Delete parked trees whose grace expired. Best-effort and per-entry: two keys syncing
        concurrently may purge at once, and losing a purge race must never fail a sync."""
        trash_root = self.root / _TRASH_DIRNAME
        if not trash_root.is_dir():
            return
        now = time.time()
        for entry in trash_root.iterdir():
            try:
                if now - entry.stat().st_mtime >= _TRASH_GRACE_SECONDS:
                    shutil.rmtree(entry, ignore_errors=True)
            except OSError:
                continue

    @staticmethod
    def _reset(path: Path, base_branch: str, clone_url: str = "") -> bool:
        """fetch + reset --hard origin/<base> + clean, on the MASTER only. False → caller recloned.

        Fetches from the URL passed as an ARGUMENT rather than from the stored remote, because the
        stored remote deliberately carries no credential (see the module docstring). The explicit
        refspec keeps `origin/<base>` meaning what it always did — without it the fetch would only
        move FETCH_HEAD and the reset below would silently use a stale ref."""
        spec = f"+refs/heads/{base_branch}:refs/remotes/origin/{base_branch}"
        fetch = ["fetch", clone_url, spec] if clone_url else ["fetch", "origin", base_branch]
        for args in (fetch,
                     ["checkout", "-f", base_branch],
                     ["reset", "--hard", f"origin/{base_branch}"],
                     ["clean", "-fdx"]):
            rc, _ = _git(args, cwd=path)
            if rc != 0:
                return False
        # a checkout cloned before this was fixed still holds a token in .git/config
        _scrub_remote(path, clone_url)
        return True


# ── the sparse cache: every source of a product, for the product role (#268, ADR-0052 D16) ─────

#: What the product role never reads as text: pictures, fonts, media, archives, compiled and packed
#: artefacts, binary data. A directory holding NOTHING ELSE is left out of a sparse checkout, so a
#: front end's pictures cost neither their blobs nor their files; a directory holding one line of
#: code among them is checked out whole (`sparse_cone`). By suffix, because a blob's size or content
#: cannot be asked of a partial clone without fetching the blob — which is the cost being avoided.
WEIGHT_SUFFIXES = frozenset({
    # pictures and design files
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".icns", ".webp", ".avif", ".heic", ".tif",
    ".tiff", ".psd", ".ai", ".sketch", ".fig", ".xcf",
    # fonts
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    # audio and video
    ".mp3", ".mp4", ".m4a", ".aac", ".mov", ".avi", ".wav", ".ogg", ".webm", ".flac", ".mkv",
    # archives and packages
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar", ".war", ".ear", ".whl",
    ".apk", ".ipa", ".dmg", ".iso", ".nupkg",
    # compiled
    ".exe", ".dll", ".so", ".dylib", ".a", ".o", ".obj", ".lib", ".class", ".pyc", ".pyo",
    ".wasm", ".bin",
    # binary data
    ".sqlite", ".sqlite3", ".db", ".parquet", ".npy", ".npz", ".pkl", ".h5", ".onnx", ".pt",
})


def is_weight(path: str) -> bool:
    """Whether the file at `path` is weight — something the role never reads as text."""
    name = str(path).rsplit("/", 1)[-1]
    return "." in name and ("." + name.rsplit(".", 1)[-1]).lower() in WEIGHT_SUFFIXES


class _Dir:
    """One directory of a tree read from `git ls-tree`: its files, and its directories."""

    __slots__ = ("_code", "dirs", "files")

    def __init__(self) -> None:
        self.files: list[str] = []
        self.dirs: dict[str, _Dir] = {}
        self._code: bool | None = None

    def own_code(self) -> bool:
        return any(not is_weight(f) for f in self.files)

    def has_code(self) -> bool:
        if self._code is None:
            self._code = self.own_code() or any(d.has_code() for d in self.dirs.values())
        return self._code


def sparse_cone(paths) -> tuple[list[str] | None, list[str]]:
    """`(cone, left_out)` for a tree whose files are `paths` (as `git ls-tree -r --name-only` names
    them): the directories a cone-mode sparse checkout lists so that every file that is not weight
    is on disk, and the directories it leaves out. `cone` None means nothing can be left out.

    WHOLE DIRECTORIES, BECAUSE CONE MODE IS. A cone takes each listed directory recursively, plus
    the files directly inside every directory above one, and the files at the root always. So a
    directory whose own files are code and whose subdirectories are all weight cannot keep the
    first and drop the second: it is taken whole. The rule errs towards disk every time — it may
    check out a picture, and it never leaves out a line of code.

    READ FROM TREES ALONE. A partial clone holds every tree and no blob it was not asked for, so the
    whole listing of a commit is local and the decision costs no fetch."""
    root = _Dir()
    for path in paths:
        parts = [p for p in str(path).split("/") if p]
        if not parts:
            continue
        node = root
        for part in parts[:-1]:
            node = node.dirs.setdefault(part, _Dir())
        node.files.append(parts[-1])
    return _plan(root, "", top=True)


def _plan(node: _Dir, prefix: str, *, top: bool = False) -> tuple[list[str] | None, list[str]]:
    listed: list[str] = []
    left_out: list[str] = []
    partial = False
    for name in sorted(node.dirs):
        child, where = node.dirs[name], f"{prefix}{name}"
        if not child.has_code():
            left_out.append(where)
            partial = True
            continue
        sub, dropped = _plan(child, where + "/")
        if sub is None:
            listed.append(where)
        else:
            listed += sub
            left_out += dropped
            partial = True
    if not partial:
        return None, []
    if not top and not listed and node.own_code():
        # its own code keeps the directory whole: cone mode cannot take its files without it
        return None, []
    return listed, left_out


#: A URL's userinfo — how a clone URL carries a credential — in any scheme.
_USERINFO_URL = re.compile(r"([a-z][a-z0-9+.-]*://)[^@/\s]+@", re.IGNORECASE)


def _credential_env(clone_url: str) -> tuple[str, dict[str, str]]:
    """`(public, env)`: the URL git may WRITE DOWN, and the environment that lets it authenticate
    without writing anything down.

    WHY NOT THE URL AS AN ARGUMENT, the way `RepoCache._reset` fetches. A partial clone fetches its
    blobs LATER — at the checkout, from the remote it was cloned from — so the credential has to
    reach that remote whenever git decides to fetch, not only on the one command this module spells.
    And a filtered fetch from a URL given as an argument RECORDS that URL as a promisor remote in
    `.git/config` (`remote.<url>.promisor`), which would write the token to disk — measured on git
    2.50 while building this. So the remote is the public URL, and `url.<credentialed>.insteadOf
    <public>` rewrites it in memory for every git process that inherits this environment: nothing
    is persisted, nothing is on a command line, and the entries a deployment already set through
    `GIT_CONFIG_COUNT` are kept."""
    public = _USERINFO_URL.sub(r"\1", clone_url or "", count=1)
    env = {"GIT_TERMINAL_PROMPT": "0"}
    if public and public != clone_url:
        try:
            n = int(os.environ.get("GIT_CONFIG_COUNT") or 0)
        except ValueError:
            n = 0
        env.update({"GIT_CONFIG_COUNT": str(n + 1),
                    f"GIT_CONFIG_KEY_{n}": f"url.{clone_url}.insteadOf",
                    f"GIT_CONFIG_VALUE_{n}": public})
    return public, env


def _git_out(args: list[str], cwd: Path | None, env: dict[str, str],
             stdin: str | None = None) -> subprocess.CompletedProcess:
    """One git command with its streams apart — a listing read from stdout must not carry a warning
    git wrote to stderr."""
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, input=stdin,
                          timeout=_GIT_TIMEOUT, env={**os.environ, **env}, check=False)


def _remote_tip(public: str, base_branch: str, env: dict[str, str]) -> tuple[str, str]:
    """`(branch, tip)` in ONE round trip: the branch to read — the declared one, else the one the
    repository points HEAD at — and the commit it is on right now. Either is `""` when the forge
    did not say: an unknown declared branch, an unreachable forge, a host that answers no symref.
    `ls-remote` transfers no objects, so this is a ref advertisement and nothing else."""
    patterns = ["HEAD", *([f"refs/heads/{base_branch}"] if base_branch else [])]
    asked = _git_out(["ls-remote", "--symref", public, *patterns], None, env)
    if asked.returncode != 0:
        return base_branch, ""
    symref = _symref_branch(asked.stdout)
    branch = base_branch or symref
    tips: dict[str, str] = {}
    for line in asked.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and not line.startswith("ref:"):
            tips[parts[1]] = parts[0]
    tip = tips.get(f"refs/heads/{branch}") or (tips.get("HEAD", "") if branch and branch == symref
                                               else "")
    return branch, tip


class SparseRepoCache(RepoCache):
    """The same cache — a master changed under a lock, a hardlink snapshot served — holding a
    PARTIAL clone checked out SPARSELY. Every source of a product is mounted from one (#268,
    ADR-0052 D16).

    PARTIAL: `--filter=blob:none` fetches every commit and every tree, and no blob until a checkout
    needs it. The history's blobs — most of a long-lived repository's weight — are never fetched.

    SPARSE: the checkout is cone mode over `sparse_cone` — every directory that holds code and none
    that holds only weight. `left_out` says which, so the prompt can.

    ON DEMAND: nothing is cloned until a turn mounts the source. After that, a turn fetches the
    commits that moved and checks out the files that changed.

    AN UNMOVED SOURCE COSTS ONE QUESTION (#369). The turn asks the forge once — `ls-remote` answers
    which branch HEAD points at AND where that branch is — and when the master already stands on
    that commit, whole, nothing else runs: no fetch, no listing of the tree, no checkout, no clean.
    It used to fetch anyway and then run the whole checkout on a tree that had not moved — two
    round trips and a full tree pass per source per turn, which at N sources is N of each before
    the role says a word. Measured on the four-source fixture: 60 git processes per unmoved turn,
    12 per source; now one process asks the forge and the rest read the master.

    INSIDE THE WINDOW IT COSTS NOTHING (#369). One question per source is still N round trips per
    message. With `fresh_for` above 0, a key brought up for the same branch less than `fresh_for`
    seconds ago, its served tree still there, is served again without starting any git process.
    The stamp under `.fresh/` says when, for which branch and over which commit, and what the cone
    left out; one that cannot be written or removed costs the window, never the source. Measured
    at 40 sources with nothing moved: 119 git processes per turn instead of 439, and 2 round trips
    instead of 42, both of them the context repository's. The default is 0, so only a caller that
    asks for a window gets one: the product role does, the system layer's refresh does not.

    Never raises, like `RepoCache.sync`. `failure` keeps git's own words about why a sync returned
    None, WITH EVERY CREDENTIAL TAKEN OUT, for the caller to classify — they are not a sentence for
    a prompt, because git names URLs."""

    def __init__(self, root: Path | None = None, *, fresh_for: float = 0,
                 clock=None) -> None:
        super().__init__(root)
        self.failure = ""
        self.left_out: list[str] = []
        #: whether the clone really is partial: a server that does not serve filters clones whole,
        #: and git says so only in a warning
        self.partial = False
        #: seconds a key brought up by this cache is served again without asking its forge. 0 — the
        #: default, and what the system layer's refresh keeps — asks every time.
        self.fresh_for = fresh_for
        self._clock = clock

    def sync(self, project: str, clone_url: str, base_branch: str = "") -> Path | None:
        self.failure, self.left_out, self.partial = "", [], False
        public, env = _credential_env(clone_url)
        try:
            with _key_lock(self.root, project).held(timeout=_LOCK_WAIT_SECONDS):
                try:
                    served = self.root / project
                    if self._fresh(project, base_branch, served):
                        return served
                    # WITHDRAWN BEFORE THE MASTER IS TOUCHED: a sync that dies half-way must not
                    # leave the last good sync's window open over a master that moved since
                    self._withdraw_fresh(project)
                    got = self._sync_sparse(project, public, base_branch, env)
                    # A HELD TREE IS NOT FRESH (#747): it stands at the commit a job's worktree
                    # holds, not the forge's, and a window over it served that old commit again
                    # for `fresh_for` seconds after the job let go (measured: the first sync after
                    # `cleanup`, 10 s into a 60 s window, still at the held commit)
                    if got is not None and not self.held:
                        self._remember_fresh(project, base_branch, got)
                    return got
                finally:
                    self._purge_displaced()   # whether or not this sync succeeded (`RepoCache`)
        except Exception as exc:  # noqa: BLE001 — cache trouble must never block the pipeline
            return self._failed(project, str(exc))

    def _stamp(self, project: str) -> Path:
        return self.root / _FRESH_DIRNAME / f"{project}.json"

    def _withdraw_fresh(self, project: str) -> None:
        """Remove `project`'s stamp, or say in the log that it could not.

        A STAMP THAT CANNOT BE REMOVED COSTS THE WINDOW, NOT THE SOURCE. A `.fresh/` turned
        read-only after a stamp was written (another uid on the volume, a remount) raised
        `PermissionError` here, and every later sync of the key returned None — read by the prompt
        as "not authorised", with `=0` too (review of #369, measured 2026-10-18). The stamp left
        behind is harmless: `_fresh` trusts it only over the commit it was written for, and the
        sync goes on, so the source is served and only the window is lost."""
        try:
            self._stamp(project).unlink(missing_ok=True)
        except OSError as exc:
            log.info("OPENFACTORY_CACHE: %s is served without a freshness window (%s)", project,
                     _one_reason(exc))

    def _fresh(self, project: str, base_branch: str, served: Path) -> bool:
        """Whether `project` was brought up for this same ask less than `fresh_for` seconds ago and
        its served tree is still there — and if so, what that sync's cone left out, read back.

        ON DISK UNDER THE ROOT, NOT IN MEMORY: a cache is built afresh per source per turn, and the
        panel and the worker are two processes on one root (`_key_lock`), so a window in memory
        would be per process and lost on every restart. Read under the key's lock, so it never
        sees a master another sync is half-way through changing.

        AND OVER THE COMMIT IT WAS WRITTEN FOR. A stamp that could not be withdrawn outlives the
        syncs after it: `main` at T0, `develop` at T0+1 over the same key, and `main` at T0+2
        would have been served develop's tree from main's window. The served tree's HEAD is read
        as a file (`_head_as_file`), because this path starts no git process."""
        if self.fresh_for <= 0:
            return False
        now = (self._clock or _now)()
        try:
            stamp = json.loads(self._stamp(project).read_text(encoding="utf-8"))
            age = now - float(stamp["at"])
            left_out = [str(d) for d in stamp["left_out"]]
            partial = bool(stamp["partial"])
            if not (stamp["asked"] == base_branch and 0 <= age < self.fresh_for
                    and stamp["head"] and stamp["head"] == _head_as_file(served)):
                return False
        except (OSError, ValueError, KeyError, TypeError):
            return False
        self.left_out, self.partial = left_out, partial
        return True

    def _remember_fresh(self, project: str, base_branch: str, served: Path) -> None:
        """Open the window: written AFTER the publish, with what THIS sync computed and the commit
        it served, so the fresh path never reads a master. A stamp that cannot be written costs
        the window and nothing else — the next turn asks the forge, as it did before there was a
        window."""
        if self.fresh_for <= 0:
            return
        stamp = self._stamp(project)
        part = stamp.with_name(f"{stamp.name}.{uuid.uuid4().hex[:8]}")
        try:
            stamp.parent.mkdir(parents=True, exist_ok=True)
            part.write_text(json.dumps({"at": (self._clock or _now)(), "asked": base_branch,
                                        "head": _head_as_file(served),
                                        "left_out": self.left_out, "partial": self.partial}),
                            encoding="utf-8")
            os.replace(part, stamp)
        except OSError as exc:
            with contextlib.suppress(OSError):
                part.unlink(missing_ok=True)
            log.info("OPENFACTORY_CACHE: %s is served without a freshness window (%s)", project,
                     _one_reason(exc))

    def _sync_sparse(self, project: str, public: str, base_branch: str,
                     env: dict[str, str]) -> Path | None:
        served = self.root / project
        master = self.root / _MASTERS_DIRNAME / project
        branch, tip = _remote_tip(public, base_branch, env)
        branch = branch or current_branch(master)
        ready = False
        if branch and (master / ".git").exists():
            # UNMOVED, AND WHOLE. The tip the forge names is the commit the master stands on, on
            # that branch, with nothing out of place — a checkout this process was killed in the
            # middle of stands on the right commit with a torn tree, and is checked out again.
            #
            # AND ITS `left_out` REMEMBERED. A master checked out before the note existed has
            # none, and reading that as "nothing was left out" served the weight directories
            # missing with the role told nothing — on every unmoved turn after an upgrade, which
            # for a stable source is for ever (review of #372). Not remembered is checked out
            # again, once, and remembered from then on.
            remembered = self._left_out_remembered(master)
            if (remembered is not None and tip and _head(master) == tip
                    and current_branch(master) == branch and not _worktree_dirty(master)):
                self.left_out = remembered
                ready = True
            else:
                spec = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
                fetched = _git_out(["fetch", "origin", spec], master, env)
                if fetched.returncode != 0:
                    # UNREACHABLE IS NOT CORRUPT: the master is kept for the turn after, and
                    # this turn is told — never served code it could not bring up to date
                    return self._failed(project, fetched.stderr or fetched.stdout)
                ready = self._checkout(master, f"origin/{branch}", env, branch=branch)
        if not ready:
            shutil.rmtree(master, ignore_errors=True)
            master.parent.mkdir(parents=True, exist_ok=True)
            cloned = _git_out(["clone", "--no-local", "--filter=blob:none", "--no-checkout",
                               *(["--branch", base_branch] if base_branch else []),
                               public, str(master)], None, env)
            if cloned.returncode != 0:
                return self._failed(project, cloned.stderr or cloned.stdout)
            if not self._checkout(master, "HEAD", env):
                return self._failed(project, self.failure or "the checkout failed")
        self.partial = _git_out(["config", "--get", "remote.origin.promisor"], master,
                                env).stdout.strip() == "true"
        if self._needs_publish(served, master):
            self._publish(project, served, master)
        return served

    @staticmethod
    def _left_out_remembered(master: Path) -> list[str] | None:
        """What the last checkout's cone left out, as `_checkout` wrote it down — the answer for
        the same commit, read rather than listed again. None when nothing was written down, which
        is not the same answer as "nothing was left out"."""
        try:
            text = (master / ".git" / _LEFT_OUT_FILE).read_text(encoding="utf-8")
        except OSError:
            return None
        return [line for line in text.splitlines() if line]

    def _checkout(self, master: Path, rev: str, env: dict[str, str], *, branch: str = "") -> bool:
        """The cone of `rev`, then `rev` checked out through it — on the MASTER only.

        The cone is set BEFORE the checkout, so a directory of weight never has its blobs fetched
        only to be deleted a moment later."""
        listed = _git_out(["ls-tree", "-r", "-z", "--name-only", rev], master, env)
        if listed.returncode != 0:
            self.failure = _scrub(listed.stderr)
            return False
        cone, self.left_out = sparse_cone(p for p in listed.stdout.split("\0") if p)
        try:
            (master / ".git" / _LEFT_OUT_FILE).write_text(
                "".join(f"{d}\n" for d in self.left_out), encoding="utf-8")
        except OSError:
            pass    # the unmoved turn then lists the tree once more, which is only slower
        steps: list[tuple[list[str], str | None]] = []
        if cone is not None:
            # from stdin, so a directory whose name starts with `-` is a name and not a flag
            steps.append((["sparse-checkout", "set", "--cone", "--stdin"],
                          "".join(f"{d}\n" for d in cone)))
        elif _git_out(["config", "--bool", "core.sparseCheckout"], master,
                      env).stdout.strip() == "true":
            steps.append((["sparse-checkout", "disable"], None))
        steps.append((["checkout", "-f", "-B", branch, rev] if branch
                      else ["reset", "--hard", rev], None))
        steps.append((["clean", "-fdx"], None))
        for args, stdin in steps:
            done = _git_out(args, master, env, stdin=stdin)
            if done.returncode != 0:
                self.failure = _scrub(done.stderr or done.stdout)
                return False
        return True

    def _failed(self, project: str, said: str) -> None:
        self.failure = _USERINFO_URL.sub(r"\1***@", _scrub(said or "")).strip()
        log.warning("OPENFACTORY_CACHE: sparse sync failed for %s (%s)", project,
                    self.failure[-160:])
        return None
