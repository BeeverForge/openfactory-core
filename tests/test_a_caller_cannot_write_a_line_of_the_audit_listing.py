"""A caller cannot write a line of the audit listing, nor of the action's log line (#694, PR #1039
review B1).

WHAT WAS TRUE BEFORE. `openfactory audit` printed a record's `action` and `project` as they were
stored, and both are whatever a caller sent: the project from the request's body, the action from
the path of `POST /api/act/{name}` when no row has it. Measured by the review on c310ba28 through
the real app with no panel token (an anonymous caller): three calls became six lines of the
listing, one reading `2026-10-21T09:00:00+00:00  alice  approve_prod  books  ok`, and a project
holding `\\x1b[2K\\r` erased its own line on a terminal. The INFO line `perform` writes on the
unknown-action path printed the name with `%s`, so `teleport\\nINFO … action=approve_prod …` was
one log record of two lines.

WHAT HOLDS NOW: every column the listing prints, and every caller string the action's log lines
print, has each control character (a `unicodedata` category starting with `C`) and each line or
paragraph separator (`Zl`, `Zp`) written as its escape — so one record is one line, and the stored
record is unchanged (`--json` prints it as it was kept).

The separators are since the branch review of 58cbd307 (2026-10-22): `str.splitlines()` breaks on
U+2028 and U+2029, which are not `C`, and the review's forged line with U+2028 in place of the
newline was two lines of the listing again (`assert 2 == 1`).
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from openfactory import actions

#: The review's three bodies (PR #1039, B1): a project that writes a line of its own, one that
#: erases its line on a terminal, and an action name that does both through the URL's path.
FORGED_LINE = "nosuch\n2026-10-21T09:00:00+00:00  alice  approve_prod  books  ok"
ERASED_LINE = "nosuch\x1b[2K\rFAKE"
#: The forged line with a Unicode line separator, a paragraph separator, and a NEL (U+0085, a `Cc`
#: that the `C` rule already escaped) in place of the newline: `str.splitlines()` breaks on all
#: three, as `observability.logs._STILL_LINE_BREAKS` measured for the JSON log lines (#818).
SEPARATED_LINE = FORGED_LINE.replace("\n", "\u2028")
PARAGRAPHED_LINE = FORGED_LINE.replace("\n", "\u2029")
NEL_LINE = FORGED_LINE.replace("\n", "\x85")
FORGED_ACTION = "teleport%0A2026-10-21T09:00:01+00:00%20%20bob%20%20merge%20%20books%20%20ok"


@pytest.fixture
def panel(tmp_path, monkeypatch) -> TestClient:
    """The real app, open (no panel token: the caller is anonymous), on a sqlite store."""
    for name in ("OPENFACTORY_PANEL_TOKEN", "OPENFACTORY_PANEL_TOKENS", "OPENFACTORY_IDENTITY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlite")
    monkeypatch.setenv("OPENFACTORY_METRICS_DB", str(tmp_path / "metrics.db"))
    from openfactory.api.app import app

    return TestClient(app)


def _listing() -> list[str]:
    from openfactory.cli import app

    result = CliRunner().invoke(app, ["audit"])
    assert result.exit_code == 0, result.output
    return result.stdout.splitlines()


@pytest.mark.parametrize(("path", "project"), [
    pytest.param("product_status", FORGED_LINE, id="a_newline_in_the_project"),
    pytest.param("product_status", ERASED_LINE, id="a_terminal_escape_in_the_project"),
    pytest.param(FORGED_ACTION, "nosuch", id="a_newline_in_the_action"),
    pytest.param("product_status", SEPARATED_LINE, id="a_line_separator_in_the_project"),
    pytest.param("product_status", PARAGRAPHED_LINE, id="a_paragraph_separator_in_the_project"),
    pytest.param("product_status", NEL_LINE, id="a_next_line_in_the_project"),
])
def test_one_call_is_one_line_of_the_listing_whatever_the_caller_sent(panel, path, project):
    """B1: one call through `POST /api/act/{name}` is one line of `openfactory audit`, its control
    characters and separators written as escapes. On c310ba28 each of these calls printed two
    lines, and the second read as somebody else's action; on 58cbd307 the two separators still
    did."""
    panel.post(f"/api/act/{path}", json={"params": {"project": project}})

    lines = _listing()

    assert len(lines) == 1, lines
    assert not [c for c in lines[0] if c in "\n\r\x1b\x85\u2028\u2029"], repr(lines[0])
    assert any(escape in lines[0] for escape in ("\\n", "\\x1b", "\\x85", "\\u2028", "\\u2029")), \
        repr(lines[0])


def test_the_json_listing_keeps_the_record_as_it_was_kept(panel):
    """The escape is the listing's, not the record's: `--json` prints the project as it was kept,
    the newline in it, which `json.dumps` escapes on its own."""
    from openfactory.cli import app

    panel.post("/api/act/product_status", json={"params": {"project": FORGED_LINE}})

    out = CliRunner().invoke(app, ["audit", "--json"])
    [record] = json.loads(out.stdout)["records"]
    assert record["project"] == FORGED_LINE, record["project"]


async def test_the_action_line_is_one_line_whatever_action_was_asked(tmp_path, monkeypatch,
                                                                    caplog):
    """B1, the log: the INFO line `perform` writes on the unknown-action path prints the name a
    caller typed, its control characters escaped, so it stays one line. On c310ba28 it was
    `action=teleport\\nINFO openfactory.actions action=approve_prod by=alice …`, two lines from
    one record."""
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    asked = "teleport\nINFO openfactory.actions action=approve_prod by=alice ok=True code=ok"

    with caplog.at_level(logging.INFO, logger="openfactory.actions"):
        await actions.perform(asked, by=actions.Actor(id="", display="somebody", via="panel"))

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("action=")]
    assert len(lines) == 1, lines
    assert "\n" not in lines[0] and "teleport\\ninfo" in lines[0], repr(lines[0])


async def test_the_plain_action_line_is_one_line_whatever_separator_was_asked(tmp_path,
                                                                             monkeypatch, caplog):
    """B1, the log with no JSON: the deployment's plain formatter (`logs._UTC(logs.FORMAT)`) does
    not escape what a message holds, so the INFO line `perform` writes is one line only if the
    name a caller typed is escaped first. On 58cbd307 a U+2028 or U+2029 in it was kept raw, and
    `splitlines()` read that one record as two lines (branch review, 2026-10-22)."""
    from openfactory.observability import logs

    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    plain = logs._UTC(logs.FORMAT)

    with caplog.at_level(logging.INFO, logger="openfactory.actions"):
        for separator in ("\u2028", "\u2029"):
            await actions.perform(f"teleport{separator}INFO openfactory.actions action=approve_prod",
                                  by=actions.SYSTEM)

    lines = [plain.format(r) for r in caplog.records if r.getMessage().startswith("action=")]
    assert len(lines) == 2, lines
    assert [len(line.splitlines()) for line in lines] == [1, 1], lines


async def test_no_log_line_about_the_record_carries_a_callers_newline(tmp_path, monkeypatch,
                                                                     caplog):
    """Every other line the record's making writes names the action a caller typed — the WARNING
    when no store could be built among them — and none splits: each control character is
    escaped there too."""
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.setenv("OPENFACTORY_METRICS_SINK", "sqlit")   # no store can be built

    with caplog.at_level(logging.INFO):
        await actions.perform("teleport\nFORGED", by=actions.SYSTEM)

    split = [r.getMessage() for r in caplog.records if "\nFORGED" in r.getMessage()
             or "\nforged" in r.getMessage()]
    assert not split, split
