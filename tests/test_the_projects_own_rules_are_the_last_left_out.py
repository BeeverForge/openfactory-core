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


# ── the other half of the project tier, and a profile's additions (review of #364) ───────────────

def _operator_and_budget_for_all_but_one(tmp_path: Path, monkeypatch, manifest: Manifest,
                                         files: dict[str, str], **kw):
    """Six operator standards, the project's `files`, and a budget one operator document short."""
    operator = _six_operator_documents(tmp_path)
    monkeypatch.setenv(og.ENV_VAR, str(operator))
    _write(tmp_path / "repo", files)
    built = ctx.build_context(manifest, tmp_path / "repo", _card(), knowledge_map="",
                              operator_root=str(operator.resolve()), **kw)
    built.prompt_budget = None
    built.prompt_budget = budgeted_bytes(built) - 7_900
    return fit_documents(built)


def test_a_components_guidelines_are_kept_before_the_operator_tier(tmp_path, monkeypatch):
    """`components.<name>.guidelines` are the project's own rules as much as `docs.guidelines`.
    The document is larger than one operator document, so drop-and-continue cannot fit it back in
    afterwards: only the priority keeps it."""
    manifest = Manifest(components={"api": {"path": "api/", "stack": "python",
                                            "guidelines": ["api/RULES.md"]}})
    fit = _operator_and_budget_for_all_but_one(
        tmp_path, monkeypatch, manifest, {"api/RULES.md": "# API rules\n" + "a" * 7_950})

    assert "api/RULES.md" in [d.path for d in fit.kept]
    assert {d.source for d in fit.left_out} == {ctx.OPERATOR}


def test_a_profiles_extension_is_left_out_before_the_operator_tier(tmp_path, monkeypatch):
    """A profile's `extend:` comes after the operator tier in the fill (ADR-0056): the deployment's
    standards outrank a class's additions, as they do in the cascade."""
    from openfactory.contracts.profile import Profile
    from openfactory.policy import profiles as prof

    profile = prof.ResolvedProfile([Profile.model_validate(
        {"name": "x", "guidelines": {"extend": ["docs/extra.md"]}})])
    fit = _operator_and_budget_for_all_but_one(
        tmp_path, monkeypatch, Manifest(), {"docs/extra.md": "# Extra\n" + "e" * 7_950},
        profile=profile)

    assert "docs/extra.md" in [d.path for d in fit.left_out]


# ── the diagnostic surfaces ask the box the job's way (review of #364) ──────────────────────────

def test_explain_gives_an_operator_document_the_fate_the_job_gives_it(tmp_path, monkeypatch):
    """`explain` pinned the operator tier on every box, so with the job leaving three operator
    standards out it told the developer the project's own `rules/house.md` was left out instead."""
    import yaml

    from openfactory.adapters.sandbox.worktree import WorktreeSandbox
    from openfactory.orchestrator import explain as ex
    from openfactory.orchestrator.machine import JobRunner

    operator = _six_operator_documents(tmp_path)
    monkeypatch.setenv(og.ENV_VAR, str(operator))
    monkeypatch.setenv("OPENFACTORY_SANDBOX", "worktree")
    repo = tmp_path / "repo"
    rules = {"rules/house.md": "# House\nReads go through the cache.\n" * 20}
    _write(repo, rules | {".openfactory/project.yaml": yaml.safe_dump(
        {"version": 1, "docs": {"guidelines": list(rules)}})})
    runner = JobRunner(tracker=object(), forge=object(), agent=object(),
                       sandbox=WorktreeSandbox(root=tmp_path / "wt"),
                       manifest=Manifest(docs={"guidelines": list(rules)}), repo_path=repo)
    whole = runner._build_context(ctx._BLANK_CARD)
    whole.prompt_budget = None
    monkeypatch.setenv("OPENFACTORY_PROMPT_BUDGET", str(budgeted_bytes(whole) - 2 * 7_900))
    job_left = {d.path for d in fit_documents(runner._build_context(ctx._BLANK_CARD)).left_out}
    assert job_left, "the job leaves nothing out"

    said = ex.explain(str(repo))

    explain_left = {line.split()[1] for line in said.splitlines() if "left out" in line}
    assert explain_left == job_left, (sorted(job_left), sorted(explain_left))


def test_doctor_asks_the_container_box_the_job_builds(tmp_path, monkeypatch):
    """The job's container box is built with the operator directory mounted (`factory.py`), and
    answers its mount; doctor built one without it, which answers nothing."""
    from openfactory import doctor
    from openfactory.adapters.sandbox.container import GUIDELINES_MOUNT

    monkeypatch.setenv(og.ENV_VAR, str(_six_operator_documents(tmp_path)))

    assert doctor._box_operator_root("container") == GUIDELINES_MOUNT


def test_box_prove_builds_its_box_with_the_operator_directory_the_job_mounts(tmp_path,
                                                                             monkeypatch):
    """The proof box is the job's box: built with the same `guidelines` knob, so the fit it
    reports leaves out what a pass would."""
    from types import SimpleNamespace

    from openfactory import box_prove
    from openfactory.adapters.sandbox import registry as sandboxes

    operator = _six_operator_documents(tmp_path)
    monkeypatch.setenv(og.ENV_VAR, str(operator))
    handed: list[dict] = []

    class _Box:
        def prepare(self, **_kw):
            return SimpleNamespace(path=str(tmp_path))

        def cleanup(self, **_kw):
            pass

    monkeypatch.setattr(sandboxes, "installed_box_traits",
                        lambda _kind: SimpleNamespace(honours_image=True))
    monkeypatch.setattr(sandboxes, "build_sandbox",
                        lambda *_a, **kw: handed.append(kw) or _Box())

    with box_prove.box_probes(SimpleNamespace(name="acme", box=None), "img", repo_path=tmp_path,
                              manifest=Manifest(), key="acme", sandbox="container"):
        pass

    assert handed and handed[0].get("guidelines") == str(operator), handed


def test_box_proves_fit_leaves_out_what_its_box_can_open(tmp_path, monkeypatch):
    """`box prove`'s fit asks ITS box where the operator directory opens: a box that answers a root
    lets the budget leave operator standards out, named at that root. Building the box with the
    knob (the test above) is half of it; under `operator_root=None` the fit pinned the operator
    tier on every box and reported the project's own guidelines left out where the job leaves the
    operator's out (second review of #364: that cut survived 358 tests)."""
    from types import SimpleNamespace

    from openfactory import box_prove
    from openfactory.adapters.sandbox import registry as sandboxes

    monkeypatch.setenv(og.ENV_VAR, str(_six_operator_documents(tmp_path)))
    monkeypatch.setenv(ctx.ENV_VAR_PROMPT_BUDGET, "20000")

    class _Box:
        def prepare(self, **_kw):
            return SimpleNamespace(path=str(tmp_path))

        def cleanup(self, **_kw):
            pass

        def guidelines_path(self, _host_dir):
            return "/opt/openfactory-guidelines"

    monkeypatch.setattr(sandboxes, "installed_box_traits",
                        lambda _kind: SimpleNamespace(honours_image=True))
    monkeypatch.setattr(sandboxes, "build_sandbox", lambda *_a, **_kw: _Box())
    with box_prove.box_probes(SimpleNamespace(name="acme", box=None), "img", repo_path=tmp_path,
                              manifest=Manifest(), key="acme", sandbox="container") as probes:
        _per_role, _note, fit = probes.inlined_documents()

    assert fit is not None and fit.left_out, "the box's root was not asked: the tier stayed pinned"
    assert {d.source for d in fit.left_out} == {ctx.OPERATOR}
    assert all(d.open_at.startswith("/opt/openfactory-guidelines/") for d in fit.left_out)


def test_explain_names_a_left_out_operator_document_where_the_box_opens_it(tmp_path, monkeypatch):
    """The fate says where to open it: the operator root the box answered, not the bare filename
    the operator tier addresses its documents by."""
    import yaml

    from openfactory.orchestrator import explain as ex

    operator = _six_operator_documents(tmp_path)
    monkeypatch.setenv(og.ENV_VAR, str(operator))
    monkeypatch.setenv("OPENFACTORY_SANDBOX", "worktree")
    monkeypatch.setenv("OPENFACTORY_PROMPT_BUDGET", "20000")
    repo = tmp_path / "repo"
    _write(repo, {".openfactory/project.yaml": yaml.safe_dump({"version": 1})})

    said = ex.explain(str(repo))

    left = [x for x in said.splitlines() if "left out" in x]
    assert left, said
    assert all(f"`{operator.resolve()}/standard-" in x for x in left), left


def test_the_jobs_box_is_built_with_the_operator_directory(tmp_path, monkeypatch):
    """The composition root's half of the same knob, read from the one place `box prove` and
    `doctor` read it (`operator_guidelines.box_knobs`): the box a job runs in is built with the
    operator directory, so a container box mounts it and answers where it opens."""
    from openfactory import factory
    from openfactory.contracts.project import Project, ProviderRef

    operator = _six_operator_documents(tmp_path)
    monkeypatch.setenv(og.ENV_VAR, str(operator))
    handed: list[dict] = []
    monkeypatch.setattr("openfactory.adapters.sandbox.registry.build_sandbox",
                        lambda *a, **kw: handed.append(kw) or object())
    monkeypatch.setattr(factory, "resolve_repo_path", lambda p, **kw: tmp_path)
    for seam in ("openfactory.adapters.tracker.registry.build_tracker",
                 "openfactory.adapters.forge.registry.build_forge",
                 "openfactory.adapters.agent.build_executor",
                 "openfactory.loader.load_manifest",
                 "openfactory.observability.registry.journal_for"):
        monkeypatch.setattr(seam, lambda *a, **kw: object())
    monkeypatch.setattr(factory, "notifier_for_project", lambda p: object())
    monkeypatch.setattr("openfactory.orchestrator.JobRunner", lambda **kw: kw)

    factory.build_runner(Project(name="books", repo_path=str(tmp_path),
                                 tracker=ProviderRef(kind="github", repo="acme/books")),
                         "1", sandbox="container", image="img", review=False)

    assert handed and handed[0].get("guidelines") == str(operator), handed


# ── the helpers' error paths (second review of #364) ─────────────────────────────────────────────

def test_a_configured_directory_that_is_not_there_is_not_mounted(tmp_path):
    """`box_knobs` is the one reader for the job, `box prove` and `doctor`: a configured directory
    that is not on disk is no knob, or `docker run -v` would create it on the host."""
    assert og.box_knobs({og.ENV_VAR: str(tmp_path / "missing")}) == {}


def test_a_configured_path_that_is_a_file_is_not_mounted(tmp_path):
    """A configured guidelines path that is a file, not a directory, is no knob either."""
    f = tmp_path / "standards.md"
    f.write_text("# not a directory\n")
    assert og.box_knobs({og.ENV_VAR: str(f)}) == {}


def test_a_box_that_cannot_be_built_here_pins_the_tier(tmp_path, monkeypatch):
    """A box this machine cannot build (a remote box, an add-on not installed) answers no root, so
    the tier stays pinned: `explain` and `doctor` print their report, not a traceback."""
    monkeypatch.setenv(og.ENV_VAR, str(_six_operator_documents(tmp_path)))

    assert og.deployment_root("no-such-box") is None


def test_explain_on_the_default_box_names_an_operator_document_at_the_mount(tmp_path, monkeypatch):
    """With no OPENFACTORY_SANDBOX the deployment runs the container box, which opens the
    operator directory at its mount: explain names a left-out standard there, as the prompt does.
    `test_explain_gives_an_operator_document_the_fate_the_job_gives_it` and
    `test_explain_names_a_left_out_operator_document_where_the_box_opens_it` set the worktree box,
    so asking "worktree" instead of the default box passed them while naming the host path the
    prompt never gives."""
    import yaml

    from openfactory.adapters.sandbox.container import GUIDELINES_MOUNT
    from openfactory.orchestrator import explain as ex

    monkeypatch.setenv(og.ENV_VAR, str(_six_operator_documents(tmp_path)))
    monkeypatch.delenv("OPENFACTORY_SANDBOX", raising=False)
    monkeypatch.setenv(ctx.ENV_VAR_PROMPT_BUDGET, "20000")
    repo = tmp_path / "repo"
    _write(repo, {".openfactory/project.yaml": yaml.safe_dump({"version": 1})})

    left = [x for x in ex.explain(str(repo)).splitlines() if "left out" in x]

    assert left and all(f"`{GUIDELINES_MOUNT}/standard-" in x for x in left), left
