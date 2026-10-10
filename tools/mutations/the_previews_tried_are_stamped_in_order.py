"""The requester-loop scenario stamps each preview it tries after the one before, so the yes reads
the preview the requester tried last whatever the wall clock does, proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/the_previews_tried_are_stamped_in_order.py

`preview.latest` reads the newest record by its stamp. The scenario records the PR 10 preview a
moment after the PR 9 one; under a loaded suite this machine's wall clock stepped back between
them, the PR 9 preview read as the newest, and the second yes was refused as untried (3 runs in 48
under parallel load). The claims, each a row:

  1. each preview tried is stamped after the one before;
  2. the stamp is the one `preview.record` writes.
"""

TEST = "tests/test_the_requesters_loop_walks_through_the_door.py"

MUTATIONS = [
    ("TODAY'S DEFECT: the preview tried is stamped by the wall clock", TEST,
     "    _STAMPED.append(max(now, _STAMPED[-1] + timedelta(seconds=1)) if _STAMPED else now)",
     "    _STAMPED.append(now)"),
    ("the stamp is kept and the record writes the wall clock's", TEST,
     '        mp.setattr(preview, "datetime", _At(_STAMPED[-1]))\n',
     ""),
]
