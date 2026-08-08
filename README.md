# Social Intelligence Platform

A Databricks-powered analytics product for detecting emerging social trends,
participation challenges, brand risk, and source-health issues from governed
event data.

[View the product site](https://social-intelligence-signals.gopalpatwa.chatgpt.site)

## Current status

The repository contains a validated working MVP:

- 943 deterministic social events processed end to end
- 0 rejected events in the validated run
- 7 unified signals across trend, challenge, and brand-risk use cases
- control, data, and experience-plane boundaries
- Bronze, Silver, and Gold lakehouse data products
- source-health, model-review, dashboard, and alert artifacts
- a responsive product landing page deployed with OpenAI Sites

The MVP uses deterministic demo data. A real provider must be approved and
configured before this is used for production decisions.

## Architecture

```text
Approved social API or licensed provider
    -> webhook, stream, or polling adapter
    -> immutable versioned event envelope
    -> Bronze validation, quarantine, and deduplication
    -> Silver canonical social posts
    -> tenant-scoped Gold metrics and signals
    -> dashboard, alerts, review queues, and future APIs
```

The control, data, and experience planes are logical boundaries in the MVP.
They can be separated into independently operated services when scale,
security, residency, or team ownership requires it.

## Repository layout

```text
app/                    Product landing-page application
public/                 Landing-page assets and social preview
tests/                  Landing-page rendered HTML tests
platform/
  databricks.yml        Databricks Asset Bundle entry point
  resources/            Workflow resources
  notebooks/            Platform initialization and analytics pipeline
  src/                   Event contracts and scoring functions
  schemas/               Machine-readable social event contract
  sql/                   Dashboard datasets and alert queries
  scripts/               Dashboard and alert payload generators
  tests/                 Contract and scoring tests
  docs/                  Architecture, operations, and readiness decisions
```

## Run the product site

Requirements: Node.js 22.13 or later.

```bash
npm install
npm run dev
```

Production validation:

```bash
npm run lint
npm test
npm audit --omit=dev --audit-level=high
```

## Validate the Databricks platform

Requirements: Python 3.10 or later.

```bash
python3 -m pip install -e ./platform
python3 -m unittest discover -s platform/tests -v
```

See [the platform guide](platform/README.md) for deployment instructions and
[the architecture decision](platform/docs/ARCHITECTURE.md) for design details.

## Real-source integration

The repository includes real-source adapters for YouTube Data API v3 and X API
v2 Recent Search. Both use the same versioned envelope, persisted checkpoints,
bounded retries, idempotent delivery, immutable raw payloads, and external
Databricks Files ingestion. The X connector adds keyword, hashtag, and account
rules with public engagement snapshots. Activation still requires provider
approval, credentials, collection rules, and a retention policy.

Databricks Free Edition uses the guarded external GitHub Actions collector to
call YouTube and land immutable batches through the Databricks Files API. Its
workflows also support X; both schedules remain disabled until repository
secrets and pilot queries are validated.

See the
[real-source integration contract](platform/docs/REAL_SOURCE_INTEGRATION.md)
and [production readiness gates](platform/docs/PRODUCTION_READINESS.md).
YouTube-specific setup is documented in the
[connector guide](platform/docs/YOUTUBE_CONNECTOR.md).
The external-worker setup is in the
[Free Edition collector runbook](platform/docs/EXTERNAL_COLLECTOR.md), with
[X-specific setup](platform/docs/X_CONNECTOR.md).

## Production boundary

Databricks Free Edition is suitable for demonstrating the architecture and
analytics. Production use requires an appropriate paid workspace, Unity
Catalog governance, separate environments, managed credentials, operational
SLAs, retention and deletion controls, labeled model evaluation data, and
named alert owners.
