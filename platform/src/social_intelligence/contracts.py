"""Canonical contracts shared by social-source connectors.

Connectors should emit this envelope without depending on the downstream
Databricks schema. The payload remains source-shaped and replayable; Silver is
responsible for mapping it into the product's canonical social-post model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping
from uuid import uuid4


EVENT_SCHEMA_VERSION = "1.0"
SUPPORTED_EVENT_TYPES = frozenset(
    {
        "social.post.observed",
        "social.post.updated",
        "social.post.deleted",
        "social.engagement.observed",
    }
)


def make_idempotency_key(
    tenant_id: str,
    platform: str,
    source_object_id: str,
    event_type: str,
    occurred_at: datetime,
) -> str:
    """Return a stable delivery-independent key for logical event identity."""
    identity = "|".join(
        (
            tenant_id.strip().lower(),
            platform.strip().lower(),
            source_object_id.strip(),
            event_type.strip().lower(),
            occurred_at.astimezone(timezone.utc).isoformat(timespec="microseconds"),
        )
    )
    return sha256(identity.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SocialEventEnvelope:
    """Versioned envelope accepted by the raw social event data plane."""

    event_id: str
    schema_version: str
    tenant_id: str
    source_id: str
    platform: str
    event_type: str
    source_object_id: str
    occurred_at: datetime
    collected_at: datetime
    idempotency_key: str
    correlation_id: str
    payload: Mapping[str, Any]
    attributes: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        source_id: str,
        platform: str,
        event_type: str,
        source_object_id: str,
        occurred_at: datetime,
        payload: Mapping[str, Any],
        collected_at: datetime | None = None,
        correlation_id: str | None = None,
        attributes: Mapping[str, str] | None = None,
    ) -> "SocialEventEnvelope":
        collected = collected_at or datetime.now(timezone.utc)
        event = cls(
            event_id=str(uuid4()),
            schema_version=EVENT_SCHEMA_VERSION,
            tenant_id=tenant_id,
            source_id=source_id,
            platform=platform,
            event_type=event_type,
            source_object_id=source_object_id,
            occurred_at=occurred_at,
            collected_at=collected,
            idempotency_key=make_idempotency_key(
                tenant_id,
                platform,
                source_object_id,
                event_type,
                occurred_at,
            ),
            correlation_id=correlation_id or str(uuid4()),
            payload=dict(payload),
            attributes=dict(attributes or {}),
        )
        event.validate()
        return event

    def validate(self) -> None:
        required = {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "source_id": self.source_id,
            "platform": self.platform,
            "event_type": self.event_type,
            "source_object_id": self.source_object_id,
            "idempotency_key": self.idempotency_key,
            "correlation_id": self.correlation_id,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"Missing required event fields: {', '.join(sorted(missing))}")
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema version: {self.schema_version}")
        if self.event_type not in SUPPORTED_EVENT_TYPES:
            raise ValueError(f"Unsupported event type: {self.event_type}")
        if self.occurred_at.tzinfo is None or self.collected_at.tzinfo is None:
            raise ValueError("Event timestamps must be timezone-aware")
        if not isinstance(self.payload, Mapping):
            raise ValueError("payload must be a mapping")

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-safe landing record with an opaque raw payload."""
        self.validate()
        record = asdict(self)
        record["occurred_at"] = self.occurred_at.astimezone(timezone.utc).isoformat()
        record["collected_at"] = self.collected_at.astimezone(timezone.utc).isoformat()
        record["payload"] = json.dumps(self.payload, sort_keys=True, default=str)
        return record
