"""`credentials.*_token_for` finds the axis VENDOR's own variable before the generic pair.

The split the funnel review (2026-08-09) measured: the shared ADO client read `AZURE_DEVOPS_PAT`
on its own, so the adapters authenticated — while everything that asks "does this project HAVE a
credential" through `credentials.py` (the doctor's presence probe, the repo-cache fetch) answered
no. An ADO-only deployment with a perfectly good PAT was told "no forge credential is
configured", with a GitHub App remedy that could not have fixed it.

Order matters more than presence: the generic fallback (`OPENFACTORY_BOT_TOKEN`) is a GITHUB
credential on a mixed deployment, and handing it to an ADO axis presents it as HTTP Basic and
reads back a 401 — a configured-looking credential failing as if revoked. So the vendor default
sits BETWEEN the registry's `token_env` (always first: an explicit declaration) and the generic
pair (last: correct exactly while one vendor exists).

AND A VENDOR THAT NAMES ITS OWN VARIABLE IS ANSWERED BY IT, AND BY NOTHING AFTER IT (#874). The
pair is the row that names none — GitHub's — and a project of no kind. A Jira project that named
no `token_env`, on a deployment with no `JIRA_API_TOKEN`, was handed `OPENFACTORY_BOT_TOKEN` and
sent it to the Jira site, which refused it as another account's (measured 2026-10-19). The rows
this holds are read from the credential registry, so a row added later is held to it unasked.
"""

from __future__ import annotations

import pytest

from openfactory.contracts.project import Project, ProviderRef
from openfactory.credentials import forge_token_for, tracker_token_for

_VENDOR_VARS = ("AZURE_DEVOPS_PAT", "JIRA_API_TOKEN", "OPENFACTORY_BOT_TOKEN",
                "OPENFACTORY_FORGE_TOKEN", "OPENFACTORY_TRACKER_TOKEN", "ACME_ADO_PAT")


@pytest.fixture(autouse=True)
def _clean_credential_env(monkeypatch):
    for name in _VENDOR_VARS:
        monkeypatch.delenv(name, raising=False)


def _ado(**options) -> Project:
    ref = ProviderRef(kind="azure_devops", repo="Deskline",
                      options={"organization": "acme", **options})
    return Project(name="dsk", repo_path="https://dev.azure.com/acme/Deskline/_git/api",
                   tracker=ref)


def test_an_ado_axis_finds_azure_devops_pat_with_nothing_named(monkeypatch):
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "the-pat")
    assert forge_token_for(_ado()) == "the-pat"
    assert tracker_token_for(_ado()) == "the-pat"


def test_the_vendor_default_beats_the_generic_github_shaped_fallback(monkeypatch):
    """Both set → the ADO axis gets the ADO credential, never the deployment's GitHub one."""
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "the-pat")
    monkeypatch.setenv("OPENFACTORY_BOT_TOKEN", "ghp_github_shaped")
    assert forge_token_for(_ado()) == "the-pat"


def test_a_named_token_env_still_beats_the_vendor_default(monkeypatch):
    """The registry's declaration is explicit and always wins."""
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "the-shared-pat")
    monkeypatch.setenv("ACME_ADO_PAT", "this-project-s-own")
    assert forge_token_for(_ado(token_env="ACME_ADO_PAT")) == "this-project-s-own"


def test_a_github_axis_is_byte_for_byte_unchanged(monkeypatch):
    """AZURE_DEVOPS_PAT in the environment must never leak onto a GitHub axis."""
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "the-pat")
    monkeypatch.setenv("OPENFACTORY_BOT_TOKEN", "ghp_mine")
    github = Project(name="gh", repo_path="/tmp/x",
                     tracker=ProviderRef(kind="github", repo="acme/api"))
    assert forge_token_for(github) == "ghp_mine"
    monkeypatch.delenv("OPENFACTORY_BOT_TOKEN")
    assert forge_token_for(github) is None


def test_a_jira_tracker_finds_jira_api_token(monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "atlassian-token")
    jira = Project(name="j", repo_path="/tmp/x",
                   tracker=ProviderRef(kind="jira", repo="DAR",
                                       options={"site": "acme.atlassian.net"}))
    assert tracker_token_for(jira) == "atlassian-token"


def test_the_doctor_probe_without_any_credential_names_the_vendor(monkeypatch):
    """The consumer that made this matter: doctor's forge probe answers presence through
    `forge_token_for`. With nothing set, the failure must carry the axis's KIND so the Finding's
    remedy can name AZURE_DEVOPS_PAT rather than sending an ADO deployment to create a GitHub
    App — the exact wrong remedy the funnel review transcribed."""
    for name in ("OPENFACTORY_GH_APP_ID", "OPENFACTORY_GH_APP_INSTALLATION_ID",
                 "OPENFACTORY_GH_APP_KEY_CONTENT", "OPENFACTORY_GH_APP_KEY"):
        monkeypatch.delenv(name, raising=False)
    from openfactory.doctor import _forge, probes_for

    probes = probes_for(_ado())
    reachable, detail = probes.forge_reachable()
    assert reachable is False
    assert "azure_devops" in detail

    finding = _forge(probes)
    assert "AZURE_DEVOPS_PAT" in finding.remedy
    assert "docs/setup/azure-devops.md" in finding.remedy
    assert "GitHub App" not in finding.remedy


def test_the_doctor_probe_with_the_pat_gets_past_presence(monkeypatch):
    """With AZURE_DEVOPS_PAT set the probe must reach the REACHABILITY half (a real HTTP call),
    not stop at 'no forge credential'. The call itself is stubbed at the adapter seam."""
    monkeypatch.setenv("AZURE_DEVOPS_PAT", "the-pat")
    from openfactory.adapters.forge import azure_devops as forge_mod
    from openfactory.doctor import probes_for

    seen: dict = {}

    def _pr_status(self, *, pr):
        seen["asked"] = pr
        raise RuntimeError("TF401180: pull request not found")  # 404-shaped: allowed to ask

    monkeypatch.setattr(forge_mod.AzureReposForge, "pr_status", _pr_status, raising=True)
    reachable, _ = probes_for(_ado()).forge_reachable()
    assert seen["asked"] == "1"
    assert reachable is True


# ── #874: a vendor that names its own variable is answered by it, and by nothing after it ──────

def _rows_that_name_their_own_variable() -> list[str]:
    """Every shipped kind whose row names a variable, needs a credential and resolves nothing
    itself — the rows the generic pair must never answer for. Read from the registry, so a row
    added later is held to this without anybody editing a list here."""
    from openfactory.adapters.credential.registry import CREDENTIALS

    return sorted(kind for kind, build in CREDENTIALS.items()
                  if (row := build()).env and row.source is None and row.needs)


def _variable_of(kind: str) -> str:
    from openfactory.adapters.credential.registry import credential_row

    return credential_row(kind).env


def _on(kind: str, axis: str, **options) -> Project:
    ref = ProviderRef(kind=kind, repo="DAR", options={"site": "acme.atlassian.net", **options})
    return Project(name="j", repo_path="/tmp/x", **{axis: ref})


def test_the_rows_this_holds_are_read_from_the_registry():
    """A parametrisation over an empty list is a test that runs nothing: Jira is the row #874 was
    found on, so it must be in the family."""
    assert "jira" in _rows_that_name_their_own_variable()


@pytest.mark.parametrize("axis", ["tracker", "forge"])
@pytest.mark.parametrize("kind", _rows_that_name_their_own_variable())
def test_a_vendor_that_names_its_own_variable_never_reads_the_generic_pair(kind, axis,
                                                                            monkeypatch):
    """Only the pair set → nothing: not `OPENFACTORY_<AXIS>_TOKEN`, not `OPENFACTORY_BOT_TOKEN`.
    Its own variable set → that, and the pair is still not what answered."""
    read = tracker_token_for if axis == "tracker" else forge_token_for
    monkeypatch.setenv("OPENFACTORY_BOT_TOKEN", "ghp_github_shaped")
    monkeypatch.setenv(f"OPENFACTORY_{axis.upper()}_TOKEN", "ghp_the_axis_s_own")
    assert read(_on(kind, axis)) is None
    monkeypatch.setenv(_variable_of(kind), "the-vendor-s-own")
    assert read(_on(kind, axis)) == "the-vendor-s-own"


@pytest.mark.parametrize("kind", _rows_that_name_their_own_variable())
def test_an_empty_token_env_on_such_a_vendor_falls_to_its_variable_and_no_further(kind,
                                                                                  monkeypatch):
    """The project's own declaration still wins; empty, it is the vendor's variable that is asked
    next — and with that unset too, nothing: the warning used to say "falling back to this
    deployment's own", and that is what it did."""
    monkeypatch.delenv("ACME_OWN_TOKEN", raising=False)
    monkeypatch.setenv("OPENFACTORY_TRACKER_TOKEN", "ghp_the_axis_s_own")
    monkeypatch.setenv("OPENFACTORY_BOT_TOKEN", "ghp_github_shaped")
    project = _on(kind, "tracker", token_env="ACME_OWN_TOKEN")
    assert tracker_token_for(project) is None
    monkeypatch.setenv(_variable_of(kind), "the-vendor-s-own")
    assert tracker_token_for(project) == "the-vendor-s-own"
    monkeypatch.setenv("ACME_OWN_TOKEN", "this-project-s-own")
    assert tracker_token_for(project) == "this-project-s-own"


def test_a_jira_tracker_built_with_what_the_project_resolves_holds_no_github_token(monkeypatch):
    """The measured defect: callers hand `build_tracker` the credential `tracker_token_for`
    resolved, and with only the deployment's pair set that was a `ghs_…`, which the site answered
    401 "different accounts". Now the tracker holds nothing, and says so (#749)."""
    from openfactory.adapters.tracker.registry import build_tracker

    monkeypatch.setenv("OPENFACTORY_BOT_TOKEN", "ghs_github_shaped")
    project = _on("jira", "tracker", email="somebody@acme.example")
    tracker = build_tracker(project, token=tracker_token_for(project))
    assert tracker.token is None


def test_the_pair_still_answers_for_the_row_that_names_no_variable_and_for_no_kind(monkeypatch):
    """The stop is the named row's, not every row's: a GitHub axis and a legacy project of no
    kind read the pair as they always have."""
    monkeypatch.setenv("OPENFACTORY_BOT_TOKEN", "ghp_mine")
    github = Project(name="gh", repo_path="/tmp/x", tracker=ProviderRef(kind="github", repo="a/r"))
    assert tracker_token_for(github) == "ghp_mine"
    blank = Project(name="old", repo_path="/tmp/x", tracker=ProviderRef(kind="", repo="a/r"))
    assert tracker_token_for(blank) == "ghp_mine"
