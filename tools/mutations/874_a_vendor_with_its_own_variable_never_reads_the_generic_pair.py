"""#874: a vendor that names its own variable is answered by it, and by nothing after it
(2026-10-25).

A Jira project that named no `token_env`, on a deployment with no `JIRA_API_TOKEN`, was handed the
deployment's generic pair — `OPENFACTORY_TRACKER_TOKEN`, then `OPENFACTORY_BOT_TOKEN`, a GitHub
token — and sent it to the Jira site, which answered 401 "different accounts" (measured
2026-10-19). The claims these cuts hold:

  - a row that names its variable (`CredentialRow.env`) is answered by `token_env` or that
    variable, and the walk ends there: the generic pair is for the row that names none (GitHub)
    and for a project of no kind;
  - the stop is that row's, not every row's: a GitHub axis and a legacy project still read the pair;
  - Jira's row names `JIRA_API_TOKEN`, so a Jira axis is in that family — and the family is read
    from the registry, so a Jira row that stopped naming it would be seen.
"""

TEST = "tests/test_the_vendors_credential_is_found_by_default.py"
CRED = "openfactory/credentials.py"
ROWS = "openfactory/adapters/credential/registry.py"

MUTATIONS = [
    ("THE DEFECT ITSELF: the walk goes on past the vendor's own variable to the generic pair",
     CRED,
     "        return credential_store.NOTHING\n    # A VENDOR THAT NEEDS NO CREDENTIAL",
     "        pass\n    # A VENDOR THAT NEEDS NO CREDENTIAL"),

    ("the stop is every row's: a GitHub axis and a project of no kind lose the pair", CRED,
     "    default = vendor_default_env(ref)\n    if default:",
     "    default = vendor_default_env(ref)\n    if True:"),

    ("Jira's row names no variable, so a Jira axis reads the pair like GitHub's", ROWS,
     '    return CredentialRow(env=SHIPPED_ENV["jira"])',
     '    return CredentialRow(env="")'),
]
