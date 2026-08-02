# YouTube Connector

## Scope

The first live-source adapter collects public YouTube videos and, when enabled,
top-level comments and replies through YouTube Data API v3. It emits the same
versioned `SocialEventEnvelope` used by the deterministic demo connector.

The initial adapter is a bounded polling connector. YouTube channel push
notifications are a later optimization for known-channel uploads; topic and
keyword discovery still require polling.

For Databricks Free Edition, the recommended runtime is the external GitHub
Actions worker documented in [EXTERNAL_COLLECTOR.md](EXTERNAL_COLLECTOR.md).
This guide also retains the paused Databricks-native collection path for a
future workspace with approved outbound API access.

## Collection flow

```text
control_source_registry + control_collection_rules
    -> search.list for keyword or channel discovery
    -> videos.list for metadata and engagement statistics
    -> optional commentThreads.list
    -> optional comments.list for complete reply pages
    -> source-shaped immutable event envelopes
    -> /Volumes/<catalog>/<schema>/raw_social/events
    -> existing Auto Loader and Bronze/Silver/Gold pipeline
```

## Reliability behavior

- Every logical resource receives a stable idempotency key.
- Each rule advances its timestamp cursor only after the event file lands.
- Polls overlap the committed cursor by five minutes to absorb indexing delay.
- A crash after landing but before checkpoint commit causes a safe replay.
- HTTP 429, transport failures, and server errors use bounded exponential
  backoff with jitter.
- Authentication, malformed requests, disabled APIs, and exhausted provider
  quotas fail without retry loops.
- Videos with comments disabled remain valid video-only results.

## Quota controls

The runtime keeps separate persisted ledgers for the YouTube search bucket and
the general API bucket. It reserves capacity below the configured provider
limits and accounts for every HTTP attempt, including retries. Quota
reservations are persisted without advancing collection cursors so a failed
job cannot forget calls it already made.

The job defaults to:

- hourly collection;
- one search page per rule;
- a six-hour initial lookback;
- comments and replies disabled;
- five search calls and 500 general units held in reserve.

Review current limits in the
[official quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost)
before changing the schedule or rule count.

## Credential setup

Create a Google Cloud project, enable YouTube Data API v3, and create an API key
restricted to that API. Store the key in Databricks; never put it in bundle
variables, notebooks, source control, or job output.

The bundle defaults to this secret reference:

```text
scope: social-intelligence
key:   youtube-api-key
```

You can override both references during deployment:

```bash
databricks bundle deploy -t dev \
  --var="youtube_secret_scope=<scope>" \
  --var="youtube_secret_key=<key>" \
  --var="youtube_search_expression=Acme|GlowUpChallenge"
```

The API key is retrieved at runtime with `dbutils.secrets.get` and is never
returned by the connector's sanitized errors.

The bundle builds the connector package as a Python wheel and installs it in a
serverless job environment used only by the ingestion task. This keeps notebook
execution reproducible, avoids runtime source-path manipulation, and satisfies
Free Edition's serverless dependency model. Increment the package version when
the wheel changes so the serverless environment does not reuse a stale cache.

## Activate the job

The `social_intelligence_youtube_ingestion` job is deployed with its schedule
paused. It is an alternative to the external worker, not a companion job. After
credential setup:

1. Review the keyword expression and optional comma-separated channel IDs.
2. Keep comments disabled for the first quota and privacy validation run.
3. Deploy the bundle and run the job manually.
4. Verify raw events, checkpoint state, dead-letter rows, and source health.
5. Reconcile discovered videos against the YouTube UI for the pilot window.
6. Enable the hourly schedule only after the first run meets acceptance gates.

Do not enable this job when the GitHub Actions collector is enabled for the
same tenant and source. Both runtimes intentionally share a durable checkpoint.

Manual execution:

```bash
databricks bundle run social_intelligence_youtube_ingestion -t dev
```

## Checkpoint and landing locations

```text
/Volumes/<catalog>/<schema>/raw_social/events/youtube-<batch-id>.json
/Volumes/<catalog>/<schema>/raw_social/checkpoints/youtube/<tenant>/<source>.json
```

Checkpoint files contain cursors, quota counters, and operational metadata but
no API credentials or response payloads.

## Data and policy boundary

Public API availability does not remove provider-policy obligations. Before a
production pilot, approve the collected fields, retention period, deletion
workflow, authorized users, and whether comment text and public author channel
IDs are necessary. YouTube should be described as a sampled signal source, not
a complete global conversation feed.

Official references:

- [YouTube Data API overview](https://developers.google.com/youtube/v3/getting-started)
- [Search endpoint](https://developers.google.com/youtube/v3/docs/search/list)
- [Comments implementation](https://developers.google.com/youtube/v3/guides/implementation/comments)
- [Push notifications](https://developers.google.com/youtube/v3/guides/push_notifications)
