"""Payment gateway. The agent never talks to a payment provider directly.

FakeGateway records refunds in SQLite. It is used for tests, the eval and the demo.
A real provider (for example Stripe) could be added later as another class with
the same `refund` method, without changing the agent.

Safety rules live here in code, not in the LLM prompt:
- A refund always goes back to the card of the original payment. There is no
  parameter for a different card or account, so the LLM cannot ask for one.
- Only succeeded payments can be refunded.
- The total refunded can never be more than the payment amount.
"""

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Protocol


class RefundError(Exception):
    """The refund is not allowed. The message says why."""


@dataclass(frozen=True)
class RefundResult:
    refund_id: str
    payment_id: str
    order_id: str
    amount_aed: float
    card_last4: str
    status: str

    def to_dict(self) -> dict:
        return asdict(self)


class PaymentGateway(Protocol):
    def refund(self, payment_id: str, amount_aed: float, reason: str) -> RefundResult: ...


def refundable_amount(con: sqlite3.Connection, payment_id: str) -> float:
    """How much of this payment can still be refunded. 0 if not refundable."""
    payment = con.execute("SELECT amount_aed, status FROM payments WHERE payment_id = ?", (payment_id,)).fetchone()
    if payment is None or payment["status"] != "succeeded":
        return 0.0
    already = con.execute(
        "SELECT COALESCE(SUM(amount_aed), 0) FROM refunds WHERE payment_id = ?", (payment_id,)
    ).fetchone()[0]
    return payment["amount_aed"] - already


class FakeGateway:
    def __init__(self, con: sqlite3.Connection):
        self.con = con

    def refund(self, payment_id: str, amount_aed: float, reason: str) -> RefundResult:
        payment = self.con.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,)).fetchone()
        if payment is None:
            raise RefundError(f"payment {payment_id} not found")
        if payment["status"] != "succeeded":
            raise RefundError(f"payment {payment_id} has status '{payment['status']}', only 'succeeded' can be refunded")
        if amount_aed <= 0:
            raise RefundError("refund amount must be above 0")
        remaining = refundable_amount(self.con, payment_id)
        if amount_aed > remaining:
            raise RefundError(f"refund AED {amount_aed} is more than the refundable AED {remaining}")

        count = self.con.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]
        result = RefundResult(
            refund_id=f"re_fake_{count + 1:04d}",
            payment_id=payment_id,
            order_id=payment["order_id"],
            amount_aed=amount_aed,
            card_last4=payment["card_last4"],
            status="succeeded",
        )
        self.con.execute(
            "INSERT INTO refunds VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (result.refund_id, payment_id, result.order_id, amount_aed, result.card_last4,
             reason, result.status, datetime.now(timezone.utc).isoformat()),
        )
        if amount_aed == remaining:
            self.con.execute("UPDATE payments SET status = 'refunded' WHERE payment_id = ?", (payment_id,))
        self.con.commit()
        return result
