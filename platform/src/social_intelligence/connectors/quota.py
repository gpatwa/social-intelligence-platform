"""Persistent daily quota enforcement for source connectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo


class QuotaExceeded(RuntimeError):
    """Raised before a request would exceed its configured daily budget."""


@dataclass(frozen=True)
class QuotaPolicy:
    """YouTube's two read buckets with an operational safety reserve."""

    search_daily_limit: int = 100
    core_daily_limit: int = 10_000
    search_reserve: int = 5
    core_reserve: int = 500
    reset_timezone: str = "America/Los_Angeles"

    def usable_limit(self, bucket: str) -> int:
        if bucket == "search":
            return self.search_daily_limit - self.search_reserve
        if bucket == "core":
            return self.core_daily_limit - self.core_reserve
        raise ValueError(f"Unknown quota bucket: {bucket}")


@dataclass
class QuotaLedger:
    quota_day: str
    search_calls: int = 0
    core_units: int = 0

    @classmethod
    def for_time(cls, now: datetime, timezone_name: str) -> "QuotaLedger":
        if now.tzinfo is None:
            raise ValueError("Quota clock must return a timezone-aware datetime")
        return cls(quota_day=now.astimezone(ZoneInfo(timezone_name)).date().isoformat())

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        now: datetime,
        timezone_name: str,
    ) -> "QuotaLedger":
        current = cls.for_time(now, timezone_name)
        if value.get("quota_day") != current.quota_day:
            return current
        return cls(
            quota_day=current.quota_day,
            search_calls=max(0, int(value.get("search_calls", 0))),
            core_units=max(0, int(value.get("core_units", 0))),
        )

    def to_mapping(self) -> dict[str, int | str]:
        return {
            "quota_day": self.quota_day,
            "search_calls": self.search_calls,
            "core_units": self.core_units,
        }


class QuotaController:
    """Thread-safe, fail-closed quota accounting performed before each call."""

    def __init__(
        self,
        policy: QuotaPolicy,
        ledger: QuotaLedger,
        on_change: Callable[[QuotaLedger], None] | None = None,
    ) -> None:
        self.policy = policy
        self.ledger = ledger
        self._on_change = on_change
        self._lock = Lock()

    def consume(self, bucket: str, units: int, endpoint: str) -> None:
        if units <= 0:
            raise ValueError("Quota units must be positive")
        with self._lock:
            used = (
                self.ledger.search_calls
                if bucket == "search"
                else self.ledger.core_units
            )
            if used + units > self.policy.usable_limit(bucket):
                raise QuotaExceeded(
                    f"Quota reserve reached for {bucket} before {endpoint}: "
                    f"used={used}, requested={units}, "
                    f"usable={self.policy.usable_limit(bucket)}"
                )
            if bucket == "search":
                self.ledger.search_calls += units
            elif bucket == "core":
                self.ledger.core_units += units
            else:
                raise ValueError(f"Unknown quota bucket: {bucket}")
            if self._on_change is not None:
                self._on_change(self.ledger)
