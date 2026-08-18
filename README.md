# Social Intelligence Platform

> **Find the signal. Shape what’s next.**

Turn audience momentum into creative ideas, smarter campaigns, and measurable
results—all in one governed decision workflow.

[![CI](https://github.com/gpatwa/social-intelligence-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/gpatwa/social-intelligence-platform/actions/workflows/ci.yml)

**[View the live product](https://social-intelligence-signals.gopalpatwa.chatgpt.site)**

## What it does

The platform helps product and marketing teams answer four connected questions:

1. **What is changing?** Detect emerging topics, challenges, engagement shifts,
   brand risk, and source-health issues across approved social sources.
2. **What should we do?** Map evidence to products and create a prioritized,
   reviewable creative recommendation.
3. **Did it work?** Convert approved recommendations into controlled experiments
   with fixed metrics, guardrails, budget, and margin assumptions.
4. **What did we learn?** Capture lift, incremental revenue, contribution margin,
   and confidence so later decisions improve.

```text
Signal -> Opportunity -> Recommendation -> Approval -> Experiment -> Learning
```

Every decision retains its source evidence, product mapping, rationale, approval
state, experiment design, and commercial outcome. The platform does not launch
ads or authorize spend automatically.

## Current status

The repository contains a working, pilot-ready implementation:

- **Live YouTube and X collection** through guarded GitHub Actions workers
- **Instagram Graph API connector** implemented and ready for final Meta authorization
- **One versioned connector contract** with immutable payloads, checkpoints,
  bounded retries, quota controls, idempotency, and replay
- **Databricks Free Edition lakehouse** with control metadata and Bronze, Silver,
  Gold, decision, quality, and operational data products
- **Governed decision engine** for opportunities, recommendations, approvals,
  experiments, and reusable learnings
- **Snowflake serving layer** with 13 curated, read-only marts for BA and SQL users
- **Automated infrastructure path** using Databricks Asset Bundles, Terraform,
  protected GitHub environments, and an idempotent Snowflake developer bootstrap
- **Live pipeline status** surfaced on the public product site from Databricks metrics
- **55 platform tests and 3 product-site tests** in the current validated delivery

The deterministic 943-event demo remains available for reproducible validation;
live-provider ingestion uses the same contracts and downstream pipeline.

## Architecture

Databricks is the governed system of record. Snowflake is the curated SQL serving
surface for analysts and BI tools.

```text
Approved social APIs
    -> external collectors (GitHub Actions for Free Edition)
    -> immutable SocialEventEnvelope NDJSON + checkpoints + run metrics
    -> Databricks Files API / managed volume
    -> Bronze validation, quarantine, and deduplication
    -> Silver canonical social observations
    -> tenant-scoped Gold signals and operational metrics
    -> opportunities -> recommendations -> experiments -> learnings
    -> Snowflake ANALYTICS marts -> BA / BI / SQL
    -> product site, live status, dashboards, alerts, and review queues
```

The system uses four logical boundaries:

| Boundary | Responsibility |
|---|---|
| Control plane | Tenants, sources, rules, contracts, ownership, quota, and policy |
| Data plane | Immutable ingestion, validation, quarantine, deduplication, and lakehouse transformations |
| Decision layer | Evidence-backed opportunities, recommendations, approvals, experiments, and learnings |
| Experience plane | Snowflake marts, dashboards, alerts, reviews, APIs, and the public product experience |

These are logical boundaries in the MVP. They can become independently operated
services when scale, security, residency, or team ownership requires it. See the
[architecture decision](platform/docs/ARCHITECTURE.md).

## Connectors

| Source | State | Initial coverage |
|---|---|---|
| YouTube Data API v3 | Live | Keyword/channel discovery, video metrics, optional comments and replies |
| X API v2 | Live | Recent search, hashtags, accounts, and San Francisco trend discovery |
| Instagram Graph API | Authorization-ready | Page-linked Business media and permitted hashtag discovery |
| Reddit | Approval pending | Connector contract and onboarding planned after API approval |

All implemented connectors share the same event envelope, checkpoint, retry,
quota, immutable landing, and Databricks ingestion path. Provider-specific setup
is documented in the [YouTube](platform/docs/YOUTUBE_CONNECTOR.md),
[X](platform/docs/X_CONNECTOR.md), and
[Instagram](platform/docs/INSTAGRAM_CONNECTOR.md) guides.

## Decision workflow

The decision layer creates four durable records:

| Record | Purpose |
|---|---|
| Opportunity | Reproducible signal projection with product fit, commercial fit, priority, confidence, expiry, and evidence |
| Recommendation | Audience, channel, hypothesis, creative brief, success metric, rationale, and approval state |
| Experiment | Control-versus-treatment plan created only after approval, with metrics, guardrails, budget, and outcomes |
| Learning | Immutable result used to calibrate later decisions for comparable products, audiences, channels, and offers |

Read the full [decision-engine contract](platform/docs/DECISION_ENGINE.md).

## Snowflake for BA and SQL users

Validated Gold and decision data is published to 13 curated marts in
`SOCIAL_INTELLIGENCE.ANALYTICS`. Analysts use the read-only
`SOCIAL_INTELLIGENCE_BA` role and a dedicated BA warehouse. Bronze payloads,
provider credentials, and workflow mutation rights are not exposed.

Start with the
[BA query pack](platform/sql/snowflake_ba_starter_queries.sql) for executive
pulse, emerging trends, challenges, brand health, connector operations,
opportunity prioritization, recommendation review, experiment performance, and
pilot scorecard analysis.

See [Snowflake serving](platform/docs/SNOWFLAKE_SERVING.md) for the publishing
contract and [Terraform infrastructure](infra/snowflake/README.md) for the
production control plane.

## Technology stack

| Layer | Technology |
|---|---|
| Collection | Python connectors, GitHub Actions, provider APIs |
| Contract and delivery | Versioned JSON Schema, NDJSON, Databricks Files API |
| Lakehouse and orchestration | Databricks Free Edition, PySpark, Delta tables, Asset Bundles |
| Analytics and decisioning | Python, SQL, governed Bronze/Silver/Gold and decision tables |
| BA serving | Snowflake, least-privilege roles, dedicated warehouses, 13 curated marts |
| Infrastructure and delivery | Terraform, GitHub Actions, protected environments |
| Product site | React, Next-compatible vinext runtime, Cloudflare Workers, OpenAI Sites |

## Repository layout

```text
app/                         Public product-site application
public/                      Product-site and social-preview assets
tests/                       Rendered product-site tests
.github/workflows/           CI and guarded collector/deployment workflows
scripts/                     Idempotent developer automation
infra/snowflake/             Terraform Snowflake control plane
platform/
  databricks.yml             Databricks Asset Bundle entry point
  resources/                 Analytics, source-setup, and ingestion jobs
  notebooks/                 Control, ingestion, analytics, validation, decision, and serving tasks
  src/social_intelligence/   Contracts, scoring, decisioning, and connectors
  schemas/                   Machine-readable event contract
  sql/                       Databricks dashboard and Snowflake BA query packs
  tests/                     Platform, connector, decision, and delivery tests
  docs/                      Architecture, operations, connector, and readiness decisions
```

## Validate locally

Requirements:

- Node.js 22.13 or later
- Python 3.10 or later

Product site:

```bash
npm install
npm test
```

Platform:

```bash
python3 -m pip install -e ./platform
python3 -m unittest discover -s platform/tests -v
```

## Deploy to Databricks Free Edition

Authenticate once through the provider-owned browser flow, then deploy the
versioned bundle:

```bash
databricks auth login \
  --host https://dbc-b8672746-8e43.cloud.databricks.com \
  --profile social-intelligence-free

databricks bundle validate -t dev --profile social-intelligence-free
databricks bundle deploy -t dev --profile social-intelligence-free
databricks bundle run social_intelligence_mvp -t dev \
  --profile social-intelligence-free
```

For live sources, the recommended Free Edition topology keeps provider API calls
in scheduled GitHub Actions collectors and lands immutable batches through the
Databricks Files API. Follow the
[Free Edition guide](platform/FREE_EDITION.md) and
[external collector runbook](platform/docs/EXTERNAL_COLLECTOR.md).

## Automate Snowflake developer setup

The idempotent developer bootstrap creates the dedicated Snowflake roles,
warehouses, database, schemas, service user, least-privilege grants, Databricks
secret, bundle deployment, and optional first publish:

```bash
python3 scripts/bootstrap_snowflake_dev.py --run-initial-publish
```

The remaining human action is Snowflake’s provider-owned SSO/MFA consent. The
automation does not store private keys in the repository or GitHub.

## Production boundary

The current deployment is designed for a focused pilot and honest learning, not
unattended commercial operation. Production requires:

- a paid Databricks workspace appropriate for commercial workloads and SLAs;
- Unity Catalog policies and tenant isolation matched to the trust boundary;
- workload identity federation and managed secret rotation;
- provider-approved retention, deletion, consent, and reconciliation workflows;
- monitored storage, recovery, data-quality, and incident-response objectives;
- statistically reviewed experiments before causal or revenue claims are made;
- explicit human approval before campaign launch or budget commitment.

Track the remaining gates in the
[production-readiness checklist](platform/docs/PRODUCTION_READINESS.md).
