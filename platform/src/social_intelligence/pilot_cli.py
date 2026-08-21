"""CLI for internal pilot planning and evidence ranking."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evidence_ranking import EvidenceCandidate, rank_evidence
from .pilot_workspace import PilotDiscoveryRequest, create_internal_pilot_plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a non-mutating Social Intelligence internal pilot artifact"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="Create a seven-day internal pilot plan")
    plan.add_argument("workflow_type", choices=["lead_response", "document_processing", "follow_up", "crm_reactivation", "internal_reporting"])
    plan.add_argument("--tenant-id", default="internal-pilot")
    plan.add_argument("--business-outcome", required=True)
    plan.add_argument("--process-owner", required=True)
    plan.add_argument("--weekly-volume", type=int, required=True)
    plan.add_argument("--minutes-per-case", type=float, required=True)
    plan.add_argument("--loaded-hourly-cost-usd", type=float, required=True)
    plan.add_argument("--baseline-success-rate", type=float, required=True)
    plan.add_argument("--target-success-rate", type=float, required=True)
    plan.add_argument("--target-time-reduction-pct", type=float, default=35)
    plan.add_argument("--integration-surface", choices=["api", "mixed", "legacy_ui"], default="mixed")
    plan.add_argument("--risk-level", choices=["low", "moderate", "high"], default="moderate")
    plan.add_argument("--cloud-preference", choices=["neutral", "databricks", "microsoft", "google", "aws"], default="databricks")
    plan.add_argument("--evidence-id", action="append", default=[])

    ranking = subparsers.add_parser("rank", help="Rank normalized evidence candidates")
    ranking.add_argument("input", type=Path, help="JSON array of evidence candidates")
    ranking.add_argument("--tenant-id", default="internal-pilot")
    ranking.add_argument("--decision-id", required=True)
    ranking.add_argument("--limit", type=int, default=5)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "plan":
        result = create_internal_pilot_plan(
            PilotDiscoveryRequest(
                tenant_id=args.tenant_id,
                workflow_type=args.workflow_type,
                business_outcome=args.business_outcome,
                process_owner=args.process_owner,
                weekly_volume=args.weekly_volume,
                minutes_per_case=args.minutes_per_case,
                loaded_hourly_cost_usd=args.loaded_hourly_cost_usd,
                baseline_success_rate=args.baseline_success_rate,
                target_success_rate=args.target_success_rate,
                target_time_reduction_pct=args.target_time_reduction_pct,
                integration_surface=args.integration_surface,
                risk_level=args.risk_level,
                cloud_preference=args.cloud_preference,
                evidence_ids=tuple(args.evidence_id),
            )
        )
    else:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("rank input must be a JSON array")
        result = rank_evidence(
            [
                EvidenceCandidate(
                    tenant_id=args.tenant_id,
                    decision_id=args.decision_id,
                    **item,
                )
                for item in payload
            ],
            limit=args.limit,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
