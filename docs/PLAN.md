# Build plan

Fast plan: no fixed days, move to the next step as soon as one is done.
You write the agent logic (`agent_logic.py`). Claude builds the support code,
reviews and debugs. See `docs/AGENT_GUIDE.md`.

| # | Goal | Status |
|---|---|---|
| 1 | Fake data and test set (62 emails) | done; label review open |
| 2 | Tools, policy search, fake payment gateway, graph wiring, eval runner | done |
| 3 | Agent logic: classify, route, decide, guardrails, approval, reply | **you, now** |
| 4 | First full eval run, honest scores, fix the worst failures | next |
| 5 | Tracing (LangSmith) | |
| 6 | FastAPI endpoint, approvals page, Docker | |
| 7 | README with diagram, real scores, known failures, short demo | |
| later | MCP server, Azure deploy, n8n trigger | optional |

## Step 1: what is ready

- `data/policy.md`: invented policy with numbered sections (cite them in replies).
- `data/seed_db.py`: 29 fake orders. Each order has a note that says which case it tests.
- `src/returns_agent/labels.py`: categories, actions, tools.
- `evals/emails.json`: 62 labelled emails, including the 4 tricky cases:
  E004 wrong order + new card, E005 fake store manager (prompt injection),
  E006 Arabic sag claim with no photo, E007 legal threat with a deadline.
  E012–E062 are drafts tagged `draft`. Review them with `evals/REVIEW.md`.
- `tests/`: checks the labels and the database. The coverage test is marked
  xfail until every draft is reviewed.

## Step 1: label review (do it alongside step 3)

1. Read `data/policy.md` and the order notes in `data/seed_db.py`.
2. Review all 62 labels with `evals/REVIEW.md`. Decide the open labeling choices.
3. Remove the `draft` tag from each email you have checked.
4. Run `pytest` after every 10 emails.
5. You can add emails or orders. Give each new order a note in `seed_db.py`.

## Design choices to be ready to explain

- **Test set before the agent.** You can't measure the agent without it, and
  writing labels forces you to decide the rules first.
- **Fixed "today".** Trial results depend on the date. A fixed date keeps tests stable.
- **`suspicious` is separate from `category`.** Category is what the email asks
  for. Suspicious is about whether we trust it. A fake manager email can ask for
  a refund and still be suspicious.
- **Required and forbidden tools, not exact order.** See `evals/README.md`.
- **Approval threshold in code and in policy.** The rule lives in policy 3.4 for
  RAG and in `APPROVAL_THRESHOLD_AED` for the hard check. The LLM must never be the
  only thing that decides if a refund needs approval.
- **Refund to original payment method only.** It stops the most common refund fraud.

## LLM and embeddings

- LLM: any OpenAI-compatible API through the `openai` Python SDK. Default is the
  Groq free tier (Gemini's free tier was only 20 requests/day). `LLM_BASE_URL`,
  `LLM_API_KEY` and `LLM_MODEL` in `.env` choose the provider, so switching needs no code change.
- Check your settings: `python scripts/check_llm.py`
- Free tiers have request limits per minute and per day. A full eval run makes
  several calls per email. Add a short pause between emails, and save results so a
  failed run can continue where it stopped.
- Structured output: `llm.parse(Schema, system, user)` in `src/returns_agent/llm.py`.
- Embeddings for the policy RAG: local `intfloat/multilingual-e5-small` with
  `sentence-transformers` (Arabic + English). Free, and RAG does not depend on the
  LLM provider.

## Known simplifications

- One product per order, quantity 1.
- Refunds run right away (after approval if needed). A real store would wait for
  pickup and inspection (policy 3.2).
- Payments use a fake gateway (`payments.py`). No real payment provider is connected.
  A real one would be a new class with the same `refund` method.
