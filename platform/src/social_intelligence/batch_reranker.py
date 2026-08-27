"""Offline, bounded recommendation reranking with verifiable evidence citations.

This module deliberately provides a deterministic baseline and a narrow adapter
protocol. Provider SDKs belong outside this package; every provider response is
validated against the same candidate and evidence boundaries before use.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Protocol, Sequence


RERANKER_VERSION = "batch-reranker-v1"
MODE = "OFFLINE"


def _text(value: object, field: str, maximum: int = 500) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum or any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{field} must be printable and between 1 and {maximum} characters")
    return normalized


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    return float(value)


class RerankerAdapter(Protocol):
    """Provider boundary. Implementations must return structured candidate rankings only."""

    provider: str
    model: str

    def rerank(self, context: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]: ...


def _validate_context(context: Mapping[str, Any]) -> dict[str, Any]:
    if context.get("context_version") != "recommendation-context-v1":
        raise ValueError("context_version must be recommendation-context-v1")
    if context.get("status") != "READY_FOR_RERANK":
        raise ValueError("context must be READY_FOR_RERANK")
    if context.get("mutation") != "none" or context.get("approval_required") is not True:
        raise ValueError("context must be non-mutating and require approval")
    normalized = dict(context)
    normalized["context_id"] = _text(context.get("context_id"), "context_id", 128)
    normalized["tenant_id"] = _text(context.get("tenant_id"), "tenant_id", 63)
    normalized["decision_id"] = _text(context.get("decision_id"), "decision_id", 256)
    evidence = context.get("evidence")
    candidates = context.get("candidate_set")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("context.evidence must be a non-empty list")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("context.candidate_set must be a non-empty list")
    evidence_ids = {_text(item.get("evidence_id"), "evidence_id", 256) for item in evidence if isinstance(item, Mapping)}
    candidate_ids = {_text(item.get("candidate_id"), "candidate_id", 256) for item in candidates if isinstance(item, Mapping)}
    if len(evidence_ids) != len(evidence) or len(candidate_ids) != len(candidates):
        raise ValueError("context evidence and candidate IDs must be unique")
    normalized["evidence"] = [dict(item) for item in evidence]
    normalized["candidate_set"] = [dict(item) for item in candidates]
    normalized["outcome_signals"] = [dict(item) for item in context.get("outcome_signals", [])]
    return normalized


def structured_rerank_request(context: Mapping[str, Any]) -> dict[str, Any]:
    """Return provider-neutral structured input, not a provider prompt transcript."""
    checked = _validate_context(context)
    return {
        "task": "rank_supplied_candidates",
        "contract_version": RERANKER_VERSION,
        "constraints": [
            "Rank only candidate_set; never invent a candidate, channel, action, or claim.",
            "Each ranked candidate must cite one or more supplied evidence IDs.",
            "Do not claim causality from observational evidence.",
            "Return structured output only; this is an offline draft, not an activation request.",
        ],
        "context": checked,
    }


@dataclass(frozen=True)
class DeterministicOfflineReranker:
    """Safe baseline used for staging, fixtures, and regression evaluation."""

    provider: str = "deterministic"
    model: str = "offline-baseline-v1"

    def rerank(self, context: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
        checked = _validate_context(context)
        evidence = sorted(
            checked["evidence"], key=lambda item: (int(item["rank"]), -float(item["rank_score"]), item["evidence_id"])
        )
        citations = [item["evidence_id"] for item in evidence[:3]]
        evidence_component = round(sum(float(item["rank_score"]) for item in evidence[:3]) / min(len(evidence), 3) * 0.75, 2)
        outcome_counts: dict[str, int] = {}
        for signal in checked["outcome_signals"]:
            candidate_id = str(signal.get("candidate_id", "")).strip()
            if candidate_id:
                outcome_counts[candidate_id] = outcome_counts.get(candidate_id, 0) + 1
        results = []
        for candidate in checked["candidate_set"]:
            candidate_id = candidate["candidate_id"]
            historical_component = min(15.0, 7.5 * outcome_counts.get(candidate_id, 0))
            channel_component = 10.0 if candidate.get("channels") else 0.0
            score = round(min(100.0, evidence_component + historical_component + channel_component), 2)
            results.append({
                "candidate_id": candidate_id,
                "score": score,
                "citations": citations,
                "rationale": "Ranked from supplied evidence strength, governed outcome-support count, and eligible channel coverage.",
                "score_components": {
                    "evidence": evidence_component,
                    "outcome_support": historical_component,
                    "channel_coverage": channel_component,
                },
            })
        return sorted(results, key=lambda item: (-item["score"], item["candidate_id"]))


def _normalize_ranked_items(
    items: Sequence[Mapping[str, Any]], context: Mapping[str, Any]
) -> list[dict[str, Any]]:
    candidate_ids = {item["candidate_id"] for item in context["candidate_set"]}
    evidence_ids = {item["evidence_id"] for item in context["evidence"]}
    if len(items) != len(candidate_ids):
        raise ValueError("reranker must return every eligible candidate exactly once")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        candidate_id = _text(item.get("candidate_id"), "candidate_id", 256)
        if candidate_id not in candidate_ids or candidate_id in seen:
            raise ValueError("reranker returned an unknown or duplicate candidate_id")
        seen.add(candidate_id)
        citations = sorted({_text(value, "citation", 256) for value in item.get("citations", [])})
        if not citations or not set(citations).issubset(evidence_ids):
            raise ValueError("reranker citations must be supplied evidence IDs")
        score = _number(item.get("score"), "score")
        if not 0 <= score <= 100:
            raise ValueError("score must be between 0 and 100")
        normalized.append({
            "candidate_id": candidate_id,
            "score": round(score, 2),
            "citations": citations,
            "rationale": _text(item.get("rationale"), "rationale", 1000),
            "score_components": dict(item.get("score_components", {})),
        })
    normalized.sort(key=lambda item: (-item["score"], item["candidate_id"]))
    for rank, item in enumerate(normalized, start=1):
        item["rank"] = rank
    return normalized


def rerank_context(context: Mapping[str, Any], adapter: RerankerAdapter | None = None) -> dict[str, Any]:
    """Run one bounded offline reranking and return a draft-only, cited result."""
    checked = _validate_context(context)
    selected = adapter or DeterministicOfflineReranker()
    ranked = _normalize_ranked_items(selected.rerank(checked), checked)
    top = ranked[0]
    identity = "|".join(f"{item['candidate_id']}:{item['rank']}:{item['score']}" for item in ranked)
    rerank_id = sha256(f"{RERANKER_VERSION}|{checked['context_id']}|{selected.provider}|{selected.model}|{identity}".encode("utf-8")).hexdigest()
    return {
        "rerank_id": rerank_id,
        "schema_version": "1.0",
        "reranker_version": RERANKER_VERSION,
        "mode": MODE,
        "context_id": checked["context_id"],
        "tenant_id": checked["tenant_id"],
        "decision_id": checked["decision_id"],
        "provider": selected.provider,
        "model": selected.model,
        "status": "PROPOSED",
        "ranked_candidates": ranked,
        "primary_candidate_id": top["candidate_id"],
        "evidence_ids": sorted({citation for item in ranked for citation in item["citations"]}),
        "guardrails": [
            "All candidates were supplied by recommendation-context-v1.",
            "Every candidate result cites supplied evidence.",
            "Output is offline, draft-only, and requires human approval.",
        ],
        "approval_required": True,
        "causality_claim": "none",
        "mutation": "none",
    }


def evaluate_reranker(cases: Sequence[Mapping[str, Any]], adapter: RerankerAdapter | None = None) -> dict[str, Any]:
    """Evaluate grounding and expected-selection quality on offline fixtures."""
    if not cases:
        raise ValueError("at least one evaluation case is required")
    results = []
    for case in cases:
        case_id = _text(case.get("case_id"), "case_id", 256)
        context = case.get("context")
        if not isinstance(context, Mapping):
            raise ValueError("evaluation case context is required")
        rerank = rerank_context(context, adapter)
        expected = {str(value).strip() for value in case.get("expected_candidate_ids", []) if str(value).strip()}
        selected = rerank["primary_candidate_id"]
        results.append({
            "case_id": case_id,
            "grounded": bool(rerank["evidence_ids"]),
            "candidate_boundary_passed": all(item["citations"] for item in rerank["ranked_candidates"]),
            "expected_selection_passed": selected in expected if expected else None,
            "selected_candidate_id": selected,
        })
    expected_cases = [item for item in results if item["expected_selection_passed"] is not None]
    return {
        "evaluation_version": "batch-reranker-eval-v1",
        "mode": MODE,
        "case_count": len(results),
        "grounding_rate": round(sum(item["grounded"] for item in results) / len(results), 4),
        "candidate_boundary_rate": round(sum(item["candidate_boundary_passed"] for item in results) / len(results), 4),
        "expected_selection_rate": round(sum(item["expected_selection_passed"] for item in expected_cases) / len(expected_cases), 4) if expected_cases else None,
        "cases": results,
        "release_gate": "PASS" if all(item["grounded"] and item["candidate_boundary_passed"] for item in results) else "FAIL",
        "mutation": "none",
    }
