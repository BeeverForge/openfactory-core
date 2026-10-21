# ADR 0058 — The floor takes an overlay: a deployment's own policy, applied from outside the package, that may only tighten

- **Status:** **Proposed** (design only — no code changes with this ADR; a maintainer accepts it in review)
- **Date:** 2026-10-21
- **Implements:** #990 — the policy floor has no operator-provided layer. This ADR decides the
  shape; implementation is deferred until the ADR is accepted.
- **Relates to:**
  - [ADR-0001](0001-foundational-conceptual-model.md) D-2 (project knowledge is a cascade;
    each layer tightens, never loosens): this names a new home for the deployment's half of
    layer 1, the floor.
  - [ADR-0022](0022-provider-seams.md) (an axis is agnostic when it is BORN with two) and
    [`docs/core/07-extensibility.md`](../core/07-extensibility.md) (a stranger adds the third
    without editing our files): the overlay is reached through that tree, and ships with its two
    kinds.
  - [ADR-0044](0044-a-project-declares-what-it-is.md): it **reserves the name "deployment
    overlay" for the PROMPT/profile cascade** (its own layer 2, which "does not exist yet"), and
    it draws the line this ADR depends on — *gates are the strong form, prose is the weak one; a
    profile may drop a guideline and may never remove a gate.* This ADR is the strong form's
    operator layer, and takes a **different name** so the two never collide.

## Context

The policy floor is the one layer of the cascade a project may not loosen (ADR-0001 D-2, layer 1).
In the tree it has exactly two homes, and both ship **inside the `openfactory` package**:

| home | what it carries | read by |
|---|---|---|
| `openfactory/policy/floor.py` | the hardcoded framework baseline — `REQUIRED_VALIDATION_ROLES` (`test`, `security`) and `GLOBAL_DENY` (prose that names the code enforcing each denial) | `policy/conformance`, the orchestrator |
| `openfactory/org_defaults/floor.yaml` | the deployment's **default** `validate:` gates and `protected_paths:` | `policy/presets.py::org_default_validation`, `policy/protected.py::floor_protected_paths`, merged into every project by `contracts/manifest.py::_inherit_the_deployment_floor` |

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
waive or replace one (ADR-0044), because prose only ever reaches the agent's prompt. The floor is
the **strong** form: its gates and protected paths reach the merge decision, and nothing may
switch them off. The strong form is the one with no operator home, and it is the one that most
needs an un-forkable one — a central security gate an operator can mount is worth more than one a
project could argue with.

This is a generic concern for anyone running a single deployment of the core. It is not about any
particular organisation's policy; it is about where a deployment's policy *lives* so that it is
not a patch on a shipped file.

## Decision

### D1 — The name: the **floor overlay**, and why not "deployment overlay"

The new layer is the **floor overlay**: the deployment's own floor, supplied from **outside** the
package and laid **over** the shipped baseline.

- **"floor"** is the tree's own word for the strong, non-loosenable form — `policy/floor.py`,
  `floor.yaml`, `floor_document`, `floor_protected_paths`, `floor_reason`, `floor_unreadable`.
  Naming the layer after it says, in one word, which half of the cascade it belongs to: the gates
  and protected paths, not the prose.
- **"overlay"** — not "layer" or "tier" — because it is **applied on top of** the shipped floor
  from outside the distribution, the way an overlay mount sits over a base filesystem. It adds to
  what is underneath and cannot cut into it. "layer" would read as a new tier baked into the
  package beside `floor.yaml`; the point is that it is *not* in the package.
- **Not "deployment overlay".** ADR-0044's closing paragraph reserves that exact name for the
  **prompt/profile cascade's layer 2** ("the deployment-overlay layer … does not exist yet").
  Reusing it would put the strong form and the weak form under one word — the precise collapse
  ADR-0044 and `policy/protected.py` are built to prevent. Two names, because the two layers
  disagree on the one question that matters: whether a lower layer may remove what they add. The
  prompt overlay's content can be dropped by a profile; the floor overlay's cannot be dropped by
  anyone. A shared name would invite a shared mechanism, and the mechanisms must differ because
  the threat models do.

### D2 — Where it merges, and the rule that it may only tighten

**The floor overlay merges between the shipped `org_defaults/floor.yaml` and the project**, so the
cascade the project inherits reads:

```
policy/floor.py            framework baseline      (REQUIRED_VALIDATION_ROLES, GLOBAL_DENY)
org_defaults/floor.yaml    deployment default      shipped in the package
  ── the floor overlay ──  deployment's own floor  mounted / fetched from outside the package   ← new
.openfactory/project.yaml  the project             adds, never subtracts (as today)
```

Concretely, and with the invariant `_inherit_the_deployment_floor` already protects in mind: the
overlay is read into the **same shape `floor.yaml` already has** — a `validate:` map of role → gate
and a `protected_paths:` list — and folded into the *effective deployment floor* that
`org_default_validation()` and `floor_protected_paths()` return. Those two accessors are the one
place both `policy/conformance._effective_validation` (which inspects the floor) and
`orchestrator/validation.applicable_validations` (which executes it) read the same answer from, so
the overlay joins the floor **before** `_inherit_the_deployment_floor` applies it to the project.
Nothing downstream of that method learns a new word: a project still inherits a floor, and the
floor now includes the operator's additions. The `None`-is-not-`{}` posture carries over
unchanged — an overlay named but unreadable yields `None`, which the callers already turn into a
hold, not into permission.

**The overlay may only ever tighten the baseline.** Each of these is rejected:

| attempted move | detected by | result |
|---|---|---|
| remove a baseline validation role (e.g. drop `security`) | the merge is **additive** for `validate:` — an overlay cannot *express* a removal, it can only redeclare — and a redeclaration is held to the strictness check below; `REQUIRED_VALIDATION_ROLES` is independently re-asserted after the merge | refused at load |
| weaken a gate — demote a **blocking** gate to `advisory: true`, or shorten the command it runs to a no-op shape | for every role the baseline declares, the merged gate's `advisory` must be **≤** the baseline's (blocking cannot become advisory) and the command must still be present; a redeclaration that loosens is a loosening, not an addition | refused at load |
| drop a protected path | `protected_paths` merges as a **union** (as `effective_protected_paths` already unions the floor with a project's own) — an overlay adds globs and cannot delete one; every baseline glob must survive the merge | refused at load |

A refusal is **fail-closed and named**: it logs `OPENFACTORY_FLOOR_OVERLAY_LOOSENS` identifying the
exact role or path and what it tried to weaken, and the deployment refuses to serve the floor —
the same direction `floor_document()` takes for an unreadable floor, and for the same reason an
off switch for the floor is the first thing that gets set (`org_defaults/floor.yaml`). The overlay
is allowed to **add** a role, **add** a protected glob, and **promote** an advisory gate to
blocking (`advisory: true → false`); those are tightenings, which is the whole purpose. What it
may never do is make the merged floor weaker than the floor shipped underneath it, and because the
check compares the *post-merge* result against the *shipped baseline*, a loosening cannot hide in
a clever redeclaration.

This is where "tighten never loosen" earns a crisp, machine-checkable meaning that it does **not**
have in the prose cascade: a guideline has no `advisory` bit and no gate to demote, so "cannot
loosen" was never expressible over prose (ADR-0044 says as much). Over the floor it is three
comparisons on structured data.

### D3 — The axis, born with two kinds: `dir` and `bundle`

The overlay is a provider axis in the ADR-0022 sense, and it ships **born with two** real kinds —
no stub (ADR-0022 §5), reached through the entry-point tree `openfactory/plugins.py` already
carries (`docs/core/07-extensibility.md`): a new axis `floor_overlay`, registered the same way
`preview` and the rest are, resolved `kind → builder`, an unknown kind refusing by name.

- **`dir`** — the operator mounts or links a directory and the overlay reads a `floor.yaml` from
  it. This is the directly-controlled case: the files are on the operator's own disk, versioned
  however the operator versions them, changed by editing them.
- **`bundle`** — the deployment fetches a **versioned archive** and the overlay reads the
  `floor.yaml` unpacked from it. This is the distributed case: a central policy, authored once and
  pulled by many deployments, pinned to a version.

**Reconciling `dir` with `OPENFACTORY_GUIDELINES_DIR`: it sits beside the guidelines tier, sharing
its posture, and does not supersede it.** The two are deliberately kept apart because they carry
different forms of rule with different mutability:

- the guidelines directory feeds **prose** into the prompt, and a profile may waive or replace any
  of it (ADR-0044) — it is advisory by nature;
- the floor overlay feeds **gates and protected paths** into the merge decision, and nothing may
  loosen it.

Folding the floor overlay into `OPENFACTORY_GUIDELINES_DIR` would force one of two collapses:
either prose becomes un-waivable (breaking ADR-0044's whole point about the weak form) or the
floor becomes waivable (breaking the strong form). So the overlay gets its **own** deployment
setting (D5), and its `dir` kind **may point at the same directory** an operator already uses for
guidelines — one home for an organisation's standards — reading the policy file there while the
guidelines tier keeps reading the `*.md`. It **generalises the operator-directory idea to a second
content type** and sits beside the first; it does not replace it. The containment check is the
same one `operator_guidelines._contained` already applies — every path resolved, must stay under
the configured root, a symlink leading out ignored with a warning — because, unlike guidelines,
these files decide whether a change may merge, so a link that escaped the directory would be worse
here, not better.

### D4 — The `bundle` format, a supply-chain surface

A bundle's files reach the merge gate, so the bundle is a supply-chain surface and is specified as
one. The format:

- **The container is a versioned, immutable archive** — a gzip-compressed tar (`.tar.gz`) holding a
  `floor.yaml` at a known path (and nothing it needs beyond that). It is addressed by an
  operator-provided reference **and a required `sha256` digest**; the reference names where to
  fetch, the digest names *what* must come back.
- **Fetched once, resolved at deployment start, cached content-addressed.** The bundle is pulled
  when the deployment boots (or on first use) into a cache keyed by its digest — the same
  ephemeral-state / persistent-cache split ADR-0001 D-4 draws for dependencies. It is **never
  fetched per job**: a job reads the already-unpacked, already-verified cache, so the floor a job
  runs under is deterministic and does not depend on a network call at pickup time.
- **Verified before it is trusted, fail-closed.** The fetched bytes must match the pinned `sha256`
  or the deployment refuses to serve the floor (`OPENFACTORY_FLOOR_OVERLAY_UNVERIFIED`), the same
  direction as an unreadable floor. The digest pin is what makes a swapped bundle *detectable*
  rather than silent. An **optional** detached signature, checked against an operator-configured
  public key, is supported for deployments that want provenance as well as integrity; absent a
  configured key, the digest is the trust anchor and the ADR does not pretend otherwise.
- **Unpacked safely.** Extraction rejects any entry that escapes the target directory (a traversal
  path, an absolute member, a symlink pointing out) — the containment posture of D3, applied to
  archive members. A malformed archive is a refusal, not a partial read.
- **Version-stamped, and the stamp is journaled.** The bundle carries a version string and its
  digest, and which version applied to a job is written where a reader of the change can see it —
  exactly as `operator_guidelines._git_version` stamps which revision of the central guidelines
  shaped a job. A floor that decided a merge without a recorded version would be a promise, not a
  mechanism.
- **Built-ins win, and a loosening is refused outright.** The shipped floor
  (`policy/floor.py` + `org_defaults/floor.yaml`) is the built-in, and the overlay — `dir` or
  `bundle` — may only add to or tighten it (D2). This is the same reasoning `plugins.py` gives for
  a built-in winning a collision: *"an add-on that could redefine `github` for every project on a
  deployment is a supply chain, not an extension point."* A bundle that could weaken what the
  floor means for every job is that supply chain. The one difference from `plugins.py` is the
  consequence: a plugin collision resolves silently in the built-in's favour and is logged,
  whereas a floor overlay that attempts to **loosen** is a hard, named refusal that holds the
  deployment — because the floor's entire value is that it cannot be made weaker, so a quiet
  "built-in won" would understate what just happened.

### D5 — Resolution is the deployment's alone

The overlay is named by the **process environment only**, never by a project's manifest and never
by an add-on package — the identical rule, and the identical reason, as `OPENFACTORY_GUIDELINES_DIR`:
*"a value a project or a stranger's wheel could set would let untrusted content decide what every
job on the deployment reads"* — and here it would decide what every job must **pass**, which is
worse. The environment belongs to whoever runs the stack.

- `OPENFACTORY_FLOOR_OVERLAY` carries the reference (a directory path for `dir`; a fetch reference
  plus its pinned digest for `bundle`), and `OPENFACTORY_FLOOR_OVERLAY_KIND` names the kind, so
  the `floor_overlay.<kind>` registry resolves it the ADR-0022 way; an unknown kind refuses at
  startup naming what IS installed.
- A project's manifest cannot set it, cannot point at it, and cannot opt out of it. A project may,
  as today, **add** its own gates and protected paths on top of the overlay (it inherits the
  overlay as part of the floor); it may not subtract from it, for the same reason it cannot
  subtract from the shipped floor.
- An add-on package may ship an additional `floor_overlay` *kind* (a new fetch mechanism) through
  the entry-point tree, but it cannot ship *content* and it cannot shadow a built-in kind — built-ins
  win (D4).

## Consequences

- **A deployment's policy stops being a patch on a shipped file.** Central gates and protected
  paths live in the operator's own directory or in a versioned, pinned bundle, survive a reinstall
  and an image rebuild, and are inherited by every deployment that mounts the same directory or
  pins the same bundle — which is what `org_defaults/floor.yaml` did for projects, now done for the
  deployment.
- **"Tighten never loosen" becomes a check, not a hope, at the one layer where it can.** The three
  comparisons in D2 run over structured data; the prose cascade could never offer them.
- **The strong form and the weak form stay apart.** Guidelines remain waivable prose
  (`OPENFACTORY_GUIDELINES_DIR`, ADR-0044); the floor overlay remains un-loosenable policy. Two
  names, two settings, two mutabilities — and the overlay's `dir` kind can still share a directory
  with the guidelines tier, so an operator keeps one home.
- **A new supply-chain surface is opened deliberately and bounded.** A bundle's files reach the
  merge gate; the digest pin, the fail-closed verification, the safe unpack, the version stamp and
  the built-ins-win rule are the price of that, and they are the price ADR-0022 §3 and `plugins.py`
  already set for letting outside content in.
- **A new axis must stay honest.** `floor_overlay` is born with `dir` and `bundle` (ADR-0022
  born-with-two, no stub), both reached through the one extension tree, both held to the same
  load-time tightening check. A third kind is a row, not a redesign.
- **Cost.** A new axis, a new read-and-verify step at deployment start, a new env pair, and a
  fetch/cache path for `bundle`. The merge position is chosen to keep the cost off the hot path:
  the overlay folds into the floor the two existing accessors already return, so
  `_inherit_the_deployment_floor`, conformance and `applicable_validations` are untouched in shape.

## Alternatives considered

- **B — put the overlay in the prompt/profile cascade (ADR-0044's layer 2).** This is the layer
  ADR-0044 already reserves "deployment overlay" for, so it is the tempting home. Rejected: that
  cascade's content is **prose**, which a profile may drop, and which has no `advisory` bit to
  promote and no protected path to add. The gates and protected paths a deployment wants to impose
  are the *strong* form; routing them through the weak form's cascade would either make them
  droppable (defeating the point) or force the prompt cascade to grow a strong-form half it was
  explicitly designed not to have. The two cascades meet different threat models (ADR-0044
  Decision 2 says so in as many words); the floor's operator layer belongs in the floor.
- **C — generalise the existing operator tier (`OPENFACTORY_GUIDELINES_DIR`) to also carry a
  `floor.yaml`.** Attractive because it reuses a directory, a containment check and a resolution
  posture that already exist. Rejected as the *primary* mechanism for the mutability reason in D3:
  one setting cannot own two forms with opposite loosening rules without collapsing the
  distinction the whole floor rests on. What survives from C is kept: the `dir` kind **shares the
  directory and the posture** (D3), so the operator still has one home — it just reads the policy
  file through a setting that means "this cannot be loosened," not through the one that means "a
  profile may waive this."

A — the floor overlay in the policy/floor cascade — is chosen because it is the only option where
the layer's content, its cascade position and its tightening rule all agree: strong-form content,
in the strong-form cascade, under a rule that is checkable because the content is structured.

## What is NOT decided here

- **No code ships with this ADR.** The axis, the two kinds, the load-time tightening check, the
  env pair and the bundle fetch/verify/cache path are implementation, deferred until this record is
  accepted (#990).
- **The bundle's fetch mechanism beyond "a pinned, digest-verified archive"** — whether a `dir`
  kind's directory may itself be a checkout stamped by its commit (as the guidelines tier reads a
  `.git` revision), and whether an OCI-registry reference is offered as a second `bundle` transport
  — is left to the implementation, within the format D4 fixes.
- **Signature verification is optional in D4**; making it mandatory (and how an operator configures
  the trusted key) is a follow-up a deployment with a stricter supply-chain posture can ask for,
  not a decision this record forces on every deployment.
- **The content-level gate protected.py names as still open** — a guard that reads a diff *hunk*
  rather than a path, so a coverage threshold inside `pyproject.toml` can be protected without
  human-gating every dependency bump — is unchanged by this ADR. The overlay carries path globs,
  the same shape `protected_paths` already carries; it does not add a content-level protection and
  does not close that open item.
