"""Every parameter the catalog takes is declared a person's words or not, the four #1032 found are
words, and a message sent on the product socket leaves its record (#694, PR #1039 review N7 and
N4, 2026-10-21), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/694_every_parameter_is_declared_words_or_not.py

On 6a41efe7 `FREE_TEXT` was a hand-kept set and nothing failed when a new free-text parameter
arrived under a new name; `context`, `requirement`, `violates` and `capability` were kept as text.
"""

TEST = "tests/test_the_audit_record_is_kept_in_the_metrics_store.py"

_BASE = "openfactory/actions/base.py"
_T = TEST + "::"

MUTATIONS = [
    ("the page context is not a person's words", _BASE,
     '    "context", "requirement", "violates", "capability",\n',
     '    "requirement", "violates", "capability",\n',
     _T + "test_the_free_text_1032_found_is_kept_as_its_length_and_digest"),
    ("a name a row takes is declared neither way", _BASE,
     '    "target", "thread", "token", "token_env", "unit", "version", "wait", "write", "yes",\n',
     '    "target", "thread", "token", "token_env", "unit", "version", "wait", "write",\n',
     _T + "test_every_parameter_the_catalog_takes_is_declared_a_persons_words_or_not"),
    ("a name is declared both ways", _BASE,
     '    "accept", "approver", "attachment",',
     '    "message", "accept", "approver", "attachment",',
     _T + "test_every_parameter_the_catalog_takes_is_declared_a_persons_words_or_not"),
    ("a message on the product socket leaves no record", "openfactory/actions/__init__.py",
     "        await audit.write(record)\n",
     "        pass\n",
     "tests/test_the_panel_is_a_chat.py::"
     "test_a_message_sent_on_the_socket_leaves_one_record_naming_who_sent_it"),
]
