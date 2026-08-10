# X connector

The X connector uses the X API v2 **Recent Search** and **Trends by WOEID**
endpoints as polling sources. It maps Posts and location-specific trend
snapshots into the versioned `SocialEventEnvelope`, preserves provider payloads
for replay, and lands immutable NDJSON in the governed Databricks volume
through the external collector pattern.

## Scope and delivery semantics

- Supported rules: `keyword` (an X query), `hashtag`, `account`, and the
  location-scoped `trend` rule derived from `X_TRENDS_WOEID`.
- Recent Search covers the provider's rolling seven-day window. It is not a
  backfill service.
- Each cursor uses a timestamp watermark with a five-minute replay overlap.
- Pagination must complete before the checkpoint moves; reaching the configured
  page cap fails the run rather than losing posts.
- The initial implementation is polling. Filtered-stream delivery is a later,
  separately operated connector mode.
- The external worker has a conservative per-run request budget. Configure it
  below the rate limits actually assigned to the approved X project; the
  provider remains authoritative.
- The San Francisco pilot uses WOEID `2487956`, requests at most 20 trend
  observations per hourly run, and makes one Trends API request. It does **not**
  automatically fan out into broad post searches; that is an explicit future
  policy decision to prevent unpredictable spend.

## Configure

1. Create an approved X developer project and app, then retain its bearer token
   only in GitHub Actions secret `X_BEARER_TOKEN`.
2. Deploy the bundle and create the governed source registration:

   ```bash
   cd platform
   databricks bundle deploy -t dev --profile social-intelligence-free
   databricks bundle run social_intelligence_x_source_setup -t dev \
     --profile social-intelligence-free
   ```

3. Set these non-secret GitHub Actions variables:

   | Variable | Default |
   | --- | --- |
   | `X_SOURCE_ID` | `x-api-v2` |
   | `X_SEARCH_EXPRESSION` | empty |
   | `X_HASHTAGS` | empty comma-separated list |
   | `X_ACCOUNT_HANDLES` | empty comma-separated list |
   | `X_TRENDS_WOEID` | `2487956` (San Francisco) |
   | `X_TRENDS_LOCATION` | `San Francisco` |
   | `X_MAX_TRENDS_PER_RUN` | `20` |
   | `X_LOOKBACK_HOURS` | `6` |
   | `X_MAX_SEARCH_PAGES_PER_RULE` | `1` |
   | `X_MAX_REQUESTS_PER_RUN` | `10` |

   Supply at least one query, hashtag, account handle, or trends WOEID. Keep
   `ENABLE_X_COLLECTOR` unset until a manual run has passed validation.

4. Run **X collector** manually in GitHub Actions. Then run the existing
   `social_intelligence_external_ingestion` job and validate the X source in
   `gold_connector_operations`, `bronze_social_events`,
   `gold_trending_topics`, and `gold_source_health` before setting
   `ENABLE_X_COLLECTOR=true`.

The bearer token, Databricks token, payloads, checkpoints, and volume paths are
never published to the landing page status endpoint.
