import unittest

from social_intelligence.recommendation_context import (
    RecommendationContextRequest,
    compile_recommendation_context,
)


def request(**overrides):
    payload = {
        "tenant_id": "demo",
        "decision_id": "sf-ai-learning",
        "business_objective": "Increase qualified enterprise AI learning demand.",
        "market": "San Francisco",
        "locale": "en-US",
        "primary_metric": "qualified_demo_rate",
        "ranked_evidence": [
            {
                "evidence_id": "ev-youtube-1", "rank": 1, "rank_score": 91.2,
                "platform": "youtube", "title": "AI builders discuss enterprise pilots",
                "source_url": "https://www.youtube.com/watch?v=pilot-1",
                "why_ranked": ["Strong match to the decision"],
            },
            {
                "evidence_id": "ev-x-1", "rank": 2, "rank_score": 86.1,
                "platform": "x", "title": "Enterprise agent workflow evidence",
                "source_url": "https://x.com/example/status/1",
                "why_ranked": ["Recently observed"],
            },
        ],
        "candidates": [
            {"candidate_id": "creative-proof", "candidate_type": "creative", "title": "Proof-point creative", "description": "Lead with observed customer outcomes.", "channels": ["linkedin", "youtube"], "expected_outcome": "Higher qualified demo rate"},
            {"candidate_id": "product-workshop", "candidate_type": "product", "title": "AI builder workshop", "description": "A practical enterprise AI learning workshop.", "channels": ["linkedin"], "expected_outcome": "More workshop registrations"},
            {"candidate_id": "blocked", "candidate_type": "channel", "title": "Blocked channel", "description": "Excluded from this decision.", "eligible": False, "channels": ["x"], "expected_outcome": "None"},
        ],
        "outcome_signals": [{"candidate_id": "creative-proof", "metric": "qualified_demo_rate", "value": 0.16, "unit": "ratio", "observed_at": "2026-08-27T12:00:00+00:00"}],
        "allowed_channels": ["linkedin"],
    }
    payload.update(overrides)
    return RecommendationContextRequest(**payload)


class RecommendationContextTests(unittest.TestCase):
    def test_compiles_deterministically_with_explainable_constraints(self):
        first = compile_recommendation_context(request())
        second = compile_recommendation_context(request(ranked_evidence=list(reversed(request().ranked_evidence))))
        self.assertEqual(first, second)
        self.assertEqual(first["context_version"], "recommendation-context-v1")
        self.assertEqual(first["status"], "READY_FOR_RERANK")
        self.assertEqual([item["candidate_id"] for item in first["candidate_set"]], ["creative-proof", "product-workshop"])
        self.assertEqual(first["excluded_candidates"], [{"candidate_id": "blocked", "reason": "candidate_marked_ineligible"}])
        self.assertTrue(first["approval_required"])
        self.assertEqual(first["causality_claim"], "none")
        self.assertEqual(first["mutation"], "none")

    def test_fails_closed_when_policy_removes_every_candidate(self):
        with self.assertRaisesRegex(ValueError, "no eligible candidates"):
            compile_recommendation_context(request(allowed_channels=["instagram"]))

    def test_outcome_must_reference_a_supplied_candidate(self):
        with self.assertRaisesRegex(ValueError, "outcome.candidate_id"):
            compile_recommendation_context(request(outcome_signals=[{
                "candidate_id": "unknown", "metric": "conversion", "value": 1,
                "unit": "ratio", "observed_at": "2026-08-27T12:00:00+00:00",
            }]))


if __name__ == "__main__":
    unittest.main()
