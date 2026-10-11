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
(`OPENFACTORY_PANEL_TOKEN(S)`, `OPENFACTORY_PRODUCT_TOKEN(S)`, an identity provider) every route
answers without one: the local-development posture, never the production one.

**Areas.** A credential may act in the **floor** (the factory: jobs, boards, projects), in the
**product** area (the product role, its documents and attachments), or in both (an unscoped
credential). `GET /api/whoami` answers which, for any credential, and is how a screen decides what
to draw for itself. The product area is every path under `/api/product/` and every catalogue row
named `product_*`; every other path under `/api/` is the floor.

**A dashboard on another origin** is admitted by `OPENFACTORY_PANEL_ORIGINS`, which names the
origins explicitly; a CORS preflight is answered without a credential, and the request after it is
gated like any other.

## 2. Refusals

Every refusal is JSON with a `detail` sentence:

| status | when | body |
|---|---|---|
| 401 | no credential, or one nobody issued | `{"detail": "unauthorized"}`, plus `"login": "<path>"` when the deployment's identity provider has a login page |
| 403 | a credential scoped away from the path's area | `{"detail": "this credential is scoped to <areas> and that is part of the <area>."}` |
| 503 | the identity provider cannot check anybody right now | `{"detail": "identity provider unavailable…"}` |
| 4xx from an action | a catalogued action refused what was asked | `{"detail": "<the action's own sentence>"}` |

A socket is refused before it is accepted: the upgrade is answered with a 403 and closed with code
**1008** for a refusal, **1011** when nobody could be judged.

## 3. Routes

Every route under `/api/`. **Area** is the area a scoped credential must hold; "every credential"
means any credential the deployment issued.

<!-- routes:start -->
| method | path | area | what it is |
|---|---|---|---|
| POST | `/api/act/{name}` | floor; a `product_*` row: product | run one catalogued action: `{"params": {...}}` |
| GET | `/api/actions` | floor | the catalogue of actions this deployment can be asked to do |
| GET | `/api/address` | floor | how a repository address would be read, before a project is added |
| GET | `/api/attention` | floor | the jobs that need a person |
| GET | `/api/board/{project}` | floor | a project's board, as its tracker holds it |
| GET | `/api/budget` | floor | the API budget of the trackers this deployment reads |
| GET | `/api/coordinator/messages` | floor | the tech-lead's recent narrated updates |
| GET | `/api/decisions` | floor | every job parked on a person's decision, with its question and options |
| GET | `/api/factory/{project}` | floor | a project's cockpit: harness, credentials, links |
| GET | `/api/floor` | floor | whether the factory is working, for every project |
| GET | `/api/floor/{project}` | floor | whether the factory is working, for one project |
| GET | `/api/inbox` | floor | what needs a person right now, in one shape for every channel |
| GET | `/api/jobs` | floor | the local jobs |
| POST | `/api/jobs` | floor | start a local job (the `start` action) |
| GET | `/api/jobs/{project}/{issue}/detail` | floor | one job's briefing: runtime, cost, pull request, why it is where it is |
| GET | `/api/jobs/{project}/{issue}/events` | floor | one run's log |
| GET | `/api/jobs/{project}/{issue}/stream` | floor | one run's log as it is written (stream, section 4) |
| GET | `/api/loops/{project}` | floor | everything the agents are still waiting on |
| GET | `/api/messages/{project}` | floor | what the factory has said to a project, and what it waits to hear |
| POST | `/api/messages/{project}/answer` | floor | a person's answer to a question the factory asked |
| POST | `/api/messages/{project}/suggestion` | floor | a person's yes to the one action the tech-lead proposed |
| GET | `/api/metrics` | floor | spend by period, model, harness and role |
| GET | `/api/preview/{project}/{unit}` | every credential | one unit's preview, and a key into it |
| POST | `/api/preview/{project}/{unit}/own_shape` | every credential | let a preview run its change's own shape |
| POST | `/api/preview/{project}/{unit}/rebuild` | every credential | build a preview again from its pull request's head |
| POST | `/api/preview/{project}/{unit}/start` | every credential | start a preview |
| POST | `/api/preview/{project}/{unit}/stop` | every credential | take a preview down, its logs kept |
| GET | `/api/product/projects` | product | the projects that have a product role |
| WS | `/api/product/stream` | product | the conversation with the product role (stream, section 4) |
| GET | `/api/product/{project}/attachments` | product | what a message may carry, before a file is sent |
| POST | `/api/product/{project}/attachments` | product | keep one file for a message |
| GET | `/api/product/{project}/attachments/{ident}` | product | a file sent in one of the person's conversations |
| GET | `/api/product/{project}/documents` | product | the product's documents as their ingestion found them |
| GET | `/api/product/{project}/documents/file/{path:path}` | product | one of the product's documents, as it is |
| GET | `/api/projects` | floor | the projects this deployment runs |
| POST | `/api/projects` | floor | add a project |
| POST | `/api/projects/{name}/enabled` | floor | turn a project's pickup on or off |
| POST | `/api/projects/{project}/scan` | floor | read a project's queue now, without waiting for the next tick |
| GET | `/api/promote/{project}/{issue}` | floor | what the production approval asks: the version, the bumps, the approvers |
| POST | `/api/promote/{project}/{issue}` | floor | release a local job to production |
| WS | `/api/stream` | floor | what changed, as it changes (stream, section 4) |
| POST | `/api/temporal/act/{project}/{issue}` | floor | a person's decision on a parked job |
| POST | `/api/temporal/approve/{project}/{issue}` | floor | the production approval, sent to the parked job |
| GET | `/api/temporal/jobs` | floor | the jobs, live, from the durable engine |
| POST | `/api/temporal/jobs` | floor | start a durable job (the `start` action) |
| GET | `/api/temporal/stream` | floor | the durable jobs' state as it changes (stream, section 4) |
| GET | `/api/whoami` | every credential | who this credential is, and which areas it may act in |
<!-- routes:end -->

**Payloads.** The API describes its own HTTP routes at `/openapi.json` (and `/docs`), served
whether or not the default front end is on. Most routes answer a JSON object without a declared
response model, so that description names the route and its parameters and not every field; the
fields a screen reads today are the default front end's, in `openfactory/api/panel.html`.

## 4. Streams

Each stream is authorized at the open, like any request, and asked again about every ten seconds
while it stays open: a credential that stops opening its path ends the stream.

| stream | transport | frames | how it ends |
|---|---|---|---|
| `/api/stream` | WebSocket; `?project=<name>` to follow one project, or send `{"project": "<name>"}` to follow another without dropping it | JSON with a `kind`: `hello` (the tick), `update` (what changed for the project), `bye` (why it stopped) | closed with 1008 when the credential is refused, 1011 when nobody could be judged |
| `/api/product/stream` | WebSocket; the default front end opens it on the cookie alone, with no credential in its address | JSON with a `kind`: `hello`, `subscribed`, `history`, `said`, `reply`, `staged`, `presence`, `ack`, `refused`, `resync`, `bye` | the same codes |
| `/api/temporal/stream` | Server-sent events | a JSON frame of the jobs' state — the jobs, whether the poller runs, the build — on connect and whenever it changes; `"jobs": null` when the engine cannot be read | a named event, `ended`, with why: `signed_out`, `not_allowed` or `unavailable` |
| `/api/jobs/{project}/{issue}/stream` | Server-sent events | the run's log events as they are written; a reconnect resumes from its `Last-Event-ID` (`v2-<n>`) | the same `ended` event |

## 5. What is not here yet

This is slice 1 of #561. The default front end still ships with the API, in the same process and
image, and is turned off by its setting; moving it into a module of its own, built only on this
contract, and a guide with a minimal example are the slices after it.
