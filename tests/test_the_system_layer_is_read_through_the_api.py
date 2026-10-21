"""A product's system layer through the front-end API (#1002): what the repositories declare, every
entry cited, no value of a variable.

Against REAL git, the way `test_the_system_layer_is_published.py` stands the product up: the four
quayside repositories and the context repository are bare remotes served over `file://`, the
knowledge refresh derives the map and pushes it, and the route reads it back through the context
repository's checkout — the product's own, synced as every product read syncs it. What is held, in
the issue's order:

  1. THE MAP, WHOLE AND CITED. Both addresses of the read (found in `app.routes`, never listed)
     answer exactly what the context repository publishes, part by part as the files hold it, and
     every entry carries where it came from — a citation naming a file that exists at the commit it
     cites, or, for an entry whose model holds no citation, the repository it is about.
  2. NAMES ONLY — THE FAMILY RULE. A secret-shaped value is planted in every kind of declaration the
     layer reads (the kinds are `derive._Declared`'s, read from the code; the fixture is held to
     fill each), the map is published and read in every state the route answers, and no planted
     value is in any field the route returns — every text field of the read model, walked from the
     model, filled at least once, so no field passes by being empty. The names do cross.
  3. NEVER AN EMPTY MAP FOR ONE THAT IS NOT KNOWN. A source that cannot be checked out is answered as
     a `source-unreadable` entry; a map not published, a published map one file of which cannot be
     read (each file of `render.LAYOUT`, broken each way), and a context repository that cannot be
     reached each answer a word, a sentence, and null in every field of the map.
  4. THE READ MODEL DESCRIBES THE MAP, at every depth; `LAYOUT` places every part of the map in one
     file; and what a hand adds beside the map's fields in a published file is never answered.
  5. THE GATE, READ-ONLY. On both addresses: no credential is a 401, a product and a floor
     credential read it, an unknown project and a project with no product role are the same 404 —
     and that 404 checks out nothing. A read pushes nothing, and files no impediment.
"""

from __future__ import annotations

import base64
import importlib
import json
import os
import shutil
import subprocess
import typing
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import BaseModel

from openfactory.api import read_models
from openfactory.contracts.product import ProductConfig
from openfactory.contracts.project import Project, ProviderRef
from openfactory.knowledge.system import refresh
from openfactory.knowledge.system.contracts import SOURCE_UNREADABLE, SystemMap
from openfactory.util import yaml_io
from tests.test_the_system_layer_is_published import FIXTURE, SOURCES, _git, _remote
from tests.test_yaml_is_read_without_aliases_and_within_bounds import _processor_seconds

# THE MODULES, NOT THE NAMES THE PACKAGE RE-EXPORTS: `openfactory.knowledge.system` exports the
# functions `derive` and `render`, which shadow the modules of the same name as its attributes.
derivation = importlib.import_module("openfactory.knowledge.system.derive")
render = importlib.import_module("openfactory.knowledge.system.render")

#: The project the route is asked about, and a declared source nobody can check out.
NAME = "quayside"
GONE = "quayside-gone"

# ── the planted values: one per place a value sits in each kind of declaration ─────────────────

_B64 = "c2VjcmV0LXExMDAyLWI2NA=="          # base64 of the value below — neither may cross
PLANTED = (
    # compose: a password in a URL, a key, a bearer, a password variable, an env file, a build
    # argument, a command line, a label
    "pw-q1002-compose-url", "sk_live_q1002compose", "tok-q1002-bearer", "pw-q1002-postgres",
    "pw-q1002-dotenv", "npm-q1002-buildarg", "pw-q1002-command", "tok-q1002-label",
    # Kubernetes: a Secret's stringData and data, a ConfigMap's value and URL, an env value, an
    # argument, an annotation on a Service
    "pw-q1002-stringdata", "secret-q1002-b64", _B64, "pw-q1002-configmap", "pw-q1002-cmurl",
    "tok-q1002-k8s-env", "tok-q1002-k8s-args", "tok-q1002-svc",
    # Terraform: a password attribute, a variable's default
    "pw-q1002-tf", "pw-q1002-tfvar",
    # OpenAPI: a server's user part, an example, a default
    "tok-q1002-oaserver", "tok-q1002-oaexample", "pw-q1002-oadefault",
    # AsyncAPI: a server's password, a message example
    "pw-q1002-amqp", "tok-q1002-asyncexample",
    # proto: an option's string
    "tok-q1002-proto",
    # migrations: a column default, a seeded row, a comment
    "sk_live_q1002sql", "sk_live_q1002insert", "pw-q1002-sqlcomment",
    # a decision record's body
    "pw-q1002-adr",
)
#: The variables those values were given under — their NAMES must cross.
NAMES = ("REPORTS_DATABASE_URL", "STRIPE_SECRET_KEY", "AUTH_HEADER", "API_TOKEN", "DB_PASSWORD")

#: Files planted into the quayside sources, beside what they declare already.
EXTRA = {
    "quayside-platform": {
        "docker-compose.reports.yml": (
            "services:\n"
            "  reports:\n"
            "    build:\n"
            "      context: ../quayside-orders\n"
            "      args:\n"
            "        NPM_TOKEN: npm-q1002-buildarg\n"
            "    command: [\"serve\", \"--password\", \"pw-q1002-command\"]\n"
            "    labels:\n"
            "      deploy.token: tok-q1002-label\n"
            "    env_file: .env\n"
            "    environment:\n"
            "      - REPORTS_DATABASE_URL=postgres://reports:pw-q1002-compose-url@orders-db:5432/o\n"
            "      - STRIPE_SECRET_KEY=sk_live_q1002compose\n"
            "      - AUTH_HEADER=Bearer tok-q1002-bearer\n"
            "  reports-db:\n"
            "    image: postgres:16-alpine\n"
            "    environment:\n"
            "      POSTGRES_PASSWORD: pw-q1002-postgres\n"),
        ".env": "SECRET=pw-q1002-dotenv\n",
        "k8s/reports.yaml": (
            "apiVersion: v1\nkind: Secret\nmetadata: {name: reports-creds}\n"
            "stringData:\n  password: pw-q1002-stringdata\n"
            f"data:\n  token: {_B64}\n---\n"
            "apiVersion: v1\nkind: ConfigMap\nmetadata: {name: reports-cfg}\n"
            "data:\n  DB_PASSWORD: pw-q1002-configmap\n"
            "  CACHE_URL: redis://:pw-q1002-cmurl@kafka:6379\n---\n"
            "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: reports}\n"
            "spec:\n  selector: {matchLabels: {app: reports}}\n"
            "  template:\n    metadata: {labels: {app: reports}}\n    spec:\n      containers:\n"
            "        - name: reports\n          image: quayside/reports:1\n"
            "          args: [\"--token=tok-q1002-k8s-args\"]\n"
            "          envFrom:\n            - configMapRef: {name: reports-cfg}\n"
            "          env:\n            - {name: API_TOKEN, value: tok-q1002-k8s-env}\n"
            "            - name: CACHE_URL\n"
            "              valueFrom: {configMapKeyRef: {name: reports-cfg, key: CACHE_URL}}\n"
            "---\n"
            "apiVersion: v1\nkind: Service\nmetadata:\n  name: reports\n"
            "  annotations: {deploy.token: tok-q1002-svc}\n"
            "spec:\n  selector: {app: reports}\n  ports: [{port: 80}]\n"),
        "infra/reports.tf": (
            'variable "reports_password" {\n  default = "pw-q1002-tfvar"\n}\n\n'
            'resource "aws_db_instance" "reports" {\n  password = "pw-q1002-tf"\n'
            '  identifier = "reports"\n  engine = "postgres"\n}\n'),
    },
    "quayside-billing": {
        "events/notifications.asyncapi.yaml": (
            "asyncapi: 2.6.0\ninfo: {title: notifications, version: 1.0.0}\n"
            "servers:\n  broker:\n    url: amqp://notify:pw-q1002-amqp@kafka:5672\n"
            "    protocol: amqp\n"
            "channels:\n  invoice.sent:\n"
            "    subscribe:\n      message:\n        name: InvoiceSent\n"
            "        payload: {type: object, properties: {token: {type: string, "
            "example: tok-q1002-asyncexample}}}\n"
            "    publish:\n      message: {name: InvoiceAcknowledged}\n"
            "    bindings:\n      amqp: {queue: {name: invoice-sent}}\n"),
        "api/receipts.openapi.yaml": (
            "openapi: 3.0.0\ninfo: {title: receipts, version: '1'}\n"
            "servers:\n  - url: https://svc:tok-q1002-oaserver@billing:8080\n"
            "paths:\n  /receipts:\n    get:\n      operationId: listReceipts\n"
            "      summary: the receipts\n"
            "      parameters:\n        - {name: key, in: query, schema: {type: string, "
            "default: pw-q1002-oadefault}}\n"
            "      responses:\n        '200':\n          description: ok\n"
            "          content: {application/json: {example: {token: tok-q1002-oaexample}}}\n"),
        "db/migration/V3__api_keys.sql": (
            "-- password: pw-q1002-sqlcomment\n"
            "CREATE TABLE api_keys (id bigint PRIMARY KEY, key text DEFAULT 'sk_live_q1002sql');\n"
            "INSERT INTO api_keys VALUES (1, 'sk_live_q1002insert');\n"),
        "docs/adr/0002-keys-are-rotated.md": (
            "# 2. Keys are rotated\n\nStatus: accepted\nDate: 2026-10-01\n\n"
            "The old key was pw-q1002-adr; it is rotated now.\n"),
    },
    "quayside-freight": {
        "proto/freight/v1/tokens.proto": (
            'syntax = "proto3";\npackage freight.v1;\n'
            'option (freight.v1.default_token) = "tok-q1002-proto";\n'
            "service Tokens {\n  rpc Issue (IssueRequest) returns (IssueReply);\n}\n"
            "message IssueRequest {}\nmessage IssueReply {}\n"),
    },
}

#: What a source's checkout leaves out: a directory of nothing but a picture.
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# ── the product ─────────────────────────────────────────────────────────────────────────────────

def _context(tmp: Path, *, sources: tuple[str, ...]) -> Path:
    """The context repository's seed: quayside's own, declaring `sources`."""
    seed = tmp / "seed-context"
    shutil.copytree(FIXTURE / "context", seed)
    manifest = seed / ".openfactory" / "product.yaml"
    declared = yaml.safe_load(manifest.read_text())
    declared["sources"] = list(sources)
    manifest.write_text(yaml.safe_dump(declared, sort_keys=False))
    shutil.rmtree(seed / ".okf" / "system", ignore_errors=True)
    return seed


@pytest.fixture
def product(tmp_path, monkeypatch):
    """Quayside on one machine, registered, with the planted files and a source nobody can check
    out. Returns `(project, remotes, tmp)`; the map is not published yet."""
    monkeypatch.setenv("OPENFACTORY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("OPENFACTORY_REPO_CACHE", str(tmp_path / "cache"))
    for var in ("OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_PRODUCT_TOKEN",
                "OPENFACTORY_PRODUCT_TOKENS", "OPENFACTORY_BOARD_TOKEN",
                "OPENFACTORY_BOARD_TOKENS"):
        monkeypatch.delenv(var, raising=False)
    remotes = {name: _remote(FIXTURE / "sources" / name, tmp_path / "work" / name,
                             tmp_path / "remotes" / f"{name}.git", extra=EXTRA.get(name),
                             weight={"assets/logo.png": _PNG} if name == "quayside-orders"
                             else None)
               for name in SOURCES}
    remotes["quayside-context"] = _remote(_context(tmp_path, sources=(*SOURCES, GONE)),
                                          tmp_path / "work" / "quayside-context",
                                          tmp_path / "remotes" / "quayside-context.git")
    monkeypatch.setattr("openfactory.adapters.forge.registry.clone_url_for",
                        lambda project, repo="", *, token=None:
                        remotes[repo].as_uri() if repo in remotes
                        else (tmp_path / "remotes" / f"{repo}.git").as_uri())
    return _register(NAME, tmp_path, docs="quayside-context"), remotes, tmp_path


def _register(name: str, tmp: Path, *, docs: str | None) -> Project:
    from openfactory.registry import ProjectRegistry

    local = {"kind": "local", "repo": "quayside-orders", "options": {}}
    ProjectRegistry().add(Project(
        name=name, repo_path=str(tmp / "work" / "quayside-orders"),
        tracker=ProviderRef(**local), forge=ProviderRef(**local),
        ci=ProviderRef(kind="none", repo="quayside-orders", options={}),
        product=ProductConfig(docs_repo=docs) if docs else None))
    return ProjectRegistry().get(name)


def _publish(project, tmp: Path) -> None:
    assert refresh.refresh_system(project, root=tmp / "cache") == refresh.PUBLISHED


@pytest.fixture
def client():
    from openfactory.api.app import app

    return TestClient(app)


def addresses() -> list[str]:
    """Every address the read is served at — found in `app.routes` by its handler."""
    from openfactory.api import app as panel

    found = sorted(r.path for r in panel.app.routes
                   if getattr(r, "endpoint", None) is panel.product_system)
    assert len(found) == 2, found
    return found


def _get(client, address: str, project: str = NAME, **kw):
    return client.get(address.replace("{project}", project), **kw)


def _published_files(remote: Path, into: Path) -> dict[str, dict]:
    """The YAML files of the map as the context repository holds them, read as a person would."""
    shutil.rmtree(into, ignore_errors=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(into)], check=True)
    where = into / refresh.system_subpath()
    return {name: yaml.safe_load((where / name).read_text()) for name in render.LAYOUT}


# ── the read model, walked ──────────────────────────────────────────────────────────────────────

def _inner(annotation) -> tuple[object, bool]:
    """`(the type a field holds, whether it holds a list of them)`, `None` left out."""
    args = [a for a in typing.get_args(annotation) if a is not type(None)] or [annotation]
    inner = args[0]
    if typing.get_origin(inner) is list:
        return typing.get_args(inner)[0], True
    return inner, False


def _model(t) -> bool:
    return isinstance(t, type) and issubclass(t, read_models.ReadModel)


def text_fields(model=read_models.SystemRead, prefix: str = "") -> list[str]:
    """Every field of the read that holds text — `a.b[].c` — walked from the model, never listed."""
    out = []
    for name, info in model.model_fields.items():
        inner, many = _inner(info.annotation)
        path = f"{prefix}{info.alias or name}{'[]' if many else ''}"
        if _model(inner):
            out += text_fields(inner, path + ".")
        elif inner is str:
            out.append(path)
    return out


def values_at(answer: object, path: str) -> list[object]:
    nodes = [answer]
    for step in path.split("."):
        key, many = step.removesuffix("[]"), step.endswith("[]")
        nxt = []
        for node in nodes:
            if isinstance(node, dict) and node.get(key) is not None:
                nxt += node[key] if many and isinstance(node[key], list) else [node[key]]
        nodes = nxt
    return nodes


def strings(node: object) -> list[str]:
    """Every string anywhere in an answer, keys included."""
    if isinstance(node, dict):
        return [s for k, v in node.items() for s in (k, *strings(v))]
    if isinstance(node, list):
        return [s for v in node for s in strings(v)]
    return [node] if isinstance(node, str) else []


def map_fields() -> list[str]:
    """The fields of the read that carry the map: every one `SystemMap` has, and the head."""
    return [*SystemMap.model_fields, "derived_key", "scope_limit"]


# ── 1. the map, whole and cited ─────────────────────────────────────────────────────────────────

def test_both_addresses_answer_the_published_map_whole(product, client):
    project, remotes, tmp = product
    _publish(project, tmp)
    files = _published_files(remotes["quayside-context"], tmp / "seen")
    for address in addresses():
        answer = _get(client, address)
        assert answer.status_code == 200, (address, answer.text)
        body = answer.json()
        assert (body["state"], body["why"]) == (render.PUBLISHED, ""), body["why"]
        assert body["project"] == NAME
        for name, parts in render.LAYOUT.items():
            for part in parts:
                assert body[part] == files[name][part], (address, part)
        head = files[render.SYSTEM_FILE]
        assert (body["version"], body["derived_key"], body["generated_at"]) == (
            head["version"], head["derived_key"], head["generated_at"])
        assert body["scope_limit"] == head["scope_limit"]
        context = _git(remotes["quayside-context"], "rev-parse", "main").strip()
        assert body["read_from"] == {"repo": "quayside-context", "path": ".okf/system",
                                     "commit": context, "line": 0}


def _cites(node: object) -> list[dict]:
    if isinstance(node, dict):
        own = [node] if {"repo", "path", "commit", "line"} <= set(node) else []
        return own + [c for v in node.values() for c in _cites(v)]
    if isinstance(node, list):
        return [c for v in node for c in _cites(v)]
    return []


def _holds_a_cite(model) -> bool:
    for info in model.model_fields.values():
        inner, _ = _inner(info.annotation)
        if inner is read_models.SystemCite or (_model(inner) and _holds_a_cite(inner)):
            return True
    return False


def test_every_entry_says_where_it_came_from_and_the_file_is_there(product, client):
    """An entry whose model holds a citation carries one naming a file that exists at the commit it
    cites; an entry whose model holds none — a source, a thing not derived — names its repository.
    Which is which is read from the model."""
    project, remotes, tmp = product
    _publish(project, tmp)
    body = _get(client, addresses()[0]).json()
    kinds = {name: inner for name, info in read_models.SystemRead.model_fields.items()
             for inner, many in [_inner(info.annotation)]
             if many and _model(inner) and name in SystemMap.model_fields}
    for name, inner in kinds.items():
        assert body[name], f"the fixture declares no {name}, so nothing here holds its entries"
        for entry in body[name]:
            if _holds_a_cite(inner):
                assert any(c["repo"] and c["path"] for c in _cites(entry)), (name, entry)
            else:
                assert entry["repo"], (name, entry)
    cites = _cites({k: body[k] for k in SystemMap.model_fields})
    for cite in cites:
        assert subprocess.run(["git", "-C", str(remotes[cite["repo"]]), "cat-file", "-e",
                               f"{cite['commit']}:{cite['path']}"],
                              capture_output=True).returncode == 0, cite


# ── 2. names only: the family rule ──────────────────────────────────────────────────────────────

def test_the_fixture_plants_every_kind_of_declaration_the_layer_reads(tmp_path):
    """The kinds are `_Declared`'s fields — what the readers fill — so a reader added tomorrow is
    a kind this fixture must plant before the rule below means anything for it."""
    from dataclasses import fields

    from openfactory.knowledge.system.tree import SourceTree

    into = derivation._Declared()
    for name in SOURCES:
        work = tmp_path / name
        shutil.copytree(FIXTURE / "sources" / name, work)
        for rel, text in EXTRA.get(name, {}).items():
            (work / rel).parent.mkdir(parents=True, exist_ok=True)
            (work / rel).write_text(text)
        derivation._read_source(SourceTree(repo=name, root=work, commit="c"), into)
    empty = [f.name for f in fields(into) if not getattr(into, f.name)]
    assert empty == [], f"no file of the fixture is read as {empty}"
    # …and each planted file is one of those kinds: it was read, not skipped
    planted = {(repo, rel) for repo, files in EXTRA.items() for rel in files if rel != ".env"}
    read = set()
    for kind in fields(into):
        for item in getattr(into, kind.name) if isinstance(getattr(into, kind.name), list) else ():
            parts = item if isinstance(item, tuple) else (item,)
            repo = next((p.repo for p in parts if hasattr(p, "repo")), "")
            read |= {(repo, p.path) for p in parts if hasattr(p, "path")}
            read |= {(repo, f) for p in parts for f in getattr(p, "files", ())}
    assert planted - read == set(), "planted files no reader took"


def _planted_breaks(name: str) -> list[str]:
    """`name` broken each way a file of the map can be, a planted value where it breaks — the
    last one anchored, so the loader's refusal, which the route quotes, is held to the rule too."""
    rest = "".join(f"{p}: []\n" for p in render.LAYOUT[name][1:])
    return [f"{PLANTED[0]}: [\n", f"- {PLANTED[0]}\n",
            f"version: '1'\n{render.LAYOUT[name][0]}: {{{PLANTED[0]}: 1}}\n{rest}",
            f"version: '1'\n{render.LAYOUT[name][0]}: [{{{PLANTED[1]}: {PLANTED[2]}}}]\n{rest}",
            f"version: '1'\n{render.LAYOUT[name][0]}: &a [{PLANTED[3]}]\n{rest}"]


def _answers(product, client) -> list[dict]:
    """The route's answer in each state it can be in, the planted values in reach of each: the map
    published from the planted sources, that map with a planted value where a file breaks, and no
    map at all — and, for every file of `LAYOUT` broken every way with a planted value where it
    breaks, the sentence the route answers as `why` (`render.read_published`'s, read on a copy of
    the published map, so the breaks cost no push each)."""
    project, remotes, tmp = product
    address = addresses()[0]
    out = []
    _publish(project, tmp)
    out.append(_get(client, address).json())
    assert out[-1]["state"] == render.PUBLISHED
    seen = tmp / "breaks"
    subprocess.run(["git", "clone", "-q", str(remotes["quayside-context"]), str(seen)],
                   check=True)
    where = seen / refresh.system_subpath()
    for name in render.LAYOUT:
        whole = (where / name).read_text()
        for broken in _planted_breaks(name):
            (where / name).write_text(broken)
            found = render.read_published(seen, refresh.system_subpath().as_posix())
            assert found.state == render.UNREADABLE, (name, broken, found)
            out.append({"state": found.state, "why": found.why})
        (where / name).write_text(whole)
    _push(remotes["quayside-context"], tmp, {render.API_FILE: _planted_breaks(render.API_FILE)[0]})
    out.append(_get(client, address).json())
    assert out[-1]["state"] == render.UNREADABLE, out[-1]
    _push(remotes["quayside-context"], tmp, {name: None for name in render.FILES})
    out.append(_get(client, address).json())
    assert out[-1]["state"] == render.NOT_PUBLISHED
    return out


def _push(remote: Path, tmp: Path, files: dict[str, str | None]) -> None:
    """Write (or, with None, remove) files of `.okf/system/` on the context repository's main."""
    clone = tmp / "edit-context"
    shutil.rmtree(clone, ignore_errors=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
    where = clone / refresh.system_subpath()
    for name, text in files.items():
        if text is None:
            (where / name).unlink(missing_ok=True)
        else:
            (where / name).write_text(text)
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "edit the map", "--allow-empty")
    _git(clone, "push", "-q", "origin", "main")


def test_no_value_of_a_variable_crosses_the_api_only_names(product, client):
    """THE FAMILY RULE: in every state the route answers, every field it returns — every text field
    of the read model, each one filled at least once across the states — holds none of the values
    planted in every kind of declaration; and the raw body holds none of them either."""
    answers = _answers(product, client)
    unfilled = [path for path in text_fields()
                if not any(v not in ("", None) for a in answers for v in values_at(a, path))]
    assert unfilled == [], f"fields no answer filled, so nothing here proves them: {unfilled}"
    for answer in answers:
        raw = json.dumps(answer, ensure_ascii=False)
        for value in (*PLANTED, base64.b64decode(_B64).decode()):
            assert value not in raw, value
            assert all(value not in s for s in strings(answer)), value
    published = answers[0]
    names = {e for c in published["components"] for e in c["env"]}
    assert set(NAMES) <= names, "the variables' names did not cross"
    assert {"env REPORTS_DATABASE_URL"} <= {lk["via"] for lk in published["links"]}


# ── 3. never an empty map for one that is not known ─────────────────────────────────────────────

def test_a_source_that_cannot_be_checked_out_is_a_source_unreadable_entry(product, client):
    project, remotes, tmp = product
    shutil.rmtree(remotes["quayside-freight"])
    _publish(project, tmp)
    body = _get(client, addresses()[0]).json()
    assert body["state"] == render.PUBLISHED
    unread = {n["repo"] for n in body["not_derived"] if n["kind"] == SOURCE_UNREADABLE}
    assert unread == {"quayside-freight", GONE}
    assert {s["repo"] for s in body["sources"] if s["missing"]} == unread


def test_a_product_none_of_whose_sources_can_be_read_is_still_not_an_empty_map(product, client):
    project, remotes, tmp = product
    for name in SOURCES:
        shutil.rmtree(remotes[name])
    _publish(project, tmp)
    body = _get(client, addresses()[0]).json()
    assert body["state"] == render.PUBLISHED
    assert {n["repo"] for n in body["not_derived"] if n["kind"] == SOURCE_UNREADABLE} == {
        *SOURCES, GONE}
    assert all(s["missing"] for s in body["sources"]) and len(body["sources"]) == 5


def _nothing_of_the_map(body: dict) -> None:
    assert body["why"], body
    for field in map_fields():
        assert body.get(field) is None, (field, body.get(field))


def test_no_map_published_yet_says_so_and_answers_no_map(product, client):
    body = _get(client, addresses()[0]).json()
    assert body["state"] == render.NOT_PUBLISHED
    assert "no system map is published" in body["why"]
    _nothing_of_the_map(body)


def _quayside(tmp: Path) -> SystemMap:
    """The quayside map, derived from the fixture's trees as they are — no git, no refresh."""
    trees = []
    for name in SOURCES:
        shutil.copytree(FIXTURE / "sources" / name, tmp / name)
        trees.append(derivation.SourceTree(repo=name, root=tmp / name, commit="c0ffee"))
    return derivation.derive(trees, missing={GONE: "not found"},
                             generated_at="2026-10-21T00:00:00+00:00")


#: Every way a file of a published map can fail to be read, each named by what it does.
_BROKEN = {
    "gone": None,
    "not YAML": "{part}: [\n",
    "not a mapping": "- a list\n",
    "a part missing": "version: '1'\n",
    "not the map's shape": "{part}: [{{name: 7}}]\n",
}


@pytest.mark.parametrize("how", sorted(_BROKEN))
@pytest.mark.parametrize("name", sorted(render.LAYOUT))
def test_a_published_map_one_file_of_which_cannot_be_read_is_answered_as_none_of_it(
        tmp_path, name, how):
    """Each file `LAYOUT` names, broken each way: the read answers why, naming the file, and no
    part of the map — never the rest of it with that file's parts silently empty."""
    render.write_system(_quayside(tmp_path), tmp_path / "ctx" / ".okf" / "system")
    text = _BROKEN[how]
    if text is not None:
        text = text.format(part=render.LAYOUT[name][0])
        if how == "not the map's shape":
            text += "".join(f"{p}: []\n" for p in render.LAYOUT[name][1:])
    target = tmp_path / "ctx" / ".okf" / "system" / name
    target.unlink() if text is None else target.write_text(text)
    found = render.read_published(tmp_path / "ctx", ".okf/system")
    assert found.system is None and found.derived_key == ""
    if how == "gone" and name == render.SYSTEM_FILE:
        assert found.state == render.NOT_PUBLISHED, found
    else:
        assert found.state == render.UNREADABLE, found
        assert f"`{name}`" in found.why, found.why


def test_an_unreadable_map_is_answered_with_no_field_of_it(product, client):
    project, remotes, tmp = product
    _publish(project, tmp)
    _push(remotes["quayside-context"], tmp, {render.API_FILE: "http: [\n"})
    body = _get(client, addresses()[0]).json()
    assert body["state"] == render.UNREADABLE and "`api.yaml` is not YAML" in body["why"], body
    _nothing_of_the_map(body)


# ── a published part with anchors or aliases, or nested past the bound ──────────────────────────
#
# The map is the core's own file: `render._dump` writes no anchor and no alias, so a part that
# holds one was not written by the refresh. It is read with the loader of the core's own files
# (`yaml_io.Loader`), which refuses it by name before anything is built from it — not with the
# counting loader `text.load_yaml` keeps for the formats the layer derives from, which reads an
# alias and counts it as one value however long the value it repeats: a long value aliased many
# times is a few kilobytes of text and megabytes of answer (on review, a 29 KB `system.yaml`
# answered ~120 MB in ~3.4 s).

def _aliased(name: str) -> str:
    """`name` holding no entries, every part after the first an alias of the first — read with its
    aliases, a well-formed part of a map that declares nothing."""
    first, *rest = render.LAYOUT[name]
    return f"version: '1'\n{first}: &none []\n" + "".join(f"{p}: *none\n" for p in rest)


#: How long the value `_repeated` anchors is, and how many times it aliases it.
_LONG, _TIMES = 2_000, 2_000


def _repeated() -> str:
    """`system.yaml` whose one source leaves out one long name, aliased `_TIMES` times: about
    16 KB of text, the map's own shape, and `_LONG * _TIMES` characters once its aliases are read."""
    rest = "".join(f"{p}: []\n" for p in render.LAYOUT[render.SYSTEM_FILE][1:])
    return (f"version: '1'\nsources:\n- repo: quayside-orders\n  left_out: [&long {'x' * _LONG}, "
            + ", ".join(["*long"] * _TIMES) + f"]\n{rest}")


#: How a published `system.yaml` is refused: the word for it → its text.
_REFUSED = {
    "an anchor and its aliases": _aliased(render.SYSTEM_FILE),
    "a long value aliased many times": _repeated(),
    "nested past the bound": "version: '1'\nsources: " + "[" * 150 + "]" * 150 + "\n",
}


def _refusal(text: str) -> str:
    """The sentence the loader of the core's own files refuses `text` with, read from the loader."""
    with pytest.raises(yaml_io.YamlRefused) as refused:
        yaml_io.load(text)
    return str(refused.value)


def test_the_refused_texts_are_refused_for_what_they_are_named_and_the_aliased_ones_are_maps():
    """What each text is refused for, and why it matters: read with their aliases, both aliased
    texts are well-formed for the map's models — the first a map that declares nothing, the second
    one that answers megabytes — and the counting loader reads both."""
    assert _refusal(_REFUSED["an anchor and its aliases"]).startswith("an anchor (`&none`, line 2)")
    assert _refusal(_REFUSED["a long value aliased many times"]).startswith(
        "an anchor (`&long`, line 4)")
    assert _refusal(_REFUSED["nested past the bound"]).startswith(
        f"nested deeper than {yaml_io.MAX_DEPTH} levels")
    parts = render.LAYOUT[render.SYSTEM_FILE]
    empty = yaml_io.load(_REFUSED["an anchor and its aliases"], loader=yaml_io.CountingLoader)
    assert {p: empty[p] for p in parts} == dict.fromkeys(parts, [])
    text = _REFUSED["a long value aliased many times"]
    long = yaml_io.load(text, loader=yaml_io.CountingLoader)
    read = SystemMap(**{p: long[p] for p in parts})
    assert len(text.encode()) < 20_000
    assert len(read.model_dump_json()) > _LONG * _TIMES


@pytest.mark.alone  # it times the read in processor time, which neighbours on its cores inflate
@pytest.mark.parametrize("name", sorted(render.LAYOUT))
def test_each_file_of_the_map_with_an_anchor_is_unreadable_and_says_the_loader_s_sentence(
        tmp_path, name):
    render.write_system(_quayside(tmp_path), tmp_path / "ctx" / ".okf" / "system")
    (tmp_path / "ctx" / ".okf" / "system" / name).write_text(_aliased(name))
    started = os.times()
    found = render.read_published(tmp_path / "ctx", ".okf/system")
    assert _processor_seconds(started) < 1.0
    assert found.state == render.UNREADABLE and found.system is None, found
    assert found.why == (f"the system map at `.okf/system` cannot be read: `{name}` is refused — "
                         f"{_refusal(_aliased(name))}")


@pytest.mark.alone
def test_a_published_part_with_anchors_or_aliases_or_too_deep_is_unreadable_fast_on_both_addresses(
        product, client, monkeypatch):
    """Each refused `system.yaml` pushed to the context repository, then read through both
    addresses: `unreadable`, the loader's own sentence in `why`, nothing of the map, an answer of a
    few hundred bytes — and the route's read of the published files in under a second of processor
    time (the checkout's fetch before it is not what is timed). The processor time, never the clock
    on the wall, which a busy machine stretches over the same work; and so the test runs `alone`."""
    project, remotes, tmp = product
    _publish(project, tmp)
    took: list[float] = []
    real = render.read_published

    def timed(*args, **kwargs):
        started = os.times()
        try:
            return real(*args, **kwargs)
        finally:
            took.append(_processor_seconds(started))

    monkeypatch.setattr(render, "read_published", timed)
    where = refresh.system_subpath().as_posix()
    for how, text in _REFUSED.items():
        _push(remotes["quayside-context"], tmp, {render.SYSTEM_FILE: text})
        for address in addresses():
            answered = _get(client, address)
            assert len(took) == 1 and took.pop() < 1.0, (how, address, took)
            assert len(answered.content) < 2_000, (how, address, len(answered.content))
            body = answered.json()
            assert body["state"] == render.UNREADABLE, (how, address, body)
            assert body["why"] == (f"the system map at `{where}` cannot be read: "
                                   f"`{render.SYSTEM_FILE}` is refused — {_refusal(text)}"), (
                how, address, body["why"])
            _nothing_of_the_map(body)


def test_a_published_file_that_is_a_link_is_not_followed(product, client):
    project, remotes, tmp = product
    _publish(project, tmp)
    clone = tmp / "link-context"
    subprocess.run(["git", "clone", "-q", str(remotes["quayside-context"]), str(clone)],
                   check=True)
    where = clone / refresh.system_subpath()
    (where / render.API_FILE).unlink()
    (where / render.API_FILE).symlink_to("/etc/hosts")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "a link")
    _git(clone, "push", "-q", "origin", "main")
    body = _get(client, addresses()[0]).json()
    assert body["state"] == render.UNREADABLE and "link" in body["why"], body
    _nothing_of_the_map(body)


def test_a_context_repository_that_cannot_be_reached_is_unreadable_never_empty(
        product, client):
    project, remotes, tmp = product
    _publish(project, tmp)
    shutil.rmtree(tmp / "cache")
    shutil.rmtree(remotes["quayside-context"])
    body = _get(client, addresses()[0]).json()
    assert body["state"] == render.UNREADABLE
    assert "context repository" in body["why"]
    assert body["read_from"] is None
    _nothing_of_the_map(body)


# ── 4. the read model describes the map; the layout places it; nothing beside it crosses ───────

def _pairs(contract, model, path: str = "") -> list[tuple[str, set, set]]:
    """`(where, the map's field names, the read model's)` at every depth, walked side by side."""
    theirs = {info.alias or name: info for name, info in contract.model_fields.items()}
    ours = {info.alias or name: info for name, info in model.model_fields.items()}
    out = [(path or model.__name__, set(theirs), set(ours))]
    for key in set(theirs) & set(ours):
        inner, _ = _inner(theirs[key].annotation)
        mine, _ = _inner(ours[key].annotation)
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            assert _model(mine), (path, key)
            out += _pairs(inner, mine, f"{path}{key}.")
    return out


def test_the_read_model_describes_every_field_the_map_carries_at_every_depth():
    route_own = {"project", "product", "state", "why", "read_from", "derived_key", "scope_limit"}
    [(top, theirs, ours), *nested] = _pairs(SystemMap, read_models.SystemRead)
    assert ours - theirs == route_own, top
    assert theirs - ours == set(), top
    for where, theirs, ours in nested:
        assert theirs == ours, where
    assert len(nested) >= 15


def test_every_part_of_the_map_is_in_exactly_one_file_and_reads_back_as_written(tmp_path):
    parts = [p for parts in render.LAYOUT.values() for p in parts]
    assert sorted(parts) == sorted(set(SystemMap.model_fields) - set(render.HEAD))
    system = _quayside(tmp_path)
    render.write_system(system, tmp_path / "ctx" / ".okf" / "system")
    found = render.read_published(tmp_path / "ctx", ".okf/system")
    assert found.state == render.PUBLISHED and found.system == system
    assert found.derived_key == render.derived_key(system)


def test_what_a_hand_adds_beside_the_map_s_fields_is_never_answered(product, client):
    project, remotes, tmp = product
    _publish(project, tmp)
    files = _published_files(remotes["quayside-context"], tmp / "seen")
    head = files[render.SYSTEM_FILE]
    head["password"] = "pw-q1002-beside-top"
    head["components"][0]["password"] = "pw-q1002-beside-entry"
    head["components"][0]["declared_by"][0]["token"] = "pw-q1002-beside-cite"
    files[render.API_FILE]["http"][0]["operations"][0]["example"] = "pw-q1002-beside-op"
    _push(remotes["quayside-context"], tmp, {
        name: yaml.safe_dump(data) for name, data in files.items()})
    body = _get(client, addresses()[0]).json()
    assert body["state"] == render.PUBLISHED
    raw = json.dumps(body)
    for planted in ("beside-top", "beside-entry", "beside-cite", "beside-op"):
        assert planted not in raw, planted


# ── 5. the gate, read-only ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def gated(product, monkeypatch):
    monkeypatch.setenv("OPENFACTORY_PANEL_TOKEN", "the-operator")
    monkeypatch.setenv("OPENFACTORY_PRODUCT_TOKENS", "the-analyst:bia")
    from openfactory.api.app import app

    return product, TestClient(app)


def test_on_both_addresses_the_gate_admits_the_product_area_and_refuses_no_credential(gated):
    (project, _remotes, tmp), client = gated
    _publish(project, tmp)
    for address in addresses():
        assert _get(client, address).status_code == 401, address
        for credential in ("the-analyst", "the-operator"):
            answer = _get(client, address, headers={"Authorization": f"Bearer {credential}"})
            assert answer.status_code == 200, (address, credential, answer.text)
            assert answer.json()["state"] == render.PUBLISHED


def _listing(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) if root.exists() else []


def test_a_project_with_no_product_role_is_the_unknown_project_s_404_and_checks_out_nothing(
        gated):
    (_project, _remotes, tmp), client = gated
    _register("plainproject", tmp, docs=None)
    analyst = {"Authorization": "Bearer the-analyst"}
    before = _listing(tmp / "cache")
    for address in addresses():
        unknown = _get(client, address, "nobody-registered", headers=analyst)
        plain = _get(client, address, "plainproject", headers=analyst)
        assert unknown.status_code == plain.status_code == 404
        assert plain.content == unknown.content.replace(b"nobody-registered", b"plainproject")
    assert _listing(tmp / "cache") == before


def test_the_description_names_the_read_s_body_and_its_404_on_both_addresses(monkeypatch):
    from openfactory.api.app import app

    monkeypatch.delenv("OPENFACTORY_PANEL_TOKEN", raising=False)
    described = TestClient(app).get("/openapi.json").json()
    for address in addresses():
        responses = described["paths"][address]["get"]["responses"]
        assert responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
            "/SystemRead"), address
        assert responses["404"]["content"]["application/json"]["schema"]["$ref"].endswith(
            "/Refusal"), address
    assert "deprecated" not in described["paths"][addresses()[1]]["get"]
    assert described["paths"][addresses()[0]]["get"]["deprecated"] is True


def test_a_read_pushes_nothing_and_files_no_impediment(product, client, monkeypatch):
    project, remotes, tmp = product
    _publish(project, tmp)
    told = []
    monkeypatch.setattr("openfactory.ops.impediment.report", lambda *a, **k: told.append(a))
    monkeypatch.setattr("openfactory.ops.impediment.resolved", lambda *a, **k: told.append(a))
    tips = {name: _git(remote, "for-each-ref").strip() for name, remote in remotes.items()}
    for address in addresses():
        assert _get(client, address).json()["state"] == render.PUBLISHED
    assert {name: _git(remote, "for-each-ref").strip() for name, remote in remotes.items()} \
        == tips
    assert told == []


# ── 6. the panel draws the map ──────────────────────────────────────────────────────────────────

def escape(text: str) -> str:
    """The page's own `esc`, spelled out: what a text becomes once the page writes it."""
    return "".join({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}.get(c, c)
                   for c in str(text))


def _drawn(answer: object, *, failed: str = "") -> str:
    """The product page's System pane, painted under node from `answer` — or from a read that
    failed with `failed`."""
    from tests.test_the_panel_is_a_chat import _run

    state = f"let _prod={{project:'quayside'}};_pv.system={json.dumps(answer)};" \
            f"_pv.systemMsg={json.dumps(failed)};"
    return _run("nodes['#pvSystem']=node();pvSystemPaint();return nodes['#pvSystem'].innerHTML",
                pathname="/product/quayside", board=state)


def test_the_product_page_draws_the_map_the_api_answers_what_could_not_be_derived_first(
        product, client):
    """THE TWO ENDS JOINED: the answer painted is the one the real route gives."""
    project, _remotes, tmp = product
    _publish(project, tmp)
    answer = _get(client, addresses()[0]).json()
    drawn = _drawn(answer)
    assert drawn.index("What could not be derived") < drawn.index("Components")
    for entry in answer["not_derived"]:
        assert escape(entry["detail"]) in drawn, entry
    for component in answer["components"]:
        assert escape(component["name"]) in drawn
        for cite in component["declared_by"]:
            assert escape(f"{cite['repo']} · {cite['path']}") in drawn, cite
    for api in answer["http"]:
        for op in api["operations"]:
            assert escape(f"{op['method']} {op['path']}") in drawn, op
    for database in answer["databases"]:
        assert escape(database["name"]) in drawn
    assert escape(answer["scope_limit"]) in drawn


def test_nothing_a_repository_declares_becomes_html_on_the_page():
    hostile = "<img src=x onerror=alert(1)>"
    cite = {"repo": hostile, "path": hostile, "commit": hostile, "line": 3}
    answer = {"state": "published", "why": "", "scope_limit": hostile,
              "not_derived": [{"kind": hostile, "detail": hostile, "repo": hostile, "path": ""}],
              "sources": [{"repo": hostile, "commit": "c", "files": 1, "left_out": [hostile],
                           "missing": ""}],
              "components": [{"name": hostile, "kind": hostile, "env": [hostile],
                              "declared_by": [cite]}],
              "links": [{"from": hostile, "to": hostile, "kind": hostile, "via": hostile}],
              "http": [{"component": hostile, "title": hostile, "version": hostile,
                        "operations": [{"method": hostile, "path": hostile, "summary": hostile}],
                        "callers": [hostile], "source": cite}],
              "grpc": [{"component": hostile, "service": hostile, "rpcs": [{"name": hostile}],
                        "source": cite}],
              "events": [{"channel": hostile, "producers": [{"component": hostile,
                                                             "source": cite}]}],
              "databases": [{"name": hostile, "owners": [hostile], "users": [hostile],
                             "tables": [{"name": hostile}], "migrations": [cite]}],
              "queues": [{"name": hostile, "kind": hostile, "source": cite}],
              "infrastructure": [{"address": hostile, "kind": hostile, "source": cite}],
              "adrs": [{"title": hostile, "status": hostile, "source": cite}]}
    drawn = _drawn(answer)
    assert "<img" not in drawn and "&lt;img" in drawn


@pytest.mark.parametrize("answer, failed, said", [
    ({"state": "not-published", "why": "no system map is published yet"}, "",
     "no system map is published yet"),
    ({"state": "unreadable", "why": "`api.yaml` is not YAML"}, "", "`api.yaml` is not YAML"),
    (None, "the read was refused", "the read was refused"),
])
def test_a_map_that_is_not_there_is_said_never_drawn_empty(answer, failed, said):
    drawn = _drawn(answer, failed=failed)
    assert escape(said) in drawn and "Components" not in drawn


def test_opening_the_system_tab_reads_the_map_and_nothing_reads_it_on_a_clock():
    from tests.test_the_panel_is_a_chat import _function, _run

    got = _run("nodes['#pvSystem']=node();pvTab('system');await new Promise(r=>setTimeout(r,0));"
               "return {asked,drawn:nodes['#pvSystem'].innerHTML}",
               pathname="/product/quayside",
               board="let _prod={project:'quay side'};const asked=[];"
                     "function api(u){asked.push(u);"
                     "return Promise.resolve({state:'not-published',why:'not yet'})}")
    assert got["asked"] == ["/api/product/quay%20side/system"]
    assert "not yet" in got["drawn"]
    for name in ("pvSystemLoad", "pvSystemPaint"):
        assert "setInterval" not in _function(name) and "setTimeout" not in _function(name)
