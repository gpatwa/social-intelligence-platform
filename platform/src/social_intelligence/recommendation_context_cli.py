"""CLI adapter for the deterministic recommendation-context-v1 compiler."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .recommendation_context import RecommendationContextRequest, compile_recommendation_context


def _request(payload: dict[str, Any]) -> RecommendationContextRequest:
    return RecommendationContextRequest(
        tenant_id=payload["tenant_id"],
        decision_id=payload["decision_id"],
        business_objective=payload["business_objective"],
        market=payload["market"],
        locale=payload["locale"],
        primary_metric=payload["primary_metric"],
        ranked_evidence=payload["ranked_evidence"],
        candidates=payload["candidates"],
        outcome_signals=payload.get("outcome_signals", []),
        allowed_channels=payload.get("allowed_channels", []),
        excluded_candidate_ids=payload.get("excluded_candidate_ids", []),
        max_evidence_items=payload.get("max_evidence_items", 5),
        action_policy=payload.get("action_policy", "DRAFT_AND_RECOMMEND_ONLY"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile recommendation-context-v1")
    parser.add_argument("input", type=Path, help="JSON request matching recommendation-context-request-v1")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    print(json.dumps(compile_recommendation_context(_request(payload)), indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    main()
