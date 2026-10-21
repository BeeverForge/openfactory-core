"""A parameter named `by` or `name` is refused by name and leaves its record, at the panel's and
the command line's doors (#694, PR #1039 review N1, 2026-10-21), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/694_a_parameter_named_by_is_refused_by_name.py

The claims: both doors hand `perform` what a caller sent as one mapping (`params=`), and `perform`
reads it. On c310ba28 a body naming `by` answered 500 and `-P by=…` a traceback, each with no
record. (`name` being positional-only has no row: with the mapping, nothing reaches `perform` as a
keyword named `name`, so a cut of it survives by construction.)
"""

TEST = "tests/test_a_parameter_named_like_performs_own_arguments_is_refused_by_name.py"

_T = TEST + "::"

MUTATIONS = [
    ("the panel spreads the body into perform's keywords", "openfactory/api/app.py",
     "    outcome = await actions.perform(name, by=_actor(request), params=body.params or {})\n",
     "    outcome = await actions.perform(name, by=_actor(request), **(body.params or {}))\n",
     _T + "test_the_panel_refuses_a_parameter_named_like_performs_own_and_records_the_call"),
    ("the command line spreads -P into perform's keywords", "openfactory/cli.py",
     "        name, by=_cli_actor(who), params=params))\n",
     "        name, by=_cli_actor(who), **params))\n",
     _T + "test_the_command_line_refuses_a_parameter_named_like_performs_own_and_records_the_call"),
    ("perform ignores the mapping a door hands it", "openfactory/actions/__init__.py",
     "    params = {**(params or {}), **named}\n",
     "    params = dict(named)\n",
     _T + "test_the_panel_refuses_a_parameter_named_like_performs_own_and_records_the_call"),
]
