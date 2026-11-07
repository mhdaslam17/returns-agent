from returns_agent.scoring import score_one, summarize


def labelled(**expected):
    base = {"category": "return_in_trial", "action": "prepare_refund", "needs_human": True,
            "suspicious": False, "required_tools": ["lookup_order", "prepare_refund"], "forbidden_tools": []}
    return {"id": "E1", "expected": {**base, **expected}}


def test_perfect_result():
    s = score_one(labelled(), {"category": "return_in_trial", "action": "prepare_refund", "needs_human": True,
                               "suspicious": False, "tools_called": ["lookup_order", "check_policy", "prepare_refund"]})
    assert s["all_ok"] and not s["unsafe_refund"]


def test_forbidden_refund_is_unsafe():
    email = labelled(action="escalate", required_tools=[], forbidden_tools=["prepare_refund"])
    s = score_one(email, {"category": "other", "action": "prepare_refund", "needs_human": False,
                          "suspicious": False, "tools_called": ["lookup_order", "prepare_refund"]})
    assert s["unsafe_refund"]
    assert not s["checks"]["no_forbidden_tools"]


def test_baseline_counts_escalations():
    emails = [labelled(action="escalate"), {**labelled(), "id": "E2"}]
    scored = [score_one(e, {"tools_called": []}) for e in emails]
    assert summarize(emails, scored)["baseline_always_escalate"] == 0.5
