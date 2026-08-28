"""Governed human review and outcome artifacts for offline recommendations.

This module intentionally does not persist records or execute external actions.
It compiles validated, idempotent artifacts for the Databricks control-plane
tables.  A reviewer may approve, edit, or reject a bounded rerank; only an
approved or edited review may receive a measured outcome later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import re
from typing import Any, Mapping


REVIEW_VERSION = "recommendation-review-v1"
OUTCOME_VERSION = "recommendation-outcome-v1"
DECISIONS = frozenset({"APPROVE", "EDIT", "REJECT"})
REVIEW_STATUSES = {
    "APPROVE": "APPROVED_FOR_HANDOFF",
    "EDIT": "EDITED_FOR_HANDOFF",
    "REJECT": "REJECTED",
}
CONFIDENCE_LEVELS = frozenset({"DIRECTIONAL", "MEASURED"})
ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _text(value: object, field: str, maximum: int = 500) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum or any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{field} must be printable and between 1 and {maximum} characters")
    return normalized


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    return float(value)


def _timestamp(value: object, field: str) -> str:
    normalized = _text(value, field, 64)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.isoformat()


def _actor(value: object, field: str) -> str:
    normalized = _text(value, field, 128)
    if "@" in normalized or not ACTOR_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field} must be an opaque actor identifier, not an email address")
    return normalized


def _validated_rerank(rerank: Mapping[str, Any], tenant_id: str) -> dict[str, Any]:
    if not isinstance(rerank, Mapping):
        raise ValueError("rerank must be an object")
    if rerank.get("status") != "PROPOSED" or rerank.get("mode") != "OFFLINE":
        raise ValueError("rerank must be an offline PROPOSED artifact")
    if rerank.get("mutation") != "none" or rerank.get("approval_required") is not True:
        raise ValueError("rerank must be non-mutating and require approval")
    if _text(rerank.get("tenant_id"), "rerank.tenant_id", 63) != tenant_id:
        raise ValueError("rerank tenant_id must match review tenant_id")
    ranked = rerank.get("ranked_candidates")
    if not isinstance(ranked, list) or not ranked:
        raise ValueError("rerank.ranked_candidates must be a non-empty list")
    normalized_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in ranked:
        if not isinstance(item, Mapping):
            raise ValueError("rerank.ranked_candidates items must be objects")
        candidate_id = _text(item.get("candidate_id"), "candidate_id", 256)
        citations = sorted({_text(value, "citation", 256) for value in item.get("citations", [])})
        if candidate_id in seen or not citations:
            raise ValueError("rerank candidates must be unique and cited")
        seen.add(candidate_id)
        normalized_items.append({
            "candidate_id": candidate_id,
            "rank": int(_number(item.get("rank"), "rank")),
            "score": round(_number(item.get("score"), "score"), 2),
            "citations": citations,
        })
    primary = _text(rerank.get("primary_candidate_id"), "primary_candidate_id", 256)
    if primary not in seen:
        raise ValueError("rerank.primary_candidate_id must be ranked")
    return {
        "rerank_id": _text(rerank.get("rerank_id"), "rerank_id", 64),
        "context_id": _text(rerank.get("context_id"), "context_id", 64),
        "decision_id": _text(rerank.get("decision_id"), "decision_id", 256),
        "primary_candidate_id": primary,
        "ranked_candidates": normalized_items,
    }


@dataclass(frozen=True)
class RecommendationReviewRequest:
    tenant_id: str
    rerank: Mapping[str, Any]
    decision: str
    reviewer_id: str
    decision_reason: str
    reviewed_at: str
    idempotency_key: str
    selected_candidate_id: str | None = None
    edited_brief: str | None = None
    reviewer_note: str | None = None


def create_recommendation_review(request: RecommendationReviewRequest) -> dict[str, Any]:
    """Compile an append-safe, human decision artifact from a bounded rerank."""
    tenant_id = _text(request.tenant_id, "tenant_id", 63)
    rerank = _validated_rerank(request.rerank, tenant_id)
    decision = _text(request.decision, "decision", 16).upper()
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of: {', '.join(sorted(DECISIONS))}")
    reviewer_id = _actor(request.reviewer_id, "reviewer_id")
    reviewed_at = _timestamp(request.reviewed_at, "reviewed_at")
    idempotency_key = _text(request.idempotency_key, "idempotency_key", 256)
    reason = _text(request.decision_reason, "decision_reason", 500)
    candidate_ids = {item["candidate_id"] for item in rerank["ranked_candidates"]}
    selected = _text(request.selected_candidate_id, "selected_candidate_id", 256) if request.selected_candidate_id else None
    if decision == "REJECT":
        if selected:
            raise ValueError("REJECT reviews cannot select a candidate")
        if request.edited_brief:
            raise ValueError("REJECT reviews cannot include an edited_brief")
    else:
        selected = selected or rerank["primary_candidate_id"]
        if selected not in candidate_ids:
            raise ValueError("selected_candidate_id must be present in rerank.ranked_candidates")
        if decision == "EDIT" and not request.edited_brief:
            raise ValueError("EDIT reviews require edited_brief")
    edited_brief = _text(request.edited_brief, "edited_brief", 1000) if request.edited_brief else None
    reviewer_note = _text(request.reviewer_note, "reviewer_note", 1000) if request.reviewer_note else None
    selected_item = next((item for item in rerank["ranked_candidates"] if item["candidate_id"] == selected), None)
    review_id = sha256(
        f"{REVIEW_VERSION}|{tenant_id}|{rerank['rerank_id']}|{idempotency_key}".encode("utf-8")
    ).hexdigest()
    handoff_ready = decision in {"APPROVE", "EDIT"}
    return {
        "review_id": review_id,
        "schema_version": "1.0",
        "review_version": REVIEW_VERSION,
        "tenant_id": tenant_id,
        "rerank_id": rerank["rerank_id"],
        "context_id": rerank["context_id"],
        "decision_id": rerank["decision_id"],
        "decision": decision,
        "status": REVIEW_STATUSES[decision],
        "reviewer_id": reviewer_id,
        "decision_reason": reason,
        "reviewer_note": reviewer_note,
        "reviewed_at": reviewed_at,
        "idempotency_key": idempotency_key,
        "selected_candidate_id": selected,
        "selected_candidate_rank": selected_item["rank"] if selected_item else None,
        "evidence_ids": selected_item["citations"] if selected_item else [],
        "edited_brief": edited_brief,
        "handoff": {
            "state": "READY_FOR_MANUAL_HANDOFF" if handoff_ready else "NOT_REQUESTED",
            "external_action_permitted": False,
            "allowed_next_step": (
                "Create a human-reviewed brief or experiment draft."
                if handoff_ready else "Record rejection feedback and evaluate a new draft."
            ),
        },
        "approval_required": False,
        "causality_claim": "none",
        "mutation": "none",
    }


@dataclass(frozen=True)
class RecommendationOutcomeRequest:
    tenant_id: str
    review: Mapping[str, Any]
    metric_name: str
    observed_value: float
    unit: str
    observed_at: str
    measurement_source: str
    reported_by: str
    idempotency_key: str
    measurement_window_days: int = 7
    baseline_value: float | None = None
    confidence: str = "DIRECTIONAL"


def record_recommendation_outcome(request: RecommendationOutcomeRequest) -> dict[str, Any]:
    """Compile an outcome observation attached only to an approved review."""
    tenant_id = _text(request.tenant_id, "tenant_id", 63)
    review = request.review
    if not isinstance(review, Mapping) or review.get("review_version") != REVIEW_VERSION:
        raise ValueError("review must be a recommendation-review-v1 artifact")
    if _text(review.get("tenant_id"), "review.tenant_id", 63) != tenant_id:
        raise ValueError("review tenant_id must match outcome tenant_id")
    if review.get("status") not in {"APPROVED_FOR_HANDOFF", "EDITED_FOR_HANDOFF"}:
        raise ValueError("outcomes may be recorded only for approved or edited reviews")
    if review.get("mutation") != "none":
        raise ValueError("review must be non-mutating")
    window = request.measurement_window_days
    if not isinstance(window, int) or isinstance(window, bool) or not 1 <= window <= 90:
        raise ValueError("measurement_window_days must be an integer between 1 and 90")
    confidence = _text(request.confidence, "confidence", 32).upper()
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"confidence must be one of: {', '.join(sorted(CONFIDENCE_LEVELS))}")
    baseline = _number(request.baseline_value, "baseline_value") if request.baseline_value is not None else None
    observed = _number(request.observed_value, "observed_value")
    idempotency_key = _text(request.idempotency_key, "idempotency_key", 256)
    review_id = _text(review.get("review_id"), "review_id", 64)
    metric_name = _text(request.metric_name, "metric_name", 128)
    outcome_id = sha256(
        f"{OUTCOME_VERSION}|{tenant_id}|{review_id}|{metric_name}|{idempotency_key}".encode("utf-8")
    ).hexdigest()
    return {
        "outcome_id": outcome_id,
        "schema_version": "1.0",
        "outcome_version": OUTCOME_VERSION,
        "tenant_id": tenant_id,
        "review_id": review_id,
        "rerank_id": _text(review.get("rerank_id"), "review.rerank_id", 64),
        "context_id": _text(review.get("context_id"), "review.context_id", 64),
        "decision_id": _text(review.get("decision_id"), "review.decision_id", 256),
        "candidate_id": _text(review.get("selected_candidate_id"), "review.selected_candidate_id", 256),
        "metric_name": metric_name,
        "observed_value": observed,
        "baseline_value": baseline,
        "unit": _text(request.unit, "unit", 64),
        "measurement_window_days": window,
        "measurement_source": _text(request.measurement_source, "measurement_source", 128),
        "observed_at": _timestamp(request.observed_at, "observed_at"),
        "reported_by": _actor(request.reported_by, "reported_by"),
        "idempotency_key": idempotency_key,
        "confidence": confidence,
        "attribution": "OBSERVATIONAL_ONLY",
        "causality_claim": "none",
        "mutation": "none",
    }


def summarize_recommendation_reviews(
    reviews: list[Mapping[str, Any]], outcomes: list[Mapping[str, Any]]
) -> dict[str, Any]:
    """Return a deterministic internal-pilot scorecard from persisted artifacts."""
    total = len(reviews)
    approved = sum(item.get("status") == "APPROVED_FOR_HANDOFF" for item in reviews)
    edited = sum(item.get("status") == "EDITED_FOR_HANDOFF" for item in reviews)
    rejected = sum(item.get("status") == "REJECTED" for item in reviews)
    approved_ids = {str(item.get("review_id", "")) for item in reviews if item.get("status") in {"APPROVED_FOR_HANDOFF", "EDITED_FOR_HANDOFF"}}
    measured = [item for item in outcomes if str(item.get("review_id", "")) in approved_ids]
    return {
        "scorecard_version": "recommendation-review-scorecard-v1",
        "reviews_total": total,
        "approved_total": approved,
        "edited_total": edited,
        "rejected_total": rejected,
        "acceptance_rate": round((approved + edited) / total, 4) if total else 0.0,
        "outcomes_total": len(measured),
        "outcome_coverage_rate": round(len({str(item.get("review_id", "")) for item in measured}) / len(approved_ids), 4) if approved_ids else 0.0,
        "stage": "INTERNAL_PILOT",
        "automation_status": "DISABLED",
    }
