import unittest
from pathlib import Path

NOTEBOOKS = Path(__file__).resolve().parents[1] / "notebooks"


def read(name):
    return (NOTEBOOKS / name).read_text(encoding="utf-8")


class OpportunityLineageTests(unittest.TestCase):
    """Static guards: Spark is not available in unit tests, so these pin the
    contract that recommendation lineage is checked against durable history."""

    def test_validations_join_durable_history_not_the_rebuilt_snapshot(self):
        for name in ("03_validate_product.py", "08_validate_external_ingestion.py"):
            source = read(name)
            self.assertIn("`decision_opportunity_history` opportunities", source, name)
            self.assertNotIn("LEFT JOIN {ns}.`gold_opportunities` opportunities", source, name)
            self.assertNotIn("LEFT JOIN {namespace}.`gold_opportunities` opportunities", source, name)

    def test_history_is_captured_before_recommendations_reference_it(self):
        source = read("12_build_decision_workflow.py")
        capture = source.index("MERGE INTO {ns}.`decision_opportunity_history`")
        rebuild = source.index("CREATE OR REPLACE TABLE {ns}.`gold_opportunities`")
        recommend = source.index("MERGE INTO {ns}.`decision_recommendations`")
        self.assertLess(rebuild, capture)
        self.assertLess(capture, recommend)

    def test_backfill_is_limited_to_recommendations_before_first_capture(self):
        source = read("00_initialize_platform.py")
        table = source.index("CREATE TABLE IF NOT EXISTS {ns}.`decision_opportunity_history`")
        backfill = source.index("'recommendation_backfill'")
        self.assertLess(source.index("CREATE TABLE IF NOT EXISTS {ns}.`decision_recommendations`"), backfill)
        self.assertLess(table, backfill)
        self.assertIn("WHERE recorded_from = 'gold_opportunities'", source)
        self.assertIn("WHEN NOT MATCHED THEN INSERT", source[backfill - 2000 : backfill])


class CollectionRuleAttributionTests(unittest.TestCase):
    """Static guards: the rule that fetched a post must reach Silver so rule
    yield can be measured, and the yield query must stay tenant-scoped."""

    def test_silver_carries_the_collection_rule_id_from_bronze(self):
        source = read("02_build_analytics.py")
        self.assertIn("event_attributes['rule_id'] AS collection_rule_id", source)
        self.assertLess(
            source.index("CREATE OR REPLACE TABLE {ns}.`silver_social_posts`"),
            source.index("event_attributes['rule_id'] AS collection_rule_id"),
        )

    def test_handle_yield_query_is_read_only_and_tenant_scoped(self):
        raw = (NOTEBOOKS.parent / "sql" / "x_handle_yield.sql").read_text(encoding="utf-8")
        query = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))
        for keyword in ("INSERT", "UPDATE", "DELETE", "DROP", "MERGE", "CREATE", "ALTER"):
            self.assertNotRegex(query.upper(), rf"\b{keyword}\b", keyword)
        # silver posts, gold evidence, and collection rules are each tenant-filtered
        self.assertEqual(query.count("tenant_id = '${tenant_id}'"), 3)
        for table in ("silver_social_posts", "gold_ranked_evidence", "control_collection_rules"):
            self.assertIn(table, query)


class GitHubAdoptionBoundaryTests(unittest.TestCase):
    """Static guards: GitHub repo rows are adoption signals and must not reach
    the post score or any post-based Gold table."""

    def test_post_table_excludes_github_and_repo_table_includes_only_github(self):
        source = read("02_build_analytics.py")
        posts = source[source.index("`silver_social_posts`\n    COMMENT"):]
        posts = posts[: posts.index("FROM deduplicated")]
        self.assertIn("AND platform <> 'github'", posts)
        repo = source[source.index("`silver_repo_activity`\n    COMMENT"):]
        repo = repo[: repo.index("FROM deduplicated")]
        self.assertIn("AND platform = 'github'", repo)

    def test_only_the_adoption_view_reads_repo_activity(self):
        source = read("02_build_analytics.py")
        start = source.index("CREATE OR REPLACE TABLE {ns}.`gold_repo_adoption`")
        end = source.index("CREATE OR REPLACE TABLE {ns}.`gold_content_performance`")
        outside = source[:start] + source[end:]
        # the validation count list names the table; no SQL reads it elsewhere
        self.assertNotIn("FROM {ns}.`silver_repo_activity`", outside)
        self.assertNotIn("JOIN {ns}.`silver_repo_activity`", outside)

    def test_adoption_view_is_tenant_partitioned_and_growth_is_not_imputed(self):
        source = read("02_build_analytics.py")
        view = source[source.index("`gold_repo_adoption`\n    COMMENT"):]
        view = view[: view.index("FROM latest")]
        self.assertIn("PARTITION BY tenant_id, repo_full_name", view)
        self.assertNotIn("COALESCE(latest.stars - baseline", view)
        self.assertNotIn("score", view.lower().replace("snapshot", ""))


if __name__ == "__main__":
    unittest.main()
