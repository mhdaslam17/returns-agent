# Agent guide: what is built, what you build

## Who wrote what

| File | Owner | What it does |
|---|---|---|
| `src/returns_agent/agent_logic.py` | **your decisions**, typed by Claude | prompts, decisions, guardrails, routing, approval pause |
| `src/returns_agent/graph.py` | Claude | LangGraph wiring, state, tool calls, refund run |
| `src/returns_agent/tools.py` | Claude | `lookup_order`, `prepare_refund` (facts only, no decisions) |
| `src/returns_agent/rag.py` | Claude | policy search: clause chunks, local embeddings, FAISS |
| `src/returns_agent/payments.py` | Claude | fake payment gateway with safety rules |
| `src/returns_agent/scoring.py`, `evals/run_eval.py` | Claude | eval runner and scores |

You must be able to explain all of it. Read every file and ask about anything unclear.

## The flow

```
START -> classify -> gather_facts -> decide --> draft_reply ----------------------> END
                                           --> escalate --------------------------> END
                                           --> prepare_refund --> execute_refund --> draft_reply
                                                              --> human_approval (pause) --> execute_refund
                                                              --> escalate (refund not possible / rejected)
```

## Your design decisions

Claude asked, you chose, Claude typed the code. Be ready to explain each choice.

| # | Question | Your choice | Why |
|---|---|---|---|
| 1 | How to spot suspicious emails? | The LLM in classify, plus code guardrails | One LLM call per email (free tier). Code covers what the LLM misses. |
| 2 | Two categories fit? | Legal first, then billing, then damaged, then the rest | A threat must always reach a person |
| 3 | Who decides in or out of trial? | Code, after lookup (`refine_category`) | Exact dates, testable, no LLM date maths. Night 100 in, 101 out. |
| 4 | Where does `ask_for_details` go? | `draft_reply` | The agent can ask for missing info. No person needed. |
| 5 | Who picks the refund payment and amount? | The LLM picks, code checks | Handles double charges. `prepare_refund` blocks wrong payments or amounts. |
| 6 | Decide prompt rules? | Short action rules in the prompt, plus RAG clauses | Reliable, and RAG still supplies the policy details |
| 7 | Guardrails? | Suspicious → escalate; a refund needs a found order the sender owns; no refund outside trial | Hard rules the LLM can't break. Legal threats are left to the prompt on purpose, and the eval shows if that is enough. |
| 8 | What does the approver see? | The proposal plus context (customer, category, reason, clauses) | The lead can decide without opening the database |
| 9 | Reply to escalated emails? | Yes, a short acknowledgment, but none to suspicious senders | Customers aren't left waiting. No reply to a possible attacker. |

Two safety details in code:
- An unclear approval (for example `"yes"` and not `true`) counts as a rejection.
- If the sender doesn't own the order, the reply LLM never sees the order details.

## Model

History (all on 2026-11-07):
- Gemini `gemini-3.8-flash` / `3.7-flash`: 503 errors and timeouts.
- Gemini `gemini-3.6-flash`: worked, but the free tier allows only **20 requests
  a day** per model. A full eval needs about 3 calls per email (186 in all).
- Now: Groq free tier, `openai/gpt-oss-120b`. Each eval result records the model,
  LLM calls and tokens. The runner stops after two 429 errors in a row; run it again later to continue.

Commands:

```bash
.venv\Scripts\python.exe evals\run_eval.py --ids E001,E005,E006,E007 --run try1 --fresh
.venv\Scripts\python.exe evals\run_eval.py --run v1
.venv\Scripts\python.exe -m pytest -q
```

Results: `evals/results/<run>.md`.

## Safety rules that are in code, not in prompts

The LLM can be fooled by an email. Code can't be. So these never depend on the LLM:

- Refunds go only to the original card. `prepare_refund` and the gateway have no
  "card" or "account" parameter at all.
- Refund above AED 500 needs approval: `requires_approval` is set in `tools.py`.
- No refund on a payment that is already refunded, and never more than was paid.
- Each email in the eval gets a fresh database.

Your guardrails in `apply_guardrails` add a second layer: suspicious, legal and
identity rules.

## Interview points to prepare

- Why a fixed workflow and not a free tool-calling loop?
- Why are tools "facts only"?
- Why does the gateway have no destination parameter?
- How does `interrupt` pause and resume? What does the checkpointer do?
- What is your score, what is the "always escalate" baseline, and which emails fail and why?
