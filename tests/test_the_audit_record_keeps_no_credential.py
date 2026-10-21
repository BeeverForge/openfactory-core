"""The audit record, its INFO line and the denial warnings keep no credential, however a caller
sends one, and the file a host keeps them in is its owner's alone (#694, PR #1039 review).

WHAT WAS TRUE BEFORE. `audit.SECRET` named four exact parameter names, read at the top level only,
and `_kept` kept every other value as sent. Measured on c310ba28 with the reviewer's fictitious
values, every one of them was in `audit.db`, which `SqliteMetricsSink` created `0644` and keeps for
`AUDIT_KEPT_DAYS`: a token in a URL's userinfo (`env_read target=https://u:ghp_…@github.com/o/r`),
the values of `api_key`, `Password` and `github_pat` on a refused `product_status` (a refused call
is recorded as faithfully as one that ran, and the panel hands `perform` every name a body holds),
and `product_say context={"password": …}`, a secret one level down.

WHAT HOLDS NOW, read off the row in the sqlite file, the bytes of the file, the INFO line read back
as the value it prints, and the denial warnings' own function: every kept string goes through
`product.model.scrub_credentials` before it is cut (a token in a URL, a credential's shape, a value
of this process's secrets); a name is a secret's by pattern, whatever its case, at every depth of a
mapping or a list; a name that only contains the letters `pat` (`path`, `repo_path`) is not one;
what is nested deeper than `NESTED_DEPTH` is not kept at all; the bound on a parameter's value
holds for a nested one; and the fallback `audit.db` is created `0600`, and one found wider is made
`0600`, said once.
"""

from __future__ import annotations

import ast
import json
import logging
import stat
from pathlib import Path

import pytest

from openfactory import actions
from openfactory.observability.sqlite_metrics import SqliteMetricsSink

#: The reviewer's fictitious credentials (PR #1039 review, 2026-10-21): a classic GitHub token in
#: its own shape, and values a credential-shape regex cannot see, which only their name gives away.
PAT = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
BY_NAME = {"api_key": "fictitious-api-key-0001", "Password": "Fictitious-Passw0rd",
           "github_pat": "fictitious-pat-value-0003"}
NESTED = "nested-fictitious-secret"


@pytest.fixture
def store(tmp_path, monkeypatch) -> SqliteMetricsSink:
    """A sqlite deployment as an operator names one, with a registry of its own; the sink returned
    is a second handle on the file `perform` writes."""
    db = tmp_path / "metrics.db"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(db))
    return SqliteMetricsSink(db)


def _row(store: SqliteMetricsSink) -> dict:
    """The one audit row the call left: its record's own fields."""
    rows = [row for row in store.scan() if row.get("kind") == "audit"]
    assert len(rows) == 1, f"{len(rows)} audit rows for one call (1 expected)"
    return rows[0]["extra"]


def _in_the_file(store: SqliteMetricsSink, secret: str) -> list[str]:
    """The files of the store — the database and its write-ahead log — whose bytes hold `secret`."""
    files = [p for p in (store.path, store.path.with_name(store.path.name + "-wal")) if p.exists()]
    return [p.name for p in files if secret.encode() in p.read_bytes()]


def _the_line(caplog) -> dict:
    """The parameters the one `action=` line printed, read back as the value they are."""
    lines = [r.getMessage() for r in caplog.records
             if r.levelname == "INFO" and r.getMessage().startswith("action=")]
    assert len(lines) == 1, f"{len(lines)} action lines for one call (1 expected): {lines}"
    return ast.literal_eval(lines[0].split(" params=", 1)[1])


async def test_a_token_in_a_urls_userinfo_reaches_neither_the_record_the_line_nor_the_file(
        store, caplog):
    """The reviewer's first case: `env_read target=https://u:ghp_…@github.com/o/r`. The record
    keeps the URL without its userinfo, the line prints what the record keeps, and the token's
    bytes are in neither the database nor its `-wal`. On c310ba28 the row's `target` was the URL
    as sent, the token in it."""
    with caplog.at_level(logging.INFO):
        await actions.perform("env_read", by=actions.Actor(id="alice", via="panel"),
                              target=f"https://u:{PAT}@github.com/o/r")

    kept = _row(store)["params"]
    assert PAT not in json.dumps(kept), kept
    assert kept["target"] == "https://github.com/o/r", kept
    assert _the_line(caplog) == kept
    assert not _in_the_file(store, PAT), "the token is in the store's files"


@pytest.mark.parametrize("name", list(BY_NAME))
async def test_a_refused_call_masks_a_secret_by_its_name_whatever_its_case_and_affix(
        store, caplog, name):
    """The reviewer's second case: a refused `product_status` sent `api_key`, `Password` and
    `github_pat` — names no row takes, which the panel hands `perform` as the body held them. Each
    is masked by its name (`key`, `password` in any case, `pat` as a word of it), in the record,
    the line and the file. On c310ba28 all three values were kept, the call refused
    `bad_parameters`."""
    with caplog.at_level(logging.INFO):
        outcome = await actions.perform("product_status", by=actions.Actor(id="alice", via="panel"),
                                        project="nosuch", **BY_NAME)

    assert outcome.data.get("reason") == actions.BAD_PARAMETERS, outcome
    kept = _row(store)["params"]
    assert kept[name] == "***", kept
    assert _the_line(caplog)[name] == "***"
    assert not _in_the_file(store, BY_NAME[name]), f"{name}'s value is in the store's files"


async def test_a_secret_nested_in_a_parameter_is_masked_like_one_at_the_top(store, caplog):
    """The reviewer's third case: `product_say context={"password": …}`. A mapping inside a
    parameter is kept with each of its names read by the same rule, so the nested password is
    `***`. On c310ba28 the row's `context` was `{"password": "nested-fictitious-secret"}`."""
    with caplog.at_level(logging.INFO):
        await actions.perform("product_say", by=actions.SYSTEM, project="nosuch", message="hi",
                              context={"password": NESTED})

    kept = _row(store)["params"]
    assert kept["context"] == {"password": "***"}, kept
    assert _the_line(caplog)["context"] == {"password": "***"}
    assert not _in_the_file(store, NESTED), "the nested password is in the store's files"


async def test_a_secret_in_a_list_is_masked_like_one_in_a_mapping(store):
    """Criterion (c) of the review's fix, for a list: `product_reorder numbers=[{"token": …}]`
    keeps the list, and the token inside its mapping is `***`. On c310ba28 the row's `numbers`
    held the token as sent."""
    await actions.perform("product_reorder", by=actions.SYSTEM, project="nosuch",
                          numbers=[3, {"token": NESTED}])

    kept = _row(store)["params"]
    assert kept["numbers"] == [3, {"token": "***"}], kept
    assert not _in_the_file(store, NESTED)


def test_a_parameter_named_like_a_path_is_not_masked():
    """The collision the name rule had to resolve: the catalog takes `path` (`product_ingest`) and
    `repo_path` (`product_first_source`), and a `*pat*` substring would mask both, so the record
    would no longer say which file was ingested. `pat` is a secret's name only as a word of it
    (`pat`, `github_pat`, `githubPat`). Green on c310ba28 (nothing but four exact names was masked);
    the cut that matches `pat` as a substring turns it red."""
    from openfactory.observability import audit

    kept = audit._kept("product_ingest", {"project": "acme", "path": "docs/a.md",
                                          "repo_path": "/srv/acme", "githubPat": "x",
                                          "pat": "y"})

    assert (kept["path"], kept["repo_path"]) == ("docs/a.md", "/srv/acme"), kept
    assert (kept["githubPat"], kept["pat"]) == ("***", "***"), kept


async def test_a_token_straddling_the_cut_is_withheld_before_the_value_is_cut(store):
    """A value is scrubbed whole and then cut to `VALUE_CHARS`, so a cut cannot split a token past
    the scrub: a token that starts 10 characters before the cut leaves none of its characters in
    the record. Scrubbed after the cut, the record would keep `ghp_A1b2C3` — the token's prefix,
    which no shape matches once cut."""
    from openfactory.observability import audit

    value = "x" * (audit.VALUE_CHARS - 11) + " " + PAT   # a token is a word: `\b` begins it

    await actions.perform("product_status", by=actions.SYSTEM, project="nosuch", note=value)

    kept = _row(store)["params"]["note"]
    assert PAT[:10] not in kept, kept[-80:]
    assert not _in_the_file(store, PAT[:10])


async def test_a_secret_this_process_holds_is_withheld_wherever_a_caller_sends_it(store,
                                                                                monkeypatch):
    """`scrub_credentials` withholds the value of every secret-named variable of this process
    (eight characters or more), whatever shape it has: a caller who pastes the panel's own secret
    into a parameter does not write it into the record. On c310ba28 it was kept as sent."""
    held = "the-panels-own-fictitious-secret"
    monkeypatch.setenv("OPENFACTORY_GATE_SECRET", held)

    await actions.perform("product_status", by=actions.SYSTEM, project="nosuch", note=held)

    assert held not in json.dumps(_row(store)["params"])
    assert not _in_the_file(store, held)


async def test_a_token_in_the_project_a_caller_typed_is_withheld_from_the_rows_key(store):
    """The `project` parameter is also the record's `project` field and the row's key, read apart
    from the parameters: it is scrubbed as they are. On c310ba28 a project typed as a URL with a
    token kept the token in the row's `pk`."""
    await actions.perform("product_status", by=actions.SYSTEM,
                          project=f"https://u:{PAT}@github.com/o/r")

    row = _row(store)
    assert PAT not in row["project"] and PAT not in json.dumps(row["params"]), row["project"]
    assert not _in_the_file(store, PAT)


async def test_a_token_sent_as_a_parameters_name_is_withheld_from_the_record(store):
    """A parameter's name is whatever a request body held, so it is scrubbed as a value is: a
    token sent as a name (`{"ghp_…": 1}`) is in neither the record nor the file. On c310ba28 the
    name was kept as sent, and only a value could be masked."""
    await actions.perform("product_status", by=actions.SYSTEM, project="nosuch", **{PAT: 1})

    assert PAT not in json.dumps(_row(store)["params"])
    assert not _in_the_file(store, PAT)


async def test_a_token_typed_as_the_action_is_withheld_from_the_record_and_the_line(store,
                                                                                   caplog):
    """The action a caller typed is the record's `action` and part of the row's key, and the INFO
    line prints it: an unknown action spelled as a token keeps the token in neither. On c310ba28
    both held it."""
    with caplog.at_level(logging.INFO):
        await actions.perform(f"see https://u:{PAT}@github.com/o/r", by=actions.SYSTEM)

    row = _row(store)
    assert PAT.lower() not in row["action"].lower(), row["action"]
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("action=")]
    assert lines and not [line for line in lines if PAT.lower() in line.lower()], lines
    assert not _in_the_file(store, PAT.lower())


def test_a_value_nested_past_the_depth_bound_is_not_kept_and_says_so():
    """Recursion is bounded: what sits deeper than `audit.NESTED_DEPTH` mappings or lists inside a
    parameter is not kept, and the record says so in its place — so a secret under a name nothing
    reads at that depth cannot reach the record as text. Ten levels is past any bound the record
    could keep. On c310ba28 the whole nest was kept as its `str`, the secret in it."""
    from openfactory.observability import audit

    deep: object = {"password": NESTED, "note": "ten levels down"}
    for _ in range(10):
        deep = {"a": deep}

    kept = audit._kept("product_say", {"project": "nosuch", "context": deep})

    assert "ten levels down" not in repr(kept), kept
    inner = kept["context"]
    while isinstance(inner, dict):
        inner = inner["a"]
    assert isinstance(inner, str) and "not kept" in inner, inner


def test_a_nested_value_is_kept_to_the_bound_a_value_is_kept_to():
    """The bound on a parameter's value holds for a nested one: a mapping of 5,000 entries of
    2,000 characters is kept as at most `PARAMS_KEPT` entries, and then cut to `VALUE_CHARS` as
    any value is. Green on c310ba28 (the mapping was cut as its `str`); the cut that keeps a nested
    value whole turns it red."""
    from openfactory.observability import audit

    sent = {f"n{i}": "v" * 2_000 for i in range(5_000)}

    kept = audit._kept("product_say", {"project": "nosuch", "context": sent})

    assert len(str(kept["context"])) < audit.VALUE_CHARS + 100, len(str(kept["context"]))


def test_the_denial_warning_masks_what_the_record_masks():
    """The denial warnings (`DENIED_SCOPE`, `DENIED`, `NO_CODE_YET`) print `actions._loggable`,
    which is `audit.redact`: it masks by the same name rule at every depth and scrubs every
    string. On c310ba28 it masked four exact names at the top level and printed the rest as
    sent — each of the reviewer's values among them."""
    printed = repr(actions._loggable({"project": "nosuch", **BY_NAME,
                                      "context": {"password": NESTED},
                                      "target": f"https://u:{PAT}@github.com/o/r"}))

    leaked = [s for s in (PAT, NESTED, *BY_NAME.values()) if s in printed]
    assert not leaked, f"the denial warning prints {leaked}"


def test_a_nested_mapping_is_read_to_PARAMS_KEPT_entries_and_the_rest_counted():
    """Each mapping inside a parameter is read to `PARAMS_KEPT` entries and the rest counted, as
    the parameters themselves are — so the work a call costs is bounded before anything is cut,
    in the denial warnings too, which keep no `VALUE_CHARS` bound. On c310ba28 the warning
    printed all 5,000 entries."""
    from openfactory.observability import audit

    printed = actions._loggable({"project": "nosuch",
                                 "context": {f"n{i}": "v" for i in range(5_000)}})

    context = printed["context"]
    assert len(context) == audit.PARAMS_KEPT + 1, len(context)
    assert context["…"] == f"{5_000 - audit.PARAMS_KEPT} more entries not kept", context["…"]


# ── the fallback file is its owner's alone ──────────────────────────────────────────────────────

@pytest.fixture
def fallback(tmp_path, monkeypatch) -> Path:
    """A host with no store declared: the records go to `audit.db` beside `registry.yaml`."""
    for name in ("OPENFACTORY_METRICS_SINK", "OPENFACTORY_METRICS_DB",
                 "OPENFACTORY_METRICS_TABLE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    return tmp_path / "audit.db"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


async def test_the_fallback_audit_file_is_created_readable_by_its_owner_alone(fallback,
                                                                             monkeypatch):
    """The reviewer's fourth point: `audit.db` holds who did what for a year, and on c310ba28 it
    was created `0644` under the default umask `0022` — readable by every account on the host.
    It is created `0600`, its write-ahead log with it, whatever the umask."""
    import os

    old = os.umask(0o022)
    try:
        await actions.perform("product_status", by=actions.SYSTEM, project="nosuch")
    finally:
        os.umask(old)

    assert fallback.exists()
    wal = fallback.with_name(fallback.name + "-wal")
    modes = {p.name: oct(_mode(p)) for p in (fallback, wal) if p.exists()}
    assert set(modes.values()) == {oct(0o600)}, modes


async def test_a_fallback_audit_file_readable_by_others_is_made_private_and_said(fallback,
                                                                                caplog):
    """A file left `0644` by an earlier version is made `0600` by the next record, and that is
    said once at INFO, naming the file and the mode it had. On c310ba28 it stayed `0644`."""
    fallback.parent.mkdir(parents=True, exist_ok=True)
    fallback.touch(mode=0o644)
    fallback.chmod(0o644)

    with caplog.at_level(logging.INFO, logger="openfactory.observability.audit"):
        await actions.perform("product_status", by=actions.SYSTEM, project="nosuch")
        await actions.perform("product_status", by=actions.SYSTEM, project="nosuch")

    assert _mode(fallback) == 0o600, oct(_mode(fallback))
    said = [r.getMessage() for r in caplog.records
            if r.name == "openfactory.observability.audit" and "0o644" in r.getMessage()]
    assert len(said) == 1 and str(fallback) in said[0], said
