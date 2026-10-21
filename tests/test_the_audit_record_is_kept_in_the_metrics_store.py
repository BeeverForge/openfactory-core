"""The record of each call into the action layer is kept in the deployment's metrics store, under a
kind of its own, one row per call, with nothing secret in the file (#694).

WHAT WAS TRUE BEFORE. `actions.perform` left nothing durable: its one trace of who asked was an INFO
line, and on a sqlite deployment (`OPENFACTORY_METRICS_SINK=sqlite`, what the compose file sets on
the worker and the panel) the store held 0 rows of kind `audit` after any call — `audit` was not a
`MetricKind` at all. Measured on bb929e49 with an empty `HOME`: `openfactory act product_status -p
nosuch` printed the refusal and kept nothing an auditor could read back.

WHAT HOLDS NOW, in this file, read off the sqlite file itself rather than a mock: a call leaves one
row of kind `audit` under its project; two records made in the same instant are two rows (the
store's `INSERT OR REPLACE` on `<ts>#<ticket>#<role>` would otherwise keep one); a password passed
to the action is masked in the row and its bytes are in neither the database nor its `-wal`; and
the INFO line is still written, once per call, beside the row; and a row is read for
`audit.AUDIT_KEPT_DAYS` and not a day longer, the period stated with its value on the page that
states every other retention. Append-only on the store's own terms: a row's key carries its
record's own id, and nothing in `openfactory/` but `audit.write` makes or writes an audit row,
nor forgets one — read off the parsed tree, never its text. `project forget` keeps a project's
records (Q8) and may: a person's words are in a record only as their length and sha256 — for the
one call driven here and for every free-text parameter the catalog takes — so the record is no
second copy of what `forget-conversations` erases. A store that does not take a record is said
at WARNING naming the action and the store, and the caller's outcome is unchanged; the record is
made and written off the event loop, and a cancel while it is made still leaves it. Records of a
call that named no project share the people store's `_deployment_` key and do not crowd a
registered person out of its read (Q7). A host CLI with no store named keeps its records in
`audit.db` beside `registry.yaml`, and the deployment's own metrics sink is still inferred `null`
there. The cost dashboard, which reads the whole store, lists no project an audit row alone is
under and opens on the same project, spend and autonomy block it showed before the rows landed.
"""

from __future__ import annotations

import ast
import dataclasses
import functools
from datetime import UTC, datetime
from pathlib import Path

import pytest

from openfactory import actions
from openfactory.observability.sqlite_metrics import SqliteMetricsSink


@pytest.fixture
def store(tmp_path, monkeypatch) -> SqliteMetricsSink:
    """A sqlite deployment, named as an operator names one: `OPENFACTORY_METRICS_SINK=sqlite` and
    the file in `OPENFACTORY_METRICS_DB`, with a registry of its own. The sink returned is a second
    handle on the same file — what the test reads is what `perform` wrote there, not a copy."""
    db = tmp_path / "metrics.db"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(db))
    return SqliteMetricsSink(db)


def _audit_rows(store: SqliteMetricsSink) -> list[dict]:
    """Every live row of kind `audit` in the file, whichever key it is under."""
    return [row for row in store.scan() if row.get("kind") == "audit"]


async def test_an_action_on_a_sqlite_deployment_leaves_a_row_of_kind_audit(store):
    """Criterion 3, "the local default sink writes audit records to the metrics store under their
    own kind": one real `perform` — a person asking for the status of a project nobody registered,
    refused by the row — leaves one row of kind `audit` under that project, saying who asked and
    what they were told. Before #694 the file held 0 such rows."""
    by = actions.Actor(id="alice", display="Alice Ferreira", via="panel")

    outcome = await actions.perform("product_status", by=by, project="nosuch")

    assert not outcome.ok and outcome.data.get("reason") == actions.NOT_FOUND, outcome
    rows = store.records_of_kind("nosuch", "audit")
    assert len(rows) == 1, f"{len(rows)} rows of kind audit for one call (1 expected)"
    [row] = rows
    assert (row["extra"]["action"], row["extra"]["actor_id"], row["extra"]["ok"],
            row["extra"]["reason"]) == ("product_status", "alice", False, actions.NOT_FOUND), row


async def test_two_records_in_the_same_instant_are_both_kept(store, monkeypatch):
    """Criterion 3, "append-only": the sqlite sink writes `INSERT OR REPLACE` on `sk =
    <ts>#<ticket>#<role|kind>` (`sqlite_metrics.py`), so two records that shared a time and a key
    would leave one row and lose the other without a word. With the clock stopped, two calls of the
    same action by the same person are two rows, at one `ts`."""
    from openfactory.observability import events

    instant = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)

    class _Stopped(datetime):
        @classmethod
        def now(cls, tz=None):  # every `now_iso()` reads this one instant
            return instant

    monkeypatch.setattr(events, "datetime", _Stopped)
    by = actions.Actor(id="alice", via="panel")

    for _ in range(2):
        await actions.perform("product_status", by=by, project="nosuch")

    rows = store.records_of_kind("nosuch", "audit")
    assert len(rows) == 2, f"{len(rows)} rows for two calls in one instant (2 expected)"
    assert {row["ts"] for row in rows} == {instant.isoformat()}, rows  # the clock did stop


async def test_a_password_reaches_neither_the_record_nor_the_store_file(store):
    """Criterion 6, "secrets are redacted in the record as they are in the line": `approve_prod`
    takes the approver's password, and a refused call — the path a wrong password takes — is still
    recorded. The row says a password was given (`***`), and the password's bytes are nowhere in
    the database file or its write-ahead log, where an uncheckpointed row lives. Before #694 there
    was no row, so nothing here could be read back at all."""
    secret = "hunter2"

    await actions.perform("approve_prod", by=actions.SYSTEM, project="nosuch", issue="1",
                          version="1.0.0", approver="alice", password=secret)

    rows = store.records_of_kind("nosuch", "audit")
    assert [row["extra"]["action"] for row in rows] == ["approve_prod"], rows
    assert rows[0]["extra"]["params"]["password"] == "***", rows[0]["extra"]["params"]
    files = [p for p in (store.path, store.path.with_name(store.path.name + "-wal")) if p.exists()]
    assert store.path in files, files
    leaked = [p.name for p in files if secret.encode() in p.read_bytes()]
    assert not leaked, f"the password is in {leaked}"


async def test_the_info_line_is_still_written_beside_the_record(store, caplog):
    """Criterion 6, "the INFO log line stays": the record does not replace the line. Each call —
    an unknown action, and a row's refusal — writes exactly one `action=<name> by=` line at INFO
    and leaves exactly one row of kind `audit`. Before #694 the unknown action wrote no line, and
    neither call left a row."""
    by = actions.Actor(id="alice", via="panel")
    calls = [("teleport", {}), ("product_status", {"project": "nosuch"})]

    with caplog.at_level("INFO", logger="openfactory.actions"):
        for name, params in calls:
            await actions.perform(name, by=by, **params)

    lines = [r.getMessage() for r in caplog.records
             if r.levelname == "INFO" and r.getMessage().startswith("action=")]
    assert [line.split()[0] for line in lines] == [f"action={name}" for name, _ in calls], lines
    assert all(" by=" in line for line in lines), lines
    rows = _audit_rows(store)
    assert sorted(row["extra"]["action"] for row in rows) == sorted(n for n, _ in calls), rows


# ── how long a record is kept, and where that is said ───────────────────────────────────────────

_DAY = 24 * 60 * 60


async def test_a_record_is_still_read_the_day_before_its_period_ends_and_not_after(store,
                                                                                    monkeypatch):
    """Criterion 3, "they survive the store's retention rules for a documented period": a record
    written at a known instant is read back on the last day of `audit.AUDIT_KEPT_DAYS` and is
    gone the day after; a purge run on that last day deletes none of it. The store honours a row's
    `expires_at` on every read (`sqlite_metrics.py`), so the period is the one the record carries.
    Before #694 there was no period at all: `AUDIT_KEPT_DAYS` did not exist, and the store held no
    row of kind `audit` to keep or to expire."""
    from openfactory.observability import events, sqlite_metrics
    from openfactory.observability.audit import AUDIT_KEPT_DAYS

    instant = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)

    class _Stopped(datetime):
        @classmethod
        def now(cls, tz=None):  # the record's `ts` is this instant
            return instant

    monkeypatch.setattr(events, "datetime", _Stopped)
    await actions.perform("product_status", by=actions.Actor(id="alice", via="panel"),
                          project="nosuch")
    written = int(instant.timestamp())
    last_day = written + AUDIT_KEPT_DAYS * _DAY - _DAY
    day_after = written + AUDIT_KEPT_DAYS * _DAY + _DAY

    monkeypatch.setattr(sqlite_metrics.time, "time", lambda: last_day)
    assert len(store.records_of_kind("nosuch", "audit")) == 1, (
        f"a record written {AUDIT_KEPT_DAYS - 1} days ago is no longer read "
        f"(its period is {AUDIT_KEPT_DAYS} days)")
    assert store.purge_expired(now=last_day) == 0, (
        "a purge on the last day of the period deleted a record still inside it")

    monkeypatch.setattr(sqlite_metrics.time, "time", lambda: day_after)
    assert store.records_of_kind("nosuch", "audit") == [], (
        f"a record written {AUDIT_KEPT_DAYS + 1} days ago is still read "
        f"(its period is {AUDIT_KEPT_DAYS} days)")


def test_the_period_is_stated_where_the_other_retentions_are():
    """Criterion 3, "a documented period": `docs/rotation-and-retention.md` is the page that says
    how long everything this tree keeps is kept, and a person asking how long the record of who
    did what lasts must find `AUDIT_KEPT_DAYS` there with its value. Before #694 the page named no
    audit record, and the constant did not exist."""
    from pathlib import Path

    from openfactory.observability.audit import AUDIT_KEPT_DAYS

    doc = Path(__file__).resolve().parents[1] / "docs" / "rotation-and-retention.md"
    lines = doc.read_text(encoding="utf-8").splitlines()

    # THE CONSTANT AND ITS VALUE ON ONE LINE, as the conversation's retention is guarded
    # (`test_a_staged_decision_survives_a_refresh.py`): checked apart, the name in the "where it
    # lives" list and the number anywhere else on the page would pass while the period read "a
    # while".
    assert any("AUDIT_KEPT_DAYS" in ln and str(AUDIT_KEPT_DAYS) in ln for ln in lines), (
        f"AUDIT_KEPT_DAYS is not documented with its value ({AUDIT_KEPT_DAYS}) in {doc.name}")


def test_an_audit_rows_key_is_its_own_record_id():
    """Criterion 3, "append-only", on the store's own terms: every sink keys a row by
    `MetricRecord.dynamo_key()`'s `sk = <ts>#<ticket>#<role|kind>`, and both the sqlite sink
    (`INSERT OR REPLACE`) and a DynamoDB `put_item` replace a row whose key they meet again. An
    audit row's `ticket` is its record's own id, so its key is `<ts>#<record_id>#<action>` and no
    other record, made in the same instant by the same person for the same action, shares it.
    Before #694 there was no audit row and so no key; keyed by the action instead, two calls in one
    instant would share one row."""
    from openfactory.observability.audit import AuditRecord, metric_of

    by = actions.Actor(id="alice", via="panel")
    outcome = actions.done("ok")
    first = AuditRecord.of("product_status", by, {"project": "x"}, outcome)
    second = dataclasses.replace(first, record_id=AuditRecord.of(
        "product_status", by, {"project": "x"}, outcome).record_id)

    keys = [metric_of(r).dynamo_key()["sk"] for r in (first, second)]

    assert keys[0] == f"{first.ts}#{first.record_id}#product_status", keys[0]
    assert keys[0] != keys[1], f"two records of one instant share the key {keys[0]}"


# ── nothing in the tree rewrites an audit row ───────────────────────────────────────────────────
#
# Read off the parsed source of `openfactory/`, never its text: a comment that explains the rule
# beside its code ("never .forget(kind='audit')") would satisfy a text search (CONTRIBUTING, six
# dated incidents). A `kind` given by name is resolved to its value — through the module's own
# constants, an imported constant, or the literal a loop walks — so a constant named anything
# that holds "audit" is caught; a `kind` the walk cannot resolve fails as unseen, never passes as
# "not audit".

_TREE = Path(__file__).resolve().parents[1] / "openfactory"
_UNSEEN = object()


def _module_of(path: Path) -> str:
    return ".".join(path.relative_to(_TREE.parent).with_suffix("").parts).removesuffix(".__init__")


@functools.cache
def _parsed() -> dict[str, ast.Module]:
    """Every module of `openfactory/`, parsed once, when the guard runs (not at collection)."""
    return {_module_of(p): ast.parse(p.read_text(encoding="utf-8"))
            for p in sorted(_TREE.rglob("*.py"))}


@functools.cache
def _constants(module: str) -> dict[str, object]:
    """The module-level names `module` binds to a literal, and what it imports by name."""
    out: dict[str, object] = {}
    for node in _parsed().get(module, ast.Module(body=[])).body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) and node.value else [])
        for t in targets:
            if isinstance(t, ast.Name):
                try:
                    out[t.id] = ast.literal_eval(node.value)
                except ValueError:
                    out[t.id] = _UNSEEN
    # IMPORTS ANYWHERE IN THE MODULE, not only at its top: this tree imports inside the function
    # that needs a name (`forget.py` reads `LEDGER_KIND` that way), and a constant imported there
    # is as much the `kind` as one imported above.
    for node in ast.walk(_parsed().get(module, ast.Module(body=[]))):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out.setdefault(alias.asname or alias.name, ("import", node.module, alias.name))
        if isinstance(node, ast.Import):  # `import a.b as m`: `m.NAME` is read in `a.b`
            for alias in node.names:
                if alias.asname:
                    out.setdefault(alias.asname, ("module", alias.name, ""))
    return out


def _bound(expr: ast.expr, module: str) -> object:
    """The literal `expr` names — a constant, a module's constant, an imported one — or
    `_UNSEEN`."""
    if isinstance(expr, ast.Constant):
        return expr.value
    name, where = ((expr.id, module) if isinstance(expr, ast.Name)
                   else (expr.attr, _constants(module).get(expr.value.id, ("", "", ""))[1])
                   if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name)
                   else (None, None))
    for _ in range(8):  # follow imports of imports; the tree has no longer chain
        bound = _constants(where).get(name, _UNSEEN) if name and where else _UNSEEN
        if isinstance(bound, tuple) and len(bound) == 3 and bound[0] == "import":
            _, where, name = bound
            continue
        return bound
    return _UNSEEN


def _values(expr: ast.expr, module: str, loops: dict[str, ast.expr]) -> set | object:
    """Every value `expr` can hold, or `_UNSEEN`."""
    if isinstance(expr, ast.Name) and expr.id in loops:  # a loop's target: what the loop walks
        walked = loops[expr.id]
        if (isinstance(walked, ast.Call) and isinstance(walked.func, ast.Attribute)
                and walked.func.attr in ("items", "keys", "values") and not walked.args):
            walked, part = walked.func.value, walked.func.attr
        else:
            part = "keys"
        held = _bound(walked, module)
        if not isinstance(held, (dict, list, tuple, set, frozenset)):
            return _UNSEEN
        return set(held.values()) if part == "values" and isinstance(held, dict) else set(held)
    held = _bound(expr, module)
    return {held} if isinstance(held, str) else _UNSEEN


def _kind_of(call: ast.Call, positional: int | None) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == "kind":
            return kw.value
    if positional is not None and len(call.args) > positional:
        return call.args[positional]
    return None


def _visit(node: ast.AST, module: str, function: str, loops: dict[str, ast.expr],
           found: list[str]) -> None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        function = node.name
    if isinstance(node, (ast.For, ast.AsyncFor)):
        names = [n.id for n in ast.walk(node.target) if isinstance(n, ast.Name)]
        loops = {**loops, **{n: node.iter for n in names}}
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        for gen in node.generators:
            names = [n.id for n in ast.walk(gen.target) if isinstance(n, ast.Name)]
            loops = {**loops, **{n: gen.iter for n in names}}
    if isinstance(node, ast.Call):
        callee = (node.func.attr if isinstance(node.func, ast.Attribute)
                  else node.func.id if isinstance(node.func, ast.Name) else "")
        where = f"{module}:{node.lineno}"
        # Each way a row is made or removed: built (`MetricRecord(kind=…)`), removed
        # (`<sink>.forget(project, kind=…)`), or an audit record's row written again
        # (`metric_of`, whose row `.record`/`record_if_absent` would replace in place
        # under the same key). NOT `<row>.model_copy(update={"kind": …})`: the walk cannot
        # tell a metrics row from the other models copied that way (`product/case.py`
        # copies a draft's `kind`), and no copy in the tree changes a row's kind.
        checked = {"MetricRecord": None, "forget": 1}.get(callee, "skip")
        if checked != "skip":
            kind = _kind_of(node, checked)
            if kind is not None:
                values = _values(kind, module, loops)
                allowed = (module, function) == ("openfactory.observability.audit",
                                                 "metric_of") and callee == "MetricRecord"
                if values is _UNSEEN:
                    found.append(f"{where} {callee}(kind={ast.unparse(kind)}) unseen")
                elif "audit" in values and not allowed:
                    found.append(f"{where} {callee}(kind={ast.unparse(kind)})")
        if callee == "metric_of" and (module, function) != (
                "openfactory.observability.audit", "_keep"):
            found.append(f"{where} metric_of(…) outside audit._keep")
    for child in ast.iter_child_nodes(node):
        _visit(child, module, function, loops, found)


def _rewrites_of_an_audit_row() -> list[str]:
    """`<module>:<line> <what>` for each place outside `audit.metric_of`/`audit._keep` that
    makes, re-writes or forgets a row of kind `audit`, or whose `kind` the walk cannot see."""
    found: list[str] = []
    for module, tree in _parsed().items():
        _visit(tree, module, "", {}, found)
    return found


def test_nothing_rewrites_an_audit_row():
    """Criterion 3, "append-only": the one place a row of kind `audit` is made is
    `audit.metric_of`, the one place it is handed to a store is `audit._keep` (behind
    `audit.write`, once per call), and nothing in `openfactory/` forgets one — only the store's
    TTL removes it, after `audit.AUDIT_KEPT_DAYS`. A second writer of an audit row would replace a
    record under its own key; a `forget` of the kind would erase who did what. Before #694 no row
    of kind `audit` existed, so there was nothing to guard."""
    found = _rewrites_of_an_audit_row()

    assert found == [], "an audit row is made, written again or forgotten outside audit.write:\n" + (
        "\n".join(found))


# ── what `project forget` keeps, and why it may: no client's words are in a record ──────────────

def test_forgetting_a_project_keeps_its_audit_records(store, tmp_path, monkeypatch):
    """Criterion 3, "the local default sink writes audit records … append-only", against the one
    command that deletes a project's rows (Q8, decided: kept). A person asks for a registered
    project's status, leaving one record under it; the project also has a card verdict, which
    `project forget` removes. After `project forget books --yes --no-backup` the verdict is gone
    and the record of who asked is still read back — an audit trail a forget erased would answer
    "who removed this project's records" with nothing. Before #694 there was no record to keep;
    `forget.RECORD_KINDS` holding `audit` turns this red."""
    import asyncio

    from typer.testing import CliRunner

    from openfactory.cli import app
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.observability.metrics import MetricRecord
    from openfactory.registry import ProjectRegistry

    monkeypatch.setenv("OPENFACTORY_BOARD_DB", str(tmp_path / "board.db"))
    monkeypatch.setenv("OPENFACTORY_LOG_DIR", str(tmp_path / "logs"))
    ProjectRegistry().add(Project(name="books", repo_path=str(tmp_path / "books"), language="en",
                                  tracker=ProviderRef(kind="local", repo="books", options={})))
    # sync, so the command below runs as a person runs it, with no event loop already going
    asyncio.run(actions.perform("product_status", by=actions.Actor(id="alice", via="panel"),
                                project="books"))
    assert store.record(MetricRecord(project="books", ticket="7", ts=datetime.now(UTC).isoformat(),
                                     kind="card_verdict", role="card_verdict"))
    assert len(store.records_of_kind("books", "audit")) == 1, "the call left no record to keep"

    done = CliRunner().invoke(app, ["project", "forget", "books", "--yes", "--no-backup"])

    assert done.exit_code == 0, done.output
    assert store.records_of_kind("books", "card_verdict") == [], "the forget did not run"
    kept = store.records_of_kind("books", "audit")
    assert [(r["extra"]["action"], r["extra"]["actor_id"]) for r in kept] == [
        ("product_status", "alice")], "project forget erased the record of who did what"


_SENTINEL = "o saldo do Joaquim vem errado desde março"


def _digest(text: str) -> dict[str, object]:
    import hashlib

    return {"chars": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


async def test_a_clients_words_never_reach_the_audit_record(store):
    """Criterion 6, and the condition Q8's "kept" rests on: what a client says to the product role
    is kept in the conversation and erased on request (`project forget-conversations`, ADR-0024);
    a record kept for `AUDIT_KEPT_DAYS` beside every call, and kept by `project forget`, must not
    be a second copy of it. `product_say` with a sentinel message leaves a record whose `message`
    is its length and sha256 and nothing else, and the sentinel's bytes are in neither the sqlite
    file nor its `-wal`. Before #694's hashing (task 12) the record would have held the message
    verbatim; dropping `message` from `actions.base.FREE_TEXT` turns this red."""
    by = actions.Actor(id="alice", via="panel")

    await actions.perform("product_say", by=by, project="nosuch", message=_SENTINEL)

    rows = store.records_of_kind("nosuch", "audit")
    assert [row["extra"]["action"] for row in rows] == ["product_say"], rows
    assert rows[0]["extra"]["params"]["message"] == _digest(_SENTINEL), rows[0]["extra"]["params"]
    files = [p for p in (store.path, store.path.with_name(store.path.name + "-wal")) if p.exists()]
    assert store.path in files, files
    leaked = [p.name for p in files if _SENTINEL.encode("utf-8") in p.read_bytes()]
    assert not leaked, f"the client's words are in {leaked}"


#: Parameters the catalog takes that ARE a person's words, each by the row that hands it on: to
#: the conversation (`product_say`), a card's thread (`card_comment`), an agent's instruction
#: (`adjust`), the product role's answer (`product_answer`), a question asked of the tech lead
#: (`ask`). A floor, not the list: `FREE_TEXT` is the list, and this says it cannot shrink below
#: the words a client is known to type.
_WORDS_A_CLIENT_TYPES = {("product_say", "message"), ("card_comment", "message"),
                         ("adjust", "instruction"), ("product_answer", "answer"),
                         ("ask", "question")}


def test_every_free_text_parameter_in_the_catalog_is_hashed():
    """Criterion 6, across the catalog rather than one row: for every row and every parameter it
    takes whose name is in `actions.base.FREE_TEXT`, the record `AuditRecord.of` makes of a call
    holds that value as `{"chars", "sha256"}` and the words nowhere in it; the words a client is
    known to type are among them; and every name in `FREE_TEXT` is one some row takes, so the set
    is not a list of words nothing passes. Before #694 there was no record and no `FREE_TEXT`."""
    from openfactory.actions.base import FREE_TEXT
    from openfactory.actions.catalog import CATALOG
    from openfactory.observability.audit import AuditRecord

    taken = {(row.name, p) for row in CATALOG.values() for p in (*row.required, *row.optional)}
    words = {(name, p) for name, p in taken if p in FREE_TEXT}
    assert _WORDS_A_CLIENT_TYPES <= words, sorted(_WORDS_A_CLIENT_TYPES - words)
    assert FREE_TEXT <= {p for _, p in taken}, sorted(FREE_TEXT - {p for _, p in taken})

    verbatim = []
    for name, param in sorted(words):
        record = AuditRecord.of(name, actions.SYSTEM, {"project": "nosuch", param: _SENTINEL},
                                actions.done("fine"), product_of=lambda _: "")
        if record.params.get(param) != _digest(_SENTINEL) or _SENTINEL in repr(record):
            verbatim.append(f"{name}.{param}")
    assert verbatim == [], f"a person's words are kept verbatim by {verbatim}"


# ── a store that does not take the record is said; the loop never waits on one ──────────────────

class _RaisingStore:
    """A sink that raises from `record` — what an out-of-tree store does that, unlike the sqlite
    one, does not catch its own failures. `path` is how the WARNING must name it."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, rec) -> bool:
        raise RuntimeError("the store is gone")


def _a_refusing_store(tmp_path: Path, monkeypatch) -> Path:
    """`OPENFACTORY_METRICS_DB` naming a directory: the sqlite sink cannot open it, logs its own
    line and returns False — a write that did not land, said by a value and not an exception."""
    where = tmp_path / "not-a-file.db"
    where.mkdir()
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(where))
    return where


def _a_raising_store(tmp_path: Path, monkeypatch) -> Path:
    from openfactory.observability import audit

    where = tmp_path / "raising-store"
    monkeypatch.setattr(audit, "sink", lambda: _RaisingStore(where))
    return where


@pytest.mark.parametrize("failing", [_a_refusing_store, _a_raising_store],
                         ids=["record_returns_false", "record_raises"])
async def test_a_store_that_refuses_the_write_is_said_and_the_outcome_stands(
        store, tmp_path, monkeypatch, caplog, failing):
    """Criterion 3 under `docs/engineering-lessons.md` §6, "silence is a failure mode": a record
    the store did not take is said, once, at WARNING, naming the action and the store, and the
    caller is told exactly what it would have been told had the store taken it. Before this, a
    store that answered False was silent at the action layer (the sqlite sink's own line names a
    project and a record id, not the action, and the bool was dropped), and one that raised was
    said without naming the store."""
    by = actions.Actor(id="alice", via="panel")
    stood = await actions.perform("product_status", by=by, project="nosuch")
    assert len(_audit_rows(store)) == 1, "the working store did not take the first record"
    where = failing(tmp_path, monkeypatch)

    with caplog.at_level("WARNING"):
        outcome = await actions.perform("product_status", by=by, project="nosuch")

    assert (outcome.ok, outcome.code, outcome.data, outcome.message) == (
        stood.ok, stood.code, stood.data, stood.message), outcome
    said = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"
            and "product_status" in r.getMessage() and str(where) in r.getMessage()]
    assert len(said) == 1, ("a record the store did not take was said "
                            f"{len(said)} times naming the action and {where} (1 expected): "
                            f"{[r.getMessage() for r in caplog.records]}")


async def test_a_sink_that_cannot_be_built_is_said_and_the_outcome_stands(store, monkeypatch,
                                                                         caplog):
    """Criterion 3, §6, before any store is reached: a deployment whose `OPENFACTORY_METRICS_SINK`
    names a kind nothing answers to cannot build the store the record goes to, so `audit.write`
    raises — and `perform` says, once, at WARNING, that the record of this action by this caller
    was not kept, and answers exactly what it would have answered. Written with the mutation plan
    (2026-10-20): the WARNING in `_leave_record` had no test, and removing it left the suite
    green."""
    by = actions.Actor(id="alice", via="panel")
    stood = await actions.perform("product_status", by=by, project="nosuch")
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlit")

    with caplog.at_level("WARNING"):
        outcome = await actions.perform("product_status", by=by, project="nosuch")

    assert (outcome.ok, outcome.code, outcome.data, outcome.message) == (
        stood.ok, stood.code, stood.data, stood.message), outcome
    said = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"
            and "product_status" in r.getMessage() and "alice" in r.getMessage()
            and "not kept" in r.getMessage()]
    assert len(said) == 1, ("a record no store could be built for was said "
                            f"{len(said)} times naming the action and the caller (1 expected): "
                            f"{[r.getMessage() for r in caplog.records]}")


async def test_the_audit_write_does_not_run_on_the_event_loop(store, monkeypatch):
    """Criterion 3, and the #748 lesson: the panel performs on its event loop, and a sqlite write
    waits on the file's lock for up to its busy timeout, so a write on the loop would hold every
    other request with it. The sink's `record` is called on a thread that is not the loop's."""
    import threading

    loop = threading.current_thread()
    seen: list[threading.Thread] = []
    real = SqliteMetricsSink.record

    def spied(self, rec):
        seen.append(threading.current_thread())
        return real(self, rec)

    monkeypatch.setattr(SqliteMetricsSink, "record", spied)

    await actions.perform("product_status", by=actions.Actor(id="alice", via="panel"),
                          project="nosuch")

    assert len(seen) == 1, f"the sink was asked to record {len(seen)} times (1 expected)"
    assert seen[0] is not loop, f"the audit write ran on the event loop's thread ({loop.name})"


async def test_the_record_reads_the_registry_off_the_event_loop(store, monkeypatch):
    """Criterion 3, the same lesson for the record's other file: naming a call's product reads
    `registry.yaml` (`audit._product_of`), and the panel reads its registry off the loop
    everywhere else (`api/app.py`, `asyncio.to_thread(lambda: ProjectRegistry().list())`). An
    unknown action reads no registry of its own, so the one read here is the record's, and it is
    not on the loop's thread. Before this the record was made on the loop, the read with it."""
    import threading

    from openfactory.registry import ProjectRegistry

    loop = threading.current_thread()
    seen: list[threading.Thread] = []
    real = ProjectRegistry.get

    def spied(self, name):
        seen.append(threading.current_thread())
        return real(self, name)

    monkeypatch.setattr(ProjectRegistry, "get", spied)

    await actions.perform("teleport", by=actions.Actor(id="alice", via="panel"), project="nosuch")

    assert [row["extra"]["action"] for row in _audit_rows(store)] == ["teleport"]
    assert seen, "the record named no product, so the registry was never read"
    assert loop not in seen, f"the record read the registry on the event loop's thread ({loop.name})"


async def test_a_call_cancelled_while_its_record_is_made_still_leaves_it(store, monkeypatch):
    """Criterion 2, "every call": `perform` makes and writes its record under `asyncio.shield`, so
    a cancel that arrives while the record is being made (a panel client hanging up, a worker
    shutting down) is passed on to the caller and the record is still written. The registry read
    the record makes is held until the cancel has landed; the row appears once it is let go."""
    import asyncio
    import threading

    from openfactory.registry import ProjectRegistry

    entered, release = threading.Event(), threading.Event()
    real = ProjectRegistry.get

    def held(self, name):
        entered.set()
        release.wait(10)
        return real(self, name)

    monkeypatch.setattr(ProjectRegistry, "get", held)
    call = asyncio.create_task(
        actions.perform("teleport", by=actions.Actor(id="alice", via="panel"), project="nosuch"))
    try:
        assert await asyncio.to_thread(entered.wait, 10), "the record never read the registry"
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
    finally:
        release.set()
    for _ in range(200):
        if _audit_rows(store):
            break
        await asyncio.sleep(0.01)

    assert [row["extra"]["action"] for row in _audit_rows(store)] == ["teleport"], (
        "a cancel while the record was made left no record")


# ── a host CLI with no store named still keeps its records, and the dashboard's store stays put ──

def test_a_host_cli_with_no_store_configured_still_keeps_the_record(tmp_path, monkeypatch):
    """Criterion 3 for the transport ADR-0039 §2 says outranks every gate (Q9, decided): on a host
    with no `OPENFACTORY_METRICS_*` at all the deployment's metrics sink is `null` and keeps
    nothing, so the record goes to `audit.db` beside `registry.yaml` (ADR-0049 D5's resolution) —
    and to no file in the directory the shell stood in. `openfactory act product_status -p nosuch`
    run as a person runs it leaves its one record there. Before #694 it left nothing anywhere."""
    from typer.testing import CliRunner

    from openfactory.cli import app

    for name in ("OPENFACTORY_METRICS_SINK", "OPENFACTORY_METRICS_DB",
                 "OPENFACTORY_METRICS_TABLE"):
        monkeypatch.delenv(name, raising=False)
    home = tmp_path / "operator"
    home.mkdir()
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(home / "registry.yaml"))
    shell = tmp_path / "where-the-shell-stood"
    shell.mkdir()
    monkeypatch.chdir(shell)

    done = CliRunner().invoke(app, ["act", "product_status", "-p", "nosuch"])

    assert done.exit_code == 1, done.output
    kept = SqliteMetricsSink(home / "audit.db").records_of_kind("nosuch", "audit")
    assert [(r["extra"]["action"], r["extra"]["via"]) for r in kept] == [
        ("product_status", "cli")], f"no record in {home / 'audit.db'}"
    assert sorted(p.name for p in shell.iterdir()) == [], "the CLI wrote into the shell's cwd"


def test_the_metrics_sink_kind_inference_is_unchanged(monkeypatch):
    """Q9's other half: the audit's fallback file is the audit's alone. With no
    `OPENFACTORY_METRICS_*` set the deployment's metrics sink is still inferred `null`, and built
    as the null sink, so a deployment's cost dashboard reads from where it read before #694
    (`metrics_sink_kind`'s docstring: changing that inference would move a live dashboard)."""
    from openfactory.observability.metrics import NullMetricsSink
    from openfactory.observability.registry import deployment_metrics_sink, metrics_sink_kind

    for name in ("OPENFACTORY_METRICS_SINK", "OPENFACTORY_METRICS_DB",
                 "OPENFACTORY_METRICS_TABLE"):
        monkeypatch.delenv(name, raising=False)

    assert metrics_sink_kind() == "null"
    assert isinstance(deployment_metrics_sink(), NullMetricsSink)


# ── the deployment-wide key is shared with the people store, and the audit does not crowd it ─────

async def test_audit_rows_under_the_deployment_key_do_not_hide_a_registered_person(store,
                                                                                  monkeypatch):
    """Q7's guard: a call that names no project (`people_invite`, an unknown action) is kept under
    the people store's deployment-wide key `_deployment_` — the partition every account lives in.
    The people store reads that key's most recent `people.READ_LAST` rows and the accounts are the
    OLDEST rows there (`identity/people.py`, the `READ_LAST` comment: five thousand permanent
    `revoked` rows once emptied the fold, review of #35, 2026-09-03). `READ_LAST + 5` audit rows
    written there after a person registered, each live for a year, leave the person found and
    their password still opening a session, because the read is by kind as well as by key.

    The positive twin of that invariant, not a red test: green on the commit before it, and red
    under a hand cut that reads the key without its kind (`query.StoreUnreadable`: the people
    store's 8 most recent rows hold no registration). Real sqlite file, real `audit.write`, real
    `PeopleStore`; `READ_LAST` is shrunk to 8 as `test_a_person_is_invited_not_signed_up.py`
    shrinks it, because 5,005 audit writes each wait on the file's fsync — 115 s measured here
    (2026-10-20) — and the arithmetic of a window is the same at eight."""
    from openfactory.identity import people
    from openfactory.observability import audit

    monkeypatch.setattr(people, "READ_LAST", 8)

    registry = people.PeopleStore()
    token, _ = registry.invite("ana@acme.example", display="Ana Lima", by="roberto")
    password = "a passphrase long enough"
    assert not isinstance(registry.register(token=token, display="Ana Lima",
                                            password=password), str)

    by = actions.Actor(id="roberto", via="panel")
    refused = actions.Outcome(ok=False, message="", code=actions.FAILED)
    for n in range(people.READ_LAST + 5):
        record = audit.AuditRecord.of("people_invite", by, {"ident": f"p{n}@acme.example"},
                                      refused)
        assert await audit.write(record), f"audit row {n} did not land"

    # The premise, read past the people store's own query so a cut there cannot blind it.
    keys = [row.get("project") for row in _audit_rows(store)]
    assert keys == [people.PROJECT] * (people.READ_LAST + 5), "the rows are not under the shared key"
    reread = people.PeopleStore()
    assert [p.id for p in reread.people()] == ["ana@acme.example"], \
        "the audit rows scrolled the account out of the people store's read"
    assert reread.login("ana@acme.example", password), "and the password still opens a session"


async def test_audit_rows_in_the_store_do_not_change_the_cost_dashboard(store):
    """The dashboard reads the whole store (`metrics_view.cost_dashboard` scans every row), and
    its project selector was every key any row was under, kind unread — with the FIRST of them
    the project shown when none is named. An audit row is written for every call, under the
    project the caller TYPED, registered or not, refused or not, and under `_deployment_` when it
    named none. Measured on this branch before the fix (2026-10-21): one refused `product_status`
    on `aaa-typo` and one unknown action made the selector `['_deployment_', 'aaa-typo', 'books']`
    and the default view `_deployment_`'s, $0.00 spent, on a store whose only spend is `books`'
    $0.50. Read through the real sqlite store and the dashboard's real door."""
    from openfactory.api.metrics_view import cost_dashboard
    from openfactory.observability.autonomy import autonomy
    from openfactory.observability.metrics import MetricRecord

    store.record(MetricRecord(project="books", ticket="#1", ts="2026-10-20T09:00:00+00:00",
                              kind="agent_run", role="executor", cost_usd=0.5))
    spend_only = store.scan()
    by = actions.Actor(id="alice", via="panel")

    await actions.perform("product_status", by=by, project="aaa-typo")
    await actions.perform("no_such_action", by=by)

    assert {row.get("project") for row in _audit_rows(store)} == {"aaa-typo", "_deployment_"}, \
        "the premise: both calls left their audit row in the store the dashboard reads"
    shown = cost_dashboard()
    assert (shown["projects"], shown["project"], shown["totals"]["cost_usd"]) == (
        ["books"], "books", 0.5), "an audit row moved the dashboard's selector or its default view"
    assert shown["autonomy"] == autonomy(spend_only, "books"), "the autonomy block read audit rows"
