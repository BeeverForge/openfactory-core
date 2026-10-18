"""#652, proven by breaking it — `init`'s closing line is a command the reader can run.

THREE CLAIMS:

  1. **Run by the installer, `init` names no next command**, on either runtime: the installer
     declares itself (`OPENFACTORY_INSTALLER`) and starts the stack, or prints how to.
  2. **By hand, the environment file is named as the person can name it**: from the working
     directory when it lies inside it (resolved on both sides), otherwise as typed.
  3. **`--build` only where the compose file here builds the worker from a Dockerfile here.**

The guards drive the real `init` through `CliRunner` against this repository's own
`docker-compose.yml` and checkout, and replay the argv and environment a real stubbed
`sh install.sh` run produced.
"""

TEST = "tests/test_init_names_the_next_command_a_person_can_run.py"

CLI = "openfactory/cli.py"
INSTALLER = "install.sh"
INSTALLER_TEST = "tests/test_the_installer_builds_the_commands_it_says_it_does.py"

_LINE = ('        typer.echo(f"\\nthen: `docker compose --env-file {_named_as_passed(out)} '
         'up -d{build}`")\n')
_GUARD = ('    if (os.environ.get("OPENFACTORY_INSTALLER") or "").strip():\n'
          '        return\n')

_BLOCK = ('    if answers.runtime == "local":\n'
          "        # THE NEXT COMMAND IS THE ONE THAT STARTS IT. `docker compose --env-file …` is "
          "the other\n"
          "        # runtime's, and printing it here sent a person who had just said "
          "\"this machine\" to\n"
          "        # install Docker.\n"
          '        typer.echo(f"\\nthen: `openfactory up` — the engine, the worker and the '
          'panel, here. "\n'
          '                   f"({dest} is read by all three.)")\n'
          "    else:\n"
          '        build = " --build" if _builds_from_this_checkout(Path.cwd()) else ""\n')

MUTATIONS = [
    ("TODAY'S DEFECT: the closing line names the destination as written and always builds", CLI,
     _LINE,
     '        typer.echo(f"\\nthen: `docker compose --env-file {dest} up -d --build`")\n'),

    # THROUGH THE INSTALLER, TODAY'S DEFECT IS TWO SITES: with the guard in place the old line is
    # never reached there (measured: the one-site cut above stays green in INSTALLER_TEST), so the
    # row restores main's whole closing block.
    ("the same defect, seen through the installer: no guard and the old line", CLI,
     _GUARD + _BLOCK + _LINE,
     _BLOCK + '        typer.echo(f"\\nthen: `docker compose --env-file {dest} up -d --build`")\n',
     INSTALLER_TEST),

    ("the installer stops declaring itself", INSTALLER,
     '    set -- -e "OPENFACTORY_INSTALLER=1" "$@"\n',
     "",
     INSTALLER_TEST),

    ("`init` ignores the declaration", CLI,
     _GUARD,
     "    if False:\n        return\n"),

    ("`init` ignores the declaration, seen through the installer", CLI,
     _GUARD,
     "    if False:\n        return\n",
     INSTALLER_TEST),

    ("the guard covers the compose branch only, and the local line is printed under the "
     "installer again", CLI,
     _GUARD + '    if answers.runtime == "local":\n',
     '    if answers.runtime == "local":\n',
     INSTALLER_TEST),

    ("`--build` always", CLI,
     "    context = project_dir / str(build.get(\"context\", \".\"))\n"
     "    return (context / str(build.get(\"dockerfile\", \"Dockerfile\"))).is_file()\n",
     "    return True\n"),

    ("`--build` never", CLI,
     "    context = project_dir / str(build.get(\"context\", \".\"))\n"
     "    return (context / str(build.get(\"dockerfile\", \"Dockerfile\"))).is_file()\n",
     "    return False\n"),

    ("no compose file here is read as a checkout", CLI,
     "    except (OSError, UnicodeDecodeError, yaml.YAMLError, KeyError, TypeError):\n"
     "        return False\n",
     "    except (OSError, UnicodeDecodeError, yaml.YAMLError, KeyError, TypeError):\n"
     "        return True\n"),

    ("the destination is printed absolute", CLI,
     "        return str(Path(out).expanduser().resolve().relative_to(Path.cwd().resolve()))\n",
     "        return str(Path(out).expanduser().resolve())\n"),

    ("the destination is printed `expanduser`-ed", CLI,
     "    except ValueError:\n        return out\n",
     "    except ValueError:\n        return str(Path(out).expanduser())\n"),

    ("the build check asks the destination's directory instead of the working directory", CLI,
     '        build = " --build" if _builds_from_this_checkout(Path.cwd()) else ""\n',
     '        build = " --build" if _builds_from_this_checkout(dest.parent) else ""\n'),

    ("the comparison is made on unresolved paths", CLI,
     "        return str(Path(out).expanduser().resolve().relative_to(Path.cwd().resolve()))\n",
     "        return str(Path(out).expanduser().relative_to(Path.cwd()))\n"),
]
