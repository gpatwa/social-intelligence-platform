"""CLI for offline recommendation reranking and fixture evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .batch_reranker import evaluate_reranker, rerank_context


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline batch reranker")
    commands = parser.add_subparsers(dest="command", required=True)
    rerank = commands.add_parser("rerank", help="Rerank one recommendation-context-v1 JSON object")
    rerank.add_argument("input", type=Path)
    evaluate = commands.add_parser("evaluate", help="Evaluate a JSON array or {cases: [...]} fixture")
    evaluate.add_argument("input", type=Path)
    args = parser.parse_args()
    payload = _load(args.input)
    if args.command == "rerank":
        if not isinstance(payload, dict):
            raise ValueError("rerank input must be a JSON object")
        result = rerank_context(payload)
    else:
        cases = payload.get("cases") if isinstance(payload, dict) else payload
        if not isinstance(cases, list):
            raise ValueError("evaluation input must be an array or an object with cases")
        result = evaluate_reranker(cases)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    main()
