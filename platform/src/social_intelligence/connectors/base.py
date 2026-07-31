"""Provider-neutral connector contracts.

The data plane accepts only :class:`SocialEventEnvelope` instances. Provider
adapters are responsible for pagination and source-specific mapping, while the
runtime owns checkpoints, quotas, and delivery semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

from social_intelligence.contracts import SocialEventEnvelope
from social_intelligence.connectors.checkpoint import ConnectorCheckpoint


SUPPORTED_RULE_TYPES = frozenset({"keyword", "channel"})


@dataclass(frozen=True)
class CollectionRule:
    """A control-plane rule consumed by a polling connector."""

    rule_id: str
    rule_type: str
    expression: str
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("rule_id is required")
        if self.rule_type not in SUPPORTED_RULE_TYPES:
            raise ValueError(f"Unsupported collection rule type: {self.rule_type}")
        if not self.expression.strip():
            raise ValueError("rule expression is required")


@dataclass(frozen=True)
class ConnectorBatch:
    """Atomic connector output returned before landing and checkpoint commit."""

    events: tuple[SocialEventEnvelope, ...]
    checkpoint: ConnectorCheckpoint
    statistics: Mapping[str, int] = field(default_factory=dict)


class SourceConnector(Protocol):
    """Interface implemented by every polling or streaming source adapter."""

    def collect(
        self,
        rules: Sequence[CollectionRule],
        checkpoint: ConnectorCheckpoint,
    ) -> ConnectorBatch:
        """Collect a replayable batch without persisting its checkpoint."""
