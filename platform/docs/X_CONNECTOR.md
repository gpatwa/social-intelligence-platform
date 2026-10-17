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

## Read budget

X bills pay-per-use per resource returned, so request counts alone do not bound
spend. The connector keeps a read ledger in its checkpoint and enforces it
before every call:

- Each returned post counts as one read. Each returned trend is also counted,
  because trend pricing is not published separately; this errs toward
  overcounting.
- A search page is requested only if at least 10 reads remain (the API
  minimum), and `max_results` is reduced to what remains, so a full page cannot
  exceed the budget. Trends requests are capped the same way.
- Billed reads are written to the checkpoint immediately after each response,
  so a later failure in the same run cannot hide spend.
- When the budget runs out, the run still succeeds and lands what it already
  read. Rules that were not fully read keep their cursors, so their window is
  collected once budget is available again. The run metric reports
  `read_budget_exhausted = 1`.
- Days and months are UTC calendar periods. The X billing cycle may differ, so
  the prepaid credit balance in the X Developer Console remains the hard
  ceiling. Keep automatic top-up off if a hard stop is required.
- Run metrics include `reads_used`, `reads_today`, `reads_remaining_today`,
  `reads_this_month`, `reads_remaining_month`, and `read_budget_exhausted`.

With the defaults, worst-case spend is 2,000 reads per day and 30,000 per
month; at $0.005 per post read (X pricing page, checked 2026-10-16) that is
about $10 per day and $150 per month.

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
   | `X_TRENDS_WOEID` | `2487956` (San Francisco); set `none` to disable trends |
   | `X_TRENDS_LOCATION` | `San Francisco` |
   | `X_MAX_TRENDS_PER_RUN` | `20` |
   | `X_LOOKBACK_HOURS` | `6` |
   | `X_MAX_SEARCH_PAGES_PER_RULE` | `1` |
   | `X_MAX_REQUESTS_PER_RUN` | `10` |
   | `X_MAX_RESULTS_PER_PAGE` | `100` (10-100) |
   | `X_DAILY_READ_BUDGET` | `2000` reads per UTC day |
   | `X_MONTHLY_READ_BUDGET` | `30000` reads per UTC calendar month (at most 3,000,000) |

   Supply at least one query, hashtag, account handle, or trends WOEID. Keep
   `ENABLE_X_COLLECTOR` unset until a manual run has passed validation.

4. Run **X collector** manually in GitHub Actions. Then run the existing
   `social_intelligence_external_ingestion` job and validate the X source in
   `gold_connector_operations`, `bronze_social_events`,
   `gold_trending_topics`, and `gold_source_health` before setting
   `ENABLE_X_COLLECTOR=true`.

The bearer token, Databricks token, payloads, checkpoints, and volume paths are
never published to the landing page status endpoint.
