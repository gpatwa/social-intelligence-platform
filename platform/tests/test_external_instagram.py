import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_intelligence.connectors.base import ConnectorBatch
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.external_instagram import (
    ExternalInstagramCollector,
    ExternalInstagramConfig,
)
from social_intelligence.contracts import SocialEventEnvelope


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


class MemoryFiles:
    def __init__(self):
        self.files = {}
        self.uploads = []
        self.directories = []

    def download(self, path):
        return self.files.get(path)

    def upload(self, path, content):
        self.files[path] = content
        self.uploads.append(path)

    def create_directory(self, path):
        self.directories.append(path)


class FakeConnector:
    def __init__(self, quota_observer, event):
        self.quota_observer = quota_observer
        self.event = event

    def collect(self, rules, checkpoint):
        self.quota_observer({"instagram_requests_used": 1, "instagram_requests_limit": 100})
        return ConnectorBatch(
            events=(self.event,),
            checkpoint=ConnectorCheckpoint(
                cursors={rules[0].rule_id: NOW.isoformat()},
                quota={"instagram_requests_used": 2, "instagram_requests_limit": 100},
                updated_at=NOW,
            ),
            statistics={"active_rules": 1, "posts_discovered": 1, "events_emitted": 1},
        )


class ExternalInstagramCollectorTests(unittest.TestCase):
    def setUp(self):
        self.config = ExternalInstagramConfig(
            databricks_host="https://dbc.example.com",
            databricks_token="token",
            instagram_access_token="access-token",
            instagram_page_id="1181090461764724",
            hashtags=("SignalStack",),
        )
        self.event = SocialEventEnvelope.create(
            tenant_id="demo",
            source_id="instagram-graph-api",
            platform="instagram",
            event_type="social.post.observed",
            source_object_id="media-1",
            occurred_at=NOW,
            collected_at=NOW,
            payload={"post_id": "media-1"},
        )

    def test_configuration_builds_stable_account_and_hashtag_rules(self):
        rules = self.config.collection_rules()
        self.assertEqual([rule.rule_type for rule in rules], ["account", "hashtag"])
        self.assertEqual(rules[0].expression, "linked_business_account")

    def test_environment_requires_page_and_access_token(self):
        with self.assertRaisesRegex(ValueError, "INSTAGRAM_ACCESS_TOKEN"):
            ExternalInstagramConfig.from_environment(
                {
                    "DATABRICKS_HOST": "https://dbc.example.com",
                    "DATABRICKS_TOKEN": "token",
                    "INSTAGRAM_PAGE_ID": "1181090461764724",
                }
            )

    def test_lands_events_before_checkpoint_and_writes_safe_status(self):
        files = MemoryFiles()

        def factory(config, quota_observer):
            return FakeConnector(quota_observer, self.event)

        with tempfile.TemporaryDirectory() as directory:
            status_path = os.path.join(directory, "pipeline-status.json")
            config = ExternalInstagramConfig(
                **{**self.config.__dict__, "status_output_path": status_path}
            )
            metric = ExternalInstagramCollector(
                config, files, connector_factory=factory, clock=lambda: NOW
            ).run()
            with open(status_path, encoding="utf-8") as status_file:
                status = json.load(status_file)

        event_path = next(path for path in files.uploads if "/events/" in path)
        checkpoint_paths = [path for path in files.uploads if "/checkpoints/instagram/" in path]
        operation_path = next(path for path in files.uploads if "/operations/instagram/" in path)
        event_index = files.uploads.index(event_path)
        checkpoint_indexes = [
            index for index, path in enumerate(files.uploads)
            if "/checkpoints/instagram/" in path
        ]
        operation_index = files.uploads.index(operation_path)
        self.assertGreater(checkpoint_indexes[-1], event_index)
        self.assertGreater(operation_index, checkpoint_indexes[-1])
        self.assertEqual(metric["requests_remaining"], 98)
        self.assertEqual(status["platform"], "instagram")
        self.assertNotIn("instagram_access_token", status)


if __name__ == "__main__":
    unittest.main()
