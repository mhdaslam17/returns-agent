"""Build the fake order database: data/orders.db

All names, emails and orders are invented. Run:
    python data/seed_db.py

The data uses a fixed "today" (REFERENCE_DATE) so trial-window results never
change when you run the tests on a different day.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "orders.db"
REFERENCE_DATE = "2026-11-06"  # the agent's "today" for all tests

SCHEMA = """
CREATE TABLE customers (
    customer_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    language      TEXT NOT NULL            -- 'en' or 'ar'
);

CREATE TABLE orders (
    order_id      TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL REFERENCES customers(customer_id),
    product       TEXT NOT NULL,
    product_type  TEXT NOT NULL,           -- mattress, topper, pillow, protector
    amount_aed    REAL NOT NULL,
    status        TEXT NOT NULL,           -- processing, shipped, delivered, cancelled
    ordered_at    TEXT NOT NULL,
    delivered_at  TEXT                     -- NULL if not delivered yet
);

CREATE TABLE payments (
    payment_id    TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL REFERENCES orders(order_id),
    amount_aed    REAL NOT NULL,
    method        TEXT NOT NULL,           -- card
    card_last4    TEXT NOT NULL,
    status        TEXT NOT NULL,           -- succeeded, refunded
    created_at    TEXT NOT NULL
);

CREATE TABLE returns (
    return_id     TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL REFERENCES orders(order_id),
    reason        TEXT NOT NULL,
    status        TEXT NOT NULL,           -- requested, pickup_scheduled, picked_up, refund_issued, rejected
    requested_at  TEXT NOT NULL,
    pickup_date   TEXT,
    refund_issued_at TEXT,
    refund_amount_aed REAL
);

-- Refunds made by the agent through the payment gateway (empty at start).
CREATE TABLE refunds (
    refund_id     TEXT PRIMARY KEY,
    payment_id    TEXT NOT NULL REFERENCES payments(payment_id),
    order_id      TEXT NOT NULL REFERENCES orders(order_id),
    amount_aed    REAL NOT NULL,
    card_last4    TEXT NOT NULL,           -- always the card of the original payment
    reason        TEXT NOT NULL,
    status        TEXT NOT NULL,           -- succeeded
    created_at    TEXT NOT NULL
);
"""

PRODUCTS = {
    "Dunelight Original": ("mattress", 2400),
    "Dunelight Hybrid": ("mattress", 3900),
    "Dunelight Kids": ("mattress", 1100),
    "Dunelight Topper": ("topper", 650),
    "Cloud Pillow": ("pillow", 180),
    "Waterproof Protector": ("protector", 250),
}

CUSTOMERS = [
    ("C001", "Sara Al Mansoori", "sara.mansoori@example.com", "en"),
    ("C002", "James Carter", "james.carter@example.com", "en"),
    ("C003", "Fatima Hassan", "fatima.hassan@example.com", "ar"),
    ("C004", "Omar Khalid", "omar.khalid@example.com", "en"),
    ("C005", "Priya Nair", "priya.nair@example.com", "en"),
    ("C006", "Ahmed Youssef", "ahmed.youssef@example.com", "ar"),
    ("C007", "Layla Ibrahim", "layla.ibrahim@example.com", "en"),
    ("C008", "Daniel Novak", "daniel.novak@example.com", "en"),
    ("C009", "Mariam Saeed", "mariam.saeed@example.com", "ar"),
    ("C010", "Khalid Rahman", "khalid.rahman@example.com", "en"),
    ("C011", "Noor Al Hashimi", "noor.hashimi@example.com", "ar"),
    ("C012", "Chen Wei", "chen.wei@example.com", "en"),
    ("C013", "Hessa Al Ketbi", "hessa.ketbi@example.com", "ar"),
    ("C014", "Ravi Menon", "ravi.menon@example.com", "en"),
    ("C015", "Aisha Bakr", "aisha.bakr@example.com", "en"),
    ("C016", "Tom Fischer", "tom.fischer@example.com", "en"),
    ("C017", "Yousef Darwish", "yousef.darwish@example.com", "ar"),
    ("C018", "Salma Qureshi", "salma.qureshi@example.com", "en"),
    ("C019", "Hamdan Al Falasi", "hamdan.falasi@example.com", "ar"),
    ("C020", "Elena Petrova", "elena.petrova@example.com", "en"),
    ("C021", "Rashid Al Nuaimi", "rashid.nuaimi@example.com", "ar"),
    ("C022", "Grace Okafor", "grace.okafor@example.com", "en"),
    ("C023", "Zainab Ali", "zainab.ali@example.com", "ar"),
    ("C024", "Bilal Saleh", "bilal.saleh@example.com", "en"),
    ("C025", "Lucy Brennan", "lucy.brennan@example.com", "en"),
    ("C026", "Hind Al Shamsi", "hind.shamsi@example.com", "ar"),
    ("C027", "Marco Rossi", "marco.rossi@example.com", "en"),
    ("C028", "Amal Haddad", "amal.haddad@example.com", "ar"),
    ("C029", "Huda Mansour", "huda.mansour@example.com", "ar"),
]

# (order_id, customer_id, product, status, ordered_at, delivered_at, note)
# The note explains why the order exists, so you know which test case uses it.
ORDERS = [
    ("DL-1001", "C001", "Dunelight Original", "delivered", "2026-08-14", "2026-08-20", "in trial, 78 nights, above AED 500"),
    ("DL-1002", "C002", "Cloud Pillow", "delivered", "2026-09-10", "2026-09-15", "pillow past 30 days, not returnable"),
    ("DL-1003", "C003", "Dunelight Hybrid", "delivered", "2026-04-03", "2026-04-10", "outside trial"),
    ("DL-1004", "C004", "Dunelight Original", "delivered", "2026-10-19", "2026-10-25", "in trial but under 30 nights"),
    ("DL-1005", "C005", "Dunelight Kids", "delivered", "2026-07-26", "2026-08-01", "return pickup scheduled"),
    ("DL-1006", "C006", "Dunelight Hybrid", "delivered", "2026-08-30", "2026-09-05", "double charge"),
    ("DL-1007", "C007", "Dunelight Topper", "delivered", "2026-07-08", "2026-07-15", "outside trial, 114 nights"),
    ("DL-1008", "C008", "Waterproof Protector", "delivered", "2026-10-15", "2026-10-20", "protector within 30 days"),
    ("DL-1009", "C009", "Dunelight Original", "delivered", "2025-11-25", "2025-12-02", "outside trial, warranty case"),
    ("DL-1010", "C010", "Dunelight Hybrid", "shipped", "2026-11-01", None, "not delivered yet"),
    ("DL-1011", "C011", "Dunelight Original", "delivered", "2026-08-22", "2026-08-28", "refund issued 2026-10-20, customer says not received"),
    ("DL-1012", "C012", "Dunelight Kids", "delivered", "2026-09-14", "2026-09-20", "in trial, above AED 500"),
    ("DL-1013", "C013", "Cloud Pillow", "delivered", "2026-10-10", "2026-10-15", "pillow within 30 days"),
    ("DL-1014", "C014", "Dunelight Original", "delivered", "2026-07-25", "2026-07-31", "in trial, 98 nights, close to the limit"),
    ("DL-1015", "C015", "Dunelight Hybrid", "delivered", "2026-05-26", "2026-06-01", "outside trial, legal threat"),
    ("DL-1016", "C016", "Dunelight Topper", "delivered", "2026-09-04", "2026-09-10", "in trial, above AED 500"),
    ("DL-1017", "C017", "Dunelight Original", "delivered", "2026-07-30", "2026-08-05", "sagging claim, in trial"),
    ("DL-1018", "C018", "Waterproof Protector", "cancelled", "2026-10-28", None, "cancelled and refunded"),
    ("DL-1019", "C019", "Dunelight Hybrid", "delivered", "2026-09-26", "2026-10-02", "in trial, 35 nights"),
    ("DL-1020", "C020", "Dunelight Original", "delivered", "2026-09-19", "2026-09-25", "target of fake manager email"),
    ("DL-1021", "C021", "Dunelight Kids", "delivered", "2026-02-08", "2026-02-14", "outside trial"),
    ("DL-1022", "C022", "Cloud Pillow", "delivered", "2026-08-04", "2026-08-10", "pillow past 30 days"),
    ("DL-1023", "C023", "Dunelight Hybrid", "delivered", "2026-09-24", "2026-09-30", "picked up, waiting for refund"),
    ("DL-1024", "C024", "Dunelight Original", "delivered", "2026-10-30", "2026-11-04", "delivered 2 days ago, delivery damage window"),
    ("DL-1025", "C025", "Dunelight Topper", "delivered", "2026-08-09", "2026-08-15", "in trial, 83 nights"),
    ("DL-1026", "C026", "Dunelight Original", "delivered", "2026-07-23", "2026-07-29", "exactly 100 nights, last day of trial"),
    ("DL-1027", "C027", "Dunelight Hybrid", "delivered", "2026-07-22", "2026-07-28", "101 nights, one night too late"),
    ("DL-1028", "C028", "Dunelight Topper", "delivered", "2026-10-28", "2026-11-02", "delivered 4 days ago, delivery damage window"),
    ("DL-1029", "C029", "Dunelight Original", "delivered", "2026-08-19", "2026-08-25", "refund issued 2026-11-02, 4 business days ago"),
]

# Extra payment rows beyond the normal one-payment-per-order.
DUPLICATE_PAYMENTS = [
    # DL-1006 was charged twice on the same day: same amount, both succeeded.
    ("PAY-1006-B", "DL-1006", 3900, "card", "4417", "succeeded", "2026-08-30"),
]

RETURNS = [
    ("RET-501", "DL-1005", "too firm", "pickup_scheduled", "2026-10-30", "2026-11-10", None, None),
    ("RET-502", "DL-1011", "too soft", "refund_issued", "2026-10-08", "2026-10-14", "2026-10-20", 2400),
    ("RET-503", "DL-1023", "back pain", "picked_up", "2026-10-27", "2026-11-03", None, None),
    ("RET-504", "DL-1019", "too firm", "requested", "2026-11-05", None, None, None),
    ("RET-505", "DL-1029", "too warm", "refund_issued", "2026-10-15", "2026-10-26", "2026-11-02", 2400),
]

CARD_LAST4 = {
    "C001": "4242", "C002": "1881", "C003": "5100", "C004": "3056", "C005": "6011",
    "C006": "4417", "C007": "2223", "C008": "3782", "C009": "5454", "C010": "4000",
    "C011": "6304", "C012": "4111", "C013": "5200", "C014": "3714", "C015": "4012",
    "C016": "5105", "C017": "4917", "C018": "6759", "C019": "4026", "C020": "5555",
    "C021": "4508", "C022": "3530", "C023": "4844", "C024": "2720", "C025": "4571",
    "C026": "4532", "C027": "5425", "C028": "4716", "C029": "2221",
}


def build(db_path: Path = DB_PATH) -> Path:
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", CUSTOMERS)

    for order_id, cust, product, status, ordered, delivered, _note in ORDERS:
        product_type, price = PRODUCTS[product]
        con.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, cust, product, product_type, price, status, ordered, delivered),
        )
        pay_status = "refunded" if status == "cancelled" else "succeeded"
        con.execute(
            "INSERT INTO payments VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"PAY-{order_id[3:]}-A", order_id, price, "card", CARD_LAST4[cust], pay_status, ordered),
        )

    for row in DUPLICATE_PAYMENTS:
        con.execute("INSERT INTO payments VALUES (?, ?, ?, ?, ?, ?, ?)", row)

    con.executemany("INSERT INTO returns VALUES (?, ?, ?, ?, ?, ?, ?, ?)", RETURNS)
    # Orders refunded through a return: mark their payment as refunded.
    con.execute(
        "UPDATE payments SET status = 'refunded' WHERE order_id IN "
        "(SELECT order_id FROM returns WHERE status = 'refund_issued')"
    )

    con.commit()
    con.close()
    return db_path


if __name__ == "__main__":
    path = build()
    print(f"Built {path} with {len(ORDERS)} orders (reference date {REFERENCE_DATE}).")
