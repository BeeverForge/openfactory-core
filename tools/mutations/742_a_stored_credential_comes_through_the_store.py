"""A stored credential comes through one seam, the credential store, named by a reference (#742).

Run:  .venv/bin/python tools/mutate.py tools/mutations/742_a_stored_credential_comes_through_the_store.py

Rows 1-9 are the family's rule, the sweep: each reader the change moved goes back to reading its
variable, in each shape a read has taken (a literal, a module constant, a function handed the
environment, an alias, a reader), and the sweep over the package must see it; then the sweep's own
verifiers. Rows 10-15 are the store's semantics: a declared store first, a refusal never a
fallback, an unknown kind refused, upgrade safety byte for byte. Rows 16-22 the file store's
checks, and that it reads at each use. Rows 23-31 the readers the issue names, the box's
pass-through, a remote box, the worktree scrub and readiness. Rows 32-38 the image's pull
credential.
"""

TEST = "tests/test_a_stored_credential_comes_through_the_store.py"
SWEEP = "tests/test_every_stored_credential_is_read_through_the_store.py"
KNOBS = "tests/test_the_box_claims_only_what_it_does.py"

CREDENTIALS = "openfactory/credentials.py"
ADAPTER = "openfactory/adapters/agent/claude_code.py"
REGISTRY = "openfactory/adapters/credential_store/registry.py"
FILE = "openfactory/adapters/credential_store/file.py"
CONTAINER = "openfactory/adapters/sandbox/container.py"
WORKTREE = "openfactory/adapters/sandbox/worktree.py"
PULL = "openfactory/adapters/sandbox/pull.py"

MUTATIONS = [
    # ── the sweep sees every reader go back to its variable ─────────────────────────────────────
    ("the App key is read from its variable again (a literal)", CREDENTIALS,
     '    content = stored("OPENFACTORY_GH_APP_KEY_CONTENT")',
     '    content = os.environ.get("OPENFACTORY_GH_APP_KEY_CONTENT")', SWEEP),
    ("the harness's single token is read from its variable again", ADAPTER,
     '    if tok := stored("CLAUDE_CODE_OAUTH_TOKEN"):',
     '    if tok := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):', SWEEP),
    ("the token pool is handed the environment again, as it was read before", ADAPTER,
     "    pool, why = _pool_in(Stored())",
     "    pool, why = _pool_in(os.environ)", SWEEP),
    ("the panel's tokens are a snapshot of the environment again (an alias)",
     "openfactory/identity/local.py",
     "            env = held(CLOSING_ENVS)",
     "            env = dict(os.environ)", SWEEP),
    ("the gate key is read from its variable by its module constant", "openfactory/gate_seal.py",
     '    declared = (stored(VARIABLE) or "").strip()',
     '    declared = (os.environ.get(VARIABLE) or "").strip()', SWEEP),
    ("the provider's client secret is read from the environment through a reader",
     "openfactory/identity/oidc.py",
     "else _environment()))",
     "else os.environ))", SWEEP),
    ("the engine's API key is read from its variable again",
     "openfactory/runtime/temporal/connection.py",
     '    api_key = stored("TEMPORAL_API_KEY")',
     '    api_key = os.environ.get("TEMPORAL_API_KEY")', SWEEP),
    ("the sweep's exemption swallows the whole package", SWEEP,
     'STORE = PACKAGE / "adapters" / "credential_store"',
     "STORE = PACKAGE", SWEEP),
    ("the sweep stops reading an alias of the environment", SWEEP,
     "                and ast.unparse(node.func.value) in self.visible(node):",
     "                and False:", SWEEP),

    # ── the store: a declared store first, a refusal never a fallback, nothing moves undeclared ─
    ("a declared store is never asked: the environment answers for every credential", REGISTRY,
     "    if kind == ENV:\n        return None",
     "    if True:\n        return None"),
    ("a refusal falls back to the variable", REGISTRY,
     '    if refused:\n        return "", None',
     "    if refused:\n        return None"),
    ("an unknown store kind is read as the environment", REGISTRY,
     "    if builder is None:\n        raise ValueError(",
     "    if builder is None:\n        return _env()\n        raise ValueError("),
    ("a bare reference asks the environment alone, never the declared store", REGISTRY,
     "    if not kind:\n        return stored_answer(name)",
     "    if not kind:\n        return _ask(ENV, name)[:2]"),
    ("UPGRADE SAFETY: an undeclared deployment's variables are stripped on the way out", REGISTRY,
     "    return os.environ.get(name) or None\n",
     "    return (os.environ.get(name) or \"\").strip() or None\n"),
    ("UPGRADE SAFETY: an env-held credential loses the identity readers key it by", REGISTRY,
     '    return (f"{ENV}:{name}", value) if value else ("", None)',
     '    return (name, value) if value else ("", None)'),

    # ── the file store's checks, and a read at each use ─────────────────────────────────────────
    ("a file its group or anyone may write is trusted", FILE,
     "        writers = _writers(found.st_mode)\n        if writers:\n",
     "        writers = _writers(found.st_mode)\n        if False:\n"),
    ("a link leading out of the directory is followed", FILE,
     "        if os.path.commonpath([root, path]) != root or path == root:",
     "        if path == root:"),
    ("a reference may name a path, not a file", FILE,
     '        if not _NAME.fullmatch(name or ""):',
     "        if False:"),
    ("a pipe named like a secret is read as one", FILE,
     "        if not stat.S_ISREG(found.st_mode):",
     "        if False:"),
    ("a directory anyone may write to is trusted", FILE,
     "        if writers and not sticky:",
     "        if False:"),
    ("a file far larger than a credential is read whole", FILE,
     "        if found.st_size > MAX_BYTES:",
     "        if False:"),
    ("a secret read once is kept and served again after the file rotates", FILE,
     "    def resolve(self, name: str) -> str | None:\n        path, shared = self._located(name)",
     "    @__import__(\"functools\").lru_cache(maxsize=None)\n"
     "    def resolve(self, name: str) -> str | None:\n        path, shared = self._located(name)"),

    # ── the readers the issue names ─────────────────────────────────────────────────────────────
    ("a secret a file holds is taken for a login, not a value, so a vendor's own resolution drops "
     "it", CREDENTIALS,
     "    return bool(kind) and kind not in _NOT_A_STORE and kind in credential_store.known()",
     "    return kind == \"env\""),
    ("a remote box is handed the name of a file it cannot read", CREDENTIALS,
     "    if found.startswith(\"env:\") or not _stored_secret(found):\n        return None",
     "    if True:\n        return None"),
    ("a value is written into a remote box's launch where a name sufficed", CREDENTIALS,
     "    if found.startswith(\"env:\") or not _stored_secret(found):",
     "    if not _stored_secret(found):"),
    ("the container box names a file-held variable and docker has no value for it", CONTAINER,
     "        return {**os.environ, **passing}",
     "        return dict(os.environ)"),
    ("the container box reads a `box.env` name from the environment alone", CONTAINER,
     "            if var not in seen and (value := stored(var)):",
     "            if var not in seen and (value := os.environ.get(var)):"),
    ("a file undoes the token the pool rotated to", CONTAINER,
     "(value := os.environ.get(var) or stored(var))",
     "(value := stored(var) or os.environ.get(var))"),
    ("a worktree workload loses a declared name held in a file", WORKTREE,
     "            if value := stored(var):",
     "            if value := None:"),
    ("the path to every secret reaches a worktree workload", WORKTREE,
     '                      "OPENFACTORY_CREDENTIAL_DIR")',
     "                      )"),
    ("readiness reports a name the box receives from a file as not set",
     "openfactory/onboarding/readiness.py",
     "    absent = [n for n in names if env.get(n) is None and p.stored(n) is None]",
     "    absent = [n for n in names if env.get(n) is None]"),

    # ── the image's pull credential: for the pull, never for the box ────────────────────────────
    ("the pull uses the worker's shared client configuration", PULL,
     '            done = run(["docker", "--config", config, "pull", "--quiet", image],',
     '            done = run(["docker", "pull", "--quiet", image],'),
    ("the login outlives the pull", PULL,
     "        shutil.rmtree(config, ignore_errors=True)",
     "        pass"),
    ("an image with no host is logged in under a key the client never reads", PULL,
     "_HUB_KEY if registry == HUB else registry",
     "registry"),
    ("the box pulls again an image the daemon holds, moving the digest a proof pinned", CONTAINER,
     '        if _host(["docker", "image", "inspect", self.image])[0] == 0:\n            return',
     "        if False:\n            return"),
    ("a refused pull starts the box anyway", CONTAINER,
     "        if not pulled:\n            raise RuntimeError(",
     "        if False:\n            raise RuntimeError("),
    ("the registry's pull credential never reaches the box", "openfactory/factory.py",
     '        knobs["pull_credential"] = pull',
     "        pass", KNOBS),
    ("box prove pulls without the project's credential", "openfactory/box_prove.py",
     "        if credential is not None:\n            pulled = pull(img, credential)[0]",
     "        if False:\n            pulled = pull(img, credential)[0]"),

    # ── the doctor ───────────────────────────────────────────────────────────────────────────────
    ("the doctor's line runs nowhere", "openfactory/doctor.py",
     "        credential_store=lambda: credential_store_line(project),\n",
     ""),
    ("a reference that can never answer passes the doctor", "openfactory/doctor.py",
     "        if why := store.refusal(reference):",
     "        if why := \"\":"),
    ("a pull credential with no user name or no secret passes the doctor", "openfactory/doctor.py",
     "    if pull is not None and not store.refusal(pull.reference) and (why := pull_problem(pull)):",
     "    if False:"),
]
