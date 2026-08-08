import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_intelligence.connectors.base import ConnectorBatch
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.external_x import ExternalXCollector, ExternalXConfig
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


class ExternalXCollectorTests(unittest.TestCase):
    def setUp(self):
        self.config = ExternalXConfig(
            databricks_host="https://dbc.example.com",
            databricks_token="token",
            x_bearer_token="bearer-token",
            search_expression="Acme",
        )
        self.event = SocialEventEnvelope.create(
            tenant_id="demo",
            source_id="x-api-v2",
            platform="x",
            event_type="social.post.observed",
            source_object_id="post-1",
            occurred_at=NOW,
            collected_at=NOW,
            payload={"post_id": "post-1"},
        )

    def test_configuration_builds_stable_cross_platform_rules(self):
        config = ExternalXConfig(
            databricks_host="https://dbc.example.com",
            databricks_token="token",
            x_bearer_token="bearer-token",
            hashtags=("#GlowUpChallenge",),
            account_handles=("@Acme",),
        )
        rules = config.collection_rules()
        self.assertEqual([rule.rule_type for rule in rules], ["hashtag", "account"])
        self.assertEqual(rules, config.collection_rules())

    def test_lands_events_before_checkpoint_and_records_x_metrics(self):
        files = MemoryFiles()

        class FakeConnector:
            def collect(self, rules, checkpoint):
                return ConnectorBatch(
                    events=(self_event,),
                    checkpoint=ConnectorCheckpoint(
                        cursors={rules[0].rule_id: NOW.isoformat()},
                        quota={"x_requests_used": 2, "x_requests_limit": 10},
                        updated_at=NOW,
                    ),
                    statistics={"active_rules": 1, "posts_discovered": 1, "events_emitted": 1},
                )

        self_event = self.event
        collector = ExternalXCollector(
            self.config,
            files,
            connector_factory=lambda config, observer: FakeConnector(),
            clock=lambda: NOW,
        )
        metric = collector.run()

        event_path = next(path for path in files.uploads if "/events/" in path)
        checkpoint_indexes = [
            index for index, path in enumerate(files.uploads) if "/checkpoints/x/" in path
        ]
        self.assertLess(files.uploads.index(event_path), checkpoint_indexes[-1])
        self.assertEqual(metric["posts_discovered"], 1)
        self.assertEqual(metric["requests_remaining"], 8)
        self.assertEqual(json.loads(files.files[event_path]) ["source_object_id"], "post-1")


if __name__ == "__main__":
    unittest.main()
