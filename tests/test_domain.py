from aftershock.domain import evaluate


def sample(checkout=True, billing=True):
    return {"checkout": {"ok": checkout}, "billing": {"ok": billing}}


def prediction(eligible=True):
    return {
        "eligible": eligible,
        "reason": "Mandatory dependency",
        "evidence_ids": ["policy-recommendations"],
        "affected_customer_groups": 1,
    }


def test_transient_billing_interruption_rejects_otherwise_recovered_fix():
    verdict = evaluate(
        "restart_data", [sample(billing=False)] + [sample()] * 3, prediction()
    )
    assert not verdict.passed
    assert verdict.billing_failures == 1


def test_initial_checkout_failures_allow_stable_recovery():
    verdict = evaluate(
        "enable_fallback", [sample(checkout=False)] + [sample()] * 3, prediction()
    )
    assert verdict.passed
    assert verdict.checkout_failures == 1


def test_policy_violation_cannot_be_overridden_by_passing_probes():
    assert not evaluate("enable_fallback", [sample()] * 3, prediction(False)).passed


def test_incomplete_experiment_cannot_pass():
    assert not evaluate("enable_fallback", [sample()] * 2, prediction()).passed
