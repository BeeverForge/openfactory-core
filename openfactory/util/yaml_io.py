"""Every YAML document the core reads, and every one it writes, goes through this module (#1005).

THE RULE: A YAML FILE A REPOSITORY HOLDS IS READ WITHOUT EXPANDING ALIASES, AND WITHIN BOUNDS.

`yaml.SafeLoader` refuses every tag that would build a Python object, and that was the only rule
the readers shared. It keeps anchors and aliases: `*a` hands back the very value `&a` built, so a
small file parses to a small value that SHARES itself many times over. Nothing goes wrong until
something walks it — a model validates it, it is dumped, turned into text, compared, iterated —
and then every repetition is written out, one level of aliases multiplying the next (#824 measured
3.5 GB and 52 seconds for one title of a 600-byte front matter). Nesting was not bounded either: a
file nested a thousand levels deep raised `RecursionError` out of every reader of it (#842). A file
a repository holds is somebody else's input, so each of those is a bound to state, not a case to
handle where it was noticed.

TWO LOADERS, BOTH BOUNDED, chosen by whose format the file is:

- `Loader` reads the core's own files — the manifest and `product.yaml`, the published system map,
  card and document front matter, flows, the knowledge bundle, the registry, a rubric, a battery,
  the package's own defaults. It REFUSES an anchor and an alias by name. None of the core's
  writers emits one (`dump` below is the only writer, and it never does), so a file that carries
  one was not written by the core, and the remedy is one sentence: write the value out.
- `CountingLoader` reads a format another specification defines and gives anchors to — compose
  files (whose specification documents fragments as `x-…: &name` with `<<: *name`), CI pipelines,
  Kubernetes manifests, OpenAPI. Refusing an anchor there would refuse a well-formed file its own
  format allows (the preview's fixture of a developer's compose file carries one). So an alias is
  read, and COUNTED AT THE FULL SIZE AND DEPTH OF WHAT IT REPEATS: the bounds below hold for the
  value as any walk of it will see it, not for the text. An alias inside the value it repeats is a
  value that contains itself, which no bound can hold, and is refused.

Both refuse, before anything is built from it, a document over `MAX_BYTES`, one nested deeper than
`MAX_DEPTH` (checked while composing, one level at a time, so the interpreter never comes near its
own recursion limit) and one holding more than `MAX_NODES` values. The refusal is `YamlRefused`, a
`yaml.MarkedYAMLError`: every reader that already answers "this file is not YAML" — with a
sentence, a finding, an unreadable state or an absent value — answers this one the same way, and
no reader needed a new branch to stay inside its own contract. It is also logged here, once, so a
reader whose contract is "absent when unreadable" does not make it silent.

ONE DOOR, HELD BY ITS SYNTAX TREE: `tests/test_yaml_is_read_without_aliases_and_within_bounds.py`
reads every module of `openfactory/` and fails on any use of the `yaml` module outside this file
other than its errors and its node classes — a `yaml.safe_load` added anywhere is red before it
merges.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml
from yaml.events import AliasEvent

log = logging.getLogger(__name__)

#: Bytes of one document. The ceiling the system layer reads a repository's file to
#: (`knowledge/system/tree.READ_CEILING`): a declaration is small, and the readers of the core's own
#: files are not to refuse what that layer admits (a test holds the two together).
MAX_BYTES = 1_000_000

#: Values on the path from a document's root to its deepest value, the root and the leaf included.
#: A compose file is about 6 deep and a Kubernetes custom resource's schema about 40. Composing
#: costs three interpreter frames a level, so 100 levels stay far inside the interpreter's own
#: limit of 1,000 wherever the reader is called from.
MAX_DEPTH = 100

#: Values one document holds — scalars, sequences and mappings — with every alias counted at the
#: size of what it repeats. A 1 MB OpenAPI file holds about 60,000.
MAX_NODES = 200_000


class YamlRefused(yaml.MarkedYAMLError):
    """A YAML document refused before anything was built from it. `problem` is the sentence: what
    was found, the line, and what to do. A `yaml.YAMLError`, so every reader that answers a file
    that is not YAML answers this one."""

    def __init__(self, problem: str, mark: yaml.Mark | None = None) -> None:
        super().__init__(problem=problem, problem_mark=mark)

    def __str__(self) -> str:
        # the sentence alone: it names the line already, and a reader that quotes `str(exc)` into
        # a finding or a health line quotes one sentence, not a snippet of the file under it
        return self.problem or ""


def _line(mark: yaml.Mark | None) -> str:
    return f"line {mark.line + 1}" if mark is not None else "the start"


def _size_of(stream: Any) -> int:
    """The document's size in bytes, measured without encoding more than the ceiling allows."""
    if isinstance(stream, bytes):
        return len(stream)
    if len(stream) > MAX_BYTES:  # a character is at least one byte, so this is already over
        return len(stream)
    return len(stream.encode("utf-8", "surrogatepass"))


def _refuse(problem: str, mark: yaml.Mark | None = None) -> YamlRefused:
    log.warning("OPENFACTORY_YAML_REFUSED a YAML document was refused before it was read: %s",
                problem)
    return YamlRefused(problem, mark)


class Loader(yaml.SafeLoader):
    """`yaml.SafeLoader` that refuses an anchor and an alias by name, and reads within the bounds.

    The checks sit in `compose_node`, the one method every value passes through on its way from
    the parser's events to a node, so they hold whatever a subclass adds (a tag of its own, a line
    on every string) and whichever of PyYAML's entry points the loader is driven by."""

    #: whether an anchor and its aliases are read (each alias counted at its full size and depth)
    #: rather than refused; `CountingLoader` says yes
    READS_ALIASES = False

    def __init__(self, stream: Any) -> None:
        if not isinstance(stream, (str, bytes)):
            stream = stream.read(MAX_BYTES + 1)
        size = _size_of(stream)
        if size > MAX_BYTES:
            raise _refuse(f"{size:,} bytes, over the {MAX_BYTES:,}-byte ceiling a YAML file is "
                          f"read to — split it or leave it out")
        super().__init__(stream)
        self._depth = 0            # the depth of the value being composed (the root is 1)
        self._reach = 0            # the deepest level reached so far, aliases counted in
        self._values = 0           # values composed so far, aliases counted at full size
        self._held: dict[yaml.Node, tuple[int, int]] = {}  # anchored node → (values, height)

    def compose_node(self, parent: yaml.Node | None, index: Any) -> yaml.Node:
        event = self.peek_event()
        if isinstance(event, AliasEvent):
            return self._alias(event, parent, index)
        anchor = getattr(event, "anchor", None)
        if anchor is not None and not self.READS_ALIASES:
            raise _refuse(f"an anchor (`&{anchor}`, {_line(event.start_mark)}): this file is read "
                          f"without anchors or aliases — write the value out where it is used",
                          event.start_mark)
        self._depth += 1
        try:
            depth, before, outer_reach = self._depth, self._values, self._reach
            self._within(depth, event.start_mark)
            self._count(1, event.start_mark)
            self._reach = depth
            node = super().compose_node(parent, index)
            if anchor is not None:
                self._held[node] = (self._values - before, self._reach - depth + 1)
            self._reach = max(outer_reach, self._reach)
            return node
        finally:
            self._depth -= 1

    def _alias(self, event: AliasEvent, parent: yaml.Node | None, index: Any) -> yaml.Node:
        if not self.READS_ALIASES:
            raise _refuse(f"an alias (`*{event.anchor}`, {_line(event.start_mark)}): this file is "
                          f"read without anchors or aliases — write the value out where it is "
                          f"used", event.start_mark)
        node = super().compose_node(parent, index)  # PyYAML refuses an alias nothing anchored
        held = self._held.get(node)
        if held is None:
            raise _refuse(f"an alias inside the value it repeats (`*{event.anchor}`, "
                          f"{_line(event.start_mark)}): a value that contains itself cannot be "
                          f"read", event.start_mark)
        values, height = held
        reach = self._depth + height
        self._within(reach, event.start_mark, alias=event.anchor)
        self._count(values, event.start_mark, alias=event.anchor)
        self._reach = max(self._reach, reach)
        return node

    def _within(self, depth: int, mark: yaml.Mark, *, alias: str | None = None) -> None:
        if depth > MAX_DEPTH:
            how = (f" once `*{alias}` is counted at the depth of what it repeats"
                   if alias is not None else "")
            raise _refuse(f"nested deeper than {MAX_DEPTH} levels{how} ({_line(mark)}): a YAML "
                          f"file is read to {MAX_DEPTH} levels", mark)

    def _count(self, values: int, mark: yaml.Mark, *, alias: str | None = None) -> None:
        self._values += values
        if self._values > MAX_NODES:
            how = (f" once `*{alias}` is counted at the size of what it repeats"
                   if alias is not None else "")
            raise _refuse(f"more than {MAX_NODES:,} values{how} ({_line(mark)}): a YAML file is "
                          f"read to {MAX_NODES:,} values", mark)


class CountingLoader(Loader):
    """`Loader` for a format whose own specification has anchors: an alias is read, counted at the
    full size and depth of what it repeats, and the bounds hold for the value as it will be
    walked."""

    READS_ALIASES = True


def load(text: str | bytes, *, loader: type[Loader] = Loader) -> Any:
    """One YAML document, read by `loader` — `Loader` unless the file is in a format whose
    specification has anchors. None for a document of nothing; `YamlRefused` (a `yaml.YAMLError`)
    for one past a rule, and `yaml.YAMLError` for one that is not YAML. A stream of several
    documents is refused, as `yaml.safe_load` refuses it."""
    if not (isinstance(loader, type) and issubclass(loader, Loader)):
        raise TypeError(f"{loader!r} is not a loader of this module")
    reader = loader(text)
    try:
        return reader.get_single_data()
    finally:
        reader.dispose()


def tokens(text: str) -> Any:
    """The scanner's tokens of `text`, for a reader that names a value as the file spells it. A
    scanner builds nothing, and the text is held to the same byte ceiling."""
    return yaml.scan(text, Loader=Loader)


class _NoAliases(yaml.SafeDumper):
    """A dumper that writes every repeated value out again rather than as an anchor and an alias.
    `yaml.safe_dump` writes `&id001` for a list or a mapping met twice; a file the core wrote must
    read back through `Loader`, and a person or a role grepping it can read neither."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


def dump(data: Any, stream: Any = None, **options: Any) -> Any:
    """`yaml.safe_dump`, without anchors or aliases. Same options, same return: the text, or None
    when written to `stream`."""
    return yaml.dump(data, stream, Dumper=_NoAliases, **options)


__all__ = ["MAX_BYTES", "MAX_DEPTH", "MAX_NODES", "CountingLoader", "Loader", "YamlRefused",
           "dump", "load", "tokens"]
