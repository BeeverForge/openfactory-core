"""The budget is filled from the project's own rules first, so they are the last thing left out
(#364, ADR-0056).

#359, a cap per role, measured the inversion this guards against. With six operator documents of
about 7.9 KB, the operator tier filled the room and the project's own guidelines were the ones
dropped, so the deployment's general standards displaced the rules written for this repository.
It also kept ADR-0007 ("partly superseded by ADR-0010") and dropped ADR-0010, because the fill ran
in glob order.

The fill runs project guidelines first, then decision records newest first, then the operator
tier, then a profile's additions. The framework baseline is never left out (ADR-0056, "What the
agent cannot open"). What is kept is rendered in the original order, so the project still has the
last word.
"""

from __future__ import annotations

from pathlib import Path

from openfactory.adapters.agent.base import budgeted_bytes, fit_documents, ticket_brief
from openfactory.contracts import Manifest, Ticket
from openfactory.orchestrator import context as ctx
from openfactory.orchestrator import operator_guidelines as og


def _card() -> Ticket:
    return Ticket(id="#41", title="feature", objective="add a feature", repo="o/app")


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def _six_operator_documents(root: Path) -> Path:
    directory = root / "central"
    _write(directory, {f"standard-{i}.md": f"# Central standard {i}\n" + f"{i}" * 7_900
                       for i in range(6)})
    return directory


_PROJECT_RULES = {"rules/house.md": "# House rules\nReads go through the cache layer.\n" * 20,
                  "rules/money.md": "# Money\nMoney is Decimal, never float.\n" * 20}
_MANIFEST = Manifest(docs={"guidelines": list(_PROJECT_RULES)})


def _room_for_four_of_six(context) -> int:
    """A budget that holds the baseline, both project guidelines and four operator documents."""
    context.prompt_budget = None
    whole = budgeted_bytes(context)
    return whole - 2 * 7_900


def _assert_the_project_wins(context, operator_root: str) -> None:
    brief = ticket_brief(context)
    for text in _PROJECT_RULES.values():
        assert text in brief, "a project guideline was left out while the operator's were kept"
    left_out = fit_documents(context).left_out
    assert left_out, "nothing was left out: the budget held all six operator documents"
    assert {d.source for d in left_out} == {ctx.OPERATOR}, [d.path for d in left_out]
    named = [d.open_at for d in left_out]
    assert all(at.startswith(f"{operator_root}/standard-") for at in named), named
    for at in named:
        assert f"`{at}`" in brief, f"{at} was left out and the prompt does not name it"
    assert budgeted_bytes(context) <= context.prompt_budget


def test_a_six_document_operator_directory_keeps_both_project_guidelines(tmp_path, monkeypatch):
    operator = _six_operator_documents(tmp_path)
    monkeypatch.setenv(og.ENV_VAR, str(operator))
    _write(tmp_path / "repo", _PROJECT_RULES)
    root = str(operator.resolve())

    built = ctx.build_context(_MANIFEST, tmp_path / "repo", _card(), knowledge_map="",
                              operator_root=root)
    built.prompt_budget = _room_for_four_of_six(built)

    _assert_the_project_wins(built, root)


def test_the_job_runner_builds_that_context_with_the_operator_root_its_box_answers(
        tmp_path, monkeypatch):
    """The same measurement through the context a real `JobRunner` builds, on a worktree box: the
    box answers where the operator directory is, so those documents can be left out and named. A
    runner that did not ask would pin them, and the project's guidelines would be left out."""
    from openfactory.adapters.sandbox.worktree import WorktreeSandbox
    from openfactory.orchestrator.machine import JobRunner

    operator = _six_operator_documents(tmp_path)
    monkeypatch.setenv(og.ENV_VAR, str(operator))
    _write(tmp_path / "repo", _PROJECT_RULES)
    runner = JobRunner(tracker=object(), forge=object(), agent=object(),
                       sandbox=WorktreeSandbox(root=tmp_path / "wt"), manifest=_MANIFEST,
                       repo_path=tmp_path / "repo")

    built = runner._build_context(_card())
    built.prompt_budget = _room_for_four_of_six(built)

    _assert_the_project_wins(built, str(operator.resolve()))


def test_the_newest_decision_record_is_kept_before_the_one_it_supersedes(tmp_path):
    _write(tmp_path, {"docs/adr/0007-the-floor-frees-at-merge.md": "# 0007\n" + "s" * 5_000,
                      "docs/adr/0010-single-line-strict.md": "# 0010\n" + "n" * 5_000})
    built = ctx.build_context(Manifest(docs={"constraints": "docs/adr/*.md"}), tmp_path, _card(),
                              knowledge_map="")
    built.prompt_budget = None
    built.prompt_budget = budgeted_bytes(built) - 1

    fit = fit_documents(built)

    assert [d.path for d in fit.kept if d.source == "docs.constraints"] == [
        "docs/adr/0010-single-line-strict.md"]
    assert [d.path for d in fit.left_out] == ["docs/adr/0007-the-floor-frees-at-merge.md"]


def test_the_kept_documents_keep_the_order_that_gives_the_project_the_last_word(
        tmp_path, monkeypatch):
    """Filled project first, rendered in the cascade's order: framework, operator, project — and
    the decision records in their own order — whatever order they were added in."""
    operator = tmp_path / "central"
    _write(operator, {"a-standard.md": "# Operator A\nOPERATOR-A\n",
                      "b-standard.md": "# Operator B\nOPERATOR-B\n"})
    monkeypatch.setenv(og.ENV_VAR, str(operator))
    repo = tmp_path / "repo"
    _write(repo, {"rules/first.md": "PROJECT-FIRST\n", "rules/second.md": "PROJECT-SECOND\n",
                  "adr/0001-a.md": "RECORD-0001\n" + "1" * 3_000,
                  "adr/0002-b.md": "RECORD-0002\n" + "2" * 3_000,
                  "adr/0003-c.md": "RECORD-0003\n" + "3" * 3_000})
    manifest = Manifest(docs={"constraints": "adr/*.md",
                              "guidelines": ["rules/first.md", "rules/second.md"]})
    built = ctx.build_context(manifest, repo, _card(), knowledge_map="",
                              operator_root=str(operator.resolve()))
    built.prompt_budget = None
    built.prompt_budget = budgeted_bytes(built) - 1  # the oldest record is left out

    brief = ticket_brief(built)
    framework = (ctx.ORG_DEFAULTS_DIR / sorted(p.name for p in ctx.ORG_DEFAULTS_DIR.glob("*.md"))[
        -1]).read_text()[:200]
    order = [brief.index(marker) for marker in
             ("RECORD-0002", "RECORD-0003", framework, "OPERATOR-A", "OPERATOR-B",
              "PROJECT-FIRST", "PROJECT-SECOND")]
    assert order == sorted(order), "the kept documents are not in the cascade's order"
    assert "RECORD-0001" not in brief
