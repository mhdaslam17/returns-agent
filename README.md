# Returns Agent

A customer support agent for returns and refunds at **Dunelight Mattress Co.**,
an invented online mattress store in the UAE. Personal portfolio project.

> All data is fictional: the store, customers, orders and policy are made up.
> Payments use a fake gateway. No real money or payment provider is involved.

**Status:** work in progress. Data, test set, tools, policy search, fake payment
gateway, graph wiring and eval runner are done. The agent's decision logic is being written.

## What it will do

1. Read a customer email (English, Arabic or mixed).
2. Classify it (return status, in trial, outside trial, damaged, billing, legal threat).
3. Look up the order in a SQLite database.
4. Check the return policy with RAG.
5. Decide: auto-reply, ask for details, prepare a refund, or escalate.
6. Pause for human approval for refunds above AED 500, suspicious emails and legal threats.
7. Trace and log every step.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then add your own keys
python data/seed_db.py      # builds data/orders.db
pytest
```

## Try it in the browser

```bash
.venv\Scripts\python.exe -m uvicorn returns_agent.api:app --app-dir src --port 8000
```

Open http://localhost:8000 (the first start takes about 20 seconds to load the
embedding model). Paste an email, or load one of the 62 test emails, and press
**Run agent**. The page shows each step: classification, order facts, policy
clauses, decision (guardrail overrides are highlighted), approval and the reply.
Refunds above AED 500 wait for **Approve** or **Reject**. The **Eval results** tab
shows the scores and failures of each eval run.

API: `POST /api/runs`, `POST /api/runs/{id}/approval`, `GET /api/test-emails`,
`GET /api/eval/{name}`. Interactive docs: http://localhost:8000/docs

## Project layout

```
data/policy.md          invented return policy (used for RAG)
data/seed_db.py         builds the fake order database
evals/emails.json       labelled test emails
evals/run_eval.py       runs the agent on all emails and scores it
src/returns_agent/      agent code (see docs/AGENT_GUIDE.md)
src/returns_agent/api.py      FastAPI backend; static/index.html is the test page
scripts/check_llm.py    checks your LLM settings
scripts/try_email.py    runs one email in the terminal, step by step
tests/                  pytest tests
docs/                   plan and guides
```

Payments use a fake gateway that records refunds in SQLite. No real payment
provider is connected.

## Evaluation results

**Run v1** (2026-11-07). Model `openai/gpt-oss-120b` on the Groq free tier, low
reasoning effort. 62 labelled emails, 51 of them draft labels not yet reviewed.

| Check | Score |
|---|---|
| All checks passed | 46/62 (74%) |
| Category | 92% |
| Action | 77% (an "always escalate" agent would score 39%) |
| Needs human | 85% |
| Suspicious detected | 100% |
| Unsafe refunds prepared | 2 (E040, E062). Both stopped at human approval; no money moved. |

Known failures:
- **Damage and warranty emails:** 6 of 8 had the wrong action. The agent often
  replied that a warranty claim was covered without asking for photos, or
  promised a replacement instead of passing the case to a person.
- **Two refunds should not have been prepared:** a damage claim with no photos
  (E040), and an order not yet delivered (E062). The approval step stopped both.
- **One soft legal threat was missed:** "my brother is a lawyer" (E055).
- **Off-topic emails and spam got automatic replies**, but the labels say a
  person should handle them (E058, E059).
