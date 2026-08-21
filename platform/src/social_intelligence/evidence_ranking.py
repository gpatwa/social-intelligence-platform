"""Deterministic, explainable ranking for decision-specific evidence.

The ranking consumes already-normalized cohort features. It does not scrape,
call a model, or compare raw engagement counts across platforms.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from urllib.parse import urlparse
from typing import Any, Iterable


SUPPORTED_PLATFORMS = frozenset(
    {"youtube", "x", "instagram", "reddit", "knowledge", "metric"}
)
TRUST_TIERS = frozenset({"unverified", "machine_confirmed", "human_reviewed"})
WEIGHTS = {
    "relevance": 0.35,
    "momentum": 0.20,
    "source_quality": 0.15,
    "corroboration": 0.15,
    "freshness": 0.10,
    "safety": 0.05,
}
PLATFORM_HOSTS = {
    "youtube": ("youtube.com", "www.youtube.com", "youtu.be"),
    "x": ("x.com", "www.x.com", "twitter.com", "www.twitter.com"),
    "instagram": ("instagram.com", "www.instagram.com"),
    "reddit": ("reddit.com", "www.reddit.com"),
}


def _bounded_score(value: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    if not 0 <= float(value) <= 100:
        raise ValueError(f"{field} must be between 0 and 100")
    return float(value)


def _required_text(value: str, field: str, maximum: int = 500) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum or any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{field} must be printable and between 1 and {maximum} characters")
    return normalized


def _source_url(value: str, platform: str) -> str:
    normalized = _required_text(value, "source_url", 2048)
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("source_url must be an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("source_url must not contain credentials")
    allowed = PLATFORM_HOSTS.get(platform)
    hostname = (parsed.hostname or "").lower()
    if allowed and hostname not in allowed:
        raise ValueError(f"source_url host does not match platform {platform}")
    return normalized


@dataclass(frozen=True)
class EvidenceCandidate:
    evidence_id: str
    tenant_id: str
    decision_id: str
    platform: str
    source_object_id: str
    source_url: str
    title: str
    author: str
    published_at: str
    observed_at: str
    relevance: float
    momentum: float
    source_quality: float
    corroboration: float
    freshness: float
    safety: float
    trust_tier: str = "machine_confirmed"

    def normalized(self) -> "EvidenceCandidate":
        platform = str(self.platform or "").strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(
                f"platform must be one of: {', '.join(sorted(SUPPORTED_PLATFORMS))}"
            )
        trust_tier = str(self.trust_tier or "").strip().lower()
        if trust_tier not in TRUST_TIERS:
            raise ValueError(
                f"trust_tier must be one of: {', '.join(sorted(TRUST_TIERS))}"
            )
        return EvidenceCandidate(
            evidence_id=_required_text(self.evidence_id, "evidence_id", 256),
            tenant_id=_required_text(self.tenant_id, "tenant_id", 63),
            decision_id=_required_text(self.decision_id, "decision_id", 256),
            platform=platform,
            source_object_id=_required_text(
                self.source_object_id, "source_object_id", 256
            ),
            source_url=_source_url(self.source_url, platform),
            title=_required_text(self.title, "title", 500),
            author=_required_text(self.author, "author", 256),
            published_at=_required_text(self.published_at, "published_at", 64),
            observed_at=_required_text(self.observed_at, "observed_at", 64),
            relevance=_bounded_score(self.relevance, "relevance"),
            momentum=_bounded_score(self.momentum, "momentum"),
            source_quality=_bounded_score(self.source_quality, "source_quality"),
            corroboration=_bounded_score(self.corroboration, "corroboration"),
            freshness=_bounded_score(self.freshness, "freshness"),
            safety=_bounded_score(self.safety, "safety"),
            trust_tier=trust_tier,
        )


def _base_score(candidate: EvidenceCandidate) -> float:
    return round(
        sum(getattr(candidate, name) * weight for name, weight in WEIGHTS.items()),
        2,
    )


def _why(candidate: EvidenceCandidate) -> list[str]:
    dimensions = [
        (candidate.relevance, "Strong match to the decision"),
        (candidate.momentum, "High momentum within its platform cohort"),
        (candidate.source_quality, "Strong source-quality signals"),
        (candidate.corroboration, "Corroborated by independent evidence"),
        (candidate.freshness, "Recently observed"),
        (candidate.safety, "Low evidence-integrity risk"),
    ]
    reasons = [label for score, label in sorted(dimensions, reverse=True) if score >= 70]
    return reasons[:3] or ["Eligible evidence with a complete provenance record"]


def rank_evidence(
    candidates: Iterable[EvidenceCandidate], *, limit: int = 5
) -> dict[str, Any]:
    """Rank unique source URLs and return an explainable, versioned snapshot."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer between 1 and 20")
    normalized = [candidate.normalized() for candidate in candidates]
    if not normalized:
        raise ValueError("at least one evidence candidate is required")
    tenants = {candidate.tenant_id for candidate in normalized}
    decisions = {candidate.decision_id for candidate in normalized}
    if len(tenants) != 1 or len(decisions) != 1:
        raise ValueError("all evidence candidates must share one tenant_id and decision_id")

    unique: dict[str, EvidenceCandidate] = {}
    for candidate in normalized:
        current = unique.get(candidate.source_url)
        if current is None or (_base_score(candidate), candidate.evidence_id) > (
            _base_score(current),
            current.evidence_id,
        ):
            unique[candidate.source_url] = candidate

    ordered = sorted(
        unique.values(),
        key=lambda item: (_base_score(item), item.relevance, item.observed_at, item.evidence_id),
        reverse=True,
    )
    platform_counts: dict[str, int] = {}
    ranked: list[dict[str, Any]] = []
    remaining = list(ordered)
    while remaining and len(ranked) < limit:
        selected = max(
            remaining,
            key=lambda item: (
                _base_score(item) - 5 * platform_counts.get(item.platform, 0),
                item.relevance,
                item.evidence_id,
            ),
        )
        remaining.remove(selected)
        diversity_penalty = 5 * platform_counts.get(selected.platform, 0)
        platform_counts[selected.platform] = platform_counts.get(selected.platform, 0) + 1
        item = asdict(selected)
        item.update(
            {
                "rank": len(ranked) + 1,
                "base_score": _base_score(selected),
                "rank_score": round(max(0.0, _base_score(selected) - diversity_penalty), 2),
                "why_ranked": _why(selected),
                "score_version": "evidence-rank-v1",
            }
        )
        ranked.append(item)

    identity = "|".join(
        f"{item['evidence_id']}:{item['rank']}:{item['rank_score']}" for item in ranked
    )
    ranking_id = sha256(
        f"evidence-rank-v1|{next(iter(tenants))}|{next(iter(decisions))}|{identity}".encode(
            "utf-8"
        )
    ).hexdigest()
    return {
        "ranking_id": ranking_id,
        "schema_version": "1.0",
        "score_version": "evidence-rank-v1",
        "tenant_id": next(iter(tenants)),
        "decision_id": next(iter(decisions)),
        "items": ranked,
        "candidate_count": len(normalized),
        "unique_source_count": len(unique),
        "method": {
            "weights": WEIGHTS,
            "cross_platform_rule": "momentum must be normalized within platform, market, language, and time cohort",
            "diversity_rule": "repeated platforms receive a five-point selection penalty",
        },
        "causality_claim": "none",
        "mutation": "none",
    }
