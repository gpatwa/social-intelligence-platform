"""Model Context Protocol adapter for governed Social Intelligence read models."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

try:
    from mcp.server import MCPServer
except ImportError:  # pragma: no cover - exercised by install guidance, not CI
    MCPServer = None  # type: ignore[assignment,misc]

from .mcp_service import InMemoryDataProvider, McpService, SnapshotDataProvider


SERVER_NAME = "social-intelligence"
SNAPSHOT_ENV = "SOCIAL_INTELLIGENCE_MCP_SNAPSHOT_DIR"


def provider_from_environment() -> SnapshotDataProvider | InMemoryDataProvider:
    snapshot_dir = os.environ.get(SNAPSHOT_ENV, "").strip()
    if not snapshot_dir:
        return InMemoryDataProvider()
    return SnapshotDataProvider(Path(snapshot_dir).expanduser())


def create_mcp_server(provider: object | None = None) -> Any:
    """Create an MCPServer with an injectable provider for tests and hosts."""
    if MCPServer is None:
        raise RuntimeError(
            "MCP support is optional; install with `pip install -e './platform[mcp]'`"
        )
    service = McpService(provider or provider_from_environment())
    server = MCPServer(
        SERVER_NAME,
        instructions=(
            "Use tenant-scoped read tools to inspect governed opportunities, evidence, "
            "metrics, and pipeline status. Drafts never persist and approvals are not "
            "available through MCP."
        ),
    )

    @server.tool()
    def list_opportunities(
        tenant_id: str,
        status: str | None = None,
        min_score: float | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List tenant-scoped commercial opportunities ranked by priority."""
        return service.list_opportunities(
            tenant_id=tenant_id, status=status, min_score=min_score, limit=limit
        )

    @server.tool()
    def get_evidence(tenant_id: str, evidence_id: str) -> dict[str, Any]:
        """Retrieve one tenant-scoped evidence record by durable evidence ID."""
        return service.get_evidence(tenant_id=tenant_id, evidence_id=evidence_id)

    @server.tool()
    def get_metrics(
        tenant_id: str,
        metric_name: str | None = None,
        source_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Read tenant-scoped metric observations with optional source filters."""
        return service.get_metrics(
            tenant_id=tenant_id,
            metric_name=metric_name,
            source_id=source_id,
            limit=limit,
        )

    @server.tool()
    def get_pipeline_status(
        tenant_id: str, source_id: str | None = None
    ) -> dict[str, Any]:
        """Read source freshness and health projections for one tenant."""
        return service.get_pipeline_status(tenant_id=tenant_id, source_id=source_id)

    @server.tool()
    def draft_recommendation(
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
        """Draft a PROPOSED recommendation; it does not write or approve anything."""
        return service.draft_recommendation(
            tenant_id=tenant_id,
            opportunity_id=opportunity_id,
            action_type=action_type,
            channel=channel,
            hypothesis=hypothesis,
            creative_brief=creative_brief,
            primary_metric=primary_metric,
            confidence_score=confidence_score,
            evidence_ids=evidence_ids,
        )

    return server


def main() -> None:
    """Run the MCP server over stdio for desktop hosts and local agents."""
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
