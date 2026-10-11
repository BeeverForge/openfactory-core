"""A front a breakdown did not file stays where the requirement is shown, beside the retry (#564),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/564b_a_front_not_filed_stays_where_the_requirement_is.py

The claims, each a row:

  1. the fronts a breakdown leaves out are kept, over what the requirement's last breakdown left
     out, for that requirement alone — never a card that landed or the verdict that the
     requirement is already built;
  2. the breakdown on the worker keeps them, and a ledger that cannot take them costs no card;
  3. the requirements read carries them, and a ledger that cannot be read costs that column only;
  4. the page shows them on the row and reloads after a breakdown;
  5. nobody is chased about them.
"""

TEST = "tests/test_a_front_not_filed_stays_where_the_requirement_is.py"
UNFILED = "openfactory/product/unfiled.py"
ACTIVITIES = "openfactory/runtime/temporal/activities.py"
CATALOG = "openfactory/actions/catalog.py"
PAGE = "openfactory/api/panel.html"

MUTATIONS = [
    # 1. what is kept
    ("the next breakdown leaves the last one's fronts standing", UNFILED,
     "    out = close_by_observation(waiting(rows, kind=UNFILED, owner=OWNER),\n"
     '                               {(UNFILED, subject, ""): BROKEN_DOWN_AGAIN})',
     "    out = []"),
    ("one requirement's breakdown clears every requirement's fronts", UNFILED,
     '                               {(UNFILED, subject, ""): BROKEN_DOWN_AGAIN})',
     '                               {(UNFILED, x.subject, ""): BROKEN_DOWN_AGAIN\n'
     '                                for x in waiting(rows, kind=UNFILED, owner=OWNER)})'),
    ("a card that landed is kept as a front left out", UNFILED,
     '            if not getattr(r, "ok", False) and not getattr(r, "nothing_to_build", False)',
     '            if not getattr(r, "nothing_to_build", False)'),
    ("the verdict that the requirement is already built is kept as a front left out", UNFILED,
     '            if not getattr(r, "ok", False) and not getattr(r, "nothing_to_build", False)',
     '            if not getattr(r, "ok", False)'),

    # 2. kept by the breakdown
    ("TODAY'S RUN: the breakdown keeps nothing of what it left out", ACTIVITIES,
     "    await _keep_what_was_not_filed(project, inp, results)\n", ""),
    ("a ledger that cannot take it costs the cards", ACTIVITIES,
     "    except Exception:  # noqa: BLE001 — the cards stand; only the record of what is missing "
     "failed",
     "    except ArithmeticError:  # noqa: BLE001"),

    # 3. carried by the read
    ("the requirements read drops what was left out", CATALOG,
     '             "unfiled": left_out.get(r.number, [])}', '             "unfiled": []}'),
    ("a ledger that cannot be read costs the whole list", CATALOG,
     "    except Exception:  # noqa: BLE001 — the list stands without it, and the log says why",
     "    except ArithmeticError:  # noqa: BLE001"),

    # 4. shown on the row
    ("the row shows nothing left out", PAGE,
     "    const left=(Array.isArray(r.unfiled)?r.unfiled:[]).filter(Boolean);",
     "    const left=[];"),
    ("the page keeps the rows it had before the breakdown", PAGE,
     "  loadRequirements();   // what it left out is shown on the row", "  // what it left out"),

    # 5. nobody is chased
    ("the product role's readers see the fronts left out", UNFILED,
     'OWNER = "breakdown"', 'OWNER = "product"'),
]
