"""Independent receipt attester for deterministic evidence rankings."""

from __future__ import annotations

from typing import Any, Mapping

from social_intelligence.evidence_ranking import EvidenceCandidate, rank_evidence


def attest(receipt: Mapping[str, Any]) -> bool:
    candidates = receipt.get("candidates")
    if not isinstance(candidates, list):
        return False
    try:
        expected = rank_evidence(
            [EvidenceCandidate(**candidate) for candidate in candidates],
            limit=receipt.get("limit", 5),
        )
    except (TypeError, ValueError):
        return False
    return all(receipt.get(field) == expected[field] for field in (
        "ranking_id",
        "tenant_id",
        "decision_id",
        "items",
        "score_version",
        "causality_claim",
    ))
