"""#745: a proof refused because the same project is already being proven says so at every door.

`box_probes` refuses a second proof of a key already being proven (`ProveBusy`), so that it never
removes the box the first one is running in. A refusal no entry point catches is reached by
nothing (engineering lessons §1), and an exception out of `box_probes` reached the person as a
traceback (CONTRIBUTING, "Failures speak by name"). Three doors reach `box_probes` in this tree:
`openfactory box prove`, `openfactory box answer`, and onboarding's `_prove_in_box`.

What must be true (AC4): each door turns `ProveBusy` into its one sentence, naming the project,
saying a proof of it is already running and to run this again when that one ends; no traceback;
and nothing is recorded — a busy proof measured nothing, and a proof recorded as failed would hold
pickup.

`ProveBusy` is read off the module inside each test body, so that on a tree without it each test
FAILS for that reason instead of the module erroring at collection.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from openfactory import box_prove, cli
from tests.test_the_same_project_proved_twice_at_once_is_refused_not_deleted import (
    _another_process_holding,
    _repository,
)


def _busy(monkeypatch, refusal) -> list:
    """`box_probes` refusing with `refusal`, and a spy on every place a proof is recorded."""
    recorded: list = []

    @contextlib.contextmanager
    def busy_box(*_a, **_kw):
        raise refusal
        yield  # pragma: no cover — a generator, so `with` can enter it

    monkeypatch.setattr(box_prove, "box_probes", busy_box)
    monkeypatch.setattr(box_prove, "prove", lambda *a, **k: recorded.append(("prove", a)))
    monkeypatch.setattr(box_prove, "save", lambda *a, **k: recorded.append(("save", a)))
    return recorded


def _cli_door(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_get_project", lambda name: SimpleNamespace(name=name, box=None))
    monkeypatch.setattr(cli, "resolve_box_image", lambda *_a, **_kw: "img")
    monkeypatch.setattr(cli, "_box_kind", lambda _explicit: "container")


def _says_it_in_one_sentence(result, refusal) -> None:
    sentence = refusal.sentence
    assert "acme" in sentence and "already running" in sentence and "again" in sentence, (
        f"the refusal does not name the project, the cause and the remedy: {sentence!r}")
    assert result.exit_code != 0, result.output
    assert not isinstance(result.exception, box_prove.ProveBusy), (
        f"ProveBusy escaped the command as a traceback: {result.exception!r}")
    assert sentence in [line.strip() for line in result.output.splitlines()], result.output
    assert "Traceback" not in result.output, result.output


def test_box_prove_says_the_proof_is_running_and_records_nothing(monkeypatch):
    """`openfactory box prove acme` while acme is being proven. Before: no `ProveBusy` at all."""
    refusal = box_prove.ProveBusy("acme")
    recorded = _busy(monkeypatch, refusal)
    _cli_door(monkeypatch)

    result = CliRunner().invoke(cli.app, ["box", "prove", "acme"])

    _says_it_in_one_sentence(result, refusal)
    assert recorded == [], f"a refused proof was proven or recorded: {recorded}"


def test_a_refused_ref_proof_leaves_the_running_proofs_checkout_alone(tmp_path, monkeypatch):
    """`openfactory box prove acme --ref feat` while a `--ref feat` proof of acme runs. Before
    (review of #745, git 2.43.0, 2026-10-21): the `--ref` checkout was resolved before the key was
    taken, so `factory._worktree_at` removed and re-added `<cache>/worktrees/acme@feat` — the tree
    the running proof reads — and only then said `already running` (`sentinel exists: False`)."""
    import subprocess

    from openfactory import factory, loader

    monkeypatch.setattr(box_prove, "PROOF_DIR", tmp_path / "proofs")
    monkeypatch.setenv("OPENFACTORY_REPO_CACHE", str(tmp_path / "cache"))
    repo = _repository(tmp_path / "acme")
    subprocess.run(["git", "-C", str(repo), "branch", "feat"], check=True, capture_output=True)
    first = factory._worktree_at(repo, "feat", "acme@feat")  # the running proof's checkout
    sentinel = first / "the-first-proof-reads-here"
    sentinel.write_text("live\n")
    holder = _another_process_holding("acme", tmp_path / "proofs")
    monkeypatch.setattr(cli, "_get_project",
                        lambda _n: SimpleNamespace(name="acme", repo_path=str(repo), box=None))
    monkeypatch.setattr(cli, "resolve_box_image", lambda *_a, **_kw: "img")
    monkeypatch.setattr(cli, "_box_kind", lambda _explicit: "container")
    monkeypatch.setattr(loader, "load_manifest", lambda *_a, **_kw: SimpleNamespace(
        base_branch="main", setup=[], validation={}))
    try:
        result = CliRunner().invoke(cli.app, ["box", "prove", "acme", "--ref", "feat"])
    finally:
        holder.kill()
        holder.wait()

    assert "already running" in result.output, result.output
    assert sentinel.exists(), (
        "the refused --ref proof removed the running proof's checkout before it was refused")




def test_a_refused_ref_proof_of_another_repository_leaves_its_checkout_alone(tmp_path, monkeypatch):
    """`openfactory box prove acme --repo org/web --ref feat` while that repository's `--ref` proof
    runs. The key the command takes before the checkout is the REPOSITORY's (`proof_key`), the one
    the checkout `<key>@<ref>` and `box_probes` use, not the project's name. Review round 2 of #745
    (2026-10-21): with the hold taken on `name`, the command locked `acme`, removed and re-added
    `<cache>/worktrees/acme--org--web@feat` under the running proof, and only then was refused by
    `box_probes`; the one `--ref` test ran without `--repo`, so nothing noticed."""
    import subprocess

    from openfactory import factory, loader
    from openfactory.runtime import card_repo

    monkeypatch.setattr(box_prove, "PROOF_DIR", tmp_path / "proofs")
    monkeypatch.setenv("OPENFACTORY_REPO_CACHE", str(tmp_path / "cache"))
    repo = _repository(tmp_path / "web")
    subprocess.run(["git", "-C", str(repo), "branch", "feat"], check=True, capture_output=True)
    first = factory._worktree_at(repo, "feat", "acme--org--web@feat")
    sentinel = first / "the-first-proof-reads-here"
    sentinel.write_text("live\n")
    holder = _another_process_holding("acme--org--web", tmp_path / "proofs")
    view = SimpleNamespace(name="acme", repo_path=str(repo), box=None)
    monkeypatch.setattr(cli, "_get_project", lambda _n: SimpleNamespace(name="acme", box=None))
    monkeypatch.setattr(card_repo, "_runner_view", lambda _p, _r: (view, "acme--org--web"))
    monkeypatch.setattr(cli, "resolve_box_image", lambda *_a, **_kw: "img")
    monkeypatch.setattr(cli, "_box_kind", lambda _explicit: "container")
    monkeypatch.setattr(loader, "load_manifest", lambda *_a, **_kw: SimpleNamespace(
        base_branch="main", setup=[], validation={}))
    try:
        result = CliRunner().invoke(
            cli.app, ["box", "prove", "acme", "--repo", "org/web", "--ref", "feat"])
    finally:
        holder.kill()
        holder.wait()

    assert "already running" in result.output, result.output
    assert sentinel.exists(), (
        "the refused --ref proof of org/web removed the running proof's checkout before it was refused")


def test_box_answer_says_the_proof_is_running(monkeypatch):
    """`openfactory box answer acme` while acme is being proven: one sentence, and no spend
    recorded for a call nobody made."""
    from openfactory.adapters.agent import registry
    from openfactory.adapters.agent.codex import CodexAdapter
    from openfactory.observability import job_record

    refusal = box_prove.ProveBusy("acme")
    recorded = _busy(monkeypatch, refusal)
    _cli_door(monkeypatch)
    monkeypatch.setattr(registry, "build_executor", lambda _project: CodexAdapter())
    monkeypatch.setattr(job_record, "record_one_pass",
                        lambda **kw: recorded.append(("record_one_pass", kw)))

    result = CliRunner().invoke(cli.app, ["box", "answer", "acme"])

    _says_it_in_one_sentence(result, refusal)
    assert recorded == [], f"a refused proof recorded something: {recorded}"


def test_onboarding_says_skipped_with_the_sentence_and_saves_nothing(monkeypatch, tmp_path):
    """Onboarding never blocks on its proof: a busy one is `skipped:` with the sentence, so the
    pull request body says why, and no proof is saved under the key."""
    from openfactory import factory
    from openfactory.onboarding import onboard

    refusal = box_prove.ProveBusy("acme")
    recorded = _busy(monkeypatch, refusal)
    monkeypatch.setattr(factory, "resolve_box_image", lambda *_a, **_kw: "img")
    manifest = SimpleNamespace(base_branch="main", setup=[], validation={})

    answer = onboard._prove_in_box(SimpleNamespace(name="acme", box=None), "acme",
                                   Path(tmp_path), manifest, sandbox="container", stream=None)

    assert answer == (f"skipped: {refusal.sentence}", [], []), answer
    assert recorded == [], f"a refused proof was proven or saved: {recorded}"


def test_onboarding_says_the_whole_sentence_for_a_long_project_name(monkeypatch, tmp_path):
    """Onboarding's generic refusal keeps the first 160 characters of an error, and the busy
    sentence is 113 characters plus the key: for a key of 48 characters or more it lost the
    remedy (measured on the generic path). A busy proof says its whole sentence whatever the key."""
    from openfactory import factory
    from openfactory.onboarding import onboard

    key = "acme-" + "storefront-" * 5  # 60 characters, a `_checkout_key`-length name
    refusal = box_prove.ProveBusy(key)
    recorded = _busy(monkeypatch, refusal)
    monkeypatch.setattr(factory, "resolve_box_image", lambda *_a, **_kw: "img")
    manifest = SimpleNamespace(base_branch="main", setup=[], validation={})

    answer = onboard._prove_in_box(SimpleNamespace(name=key, box=None), key,
                                   Path(tmp_path), manifest, sandbox="container", stream=None)

    assert answer == (f"skipped: {refusal.sentence}", [], []), answer
    assert recorded == [], f"a refused proof was proven or saved: {recorded}"
