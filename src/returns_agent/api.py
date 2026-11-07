"""REST API and test page for the agent.

    .venv\\Scripts\\python.exe -m uvicorn returns_agent.api:app --app-dir src --port 8000
    then open http://localhost:8000

Endpoints:
    GET  /api/test-emails             the 62 labelled emails (to load into the form)
    GET  /api/customers               customers and orders in the fake database
    POST /api/runs                    run the agent on one email
    POST /api/runs/{run_id}/approval  approve or reject a paused refund
    GET  /api/eval                    list of eval runs
    GET  /api/eval/{name}             scores and failures of one eval run

Each run gets a fresh copy of the fake database (like the eval), so test refunds
never pile up. Paused runs live in memory: a server restart forgets them.
"""

import importlib.util
import json
import shutil
import tempfile
import threading
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from langgraph.types import Command
from pydantic import BaseModel, Field

from returns_agent import llm
from returns_agent.config import ROOT
from returns_agent.db import connect
from returns_agent.graph import build_graph
from returns_agent.rag import get_policy_index
from returns_agent.scoring import score_one, summarize
from returns_agent.tools import lookup_order

EMAILS_PATH = ROOT / "evals" / "emails.json"
RESULTS_DIR = ROOT / "evals" / "results"
PAGE = Path(__file__).parent / "static" / "index.html"
MAX_KEPT_RUNS = 20


def _load_seed():
    spec = importlib.util.spec_from_file_location("seed_db", ROOT / "data" / "seed_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEED = _load_seed()
RUNS: "OrderedDict[str, dict]" = OrderedDict()  # run_id -> graph, connection, email, temp dir
RUNS_LOCK = threading.Lock()
LLM_LOCK = threading.Lock()  # one run at a time: llm.USAGE is shared, and free tiers limit tokens/minute


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_policy_index()  # load the embedding model once at start, not on the first request
    yield
    for run_id in list(RUNS):
        _drop(run_id)


app = FastAPI(title="Dunelight Returns Agent", lifespan=lifespan)


class EmailIn(BaseModel):
    email_id: str | None = Field(None, description="Use a labelled test email, e.g. E001")
    sender: str = "sara.mansoori@example.com"
    subject: str = "Customer email"
    body: str = ""
    attachments: list[str] = []


class ApprovalIn(BaseModel):
    approved: bool
    by: str = "web-tester"


def _test_emails() -> list[dict]:
    return json.loads(EMAILS_PATH.read_text(encoding="utf-8"))


def _drop(run_id: str) -> None:
    run = RUNS.pop(run_id, None)
    if run:
        run["con"].close()
        shutil.rmtree(run["tmp"], ignore_errors=True)


def _payload(run_id: str, state: dict, email: dict) -> dict:
    interrupted = "__interrupt__" in state
    status = "waiting_for_approval" if interrupted else "escalated" if state.get("escalated") else "done"
    return {
        "run_id": run_id,
        "status": status,
        "email": email,
        "expected": email.get("expected"),
        "classification": state.get("classification"),
        "order": state.get("order"),
        "policy": state.get("policy"),
        "decision": state.get("decision"),
        "approval_request": state["__interrupt__"][0].value if interrupted else None,
        "approval": state.get("approval"),
        "refund": state.get("refund"),
        "reply": state.get("reply"),
        "error": state.get("error"),
        "tools_called": state.get("tools_called", []),
        "usage": dict(llm.USAGE),
    }


def _invoke(run: dict, value) -> dict:
    with LLM_LOCK:
        llm.USAGE.update(calls=0, tokens=0)
        try:
            return run["graph"].invoke(value, run["config"])
        except Exception as e:  # LLM down, rate limit, bad output: tell the page why
            raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}") from e


@app.get("/")
def page():
    return FileResponse(PAGE)


@app.get("/api/test-emails")
def test_emails():
    return _test_emails()


@app.get("/api/customers")
def customers():
    """Every customer and order in the fake database, with the facts that matter for testing."""
    notes = {order[0]: order[6] for order in SEED.ORDERS}  # why each order exists
    tmp = Path(tempfile.mkdtemp(prefix="returns-customers-"))
    con = connect(SEED.build(tmp / "orders.db"))
    try:
        rows = []
        for c in con.execute("SELECT * FROM customers ORDER BY name").fetchall():
            for o in con.execute("SELECT order_id FROM orders WHERE customer_id = ? ORDER BY order_id",
                                 (c["customer_id"],)).fetchall():
                f = lookup_order(con, o["order_id"])
                rows.append({
                    "name": c["name"], "email": c["email"], "language": c["language"],
                    "order_id": f["order_id"], "product": f["product"], "amount_aed": f["amount_aed"],
                    "status": f["status"], "nights_since_delivery": f["nights_since_delivery"],
                    "note": notes.get(f["order_id"], ""),
                })
        return rows
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)


@app.post("/api/runs")
def create_run(email_in: EmailIn):
    if email_in.email_id:
        email = next((e for e in _test_emails() if e["id"] == email_in.email_id), None)
        if email is None:
            raise HTTPException(404, f"No test email {email_in.email_id}")
    else:
        if not email_in.body.strip():
            raise HTTPException(422, "The email body is empty.")
        email = {"id": "MANUAL", "from": email_in.sender.strip(), "subject": email_in.subject,
                 "body": email_in.body, "attachments": email_in.attachments}

    run_id = uuid.uuid4().hex[:12]
    tmp = Path(tempfile.mkdtemp(prefix="returns-run-"))
    con = connect(SEED.build(tmp / "orders.db"))
    run = {"graph": build_graph(con), "con": con, "tmp": tmp, "email": email,
           "config": {"configurable": {"thread_id": run_id}}}
    with RUNS_LOCK:
        RUNS[run_id] = run
        while len(RUNS) > MAX_KEPT_RUNS:
            _drop(next(iter(RUNS)))
    state = _invoke(run, {"email": email, "tools_called": []})
    return _payload(run_id, state, email)


@app.post("/api/runs/{run_id}/approval")
def approve(run_id: str, approval: ApprovalIn):
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found (the server may have restarted). Run the email again.")
    snapshot = run["graph"].get_state(run["config"])
    if not snapshot.interrupts:
        raise HTTPException(409, "This run is not waiting for approval.")
    state = _invoke(run, Command(resume={"approved": approval.approved, "by": approval.by}))
    return _payload(run_id, state, run["email"])


@app.get("/api/eval")
def eval_runs():
    return sorted(p.stem for p in RESULTS_DIR.glob("*.jsonl")) if RESULTS_DIR.exists() else []


@app.get("/api/eval/{name}")
def eval_report(name: str):
    path = RESULTS_DIR / f"{name}.jsonl"
    if not path.resolve().is_relative_to(RESULTS_DIR.resolve()) or not path.exists():
        raise HTTPException(404, f"No eval run {name}")
    results = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        results[r["email_id"]] = r
    emails = [e for e in _test_emails() if e["id"] in results]
    scored = [score_one(e, results[e["id"]]) for e in emails]
    summary = summarize(emails, scored)
    return {
        "name": name,
        "models": sorted({str(r.get("model")) for r in results.values()}),
        "tokens": sum(r.get("tokens", 0) for r in results.values()),
        **summary,
    }
