"""ADR-0049 slice 7 (follow-up), proven by breaking it — the context repository exists.

THREE CLAIMS:

  1. **It is made AND seeded** at registration on this runtime: an empty bare repository fails a
     checkout of its base branch exactly as a missing one does.
  2. **Both ends declare the pair** — the registry names the documentation repository and the
     source repository's manifest names it back.
  3. **Only here, and never at the cost of the registration.** A hosted row is left alone, because
     making a repository in somebody's organisation is an operator's decision; and a failure to
     seed is said out loud without losing the project that was already registered.

The guard under test is `tests/test_the_context_repository_exists_on_this_runtime.py`.
"""

TEST = "tests/test_the_context_repository_exists_on_this_runtime.py"

#: the seed itself, since #992: `product start` seeds a context the same way, with no source in it
SEED = "openfactory/product/onboard.py"
#: RE-PINNED 2026-10-23 (#741): `project init` maps onto the `project_init` row, and the seed is
#: its `context` step (`_the_context_step`), so the rows that cut the command cut the step. The
#: claims are unchanged; two cut a shape that moved — the step runs from the row's own reading of
#: the project rather than from a variable of the command, and a failure is a failed step rather
#: than a line the command printed.
CATALOG = "openfactory/actions/catalog.py"

MUTATIONS = [
    ("nothing is created, so the module the platform switched on has nowhere to read", CATALOG,
     "    if local and (context := _the_context_step(name)) is not None:\n"
     "        steps.append(context)\n",
     "", TEST),

    # THE DEAD END (review of #106): a seed that failed once had no retry anywhere.
    ("a failed seed is never retried, because only the run that REGISTERS tries it", CATALOG,
     "    if local and (context := _the_context_step(name)) is not None:",
     "    if local and steps[0][\"state\"] == STEP_DONE and "
     "(context := _the_context_step(name)) is not None:", TEST),

    # RE-PINNED (#992): the seed moved from `cli._seed_the_context_repository` to
    # `product.onboard.seed_context_repository`, which the CLI's verb now calls.
    ("the early return asks whether THIS run made it, so a repository with no commit is left",
     SEED,
     '    if has_a_commit.returncode == 0:\n        return created, ""',
     '    if not created:\n        return created, ""', TEST),

    ("a repository that was only finished is reported as created", CATALOG,
     '    return _step("context", STEP_DONE, f"context repository {\'created\' if created else '
     '\'seeded\'} "',
     '    return _step("context", STEP_DONE, f"context repository created "', TEST),

    ("the repository is created and left EMPTY — a checkout of `main` fails as before", SEED,
     '        git("push", "-q", "--", "origin", "HEAD:main")', "        pass", TEST),

    ("the seed says nothing about which product it is for", SEED,
     '        seed.write_text(f"product: {name}\\nsources:{listed}\\n"',
     '        seed.write_text(f"sources:{listed}\\n"', TEST),

    ("the source repository stops naming the context back, and the pair is half-declared",
     CATALOG,
     '        scaffold += f"docs_repo: {name}-context\\n"',
     '        scaffold += ""', TEST),

    ("a hosted project has a repository made in somebody's organisation without being asked",
     CATALOG,
     "    if local and (context := _the_context_step(name)) is not None:",
     "    if True and (context := _the_context_step(name)) is not None:", TEST),

    ("a failure to seed takes the registration down with it", CATALOG,
     '    except Exception as exc:  # noqa: BLE001 — the project is registered; the step is said\n'
     '        log.warning("could not seed the context repository for %s (%s)", name, str(exc)[:200])',
     '    except ValueError as exc:\n'
     '        log.warning("could not seed the context repository for %s (%s)", name, str(exc)[:200])',
     TEST),

    ("the failure is silent, so the module is off and the reason is an hour away", CATALOG,
     '        return _step("context", STEP_FAILED, f"the product role\'s context repository could '
     'not "',
     '        return None\n        _ = (f""', TEST),
]
