import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_intelligence.connectors.base import CollectionRule
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.retry import RetryPolicy
from social_intelligence.connectors.x import (
    XApiError,
    XConnector,
    XConnectorConfig,
    XPaginationLimitReached,
)


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "x" / "recent_search.json"
TRENDS_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "x" / "trends_san_francisco.json"


class FixtureTransport:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or json.loads(FIXTURE.read_text())

    def __call__(self, path, params):
        self.calls.append((path, dict(params)))
        return self.response


class XConnectorTests(unittest.TestCase):
    def connector(self, transport, **overrides):
        values = {"tenant_id": "tenant-a", "source_id": "x-api"}
        values.update(overrides)
        return XConnector(
            bearer_token="test-token",
            config=XConnectorConfig(**values),
            transport=transport,
            clock=lambda: NOW,
            sleeper=lambda _: None,
        )

    def test_maps_recent_post_with_public_metrics_and_hashtags(self):
        transport = FixtureTransport()
        batch = self.connector(transport).collect(
            [CollectionRule("challenge", "hashtag", "GlowUpChallenge")],
            ConnectorCheckpoint.empty(NOW),
        )

        self.assertEqual(len(batch.events), 1)
        event = batch.events[0]
        self.assertEqual(event.platform, "x")
        self.assertEqual(event.payload["views"], 12_000)
        self.assertEqual(event.payload["likes"], 42)
        self.assertEqual(event.payload["comments"], 7)
        self.assertEqual(event.payload["shares"], 11)
        self.assertEqual(event.payload["hashtags"], ["GlowUpChallenge"])
        self.assertEqual(batch.statistics["posts_discovered"], 1)
        request = transport.calls[0]
        self.assertEqual(request[0], "tweets/search/recent")
        self.assertEqual(request[1]["query"], "#GlowUpChallenge")
        self.assertEqual(request[1]["max_results"], "100")
        self.assertNotIn("expansions", request[1])

    def test_account_rule_maps_to_from_operator_and_checkpoint_overlap(self):
        transport = FixtureTransport()
        checkpoint = ConnectorCheckpoint(
            cursors={"owned": "2026-08-08T11:50:00Z"}, updated_at=NOW
        )
        self.connector(transport).collect(
            [CollectionRule("owned", "account", "@Acme")], checkpoint
        )
        request = transport.calls[0][1]
        self.assertEqual(request["query"], "from:Acme")
        self.assertEqual(request["start_time"], "2026-08-08T11:45:00Z")

    def test_retryable_failure_retries_and_each_attempt_counts_against_budget(self):
        transport = FixtureTransport()
        attempts = 0

        def flaky(path, params):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise XApiError(503, "internal error", "temporary")
            return transport(path, params)

        connector = XConnector(
            bearer_token="test-token",
            config=XConnectorConfig(tenant_id="tenant-a", source_id="x-api"),
            retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0, jitter_ratio=0),
            transport=flaky,
            clock=lambda: NOW,
            sleeper=lambda _: None,
        )
        batch = connector.collect(
            [CollectionRule("brand", "keyword", "Acme")], ConnectorCheckpoint.empty(NOW)
        )
        self.assertEqual(attempts, 2)
        self.assertEqual(batch.statistics["requests_used"], 2)

    def test_unread_next_page_does_not_advance_checkpoint(self):
        response = json.loads(FIXTURE.read_text())
        response["meta"]["next_token"] = "next"
        with self.assertRaises(XPaginationLimitReached):
            self.connector(FixtureTransport(response)).collect(
                [CollectionRule("brand", "keyword", "Acme")],
                ConnectorCheckpoint.empty(NOW),
            )

    def test_per_run_request_budget_fails_before_another_transport_call(self):
        transport = FixtureTransport()
        with self.assertRaisesRegex(XApiError, "localQuotaGuard"):
            self.connector(transport, max_requests_per_run=1).collect(
                [
                    CollectionRule("brand", "keyword", "Acme"),
                    CollectionRule("owned", "account", "Acme"),
                ],
                ConnectorCheckpoint.empty(NOW),
            )
        self.assertEqual(len(transport.calls), 1)

    def test_collects_ranked_san_francisco_trends_without_expanding_to_post_search(self):
        trends = json.loads(TRENDS_FIXTURE.read_text())

        def transport(path, params):
            self.assertEqual(path, "trends/by/woeid/2487956")
            self.assertEqual(params["max_trends"], "20")
            self.assertEqual(params["trend.fields"], "trend_name,tweet_count")
            return trends

        batch = self.connector(
            transport,
            trends_woeid=2487956,
            trends_location="San Francisco",
        ).collect(
            [CollectionRule("sf-trends", "trend", "woeid:2487956")],
            ConnectorCheckpoint.empty(NOW),
        )

        self.assertEqual(batch.statistics["posts_discovered"], 0)
        self.assertEqual(batch.statistics["trends_discovered"], 3)
        self.assertEqual(batch.statistics["requests_used"], 1)
        self.assertEqual([event.payload["trend_name"] for event in batch.events], [
            "#Fogust",
            "Bay to Breakers",
            "Civic Center",
        ])
        self.assertTrue(all(event.event_type == "social.trend.observed" for event in batch.events))
        self.assertEqual(batch.events[0].attributes["trend_rank"], "1")
        self.assertEqual(batch.events[0].attributes["trend_location"], "San Francisco")


if __name__ == "__main__":
    unittest.main()
