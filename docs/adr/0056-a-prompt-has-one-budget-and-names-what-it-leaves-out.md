# ADR 0056 — A job's prompt has one budget, and every document it leaves out is named in it

- **Status:** Accepted (implemented with #364)
- **Date:** 2026-10-18
- **Milestone:** 0.7.0
- **Relates to:**
  - ADR-0001 D-2 (the cascade: framework, operator, project), D-9 (ADRs "always loaded, all of
    them"; **amended by this record**), D-10 (the derived index, read on demand).
  - ADR-0013 D4: the effort budget, with turns as the currency. The cost argued below is paid per
    turn.
  - ADR-0017: "a query tool … possible later if the size budget becomes the binding constraint".
  - #326 and #360: the prompt travels off argv, and `PromptTooLarge` is the one refusal of an
    undeliverable prompt. #359: a summed cap per role, closed as superseded. #370: the profile the
    size is measured under. #418: the floor a pass's prompt stands on.

## Context

Nothing decided how large a job's prompt may be. `build_context` cut each document at
`_MAX_DOC_CHARS` (8,000 characters) and `ticket_brief` inlined every constraint and every guideline
that resulted. The configuration guide said "full text, every prompt" over a rule that had already
cut 35 records.

**Measured on this repository at d29b94a**, with `docs/adr/**` as `docs.constraints`, `docs/**` as
`docs.architecture`, `CONTRIBUTING.md` and `docs/engineering-lessons.md` as `docs.guidelines`, and
six operator documents of about 7.6 KB:

| | documents | bytes inlined |
|---|---|---|
| `docs/adr/` on disk | 56 (55 records and the README) | 713,278 |
| constraints after `_MAX_DOC_CHARS` (35 of them cut) | 56 | 398,127 |
| guidelines (framework, operator, project) | 10 | 67,651 |
| the reference index (`doc_index`) | — | 9,852 |
| **the brief a blank card is handed** | | **477,369** |

What that costs:

- **Per pass.** The sizer, the planner, the executor and every repair each carry it.
- **Per turn inside a pass.** A harness re-sends its context on every turn (as cached reads), so a
  477 KB constitution, about 119,000 tokens at about 4 bytes a token, is read again on every one of
  up to `effort_budget_turns` turns. ADR-0013 made turns the currency because a subscription's
  cost-USD is notional. The constitution is paid in that currency every turn.
- **In attention.** Before the model reads a single file of the change, it is handed the
  equivalent of a long book of standing rules. A rule a model reads once among 56 others is a rule
  it weighs less than one it reads among ten.

Three things were found while reading the real code, and the issue did not say them:

1. **The reviewer pays nothing today.** `ReviewInput.constraints` is never filled by any caller, so
   no decision record reaches the reviewer. This record does not change that, because nothing
   reaches it to bound. It is a follow-up: D-9 says a document is a constraint when it is "also
   checked by the reviewer".
2. **The plan and the failure log reach the prompt outside `build_context`.** The planner's plan
   is set on the context after it is built and rendered by each harness. A repair's failure log is
   handed to `ticket_brief` at render time. So the only place that sees every part of the prompt
   is `ticket_brief`, and the bound is applied there.
3. **`openfactory explain` said "inlined in full"** for every constraint, the 35 cut ones included.

## Decision

**A job's prompt is bounded, and the bound is over the whole declared section, not over one role
at a time.**

Default: 160,000 bytes (OPENFACTORY_PROMPT_BUDGET)

### What is counted

The UTF-8 bytes of everything the brief carries apart from the role prompt:

- the card;
- every document tier: the framework baseline, a profile's `extend:`, the operator's guidelines,
  `docs.constraints`, `docs.guidelines` and `components.<name>.guidelines`;
- the reference index (`doc_index`) and the knowledge map;
- the planner's plan (`context.plan`), a repair's failure log, `another_pass` and a person's
  `decision`;
- the notice described below.

`budgeted_bytes(context, failures=…)` in `adapters/agent/base.py` is that number:
`len(ticket_brief(...).encode()) + len(context.plan.encode())`.

The role prompt is **not** counted. It is the platform's own, fixed for each role, and
`openfactory explain` prints it. A bound that a role prompt could exhaust would leave a project's
documents out because of the platform's own words.

**Bytes, not characters**, and not argv bytes. Bytes are the unit `inlined_document_bytes` already
reports, and they are what a model's context is paid in. A cut that counted characters survived
review in #359. This is a budget, not a delivery limit: `stage_prompt`'s `PromptTooLarge` (#360)
stays the only refusal of a prompt that cannot reach the box.

### Who sets it

The **operator**, from the worker's environment. `OPENFACTORY_PROMPT_BUDGET` takes a positive
number of bytes, or `off` for no bound. When it is unset, the default above applies. Any other
value is refused by name: `openfactory doctor` fails its `documents` line, and a job holds before
any pass, the way a profile that does not resolve holds it.

The budget is **not a manifest key**. The manifest lives in the repository the agent edits. A cost
setting there would let a change to that repository decide what every later pass costs, which is
the boundary the manifest already holds for harness, model and box
(`test_a_deployment_setting_is_not_a_manifest_field`).

### Why 160,000 bytes

- About 40,000 tokens at about 4 bytes a token. That is about 20% of a 200,000-token window, the
  smallest default window among the harnesses the worker image pins (`docker/worker.Dockerfile`:
  claude-code 2.1.219, codex 0.146.0, kimi-code 0.31.1, opencode 1.18.13). **The window sizes are
  not verified from those bundles here.** They are each vendor's documented defaults, and a model
  chosen per deployment can have a larger one.
- About a third of the 477,369 bytes measured above. The rest of the window is left for what the
  pass does: the files it reads, the tool output and the conversation.
- Above every corpus the test suite and the shipped examples carry. Only a project with dozens of
  long records reaches it.

What each budget keeps on the corpus measured above (the same probe, after this change):

| budget | records inlined (of 57) | guidelines inlined (of 10) | named as left out | named as cut | `budgeted_bytes` |
|---|---|---|---|---|---|
| 96,000 | 7 (`README.md`, 0056 down to 0052, 0047) | 4 | 56 | 8 | 94,571 |
| **160,000** | **15 (`README.md`, 0056 down to 0043)** | **4** | **48** | **16** | **159,668** |
| 256,000 | 29 (`README.md`, 0056 down to 0030, and 0016) | 4 | 34 | 24 | 254,026 |
| `off` | 57 | 10 | 0 | 38 | 491,725 |

Measured on this branch with this record in `docs/adr/`, so there are 57 records against the 56
above. The four guidelines kept under every budget are the framework's two, which are pinned,
and the project's own two, which are filled first. The six operator documents are filled after
the records, so all six are left out and named. Two quirks of the measurement: `docs/adr/README.md`
sorts after the numbered records, so it counts as the newest. ADR-0016 is kept at 256,000 bytes
because the fill tries a smaller record after a larger one does not fit.

### How the budget is filled

The fixed parts are counted first: the card, the index, the knowledge map, the plan, the failure
log, `another_pass`, `decision`, any text that is not a document (the sizer's INVEST sentence),
and the notice. Then the documents are added in this priority, high weight first:

1. the project's own guidelines (`docs.guidelines`, `components.<name>.guidelines`), the last
   declared first;
2. `docs.constraints`, in **reverse** of the glob's sorted order. For numbered records that is
   newest first. A later record amends or supersedes an earlier one: #359 kept ADR-0007 ("partly
   superseded by ADR-0010") and dropped ADR-0010;
3. the operator's guidelines, the last first;
4. a profile's `extend:` guidelines;
5. the framework baseline, which is **never left out** (see below).

Documents are added one at a time. A document that does not fit is left out, and a smaller one
after it is still tried. A document that lands exactly on the budget is kept. The documents kept
are **rendered in their original order**, not the order they were added in: framework, profile,
operator, project. So the project still has the last word.

### What the agent cannot open is never left out

A left-out document is named so the agent can open it. A document the agent cannot open would be
left out in silence, which criterion 5 of #364 forbids. So two kinds of document are **pinned**:
they are counted first and always inlined.

- **The framework baseline** (`org_defaults/*.md`, 6,108 bytes). It lives in the installed
  package, not in any checkout or mount. It is ADR-0001 D-2's floor.
- **An operator tier the box does not mount.** The box answers `guidelines_path` (the worktree box
  with the host path, a container box with its mount, or nothing).

This is how #364's "project, then operator, then framework" is read: as a priority among the
documents the agent can open. When the pinned and fixed parts alone pass the budget, every
droppable document is left out and named, the pass still runs, and the job's log and
`openfactory doctor` say so.

### The notice

The notice goes inside `## Declared by this project — AUTHORITATIVE`, after the guidelines and
before the reference index, under `### Declared and not inlined here — open each before you change
what it governs`. It names the budget and the variable, then gives one line per document:

- a document **left out**: the path it can be opened at and its size;
- a document **cut** at `_MAX_DOC_CHARS`: "inlined up to 8,000 of N characters; the rest is at
  <path>". This line is written even when the budget is `off`.

A project document is named by its checkout-relative path. An operator document is named
`<operator root>/<file>`, where the root is the box's answer. A path is never named by its first
line. The job logs **one** line for each context build that leaves anything out (the count and the
budget), never one line per document: #359 logged 44 lines per build, twice per job.

`openfactory explain` says the same thing about each document (left out, or inlined up to N of M
characters), from the same fit. `openfactory doctor` and `box prove` give the budget and how many
documents a blank card's brief keeps, cuts and names. All three ask where the operator directory
opens of a box built the way the job builds it, with that directory mounted
(`operator_guidelines.box_knobs`). Otherwise they would pin the operator tier and report the
project's own guidelines left out, where the job leaves the operator's out.

### What it does not reach

- **`handed_to_a_live_session`** carries no documents. A resumed session already holds its brief.
- **The reviewer** is handed no decision records today (see Context, item 1).

## How this relates to ADR-0001 D-9

D-9 said: "ADRs (`constraints`): always loaded, all of them … We never rely on a ticket to link the
right ADR." Its **purpose** still holds. Every record is either inlined or named by path in every
prompt, so the platform links all of them, and no ticket has to link the right one. Its
**letter** ("loaded") no longer holds, so D-9 is amended in place to say what is true.

## Rejected alternatives

- **Keep everything inlined and state the cost.** The issue's own argument was that this is "the
  price of the constitution". At 477 KB, re-read on every turn of every pass, that price grows with
  every record the project writes. No one has decided it, and nothing tells the operator it is
  rising. `off` keeps this behaviour for an operator who decides to pay it.
- **Index more, inline less**, by moving `docs.constraints` into the reference index. The issue
  argued that "a budget is a quality knob wearing a cost mask": a rule left out is a rule the agent
  does not follow. That is answered by naming every left-out document in the prompt, with the path
  it can be opened at. Moving long records to `docs.architecture` is still the advice the
  configuration guide gives a project whose corpus does not fit. This record does not migrate any
  project.
- **A cap per role** (#359). It was tied to the argv limit, which #326 removed. It dropped 44 of 54
  records, and it kept ADR-0007 while dropping ADR-0010, which amends it. A cap per role also makes
  the operator tier compete with the project for room it should not have to share in that way: with
  six operator documents, #359 left out the project's own guidelines.
- **A manifest key**, including one that may only lower the budget. The manifest is in the
  repository the agent edits (see "Who sets it"). A key that may only lower the budget is safe
  from that, but it is a second place to set one number, and no project has asked for it.
- **Fill in declared order.** That would keep the framework and the operator tier and leave out the
  project's own rules first, which is the inversion #359 measured.

## Consequences

- A project whose documents pass 160,000 bytes hands its agents fewer of them inline, and every one
  left out is named in the prompt. `OPENFACTORY_PROMPT_BUDGET=off` restores the previous
  behaviour.
- `AgentContext` carries its documents as `documents: list[InlinedDocument]` and its budget as
  `prompt_budget`. `constraints` and `guidelines` stay, for text that is not a document. They are
  always rendered and never left out.
- `openfactory explain`, `doctor` and `box prove` say what the budget keeps, from the same fit.
