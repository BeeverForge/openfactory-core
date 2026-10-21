"""#745, proven by breaking it — one key, one tree, and one proof of a key at a time.

Every proof used one branch, `openfactory/box-prove`, so two projects proved at once met at one
working tree (`A tree alive: False`, git 2.43.0, 2026-10-18), and a second proof of the same project
removed the first one's box. FIVE CLAIMS:

  1. **Two keys are proven on two branches**, so on two trees: the branch carries the key's slug
     (rows 1-3). The slug keeps a hash of the key, or `acme web` and `acme/web` share a branch
     again, and it keeps only what a ref can spell, or git refuses the name (git itself is asked).
  2. **One key is proven once at a time on this machine**, by a kernel lock on a path of the key's
     own that every process computes alike (rows 4-6): two keys never block each other, and a
     holder in another process refuses this one.
  3. **The refusal comes before anything is touched** (row 7): neither the checkout sync, nor the
     box's construction, nor `prepare`. The cut moves the lock just past the sync, the earliest
     wrong place; any later place passes the sync too, and the same assertion sees it. Moving it
     past `prepare` is not one contiguous edit of this file (some 230 lines apart), so that cut is
     not a row; the tree-survives test is what would see it.
  4. **The key is free again however the proof ends** (rows 8, 9): ended, raised inside the proof,
     or raised while the checkout was being synced.
  5. **Every door says the refusal in one sentence and records nothing** (rows 10-12): `box prove`,
     `box answer`, and onboarding, whose generic refusal cut a long key's sentence at 160
     characters.

The guards are the three test files below.
"""

TWICE = "tests/test_the_same_project_proved_twice_at_once_is_refused_not_deleted.py"
APART = "tests/test_two_projects_proved_at_once_never_share_a_working_tree.py"
DOORS = "tests/test_a_busy_proof_is_refused_in_one_sentence_at_every_door.py"
TEST = TWICE

PROVE = "openfactory/box_prove.py"
CLI = "openfactory/cli.py"
ONBOARD = "openfactory/onboarding/onboard.py"

_ACQUIRE = "    held = _hold_the_proof_of(subject)\n"
_RESOLVE = ("        repo = repo_path if repo_path is not None else resolve_repo_path(project, "
            "cache_key=key)\n")
_SYNC_COMMENT = (
    "    try:\n"
    "        # RESOLVED, exactly as `build_runner` does — a proof taken against a path the job "
    "would\n"
    "        # not use proves nothing. This was left as the raw `repo_path` when #65 landed, so on "
    "the\n"
    "        # compose worker it was still a URL: the clone failed silently and the proof ran "
    "against\n"
    "        # an empty workspace, reporting the client's own gates as broken.\n"
    "        #\n"
    "        # `cache_key=key`: a `--repo` proof resolves into ITS OWN cache slot. Without it the "
    "foreign\n"
    "        # repository synced into the DEFAULT repo's shared checkout — the tree a live worker "
    "may be\n"
    "        # reading — which is the exact cross-repo contamination `_checkout_key` exists to "
    "prevent\n"
    "        # (adversarial review, 2026-08-13). `key=None` keeps the default slot, byte for "
    "byte.\n"
)

_CLEANUP = (
    "    finally:\n"
    "        try:\n"
    "            if workspace is not None:\n"
    "                box.cleanup(workspace=workspace)\n"
    "        except Exception as exc:  # noqa: BLE001 — a leaked container is a warning, not a "
    "failure\n"
    "            log.warning(\"the proof's box could not be cleaned up (%s)\", str(exc)[:160])\n"
    "        finally:\n"
    "            # after the cleanup: the lock covers the whole life of the tree, removal "
    "included\n"
    "            _let_go(held)\n"
)

MUTATIONS = [
    # ── 1. two keys, two branches ───────────────────────────────────────────────────────────────
    ("every proof is prepared on the one shared branch again, so two projects meet at one tree",
     PROVE,
     'branch=f"{namespace.BRANCH_PREFIX}/box-prove-{_prove_slug(subject)}")',
     'branch=f"{namespace.BRANCH_PREFIX}/box-prove")', APART),

    ("the slug loses its hash, so keys that slug alike (`acme web`, `acme/web`) share a branch",
     PROVE,
     '    return f"{readable}-{digest}" if readable else digest',
     '    return readable or digest', APART),

    ("the key goes into the branch unslugged, so git refuses the name a free-text key spells",
     PROVE,
     '    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", key).strip("-.").lower()',
     '    readable = key', APART),

    # ── 2. one key at a time, and only that key, from any process ──────────────────────────────
    ("every key locks one file, so proving one project refuses every other",
     PROVE,
     '    return _proof_dir() / "locks" / f"{_prove_slug(key)}.lock"',
     '    return _proof_dir() / "locks" / "proof.lock"', TWICE),

    ("the lock path carries the process id, so the CLI beside the worker never meets its lock",
     PROVE,
     '    return _proof_dir() / "locks" / f"{_prove_slug(key)}.lock"',
     '    return _proof_dir() / "locks" / f"{_prove_slug(key)}-{os.getpid()}.lock"', TWICE),

    ("a busy key is proven anyway, unlocked, instead of refused",
     PROVE,
     "        raise ProveBusy(key) from None",
     "        return None", TWICE),

    # ── 3. refused before anything is touched ──────────────────────────────────────────────────
    ("the lock is taken after the checkout is synced, so a refused proof re-syncs a live tree",
     PROVE,
     _ACQUIRE + _SYNC_COMMENT + _RESOLVE,
     "    held = None\n" + _SYNC_COMMENT + _RESOLVE
     + "        held = _hold_the_proof_of(subject)\n",
     TWICE),

    ("`box prove --ref` syncs its checkout before it takes the key, so a refused `--ref` proof "
     "removes and re-adds the tree the running one reads",
     CLI,
     "            held = _hold_the_proof_of(proof_key)\n",
     "            held = None\n", DOORS),

    # ── 4. the key is free again however the proof ends ────────────────────────────────────────
    ("the lock is never let go when the proof ends, so the key stays refused until a restart",
     PROVE,
     "        finally:\n"
     "            # after the cleanup: the lock covers the whole life of the tree, removal "
     "included\n"
     "            _let_go(held)\n",
     "        finally:\n            pass\n", TWICE),

    ("the key is let go before the box is cleaned up, so a second proof is let in while the "
     "first one's tree or container is still being removed",
     PROVE,
     _CLEANUP,
     "    finally:\n"
     "        _let_go(held)\n"
     "        try:\n"
     "            if workspace is not None:\n"
     "                box.cleanup(workspace=workspace)\n"
     "        except Exception as exc:  # noqa: BLE001 — a leaked container is a warning, not a "
     "failure\n"
     "            log.warning(\"the proof's box could not be cleaned up (%s)\", str(exc)[:160])\n",
     TWICE),

    ("a checkout sync that raises keeps the key, so every later proof of it is refused",
     PROVE,
     "    except BaseException:\n        _let_go(held)\n        raise\n",
     "    except BaseException:\n        raise\n", TWICE),

    # ── 5. every door says it in one sentence ──────────────────────────────────────────────────
    ("`box prove` lets the refusal out as a traceback",
     CLI,
     "    except ProveBusy as exc:\n        # BEFORE `save`",
     "    except LookupError as exc:\n        # BEFORE `save`", DOORS),

    ("`box answer` lets the refusal out as a traceback",
     CLI,
     "    except ProveBusy as exc:\n        # nothing was asked",
     "    except LookupError as exc:\n        # nothing was asked", DOORS),

    ("onboarding says the refusal through its generic door, which cuts a long key's remedy off",
     ONBOARD,
     "    except ProveBusy as exc:\n        # THE WHOLE SENTENCE",
     "    except LookupError as exc:\n        # THE WHOLE SENTENCE", DOORS),
]
