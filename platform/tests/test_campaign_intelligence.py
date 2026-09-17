import unittest
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from social_intelligence.batch_reranker import rerank_context
from social_intelligence.campaign_intelligence import (
    CampaignExperimentRequest,
    CampaignMeasurementRequest,
    create_campaign_experiment,
    measurement_to_outcome_signal,
    record_campaign_measurement,
)
from social_intelligence.recommendation_context import RecommendationContextRequest, compile_recommendation_context
from social_intelligence.recommendation_review import RecommendationReviewRequest, create_recommendation_review


def approved_review():
    context = compile_recommendation_context(RecommendationContextRequest(
        tenant_id="demo", decision_id="campaign-pilot", business_objective="Increase direct orders.",
        market="San Francisco", locale="en-US", primary_metric="orders",
        ranked_evidence=[{"evidence_id": "ev-1", "rank": 1, "rank_score": 90, "platform": "youtube", "title": "Local demand", "source_url": "https://www.youtube.com/watch?v=campaign", "why_ranked": ["Strong match"]}],
        candidates=[{"candidate_id": "late-night-bundle", "candidate_type": "creative", "title": "Late-night bundle", "description": "Promote a late-night meal bundle.", "channels": ["paid-social"], "expected_outcome": "More orders"}],
    ))
    rerank = rerank_context(context)
    return create_recommendation_review(RecommendationReviewRequest(
        tenant_id="demo", rerank=rerank, decision="APPROVE", reviewer_id="growth_reviewer_01",
        decision_reason="Pilot is appropriate.", reviewed_at="2026-09-16T12:00:00+00:00", idempotency_key="campaign-review-1",
    ))


def experiment(**overrides):
    values = {
        "tenant_id": "demo", "review": approved_review(), "campaign_name": "SF late night", "channel": "paid-social",
        "business_objective": "Increase direct orders.", "primary_metric": "order_conversion_rate",
        "control_definition": "Current generic creative.", "treatment_definition": "Late-night bundle creative.",
        "comparison_method": "RANDOMIZED_AB_TEST", "planned_start_at": "2026-09-17T00:00:00+00:00",
        "planned_end_at": "2026-09-24T00:00:00+00:00", "created_by": "growth_ops_01", "idempotency_key": "campaign-1",
    }
    values.update(overrides)
    return create_campaign_experiment(CampaignExperimentRequest(**values))


class CampaignIntelligenceTests(unittest.TestCase):
    def test_experiment_is_manual_no_pii_and_non_mutating(self):
        result = experiment()
        self.assertEqual(result["status"], "DRAFT")
        self.assertFalse(result["activation"]["external_action_permitted"])
        self.assertFalse(result["activation"]["audience_export_permitted"])
        self.assertEqual(result["data_policy"], "AGGREGATE_METRICS_ONLY_NO_PII")
        self.assertEqual(result["mutation"], "none")

    def test_measurement_calculates_observed_lift_but_not_causality(self):
        result = record_campaign_measurement(CampaignMeasurementRequest(
            tenant_id="demo", experiment=experiment(), observed_at="2026-09-25T00:00:00+00:00",
            measurement_source="restaurant_pos_aggregate", reported_by="growth_ops_01", idempotency_key="measurement-1",
            control_impressions=2000, treatment_impressions=2000, control_conversions=40, treatment_conversions=60,
            control_value=1000, treatment_value=1500, control_spend=100, treatment_spend=100,
        ))
        self.assertEqual(result["observed_conversion_rate_lift_pct"], 50.0)
        self.assertEqual(result["result"], "POSITIVE")
        self.assertEqual(result["confidence"], "MEASURED")
        self.assertEqual(result["causality_claim"], "none")
        self.assertTrue(result["ranking_feedback"]["eligible_for_offline_reranking"])

    def test_insufficient_measurement_cannot_feed_reranking(self):
        measurement = record_campaign_measurement(CampaignMeasurementRequest(
            tenant_id="demo", experiment=experiment(), observed_at="2026-09-25T00:00:00+00:00",
            measurement_source="restaurant_pos_aggregate", reported_by="growth_ops_01", idempotency_key="measurement-2",
            control_impressions=100, treatment_impressions=100, control_conversions=2, treatment_conversions=4,
        ))
        self.assertEqual(measurement["result"], "INSUFFICIENT_DATA")
        with self.assertRaisesRegex(ValueError, "not eligible"):
            measurement_to_outcome_signal(measurement)

    def test_invalid_experiment_and_unsafe_actor_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "later"):
            experiment(planned_end_at="2026-09-16T00:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "opaque actor"):
            experiment(created_by="operator@example.com")

    def test_outputs_validate_against_the_published_contracts(self):
        compiled_experiment = experiment()
        measurement = record_campaign_measurement(CampaignMeasurementRequest(
            tenant_id="demo", experiment=compiled_experiment, observed_at="2026-09-25T00:00:00+00:00",
            measurement_source="restaurant_pos_aggregate", reported_by="growth_ops_01", idempotency_key="measurement-schema",
            control_impressions=2000, treatment_impressions=2000, control_conversions=40, treatment_conversions=60,
        ))
        contracts = Path(__file__).resolve().parents[1] / "contracts" / "json-schema"
        for filename, artifact in (("campaign-experiment-v1.json", compiled_experiment), ("campaign-measurement-v1.json", measurement)):
            Draft202012Validator(json.loads((contracts / filename).read_text())).validate(artifact)


if __name__ == "__main__":
    unittest.main()
