"""Bounded exponential backoff shared by networked connectors."""

from __future__ import annotations

from dataclasses import dataclass
import random
import time
from typing import Callable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays cannot be negative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")

    def run(
        self,
        operation: Callable[[], T],
        should_retry: Callable[[Exception], bool],
        *,
        sleeper: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> T:
        for attempt in range(1, self.max_attempts + 1):
            try:
                return operation()
            except Exception as error:
                if attempt == self.max_attempts or not should_retry(error):
                    raise
                base = min(
                    self.max_delay_seconds,
                    self.base_delay_seconds * (2 ** (attempt - 1)),
                )
                jitter = 1 + self.jitter_ratio * (2 * random_value() - 1)
                sleeper(max(0.0, base * jitter))
        raise AssertionError("unreachable retry state")
