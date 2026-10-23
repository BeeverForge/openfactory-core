"""The manifest a new project starts from — what `project_init` writes into a checkout that has
none (#741).

It lived in the command line, as `cli._MANIFEST_TEMPLATE`, because `openfactory project init` was
the only thing that wrote it. Initialising a project is the `project_init` action now, which the
command maps onto, and an action does not import a front end — so the template lives beside the
other onboarding code, and the comments it carries for the person who opens the file are unchanged.
"""

MANIFEST_TEMPLATE = """\
# .openfactory/project.yaml — this project's plug into the platform contract.
# The framework knows nothing about this project except what is declared here.
# This is a STARTER — see docs/project.yaml.example for the full annotated reference.
version: 1
base_branch: main

# Autonomy at merge: "human" = bot opens the PR, a human merges; "auto" = merges itself when
# gates are green + review didn't reject + no high-risk component touched.
merge_policy: human

# ADR-0014 (defaults shown — omit to accept). planner_stage false = single agent (plan+code in
# one pass). review_mode advisory = the review comments on the PR but never blocks/repairs.
# planner_stage: false
# review_mode: advisory

setup:
  - "pip install -e '.[dev]'"   # how to install deps in the ephemeral workspace
  # - "npm ci"

# Repo-wide validation — the REAL quality floor. The platform runs these and reads the exit
# codes; it does NOT trust the agent to have run them. Map them to YOUR repo's commands.
validate:
  test: "pytest -q"
  # THE FLOOR REQUIRES A `security` ROLE AND THIS TEMPLATE DID NOT DECLARE ONE. `openfactory project
  # init`
  # therefore wrote a manifest that `openfactory conformance` — the very next step in ONBOARDING.md
  # —
  # refused. A client following our own script, with our own file, was told they had done it wrong,
  # and there was nothing they could have done differently.
  #
  # ADVISORY, so a starter project passes its floor on day one without anything being imposed: it
  # reports findings and never blocks a merge. A first scan of any real codebase reports the
  # accumulated debt of its whole history, and none of that is the first ticket's fault. A client
  # who wants it blocking sets `advisory: false`, deliberately.
  #
  # semgrep because it is free, offline-installable and needs no licence conversation — the same
  # reasoning as the `security-oss` preset, inlined here because presets attach to a COMPONENT's
  # stack (`components[].stack`) and a starter project declares no components.
  security:
    command: "semgrep --config=auto --error --quiet ."
    advisory: true
    timeout_minutes: 20
  # lint: "ruff check ."
  # type: "mypy ."

docs:
  constraints: docs/adr/**        # ADRs — the constitution, newest first under the budget
  # architecture: docs/architecture/**
  # guidelines: [.openfactory/guidelines/execution.md]

# Declare components only if the repo is polyglot / has risk zones; each maps a diff area to a
# stack (preset) + risk. A risk: high component always stays human-gated, even on auto.
components: {}
  # backend:
  #   path: app/
  #   stack: python
  #   risk: normal
  # infra:
  #   path: terraform/
  #   stack: terraform
  #   risk: high

# Post-merge deploy watch (optional — ADR-0005): observe your repo's CI deploy after merge.
# post_merge_deploy: { workflow: deploy.yml, env: dev, timeout_minutes: 30 }
"""
