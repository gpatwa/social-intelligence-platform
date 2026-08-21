import unittest

from social_intelligence.pilot_workspace import (
    PilotDiscoveryRequest,
    create_internal_pilot_plan,
)


def request(**overrides):
    values = {
        "tenant_id": "internal",
        "workflow_type": "lead_response",
        "business_outcome": "Reduce response time and improve qualified meetings.",
        "process_owner": "Growth operations",
        "weekly_volume": 100,
        "minutes_per_case": 20,
        "loaded_hourly_cost_usd": 60,
        "baseline_success_rate": 12,
        "target_success_rate": 18,
        "evidence_ids": ("ev-2", "ev-1", "ev-1"),
    }
    values.update(overrides)
    return PilotDiscoveryRequest(**values)


class InternalPilotWorkspaceTests(unittest.TestCase):
    def test_plan_is_deterministic_draft_only_and_economically_labeled(self):
        first = create_internal_pilot_plan(request())
        second = create_internal_pilot_plan(request())
        self.assertEqual(first, second)
        self.assertEqual(first["stage"], "INTERNAL_STAGING")
        self.assertEqual(first["workflow"]["operating_mode"], "DRAFT_AND_RECOMMEND_ONLY")
        self.assertEqual(first["evidence_ids"], ["ev-1", "ev-2"])
        self.assertEqual(len(first["seven_day_plan"]), 7)
        self.assertIn("capacity value is not booked revenue", first["discovery"]["assumptions"])
        self.assertEqual(first["scorecard"]["secondary"][-1]["target"], 0)
        self.assertTrue(first["approval_required"])
        self.assertEqual(first["mutation"], "none")

    def test_workflow_assigns_ai_and_human_boundaries(self):
        result = create_internal_pilot_plan(request(workflow_type="follow_up"))
        modes = {step["mode"] for step in result["workflow"]["steps"]}
        actions = {step["action"] for step in result["workflow"]["steps"]}
        self.assertIn("ai_generation", modes)
        self.assertIn("human", modes)
        self.assertIn("draft_only", actions)
        self.assertNotIn("external_write", actions)

    def test_invalid_economics_and_non_improving_target_fail_closed(self):
        with self.assertRaises(ValueError):
            create_internal_pilot_plan(request(weekly_volume=0))
        with self.assertRaises(ValueError):
            create_internal_pilot_plan(request(target_success_rate=10))


if __name__ == "__main__":
    unittest.main()
