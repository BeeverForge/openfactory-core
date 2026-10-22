"""The system map as files: `system.yaml`, `api.yaml`, `schema.yaml`, `adr-index.yaml`, `index.md`.

WHERE THEY LIVE: `.okf/system/` in the product's CONTEXT repository — beside `.okf/repos/`, the
per-source bundles, because the system belongs to no one source (ADR-0052 D17). `okf.py` already
reserves the `.okf/` root for what crosses repositories, and one directory under it keeps the five
files together and out of the way of `index.md`, the front door onboarding writes at the root.

    system.yaml      the sources read, the components, the links between them, the queues, the
                     infrastructure, and everything that could not be derived
    api.yaml         the interfaces: HTTP APIs with their operations, gRPC services, events with
                     their producers and consumers
    schema.yaml      the databases: each schema, its owners and its users
    adr-index.yaml   the decision records of every source
    index.md         the door, for a person and for the product role — what could NOT be derived
                     comes first, before anything the map does say (the order `okf.render_index`
                     keeps, for its reason)

DETERMINISTIC, AND IT CONVERGES. The files are written with sorted keys from pre-sorted lists, so
one state of the sources is one set of bytes. `derived_key` hashes the map with every commit and
the clock blanked: a commit that changed nothing the layer reads leaves the key where it was, and
the refresh publishes nothing (`knowledge-layer.md` §22 D-5, one artefact along) — one commit in
the context repository per real change to the system, never one per merge.

AND READ BACK WHOLE (#1002). `read_published` is the inverse of `write_system`: every part of the
map from the file `LAYOUT` puts it in — the one layout both directions use, so a part cannot be
written to one file and looked for in another — or, when there is no map to answer, why: none was
published, or one was and a file of it cannot be read. Never a map with an unreadable part left
out: an `api.yaml` that did not parse would otherwise read as a product that declares no interface.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from openfactory.knowledge.system.contracts import SystemMap
from openfactory.util import yaml_io

SYSTEM_DIRNAME = "system"
SYSTEM_FILE = "system.yaml"
API_FILE = "api.yaml"
SCHEMA_FILE = "schema.yaml"
ADR_INDEX_FILE = "adr-index.yaml"
INDEX_FILE = "index.md"
FILES = (SYSTEM_FILE, API_FILE, SCHEMA_FILE, ADR_INDEX_FILE, INDEX_FILE)

#: WHICH FILE HOLDS WHICH PART OF THE MAP: what `render` writes into each YAML file beside the head
#: (`version`, `derived_key`, `generated_at`), and where `read_published` reads each part back.
#: Every field of `SystemMap` but the head's is in exactly one of them — the suite reads the model's
#: fields and holds it, so a part added to the map is placed here before it can be published.
LAYOUT: dict[str, tuple[str, ...]] = {
    SYSTEM_FILE: ("sources", "components", "links", "queues", "infrastructure", "not_derived"),
    API_FILE: ("http", "grpc", "events"),
    SCHEMA_FILE: ("databases",),
    ADR_INDEX_FILE: ("adrs",),
}
#: The fields of `SystemMap` every file carries rather than one file holds.
HEAD = ("version", "generated_at")

#: The sentence that stops a reader taking the map for the system. Written into `system.yaml` and
#: at the top of `index.md`.
SCOPE_LIMIT = (
    "Derived without a model from what the product's repositories declare — OpenAPI, AsyncAPI, "
    "proto, migrations, compose, Kubernetes and Terraform — read as text; nothing in them was "
    "run. Every entry cites the file and the commit it came from. What a repository does not "
    "declare (an address chosen at run time, a call made through code no description names) is "
    "not here, and what could not be derived is listed. Test, example, vendored and build "
    "directories are not read. It says where to look; the code says what is true.")


def _dump(data: object) -> str:
    """Deterministic YAML — the contract `okf._dump` states: sorted keys, block style, no
    aliases (`yaml_io.dump` writes none: the files are read by people and by roles that grep them,
    and `*id001` is neither), unicode kept."""
    return yaml_io.dump(data, sort_keys=True, default_flow_style=False, allow_unicode=True,
                        width=100)


def _plain(model) -> object:
    return model.model_dump(by_alias=True, mode="json")


def derived_key(system: SystemMap) -> str:
    """The map's identity with every provenance stamp blanked — the commit on each citation, the
    commit of each source, and the clock. Equal keys: the refresh has nothing to publish."""
    data = _plain(system)
    data["generated_at"] = ""

    def blank(node: object) -> object:
        if isinstance(node, dict):
            return {k: ("" if k == "commit" else blank(v)) for k, v in node.items()}
        if isinstance(node, list):
            return [blank(v) for v in node]
        return node

    raw = json.dumps(blank(data), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def render(system: SystemMap) -> dict[str, str]:
    """`{file name: text}` for the five files: each YAML file the head and the parts `LAYOUT` gives
    it (`system.yaml` the scope limit too), and the door."""
    data = _plain(system)
    head = {"version": data["version"], "derived_key": derived_key(system)}
    if data["generated_at"]:
        head["generated_at"] = data["generated_at"]
    out = {name: _dump({**head, **({"scope_limit": SCOPE_LIMIT} if name == SYSTEM_FILE else {}),
                        **{part: data[part] for part in parts}})
           for name, parts in LAYOUT.items()}
    out[INDEX_FILE] = render_index(system)
    return out


def write_system(system: SystemMap, into: str | Path) -> list[Path]:
    """The five files, written INTO `into` (the caller chooses the directory, as `write_okf`'s
    caller does). Returns the paths written, sorted."""
    out = Path(into)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in render(system).items():
        (out / name).write_text(text, encoding="utf-8")
        written.append(out / name)
    return sorted(written)


def read_derived_key(root: str | Path, rel: str) -> str:
    """The `derived_key` the `system.yaml` at `rel` under `root` carries — "" when there is none to
    read. Read through `tree.read_text`, like every file of a checkout: a `system.yaml` somebody
    replaced with a link out of the context repository is not followed."""
    from openfactory.knowledge.system.tree import read_text

    got = read_text(root, rel)
    if got.text is None:
        return ""
    try:
        data = yaml_io.load(got.text)
    except (yaml.YAMLError, ValueError, RecursionError):
        return ""
    return str(data.get("derived_key") or "") if isinstance(data, dict) else ""


#: What a read of the published map found — a word a program branches on (`Published.state`).
#: The map was read, whole.
PUBLISHED = "published"
#: There is no `system.yaml` to read: the refresh has not published one — it has not run since the
#: product declared its sources, or the product declares none.
NOT_PUBLISHED = "not-published"
#: A map is published and a file of it cannot be read: missing, a link, too large, not YAML, or
#: not the map's shape. Named, with why; nothing of the map is answered.
UNREADABLE = "unreadable"
READ_STATES = (PUBLISHED, NOT_PUBLISHED, UNREADABLE)


@dataclass(frozen=True)
class Published:
    """The map published at one directory (`system`, with the `derived_key` its files carry), or
    the word and the sentence that say why there is none to answer."""

    state: str
    why: str = ""
    system: SystemMap | None = None
    derived_key: str = ""


def read_published(root: str | Path, rel_dir: str | PurePosixPath) -> Published:
    """The map `write_system` left at `rel_dir` under `root` — every part read back from the file
    `LAYOUT` puts it in — or why there is none to answer (`Published.state`).

    Every file through `tree.read_text`, as every file of a checkout is read here: a file replaced
    by a link, one past the ceiling, one that is not UTF-8 is refused, never followed. Every
    document through `yaml_io.load`, the loader of the core's own files — not `text.load_yaml`,
    the counting loader this layer keeps for the formats it derives from: `_dump` writes no anchor
    or alias, so a published part that holds one was not written by the refresh, and is answered
    unreadable with the loader's sentence. And every part through the map's own models, so what is
    answered is what `SystemMap` declares and nothing a hand added to a file beside it."""
    from openfactory.knowledge.system.tree import read_text

    base = PurePosixPath(rel_dir)
    if not os.path.lexists(Path(root) / base / SYSTEM_FILE):
        return Published(NOT_PUBLISHED, f"no system map is published at `{base}` yet: the "
                                        f"knowledge refresh derives it from the sources the "
                                        f"product declares, after a merge and on its schedule")
    read: dict[str, dict] = {}
    for name in LAYOUT:
        rel = str(base / name)
        got = read_text(root, rel)
        if got.text is None:
            return Published(UNREADABLE, f"the system map at `{base}` cannot be read: `{name}` "
                                         f"{got.why}")
        try:
            data = yaml_io.load(got.text)
        except yaml_io.YamlRefused as exc:
            return Published(UNREADABLE, f"the system map at `{base}` cannot be read: `{name}` is "
                                         f"refused — {exc}")
        except (yaml.YAMLError, ValueError) as exc:
            # the kind of error, never `str(exc)`: PyYAML's quotes the lines of the file under it
            return Published(UNREADABLE, f"the system map at `{base}` cannot be read: `{name}` is "
                                         f"not YAML ({type(exc).__name__})")
        if not isinstance(data, dict):
            return Published(UNREADABLE, f"the system map at `{base}` cannot be read: `{name}` "
                                         f"is not a mapping")
        missing = [part for part in LAYOUT[name] if part not in data]
        if missing:
            return Published(UNREADABLE, f"the system map at `{base}` cannot be read: `{name}` "
                                         f"holds no {', '.join(f'`{m}`' for m in missing)}")
        read[name] = data
    head = read[SYSTEM_FILE]
    try:
        system = SystemMap(**{key: head[key] for key in HEAD if head.get(key) is not None},
                           **{part: read[name][part]
                              for name, parts in LAYOUT.items() for part in parts})
    except (ValueError, TypeError) as exc:
        part, where = _first_error(exc)
        name = next((n for n, parts in LAYOUT.items() if part in parts), SYSTEM_FILE)
        return Published(UNREADABLE, f"the system map at `{base}` cannot be read: `{name}` does "
                                     f"not hold the map's shape ({where})")
    return Published(PUBLISHED, system=system, derived_key=str(head.get("derived_key") or ""))


def _first_error(exc: BaseException) -> tuple[str, str]:
    """`(the part, where in it)` a published map first departs from the map's shape at — the
    field's path and the kind of departure, never the value found there."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            first = errors()[0]
            loc = [str(p) for p in first.get("loc", ())]
            return (loc[0] if loc else ""), f"{'.'.join(loc)}: {first.get('type', '')}"
        except (IndexError, TypeError, AttributeError):
            pass
    return "", type(exc).__name__


def _where(cite) -> str:
    line = f":{cite.line}" if cite.line else ""
    return f"`{cite.repo}` `{cite.path}{line}`"


def render_index(system: SystemMap) -> str:
    """The door: what could not be derived, then the components and how they talk."""
    lines = ["# The system, across the product's sources", "", "> " + SCOPE_LIMIT, ""]
    lines += ["## What this map could not derive", ""]
    if system.not_derived:
        for n in system.not_derived:
            where = f"`{n.repo}`" + (f" `{n.path}`" if n.path else "") if n.repo else ""
            lines.append(f"- **{n.kind}** — {where + ': ' if where else ''}{n.detail}")
    else:
        lines.append("- Nothing was recorded as not derived by the pass that wrote this.")
    lines += ["", "## Sources", ""]
    for s in system.sources:
        if s.missing:
            lines.append(f"- `{s.repo}` — NOT READ: {s.missing}")
        else:
            lines.append(f"- `{s.repo}` @ `{s.commit[:12] or '(no commit)'}` — {s.files} "
                         f"declaration file(s) read"
                         + (f"; not checked out, holding only pictures, fonts or binaries: "
                            f"{', '.join(f'`{d}`' for d in s.left_out)}" if s.left_out else ""))
    lines += ["", "## Components", ""]
    if not system.components:
        lines.append("- None was declared.")
    for c in system.components:
        code = f" — code in `{c.repo}` `{c.code}`" if c.repo else ""
        lines.append(f"- **{c.name}** ({c.kind}){code}")
        for link in [lk for lk in system.links if lk.from_ == c.name]:
            lines.append(f"  - talks to **{link.to}** ({link.kind}, {link.via})")
    for heading, file_name, count in (
            ("Interfaces", API_FILE, len(system.http) + len(system.grpc) + len(system.events)),
            ("Databases", SCHEMA_FILE, len(system.databases)),
            ("Decision records", ADR_INDEX_FILE, len(system.adrs))):
        lines += ["", f"## {heading}", "", f"{count} in [`{file_name}`]({file_name})."]
    if system.http:
        lines.append("")
        for a in system.http:
            lines.append(f"- HTTP API of **{a.component}** — {len(a.operations)} operation(s), "
                         f"{_where(a.source)}")
    if system.events:
        lines.append("")
        for e in system.events:
            senders = ", ".join(sorted({p.component for p in e.producers})) or "nobody declared"
            receivers = ", ".join(sorted({c.component for c in e.consumers})) or "nobody declared"
            lines.append(f"- event `{e.channel}` — sent by {senders}; received by {receivers}")
    if system.databases:
        lines.append("")
        for d in system.databases:
            owners = ", ".join(d.owners) or "no migrations"
            users = f"; also used by {', '.join(d.users)}" if d.users else ""
            lines.append(f"- database **{d.name}** — {len(d.tables)} table(s), owned by "
                         f"{owners}{users}")
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["ADR_INDEX_FILE", "API_FILE", "FILES", "HEAD", "INDEX_FILE", "LAYOUT", "NOT_PUBLISHED",
           "PUBLISHED", "READ_STATES", "SCHEMA_FILE", "SCOPE_LIMIT", "SYSTEM_DIRNAME",
           "SYSTEM_FILE", "UNREADABLE", "Published", "derived_key", "read_derived_key",
           "read_published", "render", "render_index", "write_system"]
