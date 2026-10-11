"""The default front end is a setting: on by default, and off serves the API and no page (#561,
slice 2), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/561b_the_default_front_end_is_a_setting.py

The claims, each a row:

  1. the setting is read: off answers every page address with a 404 that says why, and on — the
     default — serves the page;
  2. a value that is neither keeps the page and says so in the log;
  3. every page route asks the setting, and the installer writes the line.
"""

TEST = "tests/test_the_default_front_end_is_a_setting.py"
APP = "openfactory/api/app.py"
DEPLOYMENT = "openfactory/onboarding/deployment.py"

MUTATIONS = [
    # 1. the setting
    ("the setting is never asked: the page is served with it off", APP,
     "    if not default_front_end_on():\n        return JSONResponse(",
     "    if False:\n        return JSONResponse("),
    ("off is read as on", APP,
     "    if value in _OFF:\n        return False",
     "    if False:\n        return False"),
    ("the page is off unless somebody turns it on, and an upgrade loses it", APP,
     'os.environ.get(DEFAULT_FRONT_END_ENV, "").strip().lower()',
     'os.environ.get(DEFAULT_FRONT_END_ENV, "off").strip().lower()'),
    ("the 404 does not say why", APP,
     'return JSONResponse({"detail": _NO_FRONT_END}, status_code=404',
     'return JSONResponse({"detail": "Not Found"}, status_code=404'),

    # 2. a value that is neither
    ("a typo takes the page away", APP,
     "                    DEFAULT_FRONT_END_ENV, value)\n    return True",
     "                    DEFAULT_FRONT_END_ENV, value)\n    return value in _ON"),
    ("a typo passes in silence", APP,
     # RE-PINNED 2026-10-11 (review of #611): said once per value and process
     "    if value not in _ON and value not in _SAID_NEITHER:\n",
     "    if False:\n"),
    ("the same typo is said on every page request", APP,
     "        _SAID_NEITHER.add(value)\n", ""),

    # 3. every route, and the installer
    ("a page route serves the panel by itself", APP,
     '    handed out unauthenticated."""\n    return _page()',
     '    handed out unauthenticated."""\n    return HTMLResponse(_read_panel(), headers=_NO_CACHE)'),
    ("the installer no longer writes the line", DEPLOYMENT,
     'OPENFACTORY_DEFAULT_FRONT_END=on\n""")',
     '""")'),
]
