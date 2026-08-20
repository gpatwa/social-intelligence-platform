import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_intelligence.scoring import (
    challenge_score,
    content_performance_score,
    cross_platform_confidence,
    engagement_rate,
    trend_score,
)


class ScoringTests(unittest.TestCase):
    def test_engagement_rate(self):
        self.assertAlmostEqual(engagement_rate(50, 10, 20, 20, 1000), 0.1)

    def test_engagement_rate_handles_zero_views(self):
        self.assertEqual(engagement_rate(10, 10, 10, 10, 0), 0.0)

    def test_content_performance_favors_efficiency_without_unbounded_volume(self):
        efficient = content_performance_score(0.10, 2_000, 20_000)
        weak = content_performance_score(0.01, 10_000, 1_000_000)
        self.assertGreater(efficient, weak)
        self.assertLessEqual(content_performance_score(10, 10**9, 10**9), 100.0)

    def test_cross_platform_confidence_requires_independent_evidence(self):
        single_platform = cross_platform_confidence(1, 1, 1)
        corroborated = cross_platform_confidence(3, 75, 400)
        self.assertGreater(corroborated, 90)
        self.assertGreater(corroborated, single_platform)

    def test_strong_trend_scores_above_baseline(self):
        baseline = trend_score(0.2, 0.1, 0.05, 5, 1, 0.1, 0.5)
        emerging = trend_score(3.5, 3.0, 1.5, 80, 3, 0.9, 0.8)
        self.assertGreater(emerging, 75)
        self.assertGreater(emerging, baseline)

    def test_penalty_reduces_trend_score(self):
        clean = trend_score(3, 3, 1, 50, 3, 0.8, 0.7)
        suspicious = trend_score(3, 3, 1, 50, 3, 0.8, 0.7, 25)
        self.assertEqual(round(clean - suspicious, 2), 25.0)

    def test_challenge_rewards_breadth(self):
        small = challenge_score(0.5, 3, 1, 1, 2)
        broad = challenge_score(2.5, 75, 5, 3, 30)
        self.assertGreater(broad, 80)
        self.assertGreater(broad, small)

    def test_scores_are_bounded(self):
        self.assertEqual(trend_score(100, 100, 100, 9999, 99, 99, 99), 100.0)
        self.assertEqual(challenge_score(100, 9999, 99, 99, 999), 100.0)


if __name__ == "__main__":
    unittest.main()
