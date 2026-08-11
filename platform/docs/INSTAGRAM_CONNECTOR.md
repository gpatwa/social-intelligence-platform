# Instagram connector

The Instagram connector uses the documented **Instagram Graph API** for the
Instagram Business account linked to a Facebook Page. It is an external,
checkpointed poller: GitHub Actions calls Meta, then writes immutable canonical
events, checkpoints, and run metrics to the Databricks volume through the Files
API.

## Supported scope

- The mandatory `account` rule collects media owned by the Business account
  linked to `INSTAGRAM_PAGE_ID`.
- Optional `hashtag` rules collect permitted recent media using Instagram's
  `ig_hashtag_search` then `recent_media` flow.
- Media snapshots include caption, permalink, media type, views when supplied,
  likes, comments, and extracted caption hashtags.
- This connector does not scrape public profiles, perform broad platform-wide
  discovery, or claim a global Instagram trends feed. Broader discovery needs a
  separately approved Meta product and an explicit product policy.

## Delivery semantics and safeguards

- The collector uses timestamp watermarks with a ten-minute replay overlap.
- It advances a rule checkpoint only after all configured pages are read and
  the immutable NDJSON event batch is safely uploaded.
- A per-run request limit, bounded retries for transient Graph API errors, and
  a durable request ledger cap unexpected use. Meta remains authoritative for
  API usage limits.
- Pagination past `INSTAGRAM_MAX_MEDIA_PAGES_PER_RULE` fails the run rather
  than silently skipping data.
- Events are at-least-once; downstream logical-event idempotency absorbs the
  replay window.

## Meta prerequisites

1. Create the Meta app and add **Facebook Login for Business** and the
   Instagram API use case.
2. Link an Instagram **Business** account to the Facebook Page used by this
   source. Personal and Creator accounts are not supported by this connector.
3. In development mode, use an app-role account. Request and approve the
   minimum permissions required for the intended data: `instagram_basic`,
   `instagram_manage_insights`, `pages_show_list`, and
   `pages_read_engagement`.
4. Obtain an access token with those permissions through Meta's supported
   authorization flow. Keep the token only in the GitHub Actions secret
   `INSTAGRAM_ACCESS_TOKEN`.

If Meta temporarily restricts Page linking or authorization, wait for the
restriction to clear before retrying. Do not work around the restriction with
scraping or an unapproved token.

## Configure the MVP

First deploy and run the governed source setup job:

```bash
cd platform
databricks bundle deploy -t dev --profile social-intelligence-free
databricks bundle run social_intelligence_instagram_source_setup -t dev \
  --profile social-intelligence-free
```

Add the secret in GitHub **Settings > Secrets and variables > Actions**:

| Secret | Value |
| --- | --- |
| `INSTAGRAM_ACCESS_TOKEN` | Meta access token for the Page-linked Business account |

Set these non-secret GitHub Actions variables:

| Variable | Default |
| --- | --- |
| `INSTAGRAM_SOURCE_ID` | `instagram-graph-api` |
| `INSTAGRAM_PAGE_ID` | Facebook Page ID linked to the Business account |
| `INSTAGRAM_HASHTAGS` | Empty comma-separated list |
| `INSTAGRAM_LOOKBACK_HOURS` | `24` |
| `INSTAGRAM_MAX_MEDIA_PAGES_PER_RULE` | `1` |
| `INSTAGRAM_MAX_REQUESTS_PER_RUN` | `100` |

The `Instagram collector` workflow is schedule-disabled until
`ENABLE_INSTAGRAM_COLLECTOR=true`. Once Page linkage and token authorization
work, run it manually first. Inspect its immutable event batch and run metric,
then run the existing `social_intelligence_external_ingestion` job:

```bash
databricks bundle run social_intelligence_external_ingestion -t dev \
  --profile social-intelligence-free
```

Validate `gold_connector_operations`, `bronze_social_events`,
`gold_trending_topics`, and `gold_source_health` before enabling hourly
collection. The external ingestion validator supports both YouTube's unit-based
quota metric and the request-headroom metric used by Instagram and X.
