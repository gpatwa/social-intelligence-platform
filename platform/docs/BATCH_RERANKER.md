# Offline Batch Reranker

The batch reranker turns one `recommendation-context-v1` packet into a cited,
draft-only candidate ranking. It is an internal-staging component, not an
autonomous campaign or content executor.

## Safety boundary

The input is already constrained by the recommendation-context compiler. A
reranker must return every eligible candidate exactly once, cite only evidence
included in the context, and cannot introduce a product, channel, claim, or
external action. Invalid provider output fails closed.

The shipped `deterministic/offline-baseline-v1` is an explainable regression
baseline. It does not call an LLM. It scores supplied candidates from the
top-ranked evidence, governed historical-outcome support count, and eligible
channel coverage.

## Provider integration

Future OpenAI, Gemini, Anthropic, or self-hosted adapters implement the narrow
`RerankerAdapter` protocol. They receive `structured_rerank_request()` and
must return structured candidates with `candidate_id`, `score`, `citations`,
and `rationale`. `rerank_context()` validates the output before it becomes an
artifact. Provider credentials, raw model transcripts, and model-specific
prompting do not enter the durable contract.

## Run locally

```bash
social-intelligence-batch-reranker rerank context.json
social-intelligence-batch-reranker evaluate evaluation-fixtures.json
```

`evaluate` reports grounding, candidate-boundary, and expected-selection rates.
It is a release gate for a provider adapter, not proof of causal business lift.
All output remains `PROPOSED`; an approval and experiment gate are still
required before any action.
