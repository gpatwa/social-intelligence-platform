# Real Social Source Integration

The MVP currently uses deterministic demo data. Connect a real source only after selecting an approved provider and obtaining API credentials and retention approval.

## Connector contract

Every connector emits the versioned envelope implemented in
`src/social_intelligence/contracts.py`:

```text
event_id, schema_version, tenant_id, source_id, platform, event_type,
source_object_id, occurred_at, collected_at, idempotency_key,
correlation_id, payload, attributes
```

`payload` contains the immutable provider response. The mapping into canonical
post fields occurs in the data plane, allowing the original event to be replayed
after mapping or enrichment changes.

## Implementation sequence

1. Obtain written approval for the provider API, rate limits, fields, retention, and deletion requirements.
2. Store credentials in a cloud secret manager or Databricks secret scope.
   `control_source_registry` stores only the scope/key reference.
3. Register the source and contract, then add a webhook, streaming, or polling
   adapter that writes envelopes to `raw_social/events` or an external Unity
   Catalog location.
4. Replace the demo generator task while retaining initialization, Auto Loader,
   Silver, Gold, validation, dashboard, and alert tasks.
5. Add a post-deletion/tombstone flow and engagement snapshots for mutable metrics.
6. Verify `gold_source_health`, exercise dead-letter replay, compare source
   totals against the provider UI/API, and label at least 200 posts for model
   evaluation.

## Required configuration before activation

| Setting | Status |
|---|---|
| Provider/platform | User decision required |
| API credential secret scope/key | User decision required |
| Refresh cadence | Default recommendation: 15 minutes |
| Retention policy | Legal/compliance decision required |
| Brand and competitor dictionary | Business-owner input required |
| Alert recipients | User decision required |

## Implemented provider foundation

The YouTube Data API v3 polling adapter is implemented under
`src/social_intelligence/connectors/` with a paused Databricks job in
`resources/youtube_ingestion.job.yml`. It is fixture-tested and credential-free
in source control. See [YOUTUBE_CONNECTOR.md](YOUTUBE_CONNECTOR.md) for the
activation and policy checklist.
