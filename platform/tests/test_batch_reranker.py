import unittest

from social_intelligence.batch_reranker import (
    DeterministicOfflineReranker,
    evaluate_reranker,
    rerank_context,
    structured_rerank_request,
)
from social_intelligence.recommendation_context import RecommendationContextRequest, compile_recommendation_context


def context():
    return compile_recommendation_context(RecommendationContextRequest(
        tenant_id="demo", decision_id="pilot-1", business_objective="Increase qualified demand.",
        market="San Francisco", locale="en-US", primary_metric="qualified_demo_rate",
        ranked_evidence=[{"evidence_id": "ev-1", "rank": 1, "rank_score": 92,
                          "platform": "youtube", "title": "Pilot evidence",
                          "source_url": "https://www.youtube.com/watch?v=pilot-1",
                          "why_ranked": ["Strong match"]}],
        candidates=[
            {"candidate_id": "creative-1", "candidate_type": "creative", "title": "Proof",
             "description": "Observed proof point.", "channels": ["linkedin"], "expected_outcome": "More demos"},
            {"candidate_id": "creative-2", "candidate_type": "creative", "title": "Workshop",
             "description": "Workshop invitation.", "channels": ["linkedin"], "expected_outcome": "More demos"},
        ],
        outcome_signals=[{"candidate_id": "creative-1", "metric": "qualified_demo_rate",
                          "value": 0.2, "unit": "ratio", "observed_at": "2026-08-27T12:00:00+00:00"}],
    ))


class BatchRerankerTests(unittest.TestCase):
    def test_offline_rerank_is_deterministic_grounded_and_non_mutating(self):
        first = rerank_context(context())
        second = rerank_context(context(), DeterministicOfflineReranker())
        self.assertEqual(first, second)
        self.assertEqual(first["primary_candidate_id"], "creative-1")
        self.assertEqual(first["evidence_ids"], ["ev-1"])
        self.assertEqual(first["status"], "PROPOSED")
        self.assertTrue(first["approval_required"])
        self.assertEqual(first["mutation"], "none")

    def test_provider_neutral_request_keeps_boundaries_explicit(self):
        request = structured_rerank_request(context())
        self.assertEqual(request["task"], "rank_supplied_candidates")
        self.assertIn("never invent", " ".join(request["constraints"]))
        self.assertNotIn("raw_social_content", str(request["context"]).lower())

    def test_bad_adapter_cannot_return_unknown_or_uncited_candidate(self):
        class BadAdapter:
            provider = "fixture"
            model = "bad"
            def rerank(self, unused):
                return [{"candidate_id": "not-supplied", "score": 90, "citations": [], "rationale": "bad"}]
        with self.assertRaisesRegex(ValueError, "every eligible candidate"):
            rerank_context(context(), BadAdapter())

    def test_evaluation_reports_grounding_and_selection(self):
        result = evaluate_reranker([{"case_id": "golden-1", "context": context(), "expected_candidate_ids": ["creative-1"]}])
        self.assertEqual(result["release_gate"], "PASS")
        self.assertEqual(result["grounding_rate"], 1.0)
        self.assertEqual(result["expected_selection_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
