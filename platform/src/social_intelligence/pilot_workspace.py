"""Internal-staging discovery and seven-day pilot planning.

This module produces a deterministic planning artifact. It does not connect to
customer systems, provision infrastructure, or execute external actions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any

from .stack_advisor import StackAdvisorRequest, recommend_stack


WORKFLOW_STEPS: dict[str, list[dict[str, str]]] = {
    "lead_response": [
        {"name": "Receive and deduplicate lead", "mode": "code", "action": "read_only"},
        {"name": "Enrich approved account fields", "mode": "workflow", "action": "read_only"},
        {"name": "Classify intent and urgency", "mode": "ai_judgment", "action": "recommend"},
        {"name": "Draft a policy-compliant reply", "mode": "ai_generation", "action": "draft_only"},
        {"name": "Approve sensitive or commercial language", "mode": "human", "action": "approve"},
        {"name": "Record outcome and learning", "mode": "workflow", "action": "internal_write"},
    ],
    "document_processing": [
        {"name": "Receive and fingerprint document", "mode": "code", "action": "internal_write"},
        {"name": "Extract structured fields", "mode": "ai_extraction", "action": "recommend"},
        {"name": "Validate types and business rules", "mode": "code", "action": "read_only"},
        {"name": "Route ambiguous exceptions", "mode": "ai_judgment", "action": "recommend"},
        {"name": "Approve high-impact exceptions", "mode": "human", "action": "approve"},
        {"name": "Write validated record and lineage", "mode": "workflow", "action": "internal_write"},
    ],
    "follow_up": [
        {"name": "Read approved contact context", "mode": "workflow", "action": "read_only"},
        {"name": "Select an approved next action", "mode": "ai_judgment", "action": "recommend"},
        {"name": "Draft channel-specific message", "mode": "ai_generation", "action": "draft_only"},
        {"name": "Check policy, cadence, and consent", "mode": "code", "action": "read_only"},
        {"name": "Approve outbound communication", "mode": "human", "action": "approve"},
        {"name": "Record response and disposition", "mode": "workflow", "action": "internal_write"},
    ],
    "crm_reactivation": [
        {"name": "Select eligible dormant records", "mode": "code", "action": "read_only"},
        {"name": "Score reactivation potential", "mode": "ai_judgment", "action": "recommend"},
        {"name": "Assign control and treatment", "mode": "code", "action": "internal_write"},
        {"name": "Draft approved message variants", "mode": "ai_generation", "action": "draft_only"},
        {"name": "Approve campaign batch", "mode": "human", "action": "approve"},
        {"name": "Measure incremental pipeline", "mode": "workflow", "action": "read_only"},
    ],
    "internal_reporting": [
        {"name": "Read governed metric tables", "mode": "workflow", "action": "read_only"},
        {"name": "Compute deterministic measures", "mode": "code", "action": "read_only"},
        {"name": "Detect material exceptions", "mode": "code", "action": "recommend"},
        {"name": "Draft grounded explanation", "mode": "ai_generation", "action": "draft_only"},
        {"name": "Verify citations and material claims", "mode": "human", "action": "approve"},
        {"name": "Publish internal report", "mode": "workflow", "action": "internal_write"},
    ],
}


def _text(value: str, field: str, maximum: int = 500) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum or any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{field} must be printable and between 1 and {maximum} characters")
    return normalized


def _number(value: float, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if not minimum <= number <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return number


@dataclass(frozen=True)
class PilotDiscoveryRequest:
    tenant_id: str
    workflow_type: str
    business_outcome: str
    process_owner: str
    weekly_volume: int
    minutes_per_case: float
    loaded_hourly_cost_usd: float
    baseline_success_rate: float
    target_success_rate: float
    target_time_reduction_pct: float = 35.0
    integration_surface: str = "mixed"
    risk_level: str = "moderate"
    cloud_preference: str = "databricks"
    evidence_ids: tuple[str, ...] = ()

    def normalized(self) -> "PilotDiscoveryRequest":
        if (
            not isinstance(self.weekly_volume, int)
            or isinstance(self.weekly_volume, bool)
            or not 1 <= self.weekly_volume <= 10_000_000
        ):
            raise ValueError("weekly_volume must be an integer between 1 and 10000000")
        baseline = _number(self.baseline_success_rate, "baseline_success_rate", 0, 100)
        target = _number(self.target_success_rate, "target_success_rate", 0, 100)
        if target <= baseline:
            raise ValueError("target_success_rate must be greater than baseline_success_rate")
        evidence_ids = tuple(
            sorted({_text(value, "evidence_id", 256) for value in self.evidence_ids})
        )
        return PilotDiscoveryRequest(
            tenant_id=_text(self.tenant_id, "tenant_id", 63),
            workflow_type=_text(self.workflow_type, "workflow_type", 64).lower(),
            business_outcome=_text(self.business_outcome, "business_outcome", 500),
            process_owner=_text(self.process_owner, "process_owner", 120),
            weekly_volume=self.weekly_volume,
            minutes_per_case=_number(self.minutes_per_case, "minutes_per_case", 0.1, 10080),
            loaded_hourly_cost_usd=_number(
                self.loaded_hourly_cost_usd, "loaded_hourly_cost_usd", 0, 10000
            ),
            baseline_success_rate=baseline,
            target_success_rate=target,
            target_time_reduction_pct=_number(
                self.target_time_reduction_pct,
                "target_time_reduction_pct",
                1,
                95,
            ),
            integration_surface=_text(
                self.integration_surface, "integration_surface", 32
            ).lower(),
            risk_level=_text(self.risk_level, "risk_level", 32).lower(),
            cloud_preference=_text(
                self.cloud_preference, "cloud_preference", 32
            ).lower(),
            evidence_ids=evidence_ids,
        )


def create_internal_pilot_plan(request: PilotDiscoveryRequest) -> dict[str, Any]:
    """Create a detailed, non-mutating internal pilot plan."""
    normalized = request.normalized()
    if normalized.workflow_type not in WORKFLOW_STEPS:
        raise ValueError(
            f"workflow_type must be one of: {', '.join(sorted(WORKFLOW_STEPS))}"
        )
    stack = recommend_stack(
        StackAdvisorRequest(
            workflow_type=normalized.workflow_type,
            integration_surface=normalized.integration_surface,
            risk_level=normalized.risk_level,
            team_profile="mixed",
            cloud_preference=normalized.cloud_preference,
            enterprise_data=True,
            personalization=False,
            external_actions=True,
            max_time_to_value_days=7,
        )
    )
    monthly_cases = normalized.weekly_volume * 4.33
    baseline_hours = monthly_cases * normalized.minutes_per_case / 60
    monthly_labor_cost = baseline_hours * normalized.loaded_hourly_cost_usd
    estimated_hours_saved = baseline_hours * normalized.target_time_reduction_pct / 100
    estimated_capacity_value = estimated_hours_saved * normalized.loaded_hourly_cost_usd
    success_gain = normalized.target_success_rate - normalized.baseline_success_rate

    request_dict = asdict(normalized)
    request_dict["evidence_ids"] = list(normalized.evidence_ids)
    identity = json.dumps(request_dict, sort_keys=True, separators=(",", ":"))
    pilot_id = sha256(f"internal-pilot-v1|{identity}".encode("utf-8")).hexdigest()

    return {
        "pilot_id": pilot_id,
        "schema_version": "1.0",
        "stage": "INTERNAL_STAGING",
        "status": "PLANNED",
        "request": request_dict,
        "discovery": {
            "problem_statement": normalized.business_outcome,
            "owner": normalized.process_owner,
            "current_monthly_cases": round(monthly_cases),
            "current_monthly_hours": round(baseline_hours, 1),
            "current_monthly_labor_cost_usd": round(monthly_labor_cost, 2),
            "target_success_gain_points": round(success_gain, 2),
            "estimated_monthly_hours_saved": round(estimated_hours_saved, 1),
            "estimated_monthly_capacity_value_usd": round(estimated_capacity_value, 2),
            "assumptions": [
                "4.33 weeks per month",
                "capacity value is not booked revenue",
                "social evidence supports prioritization but does not establish causation",
            ],
        },
        "workflow": {
            "operating_mode": "DRAFT_AND_RECOMMEND_ONLY",
            "steps": [
                {"sequence": index, **step}
                for index, step in enumerate(WORKFLOW_STEPS[normalized.workflow_type], 1)
            ],
            "prohibited_actions": [
                "automatic external publishing",
                "automatic purchases or budget changes",
                "collection of customer PII",
                "credential or permission changes",
            ],
        },
        "architecture": stack,
        "seven_day_plan": [
            {"day": 1, "focus": "Baseline", "exit": "Owner confirms workflow, baseline, evidence, and exclusions."},
            {"day": 2, "focus": "Contracts", "exit": "Inputs, outputs, identities, and action policies are typed."},
            {"day": 3, "focus": "Golden path", "exit": "One deterministic happy path runs on synthetic fixtures."},
            {"day": 4, "focus": "AI boundary", "exit": "AI-only steps pass grounded quality and refusal tests."},
            {"day": 5, "focus": "Exceptions", "exit": "Retries, duplicate protection, approvals, and kill switch pass."},
            {"day": 6, "focus": "Shadow run", "exit": "Pilot runs without external side effects and records scorecard data."},
            {"day": 7, "focus": "Outcome review", "exit": "Owner chooses GO, ITERATE, or STOP using agreed thresholds."},
        ],
        "scorecard": {
            "primary": {
                "metric": "success_rate",
                "baseline": normalized.baseline_success_rate,
                "target": normalized.target_success_rate,
                "unit": "percent",
            },
            "secondary": [
                {"metric": "cycle_time", "target_change_pct": -normalized.target_time_reduction_pct},
                {"metric": "human_review_rate", "target": "observe_then_set"},
                {"metric": "cost_per_completed_case", "target": "below_baseline"},
                {"metric": "evidence_coverage", "target": 100, "unit": "percent"},
                {"metric": "unauthorized_external_actions", "target": 0},
            ],
            "decision_rule": {
                "GO": "primary target met, zero unauthorized actions, and evidence coverage is 100%",
                "ITERATE": "quality improves but one non-safety target misses",
                "STOP": "unauthorized action, material quality regression, or no measurable benefit",
            },
        },
        "staging_controls": [
            "synthetic or non-sensitive data only",
            "secrets stored outside source control",
            "read-only integrations by default",
            "human approval before external action",
            "quota and spend caps",
            "collector and agent kill switch",
            "immutable evidence and action log",
        ],
        "evidence_ids": list(normalized.evidence_ids),
        "approval_required": True,
        "mutation": "none",
    }
