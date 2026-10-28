"""Every clone the platform runs reads its source through the pack protocol, never by copying the
source's objects directory file by file (#594), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/594_a_clone_reads_through_the_pack_protocol.py

A clone of a local path links or copies each file under the source's `.git/objects`, and fails
when git's own background maintenance repacks the source meanwhile. The local forge's repositories
are paths, and the box and the preview clone the worker's cache directory. The claims, each a row:

  1. the cache and the box clone a path with `--no-local`, and copy nothing a repack is writing;
  2. every clone the platform runs passes it, and the guard sees each shape a clone is written in.
"""

TEST = "tests/test_a_clone_reads_through_the_pack_protocol.py"
CACHE = "openfactory/runtime/repo_cache.py"
BOX = "openfactory/adapters/sandbox/container.py"
AUTHORING = "openfactory/product/authoring.py"

MUTATIONS = [
    # 1. the clones a path reaches
    ("TODAY'S DEFECT: the cache clones a path file by file", CACHE,
     '            rc, out = _git(gitpin.pinned(["clone", "--no-local",\n',
     '            rc, out = _git(gitpin.pinned(["clone",\n'),
    ("the box clones the cache file by file again, without hardlinks", BOX,
     '["clone", "--no-local", "--", str(repo_path), str(host_clone)]',
     '["clone", "--local", "--no-hardlinks", "--", str(repo_path), str(host_clone)]'),

    # 2. every clone, and the guard
    ("a clone that writes a requirement copies the objects directory", AUTHORING,
     '        rc, out = _git(gitpin.pinned(["clone", "--no-local", "--branch", base, "--", clone_url,\n',
     '        rc, out = _git(gitpin.pinned(["clone", "--branch", base, "--", clone_url,\n'),
    ("the guard reads lists and never a call's own arguments", TEST,
     "        elif isinstance(node, ast.Call):\n            items = node.args\n",
     ""),
    ("the guard does not see `git` before `clone`", TEST,
     ' or words[:2] == ["git", "clone"]',
     ""),
]
