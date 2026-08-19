"""Deterministic multi-agent workflow over the governed MCP service boundary."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Protocol
from .decisioning import stable_decision_id

class ToolGateway(Protocol):
    def list_opportunities(self, tenant_id: str, **kwargs: Any) -> dict[str, Any]: ...
    def get_evidence(self, tenant_id: str, evidence_id: str) -> dict[str, Any]: ...
    def draft_recommendation(self, tenant_id: str, **kwargs: Any) -> dict[str, Any]: ...

@dataclass(frozen=True)
class AgentArtifact:
    artifact_id: str
    run_id: str
    task_id: str
    agent_role: str
    status: str
    summary: str
    claims: list[str]
    evidence_ids: list[str]
    recommendation: dict[str, Any] | None = None
    approval_required: bool = True

    def as_dict(self) -> dict[str, Any]: return asdict(self)

class ServiceToolGateway:
    def __init__(self, service: Any): self.service = service
    def list_opportunities(self, tenant_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.service.list_opportunities(tenant_id=tenant_id, **kwargs)
    def get_evidence(self, tenant_id: str, evidence_id: str) -> dict[str, Any]:
        return self.service.get_evidence(tenant_id=tenant_id, evidence_id=evidence_id)
    def draft_recommendation(self, tenant_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.service.draft_recommendation(tenant_id=tenant_id, **kwargs)

class Supervisor:
    """Runs research, evidence, critique, and strategy without hidden side effects."""
    def __init__(self, gateway: ToolGateway): self.gateway = gateway
    def run(self, tenant_id: str, task: str, limit: int = 5) -> dict[str, Any]:
        run_id = stable_decision_id(tenant_id, task, "agent-run-v1")
        task_id = stable_decision_id(run_id, "task")
        opportunities = self.gateway.list_opportunities(tenant_id, limit=limit).get("items", [])
        selected = opportunities[0] if opportunities else None
        evidence_ids = sorted({str(x) for row in opportunities for x in row.get("evidence_ids", []) if x})
        artifacts: list[AgentArtifact] = [AgentArtifact(
            stable_decision_id(run_id, "research"), run_id, task_id, "research", "COMPLETED",
            f"Found {len(opportunities)} governed opportunities.", [str(row.get("opportunity_id", "")) for row in opportunities], evidence_ids)]
        evidence = []
        for eid in evidence_ids:
            try: evidence.append(self.gateway.get_evidence(tenant_id, eid))
            except LookupError: continue
        artifacts.append(AgentArtifact(stable_decision_id(run_id, "evidence"), run_id, task_id, "evidence", "COMPLETED",
            f"Validated {len(evidence)} evidence records.", [str(x.get("evidence_id", "")) for x in evidence], evidence_ids))
        critique_ok = bool(selected and evidence_ids)
        artifacts.append(AgentArtifact(stable_decision_id(run_id, "critic"), run_id, task_id, "critic",
            "VALIDATED" if critique_ok else "REJECTED", "Evidence gate passed." if critique_ok else "No evidenced opportunity.", [], evidence_ids))
        recommendation = None
        if critique_ok:
            recommendation = self.gateway.draft_recommendation(tenant_id, opportunity_id=str(selected["opportunity_id"]),
                action_type="PROMOTE", channel="PAID_SOCIAL", hypothesis=f"Promoting {selected.get('topic', selected['opportunity_id'])} increases qualified demand.",
                creative_brief="Create a brand-safe variant grounded in the observed signal.", primary_metric="conversion_rate",
                confidence_score=float(selected.get("opportunity_score", 0)), evidence_ids=evidence_ids)
        artifacts.append(AgentArtifact(stable_decision_id(run_id, "strategy"), run_id, task_id, "strategist",
            "PROPOSED" if recommendation else "BLOCKED", "Drafted recommendation; approval is required." if recommendation else "Strategy blocked by evidence gate.", [], evidence_ids, recommendation))
        return {"run_id": run_id, "task_id": task_id, "tenant_id": tenant_id, "status": "PROPOSED" if recommendation else "BLOCKED",
                "approval_required": True, "artifacts": [a.as_dict() for a in artifacts]}
