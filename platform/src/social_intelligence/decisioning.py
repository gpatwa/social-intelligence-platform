"""Domain rules for converting social signals into governed commercial decisions.

The lakehouse implements the same formulas in SQL. Keeping the rules here makes
the decision contract testable without Spark and gives future APIs one canonical
place to validate lifecycle transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import log1p

from .scoring import clamp


RECOMMENDATION_TRANSITIONS = {
    "PROPOSED": frozenset({"APPROVED", "REJECTED"}),
    "APPROVED": frozenset({"EXPERIMENT_PLANNED", "REJECTED"}),
    "EXPERIMENT_PLANNED": frozenset({"RUNNING", "CANCELLED"}),
    "RUNNING": frozenset({"COMPLETED", "CANCELLED"}),
    "COMPLETED": frozenset(),
    "REJECTED": frozenset(),
    "CANCELLED": frozenset(),
}


def stable_decision_id(*parts: str) -> str:
    """Return a deterministic identifier for an idempotently generated record."""
    normalized = "|".join(part.strip().lower() for part in parts)
    if not normalized.replace("|", ""):
        raise ValueError("At least one non-empty identity part is required")
    return sha256(normalized.encode("utf-8")).hexdigest()


def opportunity_score(
    signal_score: float,
    evidence_count: int,
    product_fit: float,
    commercial_fit: float,
    risk_penalty: float = 0.0,
) -> tuple[float, float]:
    """Return (priority, confidence) on bounded 0-100 scales.

    Signal momentum remains the largest input. Confidence increases with
    independent evidence and explicit product/commercial fit. Risk is visible as
    a penalty instead of being silently folded into the underlying signal.
    """
    signal_strength = clamp(signal_score) / 100.0
    evidence_strength = clamp(
        log1p(max(evidence_count, 0)) / log1p(100), 0.0, 1.0
    )
    product_strength = clamp(product_fit, 0.0, 1.0)
    commercial_strength = clamp(commercial_fit, 0.0, 1.0)
    confidence = (
        0.45 * signal_strength
        + 0.20 * evidence_strength
        + 0.20 * product_strength
        + 0.15 * commercial_strength
    )
    priority = 100.0 * (
        0.55 * signal_strength
        + 0.15 * evidence_strength
        + 0.20 * product_strength
        + 0.10 * commercial_strength
    ) - clamp(risk_penalty, 0.0, 100.0)
    return round(clamp(priority), 2), round(100.0 * clamp(confidence, 0.0, 1.0), 2)


def validate_transition(current: str, requested: str) -> None:
    """Reject lifecycle jumps that would bypass approval or measurement gates."""
    current_status = current.strip().upper()
    requested_status = requested.strip().upper()
    if current_status not in RECOMMENDATION_TRANSITIONS:
        raise ValueError(f"Unknown recommendation status: {current}")
    if requested_status not in RECOMMENDATION_TRANSITIONS[current_status]:
        raise ValueError(
            f"Invalid recommendation transition: {current_status} -> {requested_status}"
        )


@dataclass(frozen=True)
class ExperimentResult:
    """Minimal commercial outcome used to close an experiment learning loop."""

    control_revenue: float
    treatment_revenue: float
    actual_spend: float
    gross_margin_rate: float

    def validate(self) -> None:
        if min(self.control_revenue, self.treatment_revenue, self.actual_spend) < 0:
            raise ValueError("Experiment financial values cannot be negative")
        if not 0.0 <= self.gross_margin_rate <= 1.0:
            raise ValueError("gross_margin_rate must be between 0 and 1")

    @property
    def measured_lift_pct(self) -> float | None:
        self.validate()
        if self.control_revenue == 0:
            return None
        return round(
            (self.treatment_revenue - self.control_revenue)
            / self.control_revenue
            * 100.0,
            2,
        )

    @property
    def incremental_contribution_margin(self) -> float:
        self.validate()
        incremental_revenue = self.treatment_revenue - self.control_revenue
        return round(incremental_revenue * self.gross_margin_rate - self.actual_spend, 2)
