# Databricks notebook source
"""Materialize reviewer adoption and outcome feedback for the internal pilot.

This is an internal-pilot scorecard, not an autonomous activation service. It
reads append-only human review and observational outcome facts, preserving the
manual-handoff and non-causal boundaries of recommendation-review-v1.
"""

import re


dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("schema", "social_intelligence_dev")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")

ns = f"`{catalog}`.`{schema}`"

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_recommendation_review_outcomes`
    COMMENT 'Approved recommendation reviews joined to observational outcome measurements; no causal attribution'
    AS
    SELECT
      reviews.tenant_id,
      reviews.review_id,
      reviews.rerank_id,
      reviews.context_id,
      reviews.decision_id,
      reviews.decision,
      reviews.status AS review_status,
      reviews.selected_candidate_id,
      reviews.selected_candidate_rank,
      reviews.evidence_ids_json,
      reviews.handoff_state,
      reviews.reviewed_at,
      outcomes.outcome_id,
      outcomes.metric_name,
      outcomes.observed_value,
      outcomes.baseline_value,
      CASE WHEN outcomes.baseline_value IS NOT NULL
        THEN outcomes.observed_value - outcomes.baseline_value END AS observed_delta,
      outcomes.unit,
      outcomes.measurement_window_days,
      outcomes.measurement_source,
      outcomes.confidence,
      outcomes.attribution,
      outcomes.observed_at,
      outcomes.received_at AS outcome_received_at
    FROM {ns}.`decision_recommendation_reviews` reviews
    LEFT JOIN {ns}.`decision_recommendation_outcomes` outcomes
      ON reviews.tenant_id = outcomes.tenant_id
     AND reviews.review_id = outcomes.review_id
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_recommendation_review_scorecard`
    COMMENT 'Tenant-level human adoption, edit, rejection, and observational outcome coverage for internal pilot gating'
    AS
    WITH review_metrics AS (
      SELECT
        tenant_id,
        COUNT(*) AS reviews_total,
        COUNT_IF(status = 'APPROVED_FOR_HANDOFF') AS approved_total,
        COUNT_IF(status = 'EDITED_FOR_HANDOFF') AS edited_total,
        COUNT_IF(status = 'REJECTED') AS rejected_total,
        COUNT_IF(status IN ('APPROVED_FOR_HANDOFF', 'EDITED_FOR_HANDOFF')) AS accepted_total
      FROM {ns}.`decision_recommendation_reviews`
      GROUP BY tenant_id
    ), outcome_metrics AS (
      SELECT
        tenant_id,
        COUNT(*) AS outcomes_total,
        COUNT(DISTINCT review_id) AS reviews_with_outcomes,
        AVG(CASE WHEN baseline_value IS NOT NULL THEN observed_value - baseline_value END) AS avg_observed_delta
      FROM {ns}.`decision_recommendation_outcomes`
      GROUP BY tenant_id
    )
    SELECT
      review_metrics.tenant_id,
      reviews_total,
      approved_total,
      edited_total,
      rejected_total,
      accepted_total,
      CASE WHEN reviews_total > 0 THEN ROUND(accepted_total / reviews_total, 4) ELSE 0.0 END AS acceptance_rate,
      COALESCE(outcomes_total, 0) AS outcomes_total,
      COALESCE(reviews_with_outcomes, 0) AS reviews_with_outcomes,
      CASE WHEN accepted_total > 0 THEN ROUND(COALESCE(reviews_with_outcomes, 0) / accepted_total, 4) ELSE 0.0 END AS outcome_coverage_rate,
      avg_observed_delta,
      'INTERNAL_PILOT' AS stage,
      'DISABLED' AS automation_status,
      CURRENT_TIMESTAMP() AS evaluated_at
    FROM review_metrics
    LEFT JOIN outcome_metrics USING (tenant_id)
    """
)

for table_name in ("gold_recommendation_review_outcomes", "gold_recommendation_review_scorecard"):
    print(f"{catalog}.{schema}.{table_name}: {spark.table(f'{catalog}.{schema}.{table_name}').count():,} rows")
