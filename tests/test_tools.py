from datetime import date

import pytest

from returns_agent.payments import RefundError
from returns_agent.tools import business_days_between, lookup_order, prepare_refund


def test_trial_edges(fresh_con):
    assert lookup_order(fresh_con, "DL-1026")["nights_since_delivery"] == 100
    assert lookup_order(fresh_con, "DL-1027")["nights_since_delivery"] == 101
    assert lookup_order(fresh_con, "DL-1004")["nights_since_delivery"] == 12


def test_sender_must_match_owner(fresh_con):
    assert lookup_order(fresh_con, "DL-1001", "sara.mansoori@example.com")["sender_matches_owner"]
    assert not lookup_order(fresh_con, "DL-1020", "james.carter@example.com")["sender_matches_owner"]


def test_unknown_order(fresh_con):
    result = lookup_order(fresh_con, "DL-1099", "tom.fischer@example.com")
    assert result == {"found": False, "reason": "no order with number DL-1099"}


def test_lookup_by_sender_email(fresh_con):
    assert lookup_order(fresh_con, None, "zainab.ali@example.com")["order_id"] == "DL-1023"
    assert not lookup_order(fresh_con, None, "visitor.ahmad@example.com")["found"]


def test_not_delivered_has_no_nights(fresh_con):
    assert lookup_order(fresh_con, "DL-1010")["nights_since_delivery"] is None


def test_double_charge_facts(fresh_con):
    order = lookup_order(fresh_con, "DL-1006")
    assert order["succeeded_payment_count"] == 2


def test_refund_age_in_business_days(fresh_con):
    assert lookup_order(fresh_con, "DL-1011")["returns"][0]["business_days_since_refund"] == 13
    assert lookup_order(fresh_con, "DL-1029")["returns"][0]["business_days_since_refund"] == 4


def test_business_days_skip_weekend():
    # Fri 2026-11-06 -> Mon 2026-11-09 is 1 business day (Sat, Sun skipped)
    assert business_days_between(date(2026, 11, 6), date(2026, 11, 9)) == 1


def test_prepare_refund_needs_approval_above_500(fresh_con):
    assert prepare_refund(fresh_con, "DL-1001", "PAY-1001-A", 2400, "trial").requires_approval
    assert not prepare_refund(fresh_con, "DL-1013", "PAY-1013-A", 180, "pillow").requires_approval


def test_prepare_refund_rejects_wrong_order(fresh_con):
    with pytest.raises(RefundError):
        prepare_refund(fresh_con, "DL-1020", "PAY-1001-A", 2400, "payment from another order")


def test_prepare_refund_rejects_refunded_payment(fresh_con):
    with pytest.raises(RefundError):
        prepare_refund(fresh_con, "DL-1011", "PAY-1011-A", 2400, "again")
