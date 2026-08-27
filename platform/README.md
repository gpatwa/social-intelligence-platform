# Social Intelligence MVP on Databricks

This project is a deployable Databricks Asset Bundle that demonstrates an
end-to-end social intelligence product. It uses three logical planes—control,
data, and experience—on an event-driven lakehouse. It creates realistic demo
events, ingests them through Auto Loader, enriches and standardizes them, and
produces trend, challenge, brand, health, signal, opportunity, recommendation,
experiment, learning, and executive KPI tables.

## What the MVP answers

- Which topics are accelerating unusually quickly?
- Which hashtags or participation patterns look like viral challenges?
- How is brand sentiment changing?
- Which platforms, creators, and regions are driving a trend?
- Which posts and creators are outperforming their platform baseline, without
  confusing raw reach with quality?
- Are the source data and derived metrics fresh and complete?
- Which product or brand action is worth testing next, and what evidence supports it?
- Did an approved recommendation create incremental revenue and contribution margin?
- Should a business workflow use deterministic automation, a bounded agent, or
  computer use—and which governed stack best fits its constraints?

The demo deliberately includes:

- a fast-growing `#GlowUpChallenge` participation trend;
- a late negative spike around a fictional Acme battery issue;
- stable baseline topics that should not be mistaken for emerging trends.

## Architecture

```text
Control: source registry / collection rules / event contracts
                                  |
Data: API envelope -> immutable raw events -> dead letter or canonical posts
                                  -> Silver -> tenant-scoped Gold metrics
                                  |
Experience: unified signal feed -> governed decision loop -> Snowflake / dashboard / API
```

The planes are logical boundaries in the MVP. They should become independently
deployed services only when isolation, scale, regional residency, or team
ownership requires it. See [the architecture decision](docs/ARCHITECTURE.md).

## Repository layout

```text
databricks.yml                         Asset Bundle entry point
resources/social_intelligence.job.yml Serverless workflow definition
notebooks/00_initialize_platform.py    Control metadata and shared storage
notebooks/01_generate_demo_data.py     Demo connector emitting event envelopes
notebooks/02_build_analytics.py        Auto Loader and Bronze/Silver/Gold logic
notebooks/03_validate_product.py       Data and product acceptance checks
notebooks/04_model_governance.py       Tenant-scoped review and quality workflow
notebooks/12_build_decision_workflow.py Opportunity, recommendation, experiment, and learning loop
notebooks/07_ingest_connector_metrics.py External collector run and quota metrics
notebooks/08_validate_external_ingestion.py Real-source acceptance gates
sql/dashboard_queries.sql              Dashboard datasets and alert queries
src/social_intelligence/contracts.py   Versioned event-envelope contract
schemas/social-event-envelope-v1.json  Machine-readable connector contract
contracts/                             CloudEvents, evidence, artifact, and OpenAPI contracts
knowledge/social-intelligence/         OKF 0.2 definitions, policies, and computations
src/social_intelligence/mcp_server.py  MCP stdio server and governed tools
src/social_intelligence/mcp_service.py Provider-neutral tenant-scoped read model
src/social_intelligence/scoring.py     Locally testable scoring functions
src/social_intelligence/stack_advisor.py Deterministic enterprise agent stack advisor
src/social_intelligence/recommendation_context.py Deterministic context compiler for a future batch reranker
tests/                                 Contract and scoring unit tests
```

The repository includes quota-aware YouTube Data API v3, X API v2 Recent
Search, and Page-linked Instagram Graph API adapters, provider fixtures,
checkpoint and retry primitives, and separate governed source-registration
jobs. See the
[YouTube connector guide](docs/YOUTUBE_CONNECTOR.md) and
[X connector guide](docs/X_CONNECTOR.md) and
[Instagram connector guide](docs/INSTAGRAM_CONNECTOR.md).

For Databricks Free Edition, use the
[external GitHub Actions collector](docs/EXTERNAL_COLLECTOR.md). It lands
events, durable checkpoints, and quota/run metrics through the Databricks Files
API; the paused `social_intelligence_external_ingestion` job then refreshes the
Bronze, Silver, Gold, and operational tables.

## Prerequisites

- A Databricks workspace with Unity Catalog enabled.
- Permission to create a schema and a managed volume in the selected catalog.
- Databricks CLI 0.218 or newer, authenticated to the target workspace.
- Serverless workflows enabled. If serverless is unavailable, add a `job_cluster_key` and job cluster definition to the workflow resource.

## Local validation

```bash
cd social-intelligence-mvp
python3 -m pip install -e '.[mcp,standards]'
python3 scripts/build_okf_bundle.py --bundle knowledge/social-intelligence --check
python3 scripts/validate_okf_bundle.py --bundle knowledge/social-intelligence
python3 -m unittest discover -s tests -v
```

Run the MCP adapter locally with `social-intelligence-mcp`. It reads optional
JSON projections from `SOCIAL_INTELLIGENCE_MCP_SNAPSHOT_DIR`; the default empty
provider is intentional so a host never receives cross-tenant or ungoverned
data. See [MCP operations](docs/MCP.md).

`recommendation-context-v1` packages ranked evidence, business context, an
eligible candidate set, and governed outcome aggregates for a future evaluated
batch reranker. It is non-mutating and model-free; see
[Recommendation Context](docs/RECOMMENDATION_CONTEXT.md).

## Deploy and run

Using Databricks Free Edition? Start with [FREE_EDITION.md](FREE_EDITION.md) and
the generated `social-intelligence-free-edition.zip` notebook archive.

The default schema is unique to the bundle target. Override the catalog or schema if needed.

```bash
databricks bundle validate
databricks bundle deploy -t dev
databricks bundle run social_intelligence_mvp -t dev
```

For a production-style target:

```bash
databricks bundle deploy -t prod \
  --var="catalog=main" \
  --var="schema=social_intelligence_prod"
databricks bundle run social_intelligence_mvp -t prod
```

The validation task prints the fully qualified Gold table names and fails the workflow if core acceptance checks do not pass.

## Generate portable alert payloads

Alert configuration in this repository contains no workspace IDs or personal
email addresses. Supply deployment-specific values through the environment:

```bash
export DATABRICKS_WAREHOUSE_ID="<warehouse-id>"
export DATABRICKS_PARENT_PATH="/Users/<workspace-user>"
export SOCIAL_INTELLIGENCE_ALERT_EMAIL="<alert-owner@example.com>"
export SOCIAL_INTELLIGENCE_CATALOG="dev"
export SOCIAL_INTELLIGENCE_SCHEMA="social_intelligence_dev"
python3 scripts/build_alert_payloads.py ./generated-alerts
```

`SOCIAL_INTELLIGENCE_ALERT_EMAIL` is optional. Configure an approved
notification destination before enabling production alerts.

## Build an AI/BI dashboard

Open `sql/dashboard_queries.sql` in Databricks SQL and create datasets from the supplied queries. A useful first dashboard has five pages:

1. **Executive pulse** — post volume, reach, engagement, sentiment, active topics.
2. **Emerging trends** — trend score, velocity z-score, acceleration, creator breadth.
3. **Challenges** — participation score, unique creators, geographic and platform spread.
4. **Brand health** — daily sentiment, negative rate, engagement and mention changes.
5. **Content and creators** — efficiency-weighted post performance and
   platform-segmented creator performance.
6. **Operations** — freshness, invalid rows, duplicates and pipeline status.

Replace `${catalog}` and `${schema}` in the SQL file with deployed values. The queries marked `ALERT` return a row only when the relevant threshold is breached and can be attached to Databricks SQL alerts.

## Operating the product

- [Demo validation results](docs/DEMO_VALIDATION.md)
- [Architecture decision and evolution triggers](docs/ARCHITECTURE.md)
- [Signal ownership and response model](docs/OPERATING_MODEL.md)
- [Real-source integration contract](docs/REAL_SOURCE_INTEGRATION.md)
- [Snowflake BA and SQL serving](docs/SNOWFLAKE_SERVING.md)
- [Creative investment decision engine](docs/DECISION_ENGINE.md)
- [Cross-platform scoring definitions](docs/CROSS_PLATFORM_SCORING.md)
- [Production readiness gates](docs/PRODUCTION_READINESS.md)
- [Open standards decision](docs/adr/0001-open-agent-and-knowledge-standards.md)
- [Interoperability contract registry](contracts/README.md)
- [OKF knowledge bundle](knowledge/social-intelligence/index.md)
- [MCP operations](docs/MCP.md)
- [Agent Stack Advisor](docs/AGENT_STACK_ADVISOR.md)
- [Internal Pilot Workspace](docs/INTERNAL_PILOT_WORKSPACE.md)

The Free Edition deployment runs daily at 7:30 AM Pacific. It also includes a
human-review queue (`gold_model_review_queue`) and an initially empty
`silver_human_labels` table for evaluating future topic, sentiment, and risk
models against reviewer labels.

## Replace demo data with a real source

Keep the canonical event envelope and replace only the generator task:

1. Register the source in `control_source_registry`.
2. Land versioned event envelopes in the managed volume, or change the Auto
   Loader path to external cloud storage.
3. Preserve the raw provider payload, logical idempotency key, and timestamps.
4. Map platform-specific payloads into the canonical Silver columns.
5. Snapshot engagement counts because likes, views, and shares change after publication.
6. Use approved APIs and implement rate-limit, deletion, and retention handling required by each provider.

For higher volume, separate post content from engagement snapshots and use a streaming source such as Kafka. For production NLP, replace the rule-based sentiment and topic mappings with governed batch inference, while retaining model version and confidence columns.

### YouTube pilot

`social_intelligence_youtube_ingestion` is an hourly polling job whose schedule
is paused by default. It reads its API key from a Databricks secret reference,
loads active keyword and channel rules from the control plane, persists quota
reservations and rule cursors, lands immutable envelopes, and refreshes the
existing analytics pipeline. Comments and replies are opt-in because they
increase quota use and privacy obligations.

The recommended Free Edition alternative is the `YouTube collector` GitHub
Actions workflow plus the `social_intelligence_external_ingestion` Databricks
job. Do not enable both collection runtimes for the same source.

## Metric notes

- Cross-platform counts are shown separately because platform definitions differ.
- `engagement_rate` uses views as the denominator in this demo.
- Trend scores are comparative signals, not probabilities.
- The challenge score rewards participant breadth and spread, not merely raw mentions.
- Social activity should be described as correlated with business outcomes unless causal measurement is in place.
