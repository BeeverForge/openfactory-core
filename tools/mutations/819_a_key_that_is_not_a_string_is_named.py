"""A key of `.openfactory/product.yaml` that is not a string is named, never raised (#819).

`parse_docs_manifest` handed a mapping straight to `ProductDocs(**data)`, so `1: x`, `on: push` or
`<<: {1: x}` raised `TypeError: keywords must be strings` into the caller, and a list or a mapping
as a key came back in the loader's own words with no key in them. The keys are now read from the
composed nodes, after `<<` is merged and before anything is built, and every one that is not
`!!str` is one sentence naming the file, the key as written, its line and its shape. Each row
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

    ("the key is named by its value, not as the file spells it (`aGk=` for `!!binary aGk=`, a "
     "list of nodes for `[a, b]`)",
     _LOADER,
     "                    written = \" \".join(text[key.start_mark.index:key.end_mark.index]"
     ".split())\n",
     "                    written = str(key.value)\n"),

    ("a key written across lines is named with its line breaks",
     _LOADER,
     "                    written = \" \".join(text[key.start_mark.index:key.end_mark.index]"
     ".split())\n",
     "                    written = text[key.start_mark.index:key.end_mark.index].strip()\n"),

    ("the line is counted from zero, one above the key",
     _LOADER, "(line {key.start_mark.line + 1})", "(line {key.start_mark.line})"),

    ("the sentence no longer names the file",
     _LOADER, "f\"{DOCS_MANIFEST} is invalid at {written!r} \"", "f\"invalid at {written!r} \""),

    ("the sentence names the node's class instead of the shape YAML reads",
     _LOADER, "f\"not {shape}\")", "f\"not {type(key).__name__}\")"),

    ("a shape the loader builds is left out of the family, so it is never tried",
     TEST, "    \"tag:yaml.org,2002:binary\": (\"!!binary aGk=\",),\n", ""),

    ("a spelling that is not its shape: YAML 1.1 reads `1e5` as a string, not a float, so the row "
     "would try nothing",
     TEST, "(\"1.5\", \".inf\", \".nan\", \"6.8e+5\")",
     "(\"1e5\", \".inf\", \".nan\", \"6.8e+5\")"),
]
