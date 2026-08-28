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

The shipped optional OpenAI adapter uses the Responses API's strict JSON-schema
output mode, then validates its result locally. Future Gemini, Anthropic, or
self-hosted adapters implement the same narrow `RerankerAdapter` protocol.
They receive `structured_rerank_request()` and
must return structured candidates with `candidate_id`, `score`, `citations`,
and `rationale`. `rerank_context()` validates the output before it becomes an
artifact. Provider credentials, raw model transcripts, and model-specific
prompting do not enter the durable contract.

Install the optional dependency and configure an explicit model only in the
staging worker environment:

```bash
python3 -m pip install -e './platform[openai]'
export SOCIAL_INTELLIGENCE_RERANKER_PROVIDER=openai
export SOCIAL_INTELLIGENCE_OPENAI_RERANKER_MODEL='your-approved-model'
export OPENAI_API_KEY='...'
```

The OpenAI adapter is opt-in; `deterministic/offline-baseline-v1` remains the
default, including for MCP. Keep the API key in a secret manager, not Git,
Databricks notebook source, or the durable rerank artifact.

## Single-store staging setup

For this Free Edition architecture, GitHub Actions is the external staging
worker. Store the provider credential **only** as the `OPENAI_API_KEY` secret
in its `staging` environment. The shadow workflow runs there and uploads only a
non-sensitive evaluation artifact; it does not pass the credential to
Databricks or Snowflake.

After copying the newly generated OpenAI project/service-account key, run this
single trusted-machine command from the repository root:

```bash
platform/scripts/set_github_staging_openai_secret.sh
```

The helper creates the GitHub `staging` environment if necessary and streams
the clipboard value directly to GitHub without printing or writing it locally.
Then use **Actions → Recommendation reranker shadow evaluation → Run workflow**
and enter the approved model name. The workflow remains manually dispatched to
avoid surprise model spend.

## Run locally

```bash
social-intelligence-batch-reranker rerank context.json
social-intelligence-batch-reranker evaluate evaluation-fixtures.json
social-intelligence-batch-reranker evaluate-staging
```

`evaluate` reports grounding, candidate-boundary, and expected-selection rates.
It is a release gate for a provider adapter, not proof of causal business lift.
All output remains `PROPOSED`; an approval and experiment gate are still
required before any action.

`evaluate-staging` runs five synthetic, governed golden cases. It is a
regression gate only. Before production, replace it with a human-labeled,
tenant-approved 30–50 case set and add cost/latency thresholds.
