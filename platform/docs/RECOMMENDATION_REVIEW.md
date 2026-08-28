# Recommendation review v1

`recommendation-review-v1` turns a cited, offline rerank into an auditable
human decision for the internal pilot. It is the bridge from model evaluation
to measurable human adoption—not an ad-launching or agent-activation feature.

```text
recommendation-context-v1
  -> batch-reranker-v1 (offline proposed ranking)
  -> recommendation-review-v1 (approve | edit | reject)
  -> recommendation-outcome-v1 (observational measurement)
  -> Databricks Gold review scorecard -> Snowflake BA mart
```

## Review boundary

Every review request contains the complete cited rerank artifact and a
tenant-scoped opaque reviewer ID. The compiler enforces that:

- the input is `OFFLINE`, `PROPOSED`, evidence-cited, and non-mutating;
- an approval or edit selects only a supplied ranked candidate;
- an edit includes the reviewer’s bounded revised brief;
- a rejection cannot select a candidate or request handoff;
- no review grants permission to spend, publish, message, or launch anything.

An approval produces `APPROVED_FOR_HANDOFF`; an edit produces
`EDITED_FOR_HANDOFF`. Both are only `READY_FOR_MANUAL_HANDOFF`, with
`external_action_permitted: false`.

## Outcome boundary

Only an approved or edited review can receive a
`recommendation-outcome-v1` observation. The observation records its metric,
baseline when available, unit, measurement window, source, timestamp, and
confidence. Its attribution is always `OBSERVATIONAL_ONLY`; it cannot claim
that the recommendation caused the change.

## Data products

The platform initializer creates append-only Delta tables:

- `decision_recommendation_reviews`
- `decision_recommendation_outcomes`

The review scorecard task materializes:

- `gold_recommendation_review_outcomes`
- `gold_recommendation_review_scorecard`

Both Gold tables are included in the Snowflake publishing job, under
`SOCIAL_INTELLIGENCE.ANALYTICS`, for BA queries. Writes into the append-only
tables belong to the authenticated review-service boundary; MCP and the CLI
compile and validate artifacts but do not persist them.

## Internal-pilot gate

Stage 4 (shadow-live evaluation) is enabled only after there are real review
records and sufficient outcome coverage to compare model choices with human
choices. Stage 5 (narrow workflow automation) remains disabled until the pilot
defines its owner, budget and channel policy, execution adapter, audit-retention
period, and kill-switch runbook.

## Local validation

```bash
social-intelligence-recommendation-review review review-request.json
social-intelligence-recommendation-review record-outcome outcome-request.json
```

The same compile-only functions are exposed through MCP as
`create_recommendation_review` and `record_recommendation_outcome`.
