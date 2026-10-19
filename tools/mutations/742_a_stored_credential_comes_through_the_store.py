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

Rows 42 onward are the reviews of #822. A refusal is final: it opens no door, and nothing is used
in its place — the panel, the identity provider, every credential chain, the mint and the
provider after it, the harness, both boxes, the gate and preview keys, the engine, and every
doctor, readiness and onboarding line that asks whether a credential is configured (the family
test, `tests/test_a_refused_credential_opens_no_door.py`). Then the file store on a read-only
mount, its repairs and a byte-order mark; the pull's redaction, a job that pulls first, and the
pull reaching the box's daemon; and the sweep reading tables. Last, every `gh` the package starts,
and every link on a name's way.
"""

TEST = "tests/test_a_stored_credential_comes_through_the_store.py"
SWEEP = "tests/test_every_stored_credential_is_read_through_the_store.py"
KNOBS = "tests/test_the_box_claims_only_what_it_does.py"
FAMILY = "tests/test_a_refused_credential_opens_no_door.py"
GATE = "tests/test_a_refused_gate_key_is_said_as_itself.py"

CREDENTIALS = "openfactory/credentials.py"
ADAPTER = "openfactory/adapters/agent/claude_code.py"
REGISTRY = "openfactory/adapters/credential_store/registry.py"
FILE = "openfactory/adapters/credential_store/file.py"
CONTAINER = "openfactory/adapters/sandbox/container.py"
WORKTREE = "openfactory/adapters/sandbox/worktree.py"
PULL = "openfactory/adapters/sandbox/pull.py"
ACTIVITIES = "openfactory/runtime/temporal/activities.py"

MUTATIONS = [
    # ── the sweep sees every reader go back to its variable ─────────────────────────────────────
    # re-pinned 2026-10-19 (#822): the App key's content is looked up as an `Answer`
    ("the App key is read from its variable again (a literal)", CREDENTIALS,
     '    content = credential_store.lookup("OPENFACTORY_GH_APP_KEY_CONTENT")',
     '    content = credential_store.Answer(value=os.environ.get("OPENFACTORY_GH_APP_KEY_CONTENT"))',
     SWEEP),
    # re-pinned 2026-10-19 (#822): the single token is asked of the walk's `Stored`
    ("the harness's single token is read from its variable again", ADAPTER,
     '    if tok := settings.get("CLAUDE_CODE_OAUTH_TOKEN"):',
     '    if tok := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):', SWEEP),
    # re-pinned 2026-10-19 (#822): one `Stored` walk
    ("the token pool is handed the environment again, as it was read before", ADAPTER,
     "    settings = Stored()\n    pool, why = _pool_in(settings)",
     "    settings = Stored()\n    pool, why = _pool_in(os.environ)", SWEEP),
    ("the panel's tokens are a snapshot of the environment again (an alias)",
     "openfactory/identity/local.py",
     "            env = held(CLOSING_ENVS)",
     "            env = dict(os.environ)", SWEEP),
    # re-pinned 2026-10-19 (#822): the key is looked up as an `Answer`, refusal and all
    ("the gate key is read from its variable by its module constant", "openfactory/gate_seal.py",
     '    declared = (found.value or "").strip()',
     '    declared = (os.environ.get(VARIABLE) or "").strip()', SWEEP),
    ("the provider's client secret is read from the environment through a reader",
     "openfactory/identity/oidc.py",
     "else _environment()))",
     "else os.environ))", SWEEP),
    # re-pinned 2026-10-19 (#822): the key is looked up as an `Answer`
    ("the engine's API key is read from its variable again",
     "openfactory/runtime/temporal/connection.py",
     '        return {"api_key": api_key.value, "tls": True}',
     '        return {"api_key": os.environ.get("TEMPORAL_API_KEY"), "tls": True}', SWEEP),
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
    # re-pinned 2026-10-19 (#822): a refusal is an `Answer` of its own
    ("a refusal falls back to the variable", REGISTRY,
     "    return found if (found.value or found.refused) else None",
     "    return found if found.value else None"),
    ("an unknown store kind is read as the environment", REGISTRY,
     "    if builder is None:\n        raise ValueError(",
     "    if builder is None:\n        return _env()\n        raise ValueError("),
    # re-pinned 2026-10-19 (#822): `answer` is `look`'s, which asks `lookup` for a bare name
    ("a bare reference asks the environment alone, never the declared store", REGISTRY,
     "    if not kind:\n        return lookup(name, quiet=quiet)",
     "    if not kind:\n        return _ask(ENV, name, quiet=quiet)"),
    ("UPGRADE SAFETY: an undeclared deployment's variables are stripped on the way out", REGISTRY,
     "    return os.environ.get(name) or None\n",
     "    return (os.environ.get(name) or \"\").strip() or None\n"),
    # re-pinned 2026-10-19 (#822): the identity is built once, in `lookup`, which `answer` and
    # `stored_answer` both ask — the old anchor was a second copy nothing tested any more
    ("UPGRADE SAFETY: an env-held credential loses the identity readers key it by", REGISTRY,
     '    return Answer(reference=f"{ENV}:{name}", value=value) if value else NOTHING',
     "    return Answer(reference=name, value=value) if value else NOTHING"),

    # ── the file store's checks, and a read at each use ─────────────────────────────────────────
    # re-pinned 2026-10-19 (#822): a read-only mount is asked beside the bits
    ("a file its group or anyone may write is trusted", FILE,
     "        writers = _writers(found.st_mode)\n        if writers and not _mount_refuses_writes(fd=fd):\n",
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
    # re-pinned 2026-10-19 (#822): a read-only mount is asked beside the bits
    # re-pinned 2026-10-19 (#822, second round): a sticky bit no longer excuses a writable directory
    # re-pinned 2026-10-19 (#822, third round): one rule for every directory a secret is read through
    ("a directory anyone may write to is trusted", FILE,
     "        if not _mount_refuses_writes(path=here):",
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
    # RETIRED 2026-10-19 (#822, third round): "a remote box is handed the name of a file it cannot
    # read" — a remote box is handed no stored secret at all now (#903); its rule is the row below.
    ("a secret the store holds reaches a remote launcher, its value in the launch", CREDENTIALS,
     "            if held := _held_in_a_store(project, axis):",
     "            if held := \"\":", TEST),
    # re-pinned 2026-10-19 (#822, third round): the hand-over is a refusal now, and a variable the
    # box reads for itself is still handed over by name
    ("a variable the box reads for itself is refused as if a store held it", CREDENTIALS,
     "    if found.startswith(\"env:\") or not _stored_secret(found):\n        return \"\"",
     "    if not _stored_secret(found):\n        return \"\""),
    ("the container box names a file-held variable and docker has no value for it", CONTAINER,
     "        return {**os.environ, **passing}",
     "        return dict(os.environ)"),
    # re-pinned 2026-10-19 (#822): the names are looked up as `Answer`s
    ("the container box reads a `box.env` name from the environment alone", CONTAINER,
     "            if var not in seen and (value := lookup(var).value):",
     "            if var not in seen and (value := os.environ.get(var)):"),
    # re-pinned 2026-10-19 (#822): the process's own value is its `env:` reference
    ("a file undoes the token the pool rotated to", CONTAINER,
     '            if value := look(f"{ENV}:{var}").value or found.value:',
     '            if value := found.value or look(f"{ENV}:{var}").value:'),
    # re-pinned 2026-10-19 (#822): the declared names are looked up as `Answer`s
    ("a worktree workload loses a declared name held in a file", WORKTREE,
     "            elif var in kept and found.value:",
     "            elif False:"),
    ("the path to every secret reaches a worktree workload", WORKTREE,
     '                      "OPENFACTORY_CREDENTIAL_DIR")',
     "                      )"),
    # re-pinned 2026-10-19 (#822): a refused name is said apart from an absent one
    ("readiness reports a name the box receives from a file as not set",
     "openfactory/onboarding/readiness.py",
     "    absent = [n for n in names if n not in refused and env.get(n) is None and p.stored(n) is None]",
     "    absent = [n for n in names if n not in refused and env.get(n) is None]"),

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

    # ── after the reviews of #822: a refusal opens no door ──────────────────────────────────────
    ("BLOCKER: a refused closing variable opens the panel to everyone", "openfactory/identity/local.py",
     '        if self._refused:\n            log.error("OPENFACTORY_IDENTITY_REFUSED',
     '        if False:\n            log.error("OPENFACTORY_IDENTITY_REFUSED', FAMILY),
    ("the local row is built over a refusal, so the panel answers 401 where it cannot check",
     "openfactory/identity/registry.py",
     "    if refused := provider.misconfiguration():\n        raise ValueError(refused)",
     "    if False:\n        raise ValueError(refused)", FAMILY),
    ("a refused closing variable still admits the tokens the store did hand over",
     "openfactory/identity/local.py",
     "            if not token or self._refused:\n                return None",
     "            if not token:\n                return None", FAMILY),
    ("a refused client secret reads as a public client", "openfactory/identity/oidc.py",
     "        if self._refused:\n            # the variable's name",
     "        if False:\n            # the variable's name", FAMILY),
    ("a chain walks past a refusal to its next name", REGISTRY,
     "        if found.value or found.refused:\n            return found\n    return NOTHING",
     "        if found.value:\n            return found\n    return NOTHING", FAMILY),
    ("a refused tracker override is answered by the bot's token", CREDENTIALS,
     '    return credential_store.chain(("OPENFACTORY_TRACKER_TOKEN", "OPENFACTORY_BOT_TOKEN")).value',
     '    return stored("OPENFACTORY_TRACKER_TOKEN") or stored("OPENFACTORY_BOT_TOKEN")', FAMILY),
    ("a refused project reference falls back to the deployment's own", CREDENTIALS,
     "        found = credential_store.look(named)\n        if found.refused:",
     "        found = credential_store.look(named)\n        if False:", FAMILY),
    ("a refused vendor default falls back to the deployment's pair", CREDENTIALS,
     "        found = credential_store.lookup(default)\n        if found.refused:",
     "        found = credential_store.lookup(default)\n        if False:", FAMILY),
    ("a refused pair is not said, so the mint after it answers", CREDENTIALS,
     "    found = credential_store.chain(_GENERIC[axis])\n    return _refused_at(",
     "    found = credential_store.NOTHING\n    return _refused_at(", FAMILY),
    ("a mint answers after a refused reference", CREDENTIALS,
     '    if axis_refusal(project, "tracker"):\n        return None\n'
     '    return _deployment_mint(getattr(project, "tracker", None))',
     '    if False:\n        return None\n'
     '    return _deployment_mint(getattr(project, "tracker", None))', FAMILY),
    ("a provider answers after a refused reference", CREDENTIALS,
     '    if axis_refusal(project, "forge"):\n        return None\n'
     '    return _deployment_provider(getattr(project, "forge", None))',
     '    if False:\n        return None\n'
     '    return _deployment_provider(getattr(project, "forge", None))', FAMILY),
    ("the App key's path answers after its refused content", CREDENTIALS,
     "    if content.refused:\n        return None\n    path = ",
     "    if False:\n        return None\n    path = ", FAMILY),
    ("a refused bot token is replaced by a mint", "openfactory/adapters/github_app.py",
     "    if found.refused:\n        return None\n    from openfactory.credentials import",
     "    if False:\n        return None\n    from openfactory.credentials import", FAMILY),
    ("Azure falls back to a person's login over a refused PAT", "openfactory/adapters/azure_devops.py",
     "    if found.refused:\n        # A REFUSED SECRET IS NOT AN ABSENT ONE",
     "    if False:\n        # A REFUSED SECRET IS NOT AN ABSENT ONE", FAMILY),
    ("a mapping walk goes on past a refusal", REGISTRY,
     "        if self.refused:\n            return default\n        found = lookup(name)",
     "        if False:\n            return default\n        found = lookup(name)", FAMILY),
    # re-pinned 2026-10-19 (#822, second round): any refused name stops it, the pool answering or not
    ("the harness runs when its credential was refused, and the CLI reads the next variable",
     ADAPTER,
     '        if getattr(self, "_refused", None):',
     "        if False:", FAMILY),
    ("the container box passes a refused harness default's variable", CONTAINER,
     "            if var in seen or (found := lookup(var)).refused:\n                continue",
     "            if var in seen:\n                continue\n            found = lookup(var)", FAMILY),
    ("the worktree box keeps a refused name's variable", WORKTREE,
     "            if found.refused:\n                env.pop(var, None)",
     "            if False:\n                env.pop(var, None)", FAMILY),
    # re-pinned 2026-10-19 (#822, third round): the refusal is `KeyRefused`
    ("a refused gate key is replaced by the generated one", "openfactory/gate_seal.py",
     '    if found.refused:\n        raise KeyRefused(f"the gate key',
     '    if False:\n        raise KeyRefused(f"the gate key', FAMILY),
    ("a refused preview key is replaced by the process's own", "openfactory/preview/__init__.py",
     "    if found.refused:\n        # NOT THE PROCESS'S OWN IN ITS PLACE",
     "    if False:\n        # NOT THE PROCESS'S OWN IN ITS PLACE", FAMILY),
    ("a refused engine key is answered by the client certificate",
     "openfactory/runtime/temporal/connection.py",
     "    if api_key.refused:\n        raise RuntimeError(",
     "    if False:\n        raise RuntimeError(", FAMILY),
    # re-pinned 2026-10-19 (#822, second round): every name the harness reads is asked
    ("the doctor's harness line asks for a variable that is set", "openfactory/doctor.py",
     "        if refused:\n            # A REFUSAL, NOT AN ABSENCE",
     "        if False:\n            # A REFUSAL, NOT AN ABSENCE", FAMILY),
    ("the doctor's forge line says 'not configured' over a refusal", "openfactory/doctor.py",
     '        if refused := axis_refusal(project, "forge"):',
     '        if refused := "":', FAMILY),
    ("the doctor's board line asks for the tracker credential that is set", "openfactory/doctor.py",
     '        if refused := axis_refusal(project, "tracker"):',
     '        if refused := "":'),
    ("MAJOR: the doctor's store line stays green over a refused deployment credential",
     "openfactory/doctor.py",
     '        if refused:\n            wrong.append(refused_said("the deployment credential", refused))',
     '        if False:\n            wrong.append(refused_said("the deployment credential", refused))',
     FAMILY),
    # re-pinned 2026-10-19 (#822, second round): a listing store is walked by its listing alone
    ("the doctor walks only the names the code reads, so a planted file goes unsaid",
     "openfactory/doctor.py",
     "        listing = store.listed(first)\n",
     "        listing = None\n"),
    ("readiness says 'not set' over a refusal", "openfactory/onboarding/readiness.py",
     '    if refused:\n        return _fail("env_names",',
     '    if False:\n        return _fail("env_names",', FAMILY),
    ("onboarding runs its agent pass over a refused harness credential",
     "openfactory/onboarding/onboard.py",
     '        if refused:\n            return None, (f"deterministic (the harness credential "',
     '        if False:\n            return None, (f"deterministic (the harness credential "', FAMILY),
    ("onboarding reads the harness credential from the environment again",
     "openfactory/onboarding/onboard.py",
     "        missing = route.missing(held(names))",
     "        missing = route.missing(dict(os.environ))", SWEEP),
    ("the board setup says 'not configured' over a refused GH_TOKEN",
     "openfactory/adapters/tracker/github_board_setup.py",
     "    if found is not None and found.refused:",
     "    if False:", FAMILY),
    ("the panel calls a refused subscription an API key", "openfactory/api/app.py",
     '    if not subscription.refused and lookup("ANTHROPIC_API_KEY").value:',
     '    if lookup("ANTHROPIC_API_KEY").value:', FAMILY),

    # ── the file store: a read-only mount, its repairs, a byte-order mark, a stranger's file ────
    ("MAJOR: a compose secret on Ubuntu's umask is refused on its read-only mount", FILE,
     "        if writers and not _mount_refuses_writes(fd=fd):",
     "        if writers:"),
    # re-pinned 2026-10-19 (#822, second round): a sticky bit no longer excuses a writable directory
    # re-pinned 2026-10-19 (#822, third round): one rule for every directory a secret is read through
    ("a read-only directory's write bits refuse every secret in it", FILE,
     "        if not _mount_refuses_writes(path=here):",
     "        if True:"),
    ("a refusal names its cause and not its repair", FILE,
     '                                    f"else can rewrite is not this deployment\'s — "\n'
     "                                    + _UNWRITABLE.format(path=path))",
     '                                    f"else can rewrite is not this deployment\'s")'),
    ("a refusal of a directory names no repair", FILE,
     "        if not self.directory:\n"
     '            raise CredentialRefused(f"{DIR_VAR} names no directory to read secret files from — "\n'
     '                                    f"set it to where the secrets are mounted (`/run/secrets` for "\n'
     '                                    f"compose\'s `secrets:`), or unset the store that reads it")',
     "        if not self.directory:\n"
     '            raise CredentialRefused(f"{DIR_VAR} names no directory to read secret files from")',
     FAMILY),
    ("a byte-order mark an editor saved is kept in the secret", FILE,
     '            text = data.decode("utf-8-sig")',
     '            text = data.decode("utf-8")'),
    ("a stranger's file in a shared directory is trusted, the panel token included", FILE,
     "        if shared and found.st_uid not in (0, owner):",
     "        if False:", FAMILY),

    # ── the pull ────────────────────────────────────────────────────────────────────────────────
    ("the pull's client output is handed back unredacted", PULL,
     '        return done.returncode == 0, said.replace(secret, "***").replace(auth, "***")[-300:]',
     "        return done.returncode == 0, said[-300:]"),
    ("MAJOR: a job never pulls with its credential", CONTAINER,
     "        self._pull_if_absent()\n        # WHERE the clone lives",
     "        # WHERE the clone lives"),
    ("MAJOR: the pull talks to the default daemon while the box talks to the person's", PULL,
     "        daemon = _carry_the_daemon(config, user_config_dir())",
     "        daemon = {}"),
    ("the pull names the person's context and cannot resolve it", PULL,
     "    if os.path.isdir(contexts):\n        os.symlink(",
     "    if False:\n        os.symlink("),

    # ── the sweep reads tables ──────────────────────────────────────────────────────────────────
    ("the sweep stops reading a loop over a table of names", SWEEP,
     "            for walked in module.looped(node, key):\n",
     "            for walked in ():\n", SWEEP),
    ("the sweep stops seeing the environment handed to a reader of names it does not spell", SWEEP,
     "                table_readers.add(fn.name)\n                break",
     "                break", SWEEP),

    # ── the review of 493875d3: the store's rules for a shared directory and for a link ─────────
    # re-pinned 2026-10-19 (#822, third round): one rule for every directory a secret is read through
    ("a shared directory on a writable mount is read again because it is sticky", FILE,
     "        if not _mount_refuses_writes(path=here):",
     "        if not (found.st_mode & stat.S_ISVTX) and not _mount_refuses_writes(path=here):",
     FAMILY),
    # re-pinned 2026-10-20 (#822, fourth round): every link on the way is asked who made it
    ("a link another user made under a credential's name is followed", FILE,
     "            if found.st_uid not in (0, owner):",
     "            if False:", FAMILY),

    # ── a refusal is final at every construction point ──────────────────────────────────────────
    ("the worker's tracker takes the App minter after a refused reference", ACTIVITIES,
     'token_provider=None if tok else bot_token_provider_for(project, "tracker"))',
     "token_provider=None if tok else _bot_token_provider())", FAMILY),
    ("the worker's forge takes the App minter after a refused reference", ACTIVITIES,
     'token_provider=None if tok else bot_token_provider_for(project, "forge"))',
     "token_provider=None if tok else _bot_token_provider())", FAMILY),
    ("the board poll mints a token after a refused reference", ACTIVITIES,
     '        prov = bot_token_provider_for(project, "tracker")',
     "        prov = _bot_token_provider()", FAMILY),
    ("the checks a card shows are read with the minter after a refused reference",
     "openfactory/runtime/temporal/view.py",
     '                                                else bot_token_provider_for(proj, "forge")))',
     "                                                else _bot_token_provider()))", FAMILY),
    ("the product board takes the minter after a refused reference", "openfactory/product/board.py",
     '                                             else bot_token_provider_for(project, "tracker")))',
     "                                             else _bot_token_provider()))", FAMILY),
    ("the product module's tracker takes the minter after a refused reference",
     "openfactory/product/module.py",
     '                                                  bot_token_provider_for(self.project, "tracker")))',
     "                                                  _bot_token_provider()))", FAMILY),
    ("the factory's board takes the deployment's pair and the minter",
     "openfactory/ops/impediment.py",
     "    tok = tracker_token_for(on_the_board)\n",
     "    tok = __import__(\"openfactory.credentials\", fromlist=[\"x\"]).tracker_token()\n",
     FAMILY),
    # re-pinned 2026-10-19 (#822, third round): the refusal is asked once and handed to the row's sentence
    ("Jira's row answers a refused reference with JIRA_API_TOKEN",
     "openfactory/adapters/tracker/registry.py",
     '    token = kw.get("token") or (None if refused\n'
     '                                else vendor_default(getattr(project, "tracker", None)))',
     '    token = kw.get("token") or vendor_default(getattr(project, "tracker", None))', FAMILY),
    ("the remote box takes the deployment's pair after a refused reference",
     "openfactory/runtime/boxed_job.py",
     '                 or (None if axis_refusal(carried, "forge")\n'
     "                     else forge_token())",
     "                 or forge_token()", FAMILY),
    ("the doctor's deployment forge credential mints over a refused pair", "openfactory/doctor.py",
     '    return forge_token() or (None if pair_refusal("forge") else github_app_token_from_env())',
     "    return forge_token() or github_app_token_from_env()", FAMILY),
    ("board creation takes the deployment's pair before the project's own", "openfactory/cli.py",
     "                token=tracker_token_for(project) or deployment_tracker_token(project))",
     "                token=tracker_token() or deployment_tracker_token(project))", FAMILY),
    ("the guarded minter mints whatever the refusal", "openfactory/factory.py",
     "    if axis_refusal(project, axis):\n        return None\n    return _bot_token_provider()",
     "    return _bot_token_provider()", FAMILY),

    # ── every reader asks the store ─────────────────────────────────────────────────────────────
    ("readiness reads the door's tokens from the environment alone",
     "openfactory/onboarding/readiness.py",
     '        return any(str(env.get(n, "") or "").strip() or stored(n) for n in names)',
     '        return any(str(env.get(n, "") or "").strip() for n in names)'),
    ("readiness says nothing of a refused door token", "openfactory/onboarding/readiness.py",
     '    if refused:\n        return _fail(\n            "product_role",',
     '    if False:\n        return _fail(\n            "product_role",'),
    ("certify fails a panel whose tokens are held in files", "openfactory/certify/controls.py",
     "    held = _panel_in_the_store(r)\n",
     "    held = None\n", FAMILY),
    ("certify fails a store it cannot read where it ran", "openfactory/certify/controls.py",
     "    if store.deployment_store() != declared or store.unusable(declared):",
     "    if False:"),
    ("certify reads a refused panel token as a panel open to anybody",
     "openfactory/certify/controls.py",
     "        if found.refused:\n            return UNKNOWN, (f\"the credential store refuses {name}",
     "        if False:\n            return UNKNOWN, (f\"the credential store refuses {name}", FAMILY),
    ("certify's redactor misses what the store holds", "openfactory/certify/pack.py",
     "            | _held_values(named))",
     "            | set())"),
    ("the sweep reads through no mapping but the environment's", SWEEP,
     "    return sorted({(path, line, name) for path, line, name, who in\n"
     "                   _reads_through_mappings(root, exempt) if who not in declared})",
     "    return []", SWEEP),
    ("the sweep stops following a reader's arguments", SWEEP,
     "                    if isinstance(table, ast.Name) and table.id == vararg:\n"
     "                        spots.add(\"*\")",
     "                    if False:\n"
     "                        spots.add(\"*\")", SWEEP),
    ("certify reads the panel's tokens through a mapping no declaration accounts for", SWEEP,
     '    ("openfactory/certify/controls.py", "_panel"):\n',
     '    ("openfactory/certify/controls.py", "_panel_retired"):\n', SWEEP),

    # ── the harness, the preview, the box, the doctor ───────────────────────────────────────────
    ("a stale refused token file beside an answering pool goes unsaid", ADAPTER,
     "    return refusals(CREDENTIALS)\n",
     "    return refusals(CREDENTIALS[:1])\n"),
    # re-pinned 2026-10-19 (#822, third round): the question is the harness registry's, for the doctor and onboarding alike
    ("the doctor's agent line asks only the harness's walk",
     "openfactory/adapters/agent/registry.py",
     "    return {**walk.refused, **refusals(credential_names(kind))}",
     "    return dict(walk.refused)"),
    ("a refused preview key answers the card's preview with a raw 500", "openfactory/api/app.py",
     "        key = preview.mint(found.project, unit, expires=expires)\n"
     "    except RuntimeError as exc:",
     "        key = preview.mint(found.project, unit, expires=expires)\n"
     "    except LookupError as exc:", "tests/test_a_card_can_be_previewed.py"),
    ("the box is created without the client environment a file-held name needs", CONTAINER,
     "        rc, out = _host(run_cmd) if client_env is None else _host(run_cmd, env=client_env)",
     "        rc, out = _host(run_cmd)"),

    # ── the review of ef084ebd: the gate key, `gh` on the machine's login, the store's rules ────
    ("a refused gate key is a `RuntimeError` again, which every gate reads as 'not waiting'",
     "openfactory/gate_seal.py",
     "class KeyRefused(Exception):",
     "class KeyRefused(RuntimeError):", FAMILY),
    ("the merge gate says 'not waiting on a merge' over a refused gate key",
     "openfactory/actions/catalog.py",
     "    except gate_seal.KeyRefused as exc:\n        # THE ANSWER COULD NOT BE SEALED",
     "    except LookupError as exc:\n        # THE ANSWER COULD NOT BE SEALED", GATE),
    ("the production approval is not said over a refused gate key", "openfactory/actions/catalog.py",
     "        except gate_seal.KeyRefused as exc:  # the answer could not be sealed: said as itself",
     "        except LookupError as exc:  # the answer could not be sealed: said as itself", GATE),
    ("another pass at the last gate reads a refused key as 'not waiting'",
     "openfactory/product/adjust.py",
     '            log.error("OPENFACTORY_NOT_YET_NOT_SEALED project=%s card=#%s by=%s (%s)", name,\n'
     "                      card, by, exc)\n            return KEY_REFUSED",
     '            log.error("OPENFACTORY_NOT_YET_NOT_SEALED project=%s card=#%s by=%s (%s)", name,\n'
     "                      card, by, exc)\n            return NOT_WAITING", GATE),
    ("another pass at the merge gate reads a refused key as 'not waiting'",
     "openfactory/product/adjust.py",
     "                      name, card, said, by, exc)\n            return KEY_REFUSED",
     "                      name, card, said, by, exc)\n            return NOT_WAITING", GATE),
    ("a refused preview key is a raw 500 on the card again", "openfactory/api/app.py",
     '        body["why"] = str(exc)\n        return body',
     "        raise", GATE),
    ("a GitHub adapter runs `gh` on the machine's own login after a refusal",
     "openfactory/adapters/github_cli.py",
     "    if not found and refused:",
     "    if False:", FAMILY),
    ("the GitHub forge is never told its credential was refused", "openfactory/adapters/forge/registry.py",
     '                       refused="" if kw.get("token") else github_refusal(project, "forge"))',
     '                       refused="")', FAMILY),
    ("the GitHub tracker is never told its credential was refused",
     "openfactory/adapters/tracker/registry.py",
     '        refused="" if kw.get("token") else github_refusal(project, "tracker"),',
     '        refused="",', FAMILY),
    ("the GitHub board is never told its credential was refused", "openfactory/adapters/board/factory.py",
     '                              refused="" if token else github_refusal(project, "tracker"),',
     '                              refused="",', FAMILY),
    ("a refused App key is not a refusal to a GitHub adapter", CREDENTIALS,
     '        found = credential_store.lookup(name, quiet=True)\n        if found.refused:\n'
     '            return f"`{found.reference}` is refused: {found.refused}"',
     '        found = credential_store.lookup(name, quiet=True)\n        if False:\n'
     '            return f"`{found.reference}` is refused: {found.refused}"', FAMILY),
    ("the forge's `gh` call raises instead of failing as a call", "openfactory/adapters/forge/github.py",
     "        except LoginRefused as exc:",
     "        except LookupError as exc:", FAMILY),
    ("Jira's anonymous answer asks for JIRA_API_TOKEN over a refused reference",
     "openfactory/adapters/tracker/jira.py",
     "    if refused:\n        # THE CREDENTIAL STORE REFUSED IT (#742)",
     "    if False:\n        # THE CREDENTIAL STORE REFUSED IT (#742)"),
    ("Jira's row never hands its sentence the refusal", "openfactory/adapters/tracker/registry.py",
     "        refused=refused,\n",
     ""),
    ("a shared directory is shared only when it is sticky and anyone may write to it", FILE,
     "        return root, self._held_through(root, found, shown=self.directory)",
     "        return root, self._held_through(root, found, shown=self.directory) and bool(\n"
     "            found.st_mode & stat.S_ISVTX and found.st_mode & stat.S_IWOTH)", FAMILY),
    ("a shared directory of another user's is read", FILE,
     '        if found.st_uid not in (0, getattr(os, "geteuid", lambda: 0)()):',
     "        if False:", FAMILY),
    # re-pinned 2026-10-20 (#822, fourth round): the climb is `_held_up_to`, shared with the links
    ("the directories a name's link leads through are not asked", FILE,
     "        self._held_up_to(os.path.dirname(path), root, name, asked)\n",
     "", FAMILY),
    ("a file with another name elsewhere is read on a writable mount", FILE,
     "        if found.st_nlink > 1 and not _mount_refuses_writes(fd=fd):",
     "        if False:", FAMILY),
    ("a link put under the name after it was resolved is followed", FILE,
     '        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)',
     '        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)'),
    ("the checks are asked of the path, not of the file that is read", FILE,
     "            self._checked(name, os.fstat(fd), shared, fd)",
     "            self._checked(name, os.stat(path), shared, fd)"),
    ("an answer shows its value", REGISTRY,
     "    value: str | None = field(default=None, repr=False)",
     "    value: str | None = field(default=None)"),
    ("onboarding asks fewer of the harness's names than the harness refuses on",
     "openfactory/onboarding/onboard.py",
     "        refused = (harness_refusals(kind) if harness_credential(kind, {}) is not None",
     "        refused = ({} if harness_credential(kind, {}) is not None"),

    # ── the delta review of 1b5ec71d: every `gh`, and every link on a name's way ────────────────
    ("the CI observer's row hands it no refusal", "openfactory/adapters/environment/registry.py",
     '        refused="" if kw.get("token") else github_refusal(project, "forge"),',
     '        refused="",', FAMILY),
    ("the CI observer starts `gh` without asking its credential",
     "openfactory/adapters/environment/github_actions.py",
     "        token = self.token\n",
     "        token = self._static_token\n", FAMILY),
    ("board creation at init asks no refusal before `GH_TOKEN`",
     "openfactory/adapters/tracker/github_board_setup.py",
     "            if refusal:\n                raise BoardSetupError(",
     "            if False:\n                raise BoardSetupError(", FAMILY),
    ("the board's link types its owner on the machine's own login",
     "openfactory/adapters/tracker/github_project.py",
     "            kind = _owner_kind(self.owner, lambda: self.token)",
     "            kind = _owner_kind(self.owner)", FAMILY),
    ("a directory a link on the way is in is not asked", FILE,
     "            self._held_up_to(here, root, name, asked)\n",
     "", FAMILY),
    ("only the link under the name is asked who made it", FILE,
     "            if found.st_uid not in (0, owner):",
     "            if links == 1 and found.st_uid not in (0, owner):", FAMILY),
]
