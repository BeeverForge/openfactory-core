"""A YAML file a repository holds is read without expanding aliases, and within bounds (#1005).

Every YAML document the core reads goes through `openfactory/util/yaml_io.py`: `Loader` refuses
an anchor and an alias by name for the core's own files, `CountingLoader` reads them for a format
whose specification has them with each alias counted at the size and depth of what it repeats, and
both refuse a document past `MAX_BYTES`, `MAX_DEPTH` or `MAX_NODES` before anything is built. The
guard reads every module's syntax tree for a parse outside the door, lists every reader from the
calls into it, and feeds each an aliased, a deeply nested and an oversized document.

Each row below is one way that could come undone: a call site back on `yaml.safe_load`, the door
reading an anchor, a bound or a count dropped, a reader swallowing the refusal or reading with the
other loader, the log that keeps an absent value from being silent, and the writer that keeps what
the core writes readable through the door. The guard must go red on each.
"""

TEST = "tests/test_yaml_is_read_without_aliases_and_within_bounds.py"

_DOOR = "openfactory/util/yaml_io.py"

MUTATIONS = [
    ("A CALL SITE LEFT ON `yaml.safe_load`: a capability's front matter is read past the door, its "
     "aliases kept and its depth unbounded",
     "openfactory/product/capabilities.py",
     "        head = yaml_io.load(match.group(1)) or {}\n",
     "        head = yaml.safe_load(match.group(1)) or {}\n"),

    ("THE DOOR ACCEPTS ANCHORS AND ALIASES: the core's own files read them as the counting loader "
     "does",
     _DOOR, "    READS_ALIASES = False\n", "    READS_ALIASES = True\n"),

    ("an anchor nothing aliases is read: only `*name` is refused, not `&name`",
     _DOOR, "        if anchor is not None and not self.READS_ALIASES:\n", "        if False:\n"),

    ("A READER SWALLOWS THE REFUSAL: a document's front matter that is refused says nothing",
     "openfactory/adapters/extract/text.py",
     '        return {}, text, f"its front matter is not valid YAML '
     '({str(exc).splitlines()[0][:120]})"\n',
     '        return {}, text, ""\n'),

    ("a reader swallows the refusal: `product.yaml` refused reads as no error at all, through "
     "both of its readers",
     "openfactory/product/loader.py",
     '        return None, f"{DOCS_MANIFEST} is not valid YAML: {str(exc)[:200]}"\n',
     '        return None, ""\n'),

    ("the brief's document summary lets the refusal out, so one aliased front matter costs the "
     "whole brief",
     "openfactory/orchestrator/context.py",
     "            try:\n"
     "                fm = yaml_io.load(parts[1]) or {}\n"
     "            except yaml.YAMLError as exc:\n",
     "            if True:\n"
     "                fm = yaml_io.load(parts[1]) or {}\n"
     "            if False:\n"),

    ("THE DEPTH IS NOT BOUNDED: a document 150 levels deep is read, and one of 1,000 raises "
     "RecursionError out of the readers of `product.yaml` again",
     _DOOR, "        if depth > MAX_DEPTH:\n", "        if False:\n"),

    ("an alias is not counted at the depth of what it repeats, so a chain of anchors nests past "
     "the bound",
     _DOOR, "        self._within(reach, event.start_mark, alias=event.anchor)\n", "        pass\n"),

    ("THE VALUES ARE NOT BOUNDED: nine aliases a level are read to half a million values",
     _DOOR, "        if self._values > MAX_NODES:\n", "        if False:\n"),

    ("an alias counts as one value, not as the size of what it repeats",
     _DOOR, "        self._count(values, event.start_mark, alias=event.anchor)\n",
     "        self._count(1, event.start_mark, alias=event.anchor)\n"),

    ("an alias inside the value it repeats is let through, and reading it raises TypeError, no "
     "YAMLError",
     _DOOR, "        if held is None:\n", "        if False:\n"),

    ("THE BYTES ARE NOT BOUNDED: a document over the ceiling is read whole",
     _DOOR, "        if size > MAX_BYTES:\n", "        if False:\n"),

    ("the refusal is not logged, so a reader whose answer is an absent value is silent about why",
     _DOOR,
     '    log.warning("OPENFACTORY_YAML_REFUSED a YAML document was refused before it was read: '
     '%s",\n                problem)\n',
     "    pass\n"),

    ("A COMPOSE READER REFUSES THE ANCHORS ITS FORMAT HAS: a developer's compose file with a "
     "fragment is refused by the preview",
     "openfactory/preview/read.py",
     "class _ComposeLoader(yaml_io.CountingLoader):\n", "class _ComposeLoader(yaml_io.Loader):\n"),

    ("the system layer refuses the anchors of the formats it reads (compose, Kubernetes, OpenAPI)",
     "openfactory/knowledge/system/text.py",
     "class _Loader(yaml_io.CountingLoader):\n", "class _Loader(yaml_io.Loader):\n"),

    ("A READER OF THE CORE'S OWN FILES COUNTS ALIASES INSTEAD OF REFUSING THEM: the published "
     "system map with an anchor is read on every product turn",
     "openfactory/product/sight.py",
     "        data = yaml_io.load(got.text)\n",
     "        data = yaml_io.load(got.text, loader=yaml_io.CountingLoader)\n"),

    ("THE WRITER WRITES ALIASES: a value met twice is written as `&id001` and `*id001`, and the "
     "file the core wrote no longer reads back through the door",
     _DOOR,
     "    def ignore_aliases(self, data: Any) -> bool:\n        return True\n",
     "    def ignore_aliases(self, data: Any) -> bool:\n"
     "        return super().ignore_aliases(data)\n"),
]
