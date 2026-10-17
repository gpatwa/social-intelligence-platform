import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

from social_intelligence.campaign_intelligence import (
    CampaignExperimentRequest,
    CampaignMeasurementRequest,
    create_campaign_experiment,
    record_campaign_measurement,
)
from social_intelligence.record_append import (
    ARTIFACT_KEYS,
    EXPERIMENTS,
    MEASUREMENTS,
    OUTCOMES,
    REVIEWS,
    AuthenticationError,
    ConflictError,
    DatabricksSqlRecordStore,
    InMemoryRecordStore,
    PrincipalAuthenticator,
    append_record,
)
from social_intelligence.recommendation_review import (
    RecommendationOutcomeRequest,
    RecommendationReviewRequest,
    create_recommendation_review,
    record_recommendation_outcome,
)
from social_intelligence.batch_reranker import rerank_context
from social_intelligence.recommendation_context import RecommendationContextRequest, compile_recommendation_context

TOKEN = "unit-test-token"
NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


def authenticator(tenants=("demo",), actor="growth_reviewer_01"):
    return PrincipalAuthenticator.from_environment({
        "SOCIAL_INTELLIGENCE_APPEND_PRINCIPALS": json.dumps(
            [{"actor_id": actor, "tenants": list(tenants), "token_sha256": sha256(TOKEN.encode()).hexdigest()}]
        )
    })


def rerank():
    context = compile_recommendation_context(RecommendationContextRequest(
        tenant_id="demo", decision_id="append-pilot", business_objective="Increase direct orders.",
        market="San Francisco", locale="en-US", primary_metric="orders",
        ranked_evidence=[{"evidence_id": "ev-1", "rank": 1, "rank_score": 90, "platform": "youtube", "title": "Local demand", "source_url": "https://www.youtube.com/watch?v=append", "why_ranked": ["Strong match"]}],
        candidates=[{"candidate_id": "bundle", "candidate_type": "creative", "title": "Bundle", "description": "Promote a bundle.", "channels": ["paid-social"], "expected_outcome": "More orders"}],
    ))
    return rerank_context(context)


def review(decision="APPROVE", reviewer="growth_reviewer_01", key="r1"):
    return create_recommendation_review(RecommendationReviewRequest(
        tenant_id="demo", rerank=rerank(), decision=decision, reviewer_id=reviewer, decision_reason="Fits pilot.",
        reviewed_at="2026-09-16T12:00:00+00:00", idempotency_key=key,
    ))


def experiment(approved, actor="growth_reviewer_01"):
    return create_campaign_experiment(CampaignExperimentRequest(
        tenant_id="demo", review=approved, campaign_name="SF", channel="paid-social", business_objective="Orders",
        primary_metric="order_conversion_rate", control_definition="Generic", treatment_definition="Bundle",
        comparison_method="RANDOMIZED_AB_TEST", planned_start_at="2026-09-17T00:00:00+00:00",
        planned_end_at="2026-09-24T00:00:00+00:00", created_by=actor, idempotency_key="e1",
    ))


def measurement(exp, **overrides):
    values = dict(
        tenant_id="demo", experiment=exp, observed_at="2026-09-25T00:00:00+00:00", measurement_source="pos_aggregate",
        reported_by="growth_reviewer_01", idempotency_key="m1", control_impressions=2000, treatment_impressions=2000,
        control_conversions=40, treatment_conversions=60,
    )
    values.update(overrides)
    return record_campaign_measurement(CampaignMeasurementRequest(**values))


def append(kind, artifact, store, auth=None, **kwargs):
    return append_record(kind, artifact, token=TOKEN, authenticator=auth or authenticator(), store=store, clock=lambda: NOW, **kwargs)


class RecordAppendTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryRecordStore()

    def seeded(self):
        approved = review()
        append("review", approved, self.store)
        exp = experiment(approved)
        append("experiment", exp, self.store)
        return approved, exp

    def test_full_chain_appends_and_replays_idempotently(self):
        approved, exp = self.seeded()
        self.assertEqual(append("review", approved, self.store)["status"], "DUPLICATE")
        outcome = record_recommendation_outcome(RecommendationOutcomeRequest(
            tenant_id="demo", review=approved, metric_name="orders", observed_value=12, unit="count",
            observed_at="2026-09-25T00:00:00+00:00", measurement_source="pos", reported_by="growth_reviewer_01", idempotency_key="o1",
        ))
        self.assertEqual(append("outcome", outcome, self.store)["status"], "APPENDED")
        meas = measurement(exp)
        self.assertEqual(append("measurement", meas, self.store)["status"], "APPENDED")
        self.assertEqual(append("measurement", meas, self.store)["status"], "DUPLICATE")
        for table in (REVIEWS, OUTCOMES, EXPERIMENTS, MEASUREMENTS):
            self.assertEqual(len(self.store.tables[table]), 1)
        stored = self.store.tables[MEASUREMENTS][meas["measurement_id"]]
        self.assertTrue(stored["feedback_eligible"])
        self.assertEqual(stored["received_at"], NOW.isoformat())

    def test_authentication_fails_closed(self):
        with self.assertRaises(AuthenticationError):
            append_record("review", review(), token="wrong", authenticator=authenticator(), store=self.store)
        with self.assertRaises(AuthenticationError):
            append_record("review", review(), token=None, authenticator=authenticator(), store=self.store)
        with self.assertRaises(RuntimeError):
            PrincipalAuthenticator.from_environment({})
        with self.assertRaises(RuntimeError):
            PrincipalAuthenticator.from_environment({"SOCIAL_INTELLIGENCE_APPEND_PRINCIPALS": json.dumps([{"actor_id": "a", "tenants": ["demo"], "token_sha256": "plain-token"}])})

    def test_tenant_scope_is_enforced(self):
        with self.assertRaises(PermissionError):
            append("review", review(), self.store, auth=authenticator(tenants=("other",)))
        self.assertEqual(self.store.tables, {})

    def test_actor_must_match_the_authenticated_principal(self):
        with self.assertRaisesRegex(ValueError, "authenticated actor"):
            append("review", review(reviewer="someone_else"), self.store)

    def test_reused_idempotency_key_with_different_content_conflicts(self):
        approved = review()
        append("review", approved, self.store)
        changed = {**approved, "decision_reason": "Different reason."}
        with self.assertRaises(ConflictError):
            append("review", changed, self.store)

    def test_tampered_ids_unknown_fields_and_boundaries_are_rejected(self):
        approved = review()
        for tampered, message in (
            ({**approved, "review_id": "0" * 64}, "review_id"),
            ({**approved, "customer_email": "x@example.com"}, "unsupported fields"),
            ({**approved, "mutation": "write"}, "non-mutating"),
            ({**approved, "evidence_ids": []}, "citations"),
            ({**approved, "status": "REJECTED"}, "inconsistent"),
        ):
            with self.assertRaisesRegex(ValueError, message):
                append("review", tampered, self.store)

    def test_rejected_review_cannot_anchor_experiments_or_outcomes(self):
        rejected = review(decision="REJECT", key="rej")
        append("review", rejected, self.store)
        approved = review()
        exp = experiment(approved)
        forged = {**exp, "review_id": rejected["review_id"]}
        forged["experiment_id"] = sha256(f"campaign-experiment-v1|demo|{rejected['review_id']}|e1".encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "not approved"):
            append("experiment", forged, self.store)

    def test_experiment_requires_a_stored_review_and_no_activation_rights(self):
        approved = review()
        exp = experiment(approved)
        with self.assertRaisesRegex(ValueError, "not stored"):
            append("experiment", exp, self.store)
        append("review", approved, self.store)
        enabled = {**exp, "activation": {**exp["activation"], "spend_permitted": True}}
        with self.assertRaisesRegex(ValueError, "spend"):
            append("experiment", enabled, self.store)

    def test_measurement_requires_stored_experiment_and_verifiable_math(self):
        approved, exp = self.seeded()
        meas = measurement(exp)
        with self.assertRaisesRegex(ValueError, "not stored"):
            append("measurement", measurement(experiment(approved) | {"experiment_id": "f" * 64}, idempotency_key="m2"), InMemoryRecordStore())
        inflated = {**meas, "observed_conversion_rate_lift_pct": 500.0}
        with self.assertRaisesRegex(ValueError, "lift"):
            append("measurement", inflated, self.store)
        forged_gate = {**meas, "ranking_feedback": {**meas["ranking_feedback"], "eligible_for_offline_reranking": False}}
        with self.assertRaisesRegex(ValueError, "eligibility"):
            append("measurement", forged_gate, self.store)
        with_identity = {**meas, "control": {**meas["control"], "user_ids": ["u1"]}}
        with self.assertRaisesRegex(ValueError, "aggregate"):
            append("measurement", with_identity, self.store)

    def test_replay_tolerates_store_typing_and_extra_columns(self):
        approved, exp = self.seeded()
        meas = measurement(exp)
        append("measurement", meas, self.store)
        row = self.store.tables[MEASUREMENTS][meas["measurement_id"]]
        row["control_value"] = Decimal(str(row["control_value"]))
        row["treatment_value"] = Decimal(str(row["treatment_value"]))
        row["target_extra_column"] = "added by the store"
        row["observed_at"] = row["observed_at"].replace("+00:00", "Z")
        self.assertEqual(append("measurement", meas, self.store)["status"], "DUPLICATE")
        row["control_impressions"] += 1
        with self.assertRaises(ConflictError):
            append("measurement", meas, self.store)

    def test_dry_run_validates_without_writing(self):
        approved = review()
        self.assertEqual(append("review", approved, self.store, dry_run=True)["status"], "VALID")
        self.assertEqual(self.store.tables, {})

    def test_artifact_key_allowlists_match_the_compilers(self):
        approved, exp = self.seeded()
        outcome = record_recommendation_outcome(RecommendationOutcomeRequest(
            tenant_id="demo", review=approved, metric_name="orders", observed_value=1, unit="count",
            observed_at="2026-09-25T00:00:00+00:00", measurement_source="pos", reported_by="growth_reviewer_01", idempotency_key="o2",
        ))
        for kind, artifact in (("review", approved), ("outcome", outcome), ("experiment", exp), ("measurement", measurement(exp))):
            self.assertEqual(set(artifact), ARTIFACT_KEYS[kind], kind)


class FakeCursor:
    def __init__(self, log, rows):
        self.log, self.rows, self.description = log, rows, None

    def execute(self, statement, params=None):
        self.log.append((statement, params))

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.log = []

    def cursor(self):
        return FakeCursor(self.log, [])


class DatabricksStoreTests(unittest.TestCase):
    def test_merge_is_parameterized_insert_if_absent(self):
        connection = FakeConnection()
        store = DatabricksSqlRecordStore(connection, catalog="dev", schema="social_intelligence_dev")
        store.insert_if_absent(REVIEWS, "review_id", {"review_id": "x'; DROP TABLE y; --", "reviewed_at": "2026-09-16T12:00:00+00:00"})
        statement, params = connection.log[0]
        self.assertIn("MERGE INTO `dev`.`social_intelligence_dev`.`decision_recommendation_reviews`", statement)
        self.assertIn("WHEN NOT MATCHED THEN INSERT", statement)
        self.assertIn("CAST(:reviewed_at AS TIMESTAMP)", statement)
        self.assertNotIn("DROP TABLE", statement)
        self.assertEqual(params["review_id"], "x'; DROP TABLE y; --")

    def test_rejects_unknown_tables_and_unsafe_identifiers(self):
        with self.assertRaises(ValueError):
            DatabricksSqlRecordStore(FakeConnection(), catalog="dev`; --", schema="s")
        store = DatabricksSqlRecordStore(FakeConnection(), catalog="dev", schema="s")
        with self.assertRaises(ValueError):
            store.insert_if_absent("other_table", "id", {"id": "1"})
        with self.assertRaises(ValueError):
            store.insert_if_absent(REVIEWS, "review_id", {"review_id": "1", "bad col": "x"})


if __name__ == "__main__":
    unittest.main()
