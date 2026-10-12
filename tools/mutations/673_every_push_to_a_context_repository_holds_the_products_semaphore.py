"""Every push onto a context repository's base branch holds the product's semaphore (#673, journey
0, #640), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/673_every_push_to_a_context_repository_holds_the_products_semaphore.py

The claims, each a row:
  1. a publish of derived knowledge holds the product's semaphore around its clone and its push,
     so the members of one product all land and a person's save is never refused because of it;
  2. a publish that cannot have the semaphore in time is `busy`;
  3. every publish names the product it queues behind;
  4. forgetting a project's distillates holds the semaphore too, which the scan of every push
     onto a base branch finds.
"""

TEST = "tests/test_every_push_to_a_context_repository_holds_the_products_semaphore.py"
PIPELINE = "openfactory/knowledge/pipeline.py"

MUTATIONS = [
    # 1. the publish holds the semaphore
    ("TODAY'S RUN: a publish of derived knowledge takes no semaphore", PIPELINE,
     "        with semaphore.held(project, timeout=timeout):\n            return _publish_dir(",
     "        with open(os.devnull):\n            return _publish_dir("),
    ("the module map's publish names no product", PIPELINE,
     "    return publish_dir(bundle_dir, remote_url, project=project, subpath=subpath,",
     "    return publish_dir(bundle_dir, remote_url, project=None, subpath=subpath,"),

    # 2. busy
    ("a publish that could not have the semaphore reads as a failed push", PIPELINE,
     "        return BUSY\n", "        return FAILED\n"),

    # 3. every publish names its product
    ("`openfactory knowledge build` publishes naming no product", "openfactory/cli.py",
     "        if publish_bundle(dest, context_url, project=project, subpath=subpath,",
     "        if publish_bundle(dest, context_url, subpath=subpath,"),

    # 4. the scan of every push onto a base branch
    ("forgetting a project's distillates pushes without the semaphore",
     "openfactory/product/forget.py",
     "        with semaphore.held(t.project):\n", "        with open(__file__):\n"),
]
