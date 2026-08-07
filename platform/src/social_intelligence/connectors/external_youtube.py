"""External YouTube collector that lands batches through Databricks Files API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re
from typing import Callable, Mapping
from uuid import uuid4

from social_intelligence.connectors.base import CollectionRule, SourceConnector
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.databricks_files import DatabricksFilesClient
from social_intelligence.connectors.quota import QuotaPolicy
from social_intelligence.connectors.youtube import (
    YouTubeConnector,
    YouTubeConnectorConfig,
)


IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SAFE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


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


def _boolean(environment: Mapping[str, str], name: str, default: bool) -> bool:
    raw = environment.get(name, str(default)).strip().lower()
    if raw not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return raw == "true"


@dataclass(frozen=True)
class ExternalYouTubeConfig:
    """Environment-driven configuration for a stateless external worker."""

    databricks_host: str
    databricks_token: str
    youtube_api_key: str
    catalog: str = "dev"
    schema: str = "social_intelligence_dev"
    tenant_id: str = "demo"
    source_id: str = "youtube-api-v3"
    search_expression: str = ""
    channel_ids: tuple[str, ...] = ()
    region_code: str = "US"
    relevance_language: str = "en"
    lookback_hours: int = 6
    max_search_pages_per_rule: int = 1
    collect_comments: bool = False
    collect_replies: bool = False
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
        if not self.search_expression.strip() and not self.channel_ids:
            raise ValueError(
                "YOUTUBE_SEARCH_EXPRESSION or YOUTUBE_CHANNEL_IDS is required"
            )
        if not re.fullmatch(r"[A-Z]{2}", self.region_code):
            raise ValueError("YOUTUBE_REGION_CODE must be an ISO alpha-2 code")
        if not re.fullmatch(r"[A-Za-z0-9-]{2,16}", self.relevance_language):
            raise ValueError("YOUTUBE_RELEVANCE_LANGUAGE is invalid")
        for channel_id in self.channel_ids:
            if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", channel_id):
                raise ValueError(f"Unsafe YouTube channel ID: {channel_id!r}")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "ExternalYouTubeConfig":
        values = environment or os.environ
        channel_ids = tuple(
            value.strip()
            for value in values.get("YOUTUBE_CHANNEL_IDS", "").split(",")
            if value.strip()
        )
        return cls(
            databricks_host=_required(values, "DATABRICKS_HOST"),
            databricks_token=_required(values, "DATABRICKS_TOKEN"),
            youtube_api_key=_required(values, "YOUTUBE_API_KEY"),
            catalog=values.get("DATABRICKS_CATALOG", "dev").strip(),
            schema=values.get(
                "DATABRICKS_SCHEMA", "social_intelligence_dev"
            ).strip(),
            tenant_id=values.get("SOCIAL_TENANT_ID", "demo").strip(),
            source_id=values.get("YOUTUBE_SOURCE_ID", "youtube-api-v3").strip(),
            search_expression=values.get("YOUTUBE_SEARCH_EXPRESSION", "").strip(),
            channel_ids=channel_ids,
            region_code=values.get("YOUTUBE_REGION_CODE", "US").strip().upper(),
            relevance_language=values.get(
                "YOUTUBE_RELEVANCE_LANGUAGE", "en"
            ).strip(),
            lookback_hours=_integer(values, "YOUTUBE_LOOKBACK_HOURS", 6),
            max_search_pages_per_rule=_integer(
                values, "YOUTUBE_MAX_SEARCH_PAGES_PER_RULE", 1
            ),
            collect_comments=_boolean(values, "YOUTUBE_COLLECT_COMMENTS", False),
            collect_replies=_boolean(values, "YOUTUBE_COLLECT_REPLIES", False),
            status_output_path=values.get("PIPELINE_STATUS_OUTPUT", "").strip(),
        )

    @property
    def volume_root(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema}/raw_social"

    @property
    def checkpoint_path(self) -> str:
        return (
            f"{self.volume_root}/checkpoints/youtube/"
            f"{self.tenant_id}/{self.source_id}.json"
        )

    def collection_rules(self) -> tuple[CollectionRule, ...]:
        requested: list[tuple[str, str]] = []
        if self.search_expression.strip():
            requested.append(("keyword", self.search_expression.strip()))
        requested.extend(("channel", value) for value in self.channel_ids)
        return tuple(
            CollectionRule(
                rule_id=(
                    f"youtube-{rule_type}-"
                    f"{sha256(expression.encode()).hexdigest()[:12]}"
                ),
                rule_type=rule_type,
                expression=expression,
            )
            for rule_type, expression in requested
        )


ConnectorFactory = Callable[
    [ExternalYouTubeConfig, Callable[[Mapping[str, int | str]], None]],
    SourceConnector,
]


def _default_connector(
    config: ExternalYouTubeConfig,
    quota_observer: Callable[[Mapping[str, int | str]], None],
) -> SourceConnector:
    return YouTubeConnector(
        api_key=config.youtube_api_key,
        config=YouTubeConnectorConfig(
            tenant_id=config.tenant_id,
            source_id=config.source_id,
            region_code=config.region_code,
            relevance_language=config.relevance_language,
            lookback_hours=config.lookback_hours,
            max_search_pages_per_rule=config.max_search_pages_per_rule,
            collect_comments=config.collect_comments,
            collect_replies=config.collect_replies,
        ),
        quota_observer=quota_observer,
    )


class ExternalYouTubeCollector:
    """Run one fail-closed batch with durable remote quota and cursor state."""

    def __init__(
        self,
        config: ExternalYouTubeConfig,
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

        def persist_quota(quota: Mapping[str, int | str]) -> None:
            reservation = ConnectorCheckpoint(
                cursors=checkpoint.cursors,
                quota=dict(quota),
                metadata={
                    **dict(checkpoint.metadata),
                    "runtime": "external_files_api",
                    "quota_reserved_by_run_id": run_id,
                },
                updated_at=self.clock().astimezone(timezone.utc),
            )
            self._save_checkpoint(reservation)

        connector = self.connector_factory(self.config, persist_quota)
        try:
            batch = connector.collect(self.config.collection_rules(), checkpoint)
            event_path = ""
            if batch.events:
                event_path = f"{self.config.volume_root}/events/youtube-{run_id}.json"
                payload = "".join(
                    json.dumps(event.to_record(), sort_keys=True) + "\n"
                    for event in batch.events
                ).encode("utf-8")
                self.files.upload(event_path, payload)

            committed = ConnectorCheckpoint(
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
            self._save_checkpoint(committed)
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
            f"{self.config.volume_root}/checkpoints/youtube/"
            f"{self.config.tenant_id}",
            f"{self.config.volume_root}/operations/youtube/"
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
        payload = (
            json.dumps(checkpoint.to_dict(), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        self.files.upload(self.config.checkpoint_path, payload)

    def _save_metric(self, run_id: str, metric: Mapping[str, object]) -> None:
        path = (
            f"{self.config.volume_root}/operations/youtube/"
            f"{self.config.tenant_id}/{self.config.source_id}/{run_id}.json"
        )
        self.files.upload(
            path,
            (json.dumps(metric, sort_keys=True) + "\n").encode("utf-8"),
        )

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
        policy = QuotaPolicy()
        completed_at = self.clock().astimezone(timezone.utc)
        search_calls = int(quota_values.get("search_calls", 0))
        core_units = int(quota_values.get("core_units", 0))
        return {
            "run_id": run_id,
            "tenant_id": self.config.tenant_id,
            "source_id": self.config.source_id,
            "platform": "youtube",
            "runtime": "github_actions",
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "status": status,
            "active_rules": int(stats.get("active_rules", 0)),
            "videos_discovered": int(stats.get("videos_discovered", 0)),
            "events_emitted": int(stats.get("events_emitted", 0)),
            "search_calls_used": search_calls,
            "search_calls_remaining": max(
                0, policy.usable_limit("search") - search_calls
            ),
            "core_units_used": core_units,
            "core_units_remaining": max(
                0, policy.usable_limit("core") - core_units
            ),
            "event_path": event_path,
            "error_type": error_type,
        }


def main() -> int:
    config = ExternalYouTubeConfig.from_environment()
    files = DatabricksFilesClient(
        host=config.databricks_host,
        token=config.databricks_token,
    )
    result = ExternalYouTubeCollector(config, files).run()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
