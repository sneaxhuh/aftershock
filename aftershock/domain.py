from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class Action(StrEnum):
    ROLLBACK = "rollback_checkout"
    RESTART = "restart_data"
    FALLBACK = "enable_fallback"


ACTION_INFO = {
    Action.ROLLBACK: {
        "title": "Roll back checkout",
        "description": "Replace checkout v2 with the v1 process.",
        "target": "checkout",
    },
    Action.RESTART: {
        "title": "Restart shared data",
        "description": "Stop and restart the shared data process.",
        "target": "data",
    },
    Action.FALLBACK: {
        "title": "Enable graceful fallback",
        "description": "Skip optional recommendations when they time out.",
        "target": "checkout",
    },
}


class Verdict(BaseModel):
    passed: bool
    reasons: list[str]
    evidence_ids: list[str]
    billing_failures: int
    checkout_failures: int
    affected_customer_groups: int


def evaluate(action: str, observations: list[dict], prediction: dict) -> Verdict:
    """Evaluate real samples; recovery must persist across the last three probes."""
    if len(observations) < 3:
        return Verdict(
            passed=False,
            reasons=[
                "Incomplete experiment: at least three final probes are required."
            ],
            evidence_ids=prediction["evidence_ids"],
            billing_failures=0,
            checkout_failures=0,
            affected_customer_groups=0,
        )
    checkout_failures = sum(not p["checkout"]["ok"] for p in observations)
    billing_failures = sum(not p["billing"]["ok"] for p in observations)
    reasons = []
    if not prediction["eligible"]:
        reasons.append(prediction["reason"])
    if not all(p["checkout"]["ok"] for p in observations[-3:]):
        reasons.append("Checkout did not recover across the final three probes.")
    if billing_failures:
        reasons.append(
            f"Billing was interrupted in {billing_failures} observed probes."
        )
    if not reasons:
        reasons.append(
            "Checkout recovered; billing remained healthy; graph requirements passed."
        )
    return Verdict(
        passed=prediction["eligible"]
        and not billing_failures
        and all(p["checkout"]["ok"] for p in observations[-3:]),
        reasons=reasons,
        evidence_ids=prediction["evidence_ids"],
        billing_failures=billing_failures,
        checkout_failures=checkout_failures,
        affected_customer_groups=prediction["affected_customer_groups"],
    )


class CreateRun(BaseModel):
    name: str = Field(default="Northstar Commerce", max_length=80)


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=8, max_length=100)


class PolicyRequest(BaseModel):
    required: bool


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    arguments: dict = Field(default_factory=dict)
