# Demo Validation Result

Executed against `dev.social_intelligence_dev` on 2026-07-30.

| Acceptance signal | Observed result | Outcome |
|---|---:|---|
| Registered sources | 3 | Control-plane source registry active |
| Raw event envelopes | 943 | Replayable event ingestion working |
| Rejected events | 0 | Contract validation passed |
| Canonical posts | 943 | Idempotent mapping produced no loss |
| Healthy sources | 3 of 3 | Freshness and source SLO checks passed |
| Unified experience signals | 7 | Stable serving contract populated |
| Highest trend score | 52.54 | Emerging trend detected |
| Highest challenge score | 56.64 | Challenge detection working |
| High-risk brand mentions | 117 | Brand-risk signal detected |
| Human-review candidates | 100 | Review workflow ready |

The successful five-stage workflow run is
[130289422145060](https://dbc-b8672746-8e43.cloud.databricks.com/jobs/1017457148250254/runs/130289422145060?o=7474657828954669).
The demo intentionally creates a growing `GlowUpChallenge` and an Acme
battery-risk narrative. These results validate that control metadata, event
contracts, replayable ingestion, tenant isolation, scoring, source health,
dashboard datasets, and alert thresholds are connected end to end.

The alert threshold is temporarily set to 45 for the small seeded demo. Recalibrate it using at least 30 days of real-source history before production.
