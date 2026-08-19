import unittest
from social_intelligence.agents import ServiceToolGateway, Supervisor
from social_intelligence.governance import ApprovalGate, ExperimentGate, evaluate_artifact
from social_intelligence.mcp_service import InMemoryDataProvider, McpService

class GovernanceAgentTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {"tenant_id":"acme", "evidence_id":"e1", "summary":"signal"}
        self.service = McpService(InMemoryDataProvider(
            opportunity_rows=[{"tenant_id":"acme","opportunity_id":"o1","opportunity_score":90,"evidence_ids":["e1"]}],
            evidence_rows=[self.evidence]))
    def test_supervisor_is_deterministic_and_requires_approval(self):
        result = Supervisor(ServiceToolGateway(self.service)).run("acme", "promote signal")
        self.assertEqual(result["status"], "PROPOSED")
        self.assertTrue(result["approval_required"])
        self.assertEqual(len(result["artifacts"]), 4)
        self.assertTrue(evaluate_artifact(result["artifacts"][2])["passed"])
    def test_approval_then_experiment_gate(self):
        recommendation = self.service.draft_recommendation(tenant_id="acme", opportunity_id="o1", action_type="PROMOTE", channel="PAID_SOCIAL", hypothesis="h", creative_brief="b", primary_metric="conversion_rate", confidence_score=80, evidence_ids=["e1"])
        approval = ApprovalGate().approve(recommendation, "owner", "reviewed evidence")
        plan = ExperimentGate().plan(recommendation, approval)
        self.assertEqual(plan["status"], "EXPERIMENT_PLANNED")

if __name__ == "__main__": unittest.main()
