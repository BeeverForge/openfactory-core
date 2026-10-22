"""A refused gate key is said as itself, and a refused preview key on the card — never "not waiting".

The maintainer's ready tests from the review of 493875d3 (point 1), as written there: a gate key
the credential store refuses was raised as a plain `RuntimeError`, which the merge gate and both
"another pass" paths read as "the engine answered: this job is not at that gate", so a person was
told to do again what they had just done, and the key was never named. `gate_seal.KeyRefused` is
the store's refusal, said by every caller that seals an answer.
"""

import asyncio
import time

import pytest

SECRET = "fictitious-gate-key-822"


@pytest.fixture
def refused_key(tmp_path, monkeypatch):
    d = tmp_path / "secrets"
    d.mkdir(mode=0o700)
    for name in ("OPENFACTORY_GATE_SECRET", "OPENFACTORY_PREVIEW_SECRET"):
        (d / name).write_text(SECRET + "\n")
        (d / name).chmod(0o664)
        monkeypatch.setenv(name, "fictitious-variable-822")
    monkeypatch.setenv("OPENFACTORY_CREDENTIAL_STORE", "file")
    monkeypatch.setenv("OPENFACTORY_CREDENTIAL_DIR", str(d))

class _AtTheGates:
    signals: list = []
    def get_workflow_handle(self, wf): return self
    async def query(self, q, *a):
        return {"awaiting_merge": {"pr": 7, "adjusts_left": 2}, "awaiting_approval": True,
                "release_wait": {"hears": True, "adjusts_left": 2}}.get(getattr(q, "__name__", q))
    async def signal(self, *a, **k): self.signals.append(a)

def test_a_refused_gate_key_is_said_as_itself_at_the_merge_gate(refused_key, monkeypatch):
    from openfactory.actions import catalog
    async def connected(): return _AtTheGates(), None
    monkeypatch.setattr(catalog, "_project", lambda p: (type("P", (), {"name": "acme"})(), None))
    monkeypatch.setattr(catalog, "_connected", connected)
    _gate, bad = asyncio.run(catalog._answer_gate(project="acme", issue="12", by="ana", answer="merge"))
    said = str(getattr(bad, "message", bad))
    assert not _AtTheGates.signals
    assert "OPENFACTORY_GATE_SECRET" in said and "not waiting on a merge" not in said, said
    assert SECRET not in said

def test_a_refused_gate_key_is_not_a_job_that_is_not_waiting(refused_key, monkeypatch):
    import openfactory.product.release as release
    from openfactory.product import adjust
    async def client(): return _AtTheGates()
    monkeypatch.setattr(release, "_client", client)
    project = type("P", (), {"name": "acme"})()
    assert adjust._not_yet(project, "12", instruction="again", by="ana") != adjust.NOT_WAITING
    assert adjust.answer_gate(project, "12", answer="adjust", instruction="x", by="ana") != adjust.NOT_WAITING

def test_a_refused_preview_key_is_said_on_the_card_not_a_500(refused_key, monkeypatch):
    from fastapi.testclient import TestClient

    import openfactory.api.app as app
    from openfactory import preview
    from openfactory.preview import demand
    owner = type("O", (), {"name": "acme", "preview": None, "language": None})()
    monkeypatch.setattr(preview, "domain", lambda: "pv.example")
    monkeypatch.setattr(app, "ProjectRegistry", lambda: type("R", (), {"list": lambda s: [owner]})())
    monkeypatch.setattr(preview, "unit_of_card", lambda project, card: card)
    live = preview.Preview(project="acme", unit="12", state=preview.LIVE, expires_at=int(time.time()) + 3600)
    monkeypatch.setattr(preview, "latest", lambda project, unit: live)
    monkeypatch.setattr(demand, "forge_state", lambda *a, **k: None)
    monkeypatch.setattr(demand, "judge", lambda *a, **k: type("J", (), {"can_start": False, "stale": False, "why": ""})())
    r = TestClient(app.app, raise_server_exceptions=False).get("/api/preview/acme/12")
    assert r.status_code == 200, r.status_code
    assert "OPENFACTORY_PREVIEW_SECRET" in r.json()["why"] and not r.json()["live"]
    assert SECRET not in r.text


def test_a_refused_gate_key_is_said_as_itself_at_the_production_approval(refused_key, monkeypatch):
    """The approval gate seals its answer too: a refused key is said by name, never as "not parked
    at the approval gate", and nothing is signalled."""
    import openfactory.approvals as approvals
    from openfactory.actions import catalog

    engine = _AtTheGates()
    engine.signals = []

    async def connected():
        return engine, None

    acted: dict = {}

    class _Stop(Exception):
        pass

    async def door(found, issue, event, *, act, **_kw):
        acted["said"] = await act()
        raise _Stop

    monkeypatch.setattr(catalog, "_project", lambda p: (type("P", (), {"name": "acme"})(), None))
    monkeypatch.setattr(catalog, "_connected", connected)
    monkeypatch.setattr(catalog, "_prod_allowlist", lambda found: ["ana"])
    monkeypatch.setattr(approvals, "verify_approver", lambda *a, **k: True)
    monkeypatch.setattr(catalog, "_through_the_door", door)
    with pytest.raises(_Stop):
        asyncio.run(catalog._approve_prod(project="acme", issue="12", version="1.0", approver="ana",
                                          password="fictitious", by="ana"))
    said = str(getattr(acted["said"], "message", acted["said"]))
    assert "OPENFACTORY_GATE_SECRET" in said and SECRET not in said, said
    assert not engine.signals
