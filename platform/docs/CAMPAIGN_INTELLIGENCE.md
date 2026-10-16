# Campaign Intelligence v1

Campaign Intelligence turns a human-approved, evidence-cited recommendation into a reviewable campaign experiment and closes the loop with **aggregate** control/treatment measurements. It is designed for the internal pilot—not autonomous campaign execution.

## What it does

1. Compiles a `campaign-experiment-v1` from an approved or edited `recommendation-review-v1`.
2. Requires explicit control, treatment, primary metric, comparison method, target lift, and time window.
3. Accepts only aggregate counts, value, and spend for the two arms.
4. Calculates observed conversion-rate lift conservatively.
5. Emits a feedback signal only after the v1 quality gate: at least 1,000 impressions and 25 conversions in **each** arm.
6. Lets a later `recommendation-context-v1` include that signal in an offline batch rerank. It does not update model weights automatically.

## Boundaries

- No identity resolution, customer profile, customer list, audience export, tracking pixel, raw conversion event, or provider credential is accepted.
- No ad-platform API call, budget change, creative publication, or campaign activation can occur.
- `RANDOMIZED_AB_TEST` and `HOLDOUT` produce a comparative observation; `PRE_POST` remains observational. All v1 outputs set `causality_claim` to `none`.
- A reviewer still performs the handoff and owns the execution-system setup.

## Internal-pilot flow

```text
social evidence → offline rerank → human review
  → campaign experiment draft → manual execution
  → aggregate measurement → quality-gated offline feedback
```

The Databricks data plane stores append-only experiment and measurement facts in `decision_campaign_experiments` and `decision_campaign_measurements`. The `15_build_campaign_intelligence.py` task produces `gold_campaign_intelligence` and `gold_campaign_intelligence_scorecard`, which are published to Snowflake for BA SQL users.

## CLI

```bash
social-intelligence-campaign-intelligence experiment experiment.json
social-intelligence-campaign-intelligence measurement measurement.json
social-intelligence-campaign-intelligence feedback measurement-output.json
```

The CLI and MCP tools compile validated artifacts only; they do not persist.

## Persistence: authenticated append boundary

`social-intelligence-record-append <review|outcome|experiment|measurement> artifact.json` is the single write path into the four append-only tables (`decision_recommendation_reviews`, `decision_recommendation_outcomes`, `decision_campaign_experiments`, `decision_campaign_measurements`). Implementation: `record_append.py`.

For every call it:

1. **Authenticates** a bearer token read from `SOCIAL_INTELLIGENCE_APPEND_TOKEN` (never an argument). `SOCIAL_INTELLIGENCE_APPEND_PRINCIPALS` holds a JSON list of `{actor_id, tenants, token_sha256}`; only SHA-256 digests are configured, never raw tokens. Missing or malformed configuration fails closed.
2. **Authorizes the tenant** against the principal's tenant list.
3. **Binds human attribution**: `reviewer_id`, `created_by`, or `reported_by` must equal the authenticated actor.
4. **Re-verifies the artifact** instead of trusting it: the deterministic ID is recomputed from its idempotency inputs; unknown top-level fields are rejected; `mutation` and `causality_claim` must be `none`; approved reviews must carry evidence citations; experiments must keep every activation, audience-export, and spend right off; measurements are checked for aggregate-only arm fields, recomputed rates, lift, quality-gate result, and feedback eligibility.
5. **Checks lineage in the same tenant**: outcomes and experiments require a stored *approved or edited* review for the same candidate; measurements require a stored experiment with matching review, candidate, method, and metric.
6. **Appends once**. An identical replay returns `DUPLICATE` with no write; the same key with different content raises a conflict. `--dry-run` authenticates and validates without writing.

`received_at` is assigned by the writer, not the caller. The Databricks store issues a parameterized insert-if-absent `MERGE` and re-reads the row to detect a concurrent conflicting writer. Required environment: `DATABRICKS_SERVER_HOSTNAME`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN`, optionally `SOCIAL_INTELLIGENCE_CATALOG` and `SOCIAL_INTELLIGENCE_SCHEMA`; install the `databricks` extra.

Status: unit-tested with an in-memory store and a fake SQL cursor. It has **not** been run against a live Databricks workspace; verify against staging with `--dry-run` and a throwaway tenant before storing real pilot decisions. It is a CLI/library boundary, not a network service; a hosted endpoint, SSO-backed identity, token rotation, and an audit sink are later steps.
