import unittest

from social_intelligence.decisioning import (
    ExperimentResult,
    opportunity_score,
    stable_decision_id,
    validate_transition,
)


class DecisioningTests(unittest.TestCase):
    def test_stable_decision_id_is_normalized_and_repeatable(self):
        first = stable_decision_id("Demo", "Trend", "GlowUp")
        second = stable_decision_id(" demo ", "TREND", "glowup")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_opportunity_score_is_bounded_and_rewards_fit(self):
        low_fit = opportunity_score(80, 50, 0.1, 0.2)
        high_fit = opportunity_score(80, 50, 0.9, 0.9)
        self.assertGreater(high_fit[0], low_fit[0])
        self.assertGreater(high_fit[1], low_fit[1])
        self.assertTrue(all(0 <= value <= 100 for value in high_fit))

    def test_recommendation_lifecycle_cannot_skip_approval(self):
        validate_transition("PROPOSED", "APPROVED")
        with self.assertRaises(ValueError):
            validate_transition("PROPOSED", "RUNNING")

    def test_experiment_result_calculates_commercial_learning(self):
        result = ExperimentResult(
            control_revenue=10_000,
            treatment_revenue=11_500,
            actual_spend=300,
            gross_margin_rate=0.6,
        )
        self.assertEqual(result.measured_lift_pct, 15.0)
        self.assertEqual(result.incremental_contribution_margin, 600.0)


if __name__ == "__main__":
    unittest.main()
