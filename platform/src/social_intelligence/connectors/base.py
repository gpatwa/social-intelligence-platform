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


# These are intentionally provider-neutral. A connector advertises the subset it
# accepts through ``ConnectorCapabilities`` rather than overloading a YouTube
# concept such as ``channel`` for every platform.
SUPPORTED_RULE_TYPES = frozenset(
    {"keyword", "channel", "hashtag", "account", "community", "trend"}
)


@dataclass(frozen=True)
class ConnectorCapabilities:
    """Explicit provider features used by control-plane validation and UI."""

    platform: str
    supported_rule_types: frozenset[str]
    supports_public_search: bool = False
    supports_account_collection: bool = False
    supports_engagement_metrics: bool = False
    supports_webhooks: bool = False
    supports_delete_events: bool = False

    def __post_init__(self) -> None:
        if not self.platform.strip():
            raise ValueError("connector platform is required")
        unsupported = self.supported_rule_types - SUPPORTED_RULE_TYPES
        if unsupported:
            raise ValueError(
                "Unsupported connector rule types: "
                + ", ".join(sorted(unsupported))
            )


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
