"""Checks that the labelled test emails are valid and match the fake database.

These tests do not call the LLM. They catch labelling mistakes early.
"""

import re
from collections import Counter

import pytest

from returns_agent.labels import APPROVAL_THRESHOLD_AED, Action, Category, Language, Tool

ORDER_RE = re.compile(r"DL-\d{4}")
TARGET_SIZE = 60


def test_ids_are_unique(emails):
    ids = [e["id"] for e in emails]
    assert len(ids) == len(set(ids)), [i for i, n in Counter(ids).items() if n > 1]


def test_labels_are_valid(emails):
    for e in emails:
        exp = e["expected"]
        assert e["language"] in set(Language), e["id"]
        assert exp["category"] in set(Category), e["id"]
        assert exp["action"] in set(Action), e["id"]
        for tool in exp["required_tools"] + exp["forbidden_tools"]:
            assert tool in set(Tool), (e["id"], tool)
        assert not set(exp["required_tools"]) & set(exp["forbidden_tools"]), e["id"]
        assert e["why"].strip(), f"{e['id']}: explain the label in 'why'"


def test_action_and_tools_agree(emails):
    for e in emails:
        exp = e["expected"]
        if exp["action"] == Action.PREPARE_REFUND:
            assert Tool.PREPARE_REFUND in exp["required_tools"], e["id"]
        else:
            assert Tool.PREPARE_REFUND in exp["forbidden_tools"], e["id"]


def test_escalations_and_suspicious_need_a_human(emails):
    for e in emails:
        exp = e["expected"]
        if exp["action"] == Action.ESCALATE or exp["suspicious"]:
            assert exp["needs_human"], e["id"]
        if exp["suspicious"]:
            assert exp["action"] == Action.ESCALATE, e["id"]


def test_orders_and_senders_match_database(emails, db):
    customer_emails = {r["email"] for r in db.execute("SELECT email FROM customers")}
    for e in emails:
        if "unknown_sender" not in e["tags"]:
            assert e["from"] in customer_emails, f"{e['id']}: sender not in DB (or add tag unknown_sender)"
        for order_id in ORDER_RE.findall(e["body"]):
            found = db.execute("SELECT 1 FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if "unknown_order" in e["tags"]:
                assert found is None, f"{e['id']}: tagged unknown_order but {order_id} exists"
            else:
                assert found, f"{e['id']}: {order_id} not in DB (or add tag unknown_order)"


def test_refund_approval_matches_amount(emails, db):
    """A prepared refund needs a human only when it is above the threshold."""
    for e in emails:
        exp = e["expected"]
        if exp["action"] != Action.PREPARE_REFUND:
            continue
        order_id = ORDER_RE.search(e["body"]).group()
        amount = db.execute("SELECT amount_aed FROM orders WHERE order_id = ?", (order_id,)).fetchone()[0]
        assert exp["needs_human"] == (amount > APPROVAL_THRESHOLD_AED), e["id"]


@pytest.mark.xfail(reason="Dataset not reviewed yet. Remove this mark when it is.", strict=False)
def test_dataset_coverage(emails):
    drafts = [e["id"] for e in emails if "draft" in e["tags"]]
    assert not drafts, f"{len(drafts)} emails still tagged 'draft' (not reviewed): {drafts}"
    assert len(emails) >= TARGET_SIZE
    categories = Counter(e["expected"]["category"] for e in emails)
    for cat in Category:
        assert categories[cat] >= 5, f"only {categories[cat]} emails for {cat}"
    languages = Counter(e["language"] for e in emails)
    assert languages["ar"] >= 10 and languages["mixed"] >= 5
