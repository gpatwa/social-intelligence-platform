import re
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[1]


def read(relative):
    return (PLATFORM / relative).read_text(encoding="utf-8")


class DemoResetSafetyTests(unittest.TestCase):
    """Static guards: Spark is unavailable in unit tests, so these pin the
    contracts that stop the demo job from destroying live collector data."""

    def test_demo_job_is_not_scheduled(self):
        job = read("resources/social_intelligence.job.yml")
        schedule = job[job.index("schedule:"):]
        self.assertRegex(schedule, r"pause_status:\s*PAUSED")
        self.assertNotRegex(schedule, r"pause_status:\s*UNPAUSED")

    def test_reset_is_guarded_before_any_destructive_statement(self):
        source = read("notebooks/01_generate_demo_data.py")
        guard = source.index("Refusing to reset the raw data plane")
        for destructive in ("DROP TABLE IF EXISTS", "dbutils.fs.rm("):
            self.assertLess(guard, source.index(destructive), destructive)
        for prefix in ('"youtube-"', '"x-"', '"instagram-"', '"reddit-"'):
            self.assertIn(prefix, source)
        self.assertIn('allow_destructive_reset', source)

    def test_collector_batch_names_match_the_guard_prefixes(self):
        # The guard only protects files the collectors actually write.
        for module, prefix in (("external_youtube", "youtube-"), ("external_x", "x-"), ("external_instagram", "instagram-")):
            source = read(f"src/social_intelligence/connectors/{module}.py")
            self.assertIn(f"/events/{prefix}{{run_id}}.json", source, module)


class FreshnessThresholdTests(unittest.TestCase):
    def test_threshold_is_parameterized_end_to_end(self):
        notebook = read("notebooks/08_validate_external_ingestion.py")
        self.assertIn("run_age_minutes <= {max_age_minutes}", notebook)
        self.assertNotIn("run_age_minutes <= 180", notebook)
        self.assertIn("max_collection_age_minutes", read("resources/external_ingestion.job.yml"))
        bundle = read("databricks.yml")
        self.assertIn("collection_max_age_minutes", bundle)
        self.assertRegex(bundle, r'default:\s*"180"')  # strict default stays for prod
        dev = bundle[bundle.index("  dev:"):bundle.index("  prod:")]
        self.assertRegex(dev, r'collection_max_age_minutes:\s*"720"')


if __name__ == "__main__":
    unittest.main()
