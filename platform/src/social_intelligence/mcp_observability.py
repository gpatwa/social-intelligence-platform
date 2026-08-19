"""Structured MCP audit records with optional OpenTelemetry spans."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
from typing import Any, Protocol

try:
    from opentelemetry import trace
except ImportError:  # pragma: no cover - optional outside MCP extra
    trace = None  # type: ignore[assignment]


class AuditSink(Protocol):
    def write(self, record: dict[str, Any]) -> None: ...


@dataclass
class MemoryAuditSink:
    records: list[dict[str, Any]] = field(default_factory=list)

    def write(self, record: dict[str, Any]) -> None:
        self.records.append(dict(record))


@dataclass(frozen=True)
class JsonlAuditSink:
    path: Path

    def write(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True, default=str) + "\n")


class McpAuditRecorder:
    """Record tool metadata without persisting raw prompts or sensitive inputs."""

    def __init__(self, sink: AuditSink | None = None) -> None:
        self.sink = sink
        self._lock = threading.Lock()

    def record(
        self,
        *,
        tool: str,
        tenant_id: str,
        outcome: str,
        started_at: float,
        request_id: str | None = None,
        error_type: str | None = None,
    ) -> None:
        duration_ms = round((time.monotonic() - started_at) * 1000, 2)
        record = {
            "event_type": "mcp.tool.invoked",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "tenant_id": tenant_id,
            "outcome": outcome,
            "duration_ms": duration_ms,
            "request_id": request_id,
            "error_type": error_type,
        }
        if self.sink:
            with self._lock:
                self.sink.write(record)
        if trace:
            span = trace.get_current_span()
            if span.is_recording():
                span.set_attribute("mcp.tool", tool)
                span.set_attribute("tenant.id", tenant_id)
                span.set_attribute("mcp.outcome", outcome)
                span.set_attribute("mcp.duration_ms", duration_ms)
                if error_type:
                    span.set_attribute("error.type", error_type)
