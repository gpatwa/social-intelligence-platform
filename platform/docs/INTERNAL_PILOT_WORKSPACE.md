# Internal Pilot Workspace

The Internal Pilot Workspace completes the staging loop from evidence to a
measurable seven-day pilot. It is intentionally single-tenant, non-mutating,
and limited to synthetic or non-sensitive data.

## Product sequence

```text
Ranked evidence -> Discovery -> Workflow design -> Seven-day plan -> Scorecard
```

### Ranked evidence

The ranking accepts cohort-normalized 0–100 features rather than raw,
cross-platform engagement counts. The v1 score weights decision relevance,
momentum, source quality, independent corroboration, freshness, and safety. It
deduplicates canonical URLs, applies a platform-diversity selection penalty,
retains direct source links, and never claims that social momentum proves
causation.

### Discovery and economics

The pilot request records one outcome, owner, workflow, volume, cycle time,
loaded labor cost, baseline success rate, and target success rate. Capacity
value is labeled as an estimate rather than booked revenue.

### Workflow boundary

Every step is classified as deterministic code, workflow, AI judgment, AI
generation, or human review. Staging permits only read, recommend, draft,
approved internal writes, and explicit human approval. External publishing,
purchases, PII collection, and permission changes are prohibited.

### Delivery and scorecard

The plan defines one exit condition for each of seven days. The scorecard has a
primary success target and guardrails for cycle time, review rate, cost,
evidence coverage, and unauthorized actions. Day seven must end in GO, ITERATE,
or STOP.

## Interfaces

- `social-intelligence-pilot plan` generates a planning artifact.
- `social-intelligence-pilot rank` ranks a normalized JSON candidate set.
- MCP exposes `rank_evidence` and `create_internal_pilot_plan`.
- OpenAPI exposes `/evidence/ranked` and `/internal-pilots/plan`.

All interfaces are deterministic and return `mutation: none`.
