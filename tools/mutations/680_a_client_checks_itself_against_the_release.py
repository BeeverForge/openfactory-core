"""#680 — a front end checks itself against a release, proven by breaking every rule it holds.

SEVEN CLAIMS, each cut here and each required to go red:

  1. **What the API answers is held, not only that a route exists.** An unnamed status, a body
     outside the release's model, a refusal without its sentence and a read never asked each pass
     unseen without their rule; a path parameter or a query the caller fills that never reaches
     the request leaves the success bodies unchecked.
  2. **What a client names and the API lacks fails, naming it** — a route, a socket, a field (a
     list's items read through), an event kind and its field.
  3. **One release on both sides, and the 401 the contract names**: another release, a version
     route that does not say one, the wrong 401 (with no credential as well as with one nobody
     issued), a gated deployment run without a credential and a credential it refuses each fail;
     an address that does not answer is a finding, never a traceback. A deprecated alias passes
     with its note, and a socket row naming fields fails.
  4. **The default front end's manifest is what the page calls**: the method each call names, a
     socket, the comments left out, a segment and a further segment the page concatenates, a
     call that reaches no route kept so the suite names it, and the kinds it branches on. What
     the text cannot say is named, never guessed: a method outside a literal in the call's own
     options, and an address whose route is a runtime value.
  5. **The API describes the refusals the suite found**: the board, a product's attachments and
     its documents name their 404.
  6. **The manifest and the command refuse by name** with the exit codes a CI job branches on:
     2 for a credential the run cannot use, 1 for an API that stops answering mid-run.
  7. **A run never waits without bound**: the command's client has a finite timeout.

The guard under test: `tests/test_a_client_checks_itself_against_the_release.py`.
"""

TEST = "tests/test_a_client_checks_itself_against_the_release.py"

CLIENT = "openfactory/conformance/client.py"
FRONT_END = "openfactory/conformance/front_end.py"
APP = "openfactory/api/app.py"
CLI = "openfactory/cli.py"

MUTATIONS = [
    # ── 1. what the API answers ───────────────────────────────────────────────────────────────────
    ("a status the description does not name passes", CLIENT,
     "    if status not in named | set(EVERY_ROUTE):",
     "    if False:"),

    ("a body outside the release's model passes", CLIENT,
     "            model.model_validate(body)\n",
     "            pass\n"),

    ("a refusal without a sentence passes", CLIENT,
     "    elif not _says_why(status, body):",
     "    elif False:"),

    ("a 422 listing what it could not read is taken for a refusal without a sentence", CLIENT,
     "    return isinstance(detail, list) if status == 422 else isinstance(detail, str) and bool("
     "detail)",
     "    return isinstance(detail, str) and bool(detail)"),

    ("no typed read the manifest names is asked", CLIENT,
     "            _ask(http, route, operation, model, credential, params, report)",
     "            pass"),

    ("the path parameters the caller fills are not filled", CLIENT,
     "quote(params.get(m.group(1), PROBE), safe=\"\")",
     "quote(PROBE, safe=\"\")"),

    ("the query parameters the caller fills are not sent", CLIENT,
     "    query = {p[\"name\"]: params[p[\"name\"]] for p in operation.get(\"parameters\", [])\n"
     "             if p.get(\"in\") == \"query\" and p.get(\"name\") in params}",
     "    query = {}"),

    # ── 2. what a client names and the API lacks ──────────────────────────────────────────────────
    ("a route the API does not have passes", CLIENT,
     "        if operation is None:\n            report.findings.append(",
     "        if operation is None:\n            continue\n            report.findings.append("),

    ("a socket the release does not have passes", CLIENT,
     "            if route.path not in sockets:",
     "            if False:"),

    ("a field the model does not declare passes", CLIENT,
     "    here = [schema]\n    for name in dotted.split(\".\"):",
     "    return True\n    here = [schema]\n    for name in dotted.split(\".\"):"),

    ("a list's items are not read through", CLIENT,
     "            elif node.get(\"type\") == \"array\" or \"items\" in node:\n"
     "                here.append(node.get(\"items\", {}))\n",
     ""),

    ("an event kind no stream sends passes", CLIENT,
     "        if use.kind not in events.KINDS:\n            report.findings.append(",
     "        if use.kind not in events.KINDS:\n            continue\n"
     "            report.findings.append("),

    ("a field an event's data does not declare passes", CLIENT,
     "            if not _has_field(data, dotted, data):",
     "            if False:"),

    # ── 3. one release, and the 401 ───────────────────────────────────────────────────────────────
    ("an API of another release passes", CLIENT,
     "    if body.get(\"version\") != ours:",
     "    if False:"),

    ("a 401 the contract does not name passes", CLIENT,
     "        if answer.status_code != 401 or not isinstance(body, dict) or body.get(\n"
     "                \"detail\") != \"unauthorized\":",
     "        if answer.status_code != 401:"),

    ("a gated deployment run without a credential is read as an open one", CLIENT,
     "        if bare.status_code == 401:",
     "        if False:"),

    ("a credential the API refuses is not named", CLIENT,
     "    if me.status_code != 200:",
     "    if False:"),

    ("a version route that does not answer 200 with an object passes", CLIENT,
     "    if answer.status_code != 200 or not isinstance(body, dict):\n"
     "        report.findings.append(_finding(\n            \"client.release\"",
     "    if False:\n"
     "        report.findings.append(_finding(\n            \"client.release\""),

    ("a credentialed run does not hold the 401 of no credential", CLIENT,
     "    for what, answer in ((\"no credential\", bare), (\"a credential nobody issued\", "
     "stranger)):",
     "    for what, answer in ((\"a credential nobody issued\", stranger),):"),

    ("a deprecated alias passes without its note", CLIENT,
     "            report.notes.append(f\"{name} is a deprecated alias: build on its /api/v1/ "
     "address\")",
     "            pass"),

    ("a socket row naming fields passes", CLIENT,
     "            elif route.fields:",
     "            elif False:"),

    ("an address that does not answer raises", CLIENT,
     "    except httpx.HTTPError as exc:\n        report.findings.append(_finding(\n"
     "            \"client.reachable\"",
     "    except ZeroDivisionError as exc:\n        report.findings.append(_finding(\n"
     "            \"client.reachable\""),

    # ── 4. the default front end's manifest is what the page calls ────────────────────────────────
    ("every call is read as a GET", FRONT_END,
     "    if named:\n        return named.group(1).upper()",
     "    if named:\n        return \"GET\""),

    ("a socket is read as a GET", FRONT_END,
     "    if callee.group(1) and callee.group(2) == \"WebSocket\":\n        return \"WS\"\n",
     ""),

    ("a block comment's call is read as a call", FRONT_END,
     "    code = re.sub(r\"/\\*.*?\\*/|<!--.*?-->\", \"\", page, flags=re.S)",
     "    code = page"),

    ("a line comment's call is read as a call", FRONT_END,
     "    return \"\\n\".join(line for line in code.splitlines() if not line.strip()"
     ".startswith(\"//\"))",
     "    return code"),

    ("an expression after a word is never a further segment", FRONT_END,
     "    variants = [_join(pieces, after_a_word=\"\"), _join(pieces, after_a_word=\"/x\")]",
     "    variants = [_join(pieces, after_a_word=\"\")]"),

    ("an expression after a `/` is not a segment", FRONT_END,
     "        text += (\"x\" if text.endswith(\"/\") else after_a_word) + piece",
     "        text += after_a_word + piece"),

    ("what the page concatenates to an address is not read", FRONT_END,
     "        plus = _PLUS.match(code, n)",
     "        plus = None"),

    ("a call that reaches no route is dropped", FRONT_END,
     "            elif n == 0:\n                out.add((method, address))\n",
     ""),

    ("options that are not an object literal are read as a GET", FRONT_END,
     "        return UNREAD\n    top = _top_level(",
     "        return \"GET\"\n    top = _top_level("),

    ("a method that is not a string literal, or a spread, is read as a GET", FRONT_END,
     "    if \"...\" in top or re.search(",
     "    if False and re.search("),

    ("a method a header nests is read as the call's", FRONT_END,
     "    named = _METHOD.search(top)",
     "    named = _METHOD.search(options)"),

    ("an address whose route is a runtime value claims every route of one segment", FRONT_END,
     "    if _UNREAD_ROUTE.match(path):",
     "    if False:"),

    ("a runtime value right after /api/v1/ claims every v1 route of one segment", FRONT_END,
     "_UNREAD_ROUTE = re.compile(r\"^/api/(?:v1/)?\\0\")",
     "_UNREAD_ROUTE = re.compile(r\"^/api/\\0\")"),

    ("a call the page's reader could not read is taken for a route", CLIENT,
     "        if route.method == UNREAD or UNREAD_SEGMENT in route.path:",
     "        if False:"),

    ("a call the page's reader could not read is refused as a manifest error", CLIENT,
     "        if method not in METHODS and method != UNREAD:",
     "        if method not in METHODS:"),

    ("the kinds the page branches on are not read", FRONT_END,
     "            \"events\": [{\"kind\": k} for k in sorted(set(_KIND.findall(_code(page))))]}",
     "            \"events\": []}"),

    # ── 5. the refusals the suite found, described ────────────────────────────────────────────────
    ("the board does not describe its 404", APP,
     "@_read(\"/api/board/{project}\", read_models.BoardRead, refusals={\n"
     "    404: _NO_SUCH_PROJECT})",
     "@_read(\"/api/board/{project}\", read_models.BoardRead)"),

    ("a product's attachments do not describe their 404", APP,
     "@_read(\"/api/product/{project}/attachments\", read_models.AttachmentLimitsRead, refusals={\n"
     "    404: _NO_SUCH_PROJECT})",
     "@_read(\"/api/product/{project}/attachments\", read_models.AttachmentLimitsRead)"),

    ("a product's documents do not describe their 404", APP,
     "@_read(\"/api/product/{project}/documents\", read_models.DocumentsRead, refusals={\n"
     "    404: _NO_SUCH_PROJECT})",
     "@_read(\"/api/product/{project}/documents\", read_models.DocumentsRead)"),

    # ── 6. the manifest and the command ───────────────────────────────────────────────────────────
    ("a key the suite does not read is ignored", CLIENT,
     "    if unknown:\n        raise refuse(",
     "    if False:\n        raise refuse("),

    ("a manifest of another schema is read", CLIENT,
     "    if data.get(\"schema\") != SCHEMA:",
     "    if False:"),

    ("an empty manifest is read", CLIENT,
     "    if not routes and not events:",
     "    if False:"),

    ("a run with findings exits 0", CLI,
     "                   f\"{declared.client}\")\n        raise typer.Exit(1)\n",
     "                   f\"{declared.client}\")\n"),

    ("a credential variable that is not set is run without one", CLI,
     "            typer.echo(f\"--token-env names {token_env}, and it is not set in this "
     "environment\")\n            raise typer.Exit(2)\n",
     "            typer.echo(f\"--token-env names {token_env}, and it is not set in this "
     "environment\")\n"),

    ("a credential the run cannot use exits 1, as a broken client", CLI,
     "                   f\"was held for {declared.client}\")\n        raise typer.Exit(2)\n",
     "                   f\"was held for {declared.client}\")\n"),

    ("an API that stops answering mid-run is a traceback", CLI,
     "    except httpx.HTTPError as exc:\n        # the suite's first request",
     "    except ZeroDivisionError as exc:\n        # the suite's first request"),

    ("a request may wait for ever", CLI,
     "    return httpx.Client(base_url=address.rstrip(\"/\"), timeout=10.0)",
     "    return httpx.Client(base_url=address.rstrip(\"/\"), timeout=None)"),

    ("the credential its variable holds is not presented", CLI,
     "        credential = os.environ.get(token_env, \"\").strip()",
     "        credential = \"\""),
]
