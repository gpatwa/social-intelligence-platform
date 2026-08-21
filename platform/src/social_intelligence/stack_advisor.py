"""Deterministic, evidence-linked recommendations for enterprise AI agent stacks.

The advisor intentionally decides *whether* an agent is justified before it
selects products. It never provisions infrastructure or grants permissions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib.resources import files
import json
from typing import Any


WORKFLOWS = frozenset(
    {"lead_response", "document_processing", "follow_up", "crm_reactivation", "internal_reporting"}
)
INTEGRATION_SURFACES = frozenset({"api", "mixed", "legacy_ui"})
RISK_LEVELS = frozenset({"low", "moderate", "high"})
TEAM_PROFILES = frozenset({"business", "mixed", "engineering"})
CLOUD_PREFERENCES = frozenset({"neutral", "databricks", "microsoft", "google", "aws"})


def _catalog() -> dict[str, Any]:
    resource = files("social_intelligence.data").joinpath("agent_stack_catalog.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def _choice(value: str, allowed: frozenset[str], field: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise ValueError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return normalized


@dataclass(frozen=True)
class StackAdvisorRequest:
    workflow_type: str
    integration_surface: str = "mixed"
    risk_level: str = "moderate"
    team_profile: str = "mixed"
    cloud_preference: str = "neutral"
    enterprise_data: bool = True
    personalization: bool = False
    external_actions: bool = True
    max_time_to_value_days: int = 30

    def normalized(self) -> "StackAdvisorRequest":
        if not isinstance(self.max_time_to_value_days, int) or isinstance(
            self.max_time_to_value_days, bool
        ) or not 1 <= self.max_time_to_value_days <= 365:
            raise ValueError("max_time_to_value_days must be an integer between 1 and 365")
        for field in ("enterprise_data", "personalization", "external_actions"):
            if not isinstance(getattr(self, field), bool):
                raise ValueError(f"{field} must be a boolean")
        return StackAdvisorRequest(
            workflow_type=_choice(self.workflow_type, WORKFLOWS, "workflow_type"),
            integration_surface=_choice(
                self.integration_surface, INTEGRATION_SURFACES, "integration_surface"
            ),
            risk_level=_choice(self.risk_level, RISK_LEVELS, "risk_level"),
            team_profile=_choice(self.team_profile, TEAM_PROFILES, "team_profile"),
            cloud_preference=_choice(
                self.cloud_preference, CLOUD_PREFERENCES, "cloud_preference"
            ),
            enterprise_data=self.enterprise_data,
            personalization=self.personalization,
            external_actions=self.external_actions,
            max_time_to_value_days=self.max_time_to_value_days,
        )


def _component(role: str, product: str, rationale: str, required: bool = True) -> dict[str, Any]:
    return {"role": role, "product": product, "rationale": rationale, "required": required}


def _orchestrator(request: StackAdvisorRequest, pattern: str) -> dict[str, Any]:
    if pattern == "AUTOMATION_FIRST":
        if request.risk_level == "high":
            return _component("workflow", "Temporal + Python services", "Durable, explicit execution with auditable retries and compensation.")
        return _component("workflow", "n8n + typed Python functions", "Fast delivery for explicit steps; AI is confined to uncertain tasks.")
    choices = {
        "microsoft": ("Microsoft Agent Framework", "Best fit for Microsoft identity, telemetry, and enterprise application estates."),
        "google": ("Google ADK on Cloud Run", "Fits Google Cloud deployment, evaluation, and agent lifecycle tooling."),
        "aws": ("Amazon Bedrock AgentCore", "Fits AWS-native identity, runtime, and operational controls."),
        "databricks": ("LangGraph + Databricks", "Keeps orchestration model-neutral while grounding and evaluating against governed lakehouse data."),
        "neutral": ("LangGraph", "Model-neutral durable orchestration with explicit state and human interruption points."),
    }
    product, rationale = choices[request.cloud_preference]
    return _component("agent orchestration", product, rationale)


def recommend_stack(request: StackAdvisorRequest) -> dict[str, Any]:
    """Return an idempotent, non-mutating implementation recommendation."""
    normalized = request.normalized()
    catalog = _catalog()
    blueprint = catalog["blueprints"][normalized.workflow_type]
    pattern = str(blueprint["pattern"])
    stack = [_orchestrator(normalized, pattern)]

    if normalized.integration_surface == "api":
        stack.append(_component("tools", "Direct APIs + MCP", "Prefer typed, least-privilege APIs for critical actions."))
    elif normalized.integration_surface == "mixed":
        stack.append(_component("tools", "Direct APIs + MCP + Composio", "Keep critical systems direct and use managed OAuth for the long tail."))
    else:
        stack.append(_component("tools", "Direct APIs + Orgo exception path", "Use isolated computer control only where no reliable API exists."))

    stack.append(_component("operational state", "PostgreSQL", "Store workflow state, approvals, identities, and idempotency keys outside model context."))
    if normalized.enterprise_data:
        stack.extend(
            [
                _component("analytics and knowledge", "Databricks + Delta", "Ground recommendations in governed data and retain replayable evidence."),
                _component("business analytics", "Snowflake", "Expose curated outcome and adoption marts to BA and SQL users."),
            ]
        )
    else:
        stack.append(_component("knowledge", "PostgreSQL + object storage", "Keep the first deployment small until governed enterprise data becomes a requirement."))
    stack.append(_component("evaluation", "MLflow 3 + OpenTelemetry", "Trace tool calls, evaluate quality, and monitor latency, cost, and regressions."))
    if normalized.personalization:
        stack.append(_component("personal memory", "Honcho (opt-in)", "Add inferred long-term context only with retention controls and user consent.", False))

    controls = ["tenant isolation", "scoped workload identity", "immutable audit trail", "idempotent tool actions", "evaluation release gate"]
    if normalized.external_actions:
        controls.append("human approval before external side effects")
    if normalized.risk_level == "high":
        controls.extend(["four-eyes approval", "policy-as-code enforcement", "kill switch and compensating action"])
    if normalized.integration_surface == "legacy_ui":
        controls.extend(["isolated computer session", "allowlisted destinations", "step and spend limits"])
    if normalized.personalization:
        controls.extend(["memory consent", "retention and deletion policy", "authoritative-record separation"])

    delivery_days = int(blueprint["delivery_days"])
    fit_score = 92
    if normalized.integration_surface == "legacy_ui":
        fit_score -= 10
    if normalized.risk_level == "high":
        fit_score -= 6
    if normalized.team_profile == "business" and pattern != "AUTOMATION_FIRST":
        fit_score -= 7
    if normalized.max_time_to_value_days < delivery_days:
        fit_score -= min(20, (delivery_days - normalized.max_time_to_value_days) * 3)
    fit_score = max(0, min(100, fit_score))

    why = [
        f"{blueprint['name']} matches the requested {normalized.workflow_type.replace('_', ' ')} outcome.",
        "The design separates deterministic workflow state from probabilistic model decisions.",
        "Critical tools remain least-privilege and every recommendation retains evidence lineage.",
    ]
    if pattern == "AUTOMATION_FIRST":
        why.insert(1, "A full autonomous agent would add avoidable cost and failure modes to a mostly explicit process.")
    if normalized.integration_surface == "legacy_ui":
        why.append("Computer use is isolated as a fallback because GUI automation is less reliable than an API.")

    request_dict = asdict(normalized)
    identity = json.dumps(request_dict, sort_keys=True, separators=(",", ":"))
    recommendation_id = sha256(f"agent-stack-v1|{identity}".encode("utf-8")).hexdigest()
    selected_tags = {"evaluation"}
    products = " ".join(component["product"].lower() for component in stack)
    for tag in ("langgraph", "databricks", "composio", "orgo", "honcho", "microsoft", "google", "aws", "temporal", "n8n"):
        if tag in products:
            selected_tags.add(tag)
    evidence = [
        item
        for item in catalog["evidence"]
        if selected_tags.intersection(item.get("tags", []))
    ]
    return {
        "recommendation_id": recommendation_id,
        "schema_version": "1.0",
        "catalog_version": catalog["catalog_version"],
        "reviewed_at": catalog["reviewed_at"],
        "request": request_dict,
        "blueprint": {
            "id": normalized.workflow_type,
            "name": blueprint["name"],
            "summary": blueprint["summary"],
            "pattern": pattern,
            "delivery_days": delivery_days,
        },
        "fit_score": fit_score,
        "confidence": "HIGH" if fit_score >= 85 else "MEDIUM" if fit_score >= 65 else "LOW",
        "why": why,
        "stack": stack,
        "required_controls": sorted(set(controls)),
        "success_metrics": blueprint["metrics"],
        "delivery_plan": [
            "Baseline the current process, economics, exceptions, and risk owners.",
            "Build one narrow golden path with synthetic and red-team evaluation cases.",
            "Run in shadow mode before enabling bounded actions and approval gates.",
            "Compare business outcomes against a control and review results weekly.",
        ],
        "evidence": evidence,
        "approval_required": normalized.external_actions,
        "mutation": "none",
    }
