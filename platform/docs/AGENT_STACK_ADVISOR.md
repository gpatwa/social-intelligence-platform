# Agent Stack Advisor

The Agent Stack Advisor converts a bounded business workflow and its operating
constraints into a deterministic, evidence-linked implementation blueprint. It
answers the agent-versus-automation question before selecting products.

## Supported first-wave outcomes

1. Lead response and qualification.
2. Document processing and exception routing.
3. Context-aware follow-up.
4. CRM reactivation with a measured control group.
5. Governed internal reporting.

## Decision rules

- Prefer ordinary code or a workflow when the steps are explicit.
- Add an agent only where the task needs open-ended planning or contextual tool
  selection.
- Prefer typed APIs and MCP tools over screen automation.
- Use isolated computer control only when no reliable API exists.
- Keep approvals, workflow state, identities, and idempotency keys outside model
  context and memory systems.
- Require human approval for material external side effects.
- Evaluate against business outcomes and safety controls before increasing
  autonomy.

## Interfaces

The advisor is available through three equivalent product surfaces:

- `social-intelligence-stack-advisor` for scripts, CI, and solution workshops;
- `recommend_agent_stack` on the governed MCP server;
- `POST /agent-stack/recommendations` in the OpenAPI contract.

Example:

```bash
social-intelligence-stack-advisor document_processing \
  --integration-surface legacy_ui \
  --risk-level high \
  --team-profile engineering \
  --cloud-preference databricks
```

Every response includes the chosen operating pattern, fit score, stack roles,
mandatory controls, outcome metrics, evidence links, and a four-stage delivery
plan. The service is non-mutating: it never purchases products, creates cloud
resources, grants access, or approves deployment.

## Reference architecture

```text
Experience: web / CLI / MCP / Slack or Teams
                         |
Control: advisor request -> deterministic decision -> approval policy
                         |
Runtime: workflow or bounded agent -> scoped tools -> isolated UI fallback
                         |
State: PostgreSQL          Knowledge: Databricks / Delta
                         |
Quality: MLflow 3 / OpenTelemetry -> Snowflake outcome marts
```

The catalog is versioned in
`src/social_intelligence/data/agent_stack_catalog.json`. Product claims link to
the official evidence sources recorded in that catalog and carry a review date.
