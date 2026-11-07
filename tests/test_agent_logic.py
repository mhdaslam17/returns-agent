"""Tests for the code (non-LLM) parts of agent_logic.py."""

import pytest

from returns_agent.agent_logic import apply_guardrails, mentions_legal_action, refine_category, route_after_decide
from returns_agent.labels import Action, Category, Language
from returns_agent.schemas import Classification, Decision
from returns_agent.tools import lookup_order


def classified(category, order_id):
    return Classification(category=category, language=Language.EN, order_id=order_id,
                          suspicious=False, suspicious_reason=None, summary="wants to return")


@pytest.mark.parametrize("order_id, expected", [
    ("DL-1026", Category.RETURN_IN_TRIAL),  # mattress, night 100: still in
    ("DL-1027", Category.OUTSIDE_TRIAL),    # mattress, night 101: out
    ("DL-1025", Category.RETURN_IN_TRIAL),  # topper, 83 nights
    ("DL-1007", Category.OUTSIDE_TRIAL),    # topper, 114 nights
    ("DL-1013", Category.RETURN_IN_TRIAL),  # pillow, 22 days
    ("DL-1002", Category.OUTSIDE_TRIAL),    # pillow, 52 days
])
def test_trial_window_from_dates(db, order_id, expected):
    for llm_guess in (Category.RETURN_IN_TRIAL, Category.OUTSIDE_TRIAL):  # LLM guess is ignored
        result = refine_category(classified(llm_guess, order_id), lookup_order(db, order_id))
        assert result.category == expected


def test_other_categories_are_not_changed(db):
    c = classified(Category.LEGAL_THREAT, "DL-1027")
    assert refine_category(c, lookup_order(db, "DL-1027")).category == Category.LEGAL_THREAT


def test_unknown_or_undelivered_order_keeps_llm_category(db):
    c = classified(Category.RETURN_IN_TRIAL, "DL-1099")
    assert refine_category(c, lookup_order(db, "DL-1099")).category == Category.RETURN_IN_TRIAL
    c = classified(Category.RETURN_IN_TRIAL, "DL-1010")
    assert refine_category(c, lookup_order(db, "DL-1010")).category == Category.RETURN_IN_TRIAL


# --- guardrails and routing -----------------------------------------------------


PLAIN = {"subject": "return", "body": "please help", "attachments": []}


def refund_decision():
    return Decision(action=Action.PREPARE_REFUND, reason="llm says refund", policy_clauses=["2.1"],
                    refund_payment_id="PAY-1001-A", refund_amount_aed=2400, urgent=False)


def test_suspicious_always_escalates(db):
    c = classified(Category.RETURN_IN_TRIAL, "DL-1020").model_copy(update={"suspicious": True})
    d = apply_guardrails(refund_decision(), c, lookup_order(db, "DL-1020", "elena.petrova@example.com"), PLAIN)
    assert d.action == Action.ESCALATE
    assert d.refund_payment_id is None and d.reason.startswith("[guardrail]")


def test_refund_needs_found_order(db):
    d = apply_guardrails(refund_decision(), classified(Category.RETURN_IN_TRIAL, "DL-1099"),
                         lookup_order(db, "DL-1099", "tom.fischer@example.com"), PLAIN)
    assert d.action == Action.ASK_FOR_DETAILS


def test_refund_needs_owner(db):
    d = apply_guardrails(refund_decision(), classified(Category.RETURN_IN_TRIAL, "DL-1001"),
                         lookup_order(db, "DL-1001", "sara.m.home@example.com"), PLAIN)
    assert d.action == Action.ASK_FOR_DETAILS


def test_no_refund_outside_trial(db):
    d = apply_guardrails(refund_decision(), classified(Category.OUTSIDE_TRIAL, "DL-1027"),
                         lookup_order(db, "DL-1027", "marco.rossi@example.com"), PLAIN)
    assert d.action == Action.AUTO_REPLY


def test_good_refund_is_kept(db):
    d = apply_guardrails(refund_decision(), classified(Category.RETURN_IN_TRIAL, "DL-1001"),
                         lookup_order(db, "DL-1001", "sara.mansoori@example.com"), PLAIN)
    assert d == refund_decision()


def test_routes():
    assert route_after_decide(refund_decision()) == "prepare_refund"
    for action, node in [(Action.AUTO_REPLY, "draft_reply"), (Action.ASK_FOR_DETAILS, "draft_reply"),
                         (Action.ESCALATE, "escalate")]:
        assert route_after_decide(refund_decision().model_copy(update={"action": action})) == node


# --- v2 guardrails (added after the v1 eval) -------------------------------------

def decision(action):
    return refund_decision().model_copy(update={"action": action, "refund_payment_id": None,
                                                "refund_amount_aed": None})


def test_legal_words_escalate(db):
    email = {"subject": "topper", "body": "My brother is a lawyer and says you must take it back.", "attachments": []}
    d = apply_guardrails(decision(Action.AUTO_REPLY), classified(Category.OUTSIDE_TRIAL, "DL-1007"),
                         lookup_order(db, "DL-1007", "layla.ibrahim@example.com"), email)
    assert d.action == Action.ESCALATE


def test_legal_words_match_only_legal_labels(emails):
    """No false alarms on the test set: every email with legal words is labelled legal_threat."""
    hits = {e["id"] for e in emails if mentions_legal_action(e)}
    legal = {e["id"] for e in emails if e["expected"]["category"] == "legal_threat"}
    assert hits == legal, f"extra: {hits - legal}, missed: {legal - hits}"


def test_no_refund_before_delivery(db):
    d = apply_guardrails(refund_decision(), classified(Category.RETURN_IN_TRIAL, "DL-1010"),
                         lookup_order(db, "DL-1010", "khalid.rahman@example.com"), PLAIN)
    assert d.action == Action.ESCALATE


def test_damage_without_photos_asks(db):
    order = lookup_order(db, "DL-1028", "amal.haddad@example.com")
    for action in (Action.PREPARE_REFUND, Action.AUTO_REPLY):
        d = apply_guardrails(decision(action) if action != Action.PREPARE_REFUND else refund_decision(),
                             classified(Category.DAMAGED_DEFECTIVE, "DL-1028"), order, PLAIN)
        assert d.action == Action.ASK_FOR_DETAILS


def test_damage_with_photos_not_refund_escalates(db):
    with_photos = {**PLAIN, "attachments": ["whole.jpg", "closeup.jpg", "label.jpg"]}
    d = apply_guardrails(decision(Action.AUTO_REPLY), classified(Category.DAMAGED_DEFECTIVE, "DL-1009"),
                         lookup_order(db, "DL-1009", "mariam.saeed@example.com"), with_photos)
    assert d.action == Action.ESCALATE


def test_delivery_damage_refund_with_photos_is_kept(db):
    with_photos = {**PLAIN, "attachments": ["whole.jpg", "closeup.jpg", "label.jpg"]}
    refund = refund_decision().model_copy(update={"refund_payment_id": "PAY-1024-A"})
    d = apply_guardrails(refund, classified(Category.DAMAGED_DEFECTIVE, "DL-1024"),
                         lookup_order(db, "DL-1024", "bilal.saleh@example.com"), with_photos)
    assert d.action == Action.PREPARE_REFUND
