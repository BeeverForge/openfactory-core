"""A key of `.openfactory/product.yaml` that YAML does not read as a string is an error the parse
returns, naming the file and the key, never an exception (#819).

`parse_docs_manifest` promises `(docs, error)` for any text of the file, and the file is often
written by hand or by another tool. A mapping whose keys were not all strings reached
`ProductDocs(**data)` and raised `TypeError: keywords must be strings`, which nothing caught:
`1: x`, `on: push` (YAML 1.1 reads `on` as true) and a key merged in by `<<` each crashed the
caller. A list or a mapping written as a key was refused by the loader in its own words, which
named a position and no key.

THE FAMILY IS THE LOADER'S. A key is any node YAML can build, so its shapes are the tags
`yaml.SafeLoader` constructs, other than `!!str`. `SPELLINGS` writes each shape as a person would:
the words the resolver reads as a bool or a null are taken from the resolver itself, and the other
shapes are written by hand. The first test holds the table to the loader's own list, so a shape a
later PyYAML adds is a red test until it has a spelling, and a spelling that no longer means its
shape is red too. Each spelling is then written in every layout YAML gives a key (`LAYOUTS`), and
the rule is one sentence for all of them, in the shape the parse already uses for a field it
cannot read. The guard against overreach is the same spellings quoted: a key that IS a string
still loads.
"""

from __future__ import annotations

import json
import re
import textwrap

import pytest
import yaml

from openfactory.product.loader import DOCS_MANIFEST, parse_docs_manifest

STR = "tag:yaml.org,2002:str"


def _resolver_words(tag: str) -> tuple[str, ...]:
    """Every word the loader's resolver reads as `tag`. The bool and null patterns are lists of
    words (`yes|Yes|YES|no|…|on|…|off`), and those words are the keys that surprise a person."""
    return tuple(sorted({
        word
        for resolvers in yaml.SafeLoader.yaml_implicit_resolvers.values()
        for resolved, regexp in resolvers if resolved == tag
        for word in re.findall(r"[\w~]+", regexp.pattern)
    }))


#: every shape a key can take besides a string, written as a person writes it
SPELLINGS: dict[str, tuple[str, ...]] = {
    "tag:yaml.org,2002:bool": _resolver_words("tag:yaml.org,2002:bool"),
    "tag:yaml.org,2002:null": _resolver_words("tag:yaml.org,2002:null"),
    "tag:yaml.org,2002:int": ("1", "-3", "0x1F", "017", "1_000"),
    "tag:yaml.org,2002:float": ("1.5", ".inf", ".nan", "6.8e+5"),
    "tag:yaml.org,2002:timestamp": ("2026-10-18", "2026-10-18T10:00:00Z"),
    "tag:yaml.org,2002:binary": ("!!binary aGk=",),
    "tag:yaml.org,2002:seq": ("[a, b]", "[]"),
    "tag:yaml.org,2002:map": ("{a: 1}", "{}"),
    "tag:yaml.org,2002:set": ("!!set {a}",),
    "tag:yaml.org,2002:omap": ("!!omap [a: 1]",),
    "tag:yaml.org,2002:pairs": ("!!pairs [a: 1]",),
}

#: every way a key reaches the top level of the file. The key is on line 2 in each.
LAYOUTS: dict[str, str] = {
    "written": "product: books\n{key}: x\n",
    "complex-key": "product: books\n? {key}\n: x\n",
    "merged": "product: books\n<<: {{? {key} : x}}\n",
}

CASES = [pytest.param(tag, key, id=f"{tag.rsplit(':', 1)[1]}:{key}")
         for tag, keys in SPELLINGS.items() for key in keys]


def _shape(tag: str) -> str:
    return "!!" + tag.rsplit(":", 1)[1]


def _invalid_at() -> str:
    """How the parse begins the sentence for a field it cannot read: the file, then `is invalid at`."""
    _, error = parse_docs_manifest("sources: []\n")
    assert error.endswith("'product': Field required"), error
    return error.removesuffix("'product': Field required")


def test_every_shape_the_loader_builds_has_a_spelling_and_each_spelling_is_that_shape():
    built = {tag for tag in yaml.SafeLoader.yaml_constructors if tag is not None} - {STR}
    assert set(SPELLINGS) == built
    for tag, keys in SPELLINGS.items():
        assert keys, f"no spelling for {tag}"
        for key in keys:
            root = yaml.compose(f"? {key}\n: x\n", Loader=yaml.SafeLoader)
            assert root.value[0][0].tag == tag, f"{key!r} is not {tag}"


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize(("tag", "key"), CASES)
def test_a_key_that_is_not_a_string_is_an_error_naming_the_file_and_the_key(tag, key, layout):
    docs, error = parse_docs_manifest(LAYOUTS[layout].format(key=key))
    assert docs is None
    assert error.startswith(f"{DOCS_MANIFEST} ")
    assert error == f"{_invalid_at()}{key!r} (line 2): a key must be a string, not {_shape(tag)}"


def _in_block_style(node: yaml.Node) -> yaml.Node:
    if isinstance(node, yaml.SequenceNode | yaml.MappingNode):
        node.flow_style = False
        for child in node.value:
            for part in child if isinstance(child, tuple) else (child,):
                _in_block_style(part)
    return node


COLLECTIONS = [case for case in CASES
               if isinstance(yaml.compose(case.values[1], Loader=yaml.SafeLoader),
                             yaml.SequenceNode | yaml.MappingNode)]


@pytest.mark.parametrize(("tag", "key"), COLLECTIONS)
def test_a_collection_key_written_across_lines_is_named_on_one_line(tag, key):
    block = yaml.serialize(_in_block_style(yaml.compose(key, Loader=yaml.SafeLoader)),
                           Dumper=yaml.SafeDumper)
    docs, error = parse_docs_manifest(
        "product: books\n? " + textwrap.indent(block, "  ").removeprefix("  ") + ": x\n")
    assert docs is None
    named = " ".join(block.split())
    assert error == f"{_invalid_at()}{named!r} (line 2): a key must be a string, not {_shape(tag)}"


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize(("tag", "key"), CASES)
def test_the_same_key_written_as_a_string_loads(tag, key, layout):
    docs, error = parse_docs_manifest(LAYOUTS[layout].format(key=json.dumps(key)))
    assert error == ""
    assert docs is not None and docs.product == "books"
