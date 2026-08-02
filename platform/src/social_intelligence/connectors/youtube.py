"""Quota-aware YouTube Data API v3 polling connector."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
)
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint
from social_intelligence.connectors.quota import (
    QuotaController,
    QuotaLedger,
    QuotaPolicy,
)
from social_intelligence.connectors.retry import RetryPolicy
from social_intelligence.contracts import SocialEventEnvelope


YOUTUBE_API_ROOT = "https://www.googleapis.com/youtube/v3"
HASHTAG_PATTERN = re.compile(r"(?<!\w)#([\w-]+)", re.UNICODE)
RETRYABLE_REASONS = frozenset(
    {"backendError", "internalError", "rateLimitExceeded", "userRateLimitExceeded"}
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"YouTube returned a naive timestamp: {value}")
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("YouTube request timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _hashtags(*values: str) -> list[str]:
    ordered: dict[str, None] = {}
    for value in values:
        for match in HASHTAG_PATTERN.findall(value or ""):
            ordered.setdefault(match, None)
    return list(ordered)


class YouTubeApiError(RuntimeError):
    """Sanitized API failure that never includes the request API key."""

    def __init__(self, status: int | None, reason: str, message: str) -> None:
        super().__init__(f"YouTube API error {status or 'network'} ({reason}): {message}")
        self.status = status
        self.reason = reason

    @property
    def retryable(self) -> bool:
        return (
            self.status is None
            or self.status == 429
            or (self.status is not None and 500 <= self.status <= 599)
            or self.reason in RETRYABLE_REASONS
        )


Transport = Callable[[str, Mapping[str, str]], Mapping[str, Any]]


class YouTubeApiClient:
    """Small injectable client that accounts for quota on every HTTP attempt."""

    def __init__(
        self,
        *,
        api_key: str,
        quota: QuotaController,
        retry_policy: RetryPolicy,
        transport: Transport | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("YouTube API key is required")
        self._api_key = api_key
        self._quota = quota
        self._retry_policy = retry_policy
        self._transport = transport or self._http_transport
        self._sleeper = sleeper

    def list(
        self,
        resource: str,
        params: Mapping[str, str],
        *,
        bucket: str,
        units: int = 1,
    ) -> Mapping[str, Any]:
        endpoint = f"{resource}.list"

        def operation() -> Mapping[str, Any]:
            self._quota.consume(bucket, units, endpoint)
            try:
                return self._transport(resource, params)
            except YouTubeApiError:
                raise
            except Exception as error:
                raise YouTubeApiError(None, "transportError", str(error)) from error

        arguments: dict[str, Any] = {}
        if self._sleeper is not None:
            arguments["sleeper"] = self._sleeper
        return self._retry_policy.run(
            operation,
            lambda error: isinstance(error, YouTubeApiError) and error.retryable,
            **arguments,
        )

    def _http_transport(
        self,
        resource: str,
        params: Mapping[str, str],
    ) -> Mapping[str, Any]:
        query = urlencode({**params, "key": self._api_key})
        request = Request(
            f"{YOUTUBE_API_ROOT}/{resource}?{query}",
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            reason = "httpError"
            message = error.reason or "request failed"
            try:
                body = json.loads(error.read().decode("utf-8"))
                details = body.get("error", {}).get("errors", [])
                if details:
                    reason = str(details[0].get("reason", reason))
                message = str(body.get("error", {}).get("message", message))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            raise YouTubeApiError(error.code, reason, message) from error
        except URLError as error:
            raise YouTubeApiError(None, "transportError", str(error.reason)) from error


@dataclass(frozen=True)
class YouTubeConnectorConfig:
    tenant_id: str
    source_id: str
    region_code: str = "US"
    relevance_language: str = "en"
    safe_search: str = "moderate"
    lookback_hours: int = 6
    overlap_minutes: int = 5
    max_search_pages_per_rule: int = 1
    max_results_per_page: int = 50
    collect_comments: bool = False
    collect_replies: bool = False
    max_comment_pages_per_video: int = 1
    max_reply_pages_per_thread: int = 1

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.source_id.strip():
            raise ValueError("tenant_id and source_id are required")
        if not re.fullmatch(r"[A-Z]{2}", self.region_code):
            raise ValueError("region_code must be an ISO 3166-1 alpha-2 code")
        if not 1 <= self.lookback_hours <= 168:
            raise ValueError("lookback_hours must be between 1 and 168")
        if not 0 <= self.overlap_minutes <= 60:
            raise ValueError("overlap_minutes must be between 0 and 60")
        if not 1 <= self.max_search_pages_per_rule <= 10:
            raise ValueError("max_search_pages_per_rule must be between 1 and 10")
        if not 1 <= self.max_results_per_page <= 50:
            raise ValueError("max_results_per_page must be between 1 and 50")
        if not 0 <= self.max_comment_pages_per_video <= 10:
            raise ValueError("max_comment_pages_per_video must be between 0 and 10")
        if not 0 <= self.max_reply_pages_per_thread <= 10:
            raise ValueError("max_reply_pages_per_thread must be between 0 and 10")


class YouTubeConnector:
    """Collect public YouTube videos and optional comments into event envelopes."""

    def __init__(
        self,
        *,
        api_key: str,
        config: YouTubeConnectorConfig,
        quota_policy: QuotaPolicy | None = None,
        retry_policy: RetryPolicy | None = None,
        transport: Transport | None = None,
        clock: Callable[[], datetime] = _utc_now,
        sleeper: Callable[[float], None] | None = None,
        quota_observer: Callable[[Mapping[str, int | str]], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self.config = config
        self._quota_policy = quota_policy or QuotaPolicy()
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
        ledger = QuotaLedger.from_mapping(
            checkpoint.quota,
            started_at,
            self._quota_policy.reset_timezone,
        )
        quota = QuotaController(
            self._quota_policy,
            ledger,
            (
                lambda current: self._quota_observer(current.to_mapping())
                if self._quota_observer is not None
                else None
            ),
        )
        client = YouTubeApiClient(
            api_key=self._api_key,
            quota=quota,
            retry_policy=self._retry_policy,
            transport=self._transport,
            sleeper=self._sleeper,
        )

        events: dict[str, SocialEventEnvelope] = {}
        cursors = dict(checkpoint.cursors)
        searched_video_ids: set[str] = set()
        active_rules = [rule for rule in rules if rule.enabled]

        for rule in active_rules:
            published_after = self._published_after(rule, checkpoint, started_at)
            rule_videos = self._search_videos(
                client,
                rule,
                published_after,
            )
            rule_video_ids = [
                str(item.get("id", {}).get("videoId", "")).strip()
                for item in rule_videos
            ]
            searched_video_ids.update(rule_video_ids)
            for item in self._video_details(client, rule_videos):
                event = self._video_event(item, rule, started_at)
                events[event.idempotency_key] = event

                if self.config.collect_comments:
                    for comment in self._comment_events(
                        client,
                        str(item.get("id", "")),
                        rule,
                        started_at,
                    ):
                        events[comment.idempotency_key] = comment

            cursors[rule.rule_id] = _format_timestamp(started_at)

        next_checkpoint = ConnectorCheckpoint(
            cursors=cursors,
            quota=ledger.to_mapping(),
            metadata={
                **dict(checkpoint.metadata),
                "connector": "youtube_data_api_v3",
                "source_id": self.config.source_id,
                "last_batch_event_count": len(events),
                "last_batch_video_count": len(searched_video_ids),
            },
            updated_at=started_at,
        )
        return ConnectorBatch(
            events=tuple(events.values()),
            checkpoint=next_checkpoint,
            statistics={
                "active_rules": len(active_rules),
                "videos_discovered": len(searched_video_ids),
                "events_emitted": len(events),
                "search_calls": ledger.search_calls,
                "core_units": ledger.core_units,
            },
        )

    def _published_after(
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

    def _search_videos(
        self,
        client: YouTubeApiClient,
        rule: CollectionRule,
        published_after: datetime,
    ) -> list[Mapping[str, Any]]:
        params = {
            "part": "snippet",
            "type": "video",
            "order": "date",
            "maxResults": str(self.config.max_results_per_page),
            "publishedAfter": _format_timestamp(published_after),
            "regionCode": self.config.region_code,
            "relevanceLanguage": self.config.relevance_language,
            "safeSearch": self.config.safe_search,
            "fields": (
                "nextPageToken,items(id/videoId,snippet(channelId,channelTitle,"
                "title,description,publishedAt))"
            ),
        }
        if rule.rule_type == "keyword":
            params["q"] = rule.expression
        elif rule.rule_type == "channel":
            params["channelId"] = rule.expression
        else:
            raise ValueError(f"Unsupported YouTube rule type: {rule.rule_type}")

        videos: dict[str, Mapping[str, Any]] = {}
        page_token: str | None = None
        for _ in range(self.config.max_search_pages_per_rule):
            request_params = dict(params)
            if page_token:
                request_params["pageToken"] = page_token
            response = client.list("search", request_params, bucket="search")
            for item in response.get("items", []):
                video_id = str(item.get("id", {}).get("videoId", "")).strip()
                if video_id:
                    videos.setdefault(video_id, item)
            page_token = str(response.get("nextPageToken", "")).strip() or None
            if not page_token:
                break
        return list(videos.values())

    def _video_details(
        self,
        client: YouTubeApiClient,
        search_items: Sequence[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        search_by_id = {
            str(item.get("id", {}).get("videoId", "")).strip(): item
            for item in search_items
            if str(item.get("id", {}).get("videoId", "")).strip()
        }
        video_ids = list(search_by_id)
        results: list[Mapping[str, Any]] = []
        for start in range(0, len(video_ids), 50):
            chunk = video_ids[start : start + 50]
            if not chunk:
                continue
            response = client.list(
                "videos",
                {
                    "part": "statistics",
                    "id": ",".join(chunk),
                    "fields": "items(id,statistics)",
                },
                bucket="core",
            )
            stats_by_id = {
                str(item.get("id", "")).strip(): item.get("statistics", {})
                for item in response.get("items", [])
            }
            for video_id in chunk:
                search_item = search_by_id[video_id]
                results.append(
                    {
                        "id": video_id,
                        "snippet": search_item.get("snippet", {}),
                        "statistics": stats_by_id.get(video_id, {}),
                    }
                )
        return results

    def _comment_events(
        self,
        client: YouTubeApiClient,
        video_id: str,
        rule: CollectionRule,
        collected_at: datetime,
    ) -> list[SocialEventEnvelope]:
        if not video_id or self.config.max_comment_pages_per_video == 0:
            return []
        output: list[SocialEventEnvelope] = []
        page_token: str | None = None
        try:
            for _ in range(self.config.max_comment_pages_per_video):
                params = {
                    "part": "snippet,replies",
                    "videoId": video_id,
                    "order": "time",
                    "maxResults": "100",
                    "textFormat": "plainText",
                }
                if page_token:
                    params["pageToken"] = page_token
                response = client.list("commentThreads", params, bucket="core")
                for thread in response.get("items", []):
                    top_level = (
                        thread.get("snippet", {})
                        .get("topLevelComment", {})
                    )
                    if top_level:
                        output.append(
                            self._comment_event(
                                top_level,
                                thread,
                                rule,
                                collected_at,
                                video_id,
                                "top_level",
                            )
                        )
                    if self.config.collect_replies and top_level:
                        output.extend(
                            self._reply_events(
                                client,
                                str(top_level.get("id", "")),
                                rule,
                                collected_at,
                                video_id,
                            )
                        )
                page_token = str(response.get("nextPageToken", "")).strip() or None
                if not page_token:
                    break
        except YouTubeApiError as error:
            if error.reason == "commentsDisabled":
                return []
            raise
        return output

    def _reply_events(
        self,
        client: YouTubeApiClient,
        parent_id: str,
        rule: CollectionRule,
        collected_at: datetime,
        video_id: str,
    ) -> list[SocialEventEnvelope]:
        if not parent_id or self.config.max_reply_pages_per_thread == 0:
            return []
        output: list[SocialEventEnvelope] = []
        page_token: str | None = None
        for _ in range(self.config.max_reply_pages_per_thread):
            params = {
                "part": "snippet",
                "parentId": parent_id,
                "maxResults": "100",
                "textFormat": "plainText",
            }
            if page_token:
                params["pageToken"] = page_token
            response = client.list("comments", params, bucket="core")
            for reply in response.get("items", []):
                output.append(
                    self._comment_event(
                        reply,
                        reply,
                        rule,
                        collected_at,
                        video_id,
                        "reply",
                    )
                )
            page_token = str(response.get("nextPageToken", "")).strip() or None
            if not page_token:
                break
        return output

    def _video_event(
        self,
        item: Mapping[str, Any],
        rule: CollectionRule,
        collected_at: datetime,
    ) -> SocialEventEnvelope:
        video_id = str(item.get("id", "")).strip()
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        published_at = _parse_timestamp(str(snippet["publishedAt"]))
        title = str(snippet.get("title", ""))
        description = str(snippet.get("description", ""))
        text = "\n".join(part for part in (title, description) if part).strip()
        payload = {
            "post_id": video_id,
            "platform": "youtube",
            "author_id": str(snippet.get("channelId", "")),
            "author_followers": 0,
            "content_text": text,
            "hashtags": _hashtags(title, description),
            "audio_id": None,
            "created_at": _format_timestamp(published_at),
            "collected_at": _format_timestamp(collected_at),
            "views": _integer(statistics.get("viewCount")),
            "likes": _integer(statistics.get("likeCount")),
            "comments": _integer(statistics.get("commentCount")),
            "shares": 0,
            "saves": 0,
            "language": str(
                snippet.get("defaultLanguage")
                or snippet.get("defaultAudioLanguage")
                or self.config.relevance_language
            ),
            "geography": self.config.region_code,
            "brand": None,
            "source_payload": json.dumps(item, sort_keys=True, default=str),
        }
        return SocialEventEnvelope.create(
            tenant_id=self.config.tenant_id,
            source_id=self.config.source_id,
            platform="youtube",
            event_type="social.post.observed",
            source_object_id=video_id,
            occurred_at=published_at,
            collected_at=collected_at,
            correlation_id=str(uuid4()),
            payload=payload,
            attributes={
                "connector_type": "youtube_data_api_v3",
                "delivery_mode": "polling",
                "resource_type": "video",
                "rule_id": rule.rule_id,
            },
        )

    def _comment_event(
        self,
        comment: Mapping[str, Any],
        raw_payload: Mapping[str, Any],
        rule: CollectionRule,
        collected_at: datetime,
        video_id: str,
        comment_type: str,
    ) -> SocialEventEnvelope:
        comment_id = str(comment.get("id", "")).strip()
        snippet = comment.get("snippet", {})
        published_at = _parse_timestamp(str(snippet["publishedAt"]))
        text = str(snippet.get("textOriginal") or snippet.get("textDisplay") or "")
        author_channel = snippet.get("authorChannelId") or {}
        author_id = (
            str(author_channel.get("value", ""))
            if isinstance(author_channel, Mapping)
            else str(author_channel)
        )
        payload = {
            "post_id": comment_id,
            "platform": "youtube",
            "author_id": author_id or "unknown",
            "author_followers": 0,
            "content_text": text,
            "hashtags": _hashtags(text),
            "audio_id": None,
            "created_at": _format_timestamp(published_at),
            "collected_at": _format_timestamp(collected_at),
            "views": 0,
            "likes": _integer(snippet.get("likeCount")),
            "comments": _integer(
                raw_payload.get("snippet", {}).get("totalReplyCount")
                if comment_type == "top_level"
                else 0
            ),
            "shares": 0,
            "saves": 0,
            "language": self.config.relevance_language,
            "geography": self.config.region_code,
            "brand": None,
            "source_payload": json.dumps(raw_payload, sort_keys=True, default=str),
        }
        return SocialEventEnvelope.create(
            tenant_id=self.config.tenant_id,
            source_id=self.config.source_id,
            platform="youtube",
            event_type="social.post.observed",
            source_object_id=comment_id,
            occurred_at=published_at,
            collected_at=collected_at,
            correlation_id=str(uuid4()),
            payload=payload,
            attributes={
                "connector_type": "youtube_data_api_v3",
                "delivery_mode": "polling",
                "resource_type": "comment",
                "comment_type": comment_type,
                "parent_video_id": video_id,
                "rule_id": rule.rule_id,
            },
        )
