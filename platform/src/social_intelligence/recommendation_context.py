"""Compile a bounded, reviewable context for a future recommendation reranker.

This is deliberately a deterministic preparation step.  It never calls a model,
retrieves external data, ranks candidates, or changes a customer system.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


CONTEXT_VERSION = "recommendation-context-v1"
ACTION_POLICY = "DRAFT_AND_RECOMMEND_ONLY"
ALLOWED_CANDIDATE_TYPES = frozenset({"product", "creative", "channel", "ai_workflow"})
MAX_EVIDENCE_ITEMS = 20


def _text(value: object, field: str, maximum: int = 500) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum or any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{field} must be printable and between 1 and {maximum} characters")
    return normalized


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    return float(value)


def _https_url(value: object, field: str = "source_url") -> str:
    url = _text(value, field, 2048)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"{field} must be an absolute HTTPS URL without credentials")
    return url


def _string_list(values: Sequence[object], field: str, maximum_items: int = 20) -> tuple[str, ...]:
    if len(values) > maximum_items:
        raise ValueError(f"{field} may contain at most {maximum_items} values")
    return tuple(sorted({_text(value, field, 256) for value in values}))


@dataclass(frozen=True)
class RecommendationContextRequest:
    tenant_id: str
    decision_id: str
    business_objective: str
    market: str
    locale: str
    primary_metric: str
    ranked_evidence: Sequence[Mapping[str, Any]]
    candidates: Sequence[Mapping[str, Any]]
    outcome_signals: Sequence[Mapping[str, Any]] = ()
    allowed_channels: Sequence[str] = ()
    excluded_candidate_ids: Sequence[str] = ()
    max_evidence_items: int = 5
    action_policy: str = ACTION_POLICY


def _evidence(item: Mapping[str, Any]) -> dict[str, Any]:
    platform = _text(item.get("platform"), "evidence.platform", 64).lower()
    evidence = {
        "evidence_id": _text(item.get("evidence_id"), "evidence_id", 256),
        "rank": int(_number(item.get("rank"), "evidence.rank")),
        "rank_score": round(_number(item.get("rank_score"), "evidence.rank_score"), 2),
        "platform": platform,
        "title": _text(item.get("title"), "evidence.title", 500),
        "source_url": _https_url(item.get("source_url")),
        "why_ranked": list(_string_list(item.get("why_ranked", ()), "evidence.why_ranked", 3)),
    }
    if evidence["rank"] < 1:
        raise ValueError("evidence.rank must be at least 1")
    return evidence


def _candidate(item: Mapping[str, Any]) -> dict[str, Any]:
    candidate_type = _text(item.get("candidate_type"), "candidate_type", 64).lower()
    if candidate_type not in ALLOWED_CANDIDATE_TYPES:
        raise ValueError(f"candidate_type must be one of: {', '.join(sorted(ALLOWED_CANDIDATE_TYPES))}")
    eligible = item.get("eligible", True)
    if not isinstance(eligible, bool):
        raise ValueError("candidate.eligible must be a boolean")
    return {
        "candidate_id": _text(item.get("candidate_id"), "candidate_id", 256),
        "candidate_type": candidate_type,
        "title": _text(item.get("title"), "candidate.title", 500),
        "description": _text(item.get("description"), "candidate.description", 1000),
        "eligible": eligible,
        "channels": list(_string_list(item.get("channels", ()), "candidate.channels")),
        "expected_outcome": _text(item.get("expected_outcome"), "candidate.expected_outcome", 256),
        "constraints": list(_string_list(item.get("constraints", ()), "candidate.constraints")),
    }


def _outcome(item: Mapping[str, Any], candidate_ids: set[str]) -> dict[str, Any]:
    candidate_id = _text(item.get("candidate_id"), "outcome.candidate_id", 256)
    if candidate_id not in candidate_ids:
        raise ValueError("outcome.candidate_id must refer to a supplied candidate")
    return {
        "candidate_id": candidate_id,
        "metric": _text(item.get("metric"), "outcome.metric", 128),
        "value": _number(item.get("value"), "outcome.value"),
        "unit": _text(item.get("unit"), "outcome.unit", 64),
        "observed_at": _text(item.get("observed_at"), "outcome.observed_at", 64),
        "confidence": _text(item.get("confidence", "directional"), "outcome.confidence", 64).lower(),
    }


def compile_recommendation_context(request: RecommendationContextRequest) -> dict[str, Any]:
    """Create a stable, constrained context packet for offline/batch reranking."""
    if not isinstance(request.max_evidence_items, int) or isinstance(request.max_evidence_items, bool) or not 1 <= request.max_evidence_items <= MAX_EVIDENCE_ITEMS:
        raise ValueError(f"max_evidence_items must be an integer between 1 and {MAX_EVIDENCE_ITEMS}")
    if request.action_policy != ACTION_POLICY:
        raise ValueError(f"action_policy must be {ACTION_POLICY}")

    tenant_id = _text(request.tenant_id, "tenant_id", 63)
    decision_id = _text(request.decision_id, "decision_id", 256)
    business_context = {
        "business_objective": _text(request.business_objective, "business_objective", 500),
        "market": _text(request.market, "market", 120),
        "locale": _text(request.locale, "locale", 32),
        "primary_metric": _text(request.primary_metric, "primary_metric", 120),
    }
    evidence = [_evidence(item) for item in request.ranked_evidence]
    if not evidence:
        raise ValueError("at least one ranked evidence item is required")
    deduplicated_evidence = {item["evidence_id"]: item for item in evidence}
    evidence = sorted(deduplicated_evidence.values(), key=lambda item: (item["rank"], -item["rank_score"], item["evidence_id"]))[: request.max_evidence_items]

    candidates = [_candidate(item) for item in request.candidates]
    if not candidates:
        raise ValueError("at least one candidate is required")
    candidate_ids = [item["candidate_id"] for item in candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate_id values must be unique")
    allowed_channels = list(_string_list(request.allowed_channels, "allowed_channels"))
    excluded_ids = set(_string_list(request.excluded_candidate_ids, "excluded_candidate_ids"))
    eligible, excluded = [], []
    for candidate in sorted(candidates, key=lambda item: item["candidate_id"]):
        reason = None
        if not candidate["eligible"]:
            reason = "candidate_marked_ineligible"
        elif candidate["candidate_id"] in excluded_ids:
            reason = "explicitly_excluded"
        elif allowed_channels and not set(candidate["channels"]).intersection(allowed_channels):
            reason = "no_allowed_channel"
        if reason:
            excluded.append({"candidate_id": candidate["candidate_id"], "reason": reason})
        else:
            eligible.append(candidate)
    if not eligible:
        raise ValueError("no eligible candidates remain after policy filtering")

    candidate_id_set = set(candidate_ids)
    outcomes = sorted(
        (_outcome(item, candidate_id_set) for item in request.outcome_signals),
        key=lambda item: (item["candidate_id"], item["metric"], item["observed_at"]),
    )
    identity = {
        "tenant_id": tenant_id,
        "decision_id": decision_id,
        "business_context": business_context,
        "evidence": evidence,
        "candidates": eligible,
        "outcomes": outcomes,
        "allowed_channels": allowed_channels,
    }
    context_id = sha256((CONTEXT_VERSION + "|" + repr(identity)).encode("utf-8")).hexdigest()
    return {
        "context_id": context_id,
        "schema_version": "1.0",
        "context_version": CONTEXT_VERSION,
        "tenant_id": tenant_id,
        "decision_id": decision_id,
        "stage": "INTERNAL_STAGING",
        "status": "READY_FOR_RERANK",
        "business_context": business_context,
        "evidence": evidence,
        "candidate_set": eligible,
        "excluded_candidates": excluded,
        "outcome_signals": outcomes,
        "reranking_context": {
            "candidate_scope": "Rank only candidate_set; do not invent products, channels, or actions.",
            "evidence_requirement": "Cite supplied evidence_id and source_url; do not claim causality.",
            "decision_policy": ACTION_POLICY,
        },
        "guardrails": [
            "No external data retrieval or tool execution occurred.",
            "No PII or raw social content is included in this context contract.",
            "Any future recommendation remains draft-only and requires human approval.",
        ],
        "approval_required": True,
        "causality_claim": "none",
        "mutation": "none",
    }
