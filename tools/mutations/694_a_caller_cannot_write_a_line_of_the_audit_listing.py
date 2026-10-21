"""A caller cannot write a line of the `openfactory audit` listing, nor of the action's log lines
(#694, PR #1039 review B1, 2026-10-21), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/694_a_caller_cannot_write_a_line_of_the_audit_listing.py

The claims: every column the listing prints, the INFO line's action and who asked, and the
WARNING when a record is not kept, write each control character a caller sent as its escape
(`audit.printable`), so one call is one line — and `printable` itself escapes every `C`
category character, the three a reader knows by name as Python writes them.

Every row names the one test that holds its claim. On c310ba28 three calls by an anonymous
caller printed six listing lines, and the unknown-action INFO line was one record of two lines.
"""

TEST = "tests/test_a_caller_cannot_write_a_line_of_the_audit_listing.py"

_AUDIT = "openfactory/observability/audit.py"
_ACTIONS = "openfactory/actions/__init__.py"
_CLI = "openfactory/cli.py"
_T = TEST + "::"
_ONE_LINE = _T + "test_one_call_is_one_line_of_the_listing_whatever_the_caller_sent"

MUTATIONS = [
    ("the listing prints each column as stored", _CLI,
     '        typer.echo("  ".join(audit.printable(column) for column in shown))\n',
     '        typer.echo("  ".join(str(column) for column in shown))\n',
     _ONE_LINE),
    ("the INFO line prints the action as asked", _ACTIONS,
     "audit.printable(audit._scrub(key)),\n",
     "audit._scrub(key),\n",
     _T + "test_the_action_line_is_one_line_whatever_action_was_asked"),
    ("the not-kept WARNING prints the action as asked", _ACTIONS,
     "                    audit.printable(audit._scrub(key or name)), audit.printable(by), exc)\n",
     "                    key or name, by, exc)\n",
     _T + "test_no_log_line_about_the_record_carries_a_callers_newline"),
    ("printable lets a control character through", _AUDIT,
     '        elif unicodedata.category(char).startswith("C"):\n',
     "        elif False:\n",
     _ONE_LINE + "[a_terminal_escape_in_the_project]"),
    ("printable writes a newline as \\x0a, not \\n", _AUDIT,
     "        if char in _NAMED_ESCAPES:\n            shown.append(_NAMED_ESCAPES[char])\n"
     "        elif",
     "        if False:\n            pass\n        elif",
     _ONE_LINE + "[a_newline_in_the_project]"),
    ("printable returns every text as it is", _AUDIT,
     "    if text.isprintable():\n        return text\n",
     "    if True:\n        return text\n",
     _ONE_LINE),
]
