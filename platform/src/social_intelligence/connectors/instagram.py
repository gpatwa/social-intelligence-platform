"""Checkpointed Instagram Graph API connector for a Page-linked Business account.

The connector intentionally collects only media available through the account
that is linked to the configured Facebook Page.  It does not scrape public
profiles, and hashtag discovery uses the documented Graph API search flow.
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


INSTAGRAM_GRAPH_API_ROOT = "https://graph.facebook.com/v26.0"
INSTAGRAM_CAPABILITIES = ConnectorCapabilities(
    platform="instagram",
    supported_rule_types=frozenset({"account", "hashtag"}),
    supports_public_search=True,
    supports_account_collection=True,
    supports_engagement_metrics=True,
)
HASHTAG_PATTERN = re.compile(r"#?([\w-]{1,100})", re.UNICODE)
CAPTION_HASHTAG_PATTERN = re.compile(r"(?<!\w)#([\w-]+)", re.UNICODE)
RETRYABLE_GRAPH_CODES = frozenset({1, 2, 4, 17, 32, 613})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Instagram returned a naive timestamp: {value}")
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Instagram timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


class InstagramApiError(RuntimeError):
    """Sanitized Graph API failure that never includes an access token."""

    def __init__(
        self,
        status: int | None,
        code: int | None,
        message: str,
    ) -> None:
        super().__init__(f"Instagram Graph API error {status or 'network'}: {message}")
        self.status = status
        self.code = code

    @property
    def retryable(self) -> bool:
        return (
            self.code != -1
            and (
                self.status is None
                or self.status == 429
                or (self.status is not None and 500 <= self.status <= 599)
                or self.code in RETRYABLE_GRAPH_CODES
            )
        )


class InstagramPaginationLimitReached(RuntimeError):
    """Raised before a watermark advances past an unread Graph API page."""


Transport = Callable[[str, Mapping[str, str]], Mapping[str, Any]]


class InstagramGraphApiClient:
    """Injectable Graph API client with bounded retries and request accounting."""

    def __init__(
        self,
        *,
        access_token: str,
        retry_policy: RetryPolicy,
        max_requests_per_run: int,
        transport: Transport | None = None,
        sleeper: Callable[[float], None] | None = None,
        on_request: Callable[[int], None] | None = None,
    ) -> None:
        if not access_token.strip():
            raise ValueError("Instagram access token is required")
        if not 1 <= max_requests_per_run <= 450:
            raise ValueError("max_requests_per_run must be between 1 and 450")
        self._access_token = access_token
        self._retry_policy = retry_policy
        self._max_requests_per_run = max_requests_per_run
        self._transport = transport or self._http_transport
        self._sleeper = sleeper
        self._on_request = on_request
        self.requests_used = 0

    def get(self, path: str, params: Mapping[str, str]) -> Mapping[str, Any]:
        def operation() -> Mapping[str, Any]:
            if self.requests_used >= self._max_requests_per_run:
                raise InstagramApiError(429, -1, "per-run request budget reached")
            self.requests_used += 1
            if self._on_request is not None:
                self._on_request(self.requests_used)
            try:
                return self._transport(path, params)
            except InstagramApiError:
                raise
            except Exception as error:
                raise InstagramApiError(None, None, str(error)) from error

        arguments: dict[str, Any] = {}
        if self._sleeper is not None:
            arguments["sleeper"] = self._sleeper
        return self._retry_policy.run(
            operation,
            lambda error: isinstance(error, InstagramApiError) and error.retryable,
            **arguments,
        )

    def _http_transport(self, path: str, params: Mapping[str, str]) -> Mapping[str, Any]:
        query = {**params, "access_token": self._access_token}
        request = Request(
            f"{INSTAGRAM_GRAPH_API_ROOT}/{path.lstrip('/')}?{urlencode(query)}",
            headers={
                "Accept": "application/json",
                "User-Agent": "social-intelligence-instagram-connector/1.0",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            code: int | None = None
            message = str(error.reason or "request failed")
            try:
                body = json.loads(error.read().decode("utf-8"))
                api_error = body.get("error", {})
                code = int(api_error["code"]) if "code" in api_error else None
                message = str(api_error.get("message", message))
            except (TypeError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
                pass
            raise InstagramApiError(error.code, code, message) from error
        except URLError as error:
            raise InstagramApiError(None, None, str(error.reason)) from error


@dataclass(frozen=True)
class InstagramConnectorConfig:
    tenant_id: str
    source_id: str
    page_id: str
    lookback_hours: int = 24
    overlap_minutes: int = 10
    max_media_pages_per_rule: int = 1
    max_results_per_page: int = 100
    max_requests_per_run: int = 100

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.source_id.strip():
            raise ValueError("tenant_id and source_id are required")
        if not re.fullmatch(r"[0-9]{5,32}", self.page_id):
            raise ValueError("page_id must be a numeric Facebook Page ID")
        if not 1 <= self.lookback_hours <= 168:
            raise ValueError("lookback_hours must be between 1 and 168")
        if not 0 <= self.overlap_minutes <= 60:
            raise ValueError("overlap_minutes must be between 0 and 60")
        if not 1 <= self.max_media_pages_per_rule <= 10:
            raise ValueError("max_media_pages_per_rule must be between 1 and 10")
        if not 1 <= self.max_results_per_page <= 100:
            raise ValueError("max_results_per_page must be between 1 and 100")
        if not 1 <= self.max_requests_per_run <= 450:
            raise ValueError("max_requests_per_run must be between 1 and 450")


class InstagramConnector:
    """Collect owned media and permitted hashtag discovery through Graph API."""

    capabilities = INSTAGRAM_CAPABILITIES

    def __init__(
        self,
        *,
        access_token: str,
        config: InstagramConnectorConfig,
        retry_policy: RetryPolicy | None = None,
        transport: Transport | None = None,
        clock: Callable[[], datetime] = _utc_now,
        sleeper: Callable[[float], None] | None = None,
        quota_observer: Callable[[Mapping[str, int | str]], None] | None = None,
    ) -> None:
        self._access_token = access_token
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
            quota.update(
                {
                    "instagram_requests_used": used,
                    "instagram_requests_limit": self.config.max_requests_per_run,
                }
            )
            if self._quota_observer is not None:
                self._quota_observer(dict(quota))

        client = InstagramGraphApiClient(
            access_token=self._access_token,
            retry_policy=self._retry_policy,
            max_requests_per_run=self.config.max_requests_per_run,
            transport=self._transport,
            sleeper=self._sleeper,
            on_request=persist_request,
        )
        active_rules = [rule for rule in rules if rule.enabled]
        unsupported = [rule.rule_type for rule in active_rules if rule.rule_type not in self.capabilities.supported_rule_types]
        if unsupported:
            raise ValueError(f"Unsupported Instagram rule type: {unsupported[0]}")

        account = self._linked_account(client)
        account_id = str(account["id"])
        events: dict[str, SocialEventEnvelope] = {}
        cursors = dict(checkpoint.cursors)
        discovered_ids: set[str] = set()

        for rule in active_rules:
            media = self._media_for_rule(client, account_id, rule, checkpoint, started_at)
            for item in media:
                event = self._media_event(item, rule, account, started_at)
                discovered_ids.add(event.source_object_id)
                events[event.idempotency_key] = event
            cursors[rule.rule_id] = _format_timestamp(started_at)

        quota.update(
            {
                "instagram_requests_used": client.requests_used,
                "instagram_requests_limit": self.config.max_requests_per_run,
            }
        )
        next_checkpoint = ConnectorCheckpoint(
            cursors=cursors,
            quota=quota,
            metadata={
                **dict(checkpoint.metadata),
                "connector": "instagram_graph_api",
                "source_id": self.config.source_id,
                "page_id": self.config.page_id,
                "instagram_account_id": account_id,
                "instagram_username": str(account.get("username", "")),
                "last_batch_event_count": len(events),
                "last_batch_media_count": len(discovered_ids),
            },
            updated_at=started_at,
        )
        return ConnectorBatch(
            events=tuple(events.values()),
            checkpoint=next_checkpoint,
            statistics={
                "active_rules": len(active_rules),
                "posts_discovered": len(discovered_ids),
                "events_emitted": len(events),
                "requests_used": client.requests_used,
                "requests_remaining": self.config.max_requests_per_run - client.requests_used,
            },
        )

    def _linked_account(self, client: InstagramGraphApiClient) -> Mapping[str, Any]:
        response = client.get(
            self.config.page_id,
            {"fields": "instagram_business_account{id,username}"},
        )
        account = response.get("instagram_business_account")
        if not isinstance(account, Mapping) or not str(account.get("id", "")).strip():
            raise ValueError(
                "Configured Facebook Page has no linked Instagram Business account"
            )
        return account

    def _media_for_rule(
        self,
        client: InstagramGraphApiClient,
        account_id: str,
        rule: CollectionRule,
        checkpoint: ConnectorCheckpoint,
        started_at: datetime,
    ) -> list[Mapping[str, Any]]:
        if rule.rule_type == "account":
            return self._paged_media(
                client,
                f"{account_id}/media",
                self._media_params(),
                rule,
                checkpoint,
                started_at,
            )
        match = HASHTAG_PATTERN.fullmatch(rule.expression.strip())
        if match is None:
            raise ValueError(f"Invalid Instagram hashtag rule: {rule.expression!r}")
        hashtag = match.group(1)
        search = client.get(
            "ig_hashtag_search",
            {"user_id": account_id, "q": hashtag},
        )
        matches = search.get("data", [])
        if not matches:
            return []
        hashtag_id = str(matches[0].get("id", "")).strip()
        if not hashtag_id:
            return []
        return self._paged_media(
            client,
            f"{hashtag_id}/recent_media",
            {**self._media_params(), "user_id": account_id},
            rule,
            checkpoint,
            started_at,
        )

    def _paged_media(
        self,
        client: InstagramGraphApiClient,
        path: str,
        params: Mapping[str, str],
        rule: CollectionRule,
        checkpoint: ConnectorCheckpoint,
        started_at: datetime,
    ) -> list[Mapping[str, Any]]:
        watermark = self._watermark(rule, checkpoint, started_at)
        media: dict[str, Mapping[str, Any]] = {}
        after: str | None = None
        for page in range(self.config.max_media_pages_per_rule):
            request_params = dict(params)
            if after:
                request_params["after"] = after
            response = client.get(path, request_params)
            for item in response.get("data", []):
                media_id = str(item.get("id", "")).strip()
                timestamp = str(item.get("timestamp", "")).strip()
                if not media_id or not timestamp:
                    continue
                if _parse_timestamp(timestamp) >= watermark:
                    media.setdefault(media_id, item)
            cursor = response.get("paging", {}).get("cursors", {}).get("after")
            after = str(cursor).strip() if cursor else None
            if not after:
                break
            if page + 1 == self.config.max_media_pages_per_rule:
                raise InstagramPaginationLimitReached(
                    f"Instagram media for {rule.rule_id} exceeded max_media_pages_per_rule"
                )
        return list(media.values())

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

    def _media_params(self) -> dict[str, str]:
        return {
            "fields": (
                "id,caption,media_type,media_product_type,timestamp,"
                "like_count,comments_count,permalink,shortcode,video_views"
            ),
            "limit": str(self.config.max_results_per_page),
        }

    def _media_event(
        self,
        item: Mapping[str, Any],
        rule: CollectionRule,
        account: Mapping[str, Any],
        collected_at: datetime,
    ) -> SocialEventEnvelope:
        media_id = str(item.get("id", "")).strip()
        if not media_id:
            raise ValueError("Instagram media is missing id")
        created_at = _parse_timestamp(str(item["timestamp"]))
        caption = str(item.get("caption", ""))
        payload = {
            "post_id": media_id,
            "platform": "instagram",
            "author_id": str(account["id"]),
            "author_username": str(account.get("username", "")),
            "author_followers": 0,
            "content_text": caption,
            "hashtags": CAPTION_HASHTAG_PATTERN.findall(caption),
            "audio_id": None,
            "created_at": _format_timestamp(created_at),
            "collected_at": _format_timestamp(collected_at),
            "views": _integer(item.get("video_views")),
            "likes": _integer(item.get("like_count")),
            "comments": _integer(item.get("comments_count")),
            "shares": 0,
            "saves": 0,
            "language": "und",
            "geography": None,
            "brand": None,
            "permalink": str(item.get("permalink", "")),
            "media_type": str(item.get("media_type", "")),
            "media_product_type": str(item.get("media_product_type", "")),
            "source_payload": json.dumps(item, sort_keys=True, default=str),
        }
        return SocialEventEnvelope.create(
            tenant_id=self.config.tenant_id,
            source_id=self.config.source_id,
            platform="instagram",
            event_type="social.post.observed",
            source_object_id=media_id,
            occurred_at=created_at,
            collected_at=collected_at,
            correlation_id=str(uuid4()),
            payload=payload,
            attributes={
                "connector_type": "instagram_graph_api",
                "delivery_mode": "polling",
                "resource_type": "media",
                "rule_id": rule.rule_id,
            },
        )
