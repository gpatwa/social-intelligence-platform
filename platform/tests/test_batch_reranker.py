import json
import os
import unittest
from unittest.mock import patch

from social_intelligence.batch_reranker import (
    DeterministicOfflineReranker,
    OpenAIResponsesReranker,
    adapter_from_environment,
    evaluate_reranker,
    rerank_context,
    structured_rerank_request,
)
from social_intelligence.recommendation_context import RecommendationContextRequest, compile_recommendation_context
from social_intelligence.reranker_benchmark import staging_benchmark_cases


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
        self.assertEqual(request["allowed_candidate_ids"], ["creative-1", "creative-2"])
        self.assertEqual(request["allowed_evidence_ids"], ["ev-1"])
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

    def test_openai_adapter_uses_structured_output_and_still_obeys_local_validation(self):
        class Response:
            output_text = json.dumps({"ranked_candidates": [
                {"candidate_id": "creative-1", "score": 91, "citations": ["ev-1"], "rationale": "Evidence-backed."},
                {"candidate_id": "creative-2", "score": 81, "citations": ["ev-1"], "rationale": "Evidence-backed."},
            ]})

        class Client:
            def __init__(self):
                self.responses = self
                self.request = None
            def create(self, **kwargs):
                self.request = kwargs
                return Response()

        client = Client()
        result = rerank_context(context(), OpenAIResponsesReranker(model="test-model", client=client))
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["reasoning_effort"], "high")
        self.assertEqual(result["primary_candidate_id"], "creative-1")
        self.assertFalse(client.request["store"])
        self.assertEqual(client.request["text"]["format"]["type"], "json_schema")
        self.assertTrue(client.request["text"]["format"]["strict"])
        schema = client.request["text"]["format"]["schema"]
        ranking_item = schema["properties"]["ranked_candidates"]["items"]["properties"]
        self.assertEqual(ranking_item["candidate_id"]["enum"], ["creative-1", "creative-2"])
        self.assertEqual(ranking_item["citations"]["items"]["enum"], ["ev-1"])
        self.assertEqual(client.request["reasoning"], {"effort": "high"})

    def test_environment_adapter_requires_an_explicit_openai_model(self):
        with patch.dict(os.environ, {"SOCIAL_INTELLIGENCE_RERANKER_PROVIDER": "openai"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_RERANKER_MODEL"):
                adapter_from_environment()
        with patch.dict(os.environ, {"SOCIAL_INTELLIGENCE_RERANKER_PROVIDER": "openai", "SOCIAL_INTELLIGENCE_OPENAI_RERANKER_MODEL": "test-model"}, clear=True):
            adapter = adapter_from_environment()
        self.assertIsInstance(adapter, OpenAIResponsesReranker)

    def test_openai_adapter_rejects_unknown_reasoning_effort(self):
        with self.assertRaisesRegex(ValueError, "reasoning_effort"):
            OpenAIResponsesReranker(model="test-model", reasoning_effort="fast")

    def test_synthetic_staging_benchmark_protects_the_baseline(self):
        result = evaluate_reranker(staging_benchmark_cases())
        self.assertEqual(result["case_count"], 5)
        self.assertEqual(result["release_gate"], "PASS")
        self.assertEqual(result["expected_selection_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
