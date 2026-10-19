"""A key of `.openfactory/product.yaml` that is not a string is named, never raised (#819).

`parse_docs_manifest` handed a mapping straight to `ProductDocs(**data)`, so `1: x`, `on: push` or
`<<: {1: x}` raised `TypeError: keywords must be strings` into the caller, and a list or a mapping
as a key came back in the loader's own words with no key in them. The keys are now read from the
composed nodes, after `<<` is merged and before anything is built, and every one that is not
`!!str` is one sentence naming the file, the key as written, its line, its shape and the remedy.

The load is assembled by hand, so the last block of rows holds what `yaml.safe_load` did by its
name: the safe class, None for a file with no document in it, and a refusal for a file of several
documents. Each of those cuts survived a version of this plan (on review, 2026-10-19). Each row
below is one way that could come undone, and the guard must go red on each.
"""

TEST = "tests/test_product_yaml_names_a_key_that_is_not_a_string.py"

_LOADER = "openfactory/product/loader.py"

MUTATIONS = [
    ("THE DEFECT: no key is read before construction, so `1: x` raises TypeError again and a "
     "list as a key is the loader's unhashable-key error",
     _LOADER, "                if key.tag != _A_STRING:\n", "                if False:\n"),

    ("THE DEFECT, seen from the module: a key YAML reads as a bool takes `load_product_context` "
     "down instead of turning the module off with a reason",
     _LOADER, "                if key.tag != _A_STRING:\n", "                if False:\n",
     "tests/test_product_loader.py"),

    ("the sentence is computed and dropped, so the file reads as one with no `product:`",
     _LOADER, "    if refused:\n        return None, refused\n", "    if False:\n        pass\n"),

    ("`<<` is not merged before the keys are read: a key merged in is never seen, and a merge of "
     "string keys is refused as `<<`",
     _LOADER, "            loader.flatten_mapping(root)\n", "            pass\n"),

    ("only scalar keys are checked, so a list or a mapping as a key is the loader's error again",
     _LOADER, "                if key.tag != _A_STRING:\n",
     "                if isinstance(key, yaml.ScalarNode) and key.tag != _A_STRING:\n"),

    ("a quoted key is refused too: the check reads how the key is written, not what YAML reads",
     _LOADER, "                if key.tag != _A_STRING:\n",
     "                if key.tag != _A_STRING or key.style:\n"),

    ("only a key whose tag the loader can build is refused, so `!foo x:` and `!!python/str x:` "
     "reach construction and come back as `not valid YAML`",
     _LOADER, "                if key.tag != _A_STRING:\n",
     "                if key.tag != _A_STRING and key.tag in loader.yaml_constructors:\n"),

    ("an empty key (`? ` with nothing after it) is let through, and raises TypeError again",
     _LOADER, "                if key.tag != _A_STRING:\n",
     "                if key.tag != _A_STRING and key.end_mark.index > key.start_mark.index:\n"),

    # re-pinned 2026-10-19: the key is now named by `_as_written`, which drops its comments
    ("the key is named by its value, not as the file spells it (`aGk=` for `!!binary aGk=`, a "
     "list of nodes for `[a, b]`)",
     _LOADER, "    written = _as_written(text, key)\n", "    written = str(key.value)\n"),

    ("a key written across lines is named with its line breaks",
     _LOADER, "    return \" \".join(spelled.split())\n", "    return spelled.strip()\n"),

    ("a comment written inside a key is named as part of it",
     _LOADER, "            spelled += re.sub(r\"#.*\", \"\", text[at:token.start_mark.index])\n",
     "            spelled += text[at:token.start_mark.index]\n"),

    ("an empty key is named `''`, which names nothing",
     _LOADER, "    named = repr(written) if written else \"an empty key\"\n",
     "    named = repr(written)\n"),

    ("a key of any length is named whole (2,000 entries made a sentence of 23,866 characters)",
     _LOADER, "    if len(written) > _KEY_SHOWN:\n", "    if False:\n"),

    ("a key exactly as long as the cap is cut although it fits",
     _LOADER, "    if len(written) > _KEY_SHOWN:\n", "    if len(written) >= _KEY_SHOWN:\n"),

    ("a key cut at the cap is one character longer than the cap",
     _LOADER, "written[:_KEY_SHOWN - 1] + \"…\"", "written[:_KEY_SHOWN] + \"…\""),

    ("the line is counted from zero, one above the key",
     _LOADER, "(line {key.start_mark.line + 1})", "(line {key.start_mark.line})"),

    # re-pinned 2026-10-19: the sentence moved into `_not_a_string`
    ("the sentence no longer names the file",
     _LOADER, "return (f\"{DOCS_MANIFEST} is invalid at {named} ", "return (f\"invalid at {named} "),

    ("the sentence names the node's class instead of the shape YAML reads",
     _LOADER, "not {shape};", "not {type(key).__name__};"),

    ("the sentence gives the cause and no remedy",
     _LOADER, "not {shape}; quote the key if it is meant as text\")", "not {shape}\")"),

    ("a shape the loader builds is left out of the family, so it is never tried",
     TEST, "    \"tag:yaml.org,2002:binary\": (\"!!binary aGk=\",),\n", ""),

    ("a spelling that is not its shape: YAML 1.1 reads `1e5` as a string, not a float, so the row "
     "would try nothing",
     TEST, "(\"1.5\", \".inf\", \".nan\", \"6.8e+5\")",
     "(\"1e5\", \".inf\", \".nan\", \"6.8e+5\")"),

    # what `yaml.safe_load` did by its name
    ("THE FILE IS READ BY A LOADER THAT BUILDS PYTHON OBJECTS: `product: !!python/object/apply:"
     "os.getcwd []` runs `os.getcwd` on the worker that reads the file",
     _LOADER, "    loader = yaml.SafeLoader(text)\n", "    loader = yaml.UnsafeLoader(text)\n"),

    ("the key is scanned for its name by another loader than the safe one",
     _LOADER, "yaml.scan(text, Loader=yaml.SafeLoader)", "yaml.scan(text, Loader=yaml.UnsafeLoader)"),

    ("AN EMPTY DOCUMENT IS CONSTRUCTED ANYWAY: an empty or comment-only file raises "
     "AttributeError, which is no YAMLError and escapes every caller",
     _LOADER, "(loader.construct_document(root) if root is not None else None)",
     "loader.construct_document(root)"),

    ("a tag that builds a Python object is left out of the family, so it is never tried",
     TEST, "    \"tag:yaml.org,2002:python/object/apply:\": \"!!python/object/apply:os.getcwd []\",\n",
     ""),

    ("a Python spelling the unsafe loader cannot build, so its row would try nothing",
     TEST, "\"!!python/object/apply:os.getcwd []\"", "\"!!python/object/apply:os.no_such_name []\""),

    ("a text that is not empty is counted as a file with nothing in it",
     TEST, "\"# only a comment\\n\", ", "\"x  # not only a comment\\n\", "),

    # added after the re-review of 027d4b0, 2026-10-19: these three survived it
    ("ONE DOCUMENT IS READ AND THE REST IGNORED: `product: books\\n---\\nsources: [a/b]` loads "
     "with `sources` dropped without a word (the first-document idiom `load_all` uses)",
     _LOADER, "        root = loader.get_single_node()\n",
     "        root = loader.get_node() if loader.check_node() else None\n"),

    ("the cap grows past what a sentence can carry, so the 2,000-entry key is named whole again",
     _LOADER, "_KEY_SHOWN = 80\n", "_KEY_SHOWN = 100_000\n"),

    ("a flow-style root (`{product: books, on: push}`) is not checked",
     _LOADER, "        if isinstance(root, yaml.MappingNode):\n",
     "        if isinstance(root, yaml.MappingNode) and not root.flow_style:\n"),

    ("a text of one document is counted as several",
     TEST, "BETWEEN = (\"---\\n\", ", "BETWEEN = (\"\", "),
]
