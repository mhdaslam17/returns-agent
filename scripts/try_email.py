"""Run the agent on ONE email and show every step. For manual testing.

    python scripts/try_email.py E001                      # an email from evals/emails.json
    python scripts/try_email.py --from sara.mansoori@example.com --text "I want to return DL-1001"
    python scripts/try_email.py --file my_email.txt --from tom.fischer@example.com

If a refund needs approval, YOU act as the team lead and type y or n.
Each run uses a fresh copy of the fake database, so test refunds never pile up.
"""

import argparse
import importlib.util
import json
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langgraph.types import Command  # noqa: E402

from returns_agent import llm  # noqa: E402
from returns_agent.db import connect  # noqa: E402
from returns_agent.graph import build_graph  # noqa: E402


def load_seed():
    spec = importlib.util.spec_from_file_location("seed_db", ROOT / "data" / "seed_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 60 - len(title)))


def show(state: dict) -> None:
    c = state.get("classification") or {}
    section("1. CLASSIFY (LLM)")
    print(f"category:   {c.get('category')}")
    print(f"language:   {c.get('language')}")
    print(f"order_id:   {c.get('order_id')}")
    print(f"suspicious: {c.get('suspicious')}  {c.get('suspicious_reason') or ''}")
    print(f"summary:    {c.get('summary')}")

    o = state.get("order") or {}
    section("2. FACTS (lookup_order)")
    if not o.get("found"):
        print(f"order not found: {o.get('reason')}")
    else:
        print(f"{o['order_id']} {o['product']} AED {o['amount_aed']:.0f}, status {o['status']}")
        print(f"customer: {o['customer_name']}, sender owns order: {o['sender_matches_owner']}")
        print(f"nights since delivery: {o['nights_since_delivery']}")
        for p in o["payments"]:
            print(f"payment {p['payment_id']}: AED {p['amount_aed']:.0f} card *{p['card_last4']} "
                  f"{p['status']} (refundable {p['refundable_aed']:.0f})")
        for r in o["returns"]:
            print(f"return {r['return_id']}: {r['status']}")

    section("3. POLICY (check_policy, top clauses)")
    for p in state.get("policy") or []:
        print(f"[{p['clause']}] score {p['score']}: {p['text'][:90]}...")

    d = state.get("decision") or {}
    section("4. DECIDE (LLM + guardrails)")
    print(f"action: {d.get('action')}")
    print(f"reason: {d.get('reason')}")
    if d.get("refund_payment_id"):
        print(f"refund: {d['refund_payment_id']} AED {d['refund_amount_aed']}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("email_id", nargs="?", help="id from evals/emails.json, e.g. E001")
    parser.add_argument("--text", help="email body")
    parser.add_argument("--file", help="file with the email body")
    parser.add_argument("--from", dest="sender", default="sara.mansoori@example.com")
    parser.add_argument("--subject", default="Customer email")
    parser.add_argument("--attach", nargs="*", default=[], help="attachment names, e.g. photo1.jpg")
    args = parser.parse_args()

    if args.email_id:
        emails = json.loads((ROOT / "evals" / "emails.json").read_text(encoding="utf-8"))
        email = next((e for e in emails if e["id"] == args.email_id), None)
        if email is None:
            sys.exit(f"No email {args.email_id} in evals/emails.json")
    else:
        body = args.text or (Path(args.file).read_text(encoding="utf-8") if args.file else None)
        if not body:
            sys.exit("Give an email id, or --text, or --file.")
        email = {"id": "MANUAL", "from": args.sender, "subject": args.subject,
                 "body": body, "attachments": args.attach}

    section("EMAIL")
    print(f"From: {email['from']}\nSubject: {email['subject']}\nAttachments: {email['attachments'] or 'none'}")
    print(email["body"])
    if "expected" in email:
        exp = email["expected"]
        print(f"\n(label says: {exp['category']} / {exp['action']}, needs_human={exp['needs_human']})")

    with tempfile.TemporaryDirectory() as tmp:
        con = connect(load_seed().build(Path(tmp) / "orders.db"))
        graph = build_graph(con)
        config = {"configurable": {"thread_id": uuid.uuid4().hex}}
        print("\nRunning agent...")
        state = graph.invoke({"email": email, "tools_called": []}, config)
        show(state)

        if "__interrupt__" in state:
            shown = state["__interrupt__"][0].value
            p = shown["proposal"]
            section("5. HUMAN APPROVAL (graph is paused)")
            print(f"Refund AED {p['amount_aed']:.0f} for {p['order_id']} to card *{p['card_last4']}")
            print(f"Customer: {shown['customer_name']}. Reason: {shown['decision_reason']}")
            answer = input("You are the team lead. Approve? (y/n): ").strip().lower()
            state = graph.invoke(Command(resume={"approved": answer == "y", "by": "manual-tester"}), config)
            print(f"approved: {state['approval']['approved']}")

        section("RESULT")
        if state.get("refund"):
            r = state["refund"]
            print(f"REFUND DONE: {r['refund_id']} AED {r['amount_aed']:.0f} to card *{r['card_last4']}")
        if state.get("escalated"):
            print("ESCALATED to a person.")
        if state.get("error"):
            print(f"note: {state['error']}")
        print(f"tools called: {state.get('tools_called')}")
        print(f"LLM calls: {llm.USAGE['calls']}, tokens: {llm.USAGE['tokens']}")
        section("REPLY TO CUSTOMER")
        print(state.get("reply") or "(no reply sent)")
        con.close()


if __name__ == "__main__":
    main()
