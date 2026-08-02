from datetime import datetime, timezone
import json
import unittest

from social_intelligence.connectors.base import ConnectorBatch
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.external_youtube import (
    ExternalYouTubeCollector,
    ExternalYouTubeConfig,
)
from social_intelligence.contracts import SocialEventEnvelope


NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


class MemoryFiles:
    def __init__(self):
        self.files = {}
        self.uploads = []

    def download(self, path):
        return self.files.get(path)

    def upload(self, path, content):
        self.files[path] = content
        self.uploads.append(path)


class FakeConnector:
    def __init__(self, quota_observer, event):
        self.quota_observer = quota_observer
        self.event = event

    def collect(self, rules, checkpoint):
        self.quota_observer(
            {"quota_day": "2026-08-01", "search_calls": 1, "core_units": 0}
        )
        return ConnectorBatch(
            events=(self.event,),
            checkpoint=ConnectorCheckpoint(
                cursors={rules[0].rule_id: NOW.isoformat()},
                quota={
                    "quota_day": "2026-08-01",
                    "search_calls": 1,
                    "core_units": 1,
                },
                updated_at=NOW,
            ),
            statistics={
                "active_rules": 1,
                "videos_discovered": 1,
                "events_emitted": 1,
            },
        )


class ExternalYouTubeCollectorTests(unittest.TestCase):
    def setUp(self):
        self.config = ExternalYouTubeConfig(
            databricks_host="https://dbc.example.com",
            databricks_token="token",
            youtube_api_key="api-key",
            search_expression="data engineering|lakehouse",
        )
        self.event = SocialEventEnvelope.create(
            tenant_id="demo",
            source_id="youtube-api-v3",
            platform="youtube",
            event_type="social.post.observed",
            source_object_id="video-1",
            occurred_at=NOW,
            collected_at=NOW,
            payload={"post_id": "video-1"},
        )

    def test_configuration_builds_stable_rules(self):
        first = self.config.collection_rules()
        second = self.config.collection_rules()
        self.assertEqual(first[0].rule_id, second[0].rule_id)
        self.assertEqual(first[0].expression, "data engineering|lakehouse")

    def test_environment_requires_explicit_credentials_and_rules(self):
        with self.assertRaisesRegex(ValueError, "YOUTUBE_API_KEY"):
            ExternalYouTubeConfig.from_environment(
                {
                    "DATABRICKS_HOST": "https://dbc.example.com",
                    "DATABRICKS_TOKEN": "token",
                    "YOUTUBE_SEARCH_EXPRESSION": "topic",
                }
            )

    def test_lands_events_before_committing_cursor_and_writes_metrics(self):
        files = MemoryFiles()

        def factory(config, quota_observer):
            return FakeConnector(quota_observer, self.event)

        collector = ExternalYouTubeCollector(
            self.config,
            files,
            connector_factory=factory,
            clock=lambda: NOW,
        )
        metric = collector.run()

        event_upload = next(path for path in files.uploads if "/events/" in path)
        checkpoint_uploads = [
            path for path in files.uploads if "/checkpoints/youtube/" in path
        ]
        operation_upload = next(
            path for path in files.uploads if "/operations/youtube/" in path
        )
        self.assertLess(files.uploads.index(event_upload), len(files.uploads) - 1)
        self.assertEqual(len(checkpoint_uploads), 2)
        event_index = files.uploads.index(event_upload)
        checkpoint_indexes = [
            index
            for index, path in enumerate(files.uploads)
            if "/checkpoints/youtube/" in path
        ]
        operation_index = files.uploads.index(operation_upload)
        self.assertGreater(checkpoint_indexes[-1], event_index)
        self.assertGreater(operation_index, checkpoint_indexes[-1])
        self.assertEqual(metric["status"], "SUCCESS")
        self.assertEqual(metric["search_calls_remaining"], 94)
        self.assertEqual(metric["core_units_remaining"], 9499)

        records = files.files[event_upload].decode("utf-8").splitlines()
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0])["source_object_id"], "video-1")
        checkpoint = json.loads(files.files[self.config.checkpoint_path])
        self.assertEqual(checkpoint["metadata"]["runtime"], "external_files_api")


if __name__ == "__main__":
    unittest.main()
