"""External Instagram collector that lands replayable batches through Databricks Files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
import os
import re
from typing import Callable, Mapping
from uuid import uuid4

from social_intelligence.connectors.base import CollectionRule, SourceConnector
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.databricks_files import DatabricksFilesClient
from social_intelligence.connectors.instagram import InstagramConnector, InstagramConnectorConfig


IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SAFE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
HASHTAG_PATTERN = re.compile(r"#?[\w-]{1,100}", re.UNICODE)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _integer(environment: Mapping[str, str], name: str, default: int) -> int:
    raw = environment.get(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _nonnegative_integer(value: object, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ExternalInstagramConfig:
    """Environment-driven configuration for one stateless Instagram run."""

    databricks_host: str
    databricks_token: str
    instagram_access_token: str
    instagram_page_id: str
    catalog: str = "dev"
    schema: str = "social_intelligence_dev"
    tenant_id: str = "demo"
    source_id: str = "instagram-graph-api"
    hashtags: tuple[str, ...] = ()
    lookback_hours: int = 24
    max_media_pages_per_rule: int = 1
    max_requests_per_run: int = 100
    status_output_path: str = ""

    def __post_init__(self) -> None:
        for name, value in (("catalog", self.catalog), ("schema", self.schema)):
            if not IDENTIFIER_PATTERN.fullmatch(value):
                raise ValueError(f"Unsafe {name}: {value!r}")
        for name, value in (("tenant_id", self.tenant_id), ("source_id", self.source_id)):
            if not SAFE_ID_PATTERN.fullmatch(value):
                raise ValueError(f"Unsafe {name}: {value!r}")
        if not re.fullmatch(r"[0-9]{5,32}", self.instagram_page_id):
            raise ValueError("INSTAGRAM_PAGE_ID must be a numeric Facebook Page ID")
        if not 1 <= self.lookback_hours <= 168:
            raise ValueError("INSTAGRAM_LOOKBACK_HOURS must be between 1 and 168")
        if not 1 <= self.max_media_pages_per_rule <= 10:
            raise ValueError("INSTAGRAM_MAX_MEDIA_PAGES_PER_RULE must be between 1 and 10")
        if not 1 <= self.max_requests_per_run <= 450:
            raise ValueError("INSTAGRAM_MAX_REQUESTS_PER_RUN must be between 1 and 450")
        for hashtag in self.hashtags:
            if not HASHTAG_PATTERN.fullmatch(hashtag):
                raise ValueError(f"Unsafe Instagram hashtag: {hashtag!r}")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "ExternalInstagramConfig":
        values = environment or os.environ
        hashtags = tuple(
            value.strip() for value in values.get("INSTAGRAM_HASHTAGS", "").split(",") if value.strip()
        )
        return cls(
            databricks_host=_required(values, "DATABRICKS_HOST"),
            databricks_token=_required(values, "DATABRICKS_TOKEN"),
            instagram_access_token=_required(values, "INSTAGRAM_ACCESS_TOKEN"),
            instagram_page_id=_required(values, "INSTAGRAM_PAGE_ID"),
            catalog=values.get("DATABRICKS_CATALOG", "dev").strip(),
            schema=values.get("DATABRICKS_SCHEMA", "social_intelligence_dev").strip(),
            tenant_id=values.get("SOCIAL_TENANT_ID", "demo").strip(),
            source_id=values.get("INSTAGRAM_SOURCE_ID", "instagram-graph-api").strip(),
            hashtags=hashtags,
            lookback_hours=_integer(values, "INSTAGRAM_LOOKBACK_HOURS", 24),
            max_media_pages_per_rule=_integer(values, "INSTAGRAM_MAX_MEDIA_PAGES_PER_RULE", 1),
            max_requests_per_run=_integer(values, "INSTAGRAM_MAX_REQUESTS_PER_RUN", 100),
            status_output_path=values.get("PIPELINE_STATUS_OUTPUT", "").strip(),
        )

    @property
    def volume_root(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema}/raw_social"

    @property
    def checkpoint_path(self) -> str:
        return f"{self.volume_root}/checkpoints/instagram/{self.tenant_id}/{self.source_id}.json"

    def collection_rules(self) -> tuple[CollectionRule, ...]:
        requested = [("account", "linked_business_account")]
        requested.extend(("hashtag", value) for value in self.hashtags)
        return tuple(
            CollectionRule(
                rule_id=f"instagram-{rule_type}-{sha256(expression.encode()).hexdigest()[:12]}",
                rule_type=rule_type,
                expression=expression,
            )
            for rule_type, expression in requested
        )


ConnectorFactory = Callable[
    [ExternalInstagramConfig, Callable[[Mapping[str, int | str]], None]], SourceConnector
]


def _default_connector(
    config: ExternalInstagramConfig,
    quota_observer: Callable[[Mapping[str, int | str]], None],
) -> SourceConnector:
    return InstagramConnector(
        access_token=config.instagram_access_token,
        config=InstagramConnectorConfig(
            tenant_id=config.tenant_id,
            source_id=config.source_id,
            page_id=config.instagram_page_id,
            lookback_hours=config.lookback_hours,
            max_media_pages_per_rule=config.max_media_pages_per_rule,
            max_requests_per_run=config.max_requests_per_run,
        ),
        quota_observer=quota_observer,
    )


class ExternalInstagramCollector:
    """Land event files before checkpoint commits for at-least-once delivery."""

    def __init__(
        self,
        config: ExternalInstagramConfig,
        files: DatabricksFilesClient,
        *,
        connector_factory: ConnectorFactory = _default_connector,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.config = config
        self.files = files
        self.connector_factory = connector_factory
        self.clock = clock

    def diagnose_connection(self) -> Mapping[str, object]:
        """Run a sanitized Meta Page-link preflight without landing data."""
        connector = self.connector_factory(self.config, lambda _quota: None)
        diagnose = getattr(connector, "diagnose_connection", None)
        if not callable(diagnose):
            raise TypeError("Configured Instagram connector does not support diagnostics")
        result = diagnose()
        if hasattr(result, "to_dict"):
            return result.to_dict()
        if isinstance(result, Mapping):
            return dict(result)
        raise TypeError("Instagram diagnostic returned an unsupported result")

    def run(self) -> Mapping[str, object]:
        started_at = self.clock().astimezone(timezone.utc)
        run_id = f"{started_at:%Y%m%dT%H%M%S}-{uuid4().hex}"
        self._ensure_directories()
        checkpoint = self._load_checkpoint()

        def persist_quota(quota: Mapping[str, int | str]) -> None:
            self._save_checkpoint(
                ConnectorCheckpoint(
                    cursors=checkpoint.cursors,
                    quota=dict(quota),
                    metadata={
                        **dict(checkpoint.metadata),
                        "runtime": "external_files_api",
                        "quota_reserved_by_run_id": run_id,
                    },
                    updated_at=self.clock().astimezone(timezone.utc),
                )
            )

        connector = self.connector_factory(self.config, persist_quota)
        try:
            batch = connector.collect(self.config.collection_rules(), checkpoint)
            event_path = ""
            if batch.events:
                event_path = f"{self.config.volume_root}/events/instagram-{run_id}.json"
                content = "".join(
                    json.dumps(event.to_record(), sort_keys=True) + "\n" for event in batch.events
                ).encode("utf-8")
                self.files.upload(event_path, content)
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
                run_id=run_id,
                started_at=started_at,
                status="SUCCESS",
                statistics=batch.statistics,
                quota=batch.checkpoint.quota,
                event_path=event_path,
            )
            self._save_metric(run_id, metric)
            self._write_status_projection(metric)
            return metric
        except Exception as error:
            metric = self._metric(
                run_id=run_id,
                started_at=started_at,
                status="FAILED",
                error_type=type(error).__name__,
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
            f"{self.config.volume_root}/checkpoints/instagram/{self.config.tenant_id}",
            f"{self.config.volume_root}/operations/instagram/{self.config.tenant_id}/{self.config.source_id}",
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
            (json.dumps(checkpoint.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

    def _save_metric(self, run_id: str, metric: Mapping[str, object]) -> None:
        path = f"{self.config.volume_root}/operations/instagram/{self.config.tenant_id}/{self.config.source_id}/{run_id}.json"
        self.files.upload(path, (json.dumps(metric, sort_keys=True) + "\n").encode("utf-8"))

    def _write_status_projection(self, metric: Mapping[str, object]) -> None:
        if not self.config.status_output_path:
            return
        path = os.path.abspath(self.config.status_output_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as output:
            json.dump(dict(metric), output, sort_keys=True)
            output.write("\n")

    def _metric(
        self,
        *,
        run_id: str,
        started_at: datetime,
        status: str,
        statistics: Mapping[str, int] | None = None,
        quota: Mapping[str, object] | None = None,
        event_path: str = "",
        error_type: str = "",
    ) -> dict[str, object]:
        stats = statistics or {}
        quota_values = quota or {}
        request_limit = _nonnegative_integer(
            quota_values.get("instagram_requests_limit"), self.config.max_requests_per_run
        )
        requests_used = _nonnegative_integer(quota_values.get("instagram_requests_used"), 0)
        return {
            "run_id": run_id,
            "tenant_id": self.config.tenant_id,
            "source_id": self.config.source_id,
            "platform": "instagram",
            "runtime": "github_actions",
            "started_at": started_at.isoformat(),
            "completed_at": self.clock().astimezone(timezone.utc).isoformat(),
            "status": status,
            "active_rules": int(stats.get("active_rules", 0)),
            "posts_discovered": int(stats.get("posts_discovered", 0)),
            "events_emitted": int(stats.get("events_emitted", 0)),
            "requests_used": requests_used,
            "requests_remaining": max(0, request_limit - requests_used),
            "event_path": event_path,
            "error_type": error_type,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect or preflight the Instagram connector")
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="check Page access and Instagram Business linkage without collecting media",
    )
    args = parser.parse_args()
    config = ExternalInstagramConfig.from_environment()
    files = DatabricksFilesClient(host=config.databricks_host, token=config.databricks_token)
    collector = ExternalInstagramCollector(config, files)
    result = collector.diagnose_connection() if args.diagnose else collector.run()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
