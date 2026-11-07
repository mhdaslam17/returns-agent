import pytest

from returns_agent.payments import FakeGateway, RefundError


def test_refund_goes_to_original_card(fresh_con):
    result = FakeGateway(fresh_con).refund("PAY-1001-A", 2400, "trial return")
    assert result.card_last4 == "4242"  # Sara's card on the order
    assert result.refund_id == "re_fake_0001"
    status = fresh_con.execute("SELECT status FROM payments WHERE payment_id = 'PAY-1001-A'").fetchone()[0]
    assert status == "refunded"


def test_cannot_refund_more_than_paid(fresh_con):
    with pytest.raises(RefundError):
        FakeGateway(fresh_con).refund("PAY-1001-A", 2401, "too much")


def test_cannot_refund_twice(fresh_con):
    gateway = FakeGateway(fresh_con)
    gateway.refund("PAY-1001-A", 2400, "first")
    with pytest.raises(RefundError):
        gateway.refund("PAY-1001-A", 1, "second")


def test_partial_refunds_add_up(fresh_con):
    gateway = FakeGateway(fresh_con)
    gateway.refund("PAY-1001-A", 400, "part 1")
    gateway.refund("PAY-1001-A", 2000, "part 2")
    with pytest.raises(RefundError):
        gateway.refund("PAY-1001-A", 1, "part 3")


def test_already_refunded_payment_is_refused(fresh_con):
    with pytest.raises(RefundError):
        FakeGateway(fresh_con).refund("PAY-1011-A", 2400, "refund again")  # refunded on 2026-10-20


def test_duplicate_charge_payment_can_be_refunded(fresh_con):
    result = FakeGateway(fresh_con).refund("PAY-1006-B", 3900, "double charge")
    assert result.card_last4 == "4417"


def test_unknown_payment_is_refused(fresh_con):
    with pytest.raises(RefundError):
        FakeGateway(fresh_con).refund("PAY-9999-A", 10, "nope")
