"""The typed reads are served under `/api/v1`, their old paths deprecated aliases, and the API's
description committed (#678, slice b), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/the_reads_are_served_under_api_v1.py

The claims, each a row:
  1. a typed read answers under `/api/v1/…`;
  2. its unversioned path is marked deprecated;
  3. a versioned path is in its alias's area at the gate — only a registered typed read's;
  4. the committed description says the package's version;
  5. every GET under `/api/` declares its model, or the contract names it as left out of
     `/api/v1/` with the reason (#940);
  6. a read left out has no `/api/v1/` form.
"""

TEST = "tests/test_the_api_is_versioned.py"
APP = "openfactory/api/app.py"
CONTRACT = "docs/reference/the-front-end-api.md"

MUTATIONS = [
    # 1. the versioned address
    ("a typed read is served only at its unversioned path", APP,
     '        app.get(API_V1 + path.removeprefix("/api"), **_reads(model), **extra)(handler)\n',
     ""),

    # 2. the alias, deprecated
    ("the alias is not marked deprecated", APP,
     "        app.get(path, deprecated=True, **_reads(model), **extra)(handler)",
     "        app.get(path, **_reads(model), **extra)(handler)"),

    # 3. the gate
    ("the gate reads a versioned path as the floor's", APP,
     "    path = _unversioned(path)\n    if path in",
     "    if path in"),

    # 3b. only a registered read is mapped
    ("any path under /api/v1 inherits its alias's area", APP,
     "    if any(read.match(path) for read in _VERSIONED_READS):",
     '    if path.startswith(API_V1 + "/"):'),

    # 4. the version
    ("the app does not say the package's version", APP,
     '              version=__version__)',
     '              version="0.1.0")'),

    # 5. typed, or named as left out with the reason
    ("a read the default front end makes declares no model again", APP,
     '@_read("/api/address", read_models.AddressRead)',
     '@app.get("/api/address")'),
    ("a read is left out of /api/v1 without a reason", CONTRACT,
     "| a file's bytes, as the person sent it, not a JSON body |",
     "|  |"),
    ("a typed read is named as left out", CONTRACT,
     "| GET | `/api/temporal/stream` | a stream",
     "| GET | `/api/projects` | the default front end reads it |\n"
     "| GET | `/api/temporal/stream` | a stream"),

    # 6. no /api/v1 form for a read left out
    ("a read left out is served under /api/v1 too", APP,
     '@app.get("/api/temporal/stream")\n',
     '@app.get("/api/v1/temporal/stream")\n@app.get("/api/temporal/stream")\n'),
]
