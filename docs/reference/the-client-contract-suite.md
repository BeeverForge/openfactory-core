# The client contract suite — checking a front end against a release

A front end built on OpenFactory's API — the default panel, or a screen of your own — can prove,
against a given release, that it and the API still agree. You declare what your client uses in a
small manifest. The suite asks a running API for each of those things and holds every answer to
what the release promises. It ships in the package, and the core's own tests hold the default
front end to it, so it is the same test the default front end has to pass.

```bash
openfactory conformance-client http://localhost:8787 --manifest my-client.json --token-env MY_TOKEN
```

```
CONFORMANT — acme dashboard: 4 route(s) and 2 event kind(s) hold against http://localhost:8787, 5 answer(s) asked
```

The suite only reads. It calls the typed reads your manifest names (the `GET` routes whose answer
declares a model). A route that writes, a stream and a file are checked against the description
and never called, so a run against a production deployment changes nothing in it.

## 1. The manifest: what your client uses

```json
{
  "schema": "openfactory.client/1",
  "client": "acme dashboard",
  "routes": [
    {"method": "GET", "path": "/api/v1/whoami", "fields": ["display", "scopes"]},
    {"method": "GET", "path": "/api/v1/budget", "fields": ["summary", "rows.state"]},
    {"method": "POST", "path": "/api/act/{name}"},
    {"method": "WS", "path": "/api/product/stream"}
  ],
  "events": [
    {"kind": "said", "fields": ["text"]},
    {"kind": "ended"}
  ]
}
```

- `routes` are the routes your client calls, written as the contract's table writes them
  ([the front-end API](the-front-end-api.md), section 3): the method (`WS` for a socket) and the
  path with its `{parameters}`.
- `fields` are the fields of a route's answer your client reads. A dotted name reads into an
  object, and a list's items are read through, so `rows.state` is the `state` of each row. A field
  counts only if the model declares it. A key the API happens to send and no model names is not one
  a release promises to keep.
- `events` are the event kinds your client branches on, and the fields of their `data` it reads, as
  [`events.schema.json`](events.schema.json) names them.

A key the suite does not read, a method it does not know or an empty manifest is refused in one
sentence, exit 2. A key that is silently ignored would be a client that thinks it declared
something it did not.

## 2. What the suite checks

| rule | what fails it |
|---|---|
| `client.reachable` | the address does not serve the API's description at `/openapi.json` |
| `client.release` | the API runs another release than the suite's (the finding names both and the `pip install` that matches) |
| `client.credential` | the deployment asks for a credential and none was given, or the one given is refused |
| `client.refusal-401` | no credential, or one nobody issued, is not the contract's `401 {"detail": "unauthorized"}` |
| `client.route` | a route the manifest names is not a route of the API, or not with that method |
| `client.field` | a field the manifest names is not one the route's answer declares |
| `client.event`, `client.event-field` | an event kind no stream of the release sends, or a field its data does not declare |
| `client.answer-status` | a read answered a status its description does not name, beyond the `401`, `403` and `503` the contract names for every route |
| `client.answer-model` | a read said yes with a body that is not the release's model for it |
| `client.refusal-by-name` | a read refused without a `detail` sentence |

A route named in the manifest that is a deprecated alias passes, with a `NOTE` naming its
`/api/v1/` address. The run exits 0 when nothing is broken, and 1 otherwise, after listing every
finding.

**The parameters.** `--param project=acme` fills a route's `{project}` and any query parameter its
description declares by that name. A path parameter you do not fill is a name no deployment holds,
so a read that takes a project answers its refusal, and the refusal is what is checked. Fill them
to have the success bodies checked as well.

**The credential.** `--token-env` names the environment variable that holds the credential. The
credential itself is never an argument, so it never reaches a process list or a CI log. Without
one, the deployment must answer without one: the suite says the 401 was not checked, and against a
deployment that asks for one it fails `client.credential`.

## 3. Against a pinned release

The models a body is held to, and the event kinds, are those of the release the suite ships in. So
run the suite of the release your client pins, against an API of that release. Either install the
same version:

```bash
pip install openfactory==0.8.0
openfactory conformance-client http://localhost:8787 --manifest my-client.json --param project=acme
```

or run it from the image the API runs, which carries the same package:

```bash
docker run --rm --network host -v "$PWD/my-client.json:/my-client.json:ro" \
  ghcr.io/open-factory-digital/openfactory-worker:v0.8.0 \
  openfactory conformance-client http://localhost:8787 --manifest /my-client.json
```

The panel the image serves answers the API with or without the default front end turned on
(`OPENFACTORY_DEFAULT_FRONT_END`), so a deployment that runs only your screens is checked the same
way.

### In CI

A job that starts the pinned image, waits until it answers, and runs the suite against it.
Upgrading is then one change, the version in `env:`, and the job says what the upgrade breaks
before your users find out:

```yaml
name: client contract
on: [pull_request]
jobs:
  contract:
    runs-on: ubuntu-latest
    env:
      OPENFACTORY_VERSION: 0.8.0
      CLIENT_TOKEN: ci-only-credential
    steps:
      - uses: actions/checkout@v4
      - name: start the API of the pinned release
        run: |
          docker run -d --name api -p 8787:8787 -e OPENFACTORY_PANEL_TOKEN="$CLIENT_TOKEN" \
            ghcr.io/open-factory-digital/openfactory-worker:v$OPENFACTORY_VERSION \
            python -m openfactory.cli serve --host 0.0.0.0 --port 8787
          for _ in $(seq 60); do curl -fs http://localhost:8787/healthz && break; sleep 1; done
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install "openfactory==$OPENFACTORY_VERSION"
      - name: the client contract suite
        run: openfactory conformance-client http://localhost:8787 --manifest my-client.json --token-env CLIENT_TOKEN
```

## 4. The default front end is held to the same suite

The default front end's manifest is read from the page the package ships each time it is asked
for (`openfactory.conformance.front_end`), never written by hand. The routes are the addresses the
page calls, with the method each call names, and the event kinds are the ones it compares a frame's
`kind` with. So the page and the manifest cannot drift. Without `--manifest`, the command checks a
deployment against it. `python -m openfactory.conformance.front_end` prints it, which is also a
worked example of the shape.

What cannot be read off the page's text is written so the run names it, never guessed: a call
whose method is not a string literal in its own options (`mfetch(u, o)`, `method: m`, `{...o}`)
has the method `?`, and an address whose route is itself a runtime value (`` `/api/${x}` ``) is
written `/api/${…}`. Each fails `client.route`, naming the call, the way a call to a route the
release does not have does.

`tests/test_a_client_checks_itself_against_the_release.py` runs the suite with that manifest
against the app on every run of the core's suite: populated, holding nothing, and with a
credential. A change to the API that takes away something the page uses fails there, naming it.

## 5. What is not here yet

- **The streams' frames.** A socket in the manifest is checked as a route of the release, and an
  event kind against the release's event models. Neither is opened and watched: the stream that
  sends the typed envelope, with an `id` to resume from, is not served yet (section 5 of
  [the front-end API](the-front-end-api.md)). Checking its envelope, its ordering and its resume
  is the suite's next part.
- **The default front end's fields.** The page reads a body through variables a reading of its
  text cannot follow, so its manifest names routes and event kinds and no field. A client of your
  own names its fields.
- **What a route that writes answers.** Writes are checked against the description only. Calling
  them would change the deployment the suite runs against.
