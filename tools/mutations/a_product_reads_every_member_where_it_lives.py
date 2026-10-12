"""On the local row, a product reads each of its projects' code where that project lives (journey 0,
#640, #664), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/a_product_reads_every_member_where_it_lives.py

The claims, each a row:
  1. every project reads every project of its product at that project's own `repo_path`;
  2. a registered project of another product, or of none, or on a hosted row, is never read as a
     member;
  3. a registry that cannot be read answers as before, and says so in the log.
"""

TEST = "tests/test_a_product_reads_every_member_where_it_lives.py"
LOCAL = "openfactory/adapters/forge/local.py"

MUTATIONS = [
    # 1. every member
    ("TODAY'S RUN: a sibling member is looked for among the context repositories", LOCAL,
     "        member = self._member_path(name)\n", '        member = ""\n'),

    # 2. the isolation between products
    ("a project of another product is read as a member", LOCAL,
     '        return other.repo_path if product_key(other) == product_key(me) else ""',
     "        return other.repo_path"),
    ("a member on a hosted row is read as a path on this machine", LOCAL,
     '        if (getattr(other.forge, "kind", "") or "") != "local" or not other.repo_path:',
     "        if not other.repo_path:"),

    # 3. a registry that cannot be read
    ("a registry that cannot be read breaks the clone", LOCAL,
     "        except Exception as exc:  # noqa: BLE001 — answered as before, and said",
     "        except ZeroDivisionError as exc:  # noqa: BLE001 — answered as before, and said"),
    ("a registry that cannot be read is answered in silence", LOCAL,
     'log.warning("OPENFACTORY_LOCAL_FORGE_MEMBERS_UNREAD project=%s',
     'log.debug("OPENFACTORY_LOCAL_FORGE_MEMBERS_UNREAD project=%s'),
]
