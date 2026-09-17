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

The CLI and MCP tools compile validated artifacts only. An authenticated, idempotent append boundary is the next production-readiness slice before persisting real pilot decisions.
