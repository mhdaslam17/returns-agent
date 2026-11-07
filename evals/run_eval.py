"""Run the agent on the labelled emails and score it.

    python evals/run_eval.py                    # all emails, run name "latest"
    python evals/run_eval.py --ids E001,E005    # only some emails
    python evals/run_eval.py --limit 10         # first 10 emails
    python evals/run_eval.py --run v2 --fresh   # new run, ignore saved results

Results are saved after every email in evals/results/<run>.jsonl, so if the free
tier rate limit stops a run, run the same command again and it continues. Emails
that ended in an error are tried again; the others are kept.
Each email gets a fresh copy of the database, so one refund can't change the next email.
"""

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from returns_agent import llm  # noqa: E402
from returns_agent.db import connect  # noqa: E402
from returns_agent.graph import run_email  # noqa: E402
from returns_agent.scoring import score_one, summarize, to_markdown  # noqa: E402

RESULTS_DIR = ROOT / "evals" / "results"


def load_seed():
    spec = importlib.util.spec_from_file_location("seed_db", ROOT / "data" / "seed_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Arabic text on the Windows console
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="latest", help="name for this run")
    parser.add_argument("--ids", help="comma-separated email ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--fresh", action="store_true", help="delete saved results for this run first")
    parser.add_argument("--sleep", type=float, default=float(os.getenv("EVAL_SLEEP", "4")),
                        help="seconds to wait between emails (free tier rate limits)")
    args = parser.parse_args()

    emails = json.loads((ROOT / "evals" / "emails.json").read_text(encoding="utf-8"))
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        emails = [e for e in emails if e["id"] in wanted]
    if args.limit:
        emails = emails[: args.limit]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_path = RESULTS_DIR / f"{args.run}.jsonl"
    if args.fresh and results_path.exists():
        results_path.unlink()
    done = {}
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done[r["email_id"]] = r

    seed = load_seed()
    rate_limited_in_a_row = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, email in enumerate(emails, 1):
            if email["id"] in done and done[email["id"]]["status"] != "error":
                continue  # finished before; emails that errored (e.g. 503) are tried again
            con = connect(seed.build(Path(tmp) / f"{email['id']}.db"))
            llm.USAGE.update(calls=0, tokens=0)
            started = time.time()
            result = run_email(email, con).model_dump()
            con.close()
            result["seconds"] = round(time.time() - started, 1)
            result["model"] = os.getenv("LLM_MODEL")
            result["llm_calls"], result["tokens"] = llm.USAGE["calls"], llm.USAGE["tokens"]
            done[email["id"]] = result
            with results_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
            mark = "ERROR " + (result["error"] or "")[:80] if result["status"] == "error" else \
                f"{result['category']} / {result['action']} ({result['status']})"
            print(f"[{i}/{len(emails)}] {email['id']}: {mark}  [{result['tokens']} tokens]")

            # A daily quota will not come back in this run: stop instead of failing every email.
            rate_limited = "RateLimitError" in (result["error"] or "")
            rate_limited_in_a_row = rate_limited_in_a_row + 1 if rate_limited else 0
            if rate_limited_in_a_row >= 2:
                print("\nStopped: rate limit (429) twice in a row. Run the same command later to continue.")
                break
            if i < len(emails) and args.sleep:
                time.sleep(args.sleep)

    scored = [score_one(e, done[e["id"]]) for e in emails if e["id"] in done]
    summary = summarize(emails, scored)
    finished = [done[e["id"]] for e in emails if e["id"] in done]
    models = sorted({str(r.get("model")) for r in finished})
    tokens = sum(r.get("tokens", 0) for r in finished)
    header = f"Model: {', '.join(models)}. LLM tokens used: {tokens:,}."
    report = to_markdown(summary, args.run).replace("\n\n", f"\n\n{header}\n\n", 1)
    (RESULTS_DIR / f"{args.run}.md").write_text(report, encoding="utf-8")
    print()
    print(report)


if __name__ == "__main__":
    main()
