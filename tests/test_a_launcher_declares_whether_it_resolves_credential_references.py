"""A remote box's launcher declares whether it resolves credential references itself (#903).

Criterion 1 of #903: "The launcher contract has the declaration, and the shipped rows are tested
against it."

WHAT THE CONTRACT SAID BEFORE. `RemoteBox.launch` (`openfactory/adapters/sandbox/registry.py`)
takes the credentials as VALUES in `extra_env`, and a launcher may copy that environment where
others can read it (an ECS `RunTask` override is read back by `DescribeTasks`). #822 closed the hole
by refusing a secret the credential store holds for EVERY remote box, in a sentence that says "no
launcher declares it", and nothing in the contract let a launcher declare it. Measured on #822's
head (`cf7ec0f5`, 2026-10-21): the registry exports no `resolves_references`, no
`ResolvesReferences` and no `launcher_receives`, and `_checked_runner` admits a runner that claims
the declaration while its `launch` cannot take a single reference.

WHY NOT A TRAIT. `BoxTraits` is stamped into workflow histories as data (`io.JobParams.box`), and
every field of it is required: a new one would break both the histories stamped before it and
every add-on's `box` row. The declaration is asked of the RUNNER, on the activity side, which is
the only side that hands credentials over.

THE ROWS ARE DERIVED. Every kind the registry knows (`plugins.known`) once the stranger's real
distribution is installed (`tests/stranger_addon.py`) must be answered, so a row that joins
without an answer here fails by name rather than passing unasked.
"""

from __future__ import annotations

import pytest
import stranger_addon
from vendor_addons import install

from openfactory import plugins
from openfactory.adapters.sandbox import registry
from openfactory.adapters.sandbox.timeouts import LAUNCHER_TIMEOUT

#: What `launcher_receives(kind)` answers for every row there is with the stranger installed and
#: none of the platform's own add-ons (the public tree has no `openfactory-aws`). `fargate` is
#: "not installed" and NOT "values": "could not see the launcher" and "the launcher declares
#: nothing" are two facts, and one value for both would tell a deployment that has the add-on
#: the wrong thing about it (docs/engineering-lessons.md §2).
EXPECTED = {
    "worktree": "local",
    "container": "local",
    "fargate": "not installed",
    stranger_addon.KIND: "local",
    # `AcmeRunner.launch` takes no `references` and its class declares nothing: the launcher
    # every add-on wrote before this contract existed, which must keep being admitted.
    stranger_addon.REMOTE_KIND: "values",
}


class _Point:
    """One entry point, as `importlib.metadata` hands them over, loading the object it holds."""

    def __init__(self, name, value):
        self.name, self._value = name, value

    def load(self):
        return self._value


class _Tail:
    def fetch_new(self):
        return []


class _TakesReferences:
    """A launcher whose `launch` takes the keyword-only `references` the contract adds."""

    resolves_references: object = True

    def launch(self, box, *, journal=None, variant="", extra_env=None,
               timeout=LAUNCHER_TIMEOUT, run_id=None, references=None):
        raise AssertionError("this test never launches")

    def stop(self, box):
        return 0

    def tail(self, project, issue):
        return _Tail()


class _TakesNoReferences:
    """A launcher that CLAIMS the declaration while its `launch` is today's: handed a reference,
    it would raise `TypeError` inside the first job instead of at the door."""

    resolves_references = True

    def launch(self, box, *, journal=None, variant="", extra_env=None,
               timeout=LAUNCHER_TIMEOUT, run_id=None):
        raise AssertionError("this test never launches")

    def stop(self, box):
        return 0

    def tail(self, project, issue):
        return _Tail()


def _serve_remote_runner(tmp_path, monkeypatch, runner) -> str:
    """Install the stranger's real distribution, then serve its rows with `runner` in place of
    its own `box_runner` entry point. Returns the remote kind the runner answers for."""
    stranger_addon.installed(tmp_path, monkeypatch)
    own_runner = f"{registry.RUNNER_AXIS}.{stranger_addon.REMOTE_KIND}"
    points = [p for p in stranger_addon.points() if p.name != own_runner]
    install(monkeypatch, declared_rows=False,
            extra=tuple(points) + (_Point(own_runner, lambda **_kw: runner),))
    return stranger_addon.REMOTE_KIND


def test_every_shipped_box_row_answers_whether_its_launcher_is_handed_references(
        tmp_path, monkeypatch):
    """Every row there is (the core's and a stranger's) is asked, and a local box is no launcher.

    Before #903 there was nothing to ask: `launcher_receives` did not exist, so a doctor or a
    reader of the registry could not say whether a remote row's launcher is handed references or
    values (measured on `cf7ec0f5`)."""
    stranger_addon.installed(tmp_path, monkeypatch)
    install(monkeypatch, declared_rows=False, extra=tuple(stranger_addon.points()))
    known = set(plugins.known(registry.AXIS, registry.BOXES))
    assert known == set(EXPECTED), (
        f"the rows the registry knows are {sorted(known)} and this test answers for "
        f"{sorted(EXPECTED)}: a row that joins must say what its launcher is handed")
    answers = {kind: registry.launcher_receives(kind) for kind in sorted(known)}
    assert answers == EXPECTED


def test_a_launcher_that_declares_and_takes_references_is_handed_references(
        tmp_path, monkeypatch):
    """`resolves_references = True` and a `launch` with a `references` keyword is the declaration,
    and it is the only thing that makes a launcher one that is handed references."""
    runner = _TakesReferences()
    kind = _serve_remote_runner(tmp_path, monkeypatch, runner)
    assert isinstance(runner, registry.ResolvesReferences)
    assert registry.resolves_references(runner) is True
    assert registry.RESOLVES_REFERENCES_ATTR == "resolves_references"
    assert registry.remote_box(kind) is runner
    assert registry.launcher_receives(kind) == "references"


@pytest.mark.parametrize("claim", ["yes", "True", 1, [True], False, None],
                         ids=["the-string-yes", "the-string-True", "the-integer-1",
                              "a-truthy-list", "False", "None"])
def test_only_a_literal_true_is_a_declaration(claim, tmp_path, monkeypatch):
    """A truthy value that is not `True` declares nothing, so the launcher is handed values.

    A declaration read by truthiness would hand a stored secret's reference to a launcher whose
    author wrote `resolves_references = "no"` and meant it."""
    runner = _TakesReferences()
    runner.resolves_references = claim
    kind = _serve_remote_runner(tmp_path, monkeypatch, runner)
    assert registry.resolves_references(runner) is False
    assert registry.launcher_receives(kind) == "values"


def test_a_launcher_that_declares_but_cannot_take_references_is_refused_by_name(
        tmp_path, monkeypatch):
    """A runner that declares while its `launch` lacks the `references` keyword is refused when
    it is built, by a sentence naming the box and the keyword.

    On `cf7ec0f5` `_checked_runner` checks only `isinstance(runner, RemoteBox)`, which a runtime
    Protocol answers by method NAMES: it admitted this runner, and the first job that handed it a
    reference would have raised `TypeError` inside `launch` (docs/engineering-lessons.md §3)."""
    kind = _serve_remote_runner(tmp_path, monkeypatch, _TakesNoReferences())
    with pytest.raises(TypeError) as refused:
        registry.remote_box(kind)
    sentence = str(refused.value)
    assert repr(kind) in sentence or f"`{kind}`" in sentence, sentence
    assert "references" in sentence, sentence
