import unittest

from social_intelligence.batch_reranker import rerank_context
from social_intelligence.recommendation_context import RecommendationContextRequest, compile_recommendation_context
from social_intelligence.recommendation_review import (
    RecommendationOutcomeRequest,
    RecommendationReviewRequest,
    create_recommendation_review,
    record_recommendation_outcome,
    summarize_recommendation_reviews,
)


def rerank():
    context = compile_recommendation_context(RecommendationContextRequest(
        tenant_id="demo", decision_id="review-pilot", business_objective="Increase qualified demand.",
        market="San Francisco", locale="en-US", primary_metric="qualified_demo_rate",
        ranked_evidence=[{"evidence_id": "ev-1", "rank": 1, "rank_score": 90,
                          "platform": "youtube", "title": "Pilot evidence",
                          "source_url": "https://www.youtube.com/watch?v=pilot-1",
                          "why_ranked": ["Strong match"]}],
        candidates=[
            {"candidate_id": "creative-1", "candidate_type": "creative", "title": "Proof",
             "description": "Observed proof.", "channels": ["linkedin"], "expected_outcome": "More demos"},
            {"candidate_id": "creative-2", "candidate_type": "creative", "title": "Workshop",
             "description": "Workshop invitation.", "channels": ["linkedin"], "expected_outcome": "More demos"},
        ],
    ))
    return rerank_context(context)


def review(**overrides):
    values = {
        "tenant_id": "demo", "rerank": rerank(), "decision": "APPROVE", "reviewer_id": "growth_reviewer_01",
        "decision_reason": "Evidence is applicable to the target market.",
        "reviewed_at": "2026-08-28T12:00:00+00:00", "idempotency_key": "review-pilot-1",
    }
    values.update(overrides)
    return create_recommendation_review(RecommendationReviewRequest(**values))


class RecommendationReviewTests(unittest.TestCase):
    def test_approval_selects_only_cited_ranked_candidate_and_never_activates(self):
        result = review()
        self.assertEqual(result["status"], "APPROVED_FOR_HANDOFF")
        self.assertEqual(result["selected_candidate_id"], "creative-1")
        self.assertEqual(result["evidence_ids"], ["ev-1"])
        self.assertFalse(result["handoff"]["external_action_permitted"])
        self.assertEqual(result["mutation"], "none")

    def test_edit_requires_an_eligible_candidate_and_edited_brief(self):
        with self.assertRaisesRegex(ValueError, "edited_brief"):
            review(decision="EDIT")
        with self.assertRaisesRegex(ValueError, "selected_candidate_id"):
            review(decision="EDIT", selected_candidate_id="invented", edited_brief="Use a revised headline.")
        result = review(decision="EDIT", selected_candidate_id="creative-2", edited_brief="Use the workshop title only.")
        self.assertEqual(result["status"], "EDITED_FOR_HANDOFF")
        self.assertEqual(result["selected_candidate_id"], "creative-2")

    def test_rejection_cannot_select_or_handoff_a_candidate(self):
        with self.assertRaisesRegex(ValueError, "cannot select"):
            review(decision="REJECT", selected_candidate_id="creative-1")
        result = review(decision="REJECT")
        self.assertEqual(result["status"], "REJECTED")
        self.assertIsNone(result["selected_candidate_id"])
        self.assertEqual(result["handoff"]["state"], "NOT_REQUESTED")

    def test_outcome_requires_approved_review_and_is_observational(self):
        with self.assertRaisesRegex(ValueError, "only for approved"):
            record_recommendation_outcome(RecommendationOutcomeRequest(
                tenant_id="demo", review=review(decision="REJECT"), metric_name="qualified_demo_rate",
                observed_value=0.2, unit="ratio", observed_at="2026-08-29T12:00:00+00:00",
                measurement_source="crm", reported_by="growth_ops_01", idempotency_key="outcome-1",
            ))
        result = record_recommendation_outcome(RecommendationOutcomeRequest(
            tenant_id="demo", review=review(), metric_name="qualified_demo_rate", observed_value=0.2,
            baseline_value=0.12, unit="ratio", observed_at="2026-08-29T12:00:00+00:00",
            measurement_source="crm", reported_by="growth_ops_01", idempotency_key="outcome-1", confidence="MEASURED",
        ))
        self.assertEqual(result["attribution"], "OBSERVATIONAL_ONLY")
        self.assertEqual(result["causality_claim"], "none")
        self.assertEqual(result["candidate_id"], "creative-1")

    def test_scorecard_tracks_review_adoption_and_outcome_coverage(self):
        approved = review()
        rejected = review(decision="REJECT", idempotency_key="review-pilot-2")
        outcome = record_recommendation_outcome(RecommendationOutcomeRequest(
            tenant_id="demo", review=approved, metric_name="qualified_demo_rate", observed_value=0.2,
            unit="ratio", observed_at="2026-08-29T12:00:00+00:00", measurement_source="crm",
            reported_by="growth_ops_01", idempotency_key="outcome-1",
        ))
        scorecard = summarize_recommendation_reviews([approved, rejected], [outcome])
        self.assertEqual(scorecard["acceptance_rate"], 0.5)
        self.assertEqual(scorecard["outcome_coverage_rate"], 1.0)
        self.assertEqual(scorecard["automation_status"], "DISABLED")

    def test_actor_ids_must_not_be_email_addresses(self):
        with self.assertRaisesRegex(ValueError, "opaque actor"):
            review(reviewer_id="person@example.com")


if __name__ == "__main__":
    unittest.main()
