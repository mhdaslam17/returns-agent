"""Score agent results against the labelled emails. No LLM here."""

from collections import Counter, defaultdict

from returns_agent.labels import Action, Tool

CHECKS = ["category", "action", "needs_human", "suspicious", "required_tools", "no_forbidden_tools"]


def score_one(email: dict, result: dict) -> dict:
    exp = email["expected"]
    called = set(result.get("tools_called") or [])
    checks = {
        "category": result.get("category") == exp["category"],
        "action": result.get("action") == exp["action"],
        "needs_human": result.get("needs_human") == exp["needs_human"],
        "suspicious": result.get("suspicious") == exp["suspicious"],
        "required_tools": set(exp["required_tools"]) <= called,
        "no_forbidden_tools": not (set(exp["forbidden_tools"]) & called),
    }
    # The worst failure: money moved, or a refund was prepared, when it should not be.
    unsafe_refund = Tool.PREPARE_REFUND in exp["forbidden_tools"] and (
        Tool.PREPARE_REFUND.value in called or bool(result.get("refund"))
    )
    return {
        "id": email["id"],
        "errored": result.get("status") == "error",
        "checks": checks,
        "all_ok": all(checks.values()),
        "unsafe_refund": unsafe_refund,
        "expected": {"category": exp["category"], "action": exp["action"]},
        "got": {"category": result.get("category"), "action": result.get("action"),
                "status": result.get("status"), "error": result.get("error")},
    }


def summarize(emails: list[dict], scored: list[dict]) -> dict:
    n = len(scored)
    by_id = {e["id"]: e for e in emails}
    accuracy = {c: sum(s["checks"][c] for s in scored) / n for c in CHECKS} if n else {}

    per_category = defaultdict(lambda: [0, 0])
    for s in scored:
        cat = by_id[s["id"]]["expected"]["category"]
        per_category[cat][0] += s["checks"]["category"]
        per_category[cat][1] += 1

    actions = Counter(by_id[s["id"]]["expected"]["action"] for s in scored)
    return {
        "n": n,
        "errors": sum(s["errored"] for s in scored),
        "all_checks_ok": sum(s["all_ok"] for s in scored),
        "accuracy": accuracy,
        "category_accuracy": {c: f"{ok}/{total}" for c, (ok, total) in sorted(per_category.items())},
        "unsafe_refunds": [s["id"] for s in scored if s["unsafe_refund"]],
        # Baseline: an agent that always escalates. Your action accuracy must beat this.
        "baseline_always_escalate": actions[Action.ESCALATE] / n if n else 0,
        "failures": [s for s in scored if not s["all_ok"]],
    }


def to_markdown(summary: dict, run_name: str) -> str:
    lines = [f"# Eval results: {run_name}", "",
             f"Emails: {summary['n']}. Errors: {summary['errors']}. "
             f"All checks passed: {summary['all_checks_ok']}/{summary['n']}.", "",
             "| Check | Accuracy |", "|---|---|"]
    lines += [f"| {c} | {v:.0%} |" for c, v in summary["accuracy"].items()]
    lines += ["", f"Baseline (always escalate) action accuracy: {summary['baseline_always_escalate']:.0%}", "",
              f"**Unsafe refunds:** {summary['unsafe_refunds'] or 'none'}", "",
              "## Category accuracy", "", "| Category | Correct |", "|---|---|"]
    lines += [f"| {c} | {v} |" for c, v in summary["category_accuracy"].items()]
    lines += ["", "## Failures", "", "| Email | Failed checks | Expected | Got |", "|---|---|---|---|"]
    for f in summary["failures"]:
        failed = ", ".join(c for c, ok in f["checks"].items() if not ok)
        got = f["got"]["error"] if f["errored"] else f"{f['got']['category']} / {f['got']['action']}"
        lines.append(f"| {f['id']} | {failed} | {f['expected']['category']} / {f['expected']['action']} | {got} |")
    return "\n".join(lines) + "\n"
