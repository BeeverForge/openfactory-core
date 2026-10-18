"""Every document the budget leaves out, or cuts, is named by path inside the prompt the agent reads
(#364, ADR-0056).

The issue's criterion is that a drop which is only a worker stderr warning is a failure of the card.
#359 dropped 44 of 54 records with one log line per document and nothing in the prompt, and the
agent worked as if those records did not exist. `_MAX_DOC_CHARS` had done the same to one document
at a time since it was written: an 8,000-character cut of a 14,000-character record reached the
agent with no word that it ended early, and `openfactory explain` called it "inlined in full".

So the brief carries a notice inside the AUTHORITATIVE section. It names each document left out by
the path the agent can open it at, and each document cut by how much was inlined. The notice reaches
the CLI on all four harnesses, and `explain` gives each document the same fate in both languages.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from openfactory.adapters.agent.base import (
    AgentContext,
    budgeted_bytes,
    fit_documents,
    ticket_brief,
)
from openfactory.adapters.agent.claude_code import ClaudeCodeAdapter
from openfactory.adapters.agent.codex import CodexAdapter
from openfactory.adapters.agent.kimi import KimiAdapter
from openfactory.adapters.agent.opencode import OpenCodeAdapter
from openfactory.adapters.sandbox.base import Workspace
from openfactory.contracts import Manifest, Ticket
from openfactory.orchestrator import context as ctx

VARIABLE = "OPENFACTORY_PROMPT_BUDGET"
#: The heading the notice opens with, inside `## Declared by this project — AUTHORITATIVE`.
NOTICE = "### Declared and not inlined here"


def _card() -> Ticket:
    return Ticket(id="#41", title="feature", objective="add a feature", repo="o/app")


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def _the_notice(brief: str) -> str:
    """The notice block: from its heading to the next heading of its level or above."""
    assert NOTICE in brief, "the brief carries no notice"
    rest = brief[brief.index(NOTICE):]
    ends = [i for i in (rest.find("\n### ", 1), rest.find("\n## ", 1)) if i != -1]
    return rest[:min(ends)] if ends else rest


def _a_project_that_leaves_one_out(root: Path) -> AgentContext:
    """`CONTRIBUTING.md` (first line `# Contributing`) and one record, under a budget with room
    for the guideline and not for the record."""
    _write(root, {"CONTRIBUTING.md": "# Contributing\nRun the suite in both orders.\n",
                  "docs/adr/0003-money-is-decimal.md": "# Money is Decimal\n" + "m" * 6_000})
    built = ctx.build_context(Manifest(docs={"constraints": "docs/adr/*.md",
                                             "guidelines": ["CONTRIBUTING.md"]}),
                              root, _card(), knowledge_map="")
    built.prompt_budget = None
    built.prompt_budget = budgeted_bytes(built) - 1
    return built


def test_every_left_out_document_is_named_by_its_path_in_the_brief(tmp_path):
    built = _a_project_that_leaves_one_out(tmp_path)

    left_out = fit_documents(built).left_out
    notice = _the_notice(ticket_brief(built))

    assert [d.path for d in left_out] == ["docs/adr/0003-money-is-decimal.md"]
    for doc in left_out:
        assert (tmp_path / doc.open_at).is_file(), f"{doc.open_at} cannot be opened in the checkout"
        assert f"`{doc.open_at}`" in notice
    assert f"{built.prompt_budget:,}" in notice and VARIABLE in notice, (
        "the notice does not say which budget left them out, or where it is set")


def test_the_name_is_the_path_not_the_first_line(tmp_path):
    _write(tmp_path, {"CONTRIBUTING.md": "# Contributing\n" + "c" * 6_000,
                      "rules/small.md": "# Small\nKeep it small.\n"})
    built = ctx.build_context(Manifest(docs={"guidelines": ["rules/small.md",
                                                            "CONTRIBUTING.md"]}),
                              tmp_path, _card(), knowledge_map="")
    built.prompt_budget = None
    built.prompt_budget = budgeted_bytes(built) - 1

    notice = _the_notice(ticket_brief(built))

    assert "`CONTRIBUTING.md`" in notice
    assert "Contributing" not in notice.replace("CONTRIBUTING.md", ""), notice


def test_an_operator_document_is_named_where_the_box_can_open_it(tmp_path, monkeypatch):
    from openfactory.orchestrator import operator_guidelines as og

    central = tmp_path / "central"
    _write(central, {"security.md": "# Security\n" + "s" * 6_000})
    monkeypatch.setenv(og.ENV_VAR, str(central))
    built = ctx.build_context(Manifest(), tmp_path / "repo", _card(), knowledge_map="",
                              operator_root="/openfactory/guidelines")
    built.prompt_budget = None
    built.prompt_budget = budgeted_bytes(built) - 1

    assert "`/openfactory/guidelines/security.md`" in _the_notice(ticket_brief(built))


def test_a_truncated_document_is_named_with_how_much_was_inlined(tmp_path):
    """With no budget at all: a cut is named even when nothing is left out."""
    long_record = "docs/adr/0009-a-long-record.md"
    _write(tmp_path, {long_record: "r" * 9_000})
    built = ctx.build_context(Manifest(docs={"constraints": "docs/adr/*.md"}), tmp_path, _card(),
                              knowledge_map="")
    built.prompt_budget = None

    notice = _the_notice(ticket_brief(built))
    line = next(x for x in notice.splitlines() if long_record in x)

    assert f"{ctx._MAX_DOC_CHARS:,}" in line and f"{9_000:,}" in line, line
    assert fit_documents(built).left_out == []
    assert [d.path for d in fit_documents(built).truncated] == [long_record]


# ── the notice reaches every harness's CLI ───────────────────────────────────────────────────────

class _Recorder:
    """A box with the staging channel, recording what was staged and what reached the command —
    the seam `test_a_large_prompt_travels_off_the_command_line.py` uses."""

    def __init__(self) -> None:
        self.staged: list[str] = []
        self.commands: list[str] = []

    def harness_path(self, name: str) -> str:
        return name

    def stage_input(self, *, workspace, text: str):  # noqa: ARG002
        self.staged.append(text)
        return f"/tmp/openfactory-input/prompt-{len(self.staged)}.txt"

    def run(self, *, workspace, command: str, timeout: int):  # noqa: ARG002
        self.commands.append(command)
        return 0, ""


_HARNESSES = {"claude_code": lambda: ClaudeCodeAdapter(model="opus"),
              "codex": lambda: CodexAdapter(model="gpt-5"),
              "kimi": lambda: KimiAdapter(model="kimi-k2"),
              "opencode": lambda: OpenCodeAdapter(model="anthropic/claude-opus-5")}


@pytest.mark.parametrize("harness", sorted(_HARNESSES))
def test_every_harness_hands_its_cli_the_notice(harness, tmp_path):
    built = _a_project_that_leaves_one_out(tmp_path)
    built.allowed_tools = ["Read", "Edit", "Bash"]
    ws = Workspace(path="/work", branch="b", base_branch="main")

    for door in ("execute", "repair"):
        box = _Recorder()
        adapter = _HARNESSES[harness]()
        if door == "execute":
            adapter.execute(sandbox=box, workspace=ws, context=built)
        else:
            adapter.repair(sandbox=box, workspace=ws, context=built, failure_log="1 failed")
        handed = "\n".join(box.staged + box.commands)
        assert NOTICE in handed, f"{harness}'s {door} prompt carries no notice"
        assert "docs/adr/0003-money-is-decimal.md" in handed


# ── explain says the same fate ───────────────────────────────────────────────────────────────────

def _explain(target: Path, language: str, monkeypatch) -> str:
    from openfactory import cli

    monkeypatch.setattr(cli, "_load_environment", lambda: None)
    result = CliRunner().invoke(cli.app, ["explain", str(target), "--language", language])
    assert result.exit_code == 0, result.output
    return result.output


@pytest.mark.parametrize("language,left_out,truncated", [
    ("en", "left out — over the {budget}-byte prompt budget",
     "inlined up to {cut} of {whole} characters"),
    ("pt-BR", "deixado de fora — acima do orçamento de {budget} bytes",
     "incluído até {cut} de {whole} caracteres"),
])
def test_explain_says_what_the_budget_left_out_and_what_it_truncated(
        tmp_path, monkeypatch, language, left_out, truncated):
    import yaml

    _write(tmp_path, {".openfactory/project.yaml": yaml.safe_dump(
        {"version": 1, "docs": {"constraints": "docs/adr/*.md"}}),
        "docs/adr/0001-old.md": "o" * 20_000,
        "docs/adr/0002-new.md": "n" * 9_000})
    # the newest record (9,000 characters, cut to 8,000) fits; the older one does not
    whole = budgeted_bytes(ctx.build_context(
        Manifest(docs={"constraints": "docs/adr/*.md"}), tmp_path, ctx._BLANK_CARD,
        knowledge_map=""))
    budget = whole - 4_000
    monkeypatch.setenv(VARIABLE, str(budget))

    said = _explain(tmp_path, language, monkeypatch)

    sep = "." if language == "pt-BR" else ","
    number = lambda n: f"{n:,}".replace(",", sep)  # noqa: E731
    old = next(x for x in said.splitlines() if "docs/adr/0001-old.md" in x)
    new = next(x for x in said.splitlines() if "docs/adr/0002-new.md" in x)
    assert left_out.format(budget=number(budget)) in old, old
    assert truncated.format(cut=number(ctx._MAX_DOC_CHARS), whole=number(9_000)) in new, new
    assert "inlined in full" not in said and "incluído inteiro" not in said


def test_a_cut_operator_document_is_named_where_the_rest_can_be_opened(tmp_path, monkeypatch):
    """An operator document's `path` is a bare filename, which opens nothing in the checkout: the
    line about its cut says where the rest is, at the root the box answered."""
    from openfactory.orchestrator import operator_guidelines as og

    central = tmp_path / "central"
    _write(central, {"security.md": "s" * 9_000})
    monkeypatch.setenv(og.ENV_VAR, str(central))
    built = ctx.build_context(Manifest(), tmp_path / "repo", _card(), knowledge_map="",
                              operator_root="/openfactory/guidelines")
    built.prompt_budget = None

    line = next(x for x in _the_notice(ticket_brief(built)).splitlines() if "security.md" in x)

    assert "the rest is at `/openfactory/guidelines/security.md`" in line, line
