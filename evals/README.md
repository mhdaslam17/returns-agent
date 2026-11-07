# How to label a test email

Each item in `emails.json` is one customer email plus the answer we expect.

| Field | Meaning |
|---|---|
| `id` | E001, E002, ... Never reuse an id. |
| `language` | `en`, `ar` or `mixed` |
| `from` | sender email. Must be a customer in the DB, or add tag `unknown_sender`. |
| `subject`, `body` | the email. Put the order number in the body if the customer gives one. |
| `attachments` | file names, for example `["front.jpg"]`. Empty means no photos. |
| `expected.category` | one value from `Category` in `src/returns_agent/labels.py` |
| `expected.action` | `auto_reply`, `ask_for_details`, `prepare_refund` or `escalate` |
| `expected.needs_human` | true if the graph must pause for a person |
| `expected.suspicious` | true for fake staff emails, injection, identity problems |
| `expected.required_tools` | tools the agent must call |
| `expected.forbidden_tools` | tools the agent must NOT call |
| `tags` | free labels for grouping results, for example `tricky`, `arabic`. `draft` means not reviewed yet. |
| `why` | one or two lines: the reason, with the policy section number |

## Rules the tests check

- `prepare_refund` action means the tool is required. Any other action means it is forbidden.
- `escalate` or `suspicious` means `needs_human` is true.
- `suspicious` means the action is `escalate`.
- A prepared refund needs a human only if the order amount is above AED 500.
- Order numbers in the body must exist in the DB, unless tagged `unknown_order`.

## Why required and forbidden tools?

Checking the exact tool order is too strict. Two good agents can call tools in a
different order. So we check two things only: the tools that must happen, and the
tools that must never happen. The most important rule is: never call
`prepare_refund` when the answer is not a refund.

## Today's date

The DB uses a fixed "today": 2026-11-06 (`REFERENCE_DATE` in `data/seed_db.py`).
Count trial nights from that date, not from your real calendar.
