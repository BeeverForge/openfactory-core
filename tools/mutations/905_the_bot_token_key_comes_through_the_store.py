"""`openfactory bot-token` reads the App key through the credential store and has no flag for it (#905).

Run:  .venv/bin/python tools/mutate.py tools/mutations/905_the_bot_token_key_comes_through_the_store.py

Row 1 is the family's rule: an option that takes its default from the environment, the defect
itself. Rows 2-3 are what the person reads: `--help` and the refusal name the store.
"""

TEST = "tests/test_the_bot_token_command_reads_its_key_through_the_store.py"
CLI = "openfactory/cli.py"

MUTATIONS = [
    ("the flag comes back, its default read by typer from the environment", CLI,
     '    app_id: str = typer.Option(None, help="GitHub App ID (default: OPENFACTORY_GH_APP_ID)"),\n'
     "    installation_id: str = typer.Option(\n",
     '    app_id: str = typer.Option(None, help="GitHub App ID (default: OPENFACTORY_GH_APP_ID)"),\n'
     '    key_path: str = typer.Option(None, envvar="OPENFACTORY_GH_APP_KEY", help="the .pem"),\n'
     "    installation_id: str = typer.Option(\n"),
    ("`--help` stops saying where the key comes from", CLI,
     "    The App key comes through the credential store, as every credential the factory reads:\n"
     "    OPENFACTORY_GH_APP_KEY_CONTENT (the PEM itself) or OPENFACTORY_GH_APP_KEY (a path to it),\n"
     "    asked of the store OPENFACTORY_CREDENTIAL_STORE declares and then of the environment. There\n"
     "    is no flag for it.\n\n",
     ""),
    ("the refusal names the variables and not the store they are read from", CLI,
     '            "OPENFACTORY_GH_APP_KEY (a path) or OPENFACTORY_GH_APP_KEY_CONTENT (the PEM itself), "\n'
     '            "read through the credential store (the one OPENFACTORY_CREDENTIAL_STORE declares, "\n'
     '            "then the environment)",\n',
     '            "OPENFACTORY_GH_APP_KEY (a path) or OPENFACTORY_GH_APP_KEY_CONTENT (the PEM itself)",\n'),
]
