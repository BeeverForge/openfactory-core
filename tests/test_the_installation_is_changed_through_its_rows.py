"""The installation is changed through its rows, and only by its administrator (#741).

Every verb that changes what a deployment IS — the people it names, whether it picks work up, what
its product role is called and where its requirements live — was the command line's own code.
`poller pause` held the engine's schedule itself, `product name` and `product declare` wrote the
registry themselves, and nothing at all took a person back. So the panel, a script holding its
token and any front end of one's own (`POST /api/act/{name}`) could do none of it.

THE RULES HELD HERE, each over cases read from the code rather than named:

  1. a catalogue row that writes the installation — a registry writer, a people-store writer, the
     poller's hold, each read off its own module — is declared `installation`, and a row declared
     one writes it;
  2. an installation row is the administrator's: a credential scoped to either area is refused it
     before its runner runs, by `perform` and at the panel's door, and an unscoped one reaches it;
  3. no installation row is something the tech-lead may propose;
  4. the contract a front end is written against lists exactly the installation's rows;
  5. the doctor's document is one document, whichever door asked for it;
  6. a person revoked is gone — account, sessions and links — and the last one registered is not
     revoked while nothing else closes the panel's door;
  7. a project's own settings are set by its rows, and the command line writes none of them;
  8. a project is registered by one row, whichever door asked, and a registered one is never
     written over;
  9. a row of several steps says what each step came to, and running it again does only what is
     missing.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from openfactory import actions
from openfactory.actions import catalog
from openfactory.identity import people
from openfactory.identity.local import (
    BOARD_PEOPLE_ENV,
    CLOSING_ENVS,
    PRODUCT_PEOPLE_ENV,
    SHARED_ENV,
)
from tests.test_a_person_is_invited_not_signed_up import (
    GOOD,
    invite_and_register,
    local,  # noqa: F401 — the fixture
)
from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PY = ROOT / "openfactory" / "actions" / "catalog.py"
CONTRACT = ROOT / "docs" / "reference" / "the-front-end-api.md"

#: The rows that write the installation's registry and are NOT the administrator's, each with why.
#: Held EXACTLY by rule 1 — an entry that stopped writing fails too — so it cannot grow into a
#: list of permissions.
OPERATORS_LEVERS = {
    "enable": "one project's pickup, on or off: the operator's lever on the floor (ADR-0057's "
              "D3, proposed in #740, gives `enable` to `operator`), where the poller's pause is "
              "the deployment's",
}


# ── what writes the installation, read off the modules that do it ──────────────────────────────

def _writers(path: str, owner: str, through: str) -> frozenset[str]:
    """The methods of class `owner` in `path` that call `self.<through>` — its writers. Read from
    the source, so a writer added to the registry or the store is one rule 1 asks about."""
    tree = parsed(ROOT / path)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner)
    return frozenset(
        fn.name for fn in cls.body if isinstance(fn, ast.FunctionDef) and any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == through and getattr(n.func.value, "id", "") == "self"
            for n in ast.walk(fn)))


def _poller_holds() -> frozenset[str]:
    """The schedule module's functions that pause or unpause a schedule."""
    tree = parsed(ROOT / "openfactory/runtime/temporal/schedule.py")
    return frozenset(
        fn.name for fn in tree.body if isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef)
        and any(isinstance(n, ast.Call) and getattr(n.func, "attr", "") in ("pause", "unpause")
                for n in ast.walk(fn)))


#: `class whose instance is written through → its writers`.
WRITERS = {
    "ProjectRegistry": _writers("openfactory/registry.py", "ProjectRegistry", "_save_raw"),
    "PeopleStore": _writers("openfactory/identity/people.py", "PeopleStore", "_record"),
}


def _builds(node: ast.AST, cls: str) -> bool:
    """Whether `node` constructs `cls` — `ProjectRegistry()` or `_people.PeopleStore()`."""
    return isinstance(node, ast.Call) and (getattr(node.func, "id", "") == cls
                                           or getattr(node.func, "attr", "") == cls)


def _writes_directly(fn: ast.AST) -> set[str]:
    """What this one function writes: `Class.method` for a writer called on an instance it built
    (inline, or through a name it bound to one), and the poller's hold called by name."""
    bound = {cls: {t.id for n in ast.walk(fn) if isinstance(n, ast.Assign) and _builds(n.value, cls)
                   for t in n.targets if isinstance(t, ast.Name)} for cls in WRITERS}
    holds = _poller_holds()
    found: set[str] = set()
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        if getattr(n.func, "id", "") in holds:
            found.add(f"schedule.{n.func.id}")
        if not isinstance(n.func, ast.Attribute):
            continue
        for cls, methods in WRITERS.items():
            receiver = n.func.value
            if n.func.attr in methods and (_builds(receiver, cls)
                                           or getattr(receiver, "id", "") in bound[cls]):
                found.add(f"{cls}.{n.func.attr}")
    return found


def _catalog_writes() -> dict[str, set[str]]:
    """`row → what it writes`, following the catalogue's own helpers it names — by a call, or by
    handing one on: a row whose steps leave the loop hands its body to `asyncio.to_thread`, and
    that body is the row's code all the same (slice 3)."""
    tree = parsed(CATALOG_PY)
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}

    def reached(name: str, seen: set[str]) -> set[str]:
        if name in seen or name not in functions:
            return set()
        seen.add(name)
        fn = functions[name]
        out = _writes_directly(fn)
        for n in ast.walk(fn):
            if isinstance(n, ast.Name):
                out |= reached(n.id, seen)
        return out

    return {name: reached(spec.run.__name__, set()) for name, spec in catalog.CATALOG.items()}


def test_what_writes_the_installation_is_read_off_the_modules_that_write_it():
    """The rule below is only as good as this reading, so it is checked to see something: the
    registry's adding and removing, a person's invitation and withdrawal, the poller's hold."""
    assert {"add", "remove", "set_docs_repo", "set_agent_name", "set_enabled"} <= \
        WRITERS["ProjectRegistry"], WRITERS["ProjectRegistry"]
    assert {"invite", "withdraw"} <= WRITERS["PeopleStore"], WRITERS["PeopleStore"]
    assert "hold_poller" in _poller_holds()
    assert {"get", "list"}.isdisjoint(WRITERS["ProjectRegistry"]), "a read counted as a write"


# ── 1. a row that writes the installation says so, and only such a row ─────────────────────────

def test_a_row_that_writes_the_installation_is_declared_an_installation_row():
    writes = {name: what for name, what in _catalog_writes().items() if what}
    declared = {name for name, spec in catalog.CATALOG.items() if spec.installation}

    undeclared = {name: sorted(what) for name, what in writes.items()
                  if name not in declared and name not in OPERATORS_LEVERS}
    assert not undeclared, (
        f"these rows change the installation and are not `installation=True`, so a board or a "
        f"product credential reaches them: {undeclared}")
    idle = sorted(declared - set(writes))
    assert not idle, f"declared installation rows that write nothing of it: {idle}"
    assert set(OPERATORS_LEVERS) <= set(writes) - declared, (
        "OPERATORS_LEVERS names a row that no longer writes the installation, or is declared one")


# ── 2. the administrator's, by every door ──────────────────────────────────────────────────────

INSTALLATION = sorted(name for name, spec in catalog.CATALOG.items() if spec.installation)


def _params(spec) -> dict[str, object]:
    return {p: "acme" if p == "project" else "x" for p in spec.required}


@pytest.fixture
def reached(monkeypatch):
    """Every row's runner replaced by a recorder, through the table `perform` reads."""
    seen: list[str] = []

    def recorder(name: str):
        async def run(by=None, **_params):
            seen.append(name)
            return actions.done(f"recorded {name}")
        return run

    monkeypatch.setattr(catalog, "CATALOG", {
        name: dataclasses.replace(spec, run=recorder(name))
        for name, spec in catalog.CATALOG.items()})
    return seen


def test_there_are_installation_rows_to_hold_the_rule_over():
    assert {"people_invite", "people_revoke", "poller_pause", "poller_resume",
            "product_name", "product_declare"} <= set(INSTALLATION), INSTALLATION


@pytest.mark.parametrize("area", sorted(actions.SCOPES))
@pytest.mark.parametrize("name", INSTALLATION)
def test_a_scoped_credential_is_refused_every_installation_row(name, area, reached):
    """`admin=True` on purpose: a board or a product credential IS admin on its own surface, and
    what refuses it here is the installation, not the authority."""
    scoped = actions.Actor(id="leo", via="panel", admin=True, scopes=frozenset({area}))

    out = asyncio.run(actions.perform(name, by=scoped, **_params(catalog.CATALOG[name])))

    assert out.code == actions.DENIED and reached == [], (name, area, out)


@pytest.mark.parametrize("name", INSTALLATION)
def test_the_administrator_reaches_every_installation_row(name, reached):
    """The positive twin: a rule that refused everybody would pass the test above."""
    admin = actions.Actor(id="rob", via="panel", admin=True)

    out = asyncio.run(actions.perform(name, by=admin, **_params(catalog.CATALOG[name])))

    assert out.ok and reached == [name], (name, out)


@pytest.mark.parametrize("name", INSTALLATION)
def test_an_unscoped_caller_who_is_not_an_admin_is_refused_every_installation_row(name, reached):
    """The installation's rule is asked beside `needs_admin`, not instead of it: an unscoped
    caller who is nobody's admin — a chat user outside `project.admins` — is refused too."""
    nobody = actions.Actor(id="u1", via="slack", admin=False)

    out = asyncio.run(actions.perform(name, by=nobody, **_params(catalog.CATALOG[name])))

    assert out.code == actions.DENIED and reached == [], (name, out)


def test_the_doctor_answers_a_caller_who_is_not_an_admin(reached):
    """The doctor changes nothing, so it answers whoever may enter the floor — admin or not."""
    viewer = actions.Actor(id="u1", via="slack", admin=False)

    out = asyncio.run(actions.perform("doctor", by=viewer, project="acme"))

    assert out.ok and reached == ["doctor"], out


@pytest.fixture
def three_credentials(tmp_path, monkeypatch):
    """The panel's own token, a person's board token and a person's product token."""
    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(SHARED_ENV, "the-admin")
    monkeypatch.setenv(BOARD_PEOPLE_ENV, "the-board:leo:Leo")
    monkeypatch.setenv(PRODUCT_PEOPLE_ENV, "the-analyst:bia:Bia")
    from openfactory.api.app import app

    return TestClient(app)


@pytest.mark.parametrize("name", INSTALLATION)
def test_at_the_panels_door_only_the_administrators_credential_changes_the_installation(
        name, three_credentials, reached):
    """`POST /api/act/{name}` is how a front end of one's own reaches every row, so it is where
    the rule must hold for one: whichever area the path is read as, a scoped credential is
    refused and the row never runs."""
    body = {"params": _params(catalog.CATALOG[name])}
    for credential in ("the-board", "the-analyst"):
        refused = three_credentials.post(f"/api/act/{name}", json=body,
                                         headers={"Authorization": f"Bearer {credential}"})
        assert refused.status_code == 403, (name, credential, refused.text)
    assert reached == [], f"{name} ran for a scoped credential"

    admitted = three_credentials.post(f"/api/act/{name}", json=body,
                                      headers={"Authorization": "Bearer the-admin"})
    assert admitted.status_code == 200 and reached == [name], (name, admitted.text)


# ── 3. never proposed ───────────────────────────────────────────────────────────────────────────

def test_no_installation_row_is_something_the_tech_lead_may_propose():
    """`proposable` asks `perform`'s scope and admin checks and not the installation's, because
    no installation row is in the grammar a person types — held here, so the day one is, the
    third check is added there rather than a proposal to add a project reaching a chat."""
    from openfactory.actions.floor_intents import FLOOR_ROWS
    from openfactory.contracts.commands import ACTION_OF

    typeable = set(ACTION_OF.values()) | set(FLOOR_ROWS.values())
    assert typeable.isdisjoint(INSTALLATION), sorted(typeable & set(INSTALLATION))


# ── 4. the contract a front end is written against ─────────────────────────────────────────────

def _contract_rows() -> dict[str, str]:
    table = CONTRACT.read_text(encoding="utf-8").split("<!-- installation:start -->")[1]
    table = table.split("<!-- installation:end -->")[0]
    rows = {}
    for line in table.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[0].startswith("`") and cells[0] != "`name`":
            rows[cells[0].strip("`")] = cells[1]
    return rows


def test_the_front_end_contract_lists_exactly_the_installation_rows_and_what_they_take():
    rows = _contract_rows()

    assert set(rows) == set(INSTALLATION), (
        f"the contract lists {sorted(rows)}; the catalogue's installation rows are {INSTALLATION}")
    for name, takes in rows.items():
        spec = catalog.CATALOG[name]
        said = [p.strip(" `[]") for p in takes.split(",") if p.strip(" `[]-")]
        assert said == list(spec.parameters), (name, said, spec.parameters)


# ── 5. one doctor, whichever door asked ─────────────────────────────────────────────────────────

def test_the_doctor_row_answers_the_document_the_command_prints(tmp_path, monkeypatch):
    """`doctor --json` is a public contract (#356). The row is what the command maps onto now, so
    a front end of one's own reads the very document a script reads — not a second rendering."""
    from openfactory import doctor, namespace
    from openfactory.cli import app
    from tests.pinned_probes import a_fully_pinned_probe_set

    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    assert CliRunner().invoke(app, ["project", "add", "demo", str(tmp_path)]).exit_code == 0
    monkeypatch.setattr(doctor, "probes_for", lambda _p: a_fully_pinned_probe_set(
        docker_running=lambda: (False, "the daemon did not answer")))
    monkeypatch.setattr(namespace, "build_stamp", lambda: ("abc123", "2026-10-05T10:00"))
    from openfactory.api.app import app as panel

    printed = CliRunner().invoke(app, ["doctor", "demo", "--json"])
    answered = TestClient(panel).post("/api/act/doctor", json={"params": {"project": "demo"}})

    assert answered.status_code == 200, answered.text
    assert answered.json()["data"] == json.loads(printed.stdout)
    assert answered.json()["ok"] is True, "the doctor ran — `ok` is about the platform"
    assert answered.json()["data"]["ok"] is False and "docker" in answered.json()["message"]


def test_the_doctor_and_a_declaration_probe_off_the_loop_the_panel_serves_from(tmp_path,
                                                                             monkeypatch):
    """The doctor's probes (`docker info`, the forge's API, the box gate) and a declaration's read
    (`git ls-remote` with each credential) block for seconds. Through the panel these rows run on
    the one loop that serves every other request, stream and approval: measured on 2026-10-19, a
    request sent 0.3 s into a 3 s probe waited 2.75 s behind the doctor and 3.95 s behind a
    declaration. So each runs on a thread of its own, and the loop keeps serving."""
    import threading

    from openfactory import doctor
    from openfactory.cli import app
    from openfactory.product import onboard
    from tests.pinned_probes import a_fully_pinned_probe_set

    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    assert CliRunner().invoke(app, ["project", "add", "demo", str(tmp_path)]).exit_code == 0
    ran_on: dict[str, int] = {}

    def docker_running():
        ran_on["doctor"] = threading.get_ident()
        return True, ""

    def reachable(_project, _repo):
        ran_on["product_declare"] = threading.get_ident()
        return True, ""

    monkeypatch.setattr(doctor, "probes_for",
                        lambda _p: a_fully_pinned_probe_set(docker_running=docker_running))
    monkeypatch.setattr(onboard, "context_reachability", reachable)
    admin = actions.Actor(id="rob", via="panel", admin=True)

    async def on_the_loop() -> int:
        for name, params in (("doctor", {"project": "demo"}),
                             ("product_declare", {"project": "demo",
                                                  "docs_repo": "acme/demo-docs"})):
            out = await actions.perform(name, by=admin, **params)
            assert out.ok, (name, out)
        return threading.get_ident()

    loop = asyncio.run(on_the_loop())

    assert set(ran_on) == {"doctor", "product_declare"}, f"a probe was not reached: {ran_on}"
    assert loop not in ran_on.values(), f"a probe ran on the loop's own thread: {ran_on}"


def test_the_command_names_its_remedy_for_an_empty_repository(tmp_path, monkeypatch):
    """`perform` refuses `""` as a missing parameter before the row is reached, and that sentence
    names a parameter; the person typed a command, so the command says which one to type."""
    from openfactory.cli import app

    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    assert CliRunner().invoke(app, ["project", "add", "demo", str(tmp_path)]).exit_code == 0

    out = CliRunner().invoke(app, ["product", "declare", "demo", ""])

    assert out.exit_code == 2, out.output
    assert "openfactory product declare <project> <owner/repo>" in out.output, out.output


#: A pause's `in_flight` is the RUNNING jobs the floor read, never the finished ones beside them,
#: because the row filters the list and a front end renders exactly what it is handed. Each case
#: carries a closed job the answer must drop, so `data.in_flight` can never list a finished job as
#: still running.
@pytest.mark.parametrize("jobs,flight,said", [
    ([{"project": "routing", "issue": "210", "status": "running"}, {"project": "routing", "issue": "209", "status": "closed"}], [{"project": "routing", "issue": "210", "status": "running"}], "wait for them"),
    (None, None, "do not roll the deployment"),
    ([{"project": "routing", "issue": "209", "status": "closed"}], [], "Nothing is in flight"),
], ids=["running", "unread", "drained"])
def test_a_pause_from_the_panel_says_what_is_still_running(monkeypatch, jobs, flight, said):
    """The sentence `poller pause` exists to print travels with the row, so a screen of one's own
    is told it too: a pause holds NEW pickups, and a pause that read as "drained" is how a job is
    interrupted by somebody who paused to protect it. An unread list is not a drained floor, and a
    FINISHED job beside a running one is not in flight."""
    from openfactory.api.app import app
    from tests.test_the_poller_has_a_lever import _engine, _Handle, _reading

    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    _engine(_Handle(paused=False), monkeypatch)
    _reading(monkeypatch, on=False, jobs=jobs)
    if jobs is None:
        from openfactory.floor import reading as floor
        from openfactory.floor.ladder import FloorInputs

        async def unread(client=None, *, want=(), **_kw):
            return FloorInputs(jobs=None)

        monkeypatch.setattr(floor, "gather", unread)

    r = TestClient(app).post("/api/act/poller_pause", json={"params": {"note": "rolling"}})

    assert r.status_code == 200, r.text
    assert said in r.json()["message"], r.json()["message"]
    assert r.json()["data"]["in_flight"] == flight, "a finished job was counted as in flight"


# ── 6. a person revoked ─────────────────────────────────────────────────────────────────────────

def _revoke(person: str, *, by: str = "rob"):
    return asyncio.run(actions.perform("people_revoke", by=actions.Actor(id=by, via="panel",
                                                                         admin=True),
                                       person=person))


@pytest.fixture
def a_closed_door(monkeypatch):
    """A deployment whose environment closes the panel's door — so the last person may go."""
    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(SHARED_ENV, "the-admin")


def test_a_person_revoked_cannot_sign_in_and_their_sessions_end(local, a_closed_door):  # noqa: F811
    s, ana = invite_and_register(local)
    session = s.open_session(ana)

    out = _revoke("ana@acme.example")

    assert out.ok and out.data["registered"] is True and out.data["sessions"] == 1, out
    fresh = people.PeopleStore()
    assert fresh.login("ana@acme.example", GOOD) == ""
    assert fresh.session_of(session) is None
    assert fresh.people() == []
    assert local.rows[-1]["extra"]["by"] == "rob", "who revoked them is not recorded"


def test_invited_again_they_come_back_like_anybody_new_and_their_old_session_does_not(
        local, a_closed_door):  # noqa: F811
    """The store is append-only and folded in order: the withdrawal ends what came before it, and
    an invitation after it is a new person's. A session from before must stay dead — `session_of`
    would otherwise revive it the moment the same id registered again."""
    s, ana = invite_and_register(local)
    old = s.open_session(ana)
    assert _revoke("ana@acme.example").ok

    invite_and_register(local)

    back = people.PeopleStore()
    assert [p.id for p in back.people()] == ["ana@acme.example"]
    assert back.login("ana@acme.example", GOOD), "registered again, they sign in again"
    assert back.session_of(old) is None, "a session from before the revocation came back"


def test_an_open_invitation_revoked_no_longer_registers_anybody(local):  # noqa: F811
    token, _ = people.PeopleStore().invite("typo@acme.example", by="rob")

    out = _revoke("typo@acme.example")

    assert out.ok and out.data == {"person": "typo@acme.example", "registered": False,
                                   "invitations": 1, "sessions": 0, "by": "rob"}, out
    assert isinstance(people.PeopleStore().register(token=token, display="T", password=GOOD), str)


def test_nobody_by_that_name_is_not_found_and_nothing_is_written(local):  # noqa: F811
    invite_and_register(local)
    before = list(local.rows)

    out = _revoke("ghost@acme.example")

    assert out.code == actions.NOT_FOUND and local.rows == before, out


def test_the_last_person_is_not_revoked_while_nothing_else_closes_the_door(
        local, monkeypatch):  # noqa: F811
    """With nobody registered and no credential configured, the panel is open to whoever arrives —
    the new install's door, and the opposite of what revoking an account is for."""
    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    invite_and_register(local)
    before = list(local.rows)

    out = _revoke("ana@acme.example")

    assert out.code == actions.CONFLICT and local.rows == before, out
    from openfactory.identity.local import LocalIdentity

    assert not LocalIdentity().open_to_everyone(), "the door this refusal exists for opened"


@pytest.mark.parametrize("var", CLOSING_ENVS)
def test_any_credential_that_closes_the_door_lets_the_last_person_go(local, monkeypatch, var):  # noqa: F811,E501
    """Every variable that closes the door, read from the identity row itself: the refusal is about
    the door opening, so any one of them that keeps it shut is enough."""
    for other in CLOSING_ENVS:
        monkeypatch.delenv(other, raising=False)
    monkeypatch.setenv(var, "t:someone" if var.endswith("TOKENS") else "t")
    invite_and_register(local)

    assert _revoke("ana@acme.example").ok


def test_the_shell_revokes_through_the_row(local, a_closed_door):  # noqa: F811
    from openfactory.cli import app

    invite_and_register(local)

    gone = CliRunner().invoke(app, ["people", "revoke", "ana@acme.example"])
    again = CliRunner().invoke(app, ["people", "revoke", "ana@acme.example"])

    assert gone.exit_code == 0 and "ana@acme.example is revoked" in gone.output, gone.output
    assert again.exit_code == 1 and "nobody called" in again.output, again.output


def test_the_shared_panel_token_cannot_revoke_anybody(local, monkeypatch):  # noqa: F811
    """The voucher rule of #759, on the other end: the shared token is only CALLED "panel", so a
    revocation from it is signed by nobody, and it is refused before the store is read."""
    from openfactory.api.app import app

    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(SHARED_ENV, "shared-secret")
    invite_and_register(local)
    before = list(local.rows)

    r = TestClient(app).post("/api/act/people_revoke",
                             headers={"authorization": "Bearer shared-secret"},
                             json={"params": {"person": "ana@acme.example"}})

    assert r.status_code == 400 and r.json()["message"] == people.UNSIGNED_WITHDRAWAL, r.text
    assert local.rows == before and [p.id for p in people.PeopleStore().people()] == [
        "ana@acme.example"]


def test_a_revocation_nobody_signed_is_refused_before_the_store_is_read(local):  # noqa: F811
    """The panel's gate reads the store to admit a caller; the row must not read it again for an
    act it will refuse whatever the store says."""
    invite_and_register(local)
    reads = local.reads

    out = asyncio.run(actions.perform("people_revoke", by=actions.Actor(id="", via="panel",
                                                                        admin=True),
                                      person="ana@acme.example"))

    assert out.code == actions.INVALID and out.message == people.UNSIGNED_WITHDRAWAL, out
    assert local.reads == reads, "the store was read for a revocation nobody signed"


# ── the review's minors (#741, hcristia's independent review) ───────────────────────────────────

@pytest.mark.parametrize("name", ["product_name", "product_declare"])
def test_a_scoped_credential_refused_a_product_row_is_sent_to_the_administrator(name):
    """`product_name` and `product_declare` are the installation's, named `product_` only because
    they configure the product role. A product credential is refused them by the area check — but
    every floor credential is refused them too, so "ask somebody whose credential covers the
    floor" would be the wrong remedy. The sentence names the administrator instead."""
    product = actions.Actor(id="bia", via="panel", admin=True, scopes=frozenset({actions.PRODUCT}))

    out = asyncio.run(actions.perform(name, by=product, **_params(catalog.CATALOG[name])))

    assert out.code == actions.DENIED, out
    assert "administers this deployment" in out.message, out.message
    assert "covers the floor" not in out.message, out.message


def test_a_revocation_is_refused_when_the_sink_keeps_nothing(monkeypatch):
    """`people_revoke` reads the people store, which lives in the metrics sink. A sink that keeps
    nothing cannot say who is registered, so the row refuses — UNAVAILABLE, naming the sink —
    rather than answer "nobody called X" about a store it could not read."""
    from openfactory.identity import people

    monkeypatch.setattr(people, "sink_is_durable",
                        lambda: "the metrics sink is `null`, which keeps nothing")

    out = asyncio.run(actions.perform("people_revoke", by=actions.Actor(id="rob", via="panel",
                                                                        admin=True),
                                      person="ana@acme.example"))

    assert out.code == actions.UNAVAILABLE and "keeps nothing" in out.message, out
# ── 7. a project's own settings (slice 2) ───────────────────────────────────────────────────────

#: Something plausible for each parameter a project row requires besides the project itself.
_PLAUSIBLE = {"model": "a-model", "language": "en", "docs_repo": "acme/docs", "person": "x"}

#: The rows that take an address to register a project at. They take a project that is NOT
#: registered yet, so the rule below is not theirs; theirs is that what is registered already is
#: never written over (slice 3, below).
REGISTERS_AT = sorted(name for name in INSTALLATION if "repo_path" in catalog.CATALOG[name].required)

TAKES_A_PROJECT = sorted(name for name in INSTALLATION
                         if "project" in catalog.CATALOG[name].required
                         and name not in REGISTERS_AT)


@pytest.fixture
def one_project(tmp_path, monkeypatch):
    """A registry holding `acme`, and nothing else."""
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.registry import ProjectRegistry

    path = tmp_path / "registry.yaml"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(path))
    ProjectRegistry().add(Project(name="acme", repo_path=str(tmp_path / "acme"),
                                  tracker=ProviderRef(kind="local", repo="acme", options={}),
                                  forge=ProviderRef(kind="local", repo="acme", options={})))
    return path


@pytest.mark.parametrize("name", TAKES_A_PROJECT)
def test_every_installation_row_that_takes_a_project_refuses_one_nobody_registered(
        name, one_project):
    """By name, with the roster — the commonest cause is a typo, and the right name is on it —
    and with the registry exactly as it was: a write to a ghost is how a project that does not
    exist comes to have settings."""
    before = one_project.read_bytes()
    params = {p: _PLAUSIBLE.get(p, "x") for p in catalog.CATALOG[name].required}
    params["project"] = "acmee"

    out = asyncio.run(actions.perform(name, by=actions.Actor(id="rob", via="cli", admin=True),
                                      **params))

    assert out.code == actions.NOT_FOUND, (name, out)
    assert re.search(r"knows: acme\.", out.message, re.IGNORECASE), (
        f"{name} refused the ghost without the roster the right name is on: {out.message}")
    assert one_project.read_bytes() == before, f"{name} wrote the registry for a ghost"


def test_the_shell_and_a_front_end_set_the_same_preview_policy(one_project, tmp_path,
                                                               monkeypatch):
    """The flags a terminal gives and the words a JSON body carries are one request: a front end
    of one's own writes `"true"`, `"6"` and `"web=DB_URL"` where the shell passes booleans, an
    int and a list, and the policy saved must be the same."""
    from openfactory.api.app import app as panel
    from openfactory.cli import app
    from openfactory.registry import ProjectRegistry

    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    shell = CliRunner().invoke(app, ["project", "set-preview", "acme", "--required", "--hours",
                                     "6", "--env", "web=DB_URL", "--env",
                                     "api=OPENFACTORY_BOT_TOKEN", "--no-auto-start"])
    assert shell.exit_code == 0, shell.output
    by_the_shell = ProjectRegistry().get("acme").preview.model_dump()

    ProjectRegistry().set_preview("acme", {})
    answered = TestClient(panel).post("/api/act/project_set_preview", json={"params": {
        "project": "acme", "required": "true", "hours": "6",
        "env": "web=DB_URL,api=OPENFACTORY_BOT_TOKEN", "auto_start": "false"}})

    assert answered.status_code == 200, answered.text
    assert ProjectRegistry().get("acme").preview.model_dump() == by_the_shell
    assert answered.json()["data"]["preview"]["required"] is True
    # AND WHAT WAS REFUSED IS SAID to the screen too: the factory's own credential is never
    # written, and a front end that shows only the sentence must not read that as accepted
    assert answered.json()["data"]["dropped"] == ["api=OPENFACTORY_BOT_TOKEN"]
    assert "OPENFACTORY_BOT_TOKEN" in answered.json()["message"], answered.json()["message"]


@pytest.mark.parametrize("field", ["required", "auto_start", "clear_env"])
def test_a_yes_or_no_that_is_neither_is_refused_and_nothing_is_written(field, one_project):
    """`"maybe"` is not a no: read as one, a form field carrying anything but yes would lift a
    look a person must take before a merge."""
    before = one_project.read_bytes()

    out = asyncio.run(actions.perform("project_set_preview",
                                      by=actions.Actor(id="rob", via="cli", admin=True),
                                      project="acme", **{field: "maybe"}))

    assert out.code == actions.INVALID and "maybe" in out.message, out
    assert one_project.read_bytes() == before


ADMIN = actions.Actor(id="rob", via="panel", admin=True)


@pytest.mark.parametrize("argv,row", [
    (["project", "set-model", "acme", "m"], "project_set_model"),
    (["project", "set-language", "acme", "en"], "project_set_language"),
    (["project", "set-preview", "acme", "--hours", "3"], "project_set_preview"),
    (["project", "remove", "acme"], "project_remove"),
])
def test_each_project_verb_runs_its_row_and_writes_nothing_itself(argv, row, one_project,
                                                                  monkeypatch):
    """The command is a mapping: with the row's own code replaced by a recorder, the verb still
    answers, the recorder ran once, and the registry is byte for byte as it was. A verb that wrote
    the registry itself beside its row would pass every test that reads the registry back."""
    from openfactory import cli

    before, seen = one_project.read_bytes(), []

    async def recorder(by=None, **params):
        seen.append(params)
        return actions.done("recorded", preview={"required": False, "auto_start": True,
                                                 "hours": 3, "network": "", "env": {},
                                                 "build_args": {}}, dropped=[])

    monkeypatch.setattr(catalog, "CATALOG", {**catalog.CATALOG, row: dataclasses.replace(
        catalog.CATALOG[row], run=recorder)})
    monkeypatch.setattr(cli, "_model_recognition_note", lambda p, m: "")

    out = CliRunner().invoke(cli.app, argv)

    assert out.exit_code == 0, out.output
    assert len(seen) == 1, f"{argv} did not run {row}"
    assert one_project.read_bytes() == before, f"{argv} wrote the registry itself"


@pytest.mark.parametrize("model", [
    "arn:aws:bedrock:us-east-1:123:inference-profile/ACM.Fictitious.Model-" + "X" * 80,
    " padded ", "a-model-with-dashes-inside"])
def test_the_model_is_saved_verbatim(model, one_project):
    """The harness names its models its own way, so the row passes the string on as it came: no
    case folded, nothing stripped, nothing cut. The one shape refused is a leading '-' (below)."""
    from openfactory.registry import ProjectRegistry

    out = asyncio.run(actions.perform("project_set_model", by=ADMIN, project="acme", model=model))

    assert out.ok and ProjectRegistry().get("acme").model == model, out


@pytest.mark.parametrize("model", ["--looks-like-a-flag", "  -x"])
def test_a_model_that_begins_like_a_flag_is_refused_and_nothing_is_written(model, one_project):
    """A model value is handed to the harness as one `--model=<value>` token; a value that begins
    with '-' is refused, with a sentence, and the registry is byte for byte as it was."""
    from openfactory.registry import ProjectRegistry

    before = one_project.read_bytes()
    out = asyncio.run(actions.perform("project_set_model", by=ADMIN, project="acme", model=model))

    assert out.code == actions.INVALID and "begin with '-'" in out.message, out
    assert one_project.read_bytes() == before
    assert ProjectRegistry().get("acme").model is None, "a refused model was written"


def test_the_refusal_holds_the_per_role_shape_and_the_add_door(one_project):
    """Every writer passes through the one check (`model_refused`): the per-role form of
    `set_model`, and `project add`'s own model."""
    import pytest as _pytest

    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.registry import ProjectRegistry

    with _pytest.raises(ValueError, match="begin with '-'"):
        ProjectRegistry().set_model("acme", "--flag", role="executor")
    with _pytest.raises(ValueError, match="begin with '-'"):
        ProjectRegistry().add(Project(name="beta", repo_path=str(one_project.parent / "beta"),
                                      tracker=ProviderRef(kind="local", repo="beta", options={}),
                                      model="--flag"))


def test_a_model_set_through_a_front_end_says_it_was_not_checked(one_project):
    """Only the shell asks the harness whether it runs the name, on the machine that will run it.
    A front end is told the row did not, so silence never reads as a confirmation."""
    out = asyncio.run(actions.perform("project_set_model", by=ADMIN, project="acme",
                                      model="gtp-5-typo"))

    assert out.ok and "not checked" in out.message.lower() and out.data.get("checked") is False, out


def test_clear_env_drops_what_was_held(one_project):
    from openfactory.registry import ProjectRegistry

    asyncio.run(actions.perform("project_set_preview", by=ADMIN, project="acme", env="web=A"))
    asyncio.run(actions.perform("project_set_preview", by=ADMIN, project="acme",
                                clear_env="true", env="api=B"))

    assert ProjectRegistry().get("acme").preview.env == {"api": {"B": "B"}}


@pytest.mark.parametrize("hours", ["6h", "abc"])
def test_hours_that_are_not_a_number_are_refused(hours, one_project):
    """The shell types `--hours` as a number; a front end's body may carry anything, and the
    policy reads what is not a number as its default — saved and reported as a success."""
    before = one_project.read_bytes()

    out = asyncio.run(actions.perform("project_set_preview", by=ADMIN, project="acme",
                                      hours=hours))

    assert out.code == actions.INVALID and hours in out.message, out
    assert one_project.read_bytes() == before


def test_a_network_a_preview_may_not_join_is_said_and_not_saved(one_project):
    from openfactory.registry import ProjectRegistry

    out = asyncio.run(actions.perform("project_set_preview", by=ADMIN, project="acme",
                                      network="host"))

    assert out.ok and "network 'host' refused" in out.message, out
    assert ProjectRegistry().get("acme").preview.network == ""


# ── 8. registering a project (slice 3) ──────────────────────────────────────────────────────────

def _kinds_the_axes_branch_on() -> set[str]:
    """The kinds `doors.axes_for` writes differently, read off its comparisons — so a kind it
    learns to write is a kind the cases below must carry an address for."""
    fn = next(n for n in parsed(ROOT / "openfactory" / "doors.py").body
              if isinstance(n, ast.FunctionDef) and n.name == "axes_for")
    return {c.value for n in ast.walk(fn) if isinstance(n, ast.Compare)
            for c in ast.walk(n) if isinstance(c, ast.Constant) and isinstance(c.value, str)}


#: One address for each kind `doors.axes_for` writes differently: a path on this machine (every axis
#: local), a clone URL whose kind writes the tracker, and one whose kind writes two axes from the
#: coordinates the URL carries. The panel's door wrote the tracker alone for both URLs.
ADDRESSES = ("{tmp}/acme", "https://github.com/acme-corp/acme.git",
             "https://dev.azure.com/acme-org/Payments/_git/acme")


def test_the_addresses_cover_every_kind_the_row_writes_differently(tmp_path):
    from openfactory import doors

    covered = {doors.kind_for(a.format(tmp=tmp_path)) for a in ADDRESSES}

    assert covered == _kinds_the_axes_branch_on(), (covered, _kinds_the_axes_branch_on())


@pytest.mark.parametrize("address", ADDRESSES)
def test_the_command_and_the_panels_door_register_one_row(address, tmp_path, monkeypatch):
    """`project add` and `POST /api/projects` are mappings onto one row, so the same address
    registers the same project through either — every axis, not the tracker alone."""
    from openfactory.api.app import app as panel
    from openfactory.cli import app
    from openfactory.registry import ProjectRegistry

    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    where = address.format(tmp=tmp_path)
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "by-the-shell.yaml"))
    shell = CliRunner().invoke(app, ["project", "add", "acme", where])
    assert shell.exit_code == 0, shell.output
    by_the_shell = ProjectRegistry().get("acme").model_dump(mode="json")

    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "by-the-panel.yaml"))
    answered = TestClient(panel).post("/api/projects", json={"name": "acme", "repo_path": where})

    assert answered.status_code == 200, answered.text
    assert ProjectRegistry().get("acme").model_dump(mode="json") == by_the_shell


@pytest.mark.parametrize("argv,body", [
    (["project", "add", "acme", "/srv/acme"], None),
    (None, {"name": "acme", "repo_path": "/srv/acme"}),
], ids=["project add", "POST /api/projects"])
def test_each_registering_door_runs_the_row_and_writes_nothing_itself(argv, body, tmp_path,
                                                                      monkeypatch):
    """With the row's own code replaced by a recorder, the door still answers, the recorder ran
    once, and no registry was written: a door that also wrote the project itself would pass every
    test that reads the registry back."""
    from openfactory.api.app import app as panel
    from openfactory.cli import app

    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    registry = tmp_path / "registry.yaml"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(registry))
    seen = []

    async def recorder(by=None, **params):
        seen.append(params)
        return actions.done("recorded", project="acme", changed=True, registered={})

    monkeypatch.setattr(catalog, "CATALOG", {**catalog.CATALOG, "project_add": dataclasses.replace(
        catalog.CATALOG["project_add"], run=recorder)})

    if argv:
        out = CliRunner().invoke(app, argv)
        assert out.exit_code == 0, out.output
    else:
        answered = TestClient(panel).post("/api/projects", json=body)
        assert answered.status_code == 200, answered.text

    assert [p["project"] for p in seen] == ["acme"], "the door did not run project_add"
    assert not registry.exists(), "the door wrote the registry itself"


def test_registering_through_the_panels_door_is_the_administrators(three_credentials, tmp_path,
                                                                   monkeypatch):
    """`POST /api/projects` is held to the row's scoping: a board credential passes the floor's
    door and is refused by the row, a product credential is refused at the door, and nothing is
    written for either."""
    from openfactory.registry import ProjectRegistry

    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    body = {"name": "acme", "repo_path": str(tmp_path / "acme")}
    for credential in ("the-board", "the-analyst"):
        refused = three_credentials.post("/api/projects", json=body,
                                         headers={"Authorization": f"Bearer {credential}"})
        assert refused.status_code == 403, (credential, refused.text)
    assert ProjectRegistry().list() == [], "a scoped credential registered a project"

    admitted = three_credentials.post("/api/projects", json=body,
                                      headers={"Authorization": "Bearer the-admin"})

    assert admitted.status_code == 200, admitted.text
    assert [p.name for p in ProjectRegistry().list()] == ["acme"]


#: Requests no door may register as written, each with the data a door renders its refusal from.
#: Each is refused before the registry is read for writing, so the file is never touched.
UNREGISTRABLE = {
    "a host nobody here implements": ({"repo_path": "https://gitlab.com/o/acme.git"}, "foreign"),
    "an address missing the coordinates its kind needs": (
        {"repo_path": "https://dev.azure.com/acme-org/Payments"}, "missing"),
    "a model that begins like a flag": ({"repo_path": "/srv/acme", "model": "--flag"}, None),
}


@pytest.mark.parametrize("case", sorted(UNREGISTRABLE))
def test_an_address_that_cannot_be_registered_as_written_is_refused_and_nothing_is_written(
        case, tmp_path, monkeypatch):
    from openfactory.api.app import app as panel

    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    registry = tmp_path / "registry.yaml"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(registry))
    params, rendered_from = UNREGISTRABLE[case]

    out = asyncio.run(actions.perform("project_add", by=ADMIN, project="acme", **params))

    assert out.code == actions.INVALID, out
    if rendered_from:
        assert out.data.get(rendered_from), f"the refusal carries no {rendered_from!r}: {out.data}"
    assert not registry.exists(), f"{case} wrote the registry"
    if "model" not in params:
        # THE PANEL'S DOOR ANSWERS AS IT ALWAYS DID, 422 and the row's sentence
        answered = TestClient(panel).post("/api/projects", json={"name": "acme", **params})
        assert answered.status_code == 422 and answered.json()["detail"] == out.message, (
            answered.text)
        assert not registry.exists()


def test_adding_what_is_registered_changes_nothing_and_adding_it_differently_is_refused(
        tmp_path, monkeypatch):
    """Safe to run again, and never over what is there: the same request is an answer, even after
    a board was attached and a model set since — those are not what was asked — and a request
    for a different address is refused, naming what differs, with the registry byte for byte as
    it was."""
    from openfactory.registry import ProjectRegistry

    registry = tmp_path / "registry.yaml"
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(registry))
    asked = {"project": "acme", "repo_path": "https://github.com/acme-corp/acme.git",
             "language": "pt-BR"}
    assert asyncio.run(actions.perform("project_add", by=ADMIN, **asked)).data["changed"] is True
    ProjectRegistry().attach_board("acme", board_owner="acme-corp", board_number="7")
    ProjectRegistry().set_model("acme", "a-model")
    before = registry.read_bytes()

    again = asyncio.run(actions.perform("project_add", by=ADMIN, **asked))
    elsewhere = asyncio.run(actions.perform("project_add", by=ADMIN,
                                            **{**asked, "repo_path": str(tmp_path / "acme")}))

    assert again.ok and again.data["changed"] is False, again
    assert elsewhere.code == actions.CONFLICT and "repo_path" in elsewhere.data["differs"], (
        elsewhere)
    assert registry.read_bytes() == before, "registering again wrote over what was registered"


# ── 9. a row of several steps says what each came to, and is safe to run again (slice 3) ──────

def _rows_reaching(helper: str) -> set[str]:
    """The rows whose runner reaches `helper` in the catalogue, by a call or by handing a function
    on — the same walk as rule 1's."""
    tree = parsed(CATALOG_PY)
    functions = {n.name: n for n in tree.body
                 if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}

    def reaches(name: str, seen: set[str]) -> bool:
        if name in seen or name not in functions:
            return False
        seen.add(name)
        return name == helper or any(isinstance(n, ast.Name) and reaches(n.id, seen)
                                     for n in ast.walk(functions[name]))

    return {name for name, spec in catalog.CATALOG.items() if reaches(spec.run.__name__, set())}


#: The rows of several steps: those that answer through `_the_steps_came_to`.
STEPPED = sorted(_rows_reaching("_the_steps_came_to"))


@pytest.fixture
def a_machine(tmp_path, monkeypatch):
    """A one-machine deployment with a repository of the person's own — nothing of this machine
    reached, nothing remote."""
    from tests.one_machine import a_deployment, a_repository

    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    a_deployment(tmp_path, monkeypatch=monkeypatch)
    return a_repository(tmp_path)


def _a_push_that_fails_once(monkeypatch) -> None:
    """The first `git push` of the run fails, as a full disk or a dropped connection makes it."""
    import subprocess

    real, state = subprocess.run, {"failed": False}

    def once(args, *a, **kw):
        if isinstance(args, list) and "push" in args and not state["failed"]:
            state["failed"] = True
            raise subprocess.CalledProcessError(1, args, stderr="no room on the disk")
        return real(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", once)


def _init_a_path(repo, monkeypatch):
    """`project_init` on a path, with the context repository's push failing the first time."""
    _a_push_that_fails_once(monkeypatch)
    return {"project": "myapp", "repo_path": str(repo)}, "context"


#: How each row of several steps is driven to fail halfway: `(params, the step that fails)`, the
#: cause failing once and then passing.
HALFWAY = {"project_init": _init_a_path}


def test_every_row_of_several_steps_is_driven_halfway():
    assert STEPPED, "no row answers through `_the_steps_came_to` — the reading sees nothing"
    assert sorted(HALFWAY) == STEPPED, (
        f"rows of several steps {STEPPED}, driven halfway {sorted(HALFWAY)}: a row that takes "
        f"several steps must show what it says when one fails, and that running it again finishes")


@pytest.mark.parametrize("name", STEPPED)
def test_a_row_of_several_steps_says_what_was_done_when_a_step_fails_and_finishes_when_run_again(
        name, a_machine, monkeypatch):
    """A failure halfway is a list of what is done and what is not, not one sentence about the last
    thing that broke; running the row again does what is missing and nothing twice; and a third
    run finds everything there."""
    from openfactory.registry import ProjectRegistry

    params, failing = HALFWAY[name](a_machine, monkeypatch)

    first = asyncio.run(actions.perform(name, by=ADMIN, **params))
    states = {s["step"]: s["state"] for s in first.data["steps"]}
    assert first.code == actions.FAILED and states[failing] == actions.STEP_FAILED, first
    before_it = [s["step"] for s in first.data["steps"]][:list(states).index(failing)]
    assert before_it and all(states[s] == actions.STEP_DONE for s in before_it), (
        f"the steps before {failing!r} are not said to be done: {first.data['steps']}")
    for s in first.data["steps"]:
        assert s["said"] in first.message, f"{s['step']} is not said in the sentence: {first}"

    second = asyncio.run(actions.perform(name, by=ADMIN, **params))
    again = {s["step"]: s["state"] for s in second.data["steps"]}
    assert second.ok and again[failing] == actions.STEP_DONE, second
    assert all(again[s] in (actions.STEP_ALREADY, actions.STEP_SKIPPED) for s in before_it), (
        f"running it again did again what was done: {second.data['steps']}")
    registered = Path(ProjectRegistry().path).read_bytes()

    third = asyncio.run(actions.perform(name, by=ADMIN, **params))
    assert third.ok and all(s["state"] in (actions.STEP_ALREADY, actions.STEP_SKIPPED)
                            for s in third.data["steps"]), third
    assert Path(ProjectRegistry().path).read_bytes() == registered


def test_a_front_end_is_told_which_steps_were_done_when_a_later_one_failed(a_machine,
                                                                          monkeypatch):
    """Through `POST /api/act/{name}` a failed step is the outcome's code, and the steps ride with
    it — so a screen of one's own can show that the project is registered and its board made,
    and offer the same button again."""
    from openfactory.api.app import app as panel

    _a_push_that_fails_once(monkeypatch)

    r = TestClient(panel).post("/api/act/project_init", json={"params": {
        "project": "myapp", "repo_path": str(a_machine)}})

    assert r.status_code == 500, r.text
    said = {s["step"]: s["state"] for s in r.json()["data"]["steps"]}
    assert said["register"] == "done" and said["context"] == "failed", said
    assert "running it again does only what is missing" in r.json()["message"]


@pytest.mark.parametrize("argv,row", [
    (["project", "init", "acme"], "project_init"),
])
def test_each_verb_of_several_steps_runs_its_row_and_writes_nothing_itself(argv, row, one_project,
                                                                          monkeypatch):
    """The command is a mapping: with the row's own code replaced by a recorder, the verb answers,
    the recorder ran once, and the registry is byte for byte as it was."""
    from openfactory import cli

    before, seen = one_project.read_bytes(), []

    async def recorder(by=None, **params):
        seen.append(params)
        return actions.done("recorded", steps=[], local=True, base_branch="main")

    monkeypatch.setattr(catalog, "CATALOG", {**catalog.CATALOG, row: dataclasses.replace(
        catalog.CATALOG[row], run=recorder)})

    out = CliRunner().invoke(cli.app, argv)

    assert out.exit_code == 0, out.output
    assert len(seen) == 1, f"{argv} did not run {row}"
    assert one_project.read_bytes() == before, f"{argv} wrote the registry itself"


# ── 8, again: what is registered is never written over (slice 3) ────────────────────────────

#: The rows that register a project, read off what they write.
REGISTERS = sorted(name for name, what in _catalog_writes().items()
                   if "ProjectRegistry.add" in what)


def _add_elsewhere(repo):
    return {"project": "myapp", "repo_path": str(repo.parent / "elsewhere")}


def _init_elsewhere(repo):
    return {"project": "myapp", "repo_path": str(repo.parent / "elsewhere"), "language": "pt-BR"}


#: For each row that registers: a request naming a project already registered, differently.
OVER_IT = {"project_add": _add_elsewhere, "project_init": _init_elsewhere}


def test_every_row_that_registers_is_asked_to_write_over_a_project():
    assert sorted(OVER_IT) == REGISTERS, (REGISTERS, sorted(OVER_IT))


@pytest.mark.parametrize("name", REGISTERS)
def test_a_row_that_registers_never_writes_over_what_is_registered(name, a_machine):
    """Whatever the request says, a project that is registered keeps its address, its axes and its
    language: `project_add` refuses and names what differs, and `project_init` initialises the
    project as it is registered."""
    from openfactory.registry import ProjectRegistry

    assert asyncio.run(actions.perform("project_add", by=ADMIN, project="myapp",
                                       repo_path=str(a_machine))).ok
    before = Path(ProjectRegistry().path).read_bytes()

    out = asyncio.run(actions.perform(name, by=ADMIN, **OVER_IT[name](a_machine)))

    assert out.ok or out.code == actions.CONFLICT, out
    assert Path(ProjectRegistry().path).read_bytes() == before, f"{name} wrote over myapp"
