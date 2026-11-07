r"""The LangGraph wiring. The decisions are in agent_logic.py.

    START -> classify -> gather_facts -> decide --+--> draft_reply ---------------------------> END
                                                   +--> escalate --> draft_reply (acknowledgment) -> END
                                                   |            \--> END (suspicious: no reply)
                                                   +--> prepare_refund --+--> execute_refund --> draft_reply
                                                                         +--> human_approval --> execute_refund
                                                                         |        (interrupt)  \-> escalate (rejected)
                                                                         \--> escalate (refund not possible)

Design: a fixed workflow, not a free "ReAct" loop. lookup_order and check_policy
always run, and prepare_refund runs only after the decide step says so. This is
easier to test and safer for money. The cost: less flexible on strange emails.
"""

import operator
import sqlite3
import uuid
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from returns_agent import agent_logic as logic
from returns_agent.labels import Tool
from returns_agent.payments import FakeGateway, RefundError
from returns_agent.rag import check_policy
from returns_agent.schemas import AgentResult, Classification, Decision
from returns_agent.tools import lookup_order, prepare_refund


class AgentState(TypedDict, total=False):
    email: dict
    classification: dict
    order: dict
    policy: list[dict]
    decision: dict
    refund_proposal: dict | None
    approval: dict | None
    refund: dict | None
    reply: str | None
    escalated: bool
    error: str | None
    tools_called: Annotated[list[str], operator.add]  # each node adds; LangGraph joins the lists


def build_graph(con: sqlite3.Connection, checkpointer=None):
    gateway = FakeGateway(con)

    def classify(state: AgentState) -> dict:
        c = logic.classify_email(state["email"])
        return {"classification": c.model_dump(mode="json")}

    def gather_facts(state: AgentState) -> dict:
        c = Classification(**state["classification"])
        order = lookup_order(con, order_id=c.order_id, sender_email=state["email"].get("from"))
        c = logic.refine_category(c, order)  # in/out of trial from real dates
        policy = check_policy(f"{c.category}: {c.summary}")
        return {"classification": c.model_dump(mode="json"), "order": order, "policy": policy,
                "tools_called": [Tool.LOOKUP_ORDER.value, Tool.CHECK_POLICY.value]}

    def decide(state: AgentState) -> dict:
        c = Classification(**state["classification"])
        d = logic.decide_action(state["email"], c, state["order"], state["policy"])
        d = logic.apply_guardrails(d, c, state["order"], state["email"])
        return {"decision": d.model_dump(mode="json")}

    def prepare(state: AgentState) -> dict:
        d = Decision(**state["decision"])
        called = [Tool.PREPARE_REFUND.value]
        try:
            if not d.refund_payment_id or d.refund_amount_aed is None:
                raise RefundError("decision has no payment_id or amount")
            proposal = prepare_refund(con, state["order"].get("order_id"), d.refund_payment_id,
                                      d.refund_amount_aed, d.reason)
            return {"refund_proposal": proposal.to_dict(), "tools_called": called}
        except RefundError as e:
            return {"refund_proposal": None, "error": f"refund not possible: {e}", "tools_called": called}

    def human_approval(state: AgentState) -> dict:
        decision = state["decision"]
        context = {
            "email_id": state["email"]["id"],
            "customer_name": state["order"].get("customer_name"),
            "category": state["classification"]["category"],
            "decision_reason": decision["reason"],
            "policy_clauses": decision["policy_clauses"],
            "email_subject": state["email"].get("subject"),
        }
        return {"approval": logic.ask_for_approval(state["refund_proposal"], context)}

    def execute_refund(state: AgentState) -> dict:
        p = state["refund_proposal"]
        try:
            return {"refund": gateway.refund(p["payment_id"], p["amount_aed"], p["reason"]).to_dict()}
        except RefundError as e:
            return {"error": f"gateway refused: {e}"}

    def escalate(state: AgentState) -> dict:
        return {"escalated": True}

    def draft_reply(state: AgentState) -> dict:
        reply = logic.write_reply(state["email"], Classification(**state["classification"]), state["order"],
                                  state["policy"], Decision(**state["decision"]), state.get("refund"),
                                  bool(state.get("escalated")))
        return {"reply": reply, "tools_called": [Tool.DRAFT_REPLY.value]}

    def after_decide(state: AgentState) -> str:
        return logic.route_after_decide(Decision(**state["decision"]))

    def after_prepare(state: AgentState) -> str:
        proposal = state.get("refund_proposal")
        if not proposal:
            return "escalate"
        return "human_approval" if proposal["requires_approval"] else "execute_refund"

    def after_approval(state: AgentState) -> str:
        return "execute_refund" if (state.get("approval") or {}).get("approved") else "escalate"

    def after_execute(state: AgentState) -> str:
        return "draft_reply" if state.get("refund") else "escalate"

    def after_escalate(state: AgentState) -> str:
        # Real customers get a short acknowledgment. Suspicious senders get no reply.
        return END if state["classification"].get("suspicious") else "draft_reply"

    g = StateGraph(AgentState)
    g.add_node("classify", classify)
    g.add_node("gather_facts", gather_facts)
    g.add_node("decide", decide)
    g.add_node("prepare_refund", prepare)
    g.add_node("human_approval", human_approval)
    g.add_node("execute_refund", execute_refund)
    g.add_node("escalate", escalate)
    g.add_node("draft_reply", draft_reply)

    g.add_edge(START, "classify")
    g.add_edge("classify", "gather_facts")
    g.add_edge("gather_facts", "decide")
    g.add_conditional_edges("decide", after_decide, ["prepare_refund", "escalate", "draft_reply"])
    g.add_conditional_edges("prepare_refund", after_prepare, ["human_approval", "execute_refund", "escalate"])
    g.add_conditional_edges("human_approval", after_approval, ["execute_refund", "escalate"])
    g.add_conditional_edges("execute_refund", after_execute, ["draft_reply", "escalate"])
    g.add_conditional_edges("escalate", after_escalate, ["draft_reply", END])
    g.add_edge("draft_reply", END)

    # The checkpointer saves state at each step. interrupt() needs it to pause and resume.
    return g.compile(checkpointer=checkpointer or InMemorySaver())


def _to_result(email: dict, state: dict, interrupted: bool, error: str | None = None) -> AgentResult:
    classification = state.get("classification") or {}
    decision = state.get("decision") or {}
    escalated = bool(state.get("escalated"))
    if error:
        status = "error"
    elif interrupted:
        status = "waiting_for_approval"
    elif escalated:
        status = "escalated"
    else:
        status = "done"
    return AgentResult(
        email_id=email["id"],
        status=status,
        category=classification.get("category"),
        action=decision.get("action"),
        decision_reason=decision.get("reason"),
        needs_human=interrupted or escalated,
        suspicious=bool(classification.get("suspicious")),
        tools_called=state.get("tools_called", []),
        reply=state.get("reply"),
        refund_proposal=state.get("refund_proposal"),
        refund=state.get("refund"),
        error=error or state.get("error"),
    )


def run_email(email: dict, con: sqlite3.Connection, graph=None, thread_id: str | None = None) -> AgentResult:
    """Run the agent on one email. Stops at the approval pause if there is one."""
    graph = graph or build_graph(con)
    config = {"configurable": {"thread_id": thread_id or f"{email['id']}-{uuid.uuid4().hex[:8]}"}}
    try:
        state = graph.invoke({"email": email, "tools_called": []}, config)
    except Exception as e:  # report the error, keep the eval running
        partial = graph.get_state(config).values
        return _to_result(email, partial, interrupted=False, error=f"{type(e).__name__}: {e}")
    return _to_result(email, state, interrupted="__interrupt__" in state)


def resume_after_approval(email: dict, graph, thread_id: str, approved: bool, by: str) -> AgentResult:
    """A person approves or rejects a paused refund. The graph continues from the pause."""
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.invoke(Command(resume={"approved": approved, "by": by}), config)
    return _to_result(email, state, interrupted="__interrupt__" in state)
