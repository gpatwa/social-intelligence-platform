"""CLI for compile-only human review and outcome artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .recommendation_review import (
    RecommendationOutcomeRequest,
    RecommendationReviewRequest,
    create_recommendation_review,
    record_recommendation_outcome,
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile non-mutating recommendation review artifacts")
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review", help="Compile an approve, edit, or reject review artifact")
    review.add_argument("input", type=Path)
    outcome = commands.add_parser("record-outcome", help="Compile an outcome observation for an approved review")
    outcome.add_argument("input", type=Path)
    args = parser.parse_args()
    payload = _load(args.input)
    if args.command == "review":
        result = create_recommendation_review(RecommendationReviewRequest(**payload))
    else:
        result = record_recommendation_outcome(RecommendationOutcomeRequest(**payload))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    main()
