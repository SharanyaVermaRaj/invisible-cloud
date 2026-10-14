"""The HTTP API as the web app uses it."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import get_llm
from app.db import get_session
from app.main import app


def fake_llm(*calls):
    queue = [SimpleNamespace(content=[SimpleNamespace(type="tool_use", name=n, input=i, id="t")]) for n, i in calls]
    return SimpleNamespace(messages=SimpleNamespace(create=lambda **k: queue.pop(0)))


@pytest.fixture
def make_client(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_llm] = lambda: None
    yield lambda: TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(make_client):
    c = make_client()
    c.get("/api/state")
    return c


HANDOVER = {"summary": "Sarah takes Acme payroll", "operations": [
    {"op": "unrelate", "subject": "mike", "relation": "assigned_to", "object": "acme_payroll"},
    {"op": "relate", "subject": "sarah", "relation": "assigned_to", "object": "acme_payroll"}]}


def test_first_visit_creates_a_private_workspace(make_client):
    a, b = make_client(), make_client()
    sa, sb = a.get("/api/state").json(), b.get("/api/state").json()
    assert sa["workspace"]["name"] == "Parkside Accounting"
    assert sa["me"]["key"] == "elena" and sa["me"]["is_admin"]
    assert len(sa["documents"]) == 7
    # Changes in one workspace don't leak into another.
    assert a.post("/api/changes", json=HANDOVER).status_code == 201
    mike_b = b.get("/api/state", headers={"X-Acting-As": "mike"}).json()
    assert {d["key"] for d in mike_b["documents"]} == {"acme_w2", "acme_payroll_report"}


def test_requests_without_a_workspace_are_rejected(make_client):
    r = make_client().post("/api/changes", json=HANDOVER)
    assert r.status_code == 404 and "expired" in r.json()["detail"]


def test_tampered_cookie_is_ignored(make_client):
    c = make_client()
    c.cookies.set("ic_workspace", "forged")
    assert c.post("/api/changes", json=HANDOVER).status_code == 404


def test_persona_view_hides_documents(client):
    mike = client.get("/api/state", headers={"X-Acting-As": "mike"}).json()
    assert mike["me"]["is_admin"] is False
    assert mike["hidden_documents"] == 5
    assert "access" not in mike["documents"][0]


def test_only_partners_can_change_rules(client):
    r = client.post("/api/changes", json=HANDOVER, headers={"X-Acting-As": "mike"})
    assert r.status_code == 403


def test_change_preview_apply_history_undo(client):
    p = client.post("/api/changes/preview", json=HANDOVER).json()
    assert {x["person"] for x in p["lost"]} == {"mike"}
    applied = client.post("/api/changes", json=HANDOVER).json()
    history = client.get("/api/history").json()
    assert history[0]["id"] == applied["id"] and history[0]["undoable"]
    assert history[-1]["undoable"] is False
    assert client.post(f"/api/history/{applied['id']}/undo/preview").status_code == 200
    assert client.post(f"/api/history/{applied['id']}/undo").status_code == 200
    assert client.get("/api/can", params={"person": "mike", "action": "read", "resource": "acme_w2"}).json()["allowed"]
    again = client.post(f"/api/history/{applied['id']}/undo")
    assert again.status_code == 422 and "already" in again.json()["detail"]


def test_conflicts_return_409_with_resolutions(client):
    body = {"summary": "exempt", "operations": [{"op": "set_rule", "key": "ex", "text": "x",
            "definition": {"type": "exemption", "role": "accountant", "doc_kind": "tax_return", "max_amount": 10000}}]}
    r = client.post("/api/changes", json=body)
    assert r.status_code == 409
    resolutions = r.json()["preview"]["resolutions"]
    assert client.post("/api/changes", json=resolutions[0]["proposal"]).status_code == 201


def test_ask_without_ai_configured(client):
    r = client.post("/api/ask", json={"text": "Sarah is now a partner"})
    assert r.status_code == 503


def test_ask_with_ai(client):
    app.dependency_overrides[get_llm] = lambda: fake_llm(("propose_change", HANDOVER))
    r = client.post("/api/ask", json={"text": "Sarah will take Acme payroll"}).json()
    assert r["type"] == "proposal" and r["lost"]
    app.dependency_overrides[get_llm] = lambda: fake_llm(("answer", {"text": "Elena, Mike and Dana."}))
    assert client.post("/api/ask", json={"text": "Who sees the W-2?"}).json() == {
        "type": "answer", "text": "Elena, Mike and Dana."}


def test_ai_rate_limit(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "ai_limit_per_workspace_per_hour", 1)
    app.dependency_overrides[get_llm] = lambda: fake_llm(("answer", {"text": "ok"}), ("answer", {"text": "ok"}))
    assert client.post("/api/ask", json={"text": "q"}).status_code == 200
    assert client.post("/api/ask", json={"text": "q"}).status_code == 429


def test_file_download_enforces_access(client):
    ok = client.get("/api/documents/acme_w2/file", params={"as": "mike"})
    assert ok.status_code == 200 and ok.content.startswith(b"%PDF")
    assert ok.headers["content-type"] == "application/pdf"
    denied = client.get("/api/documents/acme_w2/file", params={"as": "john"})
    assert denied.status_code == 403


def test_upload_send_and_approve(client):
    r = client.post("/api/documents", headers={"X-Acting-As": "john"},
                    data={"title": "Acme amended return", "client_service": "acme_tax",
                          "kind": "tax_return", "amount": "$8,000"},
                    files={"file": ("amended.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert r.status_code == 201, r.text
    key = r.json()["key"]
    sent = client.post(f"/api/documents/{key}/send", headers={"X-Acting-As": "john"}).json()
    assert sent["status"] == "pending"
    elena = client.get("/api/state").json()
    assert [a["document"] for a in elena["approvals"]] == [key]
    assert client.post(f"/api/approvals/{sent['id']}/approve", headers={"X-Acting-As": "mike"}).status_code == 403
    assert client.post(f"/api/approvals/{sent['id']}/approve", json={"note": "ok"}).json()["status"] == "sent"


def test_upload_validation(client):
    r = client.post("/api/documents", data={"client_service": "acme_tax", "amount": "lots"},
                    files={"file": ("a.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 422
    r = client.post("/api/documents", data={"client_service": "acme_tax", "kind": "spaceship"},
                    files={"file": ("a.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 422


def test_reset_gives_a_fresh_firm(client):
    client.post("/api/changes", json=HANDOVER)
    client.post("/api/workspace/reset")
    mike = client.get("/api/state", headers={"X-Acting-As": "mike"}).json()
    assert {d["key"] for d in mike["documents"]} == {"acme_w2", "acme_payroll_report"}
    assert len(client.get("/api/history").json()) == 1


def test_spa_routes(client):
    assert client.get("/api/nope").status_code == 404
    assert client.get("/app/documents").status_code == 200
    assert client.get("/../etc/passwd").status_code == 404
