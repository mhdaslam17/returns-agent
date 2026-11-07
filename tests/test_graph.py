"""Tests the graph wiring with fake 'brain' functions. No LLM, no embedding model.

These check the plumbing: tools are recorded, small refunds run, big refunds pause
for approval, approval resumes, and errors are reported, not raised.
"""

from returns_agent import agent_logic, graph
from returns_agent.labels import Action, Category


def email(id_, sender, order_id):
    return {"id": id_, "from": sender, "subject": "test", "body": f"order {order_id}", "attachments": []}

# The fake_brain fixture (LLM parts replaced by simple rules) is in conftest.py.


def test_small_refund_runs_without_approval(fresh_con, fake_brain):
    fake_brain.update(order_id="DL-1013", action=Action.PREPARE_REFUND, payment_id="PAY-1013-A", amount=180)
    result = graph.run_email(email("T1", "hessa.ketbi@example.com", "DL-1013"), fresh_con)
    assert result.status == "done"
    assert not result.needs_human
    assert result.refund["card_last4"] == "5200"
    assert result.tools_called == ["lookup_order", "check_policy", "prepare_refund", "draft_reply"]


def test_big_refund_pauses_then_resumes(fresh_con, fake_brain):
    fake_brain.update(order_id="DL-1001", action=Action.PREPARE_REFUND, payment_id="PAY-1001-A", amount=2400)
    e = email("T2", "sara.mansoori@example.com", "DL-1001")
    g = graph.build_graph(fresh_con)

    paused = graph.run_email(e, fresh_con, graph=g, thread_id="t2")
    assert paused.status == "waiting_for_approval"
    assert paused.needs_human and paused.refund is None
    assert fresh_con.execute("SELECT COUNT(*) FROM refunds").fetchone()[0] == 0  # no money moved yet

    shown = g.get_state({"configurable": {"thread_id": "t2"}}).tasks[0].interrupts[0].value
    assert shown["type"] == "refund_approval"
    assert shown["customer_name"] == "Sara Al Mansoori"
    assert shown["proposal"]["card_last4"] == "4242" and shown["proposal"]["amount_aed"] == 2400

    done = graph.resume_after_approval(e, g, "t2", approved=True, by="lead@example.com")
    assert done.status == "done"
    assert done.refund["amount_aed"] == 2400
    assert done.reply


def test_rejected_refund_is_escalated(fresh_con, fake_brain):
    fake_brain.update(order_id="DL-1001", action=Action.PREPARE_REFUND, payment_id="PAY-1001-A", amount=2400)
    e = email("T3", "sara.mansoori@example.com", "DL-1001")
    g = graph.build_graph(fresh_con)
    graph.run_email(e, fresh_con, graph=g, thread_id="t3")
    rejected = graph.resume_after_approval(e, g, "t3", approved=False, by="lead@example.com")
    assert rejected.status == "escalated"
    assert rejected.refund is None


def test_unclear_approval_counts_as_rejection(fresh_con, fake_brain):
    fake_brain.update(order_id="DL-1001", action=Action.PREPARE_REFUND, payment_id="PAY-1001-A", amount=2400)
    e = email("T3b", "sara.mansoori@example.com", "DL-1001")
    g = graph.build_graph(fresh_con)
    graph.run_email(e, fresh_con, graph=g, thread_id="t3b")
    config = {"configurable": {"thread_id": "t3b"}}
    state = g.invoke(graph.Command(resume={"approved": "yes"}), config)  # not exactly True
    assert state["approval"]["approved"] is False
    assert state.get("refund") is None


def test_impossible_refund_is_escalated_not_paid(fresh_con, fake_brain):
    # DL-1011 was already refunded: the code must refuse even if the LLM says refund.
    fake_brain.update(order_id="DL-1011", action=Action.PREPARE_REFUND, payment_id="PAY-1011-A", amount=2400)
    result = graph.run_email(email("T4", "noor.hashimi@example.com", "DL-1011"), fresh_con)
    assert result.status == "escalated"
    assert result.refund is None
    assert "refund not possible" in result.error


def test_escalate_path(fresh_con, fake_brain):
    fake_brain.update(order_id="DL-1015", action=Action.ESCALATE, category=Category.LEGAL_THREAT)
    result = graph.run_email(email("T5", "aisha.bakr@example.com", "DL-1015"), fresh_con)
    assert result.status == "escalated" and result.needs_human
    assert "prepare_refund" not in result.tools_called
    assert result.reply  # a real customer gets a short acknowledgment


def test_suspicious_escalation_gets_no_reply(fresh_con, fake_brain):
    fake_brain.update(order_id="DL-1020", action=Action.ESCALATE, category=Category.OTHER, suspicious=True)
    result = graph.run_email(email("T7", "store.manager.dunelight@example.net", "DL-1020"), fresh_con)
    assert result.status == "escalated"
    assert result.reply is None
    assert "draft_reply" not in result.tools_called


def test_errors_are_reported_not_raised(fresh_con, fake_brain, monkeypatch):
    # If a step fails (bad LLM output, unfinished code), the eval must report it and go on.
    fake_brain.update(order_id="DL-1001")

    def broken(*args):
        raise ValueError("LLM gave no parsed output")

    monkeypatch.setattr(agent_logic, "decide_action", broken)
    result = graph.run_email(email("T6", "sara.mansoori@example.com", "DL-1001"), fresh_con)
    assert result.status == "error"
    assert "LLM gave no parsed output" in result.error
    assert result.category == "return_in_trial"  # work done before the error is kept
    assert result.tools_called == ["lookup_order", "check_policy"]
