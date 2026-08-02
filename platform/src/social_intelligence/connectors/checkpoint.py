"""Versioned connector checkpoints with atomic filesystem persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4


CHECKPOINT_SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ConnectorCheckpoint:
    """Committed source progress and daily quota usage."""

    schema_version: int = CHECKPOINT_SCHEMA_VERSION
    cursors: Mapping[str, str] = field(default_factory=dict)
    quota: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=_utc_now)

    @classmethod
    def empty(cls, now: datetime | None = None) -> "ConnectorCheckpoint":
        return cls(updated_at=now or _utc_now())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ConnectorCheckpoint":
        schema_version = int(value.get("schema_version", 0))
        if schema_version != CHECKPOINT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported checkpoint schema: {schema_version}")
        updated_at = datetime.fromisoformat(
            str(value["updated_at"]).replace("Z", "+00:00")
        )
        if updated_at.tzinfo is None:
            raise ValueError("Checkpoint updated_at must be timezone-aware")
        return cls(
            schema_version=schema_version,
            cursors=dict(value.get("cursors", {})),
            quota=dict(value.get("quota", {})),
            metadata=dict(value.get("metadata", {})),
            updated_at=updated_at.astimezone(timezone.utc),
        )

    def to_dict(self) -> dict[str, Any]:
        if self.updated_at.tzinfo is None:
            raise ValueError("Checkpoint updated_at must be timezone-aware")
        return {
            "schema_version": self.schema_version,
            "cursors": dict(self.cursors),
            "quota": dict(self.quota),
            "metadata": dict(self.metadata),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
        }


class JsonCheckpointStore:
    """Persist a checkpoint only after its corresponding events are landed."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> ConnectorCheckpoint:
        if not self.path.exists():
            return ConnectorCheckpoint.empty()
        return ConnectorCheckpoint.from_dict(json.loads(self.path.read_text()))

    def save(self, checkpoint: ConnectorCheckpoint) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(checkpoint.to_dict(), indent=2, sort_keys=True) + "\n"
            )
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()
