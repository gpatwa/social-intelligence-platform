import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_intelligence.connectors.base import CollectionRule
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.quota import QuotaExceeded, QuotaPolicy
from social_intelligence.connectors.retry import RetryPolicy
from social_intelligence.connectors.youtube import (
    YouTubeApiError,
    YouTubeConnector,
    YouTubeConnectorConfig,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "youtube"
NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


class FixtureTransport:
    def __init__(self):
        self.calls = []
        self.responses = {
            "search": fixture("search.json"),
            "videos": fixture("videos.json"),
            "commentThreads": fixture("comment_threads.json"),
            "comments": fixture("comments.json"),
        }

    def __call__(self, resource, params):
        self.calls.append((resource, dict(params)))
        return self.responses[resource]


class YouTubeConnectorTests(unittest.TestCase):
    def connector(self, transport, **overrides):
        values = {
            "tenant_id": "tenant-a",
            "source_id": "youtube-api",
            "collect_comments": True,
            "collect_replies": True,
        }
        values.update(overrides)
        return YouTubeConnector(
            api_key="test-key",
            config=YouTubeConnectorConfig(**values),
            transport=transport,
            clock=lambda: NOW,
            sleeper=lambda _: None,
        )

    def test_maps_video_comments_and_replies_to_the_canonical_envelope(self):
        transport = FixtureTransport()
        batch = self.connector(transport).collect(
            [CollectionRule("brand-acme", "keyword", "Acme|GlowUpChallenge")],
            ConnectorCheckpoint.empty(NOW),
        )

        self.assertEqual(len(batch.events), 3)
        by_id = {event.source_object_id: event for event in batch.events}
        self.assertEqual(set(by_id), {"video-001", "comment-001", "reply-001"})
        self.assertEqual(by_id["video-001"].payload["views"], 12_500)
        self.assertEqual(
            by_id["video-001"].payload["hashtags"], ["GlowUpChallenge"]
        )
        self.assertEqual(
            by_id["comment-001"].attributes["parent_video_id"], "video-001"
        )
        self.assertEqual(by_id["comment-001"].payload["comments"], 1)
        self.assertEqual(
            batch.checkpoint.cursors["brand-acme"], "2026-07-31T12:00:00Z"
        )
        self.assertEqual(batch.checkpoint.quota["search_calls"], 1)
        self.assertEqual(batch.checkpoint.quota["core_units"], 3)
        search_call = next(call for call in transport.calls if call[0] == "search")
        video_call = next(call for call in transport.calls if call[0] == "videos")
        self.assertIn("snippet", search_call[1]["fields"])
        self.assertEqual(video_call[1]["part"], "statistics")
        self.assertEqual(video_call[1]["fields"], "items(id,statistics)")

    def test_duplicate_video_across_rules_emits_one_logical_event(self):
        transport = FixtureTransport()
        batch = self.connector(
            transport,
            collect_comments=False,
            collect_replies=False,
        ).collect(
            [
                CollectionRule("brand-acme", "keyword", "Acme"),
                CollectionRule("owned-channel", "channel", "channel-001"),
            ],
            ConnectorCheckpoint.empty(NOW),
        )

        self.assertEqual(len(batch.events), 1)
        self.assertEqual(batch.statistics["videos_discovered"], 1)
        self.assertEqual(batch.checkpoint.quota["search_calls"], 2)
        search_calls = [call for call in transport.calls if call[0] == "search"]
        self.assertEqual(search_calls[1][1]["channelId"], "channel-001")

    def test_comments_disabled_is_a_valid_video_only_batch(self):
        transport = FixtureTransport()

        def comments_disabled(resource, params):
            if resource == "commentThreads":
                raise YouTubeApiError(403, "commentsDisabled", "disabled")
            return transport(resource, params)

        batch = self.connector(comments_disabled).collect(
            [CollectionRule("brand-acme", "keyword", "Acme")],
            ConnectorCheckpoint.empty(NOW),
        )
        self.assertEqual([event.source_object_id for event in batch.events], ["video-001"])

    def test_transient_search_failure_retries_and_consumes_each_attempt(self):
        transport = FixtureTransport()
        attempts = 0
        quota_updates = []

        def flaky(resource, params):
            nonlocal attempts
            if resource == "search":
                attempts += 1
                if attempts == 1:
                    raise YouTubeApiError(503, "backendError", "temporary")
            return transport(resource, params)

        connector = YouTubeConnector(
            api_key="test-key",
            config=YouTubeConnectorConfig(
                tenant_id="tenant-a",
                source_id="youtube-api",
            ),
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=0,
                jitter_ratio=0,
            ),
            transport=flaky,
            clock=lambda: NOW,
            sleeper=lambda _: None,
            quota_observer=quota_updates.append,
        )
        batch = connector.collect(
            [CollectionRule("brand-acme", "keyword", "Acme")],
            ConnectorCheckpoint.empty(NOW),
        )

        self.assertEqual(attempts, 2)
        self.assertEqual(quota_updates[0]["search_calls"], 1)
        self.assertEqual(quota_updates[1]["search_calls"], 2)
        self.assertEqual(batch.checkpoint.quota["search_calls"], 2)

    def test_persisted_quota_prevents_transport_call(self):
        transport = FixtureTransport()
        checkpoint = ConnectorCheckpoint(
            quota={
                "quota_day": "2026-07-31",
                "search_calls": 1,
                "core_units": 0,
            },
            updated_at=NOW,
        )
        connector = YouTubeConnector(
            api_key="test-key",
            config=YouTubeConnectorConfig(
                tenant_id="tenant-a",
                source_id="youtube-api",
            ),
            quota_policy=QuotaPolicy(
                search_daily_limit=1,
                search_reserve=0,
                core_daily_limit=10,
                core_reserve=0,
            ),
            transport=transport,
            clock=lambda: NOW,
        )

        with self.assertRaises(QuotaExceeded):
            connector.collect(
                [CollectionRule("brand-acme", "keyword", "Acme")],
                checkpoint,
            )
        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()
