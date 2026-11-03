from datetime import datetime, timezone
import json
import unittest

from social_intelligence.connectors.base import CollectionRule
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.external_github import (
    ExternalGitHubCollector,
    ExternalGitHubConfig,
)
from social_intelligence.connectors.github import (
    GitHubApiError,
    GitHubConnector,
    GitHubConnectorConfig,
    RequestBudgetExceeded,
)
from social_intelligence.connectors.retry import RetryPolicy


NOW = datetime(2026, 11, 3, 6, 43, tzinfo=timezone.utc)
REPO = {
    "full_name": "langchain-ai/langgraph",
    "html_url": "https://github.com/langchain-ai/langgraph",
    "description": "Build resilient agents as graphs",
    "owner": {"login": "langchain-ai"},
    "topics": ["agents", "langgraph"],
    "stargazers_count": 1200,
    "forks_count": 90,
    "open_issues_count": 40,
    "pushed_at": "2026-11-02T10:00:00Z",
}
RELEASES = [
    {"id": 3, "tag_name": "v3", "name": "v3", "body": "New", "draft": False,
     "published_at": "2026-11-01T00:00:00Z", "html_url": "https://github.com/x/y/r/3"},
    {"id": 2, "tag_name": "v2", "draft": False,
     "published_at": "2026-10-20T00:00:00Z"},
    {"id": 1, "tag_name": "v1", "draft": True, "published_at": None},
]


class FakeTransport:
    def __init__(self, missing=()):
        self.paths = []
        self.missing = set(missing)

    def __call__(self, path):
        self.paths.append(path)
        repo_path = path.split("?")[0]
        if any(repo_path.startswith(f"/repos/{name}") for name in self.missing):
            raise GitHubApiError(404, "Not Found")
        return RELEASES if repo_path.endswith("/releases") else REPO


def rule(expression="langchain-ai/langgraph"):
    return CollectionRule(
        rule_id="github-community-1", rule_type="community", expression=expression
    )


def connector(transport, **overrides):
    return GitHubConnector(
        config=GitHubConnectorConfig("demo", "github-rest-api", **overrides),
        transport=transport,
        retry_policy=RetryPolicy(max_attempts=2),
        sleeper=lambda _: None,
        clock=lambda: NOW,
    )


class GitHubConnectorTests(unittest.TestCase):
    def test_first_run_emits_snapshot_and_new_releases_only(self):
        batch = connector(FakeTransport()).collect(
            [rule()], ConnectorCheckpoint.empty(NOW)
        )
        kinds = sorted(e.attributes["resource_type"] for e in batch.events)
        self.assertEqual(kinds, ["release", "release", "repo_snapshot"])
        snapshot = next(
            e for e in batch.events if e.attributes["resource_type"] == "repo_snapshot"
        )
        self.assertEqual(snapshot.payload["post_id"], "langchain-ai/langgraph@2026-11-03")
        self.assertEqual(snapshot.payload["saves"], 1200)
        self.assertEqual(snapshot.payload["shares"], 90)
        self.assertEqual(snapshot.payload["likes"], 0)
        self.assertEqual(snapshot.attributes["rule_id"], "github-community-1")
        self.assertEqual(snapshot.platform, "github")
        self.assertEqual(batch.statistics["releases_emitted"], 2)

    def test_second_run_same_day_emits_nothing_and_keeps_cursors(self):
        first = connector(FakeTransport()).collect(
            [rule()], ConnectorCheckpoint.empty(NOW)
        )
        second = connector(FakeTransport()).collect([rule()], first.checkpoint)
        self.assertEqual(second.events, ())

    def test_next_day_emits_a_new_snapshot_but_no_old_releases(self):
        first = connector(FakeTransport()).collect(
            [rule()], ConnectorCheckpoint.empty(NOW)
        )
        later = GitHubConnector(
            config=GitHubConnectorConfig("demo", "github-rest-api"),
            transport=FakeTransport(),
            clock=lambda: NOW.replace(day=4),
        )
        batch = later.collect([rule()], first.checkpoint)
        self.assertEqual(
            [e.attributes["resource_type"] for e in batch.events], ["repo_snapshot"]
        )

    def test_snapshot_idempotency_key_is_stable_across_retries(self):
        keys = [
            next(
                e for e in connector(FakeTransport()).collect(
                    [rule()], ConnectorCheckpoint.empty(NOW)
                ).events
                if e.attributes["resource_type"] == "repo_snapshot"
            ).idempotency_key
            for _ in range(2)
        ]
        self.assertEqual(keys[0], keys[1])

    def test_missing_repo_is_counted_and_skipped(self):
        batch = connector(FakeTransport(missing=["gone/repo"])).collect(
            [rule("gone/repo")], ConnectorCheckpoint.empty(NOW)
        )
        self.assertEqual(batch.events, ())
        self.assertEqual(batch.statistics["repos_not_found"], 1)

    def test_keyword_rules_and_unsafe_repositories_are_rejected(self):
        with self.assertRaises(ValueError):
            connector(FakeTransport()).collect(
                [CollectionRule("k", "keyword", "agents")],
                ConnectorCheckpoint.empty(NOW),
            )
        with self.assertRaises(ValueError):
            connector(FakeTransport()).collect(
                [rule("a/b?x=1")], ConnectorCheckpoint.empty(NOW)
            )

    def test_request_cap_fails_closed(self):
        with self.assertRaises(RequestBudgetExceeded):
            connector(FakeTransport(), max_requests_per_run=1).collect(
                [rule()], ConnectorCheckpoint.empty(NOW)
            )

    def test_only_repo_and_release_endpoints_are_requested(self):
        transport = FakeTransport()
        batch = connector(transport).collect([rule()], ConnectorCheckpoint.empty(NOW))
        self.assertEqual(
            transport.paths,
            [
                "/repos/langchain-ai/langgraph",
                "/repos/langchain-ai/langgraph/releases?per_page=5",
            ],
        )
        for event in batch.events:
            self.assertEqual(event.payload["author_id"], "langchain-ai")


class MemoryFiles:
    def __init__(self):
        self.files = {}

    def download(self, path):
        return self.files.get(path)

    def upload(self, path, content):
        self.files[path] = content

    def create_directory(self, path):
        pass


class ExternalGitHubTests(unittest.TestCase):
    def config(self, **overrides):
        values = dict(
            databricks_host="https://example.databricks.com",
            databricks_token="token-placeholder",
            repositories=("langchain-ai/langgraph",),
        )
        values.update(overrides)
        return ExternalGitHubConfig(**values)

    def test_run_lands_events_commits_checkpoint_and_metric(self):
        files = MemoryFiles()
        collector = ExternalGitHubCollector(
            self.config(),
            files,
            connector_factory=lambda cfg: connector(FakeTransport()),
            clock=lambda: NOW,
        )
        metric = collector.run()
        self.assertEqual(metric["status"], "SUCCESS")
        self.assertEqual(metric["events_emitted"], 3)
        paths = list(files.files)
        self.assertTrue(any("/events/github-" in p for p in paths))
        self.assertTrue(any(p.endswith("/checkpoints/github/demo/github-rest-api.json") for p in paths))
        self.assertNotIn("token-placeholder", json.dumps(metric))

    def test_failed_run_does_not_commit_checkpoint(self):
        files = MemoryFiles()

        def failing(cfg):
            return connector(FakeTransport(), max_requests_per_run=1)

        with self.assertRaises(RequestBudgetExceeded):
            ExternalGitHubCollector(
                self.config(), files, connector_factory=failing, clock=lambda: NOW
            ).run()
        self.assertFalse(any("checkpoints" in p for p in files.files))

    def test_config_rejects_unsafe_input_and_a_cap_below_two_per_repo(self):
        with self.assertRaises(ValueError):
            self.config(repositories=())
        with self.assertRaises(ValueError):
            self.config(repositories=("a/b;drop",))
        with self.assertRaises(ValueError):
            self.config(max_requests_per_run=1)


if __name__ == "__main__":
    unittest.main()
