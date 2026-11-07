"""Checks the fake database has the facts the test emails depend on."""


def test_order_count(db, seed):
    assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == len(seed.ORDERS)


def test_double_charge_exists(db):
    rows = db.execute(
        "SELECT amount_aed FROM payments WHERE order_id = 'DL-1006' AND status = 'succeeded'"
    ).fetchall()
    assert [r[0] for r in rows] == [3900, 3900]


def test_every_order_has_a_payment(db):
    missing = db.execute(
        "SELECT order_id FROM orders WHERE order_id NOT IN (SELECT order_id FROM payments)"
    ).fetchall()
    assert missing == []


def test_refund_issued_for_dl_1011(db):
    row = db.execute("SELECT status, refund_issued_at FROM returns WHERE order_id = 'DL-1011'").fetchone()
    assert tuple(row) == ("refund_issued", "2026-10-20")
