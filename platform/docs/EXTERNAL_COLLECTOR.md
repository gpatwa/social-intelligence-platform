# External collector for Databricks Free Edition

Databricks Free Edition remains the lakehouse and analytics plane. A scheduled
GitHub Actions workflows call approved provider APIs, write immutable newline-
delimited JSON batches through the Databricks Files API, and store each source's
cursor and quota ledger in the same Unity Catalog volume. YouTube and X use the
same control-plane contract and delivery semantics.

```text
GitHub Actions -> YouTube Data API -> SocialEventEnvelope NDJSON
       |                                      |
       +---- checkpoint + run metrics --------+
                                              v
             /Volumes/<catalog>/<schema>/raw_social
                                              |
                                              v
             Databricks available-now ingestion job
```

This is the recommended Free Edition topology because the collector does not
depend on Databricks outbound internet access. The existing Databricks-native
YouTube job remains paused as a fallback. Never enable both collectors for the
same tenant and source at the same time because they share a checkpoint.

## One-time Databricks preparation

Authenticate the Databricks CLI and initialize the volume before enabling the
GitHub schedule:

```bash
cd platform
databricks bundle deploy -t dev --profile social-intelligence-free
databricks bundle run social_intelligence_mvp -t dev \
  --profile social-intelligence-free
```

The initialization notebook creates these durable paths:

```text
/Volumes/dev/social_intelligence_dev/raw_social/events
/Volumes/dev/social_intelligence_dev/raw_social/checkpoints
/Volumes/dev/social_intelligence_dev/raw_social/operations
```

## GitHub secrets

Add these Actions secrets under **Settings > Secrets and variables > Actions**.
Do not place the values in repository variables or source code.

| Secret | Purpose |
| --- | --- |
| `DATABRICKS_HOST` | Workspace URL, for example `https://dbc-...cloud.databricks.com` |
| `DATABRICKS_TOKEN` | Databricks credential with Files API access to the target volume |
| `YOUTUBE_API_KEY` | Google API key restricted to YouTube Data API v3 |
| `X_BEARER_TOKEN` | Bearer credential for the approved X API project |
| `PIPELINE_STATUS_INGEST_KEY` | Shared secret used only to publish a sanitized run metric to the landing page |

Use a dedicated short-lived Databricks credential when Free Edition supports
it. Rotate the credential immediately if it appears in workflow output.

## GitHub variables

Set repository Actions variables for non-secret configuration:

| Variable | Default |
| --- | --- |
| `DATABRICKS_CATALOG` | `dev` |
| `DATABRICKS_SCHEMA` | `social_intelligence_dev` |
| `SOCIAL_TENANT_ID` | `demo` |
| `YOUTUBE_SOURCE_ID` | `youtube-api-v3` |
| `YOUTUBE_SEARCH_EXPRESSION` | `Acme|GlowUpChallenge` |
| `YOUTUBE_CHANNEL_IDS` | empty comma-separated list |
| `YOUTUBE_REGION_CODE` | `US` |
| `YOUTUBE_RELEVANCE_LANGUAGE` | `en` |
| `YOUTUBE_LOOKBACK_HOURS` | `6` |
| `YOUTUBE_MAX_SEARCH_PAGES_PER_RULE` | `1` |
| `YOUTUBE_COLLECT_COMMENTS` | `false` |
| `YOUTUBE_COLLECT_REPLIES` | `false` |
| `PIPELINE_STATUS_URL` | Public landing-page endpoint, ending in `/api/pipeline-status` |

For X-specific setup and the allowed query modes, see [X connector](X_CONNECTOR.md).

Leave `ENABLE_YOUTUBE_COLLECTOR` unset during setup. Run the workflow manually,
inspect the batch, checkpoint, run metric, and Databricks tables, then set it to
`true` to enable hourly scheduled collection. GitHub may delay scheduled runs,
so this is a near-real-time MVP rather than an SLA-backed streaming service.

## Databricks ingestion

The `social_intelligence_external_ingestion` bundle job is paused by default.
After one successful external collection, run it manually:

```bash
databricks bundle run social_intelligence_external_ingestion -t dev \
  --profile social-intelligence-free
```

Validate these tables before unpausing its `:47` hourly schedule:

```text
bronze_connector_runs
gold_connector_operations
bronze_social_events
bronze_dead_letter_events
gold_source_health
gold_signal_feed
```

Acceptance gates are: no dead-letter rows, no unexplained duplicates, a fresh
successful collector run, positive quota headroom, and reconciliation of
sampled videos against the YouTube user interface.

After each collector attempt, the workflow publishes the same run metric that
lands in `gold_connector_operations` to a separate public-safe status store.
The endpoint accepts only the versioned operational fields used by the landing
page; Databricks credentials, event payloads, checkpoints, and internal volume
paths are never returned to the browser.

The external job uses source-specific validation. The deterministic demo
validator intentionally checks fictional challenge and brand-risk scenarios and
is not used as a live-source acceptance test.

## Failure and replay semantics

- Quota reservations are uploaded before every provider request completes.
- The worker idempotently creates missing Files API directories before reading
  its checkpoint, so a new source can start from an empty volume hierarchy.
- Event files are unique and immutable.
- Cursors advance only after the event file upload succeeds.
- A crash after event upload safely replays the overlap window.
- Downstream idempotency removes replayed logical events.
- Every completed or failed attempt writes a run record when Databricks remains
  reachable.
- Workflow concurrency prevents two scheduled workers from running together.

The Files API has no cross-file transaction here. These ordering rules make
delivery at-least-once and analytics idempotent without claiming exactly-once
delivery.
