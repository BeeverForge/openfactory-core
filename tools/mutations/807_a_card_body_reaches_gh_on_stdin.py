"""A card body GitHub accepts reaches `gh` on stdin, on every run, and never in argv (#807).

Run:  .venv/bin/python tools/mutate.py tools/mutations/807_a_card_body_reaches_gh_on_stdin.py

GitHub's limit is 65,536 characters; one argv element's is 131,072 bytes (`MAX_ARG_STRLEN`), so a
body in a 3-byte script crossed the second at about 43,690 characters and the create died as
`OSError: [Errno 7] Argument list too long: 'gh'` before `gh` started (gh 2.102.0, 2026-10-19).

Row 1 is the defect as it shipped: the body back in argv. Row 2 keeps `--body-file -` and sends
nothing, which would create an empty card. Rows 3-4 drop stdin from one of the two runs `_gh`
makes, the first and the secondary-rate-limit retry: each run must carry it. Row 5 is the fix the
plan refused: the create bypasses `_gh` the way `update_body` does, and loses the retry.
"""

TEST = "tests/test_a_card_body_github_accepts_is_created_whatever_its_bytes.py"

GH = "openfactory/adapters/tracker/github.py"

MUTATIONS = [
    ("THE DEFECT: the body goes back into argv as one element", GH,
     '"--title", title, "--body-file", "-"], stdin=body)',
     '"--title", title, "--body", body])'),

    ("--body-file - with nothing on stdin: the card is created empty", GH,
     '"--title", title, "--body-file", "-"], stdin=body)',
     '"--title", title, "--body-file", "-"], stdin=None)'),

    ("the first run drops stdin", GH,
     '        try:\n            p = subprocess.run(\n'
     '                ["gh", *args], input=stdin, capture_output=True,',
     '        try:\n            p = subprocess.run(\n'
     '                ["gh", *args], capture_output=True,'),

    ("the rate-limit retry drops stdin", GH,
     '            time.sleep(8)\n            p = subprocess.run(\n'
     '                ["gh", *args], input=stdin, capture_output=True,',
     '            time.sleep(8)\n            p = subprocess.run(\n'
     '                ["gh", *args], capture_output=True,'),

    ("the create bypasses _gh as update_body does, and loses the rate-limit retry", GH,
     '        p = self._gh(["issue", "create", "--repo", target,\n'
     '                      "--title", title, "--body-file", "-"], stdin=body)',
     '        p = subprocess.run(["gh", "issue", "create", "--repo", target,\n'
     '                            "--title", title, "--body-file", "-"], input=body, text=True,\n'
     '                           capture_output=True, timeout=60, check=False, env=self._env())'),
]
