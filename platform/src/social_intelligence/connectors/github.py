"""GitHub repository connector for adoption signals on a curated watchlist.

The connector reads public repository metadata and releases through the REST
API and emits the same ``SocialEventEnvelope`` as the social sources. It never
reads contributors, issues, commits, or user profiles. Only repositories the
operator listed as ``community`` rules are fetched; topic search is a later
step and ``keyword`` rules are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from social_intelligence.connectors.base import (
    CollectionRule,
    ConnectorBatch,
    ConnectorCapabilities,
)
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.retry import RetryPolicy
from social_intelligence.contracts import SocialEventEnvelope


GITHUB_API_ROOT = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}")
RELEASE_BODY_LIMIT = 2000

CAPABILITIES = ConnectorCapabilities(
    platform="github",
    supported_rule_types=frozenset({"community"}),
    supports_public_search=False,
    supports_account_collection=False,
    supports_engagement_metrics=True,
)

Transport = Callable[[str], Any]


class GitHubApiError(RuntimeError):
    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(f"GitHub API error {status}: {message}")
        self.status = status

    @property
    def retryable(self) -> bool:
        return self.status is None or self.status >= 500


class RequestBudgetExceeded(RuntimeError):
    """Raised before a request that would exceed the per-run cap."""


@dataclass(frozen=True)
class GitHubConnectorConfig:
    tenant_id: str
    source_id: str
    max_requests_per_run: int = 40
    releases_per_repo: int = 5
    release_lookback_days: int = 30

    def __post_init__(self) -> None:
        if self.max_requests_per_run < 1:
            raise ValueError("max_requests_per_run must be at least 1")
        if not 1 <= self.releases_per_repo <= 30:
            raise ValueError("releases_per_repo must be between 1 and 30")
        if self.release_lookback_days < 1:
            raise ValueError("release_lookback_days must be at least 1")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp is not timezone-aware: {value!r}")
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _integer(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


class GitHubConnector:
    """Collect one daily repo snapshot and any new releases per watchlist repo."""

    def __init__(
        self,
        *,
        config: GitHubConnectorConfig,
        token: str = "",
        transport: Transport | None = None,
        retry_policy: RetryPolicy | None = None,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.config = config
        self._token = token
        self._transport = transport or self._http_transport
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleeper = sleeper
        self._clock = clock
        self._requests = 0

    def collect(
        self,
        rules: Sequence[CollectionRule],
        checkpoint: ConnectorCheckpoint,
    ) -> ConnectorBatch:
        now = self._clock().astimezone(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        active = [rule for rule in rules if rule.enabled]
        for rule in active:
            if rule.rule_type not in CAPABILITIES.supported_rule_types:
                raise ValueError(
                    f"GitHub supports only community rules, got {rule.rule_type}"
                )
            if not REPOSITORY_PATTERN.fullmatch(rule.expression):
                raise ValueError(f"Unsafe GitHub repository: {rule.expression!r}")

        cursors = dict(checkpoint.cursors)
        events: list[SocialEventEnvelope] = []
        stats = {
            "active_rules": len(active),
            "repos_fetched": 0,
            "repos_not_found": 0,
            "snapshots_emitted": 0,
            "releases_emitted": 0,
            "events_emitted": 0,
        }

        for rule in active:
            snapshot_key = f"{rule.rule_id}:snapshot_date"
            release_key = f"{rule.rule_id}:release_published_at"
            try:
                repo = self._get(f"/repos/{rule.expression}")
            except GitHubApiError as error:
                if error.status == 404:
                    stats["repos_not_found"] += 1
                    continue
                raise
            stats["repos_fetched"] += 1

            if cursors.get(snapshot_key) != today:
                events.append(self._snapshot_event(repo, rule, now, today))
                cursors[snapshot_key] = today
                stats["snapshots_emitted"] += 1

            since = _parse_timestamp(
                cursors.get(release_key)
                or _format_timestamp(
                    now - timedelta(days=self.config.release_lookback_days)
                )
            )
            releases = self._get(
                f"/repos/{rule.expression}/releases"
                f"?per_page={self.config.releases_per_repo}"
            )
            newest = since
            for release in releases:
                if release.get("draft") or not release.get("published_at"):
                    continue
                published = _parse_timestamp(str(release["published_at"]))
                if published <= since:
                    continue
                events.append(self._release_event(repo, release, rule, now))
                stats["releases_emitted"] += 1
                newest = max(newest, published)
            cursors[release_key] = _format_timestamp(newest)

        stats["events_emitted"] = len(events)
        committed = ConnectorCheckpoint(
            cursors=cursors,
            quota={"requests_used": self._requests},
            metadata=dict(checkpoint.metadata),
            updated_at=now,
        )
        return ConnectorBatch(
            events=tuple(events),
            checkpoint=committed,
            statistics=stats,
        )

    def _get(self, path: str) -> Any:
        def operation() -> Any:
            if self._requests >= self.config.max_requests_per_run:
                raise RequestBudgetExceeded(
                    f"GitHub request cap of {self.config.max_requests_per_run} reached"
                )
            self._requests += 1
            try:
                return self._transport(path)
            except GitHubApiError:
                raise
            except Exception as error:
                raise GitHubApiError(None, str(error)) from error

        arguments: dict[str, Any] = {}
        if self._sleeper is not None:
            arguments["sleeper"] = self._sleeper
        return self._retry_policy.run(
            operation,
            lambda error: isinstance(error, GitHubApiError) and error.retryable,
            **arguments,
        )

    def _http_transport(self, path: str) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "social-intelligence-collector",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = Request(f"{GITHUB_API_ROOT}{path}", headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            # Rate-limit 403/429 are not retried: fail closed until the next run.
            raise GitHubApiError(error.code, str(error.reason)) from error

    def _snapshot_event(
        self,
        repo: Mapping[str, Any],
        rule: CollectionRule,
        collected_at: datetime,
        today: str,
    ) -> SocialEventEnvelope:
        full_name = str(repo["full_name"])
        owner = repo.get("owner") or {}
        topics = [str(topic) for topic in repo.get("topics") or []]
        description = str(repo.get("description") or "")
        post_id = f"{full_name}@{today}"
        day_start = collected_at.replace(hour=0, minute=0, second=0, microsecond=0)
        # Stars are the closest analogue of a save and forks of a share; open
        # issues are not comments, so the raw counts stay in source_payload.
        payload = self._payload(
            post_id=post_id,
            repo=repo,
            title=full_name,
            text="\n".join(part for part in (full_name, description) if part),
            created_at=day_start,
            collected_at=collected_at,
            hashtags=topics,
            saves=_integer(repo.get("stargazers_count")),
            shares=_integer(repo.get("forks_count")),
            url=str(repo.get("html_url", "")),
            raw={
                "full_name": full_name,
                "stargazers_count": repo.get("stargazers_count"),
                "forks_count": repo.get("forks_count"),
                "open_issues_count": repo.get("open_issues_count"),
                "pushed_at": repo.get("pushed_at"),
                "archived": repo.get("archived"),
                "license": (repo.get("license") or {}).get("spdx_id"),
                "language": repo.get("language"),
            },
        )
        payload["author_id"] = str(owner.get("login", ""))
        # A fixed day-start time keeps the idempotency key stable on a retried run.
        return self._envelope(
            post_id, payload, rule, "repo_snapshot", day_start, collected_at
        )

    def _release_event(
        self,
        repo: Mapping[str, Any],
        release: Mapping[str, Any],
        rule: CollectionRule,
        collected_at: datetime,
    ) -> SocialEventEnvelope:
        full_name = str(repo["full_name"])
        published = _parse_timestamp(str(release["published_at"]))
        title = str(release.get("name") or release.get("tag_name") or "")
        body = str(release.get("body") or "")[:RELEASE_BODY_LIMIT]
        post_id = f"{full_name}#release-{release['id']}"
        payload = self._payload(
            post_id=post_id,
            repo=repo,
            title=f"{full_name} {title}".strip(),
            text="\n".join(part for part in (f"{full_name} {title}".strip(), body) if part),
            created_at=published,
            collected_at=collected_at,
            hashtags=[str(topic) for topic in repo.get("topics") or []],
            saves=0,
            shares=0,
            url=str(release.get("html_url") or repo.get("html_url", "")),
            raw={
                "id": release.get("id"),
                "tag_name": release.get("tag_name"),
                "prerelease": release.get("prerelease"),
                "published_at": release.get("published_at"),
            },
        )
        payload["author_id"] = str((repo.get("owner") or {}).get("login", ""))
        return self._envelope(post_id, payload, rule, "release", published, collected_at)

    @staticmethod
    def _payload(
        *,
        post_id: str,
        repo: Mapping[str, Any],
        title: str,
        text: str,
        created_at: datetime,
        collected_at: datetime,
        hashtags: list[str],
        saves: int,
        shares: int,
        url: str,
        raw: Mapping[str, Any],
    ) -> dict[str, Any]:
        owner = repo.get("owner") or {}
        return {
            "post_id": post_id,
            "platform": "github",
            "source_url": url,
            "source_title": title,
            "source_author": str(owner.get("login", "")),
            "author_id": "",
            "author_followers": 0,
            "content_text": text,
            "hashtags": hashtags,
            "audio_id": None,
            "created_at": _format_timestamp(created_at),
            "collected_at": _format_timestamp(collected_at),
            "views": 0,
            "likes": 0,
            "comments": 0,
            "shares": shares,
            "saves": saves,
            "language": "und",
            "geography": "GLOBAL",
            "brand": None,
            "source_payload": json.dumps(raw, sort_keys=True, default=str),
        }

    def _envelope(
        self,
        post_id: str,
        payload: Mapping[str, Any],
        rule: CollectionRule,
        resource_type: str,
        occurred_at: datetime,
        collected_at: datetime | None = None,
    ) -> SocialEventEnvelope:
        collected = collected_at or occurred_at
        return SocialEventEnvelope.create(
            tenant_id=self.config.tenant_id,
            source_id=self.config.source_id,
            platform="github",
            event_type="social.post.observed",
            source_object_id=post_id,
            occurred_at=occurred_at,
            collected_at=collected,
            correlation_id=str(uuid4()),
            payload=payload,
            attributes={
                "connector_type": "github_rest_api",
                "delivery_mode": "polling",
                "resource_type": resource_type,
                "rule_id": rule.rule_id,
            },
        )
