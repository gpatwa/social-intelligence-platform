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
    XReadLedger,
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
        self.assertEqual(
            event.payload["source_url"],
            f"https://x.com/i/web/status/{event.source_object_id}",
        )
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


class XReadBudgetTests(unittest.TestCase):
    def connector(self, transport, observer=None, **overrides):
        values = {"tenant_id": "tenant-a", "source_id": "x-api"}
        values.update(overrides)
        return XConnector(
            bearer_token="test-token",
            config=XConnectorConfig(**values),
            transport=transport,
            clock=lambda: NOW,
            sleeper=lambda _: None,
            quota_observer=observer,
        )

    def spent(self, reads_today, reads_this_month=None, day="2026-08-08"):
        quota = {
            "x_read_day": day,
            "x_read_month": day[:7],
            "x_reads_today": reads_today,
            "x_reads_this_month": reads_today if reads_this_month is None else reads_this_month,
        }
        return ConnectorCheckpoint(quota=quota, updated_at=NOW)

    def test_page_size_shrinks_to_the_remaining_budget_and_reads_are_counted(self):
        transport = FixtureTransport()
        batch = self.connector(transport, daily_read_budget=50).collect(
            [CollectionRule("brand", "keyword", "Acme")], ConnectorCheckpoint.empty(NOW)
        )
        self.assertEqual(transport.calls[0][1]["max_results"], "50")
        self.assertEqual(batch.statistics["reads_used"], 1)
        self.assertEqual(batch.statistics["reads_remaining_today"], 49)
        self.assertEqual(batch.checkpoint.quota["x_reads_today"], 1)
        self.assertEqual(batch.statistics["read_budget_exhausted"], 0)

    def test_exhausted_budget_makes_no_request_and_keeps_the_cursor(self):
        transport = FixtureTransport()
        checkpoint = self.spent(1_995)
        batch = self.connector(transport).collect(
            [CollectionRule("brand", "keyword", "Acme")], checkpoint
        )
        self.assertEqual(transport.calls, [])
        self.assertEqual(batch.events, ())
        self.assertNotIn("brand", batch.checkpoint.cursors)
        self.assertEqual(batch.statistics["read_budget_exhausted"], 1)

    def test_monthly_budget_applies_across_days(self):
        transport = FixtureTransport()
        checkpoint = self.spent(0, reads_this_month=29_995)
        batch = self.connector(transport).collect(
            [CollectionRule("brand", "keyword", "Acme")], checkpoint
        )
        self.assertEqual(transport.calls, [])
        self.assertEqual(batch.statistics["read_budget_exhausted"], 1)

    def test_ledger_resets_daily_and_monthly(self):
        quota = {"x_read_day": "2026-08-07", "x_read_month": "2026-08", "x_reads_today": 1_999, "x_reads_this_month": 5_000}
        ledger = XReadLedger.from_quota(quota, NOW, daily_budget=2_000, monthly_budget=30_000)
        self.assertEqual((ledger.reads_today, ledger.reads_this_month), (0, 5_000))
        quota["x_read_month"] = "2026-07"
        ledger = XReadLedger.from_quota(quota, NOW, daily_budget=2_000, monthly_budget=30_000)
        self.assertEqual((ledger.reads_today, ledger.reads_this_month), (0, 0))

    def test_later_rules_stop_when_the_budget_runs_out_mid_run(self):
        transport = FixtureTransport()
        batch = self.connector(transport, daily_read_budget=10).collect(
            [CollectionRule("brand", "keyword", "Acme"), CollectionRule("owned", "account", "Acme")],
            ConnectorCheckpoint.empty(NOW),
        )
        self.assertEqual(len(transport.calls), 1)
        self.assertIn("brand", batch.checkpoint.cursors)
        self.assertNotIn("owned", batch.checkpoint.cursors)
        self.assertEqual(len(batch.events), 1)
        self.assertEqual(batch.statistics["read_budget_exhausted"], 1)

    def test_trends_are_capped_and_counted_and_skipped_when_exhausted(self):
        trends = json.loads(TRENDS_FIXTURE.read_text())
        calls = []

        def transport(path, params):
            calls.append(params)
            return trends

        batch = self.connector(
            transport, trends_woeid=2487956, trends_location="San Francisco", daily_read_budget=5
        ).collect([CollectionRule("sf-trends", "trend", "woeid:2487956")], ConnectorCheckpoint.empty(NOW))
        self.assertEqual(calls[0]["max_trends"], "5")
        self.assertEqual(batch.statistics["reads_used"], 3)

        calls.clear()
        batch = self.connector(
            transport, trends_woeid=2487956, trends_location="San Francisco"
        ).collect([CollectionRule("sf-trends", "trend", "woeid:2487956")], self.spent(2_000))
        self.assertEqual(calls, [])
        self.assertEqual(batch.statistics["read_budget_exhausted"], 1)

    def test_billed_reads_are_persisted_before_a_later_failure(self):
        snapshots = []
        response = json.loads(FIXTURE.read_text())
        response["meta"]["next_token"] = "next"
        with self.assertRaises(XPaginationLimitReached):
            self.connector(FixtureTransport(response), observer=snapshots.append).collect(
                [CollectionRule("brand", "keyword", "Acme")], ConnectorCheckpoint.empty(NOW)
            )
        self.assertEqual(snapshots[-1]["x_reads_today"], 1)

    def test_budget_configuration_is_validated(self):
        with self.assertRaises(ValueError):
            XConnectorConfig(tenant_id="t", source_id="s", daily_read_budget=100, monthly_read_budget=50)
        with self.assertRaises(ValueError):
            XConnectorConfig(tenant_id="t", source_id="s", monthly_read_budget=3_000_001)


if __name__ == "__main__":
    unittest.main()
