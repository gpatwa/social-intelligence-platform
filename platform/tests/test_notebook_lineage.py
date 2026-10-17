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


if __name__ == "__main__":
    unittest.main()
