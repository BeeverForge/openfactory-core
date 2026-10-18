"""A source the product role brought up inside the freshness window is served as it was and asks
its forge nothing; the window never outlives a sync that did not serve, and never reaches the
system layer's refresh (#369).

Run:  .venv/bin/python tools/mutate.py tools/mutations/369b_a_turn_inside_the_window_asks_no_forge.py

An unmoved source cost one question and no checkout (#372) — still N round trips per message, one
per source. `SparseRepoCache` now keeps a stamp per key under `<root>/.fresh/`, and a sync for the
same ask inside `fresh_for` seconds, its served tree still there, starts no git process.

Rows 1-7 are the window itself: it opens; a stamp from the future opens none; it is kept per branch
asked for; it is withdrawn before the master is touched and written only after a sync that served;
a deleted served tree is brought back inside it; and what the cone left out is read back from it.
Row 8 is a root where no stamp can be written, which loses the window and nothing else. Row 9 is
the operator's setting. Row 10 keeps the window out of the system layer's refresh, which publishes
the map right after a merge; row 11 is the product role's path passing the setting in.
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
     "                    self._stamp(project).unlink(missing_ok=True)\n",
     "                    pass\n"),

    ("a sync that failed opens a window, so 'unreachable' is never asked again inside it", CACHE,
     "                    if got is not None:\n"
     "                        self._remember_fresh(project, base_branch)\n",
     "                    if True:\n"
     "                        self._remember_fresh(project, base_branch)\n"),

    ("a served tree that is gone is never brought back while the window holds", CACHE,
     "                    and (served / \".git\").exists()):",
     "                    ):"),

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
