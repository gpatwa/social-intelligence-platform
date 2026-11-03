-- Collection-rule yield: which X rules (the keyword search and each account
-- handle) produce useful evidence per read.
-- Replace ${catalog}, ${schema}, and ${tenant_id} with deployed values.
-- Read-only. Requires silver_social_posts.collection_rule_id, which exists only
-- for posts ingested after that column was added; older rows report NULL.
--
-- Limits to keep in mind when reading the numbers:
--  * Delivery is deduplicated per logical post, so a post returned by two rules
--    is credited to only one. Overlap therefore undercounts a handle.
--  * One returned post is one billed read, so reads ~= posts landed (before
--    deduplication) and cost_usd is an estimate at the documented $0.005/read.
--  * is_on_topic is a coarse keyword heuristic, not a labelled judgement.
--    Calibrate it against a hand-labelled sample before dropping a handle.
WITH posts AS (
  SELECT
    p.event_id,
    p.author_id,
    p.engagements,
    p.collection_rule_id,
    lower(p.content_text) RLIKE
      'agent|langgraph|langchain|crewai|autogen|pydantic|mcp|eval|llm|openai|anthropic|rag|\\badk\\b' AS is_on_topic
  FROM ${catalog}.${schema}.silver_social_posts p
  WHERE p.tenant_id = '${tenant_id}'
    AND p.platform = 'x'
), cited AS (
  SELECT DISTINCT evidence_id
  FROM ${catalog}.${schema}.gold_ranked_evidence
  WHERE tenant_id = '${tenant_id}'
    AND evidence_rank <= 5
)
SELECT
  COALESCE(rules.rule_type, 'unattributed') AS rule_type,
  COALESCE(rules.expression, 'unknown (no collection_rule_id)') AS expression,
  COUNT(*) AS posts,
  ROUND(COUNT(*) * 0.005, 3) AS est_cost_usd,
  COUNT(DISTINCT posts.author_id) AS distinct_authors,
  ROUND(AVG(CASE WHEN posts.is_on_topic THEN 1.0 ELSE 0.0 END), 3) AS on_topic_share,
  COUNT_IF(cited.evidence_id IS NOT NULL) AS top5_evidence_posts,
  ROUND(
    COUNT(*) * 0.005 / NULLIF(COUNT_IF(posts.is_on_topic), 0), 4
  ) AS est_cost_per_on_topic_post_usd,
  ROUND(AVG(posts.engagements), 1) AS avg_engagements
FROM posts
LEFT JOIN ${catalog}.${schema}.control_collection_rules rules
  ON rules.tenant_id = '${tenant_id}'
 AND rules.rule_id = posts.collection_rule_id
LEFT JOIN cited ON cited.evidence_id = posts.event_id
GROUP BY rules.rule_type, rules.expression
ORDER BY top5_evidence_posts DESC, on_topic_share DESC;
