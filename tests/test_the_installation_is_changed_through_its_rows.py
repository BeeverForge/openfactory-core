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
     revoked while nothing else closes the panel's door.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import json
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
    """`row → what it writes`, following the catalogue's own helpers it calls by name."""
    tree = parsed(CATALOG_PY)
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}

    def reached(name: str, seen: set[str]) -> set[str]:
        if name in seen or name not in functions:
            return set()
        seen.add(name)
        fn = functions[name]
        out = _writes_directly(fn)
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                out |= reached(n.func.id, seen)
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


@pytest.mark.parametrize("jobs,said", [
    ([{"project": "routing", "issue": "210", "status": "running"}], "wait for them"),
    (None, "do not roll the deployment"),
    ([], "Nothing is in flight"),
], ids=["running", "unread", "drained"])
def test_a_pause_from_the_panel_says_what_is_still_running(monkeypatch, jobs, said):
    """The sentence `poller pause` exists to print travels with the row, so a screen of one's own
    is told it too: a pause holds NEW pickups, and a pause that read as "drained" is how a job is
    interrupted by somebody who paused to protect it. An unread list is not a drained floor."""
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
    assert r.json()["data"]["in_flight"] == (None if jobs is None else jobs)


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
