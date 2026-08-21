"use client";

import { useMemo, useState } from "react";

type Workflow =
  | "lead_response"
  | "document_processing"
  | "follow_up"
  | "crm_reactivation"
  | "internal_reporting";
type Integration = "api" | "mixed" | "legacy_ui";
type Risk = "low" | "moderate" | "high";
type Cloud = "neutral" | "databricks" | "microsoft" | "google" | "aws";

const blueprints: Record<
  Workflow,
  { name: string; pattern: string; summary: string; metric: string }
> = {
  lead_response: {
    name: "Bounded lead-response agent",
    pattern: "Bounded agent",
    summary: "Qualify and route demand quickly, with human control over pricing, commitments, and sensitive replies.",
    metric: "Meeting conversion",
  },
  document_processing: {
    name: "Deterministic document workflow",
    pattern: "Automation first",
    summary: "Extract and validate fields, route exceptions, and reserve AI reasoning for ambiguous documents.",
    metric: "Straight-through rate",
  },
  follow_up: {
    name: "Policy-bounded follow-up agent",
    pattern: "Bounded agent",
    summary: "Choose the next approved action and draft contextual follow-up without unrestricted outbound access.",
    metric: "Conversion lift",
  },
  crm_reactivation: {
    name: "CRM reactivation workflow",
    pattern: "Workflow with AI",
    summary: "Score dormant records, generate approved variants, and measure incremental pipeline against a control.",
    metric: "Incremental pipeline",
  },
  internal_reporting: {
    name: "Grounded reporting workflow",
    pattern: "Automation first",
    summary: "Compute metrics deterministically, use AI for explanation, and retain citations to governed records.",
    metric: "Analyst hours saved",
  },
};

const orchestrators: Record<Cloud, string> = {
  neutral: "LangGraph",
  databricks: "LangGraph + Databricks",
  microsoft: "Microsoft Agent Framework",
  google: "Google ADK on Cloud Run",
  aws: "Amazon Bedrock AgentCore",
};

function label(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function AgentStackAdvisor() {
  const [workflow, setWorkflow] = useState<Workflow>("document_processing");
  const [integration, setIntegration] = useState<Integration>("mixed");
  const [risk, setRisk] = useState<Risk>("moderate");
  const [cloud, setCloud] = useState<Cloud>("databricks");
  const [personalization, setPersonalization] = useState(false);

  const recommendation = useMemo(() => {
    const blueprint = blueprints[workflow];
    const automationFirst = blueprint.pattern === "Automation first";
    const orchestration = automationFirst
      ? risk === "high"
        ? "Temporal + Python services"
        : "n8n + typed Python functions"
      : orchestrators[cloud];
    const tools =
      integration === "api"
        ? "Direct APIs + MCP"
        : integration === "mixed"
          ? "Direct APIs + MCP + Composio"
          : "Direct APIs + Orgo exception path";
    let score = 92;
    if (integration === "legacy_ui") score -= 10;
    if (risk === "high") score -= 6;
    return {
      blueprint,
      score,
      stack: [
        { role: automationFirst ? "Workflow" : "Orchestration", product: orchestration },
        { role: "Tools", product: tools },
        { role: "State", product: "PostgreSQL" },
        { role: "Knowledge", product: "Databricks + Delta" },
        { role: "Evaluation", product: "MLflow 3 + OpenTelemetry" },
        ...(personalization ? [{ role: "Memory", product: "Honcho · opt-in" }] : []),
      ],
      controls: [
        risk === "high" ? "Four-eyes approval" : "Human approval",
        "Scoped identity",
        "Immutable audit",
        integration === "legacy_ui" ? "Isolated computer" : "Idempotent actions",
      ],
    };
  }, [workflow, integration, risk, cloud, personalization]);

  return (
    <section className="section advisor-section" id="advisor">
      <div className="advisor-intro">
        <p className="section-kicker">Agent Stack Advisor</p>
        <h2>Start with the outcome. Earn the autonomy.</h2>
        <p>
          Describe one business workflow. Get an automation-first architecture,
          implementation stack, control model, and success metric—before buying
          another agent platform.
        </p>
      </div>

      <div className="advisor-workbench">
        <form className="advisor-controls" aria-label="Agent stack constraints">
          <div className="advisor-control-heading">
            <span>01 · Define the work</span>
            <strong>Four constraints. One opinionated blueprint.</strong>
          </div>

          <label>
            Business outcome
            <select value={workflow} onChange={(event) => setWorkflow(event.target.value as Workflow)}>
              {Object.keys(blueprints).map((value) => (
                <option value={value} key={value}>{label(value)}</option>
              ))}
            </select>
          </label>

          <label>
            Integration surface
            <select value={integration} onChange={(event) => setIntegration(event.target.value as Integration)}>
              <option value="api">Reliable APIs</option>
              <option value="mixed">APIs + long-tail apps</option>
              <option value="legacy_ui">Legacy browser / desktop</option>
            </select>
          </label>

          <label>
            Operating risk
            <select value={risk} onChange={(event) => setRisk(event.target.value as Risk)}>
              <option value="low">Low · internal support</option>
              <option value="moderate">Moderate · customer-facing</option>
              <option value="high">High · regulated or financial</option>
            </select>
          </label>

          <label>
            Platform alignment
            <select value={cloud} onChange={(event) => setCloud(event.target.value as Cloud)}>
              <option value="neutral">Vendor neutral</option>
              <option value="databricks">Databricks</option>
              <option value="microsoft">Microsoft</option>
              <option value="google">Google Cloud</option>
              <option value="aws">AWS</option>
            </select>
          </label>

          <label className="advisor-toggle">
            <input
              type="checkbox"
              checked={personalization}
              onChange={(event) => setPersonalization(event.target.checked)}
            />
            <span aria-hidden="true" />
            Add persistent personalization
          </label>
          <p className="advisor-form-note">No provisioning. No credentials. No automatic spend.</p>
        </form>

        <div className="advisor-result" aria-live="polite">
          <div className="advisor-result-top">
            <div>
              <span>02 · Recommended pattern</span>
              <strong>{recommendation.blueprint.pattern}</strong>
            </div>
            <div className="advisor-fit">
              <b>{recommendation.score}</b>
              <span>fit score</span>
            </div>
          </div>
          <h3>{recommendation.blueprint.name}</h3>
          <p>{recommendation.blueprint.summary}</p>

          <div className="advisor-stack" aria-label="Recommended stack">
            {recommendation.stack.map((item) => (
              <div key={`${item.role}-${item.product}`}>
                <span>{item.role}</span>
                <strong>{item.product}</strong>
              </div>
            ))}
          </div>

          <div className="advisor-result-bottom">
            <div>
              <span>Primary outcome</span>
              <strong>{recommendation.blueprint.metric}</strong>
            </div>
            <div>
              <span>Required controls</span>
              <strong>{recommendation.controls.join(" · ")}</strong>
            </div>
          </div>
        </div>
      </div>

      <div className="advisor-evidence">
        <span>Evidence-linked · catalog v1.0 · reviewed August 2026</span>
        <div>
          <a href="https://docs.langchain.com/oss/python/langgraph/overview" target="_blank" rel="noreferrer">LangGraph ↗</a>
          <a href="https://docs.databricks.com/aws/en/mlflow3/genai/" target="_blank" rel="noreferrer">MLflow 3 ↗</a>
          <a href="https://docs.composio.dev/docs/how-composio-works" target="_blank" rel="noreferrer">Composio ↗</a>
          <a href="https://docs.orgo.ai/introduction" target="_blank" rel="noreferrer">Orgo ↗</a>
        </div>
      </div>
    </section>
  );
}
