"""Governed campaign experiment and aggregate-measurement artifacts.

Campaign Intelligence v1 deliberately works with aggregate, no-PII counts. It
creates a reviewable experiment brief from a human-approved recommendation,
compares control and treatment observations conservatively, and produces an
outcome signal that a later *offline* rerank may use. It cannot create an ad
audience, activate a campaign, spend budget, or claim causal attribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Mapping


EXPERIMENT_VERSION = "campaign-experiment-v1"
MEASUREMENT_VERSION = "campaign-measurement-v1"
COMPARISON_METHODS = frozenset({"RANDOMIZED_AB_TEST", "HOLDOUT", "PRE_POST"})
ACTOR_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-")


def _text(value: object, field: str, maximum: int = 500) -> str:
    result = str(value or "").strip()
    if not result or len(result) > maximum or any(ord(char) < 32 for char in result):
        raise ValueError(f"{field} must be printable and between 1 and {maximum} characters")
    return result


def _timestamp(value: object, field: str) -> str:
    result = _text(value, field, 64)
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.isoformat()


def _actor(value: object, field: str) -> str:
    result = _text(value, field, 128)
    if "@" in result or any(char not in ACTOR_CHARS for char in result):
        raise ValueError(f"{field} must be an opaque actor identifier, not an email address")
    return result


def _number(value: object, field: str, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < minimum:
        raise ValueError(f"{field} must be a number greater than or equal to {minimum}")
    return float(value)


def _count(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _review(review: Mapping[str, Any], tenant_id: str) -> dict[str, str]:
    if not isinstance(review, Mapping):
        raise ValueError("review must be an object")
    if review.get("review_version") != "recommendation-review-v1":
        raise ValueError("review must be a recommendation-review-v1 artifact")
    if _text(review.get("tenant_id"), "review.tenant_id", 63) != tenant_id:
        raise ValueError("review tenant_id must match experiment tenant_id")
    if review.get("status") not in {"APPROVED_FOR_HANDOFF", "EDITED_FOR_HANDOFF"}:
        raise ValueError("campaign experiments require an approved or edited review")
    if review.get("mutation") != "none" or review.get("handoff", {}).get("external_action_permitted") is not False:
        raise ValueError("review must retain the manual-handoff, non-mutating boundary")
    return {
        "review_id": _text(review.get("review_id"), "review.review_id", 64),
        "rerank_id": _text(review.get("rerank_id"), "review.rerank_id", 64),
        "context_id": _text(review.get("context_id"), "review.context_id", 64),
        "decision_id": _text(review.get("decision_id"), "review.decision_id", 256),
        "candidate_id": _text(review.get("selected_candidate_id"), "review.selected_candidate_id", 256),
    }


@dataclass(frozen=True)
class CampaignExperimentRequest:
    tenant_id: str
    review: Mapping[str, Any]
    campaign_name: str
    channel: str
    business_objective: str
    primary_metric: str
    control_definition: str
    treatment_definition: str
    comparison_method: str
    planned_start_at: str
    planned_end_at: str
    created_by: str
    idempotency_key: str
    target_lift_pct: float = 10.0


def create_campaign_experiment(request: CampaignExperimentRequest) -> dict[str, Any]:
    """Compile a draft experiment. Its activation is always a manual handoff."""
    tenant_id = _text(request.tenant_id, "tenant_id", 63)
    review = _review(request.review, tenant_id)
    method = _text(request.comparison_method, "comparison_method", 32).upper()
    if method not in COMPARISON_METHODS:
        raise ValueError(f"comparison_method must be one of: {', '.join(sorted(COMPARISON_METHODS))}")
    start, end = _timestamp(request.planned_start_at, "planned_start_at"), _timestamp(request.planned_end_at, "planned_end_at")
    if datetime.fromisoformat(end) <= datetime.fromisoformat(start):
        raise ValueError("planned_end_at must be later than planned_start_at")
    idempotency_key = _text(request.idempotency_key, "idempotency_key", 256)
    experiment_id = sha256(f"{EXPERIMENT_VERSION}|{tenant_id}|{review['review_id']}|{idempotency_key}".encode()).hexdigest()
    return {
        "experiment_id": experiment_id,
        "schema_version": "1.0",
        "experiment_version": EXPERIMENT_VERSION,
        "tenant_id": tenant_id,
        **review,
        "campaign_name": _text(request.campaign_name, "campaign_name", 256),
        "channel": _text(request.channel, "channel", 128),
        "business_objective": _text(request.business_objective, "business_objective", 500),
        "primary_metric": _text(request.primary_metric, "primary_metric", 128),
        "control_definition": _text(request.control_definition, "control_definition", 1000),
        "treatment_definition": _text(request.treatment_definition, "treatment_definition", 1000),
        "comparison_method": method,
        "target_lift_pct": _number(request.target_lift_pct, "target_lift_pct", -100.0),
        "planned_start_at": start,
        "planned_end_at": end,
        "created_by": _actor(request.created_by, "created_by"),
        "idempotency_key": idempotency_key,
        "status": "DRAFT",
        "activation": {
            "state": "READY_FOR_MANUAL_HANDOFF",
            "external_action_permitted": False,
            "audience_export_permitted": False,
            "spend_permitted": False,
        },
        "data_policy": "AGGREGATE_METRICS_ONLY_NO_PII",
        "approval_required": True,
        "causality_claim": "none",
        "mutation": "none",
    }


@dataclass(frozen=True)
class CampaignMeasurementRequest:
    tenant_id: str
    experiment: Mapping[str, Any]
    observed_at: str
    measurement_source: str
    reported_by: str
    idempotency_key: str
    control_impressions: int
    treatment_impressions: int
    control_conversions: int
    treatment_conversions: int
    control_value: float = 0.0
    treatment_value: float = 0.0
    control_spend: float = 0.0
    treatment_spend: float = 0.0
    measurement_window_days: int = 7


def _rate(conversions: int, impressions: int) -> float | None:
    return round(conversions / impressions, 8) if impressions else None


def record_campaign_measurement(request: CampaignMeasurementRequest) -> dict[str, Any]:
    """Compile a privacy-safe treatment/control comparison without causal claims."""
    tenant_id = _text(request.tenant_id, "tenant_id", 63)
    experiment = request.experiment
    if not isinstance(experiment, Mapping) or experiment.get("experiment_version") != EXPERIMENT_VERSION:
        raise ValueError("experiment must be a campaign-experiment-v1 artifact")
    if _text(experiment.get("tenant_id"), "experiment.tenant_id", 63) != tenant_id:
        raise ValueError("experiment tenant_id must match measurement tenant_id")
    if experiment.get("mutation") != "none":
        raise ValueError("experiment must be non-mutating")
    window = request.measurement_window_days
    if not isinstance(window, int) or isinstance(window, bool) or not 1 <= window <= 90:
        raise ValueError("measurement_window_days must be an integer between 1 and 90")
    control_i, treatment_i = _count(request.control_impressions, "control_impressions"), _count(request.treatment_impressions, "treatment_impressions")
    control_c, treatment_c = _count(request.control_conversions, "control_conversions"), _count(request.treatment_conversions, "treatment_conversions")
    if not control_i or not treatment_i:
        raise ValueError("control_impressions and treatment_impressions must both be greater than zero")
    if control_c > control_i or treatment_c > treatment_i:
        raise ValueError("conversions cannot exceed impressions")
    control_rate, treatment_rate = _rate(control_c, control_i), _rate(treatment_c, treatment_i)
    rate_lift_pct = round(100 * (treatment_rate - control_rate) / control_rate, 2) if control_rate else None
    target_lift = float(experiment["target_lift_pct"])
    adequate = control_i >= 1000 and treatment_i >= 1000 and control_c >= 25 and treatment_c >= 25
    result = "INSUFFICIENT_DATA" if not adequate else (
        "POSITIVE" if rate_lift_pct is not None and rate_lift_pct >= target_lift else
        "NEGATIVE" if rate_lift_pct is not None and rate_lift_pct < 0 else "INCONCLUSIVE"
    )
    measurement_id = sha256(f"{MEASUREMENT_VERSION}|{tenant_id}|{experiment['experiment_id']}|{_text(request.idempotency_key, 'idempotency_key', 256)}".encode()).hexdigest()
    confidence = "MEASURED" if adequate and experiment["comparison_method"] != "PRE_POST" else "DIRECTIONAL"
    feedback = {
        "candidate_id": _text(experiment.get("candidate_id"), "experiment.candidate_id", 256),
        "metric": "observed_campaign_conversion_lift_pct",
        "value": rate_lift_pct,
        "unit": "percent",
        "observed_at": _timestamp(request.observed_at, "observed_at"),
        "confidence": confidence.lower(),
        "eligible_for_offline_reranking": adequate and rate_lift_pct is not None,
    }
    return {
        "measurement_id": measurement_id,
        "schema_version": "1.0",
        "measurement_version": MEASUREMENT_VERSION,
        "tenant_id": tenant_id,
        "experiment_id": _text(experiment.get("experiment_id"), "experiment.experiment_id", 64),
        "review_id": _text(experiment.get("review_id"), "experiment.review_id", 64),
        "candidate_id": feedback["candidate_id"],
        "comparison_method": experiment["comparison_method"],
        "primary_metric": _text(experiment.get("primary_metric"), "experiment.primary_metric", 128),
        "control": {"impressions": control_i, "conversions": control_c, "value": _number(request.control_value, "control_value"), "spend": _number(request.control_spend, "control_spend"), "conversion_rate": control_rate},
        "treatment": {"impressions": treatment_i, "conversions": treatment_c, "value": _number(request.treatment_value, "treatment_value"), "spend": _number(request.treatment_spend, "treatment_spend"), "conversion_rate": treatment_rate},
        "observed_conversion_rate_lift_pct": rate_lift_pct,
        "result": result,
        "confidence": confidence,
        "measurement_window_days": window,
        "measurement_source": _text(request.measurement_source, "measurement_source", 128),
        "reported_by": _actor(request.reported_by, "reported_by"),
        "observed_at": feedback["observed_at"],
        "idempotency_key": _text(request.idempotency_key, "idempotency_key", 256),
        "ranking_feedback": feedback,
        "data_policy": "AGGREGATE_METRICS_ONLY_NO_PII",
        "attribution": "COMPARATIVE_OBSERVED" if experiment["comparison_method"] != "PRE_POST" else "OBSERVATIONAL_ONLY",
        "causality_claim": "none",
        "mutation": "none",
    }


def measurement_to_outcome_signal(measurement: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bounded signal only when aggregate data cleared the v1 quality gate."""
    if not isinstance(measurement, Mapping) or measurement.get("measurement_version") != MEASUREMENT_VERSION:
        raise ValueError("measurement must be a campaign-measurement-v1 artifact")
    feedback = measurement.get("ranking_feedback")
    if not isinstance(feedback, Mapping) or feedback.get("eligible_for_offline_reranking") is not True:
        raise ValueError("measurement is not eligible for offline reranking feedback")
    if measurement.get("mutation") != "none" or measurement.get("causality_claim") != "none":
        raise ValueError("measurement must preserve non-mutating, non-causal boundaries")
    return {key: feedback[key] for key in ("candidate_id", "metric", "value", "unit", "observed_at", "confidence")}
