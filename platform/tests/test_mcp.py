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
                        "rank_evidence",
                        "create_internal_pilot_plan",
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

                ranking = await session.call_tool(
                    "rank_evidence",
                    {
                        "tenant_id": TENANT,
                        "decision_id": "pilot-1",
                        "candidates": [
                            {
                                "evidence_id": "ev-youtube",
                                "platform": "youtube",
                                "source_object_id": "video-1",
                                "source_url": "https://www.youtube.com/watch?v=video-1",
                                "title": "Enterprise agent pilot",
                                "author": "Reference channel",
                                "published_at": NOW,
                                "observed_at": NOW,
                                "relevance": 90,
                                "momentum": 80,
                                "source_quality": 80,
                                "corroboration": 70,
                                "freshness": 90,
                                "safety": 95,
                            }
                        ],
                    },
                )
                self.assertFalse(ranking.is_error)
                self.assertEqual(ranking.structured_content["items"][0]["rank"], 1)

                pilot = await session.call_tool(
                    "create_internal_pilot_plan",
                    {
                        "tenant_id": TENANT,
                        "workflow_type": "lead_response",
                        "business_outcome": "Improve qualified meeting conversion.",
                        "process_owner": "Growth operations",
                        "weekly_volume": 100,
                        "minutes_per_case": 20,
                        "loaded_hourly_cost_usd": 60,
                        "baseline_success_rate": 12,
                        "target_success_rate": 18,
                        "evidence_ids": ["ev-youtube"],
                    },
                )
                self.assertFalse(pilot.is_error)
                self.assertEqual(pilot.structured_content["stage"], "INTERNAL_STAGING")
                self.assertEqual(len(pilot.structured_content["seven_day_plan"]), 7)

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
