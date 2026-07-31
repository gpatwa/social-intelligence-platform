"""Pure-Python reference implementations of product metric definitions.

The Databricks pipeline implements equivalent expressions in Spark SQL. Keeping
these small functions independent of Spark makes the business logic easy to test.
"""

from __future__ import annotations

from math import log1p


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def engagement_rate(
    likes: int,
    comments: int,
    shares: int,
    saves: int,
    views: int,
) -> float:
    """Return engagement divided by views, safely handling missing reach."""
    if views <= 0:
        return 0.0
    numerator = max(likes, 0) + max(comments, 0) + max(shares, 0) + max(saves, 0)
    return numerator / views


def trend_score(
    velocity_z: float,
    engagement_velocity_z: float,
    acceleration_pct: float,
    creator_count: int,
    platform_count: int,
    novelty: float,
    positive_share: float,
    manipulation_penalty: float = 0.0,
) -> float:
    """Calculate a bounded 0-100 comparative trend score."""
    score = (
        30.0 * clamp(velocity_z / 4.0, 0.0, 1.0)
        + 20.0 * clamp(engagement_velocity_z / 4.0, 0.0, 1.0)
        + 15.0 * clamp(acceleration_pct / 2.0, 0.0, 1.0)
        + 10.0 * clamp(log1p(max(creator_count, 0)) / log1p(100), 0.0, 1.0)
        + 10.0 * clamp(max(platform_count, 0) / 3.0, 0.0, 1.0)
        + 10.0 * clamp(novelty, 0.0, 1.0)
        + 5.0 * clamp(positive_share, 0.0, 1.0)
        - clamp(manipulation_penalty, 0.0, 100.0)
    )
    return round(clamp(score), 2)


def challenge_score(
    participant_growth_pct: float,
    unique_creators: int,
    geography_count: int,
    platform_count: int,
    persistence_hours: int,
) -> float:
    """Score challenge participation breadth, spread, growth, and persistence."""
    score = (
        35.0 * clamp(participant_growth_pct / 3.0, 0.0, 1.0)
        + 25.0 * clamp(log1p(max(unique_creators, 0)) / log1p(100), 0.0, 1.0)
        + 15.0 * clamp(max(geography_count, 0) / 5.0, 0.0, 1.0)
        + 15.0 * clamp(max(platform_count, 0) / 3.0, 0.0, 1.0)
        + 10.0 * clamp(max(persistence_hours, 0) / 24.0, 0.0, 1.0)
    )
    return round(clamp(score), 2)

