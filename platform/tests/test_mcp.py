import asyncio
from datetime import datetime, timezone
import unittest

from mcp import Client

from social_intelligence.mcp_server import create_mcp_server
from social_intelligence.mcp_service import InMemoryDataProvider, McpService


TENANT = "demo"
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc).isoformat()


def provider() -> InMemoryDataProvider:
    return InMemoryDataProvider(
        opportunity_rows=[
            {
                "opportunity_id": "opp-high",
                "tenant_id": TENANT,
                "opportunity_score": 88.0,
                "confidence_score": 76.0,
                "status": "OPEN",
                "signal_at": NOW,
                "evidence": [{"evidence_id": "ev-1"}],
            },
            {
                "opportunity_id": "opp-other-tenant",
                "tenant_id": "other",
                "opportunity_score": 99.0,
                "status": "OPEN",
            },
        ],
        evidence_rows=[
            {
                "evidence_id": "ev-1",
                "tenant_id": TENANT,
                "source_type": "social_event",
                "source_ref": "urn:event:1",
                "observed_at": NOW,
                "trust_tier": "machine_confirmed",
            }
        ],
        metric_rows=[
            {
                "tenant_id": TENANT,
                "metric_name": "trend_score",
                "source_id": "x-sf",
                "observed_at": NOW,
                "value": 72.5,
            }
        ],
        pipeline_rows=[
            {
                "tenant_id": TENANT,
                "source_id": "x-sf",
                "status": "healthy",
                "last_success_at": NOW,
            }
        ],
    )


class McpServiceTests(unittest.TestCase):
    def test_tenant_filtering_and_ranked_opportunities(self):
        result = McpService(provider()).list_opportunities(tenant_id=TENANT)
        self.assertEqual(result["returned"], 1)
        self.assertEqual(result["items"][0]["opportunity_id"], "opp-high")

    def test_read_tools_require_valid_tenant_and_evidence_scope(self):
        service = McpService(provider())
        with self.assertRaises(ValueError):
            service.get_metrics(tenant_id="../other")
        with self.assertRaises(LookupError):
            service.get_evidence(tenant_id=TENANT, evidence_id="ev-other")

    def test_draft_is_deterministic_and_has_no_mutation_path(self):
        service = McpService(provider())
        draft = service.draft_recommendation(
            tenant_id=TENANT,
            opportunity_id="opp-high",
            action_type="CREATIVE_TEST",
            channel="paid-social",
            hypothesis="A clearer proof point will improve conversion.",
            creative_brief="Show the customer outcome and evidence.",
            primary_metric="conversion_rate",
            confidence_score=76,
            evidence_ids=["ev-1", "ev-1"],
        )
        self.assertEqual(draft["status"], "PROPOSED")
        self.assertEqual(draft["mutation"], "none")
        self.assertTrue(draft["approval_required"])
        self.assertEqual(draft["evidence_ids"], ["ev-1"])


class McpProtocolTests(unittest.TestCase):
    def test_server_registers_governed_tools_and_executes_tenant_filter(self):
        async def exercise() -> None:
            server = create_mcp_server(provider())
            async with Client(server) as session:
                tools = await session.list_tools()
                self.assertEqual(
                    {tool.name for tool in tools.tools},
                    {
                        "list_opportunities",
                        "get_evidence",
                        "get_metrics",
                        "get_pipeline_status",
                        "draft_recommendation",
                        "recommend_agent_stack",
                    },
                )
                result = await session.call_tool(
                    "list_opportunities", {"tenant_id": TENANT, "limit": 10}
                )
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["returned"], 1)

                advisor = await session.call_tool(
                    "recommend_agent_stack",
                    {"tenant_id": TENANT, "workflow_type": "internal_reporting"},
                )
                self.assertFalse(advisor.is_error)
                self.assertEqual(advisor.structured_content["blueprint"]["pattern"], "AUTOMATION_FIRST")

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
