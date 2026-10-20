"""A shared credential is who it is, whatever a request says about itself.

TWO RULES, ONE ROOT — who a shared credential is:

1. A MISSING LABEL NEVER WIDENS A CREDENTIAL. The shared board and product tokens name nobody
   and are still scoped (`identity/local.py`). The panel answered `UNKNOWN` — which asserts no
   group — whenever `X-OpenFactory-Actor` was left out, so the action layer saw an unscoped
   administrator. Measured on 2026-10-19: the shared board token reached `preview_start`, a row
   of the product area, through `/api/act` without the header, and was refused it with one. And
   the panel read the credential from the Bearer header alone, while the gate also admits the
   credential cookie and `?token=`: by those, `/api/whoami` answered the board token as unscoped.
   So the rule is held by every transport the gate reads.
2. A LABEL IS NEVER AN IDENTITY. The header became the subject's display; the answer route
   recorded `id or display` as who answered and asked the product gate about that string as the
   person deciding, and `run_staged` recorded it as who pressed. It is a display hint now, carried
   as `Actor.label` and printed only by the audit line.

THE CASES ARE READ FROM THE CODE, so tomorrow's are covered without editing this file. The shared
credentials are every variable in `identity/local.py::CLOSING_ENVS` whose value is itself a
credential, resolved by the provider; the scoped ones are those whose subject carries a group the
action layer knows (`_scopes_of`). The rows are the action catalogue, and a row is outside a
credential's area when `Actor.may_enter` says so. A guard fails when either table comes back
empty. Every value here is fictitious.
"""

from __future__ import annotations

import ast
import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openfactory import actions
from openfactory.actions import catalog
from openfactory.identity.base import ANONYMOUS, Subject
from openfactory.identity.local import CLOSING_ENVS, LocalIdentity
from openfactory.memory import messages
from tests.test_a_person_is_invited_not_signed_up import local  # noqa: F401 — the fixture
from tests.test_the_panel_is_a_channel import sink  # noqa: F401 — the fixture

ROOT = Path(__file__).resolve().parents[1]

#: A credential value with no `:` — so a `token:id:display` variable reads it as no row at all,
#: and only a variable whose value IS the credential resolves it.
SECRET = "fictitious-shared-credential-4417"
#: What a caller on a shared credential says it is: a fictitious person a gate would recognise.
LABEL = "bia@acme.example"
#: A row for the variables that name one person per secret, to tell them apart from the shared.
NAMED_ROW = "fictitious-named-credential-9021:leo@acme.example:Leo Fictício"


class _NobodyRegistered:
    """The people store, with nobody in it — the provider is asked about the environment alone."""

    def session_of(self, token):
        return None

    def has_people(self):
        return False


def _resolved(var: str, value: str, credential: str):
    return LocalIdentity(env={var: value}, store=_NobodyRegistered()).identify(
        credential=credential)


def _scopes_of(subject):
    from openfactory.api.app import _scopes_of as the_panels

    return the_panels(subject)


def _shared() -> list[tuple[str, Subject]]:
    """Every closing variable whose value is a credential naming nobody, with what it resolves to."""
    out = []
    for var in CLOSING_ENVS:
        subject = _resolved(var, SECRET, SECRET)
        if subject is not None and not subject.known:
            out.append((var, subject))
    return out


def _named() -> list[tuple[str, Subject]]:
    """Every closing variable that names a person per secret, with the person it resolves to."""
    out = []
    for var in CLOSING_ENVS:
        subject = _resolved(var, NAMED_ROW, NAMED_ROW.split(":", 1)[0])
        if subject is not None and subject.known:
            out.append((var, subject))
    return out


SHARED = _shared()
SHARED_SCOPED = [(var, subject) for var, subject in SHARED if _scopes_of(subject)]
NAMED = _named()


def _outside(scopes) -> list[actions.ActionSpec]:
    """The catalogue's rows a credential of these scopes may not enter, by the layer's own rule."""
    probe = actions.Actor(id="", scopes=scopes)
    return [spec for spec in catalog.CATALOG.values() if not probe.may_enter(spec.scope)]


#: The card's own control on the product view: the row that closes or removes a card, which
#: vouches for an OPERATOR — an admin who may enter the floor — beside the card's requester.
CARD_CONTROL = "product_withdraw_card"
#: The shared scoped credentials whose area that row is in.
_REACHING_THE_CARD = [
    (var, subject) for var, subject in SHARED_SCOPED
    if actions.Actor(id="", scopes=_scopes_of(subject)).may_enter(
        catalog.CATALOG[CARD_CONTROL].scope)]


def _params(spec: actions.ActionSpec) -> dict[str, str]:
    """A value for every parameter the row requires, so `perform` gets as far as the scope check:
    a row refused for a missing parameter would be refused for the wrong reason."""
    return {name: "7" for name in spec.required}


#: THE WAYS A REQUEST PRESENTS A CREDENTIAL, in the order the gate reads them
#: (`api/app.py::_credential_of`): a fetch's Bearer header, the browser's credential cookie, and
#: `?token=`, which is how an EventSource presents one. The gate admits a request by any of them,
#: so the actor must be the same by any of them; each is held to the gate's own reader below.
TRANSPORTS = ("header", "cookie", "query")


def _presented(transport: str, credential: str = SECRET,
               label: str | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """`(headers, query)` of a request presenting `credential` by `transport`, labelled or not."""
    from openfactory.identity.base import TOKEN_COOKIE

    headers: dict[str, str] = {}
    query: dict[str, str] = {}
    if transport == "header":
        headers["authorization"] = f"Bearer {credential}"
    elif transport == "cookie":
        headers["cookie"] = f"{TOKEN_COOKIE}={credential}"   # plain http: the plain name
    elif transport == "query":
        query["token"] = credential
    else:
        raise ValueError(f"no transport called {transport!r}; there are {TRANSPORTS}")
    if label is not None:
        headers["x-openfactory-actor"] = label
    return headers, query


def _request(transport: str, credential: str = SECRET, label: str | None = None):
    """A request as the panel's door reads one — Starlette's own, so its cookie and its query are
    parsed the way a served request's are."""
    from urllib.parse import urlencode

    from starlette.requests import Request

    headers, query = _presented(transport, credential, label)
    return Request({"type": "http", "method": "GET", "path": "/api/whoami", "scheme": "http",
                    "server": ("testserver", 80), "query_string": urlencode(query).encode(),
                    "headers": [(k.encode(), v.encode()) for k, v in headers.items()]})


def _headers(label: str | None = None, credential: str = SECRET) -> dict[str, str]:
    """A Bearer request's headers: the one transport a mutating route takes (`require_auth`)."""
    return _presented("header", credential, label)[0]


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    """The panel with no credential configured; a test sets the one it is about."""
    monkeypatch.setenv("OPENFACTORY_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.delenv("OPENFACTORY_IDENTITY", raising=False)
    for var in CLOSING_ENVS:
        monkeypatch.delenv(var, raising=False)
    from openfactory.api.app import app

    return TestClient(app)


@pytest.fixture
def spied(monkeypatch) -> list[str]:
    """Every row's own code replaced by a spy: a row that runs is a row whose name lands here."""
    ran: list[str] = []

    def _spy(name: str):
        async def run(**_params):
            ran.append(name)
            return actions.done(f"{name} ran")
        return run

    for name, spec in list(catalog.CATALOG.items()):
        monkeypatch.setitem(catalog.CATALOG, name, replace(spec, run=_spy(name)))
    return ran


@pytest.fixture
def cards(deployment, tmp_path, monkeypatch):
    """`acme`, with a product role and a local board, beside the panel — and what its
    conversation is told. `(client, tracker, board, told)`."""
    monkeypatch.setenv("OPENFACTORY_BOARD_DB", str(tmp_path / "board.db"))
    monkeypatch.setenv("OPENFACTORY_LOG_DIR", str(tmp_path / "logs"))
    from openfactory.adapters.board import build_board
    from openfactory.adapters.board_setup.local import LocalBoardSetup
    from openfactory.adapters.tracker.registry import build_tracker
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.product import events
    from openfactory.product.board import forget_board
    from openfactory.registry import ProjectRegistry

    registry = ProjectRegistry()
    registry.add(Project(name="acme", repo_path=str(tmp_path), language="en",
                         tracker=ProviderRef(kind="local", repo="acme", options={}),
                         product=ProductConfig(docs_repo="acme/docs", admins=["po-admin-12"])))
    project = registry.get("acme")
    LocalBoardSetup().create(project=project, owner="", title="acme", token=None)
    forget_board()
    told: list[dict] = []
    monkeypatch.setattr(events, "_tell", lambda project, **kw: told.append(kw) or True)
    yield deployment, build_tracker(project), build_board(project), told
    forget_board()


# ── the tables this file reads ──────────────────────────────────────────────────────────────────

def test_the_tables_this_file_reads_are_not_empty():
    """A family read from an empty table is a test of nothing that passes."""
    assert SHARED_SCOPED, f"no shared scoped credential among {CLOSING_ENVS}"
    assert len(SHARED) > len(SHARED_SCOPED), "the unscoped shared panel token was not found"
    assert NAMED, f"no credential naming a person among {CLOSING_ENVS}"
    for var, subject in SHARED_SCOPED:
        assert subject.id == "" and subject.via == ANONYMOUS, (var, subject)
        assert _outside(_scopes_of(subject)), f"{var} is outside no row's area"
    assert _REACHING_THE_CARD, "no shared credential reaches the product view's card control"


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_every_transport_here_is_one_the_gate_reads(transport):
    from openfactory.api.app import _credential_of

    assert _credential_of(_request(transport)) == SECRET, transport


# ── 1. a missing label never widens a credential, by any transport ──────────────────────────────

@pytest.mark.parametrize("label", [None, LABEL], ids=["no-label", "label"])
@pytest.mark.parametrize("transport", TRANSPORTS)
@pytest.mark.parametrize(("var", "subject"), SHARED, ids=[v for v, _ in SHARED])
def test_a_shared_credential_acts_with_its_own_scope_whether_or_not_it_sends_a_label(
        deployment, monkeypatch, var, subject, transport, label):
    from openfactory.api.app import _actor, _subject

    monkeypatch.setenv(var, SECRET)
    request = _request(transport, label=label)

    who, actor = _subject(request), _actor(request)

    assert tuple(who.groups) == tuple(subject.groups), (var, transport, label, who)
    assert who.display == subject.display, (var, transport, label, who)
    assert actor.scopes == _scopes_of(subject), (var, transport, label, actor)
    assert actor.id == "" and actor.admin is True, (var, transport, label, actor)


@pytest.mark.parametrize("label", [None, LABEL], ids=["no-label", "label"])
@pytest.mark.parametrize("transport", TRANSPORTS)
@pytest.mark.parametrize(("var", "subject"), SHARED, ids=[v for v, _ in SHARED])
def test_whoami_answers_a_shared_credentials_own_scope_by_every_transport(
        deployment, monkeypatch, var, subject, transport, label):
    """The read a page renders its surface from, as a browser asks it: the scope and the name are
    the credential's, however it was presented and whatever it says about itself."""
    monkeypatch.setenv(var, SECRET)
    headers, query = _presented(transport, label=label)

    r = deployment.get("/api/whoami", headers=headers, params=query)

    assert r.status_code == 200, (var, transport, r.status_code, r.text)
    scopes = _scopes_of(subject)
    said = r.json()
    assert said["scopes"] == (sorted(scopes) if scopes is not None else None), (transport, said)
    assert (said["id"], said["known"], said["display"]) == ("", False, subject.display), said


@pytest.mark.parametrize("label", [None, LABEL], ids=["no-label", "label"])
@pytest.mark.parametrize(("var", "subject"), SHARED_SCOPED, ids=[v for v, _ in SHARED_SCOPED])
def test_a_shared_scoped_credential_is_refused_every_row_outside_its_area(
        deployment, spied, monkeypatch, var, subject, label):
    """Through `/api/act`, the door every row has. The gate refuses some of these by their path
    and the action layer the rest; either way the row's own code never runs, so nothing is
    written."""
    monkeypatch.setenv(var, SECRET)
    rows = _outside(_scopes_of(subject))

    through = {}
    for spec in rows:
        r = deployment.post(f"/api/act/{spec.name}", headers=_headers(label),
                            json={"params": _params(spec)})
        if r.status_code != 403:
            through[spec.name] = (r.status_code, r.text[:160])

    assert not through, f"{var} ({label=}) was not refused these rows: {through}"
    assert spied == [], f"{var} ({label=}) ran rows outside its area: {spied}"


@pytest.mark.parametrize("label", [None, LABEL], ids=["no-label", "label"])
@pytest.mark.parametrize(("var", "subject"), SHARED_SCOPED, ids=[v for v, _ in SHARED_SCOPED])
def test_a_shared_scoped_credential_cannot_invite_an_administrator(
        deployment, local, monkeypatch, var, subject, label):  # noqa: F811
    """`people_invite` is the administrator's by a rule in its own body, which no area expresses:
    every scoped credential is refused it as scoped — 403 — and not merely because nobody vouched,
    which is the voucher rule answering for a credential the scope check let through."""
    monkeypatch.setenv(var, SECRET)

    r = deployment.post("/api/act/people_invite", headers=_headers(label),
                        json={"params": {"person": "leo@acme.example"}})

    assert r.status_code == 403, (var, label, r.status_code, r.text)
    assert local.rows == [], "an invitation was stored"


@pytest.mark.parametrize("label", [None, LABEL], ids=["no-label", "label"])
@pytest.mark.parametrize(("var", "subject"), _REACHING_THE_CARD,
                         ids=[v for v, _ in _REACHING_THE_CARD])
def test_a_shared_credential_is_no_operator_on_a_card_of_the_product_view(
        cards, monkeypatch, var, subject, label):
    """What the scope is FOR, seen on a row inside the credential's own area. The card's control
    lets an operator close or remove any card, and an operator is an admin who may enter the
    floor: a shared product token that the panel left unscoped was one. It is nobody, scoped to its
    area, so a card somebody else asked for is refused it, and the card, the board and the
    conversation are as they were."""
    from tests.test_a_card_nobody_started_can_be_closed_and_removed import (
        _audit,
        _opened_by_product,
    )

    client, tracker, board, told = cards
    monkeypatch.setenv(var, SECRET)
    ref = _opened_by_product(tracker, board)

    for remove in (False, True):
        r = client.post(f"/api/act/{CARD_CONTROL}", headers=_headers(label),
                        json={"params": {"project": "acme", "number": ref,
                                         "reason": "not needed", "remove": remove}})
        # THE ROW'S OWN REFUSAL: the module's "not yours" is a refusal, 403 `denied` — it answered
        # 500 `failed` until #908 (measured on 620bb577)
        assert (r.status_code, r.json()["code"]) == (403, "denied"), (var, label, remove, r.text)
        assert "only the person who asked for" in r.json()["message"], r.json()["message"]

    assert tracker.get_ticket(ref).state == "open", "the card was closed"
    assert ref.lstrip("#") in {s.ref for s in tracker.list_tickets(state="open")}
    assert _audit(ref) is None, "the card was removed"
    assert told == [], "the conversation was told something happened"


# ── 2. a label is never an identity ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("transport", TRANSPORTS)
@pytest.mark.parametrize(("var", "subject"), SHARED, ids=[v for v, _ in SHARED])
def test_a_label_is_a_hint_beside_an_anonymous_actor_and_never_who_it_is(
        deployment, monkeypatch, var, subject, transport):
    """Every action runs on this actor, and a row records `id`, `display` or `str(by)` as who
    acted: the label is in none of them."""
    from openfactory.api.app import _actor, _subject

    monkeypatch.setenv(var, SECRET)
    request = _request(transport, label=LABEL)

    who, actor = _subject(request), _actor(request)

    assert LABEL not in (who.id, who.display), who
    assert who.display == subject.display, "the subject is not the provider's"
    assert actor.label == LABEL, "the label is not carried at all"
    for recorded in (actor.id, actor.display, str(actor)):
        assert LABEL not in recorded, (var, recorded)


@pytest.mark.parametrize("transport", TRANSPORTS)
@pytest.mark.parametrize(("var", "subject"), NAMED, ids=[v for v, _ in NAMED])
def test_a_named_person_carries_no_label(deployment, monkeypatch, var, subject, transport):
    from openfactory.api.app import _actor

    monkeypatch.setenv(var, NAMED_ROW)
    actor = _actor(_request(transport, NAMED_ROW.split(":", 1)[0], LABEL))

    assert (actor.id, actor.display, actor.label) == (subject.id, subject.display, ""), actor


def test_a_subject_its_provider_marked_anonymous_carries_no_id_into_the_actor():
    """`known` is the one spelling of anonymous: an id a provider filled in beside `ANONYMOUS`
    does not make the caller somebody."""
    from starlette.requests import Request

    from openfactory.api.app import _actor_of

    actor = _actor_of(Request({"type": "http", "headers": []}),
                      Subject(id=LABEL, display="a shared credential", via=ANONYMOUS),
                      label=LABEL)

    assert actor.id == "" and actor.label == LABEL, actor


@pytest.mark.parametrize(("var", "subject"), SHARED, ids=[v for v, _ in SHARED])
def test_an_answer_is_recorded_under_the_credentials_name_not_its_label(
        deployment, sink, monkeypatch, var, subject):  # noqa: F811
    monkeypatch.setenv(var, SECRET)
    messages.ask("demo", "subo?", token="ask-1", approve="Sim", reject="Não", channel="demo")

    r = deployment.post("/api/messages/demo/answer", headers=_headers(LABEL),
                        json={"token": "ask-1", "answer": "approve"})

    answered = messages.answer_of("demo", "ask-1")
    if r.status_code == 403:  # the gate refused this credential the route: nothing recorded
        assert answered is None, answered
        return
    assert r.status_code == 200, r.text
    assert answered is not None and answered.by == subject.display, answered
    assert LABEL not in r.json()["by"], r.json()


@pytest.mark.parametrize(("var", "subject"), SHARED, ids=[v for v, _ in SHARED])
def test_the_product_gate_is_asked_about_nobody_for_a_shared_credential(
        deployment, sink, tmp_path, monkeypatch, var, subject):  # noqa: F811
    """A staged product proposal is decided by WHO answers: the gate checks that id against the
    product's approvers and the proposal's requester. A credential naming nobody is nobody there,
    whatever the label says — the label here is exactly the id an approver would have."""
    from openfactory.contracts.project import Project, ProviderRef
    from openfactory.product import confirm
    from openfactory.registry import ProjectRegistry

    ProjectRegistry().add(Project(name="demo", repo_path=str(tmp_path / "demo"),
                                  tracker=ProviderRef(kind="local", repo="demo", options={})))
    monkeypatch.setenv(var, SECRET)
    messages.ask("demo", "grava?", token="key-1|fp", approve="Sim", reject="Não", channel="demo")
    asked: list[str] = []

    def _gate(project, *, user, **_kw):
        asked.append(user)
        return "unauthorized", "only an approver may say yes"

    monkeypatch.setattr(confirm, "answer_staged", _gate)

    r = deployment.post("/api/messages/demo/answer", headers=_headers(LABEL),
                        json={"token": "key-1|fp", "answer": "approve"})

    if r.status_code == 403 and not asked:  # the gate refused this credential the route
        return
    assert asked == [""], f"{var} was put to the product gate as {asked}"


@pytest.mark.parametrize(("var", "subject"), SHARED, ids=[v for v, _ in SHARED])
def test_a_pressed_proposal_is_recorded_under_the_credentials_name_not_its_label(
        deployment, sink, monkeypatch, var, subject):  # noqa: F811
    monkeypatch.setenv(var, SECRET)
    token = messages.suggestion_token("resume", "7")
    messages.say("demo", "I'd resume it", channel="demo", token=token,
                 payload=json.dumps({"suggestion": ["resume", "7"]}))

    async def _performed(name, *, by, **params):
        return actions.done(f"{name} ran")

    monkeypatch.setattr(actions, "perform", _performed)

    r = deployment.post("/api/messages/demo/suggestion", headers=_headers(LABEL),
                        json={"token": token})

    answered = messages.answer_of("demo", token)
    if r.status_code == 403 and answered is None:  # the gate refused this credential the route
        return
    assert r.status_code == 200, r.text
    assert answered is not None and answered.by == subject.display, answered


@pytest.mark.parametrize(("var", "subject"), SHARED, ids=[v for v, _ in SHARED])
def test_a_label_never_vouches_for_an_invitation(
        deployment, local, monkeypatch, var, subject):  # noqa: F811
    monkeypatch.setenv(var, SECRET)

    r = deployment.post("/api/act/people_invite", headers=_headers(LABEL),
                        json={"params": {"person": "leo@acme.example"}})

    assert r.status_code in (400, 403) and not r.json().get("ok"), r.text
    assert local.rows == [], f"{var} with a label stored an invitation"


def test_the_label_is_read_in_one_place():
    """Every reader of the header goes through `_label_of`, whose answer is only ever a hint.
    Read from the package's syntax, not its text, so a comment naming the header counts for
    nothing."""
    readers = []
    for path in sorted((ROOT / "openfactory").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = [fn for fn in ast.walk(tree)
                     if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef)]
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value.strip().lower() == "x-openfactory-actor"):
                continue
            # the innermost function around it, or the module itself for a module-level name
            around = [fn for fn in functions
                      if fn.lineno <= node.lineno <= (fn.end_lineno or fn.lineno)]
            where = min(around, key=lambda fn: fn.end_lineno - fn.lineno).name if around \
                else "<module>"
            readers.append(f"{path.relative_to(ROOT).as_posix()}::{where}")

    assert readers == ["openfactory/api/app.py::_label_of"], readers


def test_an_anonymous_actor_is_refused_as_scoped_by_the_layer_itself(spied):
    """The rule one floor down, without the panel: the actor a shared scoped credential becomes
    is refused every row outside its area by `perform`, before the row's code."""
    for _var, subject in SHARED_SCOPED:
        scopes = _scopes_of(subject)
        actor = actions.Actor(id="", display=subject.display, via="panel", admin=True,
                              scopes=scopes, label=LABEL)
        for spec in _outside(scopes):
            out = asyncio.run(actions.perform(spec.name, by=actor, **_params(spec)))
            assert out.code == actions.DENIED, (spec.name, out)
    assert spied == [], f"rows ran outside the actor's area: {spied}"
