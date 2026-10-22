"""Every remote launch site, not only the job's, hands a declaring launcher the reference (#903).

Criterion 3 of #903, on every path a remote box is launched from: "With the declaration, the
launcher receives the reference". `_remote_launch`'s docstring says the job, a promotion phase, a
re-review and a CI repair or adjustment all come through it, so what a launcher is handed cannot
differ between them; this module holds the three sites other than the job's to that.

WHAT NOTHING HELD BEFORE. Measured in the review of `17b05b8f` (2026-10-22): every #903 test drove
only `_run_remote`. Building `_run_promotion`'s box without `references=`, or having
`_run_review_pass` or `_run_ci_repair` call `remote_box(...).launch(box({}), ...)` directly, left
all 671 tests that name those sites green. Under the first, a declaring launcher is handed
`OPENFACTORY_BOX_FORGE_TOKEN` while the promotion box still reads the project's `token_env`, a
name the launcher's machine does not fill, so the box fails inside with a 401.

EACH SITE IS DRIVEN FOR REAL, with the same declaring launcher as criterion 3's module: a
promotion phase, a re-review, and the adjust path of a CI repair (a person's words, so no CI gate
is asked). What follows the launch (reading the PR, the rerun decision) is not this module's
question; the launch is recorded before it.
"""

from __future__ import annotations

import pytest
from test_a_launcher_that_resolves_references_is_handed_the_reference import (  # noqa: F401
    SECRET,
    _held_on_both_sides,
    launcher,
)

from openfactory import credentials
from openfactory.adapters.credential_store import registry as store_registry
from openfactory.contracts import RunResult
from openfactory.runtime.temporal import activities as acts
from openfactory.runtime.temporal.io import CiRepairInput, ReviewPassInput

SITES = {
    "promotion": lambda kind: acts._run_promotion("deskline", "7", "staging", {}, "run-903",
                                                  sandbox=kind),
    "review": lambda kind: acts._run_review_pass(
        ReviewPassInput(project="deskline", issue="7", pr_url="https://x/pull/1", sandbox=kind),
        "run-903"),
    "adjust": lambda kind: acts._run_ci_repair(
        CiRepairInput(project="deskline", issue="7", pr_url="https://x/pull/1", sandbox=kind),
        "run-903", ci_log="a person's words"),
}


@pytest.mark.parametrize("site", sorted(SITES))
def test_the_site_hands_the_reference_and_the_box_reads_the_variable(
        site, launcher, monkeypatch):  # noqa: F811 — the fixture imported above
    project = _held_on_both_sides("forge", "token_env-a-reference", store_registry.FILE,
                                  launcher, monkeypatch)
    monkeypatch.setattr(acts, "ProjectRegistry",
                        lambda: type("R", (), {"get": lambda self, _n: project})())
    real = launcher.runner.launch

    def launch(box, **kw):
        real(box, **kw)
        return RunResult(ok=True)

    monkeypatch.setattr(launcher.runner, "launch", launch)
    try:
        SITES[site](launcher.kind)
    except Exception:  # noqa: BLE001 — what follows the launch is not this test's question
        pass
    (launched,) = launcher.runner.launches
    variable = credentials.BOX_TOKEN_ENV["forge"]
    assert launched["references"] == {variable: "file:acme-axis-token"}
    assert launched["box"].forge_options["token_env"] == variable
    assert SECRET not in repr(launched["extra_env"])
