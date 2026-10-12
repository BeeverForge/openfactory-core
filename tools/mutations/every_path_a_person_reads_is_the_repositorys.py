"""Every path the product role writes for a person cites the file as its repository reads it
(journey 0, #640 row I-01, #672), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/every_path_a_person_reads_is_the_repositorys.py

The claims, each a row:
  1. a reply cites each file from its repository's root: the path alone in a product of one
     repository, `<repo>:<path>` in a product of several; what the platform reads in the reply
     keeps the view's path;
  2. a requirement does the same, every field of it, its conflicts' explanations included;
  3. every model call over the view whose answer a person reads is rewritten where it is made, or
     by the function named for it.
"""

TEST = "tests/test_every_path_a_person_reads_is_the_repositorys.py"
MOD = "openfactory/product/module.py"

MUTATIONS = [
    # 1. a reply
    ("TODAY'S RUN: a reply reaches the person as the view reads it", MOD,
     "        return answer.model_copy(update=_in_repository_terms(self, {\n",
     "        return answer\n        return answer.model_copy(update=_in_repository_terms(self, {\n"),
    ("a reply's paths are read against this project's repository alone", MOD,
     '            "decisions": answer.decisions, "gesture_args": answer.gesture_args},\n'
     "            product_wide=True))",
     '            "decisions": answer.decisions, "gesture_args": answer.gesture_args},\n'
     "            product_wide=False))"),
    ("a product of one repository names its repository on every path", MOD,
     '        home = ((next(iter(placed)) if len(placed) == 1 else "") if product_wide\n',
     '        home = ("" if product_wide\n'),
    ("a product of several reads one of them as home", MOD,
     "(next(iter(placed)) if len(placed) == 1 else \"\")",
     "(next(iter(placed)) if placed else \"\")"),
    ("what the platform reads in the reply is rewritten too", MOD,
     '            "decisions": answer.decisions, "gesture_args": answer.gesture_args},\n',
     '            "decisions": answer.decisions, "gesture_args": answer.gesture_args,\n'
     '            "reading": answer.reading},\n'),
    ("a mapping of the role's words is left as written", MOD,
     "            return {k: _walk(v) for k, v in value.items()}\n",
     "            return value\n"),

    # 2. a requirement
    ("TODAY'S RUN: a requirement is drafted as the view reads it", MOD,
     '            "draft": _in_repository_terms(self, drafted.draft, product_wide=True)})',
     '            "draft": drafted.draft})'),
    ("a draft's lists keep the view's paths", MOD,
     "            return type(value)(_walk(v) for v in value)\n",
     "            return value\n"),
    ("a conflict's explanation keeps the view's paths", MOD,
     "            return type(value)(_walk(v) for v in value)\n",
     "            return type(value)(_walk(v) if isinstance(v, str) else v for v in value)\n"),

    # 3. every model call over the view
    ("the triage of parked cards is left as the view reads it", MOD,
     "            answer = _in_repository_terms(self, answer)\n"
     "            # an unreadable classification", "            # an unreadable classification"),
    ("the proposed queue is left as the view reads it", MOD,
     "        proposal = QueueProposal(**_in_repository_terms(self, answer))",
     "        proposal = QueueProposal(**answer)"),
    ("the function said to rewrite a breakdown's fronts does not", MOD,
     "        draft = _in_repository_terms(self, draft, where)\n", ""),
]
