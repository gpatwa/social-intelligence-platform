# Databricks notebook source
"""Score the pilot topic rules against accepted gold labels (read-only reporting).

Reads silver_social_posts and reviewed_pilot_topic and writes three reporting
tables. It changes nothing that ranking or recommendations read: a topic is only
reported as rankable here, and slice 5 decides what to do with that flag.

Gold labels are human labels (always accepted) plus labels from labellers the
pilot owner listed in control_gold_labellers. The accepted model labeller is the
owner's explicit choice, recorded in that table, not a relabelling of provenance.
social_intelligence/topic_quality.py is the reference implementation of the
numbers; a live check compares the two.
"""

import re


dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("schema", "social_intelligence_dev")
dbutils.widgets.text("min_labelled", "40")
dbutils.widgets.text("min_precision_lower_bound", "0.7")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
min_labelled = int(dbutils.widgets.get("min_labelled"))
min_precision_lower_bound = float(dbutils.widgets.get("min_precision_lower_bound"))
for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")
if not 1 <= min_labelled <= 10000 or not 0.0 < min_precision_lower_bound < 1.0:
    raise ValueError("min_labelled must be 1-10000 and min_precision_lower_bound between 0 and 1")

ns = f"`{catalog}`.`{schema}`"
Z = 1.645  # one-sided 95%, same as the reference module

# One gold label per post: a human label beats a listed model labeller, then the
# latest label wins. Only posts the rules scored (live sources, tenants with rules).
spark.sql(
    f"""
    CREATE OR REPLACE TEMPORARY VIEW topic_quality_scored AS
    WITH accepted AS (
      SELECT labels.*
      FROM {ns}.`reviewed_pilot_topic` labels
      LEFT JOIN {ns}.`control_gold_labellers` gold
        ON gold.tenant_id = labels.tenant_id AND gold.labeller_id = labels.labeller_id
      WHERE labels.label_source = 'human' OR gold.labeller_id IS NOT NULL
    ), one_per_post AS (
      SELECT *, ROW_NUMBER() OVER (
        PARTITION BY tenant_id, platform, post_id
        ORDER BY CASE WHEN label_source = 'human' THEN 0 ELSE 1 END, labelled_at DESC, labeller_id
      ) AS row_num
      FROM accepted
    )
    SELECT
      gold.tenant_id,
      posts.pilot_taxonomy_version AS taxonomy_version,
      gold.platform,
      gold.post_id,
      gold.topic_label AS gold_topic,
      posts.pilot_topic_primary AS predicted_topic
    FROM one_per_post gold
    JOIN {ns}.`silver_social_posts` posts
      ON posts.tenant_id = gold.tenant_id AND posts.platform = gold.platform AND posts.post_id = gold.post_id
    WHERE gold.row_num = 1 AND posts.pilot_topic_primary IS NOT NULL
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_topic_quality`
    COMMENT 'Per-topic precision and recall of the pilot rules against accepted gold labels; rankable is a proposal gate, not a decision'
    AS
    WITH topics AS (
      SELECT tenant_id, taxonomy_version, gold_topic AS topic_id FROM topic_quality_scored
      UNION
      SELECT tenant_id, taxonomy_version, predicted_topic FROM topic_quality_scored
    ), counts AS (
      SELECT
        topics.tenant_id, topics.taxonomy_version, topics.topic_id,
        COUNT_IF(scored.gold_topic = topics.topic_id) AS labelled_n,
        COUNT_IF(scored.predicted_topic = topics.topic_id) AS predicted_n,
        COUNT_IF(scored.gold_topic = topics.topic_id AND scored.predicted_topic = topics.topic_id) AS true_positives
      FROM topics
      JOIN topic_quality_scored scored
        ON scored.tenant_id = topics.tenant_id AND scored.taxonomy_version = topics.taxonomy_version
      GROUP BY topics.tenant_id, topics.taxonomy_version, topics.topic_id
    ), bounded AS (
      SELECT
        *,
        CASE WHEN predicted_n > 0 THEN true_positives / predicted_n END AS precision,
        CASE WHEN labelled_n > 0 THEN true_positives / labelled_n END AS recall,
        CASE WHEN predicted_n > 0 THEN
          ((true_positives / predicted_n) + {Z} * {Z} / (2 * predicted_n)
            - {Z} * SQRT((true_positives / predicted_n) * (1 - true_positives / predicted_n) / predicted_n
                         + {Z} * {Z} / (4 * predicted_n * predicted_n)))
          / (1 + {Z} * {Z} / predicted_n)
        END AS precision_lower_bound
      FROM counts
    )
    SELECT
      bounded.tenant_id, bounded.taxonomy_version, bounded.topic_id,
      (SELECT CONCAT_WS(',', SORT_ARRAY(COLLECT_SET(g.labeller_id))) FROM {ns}.`control_gold_labellers` g
        WHERE g.tenant_id = bounded.tenant_id) AS accepted_model_labellers,
      labelled_n, predicted_n, true_positives, precision, precision_lower_bound, recall,
      labelled_n >= {min_labelled} AS meets_sample_size,
      COALESCE(precision_lower_bound >= {min_precision_lower_bound}, false) AS meets_precision,
      labelled_n >= {min_labelled}
        AND COALESCE(precision_lower_bound >= {min_precision_lower_bound}, false)
        AND topic_id NOT IN ('other', 'off_topic') AS rankable,
      CURRENT_TIMESTAMP() AS computed_at
    FROM bounded
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_topic_quality_summary`
    COMMENT 'Overall pilot topic quality against accepted gold labels'
    AS
    SELECT
      tenant_id, taxonomy_version,
      COUNT(*) AS gold_posts,
      COUNT_IF(gold_topic <> 'off_topic') AS on_topic_posts,
      COUNT_IF(gold_topic <> 'off_topic' AND gold_topic = predicted_topic)
        / NULLIF(COUNT_IF(gold_topic <> 'off_topic'), 0) AS primary_accuracy,
      COUNT_IF(gold_topic = 'off_topic') AS off_topic_posts,
      COUNT_IF(gold_topic = 'off_topic' AND predicted_topic <> 'other') AS off_topic_firing,
      COUNT_IF(predicted_topic = 'other') / COUNT(*) AS predicted_other_share,
      CURRENT_TIMESTAMP() AS computed_at
    FROM topic_quality_scored
    GROUP BY tenant_id, taxonomy_version
    """
)

# Rule yield: which rules fire, including enabled rules that never do.
spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_topic_rule_yield`
    COMMENT 'Posts matched per pilot rule, including rules with no matches'
    AS
    WITH totals AS (
      SELECT tenant_id, pilot_taxonomy_version AS taxonomy_version, COUNT(*) AS scored_posts
      FROM {ns}.`silver_social_posts`
      WHERE pilot_topic_primary IS NOT NULL
      GROUP BY tenant_id, pilot_taxonomy_version
    )
    SELECT
      rules.tenant_id, rules.taxonomy_version, rules.rule_id, rules.topic_id, rules.enabled,
      COUNT(topics.post_id) AS matches,
      COUNT(topics.post_id) / NULLIF(MAX(totals.scored_posts), 0) AS share_of_scored_posts,
      MAX(posts.created_at) AS last_matched_post_at,
      CURRENT_TIMESTAMP() AS computed_at
    FROM {ns}.`control_topic_rules` rules
    LEFT JOIN {ns}.`silver_post_topics` topics
      ON topics.tenant_id = rules.tenant_id AND topics.taxonomy_version = rules.taxonomy_version
         AND topics.rule_id = rules.rule_id
    LEFT JOIN {ns}.`silver_social_posts` posts
      ON posts.tenant_id = topics.tenant_id AND posts.platform = topics.platform AND posts.post_id = topics.post_id
    LEFT JOIN totals
      ON totals.tenant_id = rules.tenant_id AND totals.taxonomy_version = rules.taxonomy_version
    GROUP BY rules.tenant_id, rules.taxonomy_version, rules.rule_id, rules.topic_id, rules.enabled
    """
)

print(f"Topic quality reported in {catalog}.{schema} (gate: {min_labelled} labelled, lower bound {min_precision_lower_bound})")
