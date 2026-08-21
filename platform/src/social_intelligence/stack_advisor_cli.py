"""CLI entry point for the deterministic Agent Stack Advisor."""

from __future__ import annotations

import argparse
import json

from .stack_advisor import StackAdvisorRequest, recommend_stack


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recommend an enterprise AI automation stack")
    parser.add_argument("workflow_type", choices=["lead_response", "document_processing", "follow_up", "crm_reactivation", "internal_reporting"])
    parser.add_argument("--integration-surface", choices=["api", "mixed", "legacy_ui"], default="mixed")
    parser.add_argument("--risk-level", choices=["low", "moderate", "high"], default="moderate")
    parser.add_argument("--team-profile", choices=["business", "mixed", "engineering"], default="mixed")
    parser.add_argument("--cloud-preference", choices=["neutral", "databricks", "microsoft", "google", "aws"], default="neutral")
    parser.add_argument("--no-enterprise-data", action="store_true")
    parser.add_argument("--personalization", action="store_true")
    parser.add_argument("--no-external-actions", action="store_true")
    parser.add_argument("--max-time-to-value-days", type=int, default=30)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = recommend_stack(StackAdvisorRequest(
        workflow_type=args.workflow_type,
        integration_surface=args.integration_surface,
        risk_level=args.risk_level,
        team_profile=args.team_profile,
        cloud_preference=args.cloud_preference,
        enterprise_data=not args.no_enterprise_data,
        personalization=args.personalization,
        external_actions=not args.no_external_actions,
        max_time_to_value_days=args.max_time_to_value_days,
    ))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
