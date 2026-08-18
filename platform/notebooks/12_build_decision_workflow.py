# Databricks notebook source
"""Convert governed signals into an auditable recommendation/experiment loop.

Opportunities are reproducible Gold projections. Recommendation, experiment,
and learning tables are durable lifecycle records created in the control-plane
initializer and are advanced only through explicit state gates.
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

# Opportunity IDs are stable across reruns for the same daily signal/product
# pair. Explicit product maps prevent the model from inventing catalog links.
spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_opportunities`
    COMMENT 'Prioritized commercial opportunities with product fit and source evidence lineage'
    AS
    WITH candidates AS (
      SELECT
        signals.tenant_id,
        signals.signal_type,
        signals.signal_key,
        signals.signal_ts,
        signals.score AS signal_score,
        signals.severity,
        signals.summary AS signal_summary,
        signals.evidence_count,
        signals.source_table,
        mapping.product_id,
        products.product_name,
        COALESCE(mapping.product_fit, 0.20) AS product_fit,
        COALESCE(mapping.commercial_fit, 0.20) AS commercial_fit,
        mapping.target_audience,
        COALESCE(mapping.preferred_channel, 'analyst-review') AS preferred_channel
      FROM {ns}.`gold_signal_feed` signals
      LEFT JOIN {ns}.`control_signal_product_map` mapping
        ON signals.tenant_id = mapping.tenant_id
       AND LOWER(signals.signal_key) = LOWER(mapping.signal_key)
       AND mapping.active
      LEFT JOIN {ns}.`control_product_catalog` products
        ON mapping.tenant_id = products.tenant_id
       AND mapping.product_id = products.product_id
       AND products.active
    ), scored AS (
      SELECT
        *,
        LEAST(1.0, LOG1P(GREATEST(evidence_count, 0)) / LOG1P(100)) AS evidence_strength,
        CASE WHEN signal_type = 'brand_risk' THEN 'DEFEND' ELSE 'GROW' END AS opportunity_type
      FROM candidates
    )
    SELECT
      SHA2(CONCAT_WS('|', tenant_id, signal_type, signal_key,
                    COALESCE(product_id, 'unmapped'), CAST(CAST(signal_ts AS DATE) AS STRING)), 256)
        AS opportunity_id,
      tenant_id,
      opportunity_type,
      signal_type,
      signal_key,
      signal_ts,
      product_id,
      product_name,
      preferred_channel,
      target_audience,
      signal_score,
      evidence_count,
      product_fit,
      commercial_fit,
      ROUND(LEAST(100.0, GREATEST(0.0, 100.0 * (
          0.55 * LEAST(1.0, GREATEST(0.0, signal_score / 100.0))
        + 0.15 * evidence_strength
        + 0.20 * product_fit
        + 0.10 * commercial_fit
      ))), 2) AS opportunity_score,
      ROUND(LEAST(100.0, GREATEST(0.0, 100.0 * (
          0.45 * LEAST(1.0, GREATEST(0.0, signal_score / 100.0))
        + 0.20 * evidence_strength
        + 0.20 * product_fit
        + 0.15 * commercial_fit
      ))), 2) AS confidence_score,
      CASE
        WHEN product_id IS NULL THEN 'NEEDS_MAPPING'
        WHEN signal_score >= 45 THEN 'OPEN'
        ELSE 'WATCH'
      END AS status,
      CONCAT(
        CASE WHEN signal_type = 'brand_risk' THEN 'Protect ' ELSE 'Test ' END,
        COALESCE(product_name, signal_key), ': ', signal_summary
      ) AS title,
      TO_JSON(NAMED_STRUCT(
        'signal_type', signal_type,
        'signal_key', signal_key,
        'signal_ts', signal_ts,
        'source_table', source_table,
        'evidence_count', evidence_count
      )) AS evidence_ref,
      signal_ts AS first_detected_at,
      CASE
        WHEN signal_type = 'brand_risk' THEN signal_ts + INTERVAL 2 DAYS
        ELSE signal_ts + INTERVAL 7 DAYS
      END AS expires_at,
      CURRENT_TIMESTAMP() AS refreshed_at
    FROM scored
    """
)

# The generator proposes only mapped, material opportunities. A rerun can
# refresh untouched proposals but cannot overwrite an approval or rejection.
spark.sql(
    f"""
    MERGE INTO {ns}.`decision_recommendations` AS target
    USING (
      SELECT
        SHA2(CONCAT_WS('|', opportunity_id, 'recommendation-v1'), 256) AS recommendation_id,
        tenant_id,
        opportunity_id,
        product_id,
        CASE WHEN opportunity_type = 'DEFEND' THEN 'BRAND_RESPONSE' ELSE 'CREATIVE_TEST' END AS action_type,
        preferred_channel AS channel,
        target_audience,
        CASE
          WHEN opportunity_type = 'DEFEND'
            THEN CONCAT('Addressing ', signal_key, ' with evidence-led guidance will reduce negative conversation.')
          ELSE CONCAT('A ', signal_key, '-aligned creative for ', product_name,
                      ' will outperform the current control with the target audience.')
        END AS hypothesis,
        CASE
          WHEN opportunity_type = 'DEFEND'
            THEN CONCAT('Lead with the verified customer concern, the corrective action, and a measurable support path. Evidence: ', evidence_ref)
          ELSE CONCAT('Build one control and one treatment around ', signal_key,
                      '. Keep offer, audience, placement, and budget constant. Evidence: ', evidence_ref)
        END AS creative_brief,
        CASE WHEN opportunity_type = 'DEFEND' THEN 'negative_share' ELSE 'conversion_rate' END AS primary_metric,
        confidence_score,
        'PROPOSED' AS status,
        evidence_ref,
        CURRENT_TIMESTAMP() AS created_at,
        CURRENT_TIMESTAMP() AS updated_at
      FROM {ns}.`gold_opportunities`
      WHERE status = 'OPEN' AND opportunity_score >= 45
    ) AS incoming
    ON target.recommendation_id = incoming.recommendation_id
    WHEN MATCHED AND target.status = 'PROPOSED' THEN UPDATE SET
      channel = incoming.channel,
      target_audience = incoming.target_audience,
      hypothesis = incoming.hypothesis,
      creative_brief = incoming.creative_brief,
      primary_metric = incoming.primary_metric,
      confidence_score = incoming.confidence_score,
      evidence_ref = incoming.evidence_ref,
      updated_at = incoming.updated_at
    WHEN NOT MATCHED THEN INSERT (
      recommendation_id, tenant_id, opportunity_id, product_id, action_type,
      channel, target_audience, hypothesis, creative_brief, primary_metric,
      confidence_score, status, evidence_ref, created_at, updated_at,
      decided_by, decision_reason
    ) VALUES (
      incoming.recommendation_id, incoming.tenant_id, incoming.opportunity_id,
      incoming.product_id, incoming.action_type, incoming.channel,
      incoming.target_audience, incoming.hypothesis, incoming.creative_brief,
      incoming.primary_metric, incoming.confidence_score, incoming.status,
      incoming.evidence_ref, incoming.created_at, incoming.updated_at, NULL, NULL
    )
    """
)

# Approval is the only gate that creates an experiment record. The experiment
# remains PLANNED until an execution system supplies budget, dates, and variants.
spark.sql(
    f"""
    MERGE INTO {ns}.`decision_experiments` AS target
    USING (
      SELECT
        SHA2(CONCAT_WS('|', recommendation_id, 'experiment-v1'), 256) AS experiment_id,
        tenant_id,
        recommendation_id,
        'PLANNED' AS status,
        primary_metric,
        'contribution_margin' AS guardrail_metric,
        10.0 AS target_lift_pct,
        'Current best-performing eligible creative' AS control_definition,
        creative_brief AS treatment_definition,
        0.0 AS planned_budget,
        CURRENT_TIMESTAMP() AS created_at,
        CURRENT_TIMESTAMP() AS updated_at
      FROM {ns}.`decision_recommendations`
      WHERE status = 'APPROVED'
    ) AS incoming
    ON target.experiment_id = incoming.experiment_id
    WHEN NOT MATCHED THEN INSERT (
      experiment_id, tenant_id, recommendation_id, status, primary_metric,
      guardrail_metric, target_lift_pct, control_definition,
      treatment_definition, planned_budget, actual_spend, control_conversions,
      treatment_conversions, control_revenue, treatment_revenue, start_at,
      end_at, created_at, updated_at
    ) VALUES (
      incoming.experiment_id, incoming.tenant_id, incoming.recommendation_id,
      incoming.status, incoming.primary_metric, incoming.guardrail_metric,
      incoming.target_lift_pct, incoming.control_definition,
      incoming.treatment_definition, incoming.planned_budget, NULL, NULL,
      NULL, NULL, NULL, NULL, NULL, incoming.created_at, incoming.updated_at
    )
    """
)

spark.sql(
    f"""
    MERGE INTO {ns}.`decision_recommendations` AS target
    USING (
      SELECT
        recommendation_id,
        CASE status
          WHEN 'PLANNED' THEN 'EXPERIMENT_PLANNED'
          WHEN 'RUNNING' THEN 'RUNNING'
          WHEN 'COMPLETED' THEN 'COMPLETED'
          WHEN 'CANCELLED' THEN 'CANCELLED'
        END AS recommendation_status
      FROM {ns}.`decision_experiments`
      WHERE status IN ('PLANNED', 'RUNNING', 'COMPLETED', 'CANCELLED')
    ) AS incoming
    ON target.recommendation_id = incoming.recommendation_id
    WHEN MATCHED AND incoming.recommendation_status IS NOT NULL THEN UPDATE SET
      status = incoming.recommendation_status,
      updated_at = CURRENT_TIMESTAMP()
    """
)

# A completed experiment with revenue inputs closes the loop automatically.
# Confidence remains DIRECTIONAL until the execution adapter supplies sample
# sizes required for statistical inference.
spark.sql(
    f"""
    MERGE INTO {ns}.`decision_learnings` AS target
    USING (
      SELECT
        SHA2(CONCAT_WS('|', experiments.experiment_id, 'learning-v1'), 256) AS learning_id,
        experiments.tenant_id,
        experiments.experiment_id,
        experiments.recommendation_id,
        CASE
          WHEN experiments.treatment_revenue > experiments.control_revenue THEN 'WIN'
          WHEN experiments.treatment_revenue = experiments.control_revenue THEN 'INCONCLUSIVE'
          ELSE 'LOSS'
        END AS outcome,
        CASE WHEN experiments.control_revenue > 0 THEN ROUND(
          100.0 * (experiments.treatment_revenue - experiments.control_revenue)
          / experiments.control_revenue, 2
        ) END AS measured_lift_pct,
        experiments.treatment_revenue - experiments.control_revenue AS incremental_revenue,
        ROUND(
          (experiments.treatment_revenue - experiments.control_revenue)
            * COALESCE(products.gross_margin_rate, 0.0)
          - COALESCE(experiments.actual_spend, 0.0),
          2
        ) AS contribution_margin,
        'DIRECTIONAL' AS confidence_level,
        CONCAT(
          recommendations.hypothesis, ' Outcome: ',
          CASE
            WHEN experiments.treatment_revenue > experiments.control_revenue THEN 'WIN'
            WHEN experiments.treatment_revenue = experiments.control_revenue THEN 'INCONCLUSIVE'
            ELSE 'LOSS'
          END,
          '. Reuse only for comparable product, audience, channel, and offer contexts.'
        ) AS reusable_insight,
        CURRENT_TIMESTAMP() AS recorded_at,
        'decision-engine' AS recorded_by
      FROM {ns}.`decision_experiments` experiments
      INNER JOIN {ns}.`decision_recommendations` recommendations
        ON experiments.recommendation_id = recommendations.recommendation_id
      LEFT JOIN {ns}.`control_product_catalog` products
        ON recommendations.tenant_id = products.tenant_id
       AND recommendations.product_id = products.product_id
      WHERE experiments.status = 'COMPLETED'
        AND experiments.control_revenue IS NOT NULL
        AND experiments.treatment_revenue IS NOT NULL
    ) AS incoming
    ON target.learning_id = incoming.learning_id
    WHEN NOT MATCHED THEN INSERT *
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_experiment_performance`
    COMMENT 'Experiment execution and measured commercial outcomes with recommendation context'
    AS
    SELECT
      experiments.tenant_id,
      experiments.experiment_id,
      experiments.recommendation_id,
      recommendations.opportunity_id,
      recommendations.product_id,
      recommendations.action_type,
      recommendations.channel,
      experiments.status,
      experiments.primary_metric,
      experiments.target_lift_pct,
      experiments.planned_budget,
      experiments.actual_spend,
      experiments.control_conversions,
      experiments.treatment_conversions,
      experiments.control_revenue,
      experiments.treatment_revenue,
      learnings.outcome,
      learnings.measured_lift_pct,
      learnings.incremental_revenue,
      learnings.contribution_margin,
      learnings.confidence_level,
      experiments.start_at,
      experiments.end_at,
      experiments.updated_at
    FROM {ns}.`decision_experiments` experiments
    INNER JOIN {ns}.`decision_recommendations` recommendations
      ON experiments.recommendation_id = recommendations.recommendation_id
    LEFT JOIN {ns}.`decision_learnings` learnings
      ON experiments.experiment_id = learnings.experiment_id
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_pilot_scorecard`
    COMMENT 'Tenant-level adoption, experiment velocity, win rate, and commercial impact for pilot evaluation'
    AS
    WITH tenants AS (
      SELECT DISTINCT tenant_id FROM {ns}.`gold_opportunities`
      UNION
      SELECT DISTINCT tenant_id FROM {ns}.`decision_recommendations`
    ), opportunity_metrics AS (
      SELECT tenant_id,
             COUNT(*) AS opportunities_detected,
             COUNT_IF(status = 'OPEN') AS opportunities_open,
             COUNT_IF(status = 'NEEDS_MAPPING') AS opportunities_needing_mapping
      FROM {ns}.`gold_opportunities`
      GROUP BY tenant_id
    ), recommendation_metrics AS (
      SELECT tenant_id,
             COUNT(*) AS recommendations_total,
             COUNT_IF(status NOT IN ('PROPOSED', 'REJECTED')) AS recommendations_adopted,
             COUNT_IF(status = 'REJECTED') AS recommendations_rejected
      FROM {ns}.`decision_recommendations`
      GROUP BY tenant_id
    ), experiment_metrics AS (
      SELECT tenant_id,
             COUNT(*) AS experiments_total,
             COUNT_IF(status = 'COMPLETED') AS experiments_completed
      FROM {ns}.`decision_experiments`
      GROUP BY tenant_id
    ), learning_metrics AS (
      SELECT tenant_id,
             COUNT(*) AS learnings_total,
             COUNT_IF(outcome = 'WIN') AS winning_experiments,
             AVG(measured_lift_pct) AS avg_measured_lift_pct,
             SUM(incremental_revenue) AS incremental_revenue,
             SUM(contribution_margin) AS contribution_margin
      FROM {ns}.`decision_learnings`
      GROUP BY tenant_id
    )
    SELECT
      tenants.tenant_id,
      COALESCE(opportunities_detected, 0) AS opportunities_detected,
      COALESCE(opportunities_open, 0) AS opportunities_open,
      COALESCE(opportunities_needing_mapping, 0) AS opportunities_needing_mapping,
      COALESCE(recommendations_total, 0) AS recommendations_total,
      COALESCE(recommendations_adopted, 0) AS recommendations_adopted,
      COALESCE(recommendations_rejected, 0) AS recommendations_rejected,
      CASE WHEN COALESCE(recommendations_total, 0) > 0 THEN ROUND(
        100.0 * COALESCE(recommendations_adopted, 0) / recommendations_total, 2
      ) ELSE 0.0 END AS recommendation_adoption_rate_pct,
      COALESCE(experiments_total, 0) AS experiments_total,
      COALESCE(experiments_completed, 0) AS experiments_completed,
      COALESCE(learnings_total, 0) AS learnings_total,
      COALESCE(winning_experiments, 0) AS winning_experiments,
      CASE WHEN COALESCE(learnings_total, 0) > 0 THEN ROUND(
        100.0 * COALESCE(winning_experiments, 0) / learnings_total, 2
      ) ELSE 0.0 END AS experiment_win_rate_pct,
      avg_measured_lift_pct,
      COALESCE(incremental_revenue, 0.0) AS incremental_revenue,
      COALESCE(contribution_margin, 0.0) AS contribution_margin,
      CURRENT_TIMESTAMP() AS evaluated_at
    FROM tenants
    LEFT JOIN opportunity_metrics USING (tenant_id)
    LEFT JOIN recommendation_metrics USING (tenant_id)
    LEFT JOIN experiment_metrics USING (tenant_id)
    LEFT JOIN learning_metrics USING (tenant_id)
    """
)

for table_name in (
    "gold_opportunities",
    "decision_recommendations",
    "decision_experiments",
    "decision_learnings",
    "gold_experiment_performance",
    "gold_pilot_scorecard",
):
    count = spark.table(f"{catalog}.{schema}.{table_name}").count()
    print(f"{catalog}.{schema}.{table_name}: {count:,} rows")
