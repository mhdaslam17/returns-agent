import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EMAILS_PATH = ROOT / "evals" / "emails.json"


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_db", ROOT / "data" / "seed_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def seed():
    return _load_seed_module()


@pytest.fixture(scope="session")
def db(seed, tmp_path_factory):
    """A fresh copy of the fake database for each test run."""
    path = seed.build(tmp_path_factory.mktemp("db") / "orders.db")
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    yield con
    con.close()


@pytest.fixture
def fresh_con(seed, tmp_path):
    """A new database for one test. Use it when the test writes (refunds)."""
    from returns_agent.db import connect

    con = connect(seed.build(tmp_path / "orders.db"))
    yield con
    con.close()


@pytest.fixture
def fake_brain(monkeypatch):
    """Replace the LLM parts with simple rules, so graph and API tests need no LLM.
    The test fills the returned dict: order_id, action, payment_id, amount, category, suspicious."""
    from returns_agent import agent_logic, graph
    from returns_agent.labels import Action, Category, Language
    from returns_agent.schemas import Classification, Decision

    plan = {}

    def classify(e):
        return Classification(category=plan.get("category", Category.RETURN_IN_TRIAL), language=Language.EN,
                              order_id=plan.get("order_id"), suspicious=plan.get("suspicious", False),
                              suspicious_reason=None, summary="wants a refund")

    def decide(e, c, order, policy):
        return Decision(action=plan["action"], reason="test", policy_clauses=["2.1"],
                        refund_payment_id=plan.get("payment_id"), refund_amount_aed=plan.get("amount"),
                        urgent=False)

    def route(d):
        return {Action.PREPARE_REFUND: "prepare_refund", Action.ESCALATE: "escalate"}.get(d.action, "draft_reply")

    monkeypatch.setattr(agent_logic, "classify_email", classify)
    monkeypatch.setattr(agent_logic, "decide_action", decide)
    monkeypatch.setattr(agent_logic, "apply_guardrails", lambda d, c, o, e: d)
    monkeypatch.setattr(agent_logic, "route_after_decide", route)
    monkeypatch.setattr(agent_logic, "write_reply", lambda *args: "Dear customer, ...")
    monkeypatch.setattr(graph, "check_policy",
                        lambda query: [{"clause": "2.1", "section": "Trial", "text": "...", "score": 1}])
    return plan


@pytest.fixture(scope="session")
def emails():
    return json.loads(EMAILS_PATH.read_text(encoding="utf-8"))
