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
cannot read, ending with the remedy. The guard against overreach is the same spellings quoted: a
key that IS a string still loads.

A KEY REACHED THROUGH AN ALIAS IS REFUSED BY THE ALIAS (#1005). The file is read without anchors or
aliases, so the two layouts that need one (`THROUGH_AN_ALIAS`) are refused at the anchor, before
any key is read, whatever the key is — a string included. Every spelling is still written in both.

THE LOAD IS ASSEMBLED BY HAND, so what `yaml.safe_load` did by its name is held here too, through
both readers of the file (the product module's and the preview's). A tag that would build a Python
object is refused and never built, wherever it is written. That family is every tag a loader
PyYAML ships adds to the safe one. A file with no document in it reads as an empty mapping, as it
did before. A file of several documents is refused, never read in part.
"""

from __future__ import annotations

import ast
import itertools
import json
import re
import textwrap
from pathlib import Path

import pytest
import yaml

from openfactory.preview.product import read_docs
from openfactory.product.loader import (
    _KEY_SHOWN,
    DOCS_MANIFEST,
    _read_docs_manifest,
    parse_docs_manifest,
)

STR = "tag:yaml.org,2002:str"
REMEDY = "; quote the key if it is meant as text"


def _resolver_words(tag: str) -> tuple[str, ...]:
    """Every word the loader's resolver reads as `tag`. The bool and null patterns are lists of
    words (`yes|Yes|YES|no|…|on|…|off`), and those words are the keys that surprise a person. The
    null list ends with an empty word: `? ` with nothing after it is a null key."""
    return tuple(sorted({
        "".join(word.split())  # the patterns are written with re.X, which ignores the space
        for resolvers in yaml.SafeLoader.yaml_implicit_resolvers.values()
        for resolved, regexp in resolvers if resolved == tag
        for word in regexp.pattern.removeprefix("^(?:").removesuffix(")$").split("|")
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

#: every way a key reaches the top level of the file. The key is written on line 2 in each.
LAYOUTS: dict[str, str] = {
    "written": "product: books\n{key}: x\n",
    "complex-key": "product: books\n? {key}\n: x\n",
    "merged": "product: books\n<<: {{? {key} : x}}\n",
    "merged as a sequence": "product: books\n<<: [{{? {key} : x}}]\n",
    "a flow-style root": "{{product: books,\n {key}: x}}\n",
}

#: the layouts that reach the top level through an anchor and an alias: each is refused at the
#: anchor, on line 2, before any key is read (#1005)
THROUGH_AN_ALIAS: dict[str, tuple[str, str]] = {
    "merged through an alias": ("product: books\nx-base: &m {{? {key} : x}}\n<<: *m\n", "&m"),
    "an alias as a key": ("product: books\nx-key: &k {key}\n*k : x\n", "&k"),
}

#: the layouts that cannot write an empty key: `: x` alone is not YAML, in block or in flow style
NO_EMPTY_KEY = ("written", "a flow-style root")

SPELLED = [(tag, key) for tag, keys in SPELLINGS.items() for key in keys]

#: each spelling in each layout that can hold it. The empty key is left out of `NO_EMPTY_KEY` only,
#: and the first test holds that this is YAML's limit, not the test's.
CASES = [pytest.param(tag, key, layout, id=f"{layout}-{tag.rsplit(':', 1)[1]}:{key}")
         for layout in LAYOUTS for tag, key in SPELLED if key or layout not in NO_EMPTY_KEY]


def _shape(tag: str) -> str:
    return "!!" + tag.rsplit(":", 1)[1]


def _named(key: str, layout: str) -> str:
    """How the sentence names a key in `layout`: as written and quoted, or `an empty key` when
    nothing is written."""
    written = " ".join(key.split())
    return repr(written) if written else "an empty key"


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
    for layout in NO_EMPTY_KEY:
        with pytest.raises(yaml.YAMLError):
            yaml.compose(LAYOUTS[layout].format(key=""), Loader=yaml.SafeLoader)


@pytest.mark.parametrize(("tag", "key", "layout"), CASES)
def test_a_key_that_is_not_a_string_is_an_error_naming_the_file_and_the_key(tag, key, layout):
    docs, error = parse_docs_manifest(LAYOUTS[layout].format(key=key))
    assert docs is None
    assert error.startswith(f"{DOCS_MANIFEST} ")
    assert error == (f"{_invalid_at()}{_named(key, layout)} (line 2): a key must be a string, "
                     f"not {_shape(tag)}{REMEDY}")


def _in_block_style(node: yaml.Node) -> yaml.Node:
    if isinstance(node, yaml.SequenceNode | yaml.MappingNode):
        node.flow_style = False
        for child in node.value:
            for part in child if isinstance(child, tuple) else (child,):
                _in_block_style(part)
    return node


COLLECTIONS = [(tag, key) for tag, key in SPELLED
               if isinstance(yaml.compose(key, Loader=yaml.SafeLoader),
                             yaml.SequenceNode | yaml.MappingNode)]

NOTE = "  # a note"


def _across_lines(key: str, style: str) -> str:
    """`key` written across lines: in block style, then the same with a comment ending every line,
    then in its own flow style broken after every bracket and comma, a comment ending every line."""
    if style.startswith("block"):
        block = yaml.serialize(_in_block_style(yaml.compose(key, Loader=yaml.SafeLoader)),
                               Dumper=yaml.SafeDumper)
        return block if style == "block" else "".join(f"{ln}{NOTE}\n" for ln in block.splitlines())
    for mark in "[{,":
        key = key.replace(mark, f"{mark}{NOTE}\n")
    return f"{key}{NOTE}\n"


@pytest.mark.parametrize("style", ["block", "block, a comment on every line",
                                   "flow, a comment on every line"])
@pytest.mark.parametrize(("tag", "key"), COLLECTIONS)
def test_a_key_written_across_lines_is_named_on_one_line_without_its_comments(tag, key, style):
    written = _across_lines(key, style)
    docs, error = parse_docs_manifest(
        "product: books\n? " + textwrap.indent(written, "  ").removeprefix("  ") + ": x\n")
    assert docs is None
    named = " ".join(written.replace(NOTE, "").split())
    assert error == (f"{_invalid_at()}{named!r} (line 2): a key must be a string, "
                     f"not {_shape(tag)}{REMEDY}")


#: the longest the sentence may be, however long the key. It is a health line, a panel row and a
#: chat message. This is a fixed number, the bound the first review set, so the cap cannot grow
#: past it unseen: the boundary rows read the cap itself.
AT_MOST = 300


def _long_keys() -> list[str]:
    """Keys at the cap and on either side of it, and one far past it: a flow mapping of 2,000
    entries, which was named whole in a sentence of 23,866 characters."""
    around = [_KEY_SHOWN - 1, _KEY_SHOWN, _KEY_SHOWN + 1, 2 * _KEY_SHOWN]
    return (["[" + "a" * (length - 2) + "]" for length in around]
            + ["{" + ", ".join(f"k{i}: {i}" for i in range(2000)) + "}"])


@pytest.mark.parametrize("key", _long_keys(), ids=lambda key: f"{len(key)} characters")
def test_a_long_key_is_named_by_its_beginning_and_the_sentence_stays_short(key):
    _, error = parse_docs_manifest(LAYOUTS["complex-key"].format(key=key))
    named = ast.literal_eval(re.search(r" is invalid at ('.*') \(line 2\)", error).group(1))
    assert len(named) <= _KEY_SHOWN
    if len(key) <= _KEY_SHOWN:
        assert named == key
    else:
        assert named.endswith("…") and key.startswith(named.removesuffix("…"))
    _, short = parse_docs_manifest(LAYOUTS["complex-key"].format(key="[]"))
    assert len(error) <= len(short) - len("[]") + _KEY_SHOWN
    assert len(error) <= AT_MOST


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize(("tag", "key"), SPELLED)
def test_the_same_key_written_as_a_string_loads(tag, key, layout):
    docs, error = parse_docs_manifest(LAYOUTS[layout].format(key=json.dumps(key)))
    assert error == ""
    assert docs is not None and docs.product == "books"


@pytest.mark.parametrize("layout", THROUGH_AN_ALIAS)
@pytest.mark.parametrize("key", [*(k for _, k in SPELLED if k), *(json.dumps(k) for _, k in SPELLED),
                                 "!foo x"])
def test_a_key_reached_through_an_alias_is_refused_at_the_anchor(key, layout):
    text, anchor = THROUGH_AN_ALIAS[layout]
    docs, error = parse_docs_manifest(text.format(key=key))
    assert docs is None
    assert error == (f"{DOCS_MANIFEST} is not valid YAML: an anchor (`{anchor}`, line 2): this file "
                     f"is read without anchors or aliases — write the value out where it is used")


# --- what `yaml.safe_load` did by its name ------------------------------------------------------

#: both readers of the file: the product module's, and the preview's from its own checkout
READERS = {
    "the product module": lambda root: _read_docs_manifest(root),
    "the preview": lambda root: read_docs(str(root)),
}


def _read(reader: str, root: Path, text: str):
    path = root / DOCS_MANIFEST
    path.parent.mkdir(parents=True)
    path.write_bytes(text.encode("utf-8"))
    return READERS[reader](root)


#: a file with no document in it: no text, a space, line breaks, a byte-order mark, a comment
NOTHING = ("", " ", "\n\n", "\r\n", "\ufeff", "# only a comment\n", "\ufeff  # a comment\r\n\n")
#: an empty document, said with its markers
AN_EMPTY_DOCUMENT = ("---\n", "--- # a comment\n...\n")


def test_nothing_and_an_empty_document_are_what_yaml_reads_them_as():
    for text in NOTHING:
        assert yaml.compose(text, Loader=yaml.SafeLoader) is None, repr(text)
    for text in AN_EMPTY_DOCUMENT:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
        assert (node.tag, node.value) == ("tag:yaml.org,2002:null", ""), repr(text)


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("text", NOTHING + AN_EMPTY_DOCUMENT)
def test_a_file_with_nothing_in_it_reads_as_an_empty_mapping(tmp_path, reader, text):
    assert _read(reader, tmp_path, text) == parse_docs_manifest("{}\n")


#: documents a file may hold, each one readable on its own: one that loads, one that does not
#: validate, and one whose key is not a string
DOCUMENTS = ("product: books\n", "sources: [a/b]\n", "1: x\n")
#: how one document ends and the next begins
BETWEEN = ("---\n", "...\n---\n")
#: two and three of them, in every order, with either way between them
SEVERAL = [between.join(docs) for between in BETWEEN
           for n in (2, 3) for docs in itertools.permutations(DOCUMENTS, n)]


def test_several_documents_are_what_yaml_reads_them_as():
    for text in SEVERAL:
        assert len(list(yaml.compose_all(text, Loader=yaml.SafeLoader))) > 1, repr(text)


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("text", SEVERAL)
def test_a_file_of_several_documents_is_refused_never_read_in_part(tmp_path, reader, text):
    docs, error = _read(reader, tmp_path, text)
    assert docs is None
    assert error.startswith(f"{DOCS_MANIFEST} is not valid YAML: expected a single document")


#: every tag a loader that builds Python objects adds to the safe one, each spelled so that such a
#: loader builds it. A tag that ends in `:` is a prefix, and what follows it names the object.
PYTHON: dict[str, str] = {
    "tag:yaml.org,2002:python/none": "!!python/none ''",
    "tag:yaml.org,2002:python/bool": "!!python/bool true",
    "tag:yaml.org,2002:python/str": "!!python/str x",
    "tag:yaml.org,2002:python/unicode": "!!python/unicode x",
    "tag:yaml.org,2002:python/bytes": "!!python/bytes aGk=",
    "tag:yaml.org,2002:python/int": "!!python/int 1",
    "tag:yaml.org,2002:python/long": "!!python/long 1",
    "tag:yaml.org,2002:python/float": "!!python/float 1.5",
    "tag:yaml.org,2002:python/complex": "!!python/complex 1+2j",
    "tag:yaml.org,2002:python/list": "!!python/list [a]",
    "tag:yaml.org,2002:python/tuple": "!!python/tuple [a]",
    "tag:yaml.org,2002:python/dict": "!!python/dict {a: 1}",
    "tag:yaml.org,2002:python/name:": "!!python/name:os.getcwd ''",
    "tag:yaml.org,2002:python/module:": "!!python/module:os ''",
    "tag:yaml.org,2002:python/object:": "!!python/object:argparse.Namespace {a: 1}",
    "tag:yaml.org,2002:python/object/apply:": "!!python/object/apply:os.getcwd []",
    "tag:yaml.org,2002:python/object/new:": "!!python/object/new:argparse.Namespace {}",
}

#: where a value is written: as a field's own value, and as an item under a field
VALUES = {
    "a field's value": "product: {spelling}\n",
    "an item under a field": "product: books\nsources: [{spelling}]\n",
}


def _tags(loader: type) -> set[str]:
    return {t for t in (*loader.yaml_constructors, *loader.yaml_multi_constructors) if t}


def test_every_tag_a_loader_of_python_objects_adds_has_a_spelling_that_it_builds():
    loaders = [c for c in vars(yaml).values()
               if isinstance(c, type) and issubclass(c, yaml.constructor.BaseConstructor)]
    assert set(PYTHON) == set().union(*map(_tags, loaders)) - _tags(yaml.SafeLoader)
    for tag, spelling in PYTHON.items():
        built = yaml.compose(spelling, Loader=yaml.SafeLoader).tag
        assert built == tag or (tag.endswith(":") and built.startswith(tag)), spelling
        # a spelling the unsafe loader cannot build would try nothing
        yaml.load(spelling, Loader=yaml.UnsafeLoader)


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("where", VALUES)
@pytest.mark.parametrize("spelling", PYTHON.values())
def test_a_tag_that_would_build_a_python_object_is_refused_never_built(tmp_path, reader, where,
                                                                        spelling):
    docs, error = _read(reader, tmp_path, VALUES[where].format(spelling=spelling))
    assert docs is None
    assert error.startswith(
        f"{DOCS_MANIFEST} is not valid YAML: could not determine a constructor for the tag ")
    assert yaml.compose(spelling, Loader=yaml.SafeLoader).tag in error


@pytest.mark.parametrize("text", ["product: books\n", "product: books\n? [a, b]\n: x\n"])
def test_every_loader_the_parse_starts_is_the_safe_one(monkeypatch, text):
    """The class name IS the property, so the class of each loader is read as it is made: every
    pure-Python loader PyYAML ships starts in `Reader.__init__`. The second text is refused, and
    naming its key scans the file again."""
    started: list[type] = []
    start = yaml.reader.Reader.__init__

    def spy(self, stream):
        started.append(type(self))
        start(self, stream)

    monkeypatch.setattr(yaml.reader.Reader, "__init__", spy)
    parse_docs_manifest(text)
    assert started and all(issubclass(c, yaml.SafeLoader) for c in started), started


#: a key whose tag the safe loader builds nothing for: a tag of the file's own, and every Python one
UNBUILT = ("!foo x", *PYTHON.values())


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("spelling", UNBUILT)
def test_a_key_with_a_tag_the_loader_cannot_build_is_named_with_its_tag(spelling, layout):
    docs, error = parse_docs_manifest(LAYOUTS[layout].format(key=spelling))
    assert docs is None
    tag = spelling.split()[0]
    assert error == (f"{_invalid_at()}{_named(spelling, layout)} (line 2): a key must be a string, "
                     f"not {tag}{REMEDY}")
