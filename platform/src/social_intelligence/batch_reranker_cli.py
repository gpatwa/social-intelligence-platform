"""CLI for offline recommendation reranking and fixture evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .batch_reranker import (
    DeterministicOfflineReranker,
    OpenAIResponsesReranker,
    evaluate_reranker,
    rerank_context,
)
from .reranker_benchmark import staging_benchmark_cases


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline batch reranker")
    parser.add_argument("--provider", choices=["deterministic", "openai"], default="deterministic")
    parser.add_argument("--model", help="Required for --provider openai; never stored in the result contract")
    commands = parser.add_subparsers(dest="command", required=True)
    rerank = commands.add_parser("rerank", help="Rerank one recommendation-context-v1 JSON object")
    rerank.add_argument("input", type=Path)
    evaluate = commands.add_parser("evaluate", help="Evaluate a JSON array or {cases: [...]} fixture")
    evaluate.add_argument("input", type=Path)
    commands.add_parser("evaluate-staging", help="Evaluate the built-in synthetic staging benchmark")
    args = parser.parse_args()
    if args.provider == "openai" and not args.model:
        parser.error("--model is required when --provider openai")
    adapter = OpenAIResponsesReranker(args.model) if args.provider == "openai" else DeterministicOfflineReranker()
    if args.command == "rerank":
        payload = _load(args.input)
        if not isinstance(payload, dict):
            raise ValueError("rerank input must be a JSON object")
        result = rerank_context(payload, adapter)
    elif args.command == "evaluate":
        payload = _load(args.input)
        cases = payload.get("cases") if isinstance(payload, dict) else payload
        if not isinstance(cases, list):
            raise ValueError("evaluation input must be an array or an object with cases")
        result = evaluate_reranker(cases, adapter)
    else:
        result = evaluate_reranker(staging_benchmark_cases(), adapter)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    main()
