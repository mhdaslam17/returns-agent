"""Tools the agent can use.

Tools return FACTS (dates, amounts, nights, who owns the order). They do not
decide what to do. Decisions happen in the graph, so you can test and explain
them in one place.

lookup_order   - read the order database
check_policy   - search the policy (see rag.py)
prepare_refund - check a refund is possible and build a proposal. Moves no money.
draft_reply    - written by the LLM in the graph (no function here)
"""

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from returns_agent.config import TODAY
from returns_agent.labels import APPROVAL_THRESHOLD_AED
from returns_agent.payments import RefundError, refundable_amount


def business_days_between(start: date, end: date) -> int:
    """Business days after `start` up to and including `end`. UAE weekend is Sat-Sun."""
    days, current = 0, start
    while current < end:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 ... Fri=4
            days += 1
    return days


def _order_facts(con: sqlite3.Connection, order: sqlite3.Row, sender_email: str | None, today: date) -> dict:
    customer = con.execute("SELECT * FROM customers WHERE customer_id = ?", (order["customer_id"],)).fetchone()
    payments = [dict(p) for p in con.execute(
        "SELECT payment_id, amount_aed, card_last4, status, created_at FROM payments WHERE order_id = ? ORDER BY payment_id",
        (order["order_id"],),
    )]
    for p in payments:
        p["refundable_aed"] = refundable_amount(con, p["payment_id"])

    returns = []
    for r in con.execute("SELECT * FROM returns WHERE order_id = ?", (order["order_id"],)):
        r = dict(r)
        if r["refund_issued_at"]:
            r["business_days_since_refund"] = business_days_between(date.fromisoformat(r["refund_issued_at"]), today)
        returns.append(r)

    delivered = order["delivered_at"]
    return {
        "found": True,
        "order_id": order["order_id"],
        "customer_name": customer["name"],
        "customer_language": customer["language"],
        "sender_matches_owner": sender_email is not None and sender_email.lower() == customer["email"].lower(),
        "product": order["product"],
        "product_type": order["product_type"],
        "amount_aed": order["amount_aed"],
        "status": order["status"],
        "ordered_at": order["ordered_at"],
        "delivered_at": delivered,
        "nights_since_delivery": (today - date.fromisoformat(delivered)).days if delivered else None,
        "payments": payments,
        "succeeded_payment_count": sum(p["status"] == "succeeded" for p in payments),
        "returns": returns,
        "today": today.isoformat(),
    }


def lookup_order(con: sqlite3.Connection, order_id: str | None = None,
                 sender_email: str | None = None, today: date = TODAY) -> dict:
    """Find an order by order number, or by the sender's email if no number is given.

    Never returns the customer's email or full card details: only card_last4.
    """
    if order_id:
        order = con.execute("SELECT * FROM orders WHERE order_id = ?", (order_id.strip().upper(),)).fetchone()
        if order is None:
            return {"found": False, "reason": f"no order with number {order_id}"}
        return _order_facts(con, order, sender_email, today)

    if sender_email:
        orders = con.execute(
            "SELECT o.* FROM orders o JOIN customers c ON c.customer_id = o.customer_id WHERE lower(c.email) = ?",
            (sender_email.lower(),),
        ).fetchall()
        if len(orders) == 1:
            return _order_facts(con, orders[0], sender_email, today)
        if len(orders) > 1:
            return {"found": False, "reason": "sender has several orders; ask which one",
                    "order_ids": [o["order_id"] for o in orders]}
        return {"found": False, "reason": "no order number given and sender is not a known customer"}

    return {"found": False, "reason": "no order number and no sender email"}


@dataclass(frozen=True)
class RefundProposal:
    order_id: str
    payment_id: str
    amount_aed: float
    card_last4: str
    reason: str
    requires_approval: bool  # set by code (policy 3.4), never by the LLM

    def to_dict(self) -> dict:
        return asdict(self)


def prepare_refund(con: sqlite3.Connection, order_id: str, payment_id: str,
                   amount_aed: float, reason: str) -> RefundProposal:
    """Check a refund is allowed and build a proposal. Raises RefundError if not.

    The refund goes to the card of `payment_id`. There is no way to choose another card.
    """
    payment = con.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,)).fetchone()
    if payment is None or payment["order_id"] != order_id:
        raise RefundError(f"payment {payment_id} does not belong to order {order_id}")
    remaining = refundable_amount(con, payment_id)
    if remaining <= 0:
        raise RefundError(f"payment {payment_id} cannot be refunded (status '{payment['status']}')")
    if not 0 < amount_aed <= remaining:
        raise RefundError(f"amount AED {amount_aed} must be above 0 and at most AED {remaining}")
    return RefundProposal(
        order_id=order_id,
        payment_id=payment_id,
        amount_aed=amount_aed,
        card_last4=payment["card_last4"],
        reason=reason,
        requires_approval=amount_aed > APPROVAL_THRESHOLD_AED,
    )
