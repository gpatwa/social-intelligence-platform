# Recommendation Context v1

`recommendation-context-v1` is the governed bridge between ranked social
evidence and a future LLM-assisted recommendation ranker. It is intentionally
not a model feature: the compiler only validates, filters, and packages facts.

## What it compiles

One packet contains a tenant-scoped decision, explicit business objective and
market, ranked evidence with canonical URLs, an eligible candidate set, and
optional observed outcome signals. It returns `READY_FOR_RERANK` only when at
least one candidate survives deterministic policy filtering.

The context is safe for an offline batch reranker because it says exactly what
the reranker may consider: rank supplied candidates only, cite supplied
evidence, and never infer causality. Every downstream output stays draft-only
until a human approval gate.

## Deliberate boundaries

- No model invocation, web retrieval, social scraping, SQL execution, or write
  occurs in the compiler.
- No raw social content or PII belongs in this contract; use durable evidence
  IDs, titles, URLs, scored features, and governed aggregates.
- Candidate eligibility, allowed channels, and explicit exclusions are applied
  before any model sees a candidate.
- The compiler is deterministic. Reordered inputs produce the same context ID.

## Use it

```bash
social-intelligence-recommendation-context request.json
```

Or call the `compile_recommendation_context` MCP tool / `POST
/recommendation-contexts/compile` API. The request and response contracts live
in [`../contracts/json-schema`](../contracts/json-schema).

The next phase is an evaluated batch reranker that consumes this packet,
returns citations and a structured draft, and is measured against a holdout
and approved business outcomes—not a free-form autonomous agent.
