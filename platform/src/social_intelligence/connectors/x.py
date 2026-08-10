"""Checkpointed X recent-search connector.

The connector deliberately uses the polling Search Posts endpoint rather than
the filtered stream. It is deployable from GitHub Actions, works with a
bounded credential, and preserves a replay overlap for at-least-once landing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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


X_API_ROOT = "https://api.x.com/2"
X_CAPABILITIES = ConnectorCapabilities(
    platform="x",
    supported_rule_types=frozenset({"keyword", "hashtag", "account", "trend"}),
    supports_public_search=True,
    supports_account_collection=True,
    supports_engagement_metrics=True,
)
RETRYABLE_TITLES = frozenset({"over capacity", "internal error"})
HASHTAG_PATTERN = re.compile(r"(?<!\w)#([\w-]+)", re.UNICODE)
ACCOUNT_PATTERN = re.compile(r"@?([A-Za-z0-9_]{1,15})$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"X returned a naive timestamp: {value}")
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("X request timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


class XApiError(RuntimeError):
    """Sanitized X API failure that never includes the bearer token."""

    def __init__(self, status: int | None, title: str, message: str) -> None:
        super().__init__(f"X API error {status or 'network'} ({title}): {message}")
        self.status = status
        self.title = title

    @property
    def retryable(self) -> bool:
        return (
            self.title != "localQuotaGuard"
            and (
                self.status is None
            or self.status == 429
            or (self.status is not None and 500 <= self.status <= 599)
            or self.title.lower() in RETRYABLE_TITLES
            )
        )


class XPaginationLimitReached(RuntimeError):
    """Fail closed instead of advancing a cursor beyond an unpaged result set."""


Transport = Callable[[str, Mapping[str, str]], Mapping[str, Any]]


class XApiClient:
    """Minimal injectable client with bounded retries and request accounting."""

    def __init__(
        self,
        *,
        bearer_token: str,
        retry_policy: RetryPolicy,
        max_requests_per_run: int,
        transport: Transport | None = None,
        sleeper: Callable[[float], None] | None = None,
        on_request: Callable[[int], None] | None = None,
    ) -> None:
        if not bearer_token.strip():
            raise ValueError("X bearer token is required")
        if not 1 <= max_requests_per_run <= 450:
            raise ValueError("max_requests_per_run must be between 1 and 450")
        self._bearer_token = bearer_token
        self._retry_policy = retry_policy
        self._max_requests_per_run = max_requests_per_run
        self._transport = transport or self._http_transport
        self._sleeper = sleeper
        self._on_request = on_request
        self.requests_used = 0

    def recent_search(self, params: Mapping[str, str]) -> Mapping[str, Any]:
        return self._request("tweets/search/recent", params)

    def trends_by_woeid(self, *, woeid: int, max_trends: int) -> Mapping[str, Any]:
        if woeid <= 0:
            raise ValueError("woeid must be positive")
        if not 1 <= max_trends <= 20:
            raise ValueError("max_trends must be between 1 and 20")
        return self._request(
            f"trends/by/woeid/{woeid}",
            {
                "max_trends": str(max_trends),
                "trend.fields": "trend_name,tweet_count",
            },
        )

    def _request(self, path: str, params: Mapping[str, str]) -> Mapping[str, Any]:
        def operation() -> Mapping[str, Any]:
            if self.requests_used >= self._max_requests_per_run:
                raise XApiError(429, "localQuotaGuard", "per-run request budget reached")
            self.requests_used += 1
            if self._on_request is not None:
                self._on_request(self.requests_used)
            try:
                return self._transport(path, params)
            except XApiError:
                raise
            except Exception as error:
                raise XApiError(None, "transportError", str(error)) from error

        arguments: dict[str, Any] = {}
        if self._sleeper is not None:
            arguments["sleeper"] = self._sleeper
        return self._retry_policy.run(
            operation,
            lambda error: isinstance(error, XApiError) and error.retryable,
            **arguments,
        )

    def _http_transport(self, path: str, params: Mapping[str, str]) -> Mapping[str, Any]:
        request = Request(
            f"{X_API_ROOT}/{path}?{urlencode(params)}",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._bearer_token}",
                "User-Agent": "social-intelligence-x-connector/1.0",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            title = "httpError"
            message = str(error.reason or "request failed")
            try:
                body = json.loads(error.read().decode("utf-8"))
                title = str(body.get("title", title))
                message = str(body.get("detail", body.get("message", message)))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            raise XApiError(error.code, title, message) from error
        except URLError as error:
            raise XApiError(None, "transportError", str(error.reason)) from error


@dataclass(frozen=True)
class XConnectorConfig:
    tenant_id: str
    source_id: str
    lookback_hours: int = 6
    overlap_minutes: int = 5
    max_search_pages_per_rule: int = 1
    max_results_per_page: int = 100
    max_requests_per_run: int = 100
    trends_woeid: int | None = None
    trends_location: str = ""
    max_trends_per_run: int = 20

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.source_id.strip():
            raise ValueError("tenant_id and source_id are required")
        if not 1 <= self.lookback_hours <= 168:
            raise ValueError("lookback_hours must be between 1 and 168")
        if not 0 <= self.overlap_minutes <= 60:
            raise ValueError("overlap_minutes must be between 0 and 60")
        if not 1 <= self.max_search_pages_per_rule <= 10:
            raise ValueError("max_search_pages_per_rule must be between 1 and 10")
        if not 10 <= self.max_results_per_page <= 100:
            raise ValueError("max_results_per_page must be between 10 and 100")
        if not 1 <= self.max_requests_per_run <= 450:
            raise ValueError("max_requests_per_run must be between 1 and 450")
        if self.trends_woeid is not None and self.trends_woeid <= 0:
            raise ValueError("trends_woeid must be positive")
        if self.trends_woeid is not None and not self.trends_location.strip():
            raise ValueError("trends_location is required when trends_woeid is configured")
        if len(self.trends_location) > 100 or any(ord(char) < 32 for char in self.trends_location):
            raise ValueError("trends_location must be a printable value no longer than 100 characters")
        if not 1 <= self.max_trends_per_run <= 20:
            raise ValueError("max_trends_per_run must be between 1 and 20")


class XConnector:
    """Map X recent Posts to canonical event envelopes without cursor gaps."""

    capabilities = X_CAPABILITIES

    def __init__(
        self,
        *,
        bearer_token: str,
        config: XConnectorConfig,
        retry_policy: RetryPolicy | None = None,
        transport: Transport | None = None,
        clock: Callable[[], datetime] = _utc_now,
        sleeper: Callable[[float], None] | None = None,
        quota_observer: Callable[[Mapping[str, int | str]], None] | None = None,
    ) -> None:
        self._bearer_token = bearer_token
        self.config = config
        self._retry_policy = retry_policy or RetryPolicy()
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper
        self._quota_observer = quota_observer

    def collect(
        self,
        rules: Sequence[CollectionRule],
        checkpoint: ConnectorCheckpoint,
    ) -> ConnectorBatch:
        started_at = self._clock()
        if started_at.tzinfo is None:
            raise ValueError("Connector clock must return a timezone-aware datetime")
        started_at = started_at.astimezone(timezone.utc)
        quota = dict(checkpoint.quota)

        def persist_request(used: int) -> None:
            quota.update({"x_requests_used": used, "x_requests_limit": self.config.max_requests_per_run})
            if self._quota_observer is not None:
                self._quota_observer(dict(quota))

        client = XApiClient(
            bearer_token=self._bearer_token,
            retry_policy=self._retry_policy,
            max_requests_per_run=self.config.max_requests_per_run,
            transport=self._transport,
            sleeper=self._sleeper,
            on_request=persist_request,
        )
        events: dict[str, SocialEventEnvelope] = {}
        cursors = dict(checkpoint.cursors)
        active_rules = [rule for rule in rules if rule.enabled]
        trend_rules = [rule for rule in active_rules if rule.rule_type == "trend"]
        post_rules = [rule for rule in active_rules if rule.rule_type != "trend"]
        if trend_rules and self.config.trends_woeid is None:
            raise ValueError("X trend rules require trends_woeid connector configuration")
        discovered_ids: set[str] = set()
        trend_events: list[SocialEventEnvelope] = []

        for rule in post_rules:
            posts = self._search_posts(client, rule, checkpoint, started_at)
            for post in posts:
                event = self._post_event(post, rule, started_at)
                discovered_ids.add(event.source_object_id)
                events[event.idempotency_key] = event
            # The timestamp watermark has a deliberate overlap. It only advances
            # after every page was read, while event-file landing remains the
            # responsibility of the external runtime.
            cursors[rule.rule_id] = _format_timestamp(started_at)

        if self.config.trends_woeid is not None:
            trend_events = self._collect_trends(client, started_at)
            if trend_rules:
                cursors[trend_rules[0].rule_id] = _format_timestamp(started_at)

        quota.update(
            {
                "x_requests_used": client.requests_used,
                "x_requests_limit": self.config.max_requests_per_run,
            }
        )
        next_checkpoint = ConnectorCheckpoint(
            cursors=cursors,
            quota=quota,
            metadata={
                **dict(checkpoint.metadata),
                "connector": "x_api_v2",
                "source_id": self.config.source_id,
                "last_batch_event_count": len(events),
                "last_batch_post_count": len(discovered_ids),
                "last_batch_trend_count": len(trend_events),
                "trends_woeid": self.config.trends_woeid or "",
                "trends_location": self.config.trends_location,
            },
            updated_at=started_at,
        )
        return ConnectorBatch(
            events=tuple(events.values()) + tuple(trend_events),
            checkpoint=next_checkpoint,
            statistics={
                "active_rules": len(active_rules),
                "posts_discovered": len(discovered_ids),
                "trends_discovered": len(trend_events),
                "events_emitted": len(events) + len(trend_events),
                "requests_used": client.requests_used,
                "requests_remaining": self.config.max_requests_per_run - client.requests_used,
            },
        )

    def _search_posts(
        self,
        client: XApiClient,
        rule: CollectionRule,
        checkpoint: ConnectorCheckpoint,
        started_at: datetime,
    ) -> list[Mapping[str, Any]]:
        if rule.rule_type not in self.capabilities.supported_rule_types:
            raise ValueError(f"Unsupported X rule type: {rule.rule_type}")
        watermark = self._watermark(rule, checkpoint, started_at)
        params = {
            "query": self._query(rule),
            "start_time": _format_timestamp(watermark),
            "max_results": str(self.config.max_results_per_page),
            "sort_order": "recency",
            "tweet.fields": "id,text,author_id,created_at,lang,public_metrics,entities,conversation_id,referenced_tweets,geo",
        }
        posts: dict[str, Mapping[str, Any]] = {}
        page_token: str | None = None
        for page in range(self.config.max_search_pages_per_rule):
            request_params = dict(params)
            if page_token:
                request_params["next_token"] = page_token
            response = client.recent_search(request_params)
            for item in response.get("data", []):
                post_id = str(item.get("id", "")).strip()
                if post_id:
                    posts.setdefault(post_id, item)
            metadata = response.get("meta", {})
            page_token = str(metadata.get("next_token", "")).strip() or None
            if not page_token:
                break
            if page + 1 == self.config.max_search_pages_per_rule:
                raise XPaginationLimitReached(
                    f"X search for {rule.rule_id} exceeded max_search_pages_per_rule"
                )
        return list(posts.values())

    def _collect_trends(
        self,
        client: XApiClient,
        collected_at: datetime,
    ) -> list[SocialEventEnvelope]:
        if self.config.trends_woeid is None:
            return []
        response = client.trends_by_woeid(
            woeid=self.config.trends_woeid,
            max_trends=self.config.max_trends_per_run,
        )
        trends = [
            item
            for item in response.get("data", [])
            if str(item.get("trend_name", "")).strip()
        ]
        trends.sort(
            key=lambda item: (
                -_integer(item.get("tweet_count")),
                str(item.get("trend_name", "")).casefold(),
            )
        )
        events: list[SocialEventEnvelope] = []
        for rank, item in enumerate(trends[: self.config.max_trends_per_run], start=1):
            trend_name = str(item["trend_name"]).strip()
            source_object_id = (
                f"trend:{self.config.trends_woeid}:"
                f"{sha256(trend_name.casefold().encode()).hexdigest()[:20]}"
            )
            payload = {
                "platform": "x",
                "trend_name": trend_name,
                "tweet_count": _integer(item.get("tweet_count")),
                "woeid": self.config.trends_woeid,
                "location": self.config.trends_location,
                "observed_at": _format_timestamp(collected_at),
                "source_payload": json.dumps(item, sort_keys=True, default=str),
            }
            events.append(
                SocialEventEnvelope.create(
                    tenant_id=self.config.tenant_id,
                    source_id=self.config.source_id,
                    platform="x",
                    event_type="social.trend.observed",
                    source_object_id=source_object_id,
                    occurred_at=collected_at,
                    collected_at=collected_at,
                    correlation_id=str(uuid4()),
                    payload=payload,
                    attributes={
                        "connector_type": "x_api_v2_trends_by_woeid",
                        "delivery_mode": "polling",
                        "resource_type": "trend",
                        "trend_woeid": str(self.config.trends_woeid),
                        "trend_location": self.config.trends_location,
                        "trend_rank": str(rank),
                    },
                )
            )
        return events

    def _watermark(
        self,
        rule: CollectionRule,
        checkpoint: ConnectorCheckpoint,
        started_at: datetime,
    ) -> datetime:
        cursor = checkpoint.cursors.get(rule.rule_id)
        if cursor:
            watermark = _parse_timestamp(cursor)
        else:
            watermark = started_at - timedelta(hours=self.config.lookback_hours)
        return watermark - timedelta(minutes=self.config.overlap_minutes)

    def _query(self, rule: CollectionRule) -> str:
        expression = rule.expression.strip()
        if rule.rule_type == "keyword":
            return expression
        if rule.rule_type == "hashtag":
            hashtag = expression[1:] if expression.startswith("#") else expression
            if not re.fullmatch(r"[\w-]{1,100}", hashtag, re.UNICODE):
                raise ValueError(f"Invalid X hashtag rule: {expression!r}")
            return f"#{hashtag}"
        match = ACCOUNT_PATTERN.fullmatch(expression)
        if match is None:
            raise ValueError(f"Invalid X account rule: {expression!r}")
        return f"from:{match.group(1)}"

    def _post_event(
        self,
        item: Mapping[str, Any],
        rule: CollectionRule,
        collected_at: datetime,
    ) -> SocialEventEnvelope:
        post_id = str(item.get("id", "")).strip()
        if not post_id:
            raise ValueError("X post is missing id")
        created_at = _parse_timestamp(str(item["created_at"]))
        metrics = item.get("public_metrics", {})
        entities = item.get("entities", {})
        hashtags = [
            str(tag.get("tag", ""))
            for tag in entities.get("hashtags", [])
            if str(tag.get("tag", "")).strip()
        ]
        if not hashtags:
            hashtags = HASHTAG_PATTERN.findall(str(item.get("text", "")))
        payload = {
            "post_id": post_id,
            "platform": "x",
            "author_id": str(item.get("author_id", "unknown")) or "unknown",
            "author_followers": 0,
            "content_text": str(item.get("text", "")),
            "hashtags": hashtags,
            "audio_id": None,
            "created_at": _format_timestamp(created_at),
            "collected_at": _format_timestamp(collected_at),
            "views": _integer(metrics.get("impression_count")),
            "likes": _integer(metrics.get("like_count")),
            "comments": _integer(metrics.get("reply_count")),
            "shares": _integer(metrics.get("retweet_count")) + _integer(metrics.get("quote_count")),
            "saves": _integer(metrics.get("bookmark_count")),
            "language": str(item.get("lang", "und")),
            "geography": None,
            "brand": None,
            "source_payload": json.dumps(item, sort_keys=True, default=str),
        }
        return SocialEventEnvelope.create(
            tenant_id=self.config.tenant_id,
            source_id=self.config.source_id,
            platform="x",
            event_type="social.post.observed",
            source_object_id=post_id,
            occurred_at=created_at,
            collected_at=collected_at,
            correlation_id=str(uuid4()),
            payload=payload,
            attributes={
                "connector_type": "x_api_v2_recent_search",
                "delivery_mode": "polling",
                "resource_type": "post",
                "rule_id": rule.rule_id,
            },
        )
