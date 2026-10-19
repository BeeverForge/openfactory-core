"""#743: one deployment serves one GitHub organisation, and `openfactory doctor` checks it.

The claims, each held by one named test and broken here by one cut:
- the App installation's account is compared with the one organisation the registry names, and
  a mismatch fails; GitHub logins compare without case;
- with no App configured the line says "not applicable" first and verifies nothing; an App that
  could not be read is never a pass;
- a registry that spans organisations fails the line in exactly the sentence the load path logs
  (`registry.spanning_message`), with or without an App;
- the read is `GET /app/installations/{id}` signed with the App's own JWT — nothing is minted —
  and bounded at ten seconds;
- the line is reachable: the live probe set builds it and `diagnose` emits it under its own id,
  the id `registry.py`'s docstring promises;
- `docs/configuration.md` §5 has the section that states the rule.

Every row names the one test it must turn red, so a cut that some OTHER test happens to catch
does not pass for the guard that claims it.
"""

ADAPTER = "openfactory/adapters/github_app.py"
REGISTRY = "openfactory/registry.py"
DOCTOR = "openfactory/doctor.py"
CONFIGURATION = "docs/configuration.md"

LINE = "tests/test_the_doctor_asks_the_app_which_organisation_it_is_installed_on.py"
SPANNING = "tests/test_a_registry_that_spans_organisations_fails_the_doctor.py"
READ = "tests/test_the_app_installation_is_read_with_the_apps_own_jwt_and_mints_nothing.py"
WRITTEN = "tests/test_the_one_organisation_rule_is_written_where_an_operator_reads.py"

TEST = LINE

MUTATIONS = [
    # ── the comparison (registry.installation_scope_line) ───────────────────────────────────────
    ("an installation on another organisation passes — the mismatch branch answers ok", REGISTRY,
     '    return (False, f"the GitHub App installation this deployment authenticates as is on '
     '{login}, "',
     '    return (True, f"the GitHub App installation this deployment authenticates as is on '
     '{login}, "',
     f"{LINE}::test_an_installation_on_another_organisation_fails_naming_both_and_the_repair"),

    ("the comparison is case-sensitive, so `Acme` in the registry fails an installation on `acme`",
     REGISTRY,
     "    if owner.casefold() == login.casefold():",
     "    if owner == login:",
     f"{LINE}::test_the_organisation_is_compared_as_github_compares_logins_without_case"),

    ("no App reads as a verified scope — the line no longer begins with NOT_APPLICABLE", REGISTRY,
     '        return (True, NOT_APPLICABLE + "no GitHub App installation is configured for this "',
     '        return (True, "the scope is fine: no GitHub App installation is configured for this "',
     f"{LINE}::test_no_app_is_reported_as_not_applicable_and_not_as_a_verified_scope"),

    ("an installation that could not be read is reported as a pass", REGISTRY,
     '        return (False, f"the GitHub App installation could not be read: {reason}",',
     '        return (True, f"the GitHub App installation could not be read: {reason}",',
     f"{LINE}::test_an_installation_that_could_not_be_read_is_not_a_pass"),

    # ── the spanning registry (S2) ──────────────────────────────────────────────────────────────
    ("the spanning branch is gone — a registry over two organisations reads not applicable",
     REGISTRY,
     "    if len(by_owner) > 1:\n        return (False, spanning_message(by_owner),",
     "    if False:\n        return (False, spanning_message(by_owner),",
     f"{SPANNING}::test_a_spanning_registry_fails_doctor_with_no_app_configured"),

    # The plan placed the reworded sentence "in doctor"; since the sentences moved beside
    # `spanning_message` (the vendor guard's LEDGER), this is the one place the line's spanning
    # words are chosen, so the rewording is cut here.
    ("the line says the spanning in its own words instead of the sentence the load path logs",
     REGISTRY,
     "        return (False, spanning_message(by_owner),",
     '        return (False, "this registry spans more than one GitHub organisation: "\n'
     '                + ", ".join(sorted(by_owner)),',
     f"{SPANNING}::test_a_spanning_registry_fails_doctor_with_the_sentence_the_load_logs"),

    # ── the read (adapters/github_app.installation_account) ─────────────────────────────────────
    ("the read mints an installation token to ask instead of signing the App's JWT", ADAPTER,
     "        app_jwt = _app_jwt(app_id, private_key)\n    except Exception as exc:",
     "        app_jwt = mint_installation_token(app_id=app_id, private_key=private_key,\n"
     "                                          installation_id=installation_id)[0]\n"
     "    except Exception as exc:",
     f"{READ}::test_no_installation_token_is_minted_to_ask"),

    # The plan's cut was `timeout=None`, but that also breaks the reason's `{timeout:g}`, so the
    # test went red on a TypeError rather than on the bound. A minute is a bound the doctor
    # should not wait on, and leaves the sentence intact: red on `0 < timeout <= 10` alone.
    ("the read waits a minute — a firewalled box holds the doctor six times longer", ADAPTER,
     "installation_id: str, timeout: float = 10.0",
     "installation_id: str, timeout: float = 60.0",
     f"{READ}::test_a_read_that_times_out_is_a_reason_and_not_a_raise"),

    # ── reachability (doctor) ───────────────────────────────────────────────────────────────────
    ("the live probe set no longer builds the line's probe", DOCTOR,
     "        installation_scope=_installation_scope_probe,\n    )",
     "    )",
     f"{READ}::test_the_live_probes_ask_the_installation_and_doctor_reports_it"),

    ("`diagnose` no longer emits the line, so `--json` has no such id", DOCTOR,
     "        *([_guarded(INSTALLATION_SCOPE, lambda: _installation_scope(probes))]\n"
     "          if probes.installation_scope else []),\n",
     "",
     f"{LINE}::test_the_check_is_a_line_of_the_json_document_under_its_own_id"),

    ("…and the check `registry.py`'s docstring promises is one doctor does not run", DOCTOR,
     "        *([_guarded(INSTALLATION_SCOPE, lambda: _installation_scope(probes))]\n"
     "          if probes.installation_scope else []),\n",
     "",
     f"{SPANNING}::test_the_check_the_registry_promises_is_a_check_doctor_runs"),

    # ── the rule is written (S3) ────────────────────────────────────────────────────────────────
    ("the configuration reference's section is renamed so no heading names one organisation",
     CONFIGURATION,
     "### One deployment, one GitHub organisation",
     "### Deployments and GitHub",
     f"{WRITTEN}::test_the_configuration_reference_states_the_rule_its_reason_and_the_way_to_run_two"),
]
