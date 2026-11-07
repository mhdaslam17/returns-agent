"""API tests with the fake brain. No LLM, and no embedding model (lifespan is not started)."""

import pytest
from fastapi.testclient import TestClient

from returns_agent.api import app
from returns_agent.labels import Action


@pytest.fixture
def client():
    return TestClient(app)  # not used as a context manager, so the model warm-up does not run


def test_page_and_test_emails(client):
    assert "Returns Agent Tester" in client.get("/").text
    emails = client.get("/api/test-emails").json()
    assert len(emails) >= 60 and emails[0]["id"] == "E001"


def test_customers_come_from_the_database(client):
    rows = client.get("/api/customers").json()
    assert len(rows) == 29
    by_order = {r["order_id"]: r for r in rows}
    assert by_order["DL-1026"]["nights_since_delivery"] == 100
    assert by_order["DL-1026"]["note"].startswith("exactly 100 nights")
    assert by_order["DL-1010"]["nights_since_delivery"] is None
    assert "sara.husband@example.com" not in {r["email"] for r in rows}  # not a customer


def test_big_refund_pauses_then_approval_pays(client, fake_brain):
    fake_brain.update(order_id="DL-1001", action=Action.PREPARE_REFUND, payment_id="PAY-1001-A", amount=2400)
    run = client.post("/api/runs", json={"email_id": "E001"}).json()
    assert run["status"] == "waiting_for_approval"
    assert run["approval_request"]["proposal"]["card_last4"] == "4242"
    assert run["expected"]["action"] == "prepare_refund"

    done = client.post(f"/api/runs/{run['run_id']}/approval", json={"approved": True}).json()
    assert done["status"] == "done"
    assert done["refund"]["amount_aed"] == 2400
    assert done["approval"] == {"approved": True, "by": "web-tester"}

    again = client.post(f"/api/runs/{run['run_id']}/approval", json={"approved": True})
    assert again.status_code == 409  # can't approve twice


def test_pasted_email_runs(client, fake_brain):
    fake_brain.update(order_id="DL-1015", action=Action.ESCALATE)
    run = client.post("/api/runs", json={"sender": "aisha.bakr@example.com", "subject": "x",
                                         "body": "Refund DL-1015 or I call my lawyer", "attachments": []}).json()
    assert run["status"] == "escalated"
    assert run["email"]["id"] == "MANUAL" and run["expected"] is None


def test_bad_requests(client):
    assert client.post("/api/runs", json={"body": "   "}).status_code == 422
    assert client.post("/api/runs", json={"email_id": "E999"}).status_code == 404
    assert client.post("/api/runs/nope/approval", json={"approved": True}).status_code == 404
    assert client.get("/api/eval/..%2F..%2Fsecrets").status_code == 404


def test_llm_failure_is_a_502(client, fake_brain, monkeypatch):
    from returns_agent import agent_logic

    def down(e):
        raise RuntimeError("rate limit")

    monkeypatch.setattr(agent_logic, "classify_email", down)
    res = client.post("/api/runs", json={"email_id": "E001"})
    assert res.status_code == 502 and "rate limit" in res.json()["detail"]
