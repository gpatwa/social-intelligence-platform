"""Provider-neutral, tenant-scoped service methods exposed through MCP.

The service deliberately knows nothing about Databricks or a model provider.
Adapters can supply rows from a lakehouse, Snowflake, or a test snapshot while
the governance and output contract stays identical.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping, Protocol, Sequence

from .decisioning import stable_decision_id
from .authorization import StaticTenantAuthorizer, TenantAuthorizer
from .evidence_ranking import EvidenceCandidate, rank_evidence
from .pilot_workspace import PilotDiscoveryRequest, create_internal_pilot_plan
from .recommendation_context import (
    RecommendationContextRequest,
    compile_recommendation_context,
)
from .stack_advisor import StackAdvisorRequest, recommend_stack


TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$")
MAX_LIMIT = 100


class SocialIntelligenceDataProvider(Protocol):
    """Read-only provider boundary used by the MCP service."""

    def opportunities(self) -> Sequence[Mapping[str, Any]]: ...

    def evidence(self) -> Sequence[Mapping[str, Any]]: ...

    def metrics(self) -> Sequence[Mapping[str, Any]]: ...

    def pipeline_status(self) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class SnapshotDataProvider:
    """Read JSON snapshots produced by a scheduled serving/export task.

    Each file may contain either a JSON array or ``{"items": [...]}``. An
    absent file is treated as an empty projection so the MCP server can start
    before the first Databricks refresh.
    """

    root: Path

    def _items(self, filename: str) -> list[Mapping[str, Any]]:
        path = self.root / filename
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Unable to read MCP snapshot {filename}") from error
        items = payload.get("items", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise RuntimeError(f"MCP snapshot {filename} must contain an object list")
        return items

    def opportunities(self) -> Sequence[Mapping[str, Any]]:
        return self._items("opportunities.json")

    def evidence(self) -> Sequence[Mapping[str, Any]]:
        return self._items("evidence.json")

    def metrics(self) -> Sequence[Mapping[str, Any]]:
        return self._items("metrics.json")

    def pipeline_status(self) -> Sequence[Mapping[str, Any]]:
        return self._items("pipeline_status.json")


@dataclass(frozen=True)
class InMemoryDataProvider:
    """Deterministic provider used by unit tests and local integrations."""

    opportunity_rows: Sequence[Mapping[str, Any]] = ()
    evidence_rows: Sequence[Mapping[str, Any]] = ()
    metric_rows: Sequence[Mapping[str, Any]] = ()
    pipeline_rows: Sequence[Mapping[str, Any]] = ()

    def opportunities(self) -> Sequence[Mapping[str, Any]]:
        return self.opportunity_rows

    def evidence(self) -> Sequence[Mapping[str, Any]]:
        return self.evidence_rows

    def metrics(self) -> Sequence[Mapping[str, Any]]:
        return self.metric_rows

    def pipeline_status(self) -> Sequence[Mapping[str, Any]]:
        return self.pipeline_rows


def _tenant(tenant_id: str) -> str:
    value = str(tenant_id or "").strip()
    if not TENANT_PATTERN.fullmatch(value):
        raise ValueError("tenant_id must be an opaque alphanumeric tenant identifier")
    return value


def _limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be an integer between 1 and {MAX_LIMIT}")
    return limit


def _tenant_rows(rows: Sequence[Mapping[str, Any]], tenant_id: str) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row.get("tenant_id") == tenant_id]


class McpService:
    """Governed read model and non-persisting recommendation draft service."""

    def __init__(
        self,
        provider: SocialIntelligenceDataProvider,
        authorizer: TenantAuthorizer | None = None,
    ):
        self.provider = provider
        self.authorizer = authorizer or StaticTenantAuthorizer()

    def _authorized_tenant(self, tenant_id: str) -> str:
        tenant = _tenant(tenant_id)
        self.authorizer.authorize(tenant)
        return tenant

    def list_opportunities(
        self,
        *,
        tenant_id: str,
        status: str | None = None,
        min_score: float | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        tenant = self._authorized_tenant(tenant_id)
        page_size = _limit(limit)
        if min_score is not None and not 0 <= min_score <= 100:
            raise ValueError("min_score must be between 0 and 100")
        wanted_status = status.strip().upper() if status else None
        rows = _tenant_rows(self.provider.opportunities(), tenant)
        if wanted_status:
            rows = [row for row in rows if str(row.get("status", "")).upper() == wanted_status]
        if min_score is not None:
            rows = [row for row in rows if float(row.get("opportunity_score", 0)) >= min_score]
        rows.sort(
            key=lambda row: (
                float(row.get("opportunity_score", 0)),
                str(row.get("signal_at", row.get("signal_ts", ""))),
            ),
            reverse=True,
        )
        return {
            "tenant_id": tenant,
            "items": rows[:page_size],
            "returned": min(len(rows), page_size),
            "available": len(rows),
            "next_page": len(rows) > page_size,
        }

    def get_evidence(self, *, tenant_id: str, evidence_id: str) -> dict[str, Any]:
        tenant = self._authorized_tenant(tenant_id)
        identifier = str(evidence_id or "").strip()
        if not identifier:
            raise ValueError("evidence_id is required")
        matches = [
            row
            for row in _tenant_rows(self.provider.evidence(), tenant)
            if row.get("evidence_id") == identifier
        ]
        if not matches:
            raise LookupError("Evidence was not found for this tenant")
        return matches[0]

    def get_metrics(
        self,
        *,
        tenant_id: str,
        metric_name: str | None = None,
        source_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        tenant = self._authorized_tenant(tenant_id)
        page_size = _limit(limit)
        rows = _tenant_rows(self.provider.metrics(), tenant)
        if metric_name:
            rows = [row for row in rows if row.get("metric_name") == metric_name]
        if source_id:
            rows = [row for row in rows if row.get("source_id") == source_id]
        rows.sort(key=lambda row: str(row.get("observed_at", "")), reverse=True)
        return {"tenant_id": tenant, "items": rows[:page_size], "returned": min(len(rows), page_size)}

    def get_pipeline_status(
        self, *, tenant_id: str, source_id: str | None = None
    ) -> dict[str, Any]:
        tenant = self._authorized_tenant(tenant_id)
        rows = _tenant_rows(self.provider.pipeline_status(), tenant)
        if source_id:
            rows = [row for row in rows if row.get("source_id") == source_id]
        return {
            "tenant_id": tenant,
            "items": rows,
            "healthy": bool(rows) and all(row.get("status") == "healthy" for row in rows),
        }

    def draft_recommendation(
        self,
        *,
        tenant_id: str,
        opportunity_id: str,
        action_type: str,
        channel: str,
        hypothesis: str,
        creative_brief: str,
        primary_metric: str,
        confidence_score: float,
        evidence_ids: Sequence[str],
    ) -> dict[str, Any]:
        """Return a deterministic PROPOSED draft; never persists or approves it."""
        tenant = self._authorized_tenant(tenant_id)
        if (
            not opportunity_id.strip()
            or not action_type.strip()
            or not channel.strip()
            or not hypothesis.strip()
            or not creative_brief.strip()
            or not primary_metric.strip()
        ):
            raise ValueError(
                "opportunity_id, action_type, channel, hypothesis, creative_brief, "
                "and primary_metric are required"
            )
        if not 0 <= confidence_score <= 100:
            raise ValueError("confidence_score must be between 0 and 100")
        ids = sorted({str(value).strip() for value in evidence_ids if str(value).strip()})
        if not ids:
            raise ValueError("at least one evidence_id is required")
        return {
            "recommendation_id": stable_decision_id(tenant, opportunity_id, "recommendation-v1"),
            "schema_version": "1.0",
            "tenant_id": tenant,
            "opportunity_id": opportunity_id,
            "action_type": action_type,
            "channel": channel,
            "hypothesis": hypothesis,
            "creative_brief": creative_brief,
            "primary_metric": primary_metric,
            "confidence_score": confidence_score,
            "status": "PROPOSED",
            "evidence_ids": ids,
            "mutation": "none",
            "approval_required": True,
        }

    def recommend_agent_stack(
        self,
        *,
        tenant_id: str,
        workflow_type: str,
        integration_surface: str = "mixed",
        risk_level: str = "moderate",
        team_profile: str = "mixed",
        cloud_preference: str = "neutral",
        enterprise_data: bool = True,
        personalization: bool = False,
        external_actions: bool = True,
        max_time_to_value_days: int = 30,
    ) -> dict[str, Any]:
        """Recommend a stack without provisioning, authenticating, or writing data."""
        tenant = self._authorized_tenant(tenant_id)
        result = recommend_stack(
            StackAdvisorRequest(
                workflow_type=workflow_type,
                integration_surface=integration_surface,
                risk_level=risk_level,
                team_profile=team_profile,
                cloud_preference=cloud_preference,
                enterprise_data=enterprise_data,
                personalization=personalization,
                external_actions=external_actions,
                max_time_to_value_days=max_time_to_value_days,
            )
        )
        return {"tenant_id": tenant, **result}

    def rank_evidence(
        self,
        *,
        tenant_id: str,
        decision_id: str,
        candidates: Sequence[Mapping[str, Any]],
        limit: int = 5,
    ) -> dict[str, Any]:
        """Rank normalized evidence without fetching, scraping, or writing data."""
        tenant = self._authorized_tenant(tenant_id)
        decision = str(decision_id or "").strip()
        if not decision:
            raise ValueError("decision_id is required")
        normalized_candidates = []
        for item in candidates:
            values = dict(item)
            values.pop("tenant_id", None)
            values.pop("decision_id", None)
            normalized_candidates.append(
                EvidenceCandidate(tenant_id=tenant, decision_id=decision, **values)
            )
        return rank_evidence(normalized_candidates, limit=limit)

    def create_internal_pilot_plan(
        self,
        *,
        tenant_id: str,
        workflow_type: str,
        business_outcome: str,
        process_owner: str,
        weekly_volume: int,
        minutes_per_case: float,
        loaded_hourly_cost_usd: float,
        baseline_success_rate: float,
        target_success_rate: float,
        target_time_reduction_pct: float = 35,
        integration_surface: str = "mixed",
        risk_level: str = "moderate",
        cloud_preference: str = "databricks",
        evidence_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Create a non-mutating, draft-only seven-day internal pilot plan."""
        tenant = self._authorized_tenant(tenant_id)
        return create_internal_pilot_plan(
            PilotDiscoveryRequest(
                tenant_id=tenant,
                workflow_type=workflow_type,
                business_outcome=business_outcome,
                process_owner=process_owner,
                weekly_volume=weekly_volume,
                minutes_per_case=minutes_per_case,
                loaded_hourly_cost_usd=loaded_hourly_cost_usd,
                baseline_success_rate=baseline_success_rate,
                target_success_rate=target_success_rate,
                target_time_reduction_pct=target_time_reduction_pct,
                integration_surface=integration_surface,
                risk_level=risk_level,
                cloud_preference=cloud_preference,
                evidence_ids=tuple(evidence_ids),
            )
        )

    def compile_recommendation_context(
        self,
        *,
        tenant_id: str,
        decision_id: str,
        business_objective: str,
        market: str,
        locale: str,
        primary_metric: str,
        ranked_evidence: Sequence[Mapping[str, Any]],
        candidates: Sequence[Mapping[str, Any]],
        outcome_signals: Sequence[Mapping[str, Any]] = (),
        allowed_channels: Sequence[str] = (),
        excluded_candidate_ids: Sequence[str] = (),
        max_evidence_items: int = 5,
    ) -> dict[str, Any]:
        """Compile a non-mutating, constrained input for a future batch reranker."""
        tenant = self._authorized_tenant(tenant_id)
        return compile_recommendation_context(
            RecommendationContextRequest(
                tenant_id=tenant,
                decision_id=decision_id,
                business_objective=business_objective,
                market=market,
                locale=locale,
                primary_metric=primary_metric,
                ranked_evidence=ranked_evidence,
                candidates=candidates,
                outcome_signals=outcome_signals,
                allowed_channels=allowed_channels,
                excluded_candidate_ids=excluded_candidate_ids,
                max_evidence_items=max_evidence_items,
            )
        )
