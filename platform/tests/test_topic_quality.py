import math
import unittest

from social_intelligence.topic_quality import (
    MIN_LABELLED,
    wilson_lower_bound,
    score_topics,
    summarize,
)


def by_topic(results):
    return {r.topic_id: r for r in results}


class WilsonTests(unittest.TestCase):
    def test_known_values(self):
        self.assertAlmostEqual(wilson_lower_bound(10, 10), 0.787, places=3)
        self.assertAlmostEqual(wilson_lower_bound(0, 10), 0.0, places=6)
        self.assertAlmostEqual(wilson_lower_bound(7, 10), 0.4417, places=3)
        self.assertIsNone(wilson_lower_bound(0, 0))

    def test_more_evidence_tightens_the_bound(self):
        self.assertGreater(wilson_lower_bound(90, 100), wilson_lower_bound(9, 10))

    def test_bound_never_exceeds_the_point_estimate(self):
        for n in (1, 5, 20, 200):
            for k in range(n + 1):
                self.assertLessEqual(wilson_lower_bound(k, n), k / n + 1e-9)


class ScoreTests(unittest.TestCase):
    def pairs(self):
        return ([("evals", "evals")] * 8 + [("evals", "other")] * 2 +
                [("mcp", "mcp")] * 3 + [("mcp", "evals")] * 1 +
                [("other", "other")] * 4 + [("off_topic", "other")] * 2 + [("off_topic", "mcp")])

    def test_precision_uses_predictions_and_recall_uses_labels(self):
        topics = by_topic(score_topics(self.pairs(), min_labelled=5, min_precision_lower_bound=0.5))
        evals = topics["evals"]
        self.assertEqual((evals.labelled_n, evals.predicted_n, evals.true_positives), (10, 9, 8))
        self.assertAlmostEqual(evals.precision, 8 / 9)
        self.assertAlmostEqual(evals.recall, 8 / 10)
        self.assertIsNone(topics["off_topic"].precision)  # never predicted
        self.assertEqual(topics["off_topic"].recall, 0.0)

    def test_rankable_needs_sample_size_and_precision_and_excludes_other(self):
        topics = by_topic(score_topics(self.pairs(), min_labelled=5, min_precision_lower_bound=0.5))
        self.assertTrue(topics["evals"].rankable)
        self.assertFalse(topics["mcp"].rankable)      # 4 labelled < 5
        self.assertFalse(topics["other"].rankable)    # fallback is never ranked
        strict = by_topic(score_topics(self.pairs(), min_labelled=5, min_precision_lower_bound=0.95))
        self.assertTrue(strict["evals"].meets_sample_size)
        self.assertFalse(strict["evals"].meets_precision)
        self.assertFalse(strict["evals"].rankable)

    def test_the_design_gate_cannot_pass_on_a_sixty_post_set(self):
        sixty = [("framework", "framework")] * 23 + [("other", "other")] * 37
        self.assertEqual(MIN_LABELLED, 40)
        self.assertFalse(by_topic(score_topics(sixty))["framework"].meets_sample_size)

    def test_summary(self):
        s = summarize(self.pairs())
        self.assertEqual((s["gold_posts"], s["on_topic_posts"], s["off_topic_posts"]), (21, 18, 3))
        self.assertAlmostEqual(s["primary_accuracy"], 15 / 18)
        self.assertEqual(s["off_topic_firing"], 1)
        self.assertAlmostEqual(s["predicted_other_share"], 8 / 21)

    def test_empty_input(self):
        self.assertEqual(score_topics([]), [])
        self.assertIsNone(summarize([])["primary_accuracy"])


if __name__ == "__main__":
    unittest.main()


import ast
from pathlib import Path

from social_intelligence.topic_quality import MIN_PRECISION_LOWER_BOUND, Z

PLATFORM = Path(__file__).resolve().parents[1]
QUALITY_NOTEBOOK = (PLATFORM / "notebooks" / "16_build_topic_quality.py").read_text(encoding="utf-8")


class QualityNotebookGuardTests(unittest.TestCase):
    """Static guards: Spark is unavailable in unit tests."""

    def test_constants_and_defaults_equal_the_reference(self):
        self.assertIn(f"Z = {Z}", QUALITY_NOTEBOOK)
        self.assertIn(f'dbutils.widgets.text("min_labelled", "{MIN_LABELLED}")', QUALITY_NOTEBOOK)
        self.assertIn(f'dbutils.widgets.text("min_precision_lower_bound", "{MIN_PRECISION_LOWER_BOUND}")', QUALITY_NOTEBOOK)

    def test_human_labels_are_always_gold_and_models_only_while_listed(self):
        self.assertIn("labels.label_source = 'human' OR gold.labeller_id IS NOT NULL", QUALITY_NOTEBOOK)
        self.assertIn("gold.tenant_id = labels.tenant_id AND gold.labeller_id = labels.labeller_id", QUALITY_NOTEBOOK)

    def test_one_gold_label_per_post_with_human_first(self):
        self.assertIn("PARTITION BY tenant_id, platform, post_id", QUALITY_NOTEBOOK)
        self.assertIn("CASE WHEN label_source = 'human' THEN 0 ELSE 1 END", QUALITY_NOTEBOOK)
        self.assertIn("gold.row_num = 1", QUALITY_NOTEBOOK)

    def test_every_join_is_tenant_scoped(self):
        for fragment in ("posts.tenant_id = gold.tenant_id", "scored.tenant_id = topics.tenant_id",
                         "topics.tenant_id = rules.tenant_id", "totals.tenant_id = rules.tenant_id"):
            self.assertIn(fragment, QUALITY_NOTEBOOK)

    def test_other_and_off_topic_are_never_rankable(self):
        self.assertIn("topic_id NOT IN ('other', 'off_topic') AS rankable", QUALITY_NOTEBOOK)

    def test_it_only_writes_its_own_reporting_tables(self):
        created = {line.split("`")[1] for line in QUALITY_NOTEBOOK.splitlines() if "CREATE OR REPLACE TABLE" in line}
        self.assertEqual(created, {"gold_topic_quality", "gold_topic_quality_summary", "gold_topic_rule_yield"})
        for forbidden in ("INSERT", "DELETE", "MERGE", "UPDATE", "DROP"):
            self.assertNotRegex(QUALITY_NOTEBOOK.upper().replace("CURRENT_TIMESTAMP", ""), rf"\b{forbidden}\b")

    def test_job_runs_it_after_analytics_and_nothing_depends_on_it(self):
        job = (PLATFORM / "resources" / "external_ingestion.job.yml").read_text(encoding="utf-8")
        block = job[job.index("task_key: build_topic_quality"):]
        self.assertIn("task_key: refresh_analytics", block[: block.index("notebook_task")])
        self.assertEqual(job.count("task_key: build_topic_quality"), 1)  # defined once, never a dependency

    def test_gold_labeller_seed_records_the_owner_decision_and_revocation_is_tenant_scoped(self):
        init = (PLATFORM / "notebooks" / "00_initialize_platform.py").read_text(encoding="utf-8")
        tree = ast.parse(init)
        seed = next(ast.literal_eval(n.value) for n in tree.body
                    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "GOLD_LABELLER_SEED" for t in n.targets))
        self.assertEqual([row[0] for row in seed], ["agent_reviewer_01"])
        merge = init[init.index("MERGE INTO {ns}.`control_gold_labellers`"):]
        merge = merge[: merge.index('"""')]
        self.assertIn("WHEN NOT MATCHED BY SOURCE AND target.tenant_id = '{tenant_id}' THEN DELETE", merge)
        self.assertIn("target.tenant_id = incoming.tenant_id AND target.labeller_id = incoming.labeller_id", merge)
