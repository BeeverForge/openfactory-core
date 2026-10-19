"""Two processes that share a repository cache never change one checkout at the same time (#656,
journey 0, #640), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/656_two_processes_never_change_one_checkout_at_once.py

The claims, each a row:
  1. one key of a cache root is changed by one process at a time, in both caches;
  2. two keys are not queued behind each other;
  3. a sync that cannot have its key within its wait degrades instead of waiting for ever.
"""

TEST = "tests/test_two_processes_never_change_one_checkout_at_once.py"
CACHE = "openfactory/runtime/repo_cache.py"

MUTATIONS = [
    # 1. one process at a time
    ("TODAY'S RUN: the key's lock is held per process, as the thread lock was", CACHE,
     '    return FileLock(Path(root) / _LOCKS_DIRNAME / f"{key}.lock")',
     '    return FileLock(Path(root) / _LOCKS_DIRNAME / f"{key}.{os.getpid()}.lock")'),
    ("the plain cache syncs a key without its lock", CACHE,
     "            with _key_lock(self.root, project).held(timeout=_LOCK_WAIT_SECONDS):\n"
     "                try:\n                    return self._sync(",
     "            with open(os.devnull):\n                try:\n                    return self._sync("),
    # RE-PINNED 2026-10-18 (#369 window): the sparse `sync` now looks at its freshness window
    # before `_sync_sparse`, inside the same lock, so the anchor is the line that opens the body.
    ("the sparse cache syncs a key without its lock", CACHE,
     "            with _key_lock(self.root, project).held(timeout=_LOCK_WAIT_SECONDS):\n"
     "                try:\n                    served = self.root / project\n",
     "            with open(os.devnull):\n                try:\n"
     "                    served = self.root / project\n"),

    # 2. per key
    ("one lock for every key of a root", CACHE,
     '    return FileLock(Path(root) / _LOCKS_DIRNAME / f"{key}.lock")',
     '    return FileLock(Path(root) / _LOCKS_DIRNAME / "every-key.lock")'),

    # 3. the wait
    ("the plain cache waits for its key for ever", CACHE,
     "            with _key_lock(self.root, project).held(timeout=_LOCK_WAIT_SECONDS):\n"
     "                try:\n                    return self._sync(",
     "            with _key_lock(self.root, project).held(timeout=10 ** 9):\n"
     "                try:\n                    return self._sync("),
    # RE-PINNED 2026-10-18 (#369 window), as row 1.
    ("the sparse cache waits for its key for ever", CACHE,
     "            with _key_lock(self.root, project).held(timeout=_LOCK_WAIT_SECONDS):\n"
     "                try:\n                    served = self.root / project\n",
     "            with _key_lock(self.root, project).held(timeout=10 ** 9):\n"
     "                try:\n                    served = self.root / project\n"),
]
