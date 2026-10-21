"""An explicit `openfactory bot-token --key-path` is the key the App JWT is signed with, and no
option of the CLI reads the environment by itself (#905).

Claims:
  - the key at an explicit `--key-path` signs the JWT, over a key the environment holds as content
    or as a path, and with no environment at all (the defect: the flag was bound and never read);
  - the option carries no `envvar=`: the walk over every built command reads `param.envvar`, and
    `bot-token --help` shows no `[env var: …]` binding;
  - the walk reaches a sub-typer's command, so an `envvar=` there is caught too (not only on a
    top-level command);
  - an explicit path that cannot be read refuses, naming that path, and never falls back to the
    environment's key;
  - an empty `--key-path` (`"$NEW_PEM"` with the variable unset) is a path given, not "no flag":
    it refuses and never proves the environment's key;
  - `~` in the flag's value resolves against `HOME` (`app_private_key_at` expands it), as
    `OPENFACTORY_GH_APP_KEY` always did;
  - without the flag, `app_private_key()` still reads the path form through
    `app_private_key_at` (preservation).
"""

TEST = "tests/test_an_explicit_key_path_is_the_key_the_bot_token_signs_with.py"
ENV_WALK = "tests/test_no_option_of_the_cli_reads_the_environment_by_itself.py"
CLI = "openfactory/cli.py"
CREDENTIALS = "openfactory/credentials.py"

SIGNS = TEST + "::test_the_jwt_is_signed_by_the_key_at_key_path_and_not_by_the_environments"
ALONE = TEST + "::test_key_path_alone_with_the_two_id_flags_mints_with_no_environment_at_all"
TILDE = ALONE + "[tilde]"
REFUSES = (TEST + "::test_an_unreadable_key_path_refuses_naming_the_path_and_does_not_use_the_"
           "environments_key")
EMPTY = TEST + "::test_an_empty_key_path_refuses_and_does_not_use_the_environments_key"
WITHOUT_FLAG = TEST + "::test_without_the_flag_the_key_the_environment_names_by_path_is_still_used"
NO_ENVVAR = ENV_WALK + "::test_no_option_of_any_openfactory_command_declares_an_envvar"
HELP = ENV_WALK + "::test_the_bot_token_help_names_the_variables_in_prose_and_no_env_var_binding"
A_PATH_STILL_WORKS = "tests/test_the_app_key_reaches_every_entry_point.py::test_a_path_still_works"

_EXPLICIT = "            key = app_private_key_at(key_path)\n"
_REFUSAL = (
    '            typer.echo(f"✗ the App key at {key_path} could not be read '
    '({exc.strerror or exc}) — "\n'
    '                       "nothing was minted; pass a readable .pem or leave --key-path out '
    'to use "\n'
    "                       \"the deployment's key\", err=True)\n"
    "            raise typer.Exit(1) from None\n"
)

MUTATIONS = [
    # ── M1: the defect itself, the flag bound and the environment's key used ───────────────────
    ("M1 the explicit path is ignored: the environment's key signs (over B in the environment)",
     CLI, _EXPLICIT, "            key = app_private_key()\n", SIGNS),
    ("M1 the explicit path is ignored: the environment's key signs (with no environment)",
     CLI, _EXPLICIT, "            key = app_private_key()\n", ALONE),
    # ── M2: the envvar re-added ────────────────────────────────────────────────────────────────
    ("M2 --key-path is read from OPENFACTORY_GH_APP_KEY by typer (the walk)", CLI,
     "    key_path: str = typer.Option(\n        None,\n",
     '    key_path: str = typer.Option(\n        None, envvar="OPENFACTORY_GH_APP_KEY",\n',
     NO_ENVVAR),
    ("M2 --key-path is read from OPENFACTORY_GH_APP_KEY by typer (the help)", CLI,
     "    key_path: str = typer.Option(\n        None,\n",
     '    key_path: str = typer.Option(\n        None, envvar="OPENFACTORY_GH_APP_KEY",\n',
     HELP),
    # ── M3: a refusal becomes a fallback ───────────────────────────────────────────────────────
    ("M3 an unreadable explicit path falls back to the environment's key", CLI,
     _REFUSAL, "            key = app_private_key()\n", REFUSES),
    # ── M4: the refusal does not name the path ─────────────────────────────────────────────────
    ("M4 the refusal does not name the path it could not read", CLI,
     'typer.echo(f"✗ the App key at {key_path} could not be read',
     'typer.echo(f"✗ the App key could not be read', REFUSES),
    # ── M5: `~` is not expanded ────────────────────────────────────────────────────────────────
    ("M5 the key file's path is read without expanding ~", CREDENTIALS,
     "    return Path(path).expanduser().read_text()\n",
     "    return Path(path).read_text()\n", TILDE),
    # ── M6: preservation, the environment's path form ──────────────────────────────────────────
    ("M6 app_private_key no longer reads the path form (bot-token without the flag)", CREDENTIALS,
     "        return app_private_key_at(path)\n", "        return None\n", WITHOUT_FLAG),
    ("M6 app_private_key no longer reads the path form (the composition root)", CREDENTIALS,
     "        return app_private_key_at(path)\n", "        return None\n", A_PATH_STILL_WORKS),
    # ── M7: the walk reaches a sub-typer's command ─────────────────────────────────────────────
    ("M7 an option of a sub-typer's command (preview login --username) declares an envvar", CLI,
     '"--username", "-u", prompt=True,',
     '"--username", "-u", prompt=True, envvar="X",', NO_ENVVAR),
    # ── M8: an empty path is read as "no flag" ─────────────────────────────────────────────────
    ("M8 an empty --key-path takes the no-flag branch and proves the environment's key", CLI,
     "    if key_path is not None:\n", "    if key_path:\n", EMPTY),
]
