import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_intelligence.connectors.base import CollectionRule
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.instagram import (
    InstagramApiError,
    InstagramConnector,
    InstagramConnectorConfig,
    InstagramPaginationLimitReached,
)
from social_intelligence.connectors.retry import RetryPolicy


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "instagram"
PAGE = json.loads((FIXTURES / "page_account.json").read_text())
MEDIA = json.loads((FIXTURES / "media.json").read_text())
HASHTAG = json.loads((FIXTURES / "hashtag_search.json").read_text())


class FixtureTransport:
    def __init__(self, media=MEDIA):
        self.calls = []
        self.media = media

    def __call__(self, path, params):
        self.calls.append((path, dict(params)))
        if path == "1181090461764724":
            return PAGE
        if path == "ig_hashtag_search":
            return HASHTAG
        return self.media


class InstagramConnectorTests(unittest.TestCase):
    def connector(self, transport, **overrides):
        values = {
            "tenant_id": "tenant-a",
            "source_id": "instagram-api",
            "page_id": "1181090461764724",
        }
        values.update(overrides)
        return InstagramConnector(
            access_token="test-token",
            config=InstagramConnectorConfig(**values),
            transport=transport,
            clock=lambda: NOW,
            sleeper=lambda _: None,
        )

    def test_maps_linked_business_media_to_canonical_event(self):
        transport = FixtureTransport()
        batch = self.connector(transport).collect(
            [CollectionRule("owned", "account", "linked_business_account")],
            ConnectorCheckpoint.empty(NOW),
        )

        self.assertEqual(len(batch.events), 1)
        event = batch.events[0]
        self.assertEqual(event.platform, "instagram")
        self.assertEqual(event.payload["author_username"], "socialsignals")
        self.assertEqual(event.payload["views"], 1200)
        self.assertEqual(event.payload["likes"], 52)
        self.assertEqual(event.payload["comments"], 8)
        self.assertEqual(event.payload["hashtags"], ["SignalStack", "DataCommunity"])
        self.assertEqual(batch.statistics["requests_used"], 2)
        self.assertEqual(transport.calls[1][0], "17841400000000001/media")
        self.assertEqual(transport.calls[1][1]["limit"], "100")

    def test_hashtag_rule_uses_documented_search_then_recent_media_flow(self):
        transport = FixtureTransport()
        self.connector(transport).collect(
            [CollectionRule("tag", "hashtag", "SignalStack")],
            ConnectorCheckpoint.empty(NOW),
        )
        self.assertEqual([call[0] for call in transport.calls], [
            "1181090461764724",
            "ig_hashtag_search",
            "17843700000000001/recent_media",
        ])
        self.assertEqual(transport.calls[1][1]["q"], "SignalStack")
        self.assertEqual(transport.calls[1][1]["user_id"], "17841400000000001")

    def test_checkpoint_overlap_is_applied_and_old_media_is_not_emitted(self):
        old_media = json.loads(json.dumps(MEDIA))
        old_media["data"][0]["timestamp"] = "2026-08-08T11:30:00+0000"
        transport = FixtureTransport(old_media)
        checkpoint = ConnectorCheckpoint(
            cursors={"owned": "2026-08-08T11:50:00Z"}, updated_at=NOW
        )
        batch = self.connector(transport).collect(
            [CollectionRule("owned", "account", "linked_business_account")], checkpoint
        )
        self.assertEqual(batch.events, ())
        self.assertEqual(batch.checkpoint.cursors["owned"], "2026-08-08T12:00:00Z")

    def test_unread_next_page_does_not_advance_checkpoint(self):
        paged_media = json.loads(json.dumps(MEDIA))
        paged_media["paging"]["cursors"]["after"] = "next-page"
        with self.assertRaises(InstagramPaginationLimitReached):
            self.connector(FixtureTransport(paged_media)).collect(
                [CollectionRule("owned", "account", "linked_business_account")],
                ConnectorCheckpoint.empty(NOW),
            )

    def test_retryable_failure_retries_and_counts_each_attempt(self):
        transport = FixtureTransport()
        attempts = 0

        def flaky(path, params):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise InstagramApiError(503, 2, "temporary")
            return transport(path, params)

        connector = InstagramConnector(
            access_token="test-token",
            config=InstagramConnectorConfig(
                tenant_id="tenant-a",
                source_id="instagram-api",
                page_id="1181090461764724",
            ),
            retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0, jitter_ratio=0),
            transport=flaky,
            clock=lambda: NOW,
            sleeper=lambda _: None,
        )
        batch = connector.collect(
            [CollectionRule("owned", "account", "linked_business_account")],
            ConnectorCheckpoint.empty(NOW),
        )
        self.assertEqual(attempts, 3)
        self.assertEqual(batch.statistics["requests_used"], 3)


if __name__ == "__main__":
    unittest.main()
