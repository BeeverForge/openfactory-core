# The front end's API — what a screen built on OpenFactory may rely on

OpenFactory's core serves an API, and the panel is its **default front end**: a page that uses this
API and nothing else (#561). A deployment may turn the page off (`OPENFACTORY_DEFAULT_FRONT_END`,
see `docs/configuration.md`) and build screens of its own on the same API. This document is that
API's contract: the credentials, the refusals, every route, and the streams.

It is pinned: `tests/test_the_front_end_api_is_a_contract.py` fails when a route exists that this
document does not list, when a row here names a route that does not exist or sits in another area,
and when the default front end calls anything not listed here.

## 1. Credentials

**One credential, three ways to present it**, read in this order by every route and every stream:

| how | where it is used |
|---|---|
| `Authorization: Bearer <credential>` | `fetch` and any program |
| the `openfactory_token` cookie (`__Host-openfactory_token` when the panel is served over TLS) | a browser on the API's own origin |
| `?token=<credential>` | an `EventSource`, which cannot set a header |

**Nothing configured means open.** With no credential configured on the deployment
(`OPENFACTORY_PANEL_TOKEN(S)`, `OPENFACTORY_PRODUCT_TOKEN(S)`, `OPENFACTORY_BOARD_TOKEN(S)`, an
identity provider) every route
answers without one: the local-development posture, never the production one.

**Areas.** A credential may act in the **floor** (the factory: jobs, boards, projects), in the
**product** area (the product role, its documents and attachments), or in both (an unscoped
credential). `GET /api/whoami` answers which, for any credential, and is how a screen decides what
to draw for itself. The product area is every path under `/api/product/` and every catalogue row
named `product_*`; every other path under `/api/` is the floor, with one read the product area
makes too: `GET /api/board/{project}` for a project with a product role, never with `?pr=` (#562).

**A dashboard on another origin** is admitted by `OPENFACTORY_PANEL_ORIGINS`, which names the
origins explicitly; a CORS preflight is answered without a credential, and the request after it is
gated like any other.

## 2. Refusals

Every refusal is JSON with a `detail` sentence — but for the framework's 422, whose `detail` is
the list of what it could not read:

| status | when | body |
|---|---|---|
| 401 | no credential, or one nobody issued | `{"detail": "unauthorized"}`, plus `"login": "<path>"` when the deployment's identity provider has a login page |
| 403 | a credential scoped away from the path's area | `{"detail": "this credential is scoped to <areas> and that is part of the <area>."}` |
| 503 | the identity provider cannot check anybody right now | `{"detail": "identity provider unavailable…"}` |
| 4xx from an action | a catalogued action refused what was asked | `{"detail": "<the action's own sentence>"}` |
| 4xx from a read | a read refused what was asked — a project it does not hold, a parameter past its declared bound; `openapi.json` names each status a read refuses with | `{"detail": "<the read's own sentence>"}` |
| 422 | a parameter or a body could not be read as the type the route declares (a `limit` that is not a number) | `{"detail": [{"loc": ["query", "limit"], "msg": "…", …}]}` — one entry per field; `openapi.json` names it `HTTPValidationError` |

A refusal from `POST /api/act/{name}` is the action's whole outcome — `ok`, `message`, `code`,
`data` and `detail` — and `data.reason` says why in a word a program branches on: the `code` itself
where nothing finer applies, or one of `bad_parameters`, `bad_ref`, `out_of_scope`, `not_admin`,
`engine_unreachable`, `raised`, `reported_nothing`, and `unknown_action` for a name no action has.
`GET /api/v1/actions` lists, as `refusals`, every reason each action can answer.

**A product row's refusal is a refusal, not a 500.** When the product role declines a write on
purpose, a `product_*` row (and `card_close`, `card_remove`) answers with the role's own sentence as
`message`, and with the role's word in `data.refusal`:

| `data.refusal` | status | `code` |
|---|---|---|
| `not_yours` | 403 | `denied` |
| `not_found` | 404 | `not_found` |
| `not_waiting`, `already_closed`, `already_there` | 409 | `conflict` |
| `not_valid` | 400 | `invalid` |

**`data.refusal` has two meanings, and `ok` says which.** On an answer with `ok: false` from the
rows above it is the product role's word, one of the table's. On an answer with `ok: true` from
`card_create`, `card_edit` and `card_check` it is what pickup's spec gate would say about the card:
`""` when pickup would take it, the gate's sentence when it would not. No row answers both — the
three card rows never render a product write, and a product write's answer carries the word only
when it is not ok — so a program reads the word when `ok` is false and the verdict when it is true.

`data.reason` stays the code, so the list of reasons above is unchanged. Only a write the product
role tried and that did not happen — the board unreadable when the role reads it, the forge down —
answers 500 `failed`; the row's own card check, which runs first, still answers a board it cannot
read as 409 `conflict` (a known limitation,
[#969](https://github.com/Open-Factory-Digital/openfactory-core/issues/969)). A 500 `failed` from
one of these rows that writes, or from `product_refine_card`, `product_align_card`,
`product_break_down`, `product_baseline` and `product_answer` (which the worker runs), carries
`data.reference`, and the panel's log line for that failure carries the same `reference=…` — for a
write the role reported, the `OPENFACTORY_PRODUCT_FAILURE_ANSWERED` line. The rows that only read
or converse — `product_pending`, `product_needs_action`, `product_say` and `product_queue` — do
not carry one yet. A row whose implementation raised answers `code: "failed"` with
`data.reason: "raised"`, and its `data.reference` names the `action … raised` log line.

A socket is refused before it is accepted: the upgrade is answered with a 403 and closed with code
**1008** for a refusal, **1011** when nobody could be judged.

## 3. Routes

Every route under `/api/`. **Area** is the area a scoped credential must hold; "every credential"
means any credential the deployment issued.

<!-- routes:start -->
| method | path | area | what it is |
|---|---|---|---|
| POST | `/api/act/{name}` | floor; a `product_*` row: product | run one catalogued action: `{"params": {...}}` |
| GET | `/api/actions` | floor | deprecated alias of `/api/v1/actions` |
| GET | `/api/address` | floor | how a repository address would be read, before a project is added |
| GET | `/api/attention` | floor | deprecated alias of `/api/v1/attention` |
| GET | `/api/board/{project}` | floor; product, for a project with a product role and without `?pr=` | deprecated alias of `/api/v1/board/{project}` |
| GET | `/api/budget` | floor | deprecated alias of `/api/v1/budget` |
| GET | `/api/coordinator/messages` | floor | the tech-lead's recent narrated updates |
| GET | `/api/decisions` | floor | deprecated alias of `/api/v1/decisions` |
| GET | `/api/factory/{project}` | floor | a project's cockpit: harness, credentials, links |
| GET | `/api/floor` | floor | deprecated alias of `/api/v1/floor` |
| GET | `/api/floor/{project}` | floor | deprecated alias of `/api/v1/floor/{project}` |
| GET | `/api/inbox` | floor | deprecated alias of `/api/v1/inbox` |
| GET | `/api/jobs` | floor | deprecated alias of `/api/v1/jobs` |
| POST | `/api/jobs` | floor | start a local job (the `start` action) |
| GET | `/api/jobs/{project}/{issue}/detail` | floor | deprecated alias of `/api/v1/jobs/{project}/{issue}/detail` |
| GET | `/api/jobs/{project}/{issue}/events` | floor | one run's log |
| GET | `/api/jobs/{project}/{issue}/stream` | floor | one run's log as it is written (stream, section 4) |
| GET | `/api/loops/{project}` | floor | deprecated alias of `/api/v1/loops/{project}` |
| GET | `/api/messages/{project}` | floor | deprecated alias of `/api/v1/messages/{project}` |
| POST | `/api/messages/{project}/answer` | floor | a person's answer to a question the factory asked |
| POST | `/api/messages/{project}/suggestion` | floor | a person's yes to the one action the tech-lead proposed |
| GET | `/api/metrics` | floor | deprecated alias of `/api/v1/metrics` |
| GET | `/api/preview/{project}/{unit}` | every credential | one unit's preview, and a key into it |
| POST | `/api/preview/{project}/{unit}/own_shape` | every credential | let a preview run its change's own shape |
| POST | `/api/preview/{project}/{unit}/rebuild` | every credential | build a preview again from its pull request's head |
| POST | `/api/preview/{project}/{unit}/start` | every credential | start a preview |
| POST | `/api/preview/{project}/{unit}/stop` | every credential | take a preview down, its logs kept |
| GET | `/api/product/projects` | product | deprecated alias of `/api/v1/product/projects` |
| WS | `/api/product/stream` | product | the conversation with the product role (stream, section 4) |
| GET | `/api/product/{project}/attachments` | product | deprecated alias of `/api/v1/product/{project}/attachments` |
| POST | `/api/product/{project}/attachments` | product | keep one file for a message |
| GET | `/api/product/{project}/attachments/{ident}` | product | a file sent in one of the person's conversations |
| GET | `/api/product/{project}/documents` | product | deprecated alias of `/api/v1/product/{project}/documents` |
| GET | `/api/product/{project}/documents/file/{path:path}` | product | one of the product's documents, as it is |
| GET | `/api/product/{project}/search` | product | deprecated alias of `/api/v1/product/{project}/search` |
| GET | `/api/projects` | floor | the projects this deployment runs |
| POST | `/api/projects` | floor | add a project |
| POST | `/api/projects/{name}/enabled` | floor | turn a project's pickup on or off |
| POST | `/api/projects/{project}/scan` | floor | read a project's queue now, without waiting for the next tick |
| GET | `/api/promote/{project}/{issue}` | floor | what the production approval asks: the version, the bumps, the approvers |
| POST | `/api/promote/{project}/{issue}` | floor | release a local job to production |
| WS | `/api/stream` | floor | what changed, as it changes (stream, section 4) |
| POST | `/api/temporal/act/{project}/{issue}` | floor | a person's decision on a parked job |
| POST | `/api/temporal/approve/{project}/{issue}` | floor | the production approval, sent to the parked job |
| GET | `/api/temporal/jobs` | floor | deprecated alias of `/api/v1/temporal/jobs` |
| POST | `/api/temporal/jobs` | floor | start a durable job (the `start` action) |
| GET | `/api/temporal/stream` | floor | the durable jobs' state as it changes (stream, section 4) |
| GET | `/api/v1/actions` | floor | the catalogue of actions this deployment can be asked to do |
| GET | `/api/v1/attention` | floor | the jobs that need a person |
| GET | `/api/v1/board/{project}` | floor; product, for a project with a product role and without `?pr=` | a project's board, as its tracker holds it |
| GET | `/api/v1/budget` | floor | the API budget of the trackers this deployment reads |
| GET | `/api/v1/decisions` | floor | every job parked on a person's decision, with its question and options |
| GET | `/api/v1/floor` | floor | whether the factory is working, for every project |
| GET | `/api/v1/floor/{project}` | floor | whether the factory is working, for one project |
| GET | `/api/v1/inbox` | floor | what needs a person right now, in one shape for every channel |
| GET | `/api/v1/jobs` | floor | the local jobs |
| GET | `/api/v1/jobs/{project}/{issue}/detail` | floor | one job's briefing: runtime, cost, pull request, why it is where it is |
| GET | `/api/v1/loops/{project}` | floor | everything the agents are still waiting on |
| GET | `/api/v1/messages/{project}` | floor | what the factory has said to a project, and what it waits to hear |
| GET | `/api/v1/metrics` | floor | spend by period, model, harness and role |
| GET | `/api/v1/product/projects` | product | the projects that have a product role |
| GET | `/api/v1/product/{project}/attachments` | product | what a message may carry, before a file is sent |
| GET | `/api/v1/product/{project}/documents` | product | the product's documents as their ingestion found them |
| GET | `/api/v1/product/{project}/search` | product | one product's published knowledge, searched with `q` and `limit`, in the product owner's ranking — a blank `q` finds nothing, a `q` past its declared length is a 400, and a project with no product role is the same 404 an unknown project is |
| GET | `/api/v1/temporal/jobs` | floor | the jobs, live, from the durable engine |
| GET | `/api/v1/version` | floor | which version this deployment runs, and every add-on installed into it (below) |
| GET | `/api/v1/whoami` | every credential | who this credential is, and which areas it may act in |
| GET | `/api/whoami` | every credential | deprecated alias of `/api/v1/whoami` |
<!-- routes:end -->

**Payloads.** The API describes its own HTTP routes at `/openapi.json` (and `/docs`), served
whether or not the default front end is on, and the same description is committed with the code
as [`openapi.json`](openapi.json), its `info.version` the package's version. Every read under
`/api/v1/` declares the model it answers in, so the description names its fields; a route outside
`/api/v1/` answers a JSON object without a declared model, and the description names the route and
its parameters and not every field. The committed file is generated, never edited by hand:
`tests/test_the_api_is_versioned.py` fails when it is not what the app generates, and

```bash
python -m openfactory.api.openapi
```

writes it again.

### Versions, and the aliases

**`/api/v1/` is the address a front end of its own builds on.** Each read that declares its model
is served there, and its unversioned path — the one the default front end calls — answers the same
body from the same handler: it is an **alias**, marked `deprecated: true` in the description. A
read added since, like `/api/v1/version`, is born under `/api/v1/` and has no alias. A
credential reaches a versioned path exactly where it reaches its alias: the area of
`/api/v1/<rest>` is the area of `/api/<rest>`.

**The alias period.** The unversioned aliases answer for the whole of the 0.7 series. They are
removed no earlier than 0.8.0, only in a release whose notes say so under "what an installation
must do", and never in a patch release. A screen that calls `/api/v1/` today has nothing to do then.

**The deprecation policy, for `/api/v1/` itself.** Within a version a read only grows: a field may
be added, and none is removed, renamed or given another type. A change that would break a reader is
a new version, served beside the old one, and the old one then follows the same course as the
aliases: marked `deprecated: true` in the description, announced in the release notes, and
answered for at least one more minor release.

**The version.** `GET /api/v1/version` answers which version the deployment runs, for a credential
like any read of the floor — which add-ons a deployment carries is a fact about the deployment:

```json
{"version": "0.7.0", "image": {"digest": "sha256:…", "code": "3f9a1c0e2b7d", "built_at": "2026-10-19T08:00:00Z"},
 "engine": {"address_kind": "remote"},
 "addons": [{"distribution": "openfactory-acme", "version": "1.2.0", "axis": "forge", "kind": "acme"}]}
```

`image` is `null` outside an image. Its `digest` is the one the deployment names in
`OPENFACTORY_IMAGE_DIGEST`, since an image cannot carry its own; `code` and `built_at` are the stamp
the image wrote when it was built. `address_kind` is the kind of address the engine is reached at,
never the address: `cloud`, `local` (this machine), `remote` (another host), `undeclared` or
`unreadable`, and `null` on an install without the engine's client library. `addons` has one row
per add-on row installed, read from the packages' metadata without loading them.

### Outside `/api/`: what a supervisor asks

Two routes answer **without a credential**, with the default front end on or off, so a container's
healthcheck, an orchestrator's probe or a load balancer can ask them. The panel serves both on its
own port; the worker, which serves no other HTTP, answers both on `OPENFACTORY_HEALTH_PORT` when it
is set, on `OPENFACTORY_HEALTH_HOST` (this machine's loopback unless the deployment says otherwise),
once its boot's own steps are done (the compose file sets the port, and its healthchecks ask both
processes from inside their containers through
`python -m openfactory.observability.health --port <port>`).

<!-- probes:start -->
| method | path | answers |
|---|---|---|
| GET | `/healthz` | `200 {"alive": true}` while the process serves. It reads nothing, so it never fails for somebody else's outage |
| GET | `/readyz` | `200` when the durable engine answers, the registry reads and the identity provider can admit; otherwise `503`, naming each check that failed |
<!-- probes:end -->

A `503` from `/readyz` names each failing check and says one sentence about it; the cause is in the
process's log, never in the body, because nobody identified the caller:

```json
{"ready": false,
 "checks": {"engine": {"ok": false, "detail": "the durable engine did not answer"},
            "registry": {"ok": true}, "identity": {"ok": true}},
 "failing": ["engine"]}
```

It answers within a bounded time whatever a check is waiting on — twice the engine's read deadline
(`OPENFACTORY_ENGINE_DEADLINE`, three seconds by default) and a second more, seven seconds by
default — and a late check is named, never the one beside it. Each dependency is asked at most once
every five seconds, by one question at a time, however many supervisors ask, and never on a thread
the authenticated routes need: readiness is not load on a dependency that is already struggling,
and asking it cannot slow anybody else down.

Each ask is a request like any other, so the panel's log has a line for it: with the compose
file's healthchecks, one `uvicorn.access` line per probe, every 15 seconds, in either log format.
The worker's log says once where it answers, and readiness logs one `NOT_READY` warning when a
check starts failing and one line when it answers again.

## 4. Streams

Each stream is authorized at the open, like any request, and asked again about every ten seconds
while it stays open: a credential that stops opening its path ends the stream.

| stream | transport | frames | how it ends |
|---|---|---|---|
| `/api/stream` | WebSocket; `?project=<name>` to follow one project, or send `{"project": "<name>"}` to follow another without dropping it | JSON with a `kind`: `hello` (the tick), `update` (what changed for the project), `bye` (why it stopped) | closed with 1008 when the credential is refused, 1011 when nobody could be judged |
| `/api/product/stream` | WebSocket; the default front end opens it on the cookie alone, with no credential in its address | JSON with a `kind`: `hello`, `subscribed`, `history`, `earlier` (the page before the one shown, answering `{"kind": "earlier", "before": <cursor>}`), `said`, `reply`, `staged`, `presence`, `ack`, `refused`, `resync`, `bye` | the same codes |
| `/api/temporal/stream` | Server-sent events | a JSON frame of the jobs' state — the jobs, whether the poller runs, the build — on connect and whenever it changes; `"jobs": null` when the engine cannot be read | a named event, `ended`, with why: `signed_out`, `not_allowed` or `unavailable` |
| `/api/jobs/{project}/{issue}/stream` | Server-sent events | the run's log events as they are written; a reconnect resumes from its `Last-Event-ID` (`v2-<n>`) | the same `ended` event |

## 5. What is not here yet

This is slice 1 of #561. The default front end still ships with the API, in the same process and
image, and is turned off by its setting; moving it into a module of its own, built only on this
contract, and a guide with a minimal example are the slices after it. Only the reads that declare
their model are under `/api/v1/` (#678); the actions, the streams and the other reads are not
versioned yet.
