"""Policy, evaluation, approval, and experiment gates for agent outputs."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Mapping
from .decisioning import stable_decision_id

def evaluate_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        "has_identity": bool(artifact.get("artifact_id") and artifact.get("run_id")),
        "has_evidence": bool(artifact.get("evidence_ids")),
        "known_status": artifact.get("status") in {"VALIDATED", "PROPOSED", "COMPLETED"},
    }
    return {"passed": all(checks.values()), "checks": checks, "status": "PASS" if all(checks.values()) else "FAIL"}

class ApprovalGate:
    def approve(self, recommendation: Mapping[str, Any], actor: str, reason: str) -> dict[str, Any]:
        if not actor.strip() or not reason.strip(): raise ValueError("actor and reason are required")
        if recommendation.get("status") != "PROPOSED": raise ValueError("Only PROPOSED recommendations can be approved")
        if not recommendation.get("evidence_ids"): raise ValueError("Approval requires evidence")
        return {"status": "APPROVED", "recommendation_id": recommendation.get("recommendation_id"),
                "decided_by": actor.strip(), "decision_reason": reason.strip(),
                "decided_at": datetime.now(timezone.utc).isoformat()}

class ExperimentGate:
    def plan(self, recommendation: Mapping[str, Any], approval: Mapping[str, Any]) -> dict[str, Any]:
        if approval.get("status") != "APPROVED": raise ValueError("An approved recommendation is required")
        rid = str(recommendation.get("recommendation_id", "")).strip()
        if not rid: raise ValueError("recommendation_id is required")
        return {"experiment_id": stable_decision_id(rid, "experiment-v1"), "recommendation_id": rid,
                "status": "EXPERIMENT_PLANNED", "primary_metric": recommendation.get("primary_metric"),
                "approval": dict(approval)}
