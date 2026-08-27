"""Synthetic, governed staging benchmark for recommendation rerankers.

These cases deliberately contain no customer identifiers, raw social content,
or external API calls. They establish a small regression gate before a larger
human-labeled evaluation set is introduced.
"""

from __future__ import annotations

from typing import Any

from .recommendation_context import RecommendationContextRequest, compile_recommendation_context


def _evidence(identifier: str, platform: str, score: float) -> dict[str, Any]:
    host = "www.youtube.com/watch?v=" if platform == "youtube" else "x.com/example/status/"
    return {
        "evidence_id": identifier,
        "rank": 1,
        "rank_score": score,
        "platform": platform,
        "title": f"Governed evidence {identifier}",
        "source_url": f"https://{host}{identifier}",
        "why_ranked": ["Strong match to the decision"],
    }


def _candidate(identifier: str, *, channels: list[str] | None = None) -> dict[str, Any]:
    return {
        "candidate_id": identifier,
        "candidate_type": "creative",
        "title": f"Candidate {identifier}",
        "description": "A bounded test candidate with an observable outcome.",
        "channels": channels or ["linkedin"],
        "expected_outcome": "Improve qualified enterprise demand.",
    }


def staging_benchmark_cases() -> list[dict[str, Any]]:
    """Return five repeatable golden cases for the deterministic baseline."""
    cases = []
    for number, signal in enumerate(("proof", "workshop", "migration", "security", "analytics"), start=1):
        winner = f"{signal}-winner"
        context = compile_recommendation_context(RecommendationContextRequest(
            tenant_id="staging",
            decision_id=f"benchmark-{number}",
            business_objective="Increase qualified enterprise AI learning demand.",
            market="San Francisco",
            locale="en-US",
            primary_metric="qualified_demo_rate",
            ranked_evidence=[_evidence(f"ev-{number}", "youtube" if number % 2 else "x", 92 - number)],
            candidates=[_candidate(winner), _candidate(f"{signal}-alternative")],
            outcome_signals=[{
                "candidate_id": winner,
                "metric": "qualified_demo_rate",
                "value": 0.15,
                "unit": "ratio",
                "observed_at": "2026-08-27T12:00:00+00:00",
                "confidence": "directional",
            }],
        ))
        cases.append({"case_id": f"staging-{signal}", "context": context, "expected_candidate_ids": [winner]})
    return cases
