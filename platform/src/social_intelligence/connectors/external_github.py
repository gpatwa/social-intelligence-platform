"""External GitHub collector that lands batches through Databricks Files API.

This mirrors the YouTube worker: durable remote checkpoint, one immutable event
file per run, and a sanitized metric. Extracting a shared runner is a follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re
from typing import Callable, Mapping
from uuid import uuid4

from social_intelligence.connectors.base import CollectionRule
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.databricks_files import DatabricksFilesClient
from social_intelligence.connectors.external_youtube import (
    IDENTIFIER_PATTERN,
    SAFE_ID_PATTERN,
    _integer,
    _required,
)
from social_intelligence.connectors.github import (
    REPOSITORY_PATTERN,
    GitHubConnector,
    GitHubConnectorConfig,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ExternalGitHubConfig:
    """Environment-driven configuration for a stateless external worker."""

    databricks_host: str
    databricks_token: str
    repositories: tuple[str, ...]
    github_token: str = ""
    catalog: str = "dev"
    schema: str = "social_intelligence_dev"
    tenant_id: str = "demo"
    source_id: str = "github-rest-api"
    max_requests_per_run: int = 40
    releases_per_repo: int = 5
    release_lookback_days: int = 30
    status_output_path: str = ""

    def __post_init__(self) -> None:
        for name, value in (("catalog", self.catalog), ("schema", self.schema)):
            if not IDENTIFIER_PATTERN.fullmatch(value):
                raise ValueError(f"Unsafe {name}: {value!r}")
        for name, value in (
            ("tenant_id", self.tenant_id),
            ("source_id", self.source_id),
        ):
            if not SAFE_ID_PATTERN.fullmatch(value):
                raise ValueError(f"Unsafe {name}: {value!r}")
        if not self.repositories:
            raise ValueError("GITHUB_REPOSITORIES is required")
        for repository in self.repositories:
            if not REPOSITORY_PATTERN.fullmatch(repository):
                raise ValueError(f"Unsafe GitHub repository: {repository!r}")
        # Two requests per repository (metadata and releases).
        if self.max_requests_per_run < 2 * len(self.repositories):
            raise ValueError(
                "GITHUB_MAX_REQUESTS_PER_RUN must cover two requests per repository"
            )

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "ExternalGitHubConfig":
        values = environment or os.environ
        repositories = tuple(
            value.strip()
            for value in values.get("GITHUB_REPOSITORIES", "").split(",")
            if value.strip()
        )
        return cls(
            databricks_host=_required(values, "DATABRICKS_HOST"),
            databricks_token=_required(values, "DATABRICKS_TOKEN"),
            repositories=repositories,
            github_token=values.get("GITHUB_API_TOKEN", "").strip(),
            catalog=values.get("DATABRICKS_CATALOG", "dev").strip(),
            schema=values.get(
                "DATABRICKS_SCHEMA", "social_intelligence_dev"
            ).strip(),
            tenant_id=values.get("SOCIAL_TENANT_ID", "demo").strip(),
            source_id=values.get("GITHUB_SOURCE_ID", "github-rest-api").strip(),
            max_requests_per_run=_integer(values, "GITHUB_MAX_REQUESTS_PER_RUN", 40),
            releases_per_repo=_integer(values, "GITHUB_RELEASES_PER_REPO", 5),
            release_lookback_days=_integer(values, "GITHUB_RELEASE_LOOKBACK_DAYS", 30),
            status_output_path=values.get("PIPELINE_STATUS_OUTPUT", "").strip(),
        )

    @property
    def volume_root(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema}/raw_social"

    @property
    def checkpoint_path(self) -> str:
        return (
            f"{self.volume_root}/checkpoints/github/"
            f"{self.tenant_id}/{self.source_id}.json"
        )

    def collection_rules(self) -> tuple[CollectionRule, ...]:
        return tuple(
            CollectionRule(
                rule_id=f"github-community-{sha256(repo.encode()).hexdigest()[:12]}",
                rule_type="community",
                expression=repo,
            )
            for repo in self.repositories
        )


ConnectorFactory = Callable[[ExternalGitHubConfig], GitHubConnector]


def _default_connector(config: ExternalGitHubConfig) -> GitHubConnector:
    return GitHubConnector(
        config=GitHubConnectorConfig(
            tenant_id=config.tenant_id,
            source_id=config.source_id,
            max_requests_per_run=config.max_requests_per_run,
            releases_per_repo=config.releases_per_repo,
            release_lookback_days=config.release_lookback_days,
        ),
        token=config.github_token,
    )


class ExternalGitHubCollector:
    """Run one fail-closed batch with a durable remote cursor."""

    def __init__(
        self,
        config: ExternalGitHubConfig,
        files: DatabricksFilesClient,
        *,
        connector_factory: ConnectorFactory = _default_connector,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.config = config
        self.files = files
        self.connector_factory = connector_factory
        self.clock = clock

    def run(self) -> Mapping[str, object]:
        started_at = self.clock().astimezone(timezone.utc)
        run_id = f"{started_at:%Y%m%dT%H%M%S}-{uuid4().hex}"
        self._ensure_directories()
        checkpoint = self._load_checkpoint()
        try:
            connector = self.connector_factory(self.config)
            batch = connector.collect(self.config.collection_rules(), checkpoint)
            event_path = ""
            if batch.events:
                event_path = f"{self.config.volume_root}/events/github-{run_id}.json"
                payload = "".join(
                    json.dumps(event.to_record(), sort_keys=True) + "\n"
                    for event in batch.events
                ).encode("utf-8")
                self.files.upload(event_path, payload)
            self._save_checkpoint(
                ConnectorCheckpoint(
                    schema_version=batch.checkpoint.schema_version,
                    cursors=batch.checkpoint.cursors,
                    quota=batch.checkpoint.quota,
                    metadata={
                        **dict(batch.checkpoint.metadata),
                        "runtime": "external_files_api",
                        "last_run_id": run_id,
                        "last_event_path": event_path,
                    },
                    updated_at=batch.checkpoint.updated_at,
                )
            )
            metric = self._metric(
                run_id, started_at, "SUCCESS", batch.statistics,
                int(batch.checkpoint.quota.get("requests_used", 0)), event_path,
            )
            self._save_metric(run_id, metric)
            self._write_status_projection(metric)
            return metric
        except Exception as error:
            metric = self._metric(
                run_id, started_at, "FAILED", error_type=type(error).__name__
            )
            try:
                self._save_metric(run_id, metric)
            except Exception:
                pass
            self._write_status_projection(metric)
            raise

    def _ensure_directories(self) -> None:
        for path in (
            f"{self.config.volume_root}/events",
            f"{self.config.volume_root}/checkpoints/github/{self.config.tenant_id}",
            f"{self.config.volume_root}/operations/github/"
            f"{self.config.tenant_id}/{self.config.source_id}",
        ):
            self.files.create_directory(path)

    def _load_checkpoint(self) -> ConnectorCheckpoint:
        payload = self.files.download(self.config.checkpoint_path)
        if payload is None:
            return ConnectorCheckpoint.empty(self.clock().astimezone(timezone.utc))
        try:
            return ConnectorCheckpoint.from_dict(json.loads(payload.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
            raise ValueError("Remote connector checkpoint is invalid") from error

    def _save_checkpoint(self, checkpoint: ConnectorCheckpoint) -> None:
        self.files.upload(
            self.config.checkpoint_path,
            (json.dumps(checkpoint.to_dict(), indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )

    def _save_metric(self, run_id: str, metric: Mapping[str, object]) -> None:
        path = (
            f"{self.config.volume_root}/operations/github/"
            f"{self.config.tenant_id}/{self.config.source_id}/{run_id}.json"
        )
        self.files.upload(path, (json.dumps(metric, sort_keys=True) + "\n").encode("utf-8"))

    def _write_status_projection(self, metric: Mapping[str, object]) -> None:
        if not self.config.status_output_path:
            return
        output_path = os.path.abspath(self.config.status_output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as output:
            json.dump(dict(metric), output, sort_keys=True)
            output.write("\n")

    def _metric(
        self,
        run_id: str,
        started_at: datetime,
        status: str,
        statistics: Mapping[str, int] | None = None,
        requests_used: int = 0,
        event_path: str = "",
        error_type: str = "",
    ) -> dict[str, object]:
        stats = statistics or {}
        return {
            "run_id": run_id,
            "tenant_id": self.config.tenant_id,
            "source_id": self.config.source_id,
            "platform": "github",
            "runtime": "github_actions",
            "started_at": started_at.isoformat(),
            "completed_at": self.clock().astimezone(timezone.utc).isoformat(),
            "status": status,
            "active_rules": int(stats.get("active_rules", 0)),
            "repos_fetched": int(stats.get("repos_fetched", 0)),
            "repos_not_found": int(stats.get("repos_not_found", 0)),
            "snapshots_emitted": int(stats.get("snapshots_emitted", 0)),
            "releases_emitted": int(stats.get("releases_emitted", 0)),
            "events_emitted": int(stats.get("events_emitted", 0)),
            "requests_used": requests_used,
            "requests_cap": self.config.max_requests_per_run,
            "event_path": event_path,
            "error_type": error_type,
        }


def main() -> int:
    config = ExternalGitHubConfig.from_environment()
    files = DatabricksFilesClient(
        host=config.databricks_host,
        token=config.databricks_token,
    )
    result = ExternalGitHubCollector(config, files).run()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
