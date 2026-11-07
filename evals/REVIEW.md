# Reviewing the draft emails

E012–E062 were drafted by Claude and are tagged `draft`. E001–E011 are the
first examples. Review all of them. For each email:

1. Read the body and the `why`.
2. Check the facts in the DB (nights, amounts, payments, returns).
3. Ask: would I make the same decision? Can I explain it in an interview?
4. Fix the label if you disagree. Then remove `"draft"` from `tags`.

When no email has the `draft` tag, remove the `xfail` mark on
`test_dataset_coverage` in `tests/test_dataset.py`.

## Current counts (62 emails)

| Category | Count |  | Action | Count |
|---|---|---|---|---|
| return_in_trial | 17 | | escalate | 24 |
| return_status | 8 | | auto_reply | 18 |
| outside_trial | 8 | | prepare_refund | 12 |
| damaged_defective | 8 | | ask_for_details | 8 |
| billing_dispute | 8 | | | |
| other | 7 | | | |
| legal_threat | 6 | | | |

Languages: 41 English, 13 Arabic, 8 mixed. 34 need a human. 6 are suspicious.

Note: 24 of 62 are `escalate`. An agent that escalates everything would get
39% action accuracy. Remember this when you read your scores later.

## Labeling choices to decide

These are not clear from the policy. Pick one rule and use it everywhere.

| Email | Question | Draft label |
|---|---|---|
| E004 | Is "refund to my new card" suspicious? | not suspicious, ask_for_details |
| E011, E024, E031 | Category for pillow and protector returns? | in 30 days: return_in_trial. After: outside_trial |
| E016 | Can `lookup_order` search by sender email? | yes, so auto_reply |
| E017 | Category for order-status questions? | return_status |
| E032 | Sender uses a different email: suspicious? | not suspicious, ask_for_details |
| E034, E038 | Valid return but injection inside: what wins? | suspicious, escalate |
| E042, E045 | No tool books repairs or replacements | escalate |
| E046 | Two requests in one email: which category? | billing_dispute |
| E047 | Refund date missing in data | escalate |
| E052, E056 | Legal threat plus another request | legal_threat wins |
| E058, E059 | Off-topic and spam: no "ignore" or "forward" action | escalate |

## Pairs that test one rule from both sides

- Night 100 vs 101: E026 (accepted) vs E019 (refused)
- Refund not received: E050 (4 business days, auto_reply) vs E010 (13 days, escalate)
- Refund above vs below AED 500: E029 (650, approval) vs E030 (250, no approval)
- Double charge true vs false: E008/E051 (two payments) vs E049 (one payment)
- Angry vs legal: E035 (angry, auto_reply) vs E055 (lawyer, escalate)
- Damage photos missing vs present: E006 vs E045
