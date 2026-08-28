"""Model Context Protocol adapter for governed Social Intelligence read models."""
from __future__ import annotations
import hmac
import os
import time
from typing import Any

try:
    from mcp.server import MCPServer
except ImportError:  # pragma: no cover
    MCPServer = None  # type: ignore[assignment,misc]

from .authorization import TenantAuthorizer, authorizer_from_environment
from .mcp_observability import McpAuditRecorder
from .mcp_provider import provider_from_environment
from .mcp_service import McpService, SocialIntelligenceDataProvider

SERVER_NAME = "social-intelligence"


class BearerAuthMiddleware:
    """Small ASGI boundary for Streamable HTTP deployments."""
    def __init__(self, app: Any, token: str) -> None:
        self.app, self.token = app, token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"authorization", b"").decode("latin-1")
        if not hmac.compare_digest(supplied, f"Bearer {self.token}"):
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
            return
        await self.app(scope, receive, send)


def create_mcp_server(provider: SocialIntelligenceDataProvider | None = None,
                      authorizer: TenantAuthorizer | None = None,
                      audit: McpAuditRecorder | None = None) -> Any:
    """Create an MCPServer with injectable boundaries for tests and hosts."""
    if MCPServer is None:
        raise RuntimeError("Install MCP support with `pip install -e './platform[mcp]'`")
    service = McpService(provider or provider_from_environment(),
                         authorizer=authorizer or authorizer_from_environment())
    recorder = audit or McpAuditRecorder()
    server = MCPServer(SERVER_NAME, instructions=(
        "Use tenant-scoped read tools to inspect governed opportunities, evidence, "
        "metrics, pipeline status, ranked evidence, recommendation contexts, offline reranks, non-persisting human review/outcome artifacts, internal pilot plans, and "
        "evidence-linked agent stack recommendations. "
        "Drafts never persist and approvals are not available through MCP."
    ))

    def invoke(tool: str, tenant_id: str, operation: Any) -> Any:
        started = time.monotonic()
        try:
            result = operation()
        except Exception as error:
            recorder.record(tool=tool, tenant_id=str(tenant_id), outcome="error",
                            started_at=started, error_type=type(error).__name__)
            raise
        recorder.record(tool=tool, tenant_id=str(tenant_id), outcome="ok", started_at=started)
        return result

    @server.tool()
    def list_opportunities(tenant_id: str, status: str | None = None,
                           min_score: float | None = None, limit: int = 20) -> dict[str, Any]:
        """List tenant-scoped commercial opportunities ranked by priority."""
        return invoke("list_opportunities", tenant_id, lambda: service.list_opportunities(
            tenant_id=tenant_id, status=status, min_score=min_score, limit=limit))

    @server.tool()
    def get_evidence(tenant_id: str, evidence_id: str) -> dict[str, Any]:
        """Retrieve one tenant-scoped evidence record by durable evidence ID."""
        return invoke("get_evidence", tenant_id, lambda: service.get_evidence(
            tenant_id=tenant_id, evidence_id=evidence_id))

    @server.tool()
    def get_metrics(tenant_id: str, metric_name: str | None = None,
                    source_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        """Read tenant-scoped metric observations with optional source filters."""
        return invoke("get_metrics", tenant_id, lambda: service.get_metrics(
            tenant_id=tenant_id, metric_name=metric_name, source_id=source_id, limit=limit))

    @server.tool()
    def get_pipeline_status(tenant_id: str, source_id: str | None = None) -> dict[str, Any]:
        """Read source freshness and health projections for one tenant."""
        return invoke("get_pipeline_status", tenant_id, lambda: service.get_pipeline_status(
            tenant_id=tenant_id, source_id=source_id))

    @server.tool()
    def draft_recommendation(tenant_id: str, opportunity_id: str, action_type: str,
                             channel: str, hypothesis: str, creative_brief: str,
                             primary_metric: str, confidence_score: float,
                             evidence_ids: list[str]) -> dict[str, Any]:
        """Draft a PROPOSED recommendation; it does not write or approve anything."""
        return invoke("draft_recommendation", tenant_id, lambda: service.draft_recommendation(
            tenant_id=tenant_id, opportunity_id=opportunity_id, action_type=action_type,
            channel=channel, hypothesis=hypothesis, creative_brief=creative_brief,
            primary_metric=primary_metric, confidence_score=confidence_score,
            evidence_ids=evidence_ids))

    @server.tool()
    def recommend_agent_stack(
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
        """Recommend a governed AI automation stack; this tool never provisions it."""
        return invoke("recommend_agent_stack", tenant_id, lambda: service.recommend_agent_stack(
            tenant_id=tenant_id,
            workflow_type=workflow_type,
            integration_surface=integration_surface,
            risk_level=risk_level,
            team_profile=team_profile,
            cloud_preference=cloud_preference,
            enterprise_data=enterprise_data,
            personalization=personalization,
            external_actions=external_actions,
            max_time_to_value_days=max_time_to_value_days,
        ))

    @server.tool()
    def rank_evidence(
        tenant_id: str,
        decision_id: str,
        candidates: list[dict[str, Any]],
        limit: int = 5,
    ) -> dict[str, Any]:
        """Rank decision-specific evidence; candidate features must already be normalized."""
        return invoke("rank_evidence", tenant_id, lambda: service.rank_evidence(
            tenant_id=tenant_id,
            decision_id=decision_id,
            candidates=candidates,
            limit=limit,
        ))

    @server.tool()
    def create_internal_pilot_plan(
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
        evidence_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a draft-only seven-day internal pilot plan; nothing is deployed."""
        return invoke("create_internal_pilot_plan", tenant_id, lambda: service.create_internal_pilot_plan(
            tenant_id=tenant_id,
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
            evidence_ids=evidence_ids or [],
        ))

    @server.tool()
    def compile_recommendation_context(
        tenant_id: str,
        decision_id: str,
        business_objective: str,
        market: str,
        locale: str,
        primary_metric: str,
        ranked_evidence: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        outcome_signals: list[dict[str, Any]] | None = None,
        allowed_channels: list[str] | None = None,
        excluded_candidate_ids: list[str] | None = None,
        max_evidence_items: int = 5,
    ) -> dict[str, Any]:
        """Compile a constrained, draft-only context for future batch reranking."""
        return invoke("compile_recommendation_context", tenant_id, lambda: service.compile_recommendation_context(
            tenant_id=tenant_id,
            decision_id=decision_id,
            business_objective=business_objective,
            market=market,
            locale=locale,
            primary_metric=primary_metric,
            ranked_evidence=ranked_evidence,
            candidates=candidates,
            outcome_signals=outcome_signals or [],
            allowed_channels=allowed_channels or [],
            excluded_candidate_ids=excluded_candidate_ids or [],
            max_evidence_items=max_evidence_items,
        ))

    @server.tool()
    def rerank_recommendation_context(
        tenant_id: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Run the offline baseline on a supplied tenant-owned context; never activates anything."""
        return invoke("rerank_recommendation_context", tenant_id, lambda: service.rerank_recommendation_context(
            tenant_id=tenant_id, context=context,
        ))

    @server.tool()
    def create_recommendation_review(
        tenant_id: str,
        rerank: dict[str, Any],
        decision: str,
        reviewer_id: str,
        decision_reason: str,
        reviewed_at: str,
        idempotency_key: str,
        selected_candidate_id: str | None = None,
        edited_brief: str | None = None,
        reviewer_note: str | None = None,
    ) -> dict[str, Any]:
        """Compile a cited human approval, edit, or rejection; it never triggers an external action."""
        return invoke("create_recommendation_review", tenant_id, lambda: service.create_recommendation_review(
            tenant_id=tenant_id, rerank=rerank, decision=decision, reviewer_id=reviewer_id,
            decision_reason=decision_reason, reviewed_at=reviewed_at, idempotency_key=idempotency_key,
            selected_candidate_id=selected_candidate_id, edited_brief=edited_brief, reviewer_note=reviewer_note,
        ))

    @server.tool()
    def record_recommendation_outcome(
        tenant_id: str,
        review: dict[str, Any],
        metric_name: str,
        observed_value: float,
        unit: str,
        observed_at: str,
        measurement_source: str,
        reported_by: str,
        idempotency_key: str,
        measurement_window_days: int = 7,
        baseline_value: float | None = None,
        confidence: str = "DIRECTIONAL",
    ) -> dict[str, Any]:
        """Compile an observational outcome for an approved review; it never writes to an external system."""
        return invoke("record_recommendation_outcome", tenant_id, lambda: service.record_recommendation_outcome(
            tenant_id=tenant_id, review=review, metric_name=metric_name, observed_value=observed_value,
            unit=unit, observed_at=observed_at, measurement_source=measurement_source,
            reported_by=reported_by, idempotency_key=idempotency_key,
            measurement_window_days=measurement_window_days, baseline_value=baseline_value, confidence=confidence,
        ))
    return server


def main() -> None:
    """Run MCP over stdio (local) or authenticated Streamable HTTP (service)."""
    server = create_mcp_server()
    transport = os.environ.get("SOCIAL_INTELLIGENCE_MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        server.run(transport="stdio")
        return
    if transport not in {"streamable-http", "streamable_http", "http"}:
        raise RuntimeError("SOCIAL_INTELLIGENCE_MCP_TRANSPORT must be stdio or streamable-http")
    token = os.environ.get("SOCIAL_INTELLIGENCE_MCP_BEARER_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SOCIAL_INTELLIGENCE_MCP_BEARER_TOKEN is required for HTTP mode")
    import uvicorn
    host = os.environ.get("SOCIAL_INTELLIGENCE_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("SOCIAL_INTELLIGENCE_MCP_PORT", "8000"))
    app = server.streamable_http_app(json_response=True, stateless_http=True, host=host)
    uvicorn.run(BearerAuthMiddleware(app, token), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
