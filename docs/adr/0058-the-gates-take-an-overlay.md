# ADR 0058 — The gates take an overlay: a deployment's own gates and protected paths, applied from outside the package, that may only tighten

- **Status:** **Proposed** (design only — no code changes with this ADR; a maintainer accepts it in review)
- **Date:** 2026-10-21
- **Implements:** #990 — the policy floor has no operator-provided layer. This ADR decides the
  shape; implementation is deferred until the ADR is accepted.
- **Relates to:**
  - [ADR-0001](0001-foundational-conceptual-model.md) D-2 (project knowledge is a cascade;
    each layer tightens, never loosens): this names a new home for the deployment's half of
    layer 1, the policy floor.
  - [ADR-0022](0022-provider-seams.md) (an axis is agnostic when it is BORN with two) and
    [`docs/core/07-extensibility.md`](../core/07-extensibility.md) (a stranger adds the third
    without editing our files): the overlay is reached through that tree, and ships with its two
    kinds.
  - [ADR-0044](0044-a-project-declares-what-it-is.md): it **reserves the name "deployment
    overlay" for the PROMPT/profile cascade** (its own layer 2, which "does not exist yet"), and
    it draws the line this ADR depends on — *gates are the strong form, prose is the weak one; a
    profile may drop a guideline and may never remove a gate.* This ADR is the strong form's
    operator layer, and takes a **different name** so the two never collide.
  - [ADR-0057](0057-who-may-act-is-one-decision-and-a-production-approval-is-a-person.md): its D2
    makes `floor` the name of an authorisation **area**, which is why this layer is not called the
    "floor overlay" (D1); and its rules — *who may act is one decision*, made from grants that
    live with the host and the identity provider, and *the manifest narrows, never grants* — are
    why the overlay carries no key that could grant (D6).

## Context

The policy floor is the one layer of the cascade a project may not loosen (ADR-0001 D-2, layer 1).
In the tree it has exactly two homes, and both ship **inside the `openfactory` package**:

| home | what it carries | read by |
|---|---|---|
| `openfactory/policy/floor.py` | the hardcoded framework baseline — `REQUIRED_VALIDATION_ROLES` (`test`, `security`) and `GLOBAL_DENY` (prose that names the code enforcing each denial) | `policy/conformance`, the orchestrator |
| `openfactory/org_defaults/floor.yaml` | the deployment's **default** `validate:` gates and `protected_paths:` | `policy/presets.py::org_default_validation`, `policy/protected.py::floor_protected_paths`, merged into every project by `contracts/manifest.py::_inherit_the_deployment_floor` |

The two keys of `floor.yaml` bind differently, and the difference matters below. Its
`protected_paths:` is a floor in the strict sense: a project's own globs are unioned with it and
none can be removed. Its `validate:` is a **default**: `_inherit_the_deployment_floor` merges a
gate only for a role the project's file leaves undeclared — *"the project always wins … to
replace a deployment default, declare that role"* — in `.openfactory/project.yaml`, which the
shipped floor itself protects (`.openfactory/**`), so the replacement needs a person.

`org_defaults/floor.yaml` exists precisely because there was no deployment-level term before it:
its own docstring records that "adopt the security gate across the fleet" used to mean editing the
manifest of every client repository by hand, and a new client inherited nothing. It closed that
hole with a good default — but it is a file in the wheel. A deployment that wants to add **its
own** organisation-wide gate, or protect **its own** path, has only one move today: edit a file
inside the installed distribution. A reinstall or an image rebuild (ADR-0043: the code is baked
into the image) overwrites the edit, and a second deployment of the same image inherits none of
it. The hole `floor.yaml` closed for projects reopens one level up, for the deployment.

The prose half of the cascade already solved exactly this. `OPENFACTORY_GUIDELINES_DIR`
(`orchestrator/operator_guidelines.py`) lets an operator mount central **guideline documents**
from outside the package — a first-class, deployment-level home for an organisation's standards,
read from the environment and nowhere else. But guidelines are the **weak** form: a profile may
waive or replace one (ADR-0044), because prose only ever reaches the agent's prompt. The policy
floor is the **strong** form: its gates and protected paths reach the merge decision, and nothing
may switch them off. The strong form is the one with no operator home, and it is the one that most
needs an un-forkable one — a central gate an operator can mount is worth more than one a project
could argue with.

This is a generic concern for anyone running a single deployment of the core. It is not about any
particular organisation's policy; it is about where a deployment's policy *lives* so that it is
not a patch on a shipped file.

## Decision

### D1 — The name: the **gate overlay**; not "deployment overlay", and not "floor overlay"

The new layer is the **gate overlay**: the deployment's own gates and protected paths, supplied
from **outside** the package and laid **over** the shipped policy floor.

- **"gate"** is the tree's own word for the strong form. ADR-0044 draws the line in it — *a
  profile may drop a guideline and may never remove a gate* — the overlay's `validate:` entries
  are `contracts/manifest.py::Gate` values, and its protected paths are human gates
  (`policy/protected.py`: a change to one "is human-gated"). Naming the layer after it says, in
  one word, which half of the cascade it belongs to: the gates, not the prose.
- **"overlay"** — not "layer" or "tier" — because it is **applied on top of** the shipped floor
  from outside the distribution, the way an overlay mount sits over a base filesystem. It adds to
  what is underneath and cannot cut into it. "layer" would read as a new tier baked into the
  package beside `floor.yaml`; the point is that it is *not* in the package.
- **Not "deployment overlay".** ADR-0044's closing paragraph reserves that exact name for the
  **prompt/profile cascade's layer 2** ("the deployment-overlay layer … does not exist yet").
  Reusing it would put the strong form and the weak form under one word — the precise collapse
  ADR-0044 and `policy/protected.py` are built to prevent. Two names, because the two layers
  disagree on the one question that matters: whether a lower layer may remove what they add. The
  prompt overlay's content can be dropped by a profile; the gate overlay's cannot be dropped by
  anyone. A shared name would invite a shared mechanism, and the mechanisms must differ because
  the threat models do.
- **Not "floor overlay"**, the name this record's first draft used. The tree already spends
  `floor` on two things — the policy floor (`policy/floor.py`, `floor.yaml`,
  `OPENFACTORY_FLOOR_UNREADABLE`) and the shop floor (`openfactory/floor/`, whose docstring warns
  its reader about the first) — and ADR-0057 D2 makes it a third: the authorisation **area**
  `floor`, the operator's console, *the name on the wire* (`BOARD_GROUP`, the right-hand side of
  an OIDC group map). A setting called `OPENFACTORY_FLOOR_OVERLAY` beside
  `OPENFACTORY_OIDC_GROUPS="eng-leads=floor"` reads as an overlay **on the `floor` area** — on
  who may act at the console — which is exactly what this layer must refuse to carry (D6).
  ADR-0057 D2's own argument settles it: renaming a private name breaks nobody, renaming a
  published one breaks every deployment. This axis, its setting and its log codes are not
  published yet, so they are named once, now, away from the collision. The code's existing
  `floor_*` identifiers (`floor_document`, `floor_protected_paths`, `floor_reason`) name the
  policy floor, predate both records, and are not renamed here; in this record "the policy floor"
  always means ADR-0001 D-2 layer 1, and the bare word is not used for anything new.

### D2 — Where it merges, what it may say, and the rule that it may only tighten

**The gate overlay merges between the shipped `org_defaults/floor.yaml` and the project**, so the
cascade the project inherits reads:

```
policy/floor.py            framework baseline      (REQUIRED_VALIDATION_ROLES, GLOBAL_DENY)
org_defaults/floor.yaml    deployment default      shipped in the package
  ── the gate overlay ──   deployment's own gates  mounted / fetched from outside the package   ← new
.openfactory/project.yaml  the project             replaces a default, cannot touch an added gate
```

The overlay is one file, `gates.yaml`, in **the same shape `floor.yaml` already has** — a
`validate:` map of role → gate and a `protected_paths:` list — and it joins the policy floor
inside `_inherit_the_deployment_floor`, the one place both `policy/conformance._effective_validation`
(which inspects the floor) and `orchestrator/validation.applicable_validations` (which executes
it) read the same answer from, along with `box_prove`'s gate list. What each entry may say depends
on what it names:

- **A baseline role** — a role the shipped `floor.yaml` declares (today: `security`). The overlay
  may say **exactly one thing** about it: `advisory: false`, which promotes it to blocking. Its
  `command` and its `timeout_minutes` are **immutable**: an entry for a baseline role that carries
  either key — whatever the value — or `advisory: true` is refused at load. A rule of "the command
  must still be present" would pass `security: {command: "true", advisory: false}`, a promotion
  that removes the secret scan; and an overlay that had to copy the shipped command would, on the
  release that improves the shipped scan, either be refused or freeze the old one. Carrying only
  the bit, it promotes whatever the shipped gate is. The timeout is immutable because neither
  direction is uniformly tighter — a shorter one can turn a slow real scan into a gate that could
  not run, a longer one lets a hung scanner hold the queue — so there is no order a load-time
  check could hold it to, and equality is the one rule that is both checkable and cannot loosen.
  **A promoted baseline role stays a default**: a project that declares the role itself replaces
  it exactly as it replaces the shipped default today. This record does not change that protocol
  for the shipped roles; a deployment that wants a gate no project can replace **adds** one.
- **A required role the shipped floor leaves to the project** — `test` today — is refused at
  load. `floor.yaml` says why it is absent (no command runs every project's tests), and an
  overlay entry with the name would read as satisfying a required role while satisfying nothing.
- **An added role** — any other name — carries `command` (required), `advisory` and
  `timeout_minutes`: the `Gate` fields, and no others. **It is binding.** The merge files it under
  `deployment.<role>`, a role name `Manifest` refuses at load in a project's `validate:` and in a
  component's (and a test holds `openfactory/presets/` to the same rule), so no project, component
  or stack preset can declare, replace or shadow it — per-component precedence in
  `applicable_validations` has nothing to win with — and it cannot shadow theirs. It runs
  repo-wide, on every diff, beside whatever the project resolves, and it never counts towards a
  required role: `floor_reason` still asks the project for its own `test` and `security`.
- **`protected_paths:`** merges as a **union** with the shipped globs, as `effective_protected_paths`
  already unions the floor with a project's own: an overlay adds globs and cannot express a
  deletion, and every shipped glob is re-asserted after the merge.

**Each of these is refused at load:**

| attempted move | detected by | result |
|---|---|---|
| remove a baseline or required role (e.g. drop `security`) | the merge is **additive** — an overlay cannot *express* a removal — and `REQUIRED_VALIDATION_ROLES` and every shipped role are re-asserted after it | refused at load |
| replace a baseline gate's command, or change its timeout | the presence of `command` or `timeout_minutes` on a baseline role's entry, whatever the value | refused at load |
| demote a baseline gate (`advisory: true`) | the only key a baseline role's entry may carry is `advisory`, and its only value is `false` | refused at load |
| declare `test` | a required role the shipped floor leaves to the project | refused at load |
| drop a protected path | the union; every shipped glob must survive the merge | refused at load |
| carry anything that is not a gate or a protected path | D6 | refused at load |

A refusal is **fail-closed and named**: it logs `OPENFACTORY_GATE_OVERLAY_LOOSENS` identifying the
exact role or path and what it tried to weaken, and the deployment does not start (D7). The overlay
is allowed to **add** a role, **add** a protected glob, and **promote** a baseline gate to
blocking; those are tightenings, which is the whole purpose — though "tightening" is not "free",
and D8 says what an addition costs and who decides it. What it may never do is make the merged
policy floor weaker than the floor shipped underneath it, and because the check compares the
*post-merge* result against the *shipped baseline*, a loosening cannot hide in a clever
redeclaration.

This is where "tighten never loosen" earns a crisp, machine-checkable meaning that it does **not**
have in the prose cascade: a guideline has no `advisory` bit and no gate to demote, so "cannot
loosen" was never expressible over prose (ADR-0044 says as much). Over the gates it is a handful
of comparisons on structured data.

### D3 — The axis, born with two kinds: `dir` and `bundle`

The overlay is a provider axis in the ADR-0022 sense, and it ships **born with two** real kinds —
no stub (ADR-0022 §5), reached through the entry-point tree `openfactory/plugins.py` already
carries (`docs/core/07-extensibility.md`): a new axis `gate_overlay`, registered the same way
`preview` and the rest are, resolved `kind → builder`, an unknown kind refusing by name.

- **`dir`** — the operator mounts or links a directory and the overlay reads `gates.yaml` from
  it. This is the directly-controlled case: the file is on the host owner's own disk, versioned
  however the operator versions it, changed by editing it.
- **`bundle`** — the deployment fetches a **versioned archive** and the overlay reads the
  `gates.yaml` unpacked from it. This is the distributed case: a central policy, authored once and
  pulled by many deployments, pinned to a version.

**Who writes a `dir` overlay, how the stack holds it, and its stamp.**

- **The host's owner writes it, and nothing in the core does.** It is the same party that writes
  `.env.compose`, and the one ADR-0057 leaves as the only writer of `approver` and
  `product-owner` grants (the registry's `roles:`, `OPENFACTORY_PROD_APPROVERS`,
  `OPENFACTORY_OIDC_GROUPS`). No catalog row, CLI verb, panel route or agent writes it.
- **The stack holds it read-only.** It is mounted `:ro` into the services that read the policy
  floor, as the worker mounts `OPENFACTORY_GUIDELINES_DIR` (`docker-compose.yml`;
  `docs/RELEASING.md`: "the stack never writes it"), and — unlike the guidelines directory —
  **never into a box**: a box mounts what a job reads, and no job reads the policy that judges it.
- **Its permissions are checked at load.** `gates.yaml`, and every directory from it up to and
  including the configured root, must be writable by its owner alone — no group or other write
  bit (`mode & 0o022`) — or the overlay is refused (`OPENFACTORY_GATE_OVERLAY_WRITABLE`), naming
  the path, its mode and the remedy (`chmod go-w <path>`). It is the shape `preflight._env_file`
  already gives `.env.compose` (`mode & 0o077`), over the write bits instead of the read bits,
  because what matters here is who can change the file, not who can read it. The owner's uid is
  **not** compared: inside a container a bind mount's owner is the host's uid, not the worker's,
  and on Docker Desktop not even that (`preflight._the_socket_as_this_process_sees_it` exists for
  that difference), so an equality check would refuse every correct compose install.
- **It is version-stamped, always.** The stamp is the `sha256` of the `gates.yaml` bytes the
  process read — present for a plain mount as for a checkout — and, when the directory is a git
  checkout, its short commit, read from `.git` as text exactly as `operator_guidelines._git_version`
  reads it (never by running `git` in an operator-named directory). The stamp is journaled on
  every job and shown beside each overlay gate (D8). The first draft of this record left a `dir`
  stamp to the implementation; a policy that decided a merge without a recorded version would be a
  promise, not a mechanism, so it is decided here.

**Reconciling `dir` with `OPENFACTORY_GUIDELINES_DIR`: it sits beside the guidelines tier, sharing
its posture, and does not supersede it.** The two are deliberately kept apart because they carry
different forms of rule with different mutability:

- the guidelines directory feeds **prose** into the prompt, and a profile may waive or replace any
  of it (ADR-0044) — it is advisory by nature;
- the gate overlay feeds **gates and protected paths** into the merge decision, and nothing may
  loosen it.

Folding the gate overlay into `OPENFACTORY_GUIDELINES_DIR` would force one of two collapses:
either prose becomes un-waivable (breaking ADR-0044's whole point about the weak form) or the
gates become waivable (breaking the strong form). So the overlay gets its **own** deployment
setting (D5), and its `dir` kind **may point at the same directory** an operator already uses for
guidelines — one home for an organisation's standards — reading `gates.yaml` there while the
guidelines tier keeps reading the `*.md`. It **generalises the operator-directory idea to a second
content type** and sits beside the first; it does not replace it. The containment check is the
same one `operator_guidelines._contained` already applies — every path resolved, must stay under
the configured root — with one difference: a `gates.yaml` that resolves outside the root is a
**refusal** (`OPENFACTORY_GATE_OVERLAY_UNREADABLE`, naming where the link led), not a warning,
because unlike a guideline this file decides whether a change may merge, so a link that escaped
the directory would be worse here, not better.

### D4 — The `bundle` format, a supply-chain surface

A bundle's files reach the merge gate, so the bundle is a supply-chain surface and is specified as
one. The format:

- **The container is a versioned, immutable archive** — a gzip-compressed tar (`.tar.gz`) holding a
  `gates.yaml` at a known path (and nothing it needs beyond that). It is addressed by an
  operator-provided reference **and a required `sha256` digest**; the reference names where to
  fetch, the digest names *what* must come back.
- **Resolved at start, cached content-addressed, never fetched per job.** The bundle is resolved
  when a process starts (D7), into a cache keyed by its digest — the same ephemeral-state /
  persistent-cache split ADR-0001 D-4 draws for dependencies. A start that finds the digest in the
  cache verifies the cached bytes and does not fetch; a start that can neither find nor fetch it
  does not start. A job reads the already-unpacked, already-verified copy, so the policy a job runs
  under is deterministic and does not depend on a network call at pickup time.
- **Verified before it is trusted, fail-closed.** The bytes must match the pinned `sha256` or the
  deployment does not start (`OPENFACTORY_GATE_OVERLAY_UNVERIFIED`). The digest pin is what makes a
  swapped bundle *detectable* rather than silent. An **optional** detached signature, checked
  against an operator-configured public key, is supported for deployments that want provenance as
  well as integrity; absent a configured key, the digest is the trust anchor and the ADR does not
  pretend otherwise.
- **Unpacked safely.** Extraction rejects any entry that escapes the target directory (a traversal
  path, an absolute member, a symlink pointing out) — the containment posture of D3, applied to
  archive members. A malformed archive is a refusal, not a partial read.
- **Version-stamped, and the stamp is journaled.** The bundle carries a version string and its
  digest, and which version applied to a job is written where a reader of the change can see it —
  as D3 stamps a `dir`, and as `operator_guidelines._git_version` stamps which revision of the
  central guidelines shaped a job.
- **Built-ins win, and a loosening is refused outright.** The shipped floor
  (`policy/floor.py` + `org_defaults/floor.yaml`) is the built-in, and the overlay — `dir` or
  `bundle` — may only add to or tighten it (D2). This is the same reasoning `plugins.py` gives for
  a built-in winning a collision: *"an add-on that could redefine `github` for every project on a
  deployment is a supply chain, not an extension point."* A bundle that could weaken the gates of
  every job is that supply chain. The one difference from `plugins.py` is the consequence: a
  plugin collision resolves silently in the built-in's favour and is logged, whereas an overlay
  that attempts to **loosen** is a hard, named refusal that stops the deployment from starting
  (D7) — because the policy floor's entire value is that it cannot be made weaker, so a quiet
  "built-in won" would understate what just happened.

### D5 — Resolution is the deployment's alone

The overlay is named by the **process environment only**, never by a project's manifest and never
by an add-on package — the identical rule, and the identical reason, as `OPENFACTORY_GUIDELINES_DIR`:
*"a value a project or a stranger's wheel could set would let untrusted content decide what every
job on the deployment reads"* — and here it would decide what every job must **pass**, which is
worse. The environment belongs to whoever runs the stack.

- `OPENFACTORY_GATE_OVERLAY` carries the reference (a directory path for `dir`; a fetch reference
  plus its pinned digest for `bundle`), and `OPENFACTORY_GATE_OVERLAY_KIND` names the kind, so
  the `gate_overlay.<kind>` registry resolves it the ADR-0022 way; an unknown kind refuses at
  start naming what IS installed. Unset, there is no overlay and nothing is said; set, an overlay
  that is absent or unparseable is a refusal (`OPENFACTORY_GATE_OVERLAY_UNREADABLE`), not "no
  overlay" — unlike the guidelines directory, which is tolerated absent, because a policy the
  deployment named and cannot find is not the same fact as no policy.
- A project's manifest cannot set it, cannot point at it, and cannot opt out of it. A project
  inherits the overlay as part of the policy floor: it cannot declare, replace or shadow an added
  gate (`deployment.<role>`, D2), cannot drop an overlay glob, and replaces a baseline role's
  default only as it does today. It may, as today, **add** its own gates and protected paths.
- An add-on package may ship an additional `gate_overlay` *kind* (a new fetch mechanism) through
  the entry-point tree, but it cannot ship *content* and it cannot shadow a built-in kind — built-ins
  win (D4).

### D6 — The overlay carries gates and protected paths, and nothing else

**`gates.yaml` may hold two top-level keys, `validate:` and `protected_paths:`. Any other key is
refused at load** (`OPENFACTORY_GATE_OVERLAY_OUT_OF_SCOPE`), naming it — among them `roles:`,
`prod_approvers`, `review_mode`, autonomy, a `harness`, a box's `network`: any key of the manifest
or the registry. Inside `validate:`, an entry may carry only the `Gate` fields D2 allows it; an
unknown field is refused, not ignored, because a typo there is a gate quietly not applied.

- **Who may act stays where ADR-0057 put it.** ADR-0057 makes *who may act* one decision,
  `policy.may`, answered from grants that live in the registry's `roles:`, the host's environment
  and the identity provider's group map — and it was written because five places answered that
  question and disagreed. An overlay that accepted `roles:` or `prod_approvers` would be a sixth.
  Adding a source of grants is ADR-0057's decision to make, not this record's.
- **It is ADR-0057 D4's principle, one layer over.** *The manifest narrows, never grants*: a
  project's `prod_approvers` narrows who of the approvers may approve and grants nothing. A layer
  that may only tighten cannot hold a key whose value grants — and a role, an approver list or an
  autonomy level is exactly such a key.
- **The other settings are refused rather than checked**, because they have no order a load-time
  check could hold the overlay to: there is no stricter harness and no stricter network. The ones
  that have an order (`review_mode`: `off` < `advisory` < `blocking`) are left to a record that
  wants them (*What is NOT decided here*).

### D7 — When the overlay is read, and what a refusal does

**Every process that reads the policy floor resolves the overlay once, as it starts, and holds the
result for its life** — the worker, the panel, a CLI command — the way `floor_document()` is read
once and cached for the process today. A job never re-reads it: the policy a job runs under is the
one its process started with, and its stamp (D3, D4) says which. An edit to a `dir` overlay takes
effect at the next start, as an edit to `.env.compose` does, and `openfactory doctor` warns while
the bytes on disk differ from the stamp the running deployment loaded (*"the gate overlay on disk
is not the one this deployment runs — restart to apply it"*).

**A refusal stops the process from starting.** Every refusal in this record —
`OPENFACTORY_GATE_OVERLAY_LOOSENS`, `_OUT_OF_SCOPE`, `_WRITABLE`, `_UNVERIFIED`, `_UNREADABLE`, an
unknown kind — makes the worker and the panel exit non-zero, printing the code, the exact entry
and the remedy, and a CLI command exit the same way. `openfactory doctor` is the one exception: it
reports the refusal as a failing line and carries on, because it is the command every remedy sends
the operator to.

**Why not hold every job instead**, which is what an unreadable shipped `floor.yaml` does: that
posture is `None`, and for `validate:` `None` holds only the projects that have no `security` of
their own (`org_default_validation`'s docstring). Reused here, a refused overlay would let every
project that declares its own gates run **without the gates the overlay existed to add** — the
failure would be open exactly where it matters. A start that does not happen leaves nothing
running under a policy the deployment named and cannot vouch for, and it is found at the restart
after the edit, not at a merge.

### D8 — Adding a gate is the operator's trust decision, and the deployment shows it

**What an addition can do, said plainly.** An added gate is a command that runs in every job's
box, against every project's clone, with whatever that box is handed. An added blocking gate that
always fails stops every merge; `protected_paths: ["**"]` sends every change to a person. By D2's
definition each is a tightening — nothing passes that would not have passed — and none is refused,
because a check cannot tell a strict deployment from a broken one: "every change waits for a
person" is a legitimate posture for a regulated one.

**So adding a gate is a trust decision, and it is the operator's.** The overlay's writer is the
host's owner (D3), or the bundle the host's owner pinned (D4, D5), and the trust it asks for is no
more than that owner already holds: `.env.compose` carries a forge credential with write access to
the repositories the deployment serves and the harness token that bills (`preflight._env_file`).
An overlay grants its writer no access they lacked; it gives them a place to put policy that a
reinstall does not erase.

**Recorded and shown, never implied:**

- at start, `OPENFACTORY_GATE_OVERLAY_APPLIED` logs the kind, the reference, the stamp and every
  entry — each added gate with its command and whether it blocks, each promoted baseline role,
  each added glob;
- `openfactory doctor` prints the same, and warns when an added glob matches every tracked path of
  a registered project, and while the bytes on disk differ from the loaded stamp (D7);
- `openfactory explain` names each overlay gate with its source and stamp, as it names the operator
  tier's guidelines;
- each gate's result in a pull request carries its name, so `deployment.<role>` says where it came
  from, and the job's journal carries the stamp;
- an added blocking gate that fails on untouched main holds pickup at `box prove` with a named
  finding (its `validate` station demands rc==0 of every blocking repo-wide gate on untouched
  main), so an always-failing gate is found as one held pickup per project, with its name — not as
  a fleet of paid jobs failing one at a time.

## Consequences

- **A deployment's policy stops being a patch on a shipped file.** Central gates and protected
  paths live in the operator's own directory or in a versioned, pinned bundle, survive a reinstall
  and an image rebuild, and are inherited by every deployment that mounts the same directory or
  pins the same bundle — which is what `org_defaults/floor.yaml` did for projects, now done for the
  deployment.
- **"Tighten never loosen" becomes a check, not a hope, at the one layer where it can.** The
  comparisons in D2 run over structured data; the prose cascade could never offer them. A baseline
  gate's command and timeout cannot be touched at all, so a redeclaration has nothing to hide a
  loosening in, and an added gate cannot be shadowed from below.
- **The strong form and the weak form stay apart.** Guidelines remain waivable prose
  (`OPENFACTORY_GUIDELINES_DIR`, ADR-0044); the gate overlay remains un-loosenable policy. Two
  names, two settings, two mutabilities — and the overlay's `dir` kind can still share a directory
  with the guidelines tier, so an operator keeps one home.
- **Who may act is not reopened.** The overlay holds gates and globs and is refused anything else
  (D6), so ADR-0057's one decision keeps its one set of sources, and the name `floor` keeps
  meaning ADR-0057's area on the wire.
- **A new supply-chain surface is opened deliberately and bounded.** A bundle's files reach the
  merge gate; the digest pin, the fail-closed verification, the safe unpack, the version stamp and
  the built-ins-win rule are the price of that, and they are the price ADR-0022 §3 and `plugins.py`
  already set for letting outside content in. A `dir` is held to its owner's write bit and to the
  stack's read-only mount instead.
- **A broken overlay is loud, and early.** It stops the deployment at start (D7) rather than
  failing open for the projects that declare their own gates; the cost is that a bad edit takes
  the deployment down at its next restart, which is when the operator who made it is looking.
- **A new axis must stay honest.** `gate_overlay` is born with `dir` and `bundle` (ADR-0022
  born-with-two, no stub), both reached through the one extension tree, both held to the same
  load-time checks. A third kind is a row, not a redesign.
- **Cost.** A new axis, a new read-and-verify step at start, a new env pair, a fetch/cache path for
  `bundle`, a reserved `deployment.` role prefix the manifest refuses, and the lines D8 adds to
  `doctor`, `explain` and the journal. The merge position keeps the cost off the hot path: the
  overlay joins the policy floor in `_inherit_the_deployment_floor`, so conformance and
  `applicable_validations` read one map, as today.

## Alternatives considered

- **B — put the overlay in the prompt/profile cascade (ADR-0044's layer 2).** This is the layer
  ADR-0044 already reserves "deployment overlay" for, so it is the tempting home. Rejected: that
  cascade's content is **prose**, which a profile may drop, and which has no `advisory` bit to
  promote and no protected path to add. The gates and protected paths a deployment wants to impose
  are the *strong* form; routing them through the weak form's cascade would either make them
  droppable (defeating the point) or force the prompt cascade to grow a strong-form half it was
  explicitly designed not to have. The two cascades meet different threat models (ADR-0044
  Decision 2 says so in as many words); the deployment's gates belong in the policy floor.
- **C — generalise the existing operator tier (`OPENFACTORY_GUIDELINES_DIR`) to also carry a
  `gates.yaml`.** Attractive because it reuses a directory, a containment check and a resolution
  posture that already exist. Rejected as the *primary* mechanism for the mutability reason in D3:
  one setting cannot own two forms with opposite loosening rules without collapsing the
  distinction the policy floor rests on. What survives from C is kept: the `dir` kind **shares the
  directory and the posture** (D3), so the operator still has one home — it just reads the policy
  file through a setting that means "this cannot be loosened," not through the one that means "a
  profile may waive this."
- **D — let an added gate be a default, like `floor.yaml`'s.** Simpler: the overlay's gates would
  merge exactly as the shipped ones do, and a project that declared the role would replace them.
  Rejected: then the overlay could only ever be a default, and a central gate a project could
  replace is the one the Context says is worth least. The shipped roles keep their default
  protocol because every existing manifest relies on it; an added role has no such history, so it
  is born binding.
- **E — on a refusal, hold every job rather than refuse to start.** It keeps the panel up to say
  why. Rejected for the reason in D7: the hold the core already has for a broken floor is `None`,
  and `None` fails open for every project that declares its own gates.

A — the gate overlay in the policy-floor cascade — is chosen because it is the only option where
the layer's content, its cascade position and its tightening rule all agree: strong-form content,
in the strong-form cascade, under a rule that is checkable because the content is structured.

## What is NOT decided here

- **No code ships with this ADR.** The axis, the two kinds, the load-time checks, the env pair, the
  reserved role prefix, the bundle fetch/verify/cache path and the lines D8 adds are
  implementation, deferred until this record is accepted (#990).
- **The bundle's transport beyond "a pinned, digest-verified archive"** — whether an OCI-registry
  reference is offered as a second `bundle` transport — is left to the implementation, within the
  format D4 fixes.
- **Signature verification is optional in D4**; making it mandatory (and how an operator configures
  the trusted key) is a follow-up a deployment with a stricter supply-chain posture can ask for,
  not a decision this record forces on every deployment.
- **Settings that do have an order.** `review_mode` (`off` < `advisory` < `blocking`) could be
  tightened by an overlay the way a gate is promoted; D6 refuses it today, and a record that wants
  it adds it with its own check.
- **The content-level gate protected.py names as still open** — a guard that reads a diff *hunk*
  rather than a path, so a coverage threshold inside `pyproject.toml` can be protected without
  human-gating every dependency bump — is unchanged by this ADR. The overlay carries path globs,
  the same shape `protected_paths` already carries; it does not add a content-level protection and
  does not close that open item.
