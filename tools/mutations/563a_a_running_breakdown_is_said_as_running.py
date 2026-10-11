"""A breakdown asked for while one of the same requirement runs is said as running, and reads what
the running one filed (#563, ADR-0051 D18 slice 18a), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/563a_a_running_breakdown_is_said_as_running.py

The engine refuses a second start of a requirement's breakdown while one runs, and both catalog
doors turned that refusal into "nothing was filed" while the first was filing the cards. The
claims, each a row:

  1. the refusal is caught where the breakdown is dispatched, and the door reads the SAME
     execution's result, filing nothing;
  2. the acceptance and the explicit door each say it as running, with what it filed, and a
     running breakdown that filed nothing is said with its reason;
  3. the id is spelled in one place.
"""

TEST = "tests/test_a_running_breakdown_is_said_as_running.py"
CATALOG = "openfactory/actions/catalog.py"

MUTATIONS = [
    # 1. the dispatch
    ("TODAY'S DEFECT: the engine's refusal falls into each door's catch-all", CATALOG,
     "    except WorkflowAlreadyStartedError:\n        # THE REFUSAL THIS ID WAS SHARED FOR",
     "    except ZeroDivisionError:\n        # THE REFUSAL THIS ID WAS SHARED FOR"),
    ("the second door files nothing and never reads what the running one filed", CATALOG,
     "            filed = await client.get_workflow_handle(breaking).result() or []\n",
     "            filed = []\n"),

    # 2. the doors' sentences
    ("the acceptance says a running breakdown as one that filed nothing", CATALOG,
     "    except _AlreadyBreakingDown as running:\n"
     "        data = {**accepted.data,",
     "    except ZeroDivisionError as running:\n"
     "        data = {**accepted.data,"),
    ("the explicit door says a running breakdown as one it could not reach", CATALOG,
     "    except _AlreadyBreakingDown as running:\n"
     '        data = {"project": proj.name,',
     "    except ZeroDivisionError as running:\n"
     '        data = {"project": proj.name,'),
    ("a running breakdown that filed nothing is said as done", CATALOG,
     "        if running.filed is not None and not any(r.get(\"ok\") for r in running.filed):\n",
     "        if False:\n"),

    # 3. one spelling
    ("the dispatch spells the id by hand again", CATALOG,
     "            id=breaking,\n",
     '            id=f"openfactory-product-breakdown-{project}-{number}",\n'),
]
