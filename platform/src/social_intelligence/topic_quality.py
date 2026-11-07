"""Reference implementation of the pilot topic quality report.

The report scores the rules' primary topic against accepted gold labels, per topic.
``16_build_topic_quality.py`` computes the same numbers in Spark SQL; this module
is the oracle a live check compares it against. Precision is measured among the
posts the rules assigned to a topic, so its confidence bound uses that count, and
recall among the posts the gold labels assign to it. The labelled posts are a
random sample of live posts, so both are sample estimates.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

OFF_TOPIC = "off_topic"
OTHER = "other"
# One-sided 95% for the lower bound. A proposal from the design doc, not a tested
# standard: a ranked topic needs enough gold examples and a precision lower bound
# above the floor.
Z = 1.645
MIN_LABELLED = 40
MIN_PRECISION_LOWER_BOUND = 0.7


def wilson_lower_bound(successes: int, n: int, z: float = Z) -> float | None:
    """Lower end of the Wilson score interval for a proportion; None when n is 0."""
    if n <= 0:
        return None
    p = successes / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - spread) / (1 + z * z / n)


@dataclass(frozen=True)
class TopicQuality:
    topic_id: str
    labelled_n: int
    predicted_n: int
    true_positives: int
    precision: float | None
    precision_lower_bound: float | None
    recall: float | None
    meets_sample_size: bool
    meets_precision: bool
    rankable: bool


def score_topics(
    pairs: Iterable[tuple[str, str]],
    *,
    min_labelled: int = MIN_LABELLED,
    min_precision_lower_bound: float = MIN_PRECISION_LOWER_BOUND,
) -> list[TopicQuality]:
    """``pairs`` are (gold_topic, predicted_primary_topic), one per gold-labelled post."""
    pairs = list(pairs)
    gold = Counter(g for g, _ in pairs)
    predicted = Counter(p for _, p in pairs)
    hits = Counter(g for g, p in pairs if g == p)
    results = []
    for topic in sorted(set(gold) | set(predicted)):
        labelled_n, predicted_n, tp = gold[topic], predicted[topic], hits[topic]
        lower = wilson_lower_bound(tp, predicted_n)
        sample_ok = labelled_n >= min_labelled
        precision_ok = lower is not None and lower >= min_precision_lower_bound
        results.append(TopicQuality(
            topic_id=topic, labelled_n=labelled_n, predicted_n=predicted_n, true_positives=tp,
            precision=tp / predicted_n if predicted_n else None, precision_lower_bound=lower,
            recall=tp / labelled_n if labelled_n else None,
            meets_sample_size=sample_ok, meets_precision=precision_ok,
            rankable=sample_ok and precision_ok and topic not in (OTHER, OFF_TOPIC),
        ))
    return results


def summarize(pairs: Sequence[tuple[str, str]]) -> dict[str, float | int | None]:
    """Overall numbers: how many posts, accuracy on on-topic posts, and off-topic leakage."""
    pairs = list(pairs)
    on_topic = [(g, p) for g, p in pairs if g != OFF_TOPIC]
    off_topic = [(g, p) for g, p in pairs if g == OFF_TOPIC]
    return {
        "gold_posts": len(pairs),
        "on_topic_posts": len(on_topic),
        "primary_accuracy": sum(g == p for g, p in on_topic) / len(on_topic) if on_topic else None,
        "off_topic_posts": len(off_topic),
        # a rule fired on a post the gold says is off topic
        "off_topic_firing": sum(p != OTHER for _, p in off_topic),
        "predicted_other_share": sum(p == OTHER for _, p in pairs) / len(pairs) if pairs else None,
    }
