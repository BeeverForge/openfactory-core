"""#1002: a product's system layer through the front-end API — every entry cited, names only.

Each cut breaks one promise the read makes and must turn its target red. The rows are grouped by
label, and each group runs alone with `--only`:

  "names only:"    a value crosses — from a compose file, or from beside the map's fields in a
                   published file — or a reader or a field joins that the family rule does not see
  "cited:"         an entry loses where it came from
  "never empty:"   a map that is not known is answered as an empty one, or in part
  "refused:"       a published part with anchors or aliases is read, or answered without the
                   loader's sentence
  "described:"     the read model or the layout loses a part of the map
  "gate:"          a project with no product role is read, or told apart, or the read writes
  "page:"          the product page drops, mis-draws or never reads the map

No row writes outside a test's temporary directory: every fixture's remotes, caches and journals
live under `tmp_path`, and the impediment row runs only the test that stands the reporter in.
"""

TEST = "tests/test_the_system_layer_is_read_through_the_api.py"
APP = "openfactory/api/app.py"
RENDER = "openfactory/knowledge/system/render.py"
DERIVE = "openfactory/knowledge/system/derive.py"
DEPLOY = "openfactory/knowledge/system/deployments.py"
MODELS = "openfactory/api/read_models.py"
PAGE = "openfactory/api/panel.html"

_FAMILY = f"{TEST}::test_no_value_of_a_variable_crosses_the_api_only_names"
_KINDS = f"{TEST}::test_the_fixture_plants_every_kind_of_declaration_the_layer_reads"
_BESIDE = f"{TEST}::test_what_a_hand_adds_beside_the_map_s_fields_is_never_answered"
_CITED = f"{TEST}::test_every_entry_says_where_it_came_from_and_the_file_is_there"
_WHOLE = f"{TEST}::test_both_addresses_answer_the_published_map_whole"
_ROLE = (f"{TEST}::test_a_project_with_no_product_role_is_the_unknown_project_s_404_and_checks_"
         f"out_nothing")
_WRITES = f"{TEST}::test_a_read_pushes_nothing_and_files_no_impediment"
_DRAWN = (f"{TEST}::test_the_product_page_draws_the_map_the_api_answers_what_could_not_be_"
          f"derived_first")
_REFUSED = (f"{TEST}::test_a_published_part_with_anchors_or_aliases_or_too_deep_is_unreadable_"
            f"fast_on_both_addresses")

MUTATIONS = [
    # ── names only ──────────────────────────────────────────────────────────────────────────────
    ("names only: a compose service's environment keeps each value beside its name",
     DEPLOY,
     "        target.env.append(name)\n",
     '        target.env.append(f"{name}={value}" if value is not None else name)\n',
     _FAMILY),

    ("names only: the published files are answered as they are, not through the map's models — "
     "what a hand put beside the map's fields crosses",
     RENDER,
     "        system = SystemMap(**{key: head[key] for key in HEAD if head.get(key) is not None},",
     "        system = SystemMap.model_construct(**{key: head[key] for key in HEAD "
     "if head.get(key) is not None},",
     _BESIDE),

    ("names only: a reader joins the layer and the fixture plants nothing it reads",
     DERIVE,
     "    adrs: list[tuple[Cite, adr_reader.AdrDecl]] = field(default_factory=list)\n",
     "    adrs: list[tuple[Cite, adr_reader.AdrDecl]] = field(default_factory=list)\n"
     "    helm: list = field(default_factory=list)\n",
     _KINDS),

    ("names only: the read grows a text field no answer fills, so nothing proves it holds no value",
     MODELS,
     "    not_derived: list[SystemNotDerived] | None = None\n",
     "    not_derived: list[SystemNotDerived] | None = None\n    note: str | None = None\n",
     _FAMILY),

    # ── cited ───────────────────────────────────────────────────────────────────────────────────
    ("cited: a component is answered without the declarations that name it",
     APP,
     '        out.update(found.system.model_dump(by_alias=True, mode="json"),',
     '        out.update(found.system.model_dump(by_alias=True, mode="json", exclude={'
     '"components": {"__all__": {"declared_by"}}}),',
     _CITED),

    # ── never empty ─────────────────────────────────────────────────────────────────────────────
    ("never empty: a map nobody published is answered as a published empty one",
     RENDER,
     '        return Published(NOT_PUBLISHED, f"no system map is published at `{base}` yet: the "',
     '        return Published(PUBLISHED, system=SystemMap()) or Published('
     'NOT_PUBLISHED, f"no system map is published at `{base}` yet: the "'),

    ("never empty: a file of the map that is not YAML is read as parts that declare nothing",
     RENDER,
     '            return Published(UNREADABLE, f"the system map at `{base}` cannot be read: '
     '`{name}` is "\n'
     '                                         f"not YAML ({type(exc).__name__})")\n',
     "            data = {part: [] for part in LAYOUT[name]}\n"),

    ("never empty: the route reads the map wherever it stands when the context repository is not "
     "there",
     APP,
     "    if not ctx.docs_path:\n",
     "    if False:\n"),

    ("never empty: a source the refresh could not check out is left out of what could not be "
     "derived",
     DERIVE,
     "        notes.append(NotDerived(kind=SOURCE_UNREADABLE, repo=repo,\n"
     '                                detail=f"could not be read ({why}); nothing it declares '
     'is in "\n'
     '                                       f"the map"))\n',
     ""),

    # ── refused ─────────────────────────────────────────────────────────────────────────────────
    ("refused: the published map is read back on `text.load_yaml`, the counting loader the layer "
     "keeps for the formats it derives from — a part with anchors or aliases is read, and a long "
     "value aliased many times answers megabytes",
     RENDER,
     "            data = yaml_io.load(got.text)\n",
     "            from openfactory.knowledge.system.text import load_yaml\n"
     "            data = load_yaml(got.text)\n",
     _REFUSED),

    ("refused: a refusal is answered as a file that is not YAML, by its kind, without the "
     "loader's sentence",
     RENDER,
     "        except yaml_io.YamlRefused as exc:\n",
     "        except ZeroDivisionError as exc:\n",
     _REFUSED),

    # ── described ───────────────────────────────────────────────────────────────────────────────
    ("described: the read model forgets the tool a database's migrations were written with",
     MODELS,
     "    tool: str | None = None\n    tables: list[SystemTable] | None = None\n",
     "    tables: list[SystemTable] | None = None\n"),

    ("described: the layout forgets the events, so the map is written and read back without them",
     RENDER,
     '    API_FILE: ("http", "grpc", "events"),',
     '    API_FILE: ("http", "grpc"),'),

    # ── gate ────────────────────────────────────────────────────────────────────────────────────
    ("gate: a project with no product role is read like a product",
     APP,
     "    if not _has_product_role(proj):\n        raise _no_such_project(project)\n"
     "    where = system_subpath().as_posix()\n",
     "    where = system_subpath().as_posix()\n",
     _ROLE),

    ("gate: a project with no product role is told apart from an unknown one",
     APP,
     "        raise _no_such_project(project)\n    where = system_subpath().as_posix()\n",
     '        raise HTTPException(404, f"{project!r} has no product role")\n'
     "    where = system_subpath().as_posix()\n",
     _ROLE),

    ("gate: the read goes through the product module's context, which files an impediment",
     APP,
     "    ctx = load_product_context(\n"
     '        proj, token=forge_token_for(proj) or deployment_forge_token(proj) or "")\n',
     '    ctx = __import__("openfactory.actions.catalog", fromlist=["_product_module"])'
     "._product_module(project)[0].context()\n",
     _WRITES),

    # ── page ────────────────────────────────────────────────────────────────────────────────────
    ("page: the System pane leaves out what could not be derived",
     PAGE,
     '    sec("What could not be derived",all(s.not_derived),',
     '    sec("What could not be derived",[],',
     _DRAWN),

    ("page: a citation is written into the page as HTML",
     PAGE,
     '${esc(c.repo)} · ${esc(c.path||"")}',
     '${c.repo} · ${c.path||""}'),

    ("page: a map that is not there is drawn as an empty map",
     PAGE,
     '  if(!s||s.state!=="published"){',
     "  if(!s){"),

    ("page: opening the System tab reads nothing",
     PAGE,
     '  if(k==="system")pvSystemLoad();\n',
     ""),
]
