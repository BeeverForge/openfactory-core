"""A source the product role brought up inside the freshness window is served as it was and asks
its forge nothing; the window never outlives a sync that did not serve, and never reaches the
system layer's refresh (#369).

Run:  .venv/bin/python tools/mutate.py tools/mutations/369b_a_turn_inside_the_window_asks_no_forge.py

An unmoved source cost one question and no checkout (#372) — still N round trips per message, one
per source. `SparseRepoCache` now keeps a stamp per key under `<root>/.fresh/`, and a sync for the
same ask inside `fresh_for` seconds, its served tree still there, starts no git process.

Rows 1-6 and 9 are the window itself: it opens; a stamp from the future opens none; it is kept
per branch asked for; it is withdrawn before the master is touched and written only after a sync
that served; a deleted served tree, or one on another commit than its stamp names, is brought up
again inside it; and what the cone left out is read back from it. Rows 7-8 are a stamp that cannot
be removed: the sync goes on, and the stamp left behind is trusted only over the COMMIT it names,
read from the served tree's `.git` as files — not over the branch HEAD points at. Row 10 is a root
where no stamp can be written, which loses the window and nothing else. Rows 11-12 are the
operator's setting, read, and refused when it is `inf`. Row 13 keeps the window out of the system
layer's refresh, which publishes the map right after a merge; row 14 is the product role's path
passing the setting in.
"""

TEST = "tests/test_a_source_brought_up_inside_the_window_asks_no_forge.py"

CACHE = "openfactory/runtime/repo_cache.py"
SOURCES = "openfactory/product/sources.py"
MODULE = "openfactory/product/module.py"

MUTATIONS = [
    ("TODAY'S COST: the window never opens, every turn asks every source's forge", CACHE,
     "                    if self._fresh(project, base_branch, served):\n",
     "                    if False:\n"),

    ("a stamp from the future — a clock that went back, a skewed volume — opens a window", CACHE,
     "0 <= age < self.fresh_for",
     "age < self.fresh_for"),

    ("another branch is served from the window of the one asked before it", CACHE,
     "            if not (stamp[\"asked\"] == base_branch and 0 <= age",
     "            if not (0 <= age"),

    ("a sync that died half-way leaves the last good sync's window open over a moved master",
     CACHE,
     "                    self._withdraw_fresh(project)\n",
     "                    pass\n"),

    ("a sync that failed opens a window, so 'unreachable' is never asked again inside it", CACHE,
     # re-pinned 2026-10-19 (#747): the guard now also skips a held sync's stamp
     "                    if got is not None and not self.held:\n"
     "                        self._remember_fresh(project, base_branch, got)\n",
     "                    if True:\n"
     "                        self._remember_fresh(project, base_branch, got or served)\n"),

    ("a served tree that is gone, or stands on another commit than its stamp, is served from the "
     "window", CACHE,
     "                    and stamp[\"head\"] and stamp[\"head\"] == _head_as_file(served)):",
     "                    ):"),

    ("a stamp that cannot be removed fails every later sync of its key", CACHE,
     "            self._stamp(project).unlink(missing_ok=True)\n"
     "        except OSError as exc:\n",
     "            self._stamp(project).unlink(missing_ok=True)\n"
     "        except ZeroDivisionError as exc:\n"),

    ("the stamp names the branch HEAD points at, not the commit, so a stamp left behind is "
     "trusted over a tree another sync moved", CACHE,
     "        ref = head[len(\"ref: \"):].strip()\n",
     "        return head\n"),

    ("the window forgets what the cone left out", CACHE,
     "        self.left_out, self.partial = left_out, partial\n",
     "        self.left_out, self.partial = [], partial\n"),

    ("a root where no stamp can be written fails the sync instead of only losing the window",
     CACHE,
     "        except OSError as exc:\n"
     "            with contextlib.suppress(OSError):\n",
     "        except ZeroDivisionError as exc:\n"
     "            with contextlib.suppress(OSError):\n"),

    ("the operator's window is ignored", SOURCES,
     "    raw = (os.environ.get(\"OPENFACTORY_SOURCES_FRESH_SECONDS\") or \"\").strip()\n",
     "    raw = \"\"\n"),

    ("an operator's `inf` is a window that never closes", SOURCES,
     "    if not 0 <= value < float(\"inf\"):\n",
     "    if not 0 <= value:\n"),

    ("the window leaks into the system layer's refresh", CACHE,
     "        self.fresh_for = fresh_for\n",
     "        self.fresh_for = fresh_for or __import__(\"openfactory.product.sources\",\n"
     "                                                 fromlist=[\"fresh_for\"]).fresh_for()\n",
     "tests/test_the_system_layer_is_published.py"),

    ("the product role's turn is never given the window", MODULE,
     "            cache = SparseRepoCache(fresh_for=fresh_for())\n",
     "            cache = SparseRepoCache()\n",
     "tests/test_every_source_is_mounted.py"),
]
