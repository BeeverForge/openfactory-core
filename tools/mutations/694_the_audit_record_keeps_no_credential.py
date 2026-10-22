"""The audit record, its INFO line and the denial warnings keep no credential however a caller
sends one, and the fallback file is its owner's alone (#694, PR #1039 review, 2026-10-21),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/694_the_audit_record_keeps_no_credential.py

The claims, one group of rows each:
  1. a secret's name is matched by its pattern (a word anywhere in it, in any case), and `pat`
     only as a word of it — so `api_key`, `Password` and `github_pat` are masked and `path` and
     `repo_path` are not;
  2. every string is scrubbed of credentials (a URL's userinfo, a credential's shape, this
     process's secrets) — a value, a name, the project, the action, and the action in the line —
     and a value is scrubbed whole before it is cut;
  3. a mapping or a list inside a parameter is read by the same rules at every depth, to
     `PARAMS_KEPT` entries and `NESTED_DEPTH` levels, and a nested value is cut to `VALUE_CHARS`
     like any other;
  4. the denial warnings print the same masking (`actions._loggable` is `audit.redact`);
  5. the fallback `audit.db` is created `0600`, and one found wider is made so and said.

Every row names the one test that holds its claim.
"""

TEST = "tests/test_the_audit_record_keeps_no_credential.py"

_AUDIT = "openfactory/observability/audit.py"
_ACTIONS = "openfactory/actions/__init__.py"
_T = TEST + "::"

MUTATIONS = [
    # 1. the name rule
    ("a secret's name is matched exactly, not by its pattern", _AUDIT,
     "    lowered = text.lower()\n    if any(word in lowered for word in SECRET_WORDS):\n",
     "    lowered = text.lower()\n    return text in SECRET\n"
     "    if any(word in lowered for word in SECRET_WORDS):\n",
     _T + "test_a_refused_call_masks_a_secret_by_its_name_whatever_its_case_and_affix"),
    ("the case of a name decides whether it is a secret's", _AUDIT,
     "    lowered = text.lower()\n    if any(",
     "    lowered = text\n    if any(",
     _T + "test_a_refused_call_masks_a_secret_by_its_name_whatever_its_case_and_affix"
          "[Password]"),
    ("`pat` is not a word of a secret's name", _AUDIT,
     'SECRET_TOKENS = frozenset({"pat"})\n',
     "SECRET_TOKENS = frozenset()\n",
     _T + "test_a_refused_call_masks_a_secret_by_its_name_whatever_its_case_and_affix"
          "[github_pat]"),
    ("`pat` is matched as a substring, so `path` and `repo_path` are masked", _AUDIT,
     "    return any(word.lower() in SECRET_TOKENS for word in _WORD.findall(text))\n",
     "    return any(word in lowered for word in SECRET_TOKENS)\n",
     _T + "test_a_parameter_named_like_a_path_is_not_masked"),
    # 2. the scrub
    ("no string is scrubbed of credentials", _AUDIT,
     "    return scrub_credentials(text)\n",
     "    return text\n",
     _T + "test_a_token_in_a_urls_userinfo_reaches_neither_the_record_the_line_nor_the_file"),
    ("no string is scrubbed (this process's own secrets)", _AUDIT,
     "    return scrub_credentials(text)\n",
     "    return text\n",
     _T + "test_a_secret_this_process_holds_is_withheld_wherever_a_caller_sends_it"),
    ("a value is cut before it is scrubbed", _AUDIT,
     "        clean = _clean(value, depth=1, words=True)\n",
     "        clean = _clean(_cut(value) if isinstance(value, str) else value, depth=1,"
     " words=True)\n",
     _T + "test_a_token_straddling_the_cut_is_withheld_before_the_value_is_cut"),
    ("the project is not scrubbed", _AUDIT,
     '        project = _cut(_storable(_scrub(str(params.get("project") or ""))))\n',
     '        project = _cut(_storable(str(params.get("project") or "")))\n',
     _T + "test_a_token_in_the_project_a_caller_typed_is_withheld_from_the_rows_key"),
    ("a parameter's name is not scrubbed", _AUDIT,
     "    text = _scrub(str(name))\n",
     "    text = str(name)\n",
     _T + "test_a_token_sent_as_a_parameters_name_is_withheld_from_the_record"),
    ("the record's action is not scrubbed", _AUDIT,
     '        asked = _scrub((name or "").strip()).lower() or _scrub(name or "")\n',
     '        asked = (name or "").strip().lower() or name\n',
     _T + "test_a_token_typed_as_the_action_is_withheld_from_the_record_and_the_line"),
    ("the line's action is not scrubbed", _ACTIONS,
     "audit.printable(audit._scrub(key)),\n",
     "audit.printable(key),\n",
     _T + "test_a_token_typed_as_the_action_is_withheld_from_the_record_and_the_line"),
    # 3. nested values
    ("a nested mapping's names are not read", _AUDIT,
     "            if is_secret(name):\n                cleaned[_name(name)] = MASK\n",
     "            if False:\n                cleaned[_name(name)] = MASK\n",
     _T + "test_a_secret_nested_in_a_parameter_is_masked_like_one_at_the_top"),
    ("a list's items are kept as sent", _AUDIT,
     "        items = [_clean(inner, depth=depth + 1, words=words)\n",
     "        items = [inner\n",
     _T + "test_a_secret_in_a_list_is_masked_like_one_in_a_mapping"),
    ("nothing bounds the depth a value is read to", _AUDIT,
     "    if isinstance(value, Mapping | list | tuple | set | frozenset) and depth >= "
     "NESTED_DEPTH:\n",
     "    if False:\n",
     _T + "test_a_value_nested_past_the_depth_bound_is_not_kept_and_says_so"),
    ("a nested mapping is read whole, however many entries", _AUDIT,
     "        for name, inner in islice(value.items(), PARAMS_KEPT):\n",
     "        for name, inner in value.items():\n",
     _T + "test_a_nested_mapping_is_read_to_PARAMS_KEPT_entries_and_the_rest_counted"),
    ("the entries a nested mapping leaves out are not counted", _AUDIT,
     '            cleaned["…"] = f"{len(value) - PARAMS_KEPT} more entries not kept"\n',
     "            pass\n",
     _T + "test_a_nested_mapping_is_read_to_PARAMS_KEPT_entries_and_the_rest_counted"),
    ("a nested value is kept whole, past VALUE_CHARS", _AUDIT,
     "        if len(text) <= VALUE_CHARS:\n            kept[shown] = clean\n",
     "        if len(text) <= VALUE_CHARS or not isinstance(clean, str):\n"
     "            kept[shown] = clean\n",
     _T + "test_a_nested_value_is_kept_to_the_bound_a_value_is_kept_to"),
    # 4. the denial warnings
    ("the denial warnings mask four exact names at the top level, as on c310ba28", _AUDIT,
     "    return {_scrub(str(k)): (MASK if is_secret(k) else _clean(v, depth=1, words=False))\n",
     "    return {k: (MASK if k in SECRET else v)\n",
     _T + "test_the_denial_warning_masks_what_the_record_masks"),
    # 5. the file
    ("the fallback file is created as the umask leaves it", _AUDIT,
     "    where = _private(audit_path())\n",
     "    where = audit_path()\n",
     _T + "test_the_fallback_audit_file_is_created_readable_by_its_owner_alone"),
    ("a fallback file found wider is left as it is", _AUDIT,
     "        if had & 0o077:\n",
     "        if False:\n",
     _T + "test_a_fallback_audit_file_readable_by_others_is_made_private_and_said"),
    ("a fallback file made private is not said", _AUDIT,
     '            log.info("audit: %s was mode %s, readable by others; it is now 0o600", path, '
     "oct(had))\n",
     "            pass\n",
     _T + "test_a_fallback_audit_file_readable_by_others_is_made_private_and_said"),
]
