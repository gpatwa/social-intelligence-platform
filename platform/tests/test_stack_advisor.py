import unittest

from social_intelligence.stack_advisor import StackAdvisorRequest, recommend_stack


class StackAdvisorTests(unittest.TestCase):
    def test_deterministic_workflow_is_automation_first(self):
        request = StackAdvisorRequest(
            workflow_type="document_processing",
            integration_surface="api",
            risk_level="high",
            team_profile="engineering",
            cloud_preference="neutral",
            external_actions=False,
        )
        first = recommend_stack(request)
        second = recommend_stack(request)
        self.assertEqual(first, second)
        self.assertEqual(first["blueprint"]["pattern"], "AUTOMATION_FIRST")
        self.assertEqual(first["stack"][0]["product"], "Temporal + Python services")
        self.assertFalse(first["approval_required"])
        self.assertEqual(first["mutation"], "none")

    def test_legacy_agent_adds_computer_use_controls(self):
        result = recommend_stack(StackAdvisorRequest(
            workflow_type="lead_response",
            integration_surface="legacy_ui",
            personalization=True,
        ))
        products = {component["product"] for component in result["stack"]}
        self.assertIn("Direct APIs + Orgo exception path", products)
        self.assertIn("Honcho (opt-in)", products)
        self.assertIn("isolated computer session", result["required_controls"])
        self.assertIn("memory consent", result["required_controls"])
        self.assertTrue(result["approval_required"])
        evidence_ids = {item["id"] for item in result["evidence"]}
        self.assertIn("orgo-computer-use", evidence_ids)
        self.assertIn("honcho-memory", evidence_ids)

    def test_cloud_preference_selects_enterprise_framework(self):
        result = recommend_stack(StackAdvisorRequest(
            workflow_type="follow_up",
            cloud_preference="microsoft",
        ))
        self.assertEqual(result["stack"][0]["product"], "Microsoft Agent Framework")

    def test_invalid_values_fail_closed(self):
        with self.assertRaises(ValueError):
            recommend_stack(StackAdvisorRequest(workflow_type="general_agent"))
        with self.assertRaises(ValueError):
            recommend_stack(StackAdvisorRequest(workflow_type="lead_response", max_time_to_value_days=0))

    def test_small_deployment_does_not_require_enterprise_warehouses(self):
        result = recommend_stack(StackAdvisorRequest(
            workflow_type="internal_reporting",
            enterprise_data=False,
            external_actions=False,
        ))
        products = {component["product"] for component in result["stack"]}
        self.assertNotIn("Databricks + Delta", products)
        self.assertNotIn("Snowflake", products)
        self.assertIn("PostgreSQL + object storage", products)


if __name__ == "__main__":
    unittest.main()
