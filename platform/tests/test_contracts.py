import sys
import unittest
from datetime import datetime, timezone
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_intelligence.contracts import SocialEventEnvelope, make_idempotency_key


class SocialEventEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.occurred_at = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

    def test_idempotency_key_is_stable_across_retries(self):
        first = make_idempotency_key(
            "tenant-a", "youtube", "video-123", "social.post.observed", self.occurred_at
        )
        retry = make_idempotency_key(
            "tenant-a", "youtube", "video-123", "social.post.observed", self.occurred_at
        )
        self.assertEqual(first, retry)

    def test_idempotency_key_is_tenant_scoped(self):
        first = make_idempotency_key(
            "tenant-a", "youtube", "video-123", "social.post.observed", self.occurred_at
        )
        second = make_idempotency_key(
            "tenant-b", "youtube", "video-123", "social.post.observed", self.occurred_at
        )
        self.assertNotEqual(first, second)

    def test_envelope_serializes_payload_as_replayable_json(self):
        event = SocialEventEnvelope.create(
            tenant_id="tenant-a",
            source_id="youtube-owned",
            platform="youtube",
            event_type="social.post.observed",
            source_object_id="video-123",
            occurred_at=self.occurred_at,
            collected_at=self.occurred_at,
            payload={"title": "Launch", "views": 100},
        )
        record = event.to_record()
        self.assertEqual(record["schema_version"], "1.0")
        self.assertEqual(record["source_object_id"], "video-123")
        self.assertEqual(record["payload"], '{"title": "Launch", "views": 100}')

    def test_unknown_event_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported event type"):
            SocialEventEnvelope.create(
                tenant_id="tenant-a",
                source_id="youtube-owned",
                platform="youtube",
                event_type="social.unknown",
                source_object_id="video-123",
                occurred_at=self.occurred_at,
                payload={},
            )

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            SocialEventEnvelope.create(
                tenant_id="tenant-a",
                source_id="youtube-owned",
                platform="youtube",
                event_type="social.post.observed",
                source_object_id="video-123",
                occurred_at=datetime(2026, 7, 30, 12, 0),
                payload={},
            )

    def test_machine_readable_schema_matches_required_contract(self):
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "social-event-envelope-v1.json"
        )
        schema = json.loads(schema_path.read_text())
        required = set(schema["required"])
        self.assertEqual(
            required,
            {
                "event_id",
                "schema_version",
                "tenant_id",
                "source_id",
                "platform",
                "event_type",
                "source_object_id",
                "occurred_at",
                "collected_at",
                "idempotency_key",
                "correlation_id",
                "payload",
                "attributes",
            },
        )


if __name__ == "__main__":
    unittest.main()
