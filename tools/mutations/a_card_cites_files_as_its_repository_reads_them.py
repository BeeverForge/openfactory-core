"""A card the product role writes cites each file as the repository it lands in reads it (journey 0,
#640), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/a_card_cites_files_as_its_repository_reads_them.py

The claims, each a row:
  1. the repository's own `src/<name>/` goes, another source's names its repository, only a path
     that starts at the view is rewritten, and one already the repository's own is left alone;
  2. every writer rewrites the role's words: a breakdown's front, a requested card, a defect, and
     the criteria refine, align and correct write;
  3. a rewrite that cannot be made files the card as written, and logs it.
"""

TEST = "tests/test_a_card_cites_files_as_its_repository_reads_them.py"
WS = "openfactory/product/workspace.py"
MOD = "openfactory/product/module.py"

MUTATIONS = [
    # 1. the paths
    ("TODAY'S RUN: the repository's own prefix is kept", WS,
     "                return found.group(0)\n        return rest\n",
     "                return found.group(0)\n        return found.group(0)\n"),
    ("another source's path is read as this repository's", WS,
     '            return f"{repo}:{rest}"', "            return rest"),
    ("a path that does not start at the view is rewritten", WS,
     'pattern = re.compile(r"(?<![\\w./-])(?:\\./)?src/("', 'pattern = re.compile(r"(?:\\./)?src/("'),
    ("a path already the repository's own is cut short", WS,
     "            if as_the_repository.exists() and not as_the_view.exists():",
     "            if False:"),

    # 2. every writer
    ("TODAY'S RUN: a breakdown's front is filed as the view reads it", MOD,
     "        draft = self._in_repository_terms(draft, where)\n", ""),
    ("a requested card is filed as the view reads it", MOD,
     "        described = self._in_repository_terms(described)\n", ""),
    ("a defect is filed as the view reads it", MOD,
     "        title, restated = self._in_repository_terms([title, restated])\n", ""),
    ("refine writes its criteria as the view reads them", MOD,
     "        answer = self._in_repository_terms(\n            answer, split_repo_ref(number, "
     "self._source_repo())[0])\n        body = _with_criteria(",
     "        body = _with_criteria("),
    ("an alignment writes its criteria as the view reads them", MOD,
     "        answer = self._in_repository_terms(\n            answer, split_repo_ref(number, "
     "self._source_repo())[0])\n        criteria = answer.get(\"criteria\") or criteria\n", ""),
    ("a correction writes its text as the view reads it", MOD,
     "        text, title = self._in_repository_terms([(text or \"\").strip(), (title or \"\").strip()],"
     "\n                                                home)",
     "        text, title = (text or \"\").strip(), (title or \"\").strip()"),
    ("the view this turn composed is not what places the paths", MOD,
     "            placed = {repo: Path(path).name for repo, path in mounted.items()}",
     "            placed = {}"),

    # 3. a rewrite that cannot be made
    ("a rewrite that cannot be made loses the card's words", MOD,
     "                        exc_info=True)\n            return value\n",
     "                        exc_info=True)\n            return \"\"\n"),
]
