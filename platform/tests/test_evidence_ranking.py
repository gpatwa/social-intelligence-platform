import unittest

from social_intelligence.evidence_ranking import EvidenceCandidate, rank_evidence


def candidate(
    evidence_id: str,
    *,
    platform: str = "youtube",
    source_url: str | None = None,
    relevance: float = 90,
    momentum: float = 80,
    source_quality: float = 75,
    corroboration: float = 70,
    freshness: float = 85,
    safety: float = 95,
) -> EvidenceCandidate:
    return EvidenceCandidate(
        evidence_id=evidence_id,
        tenant_id="internal",
        decision_id="pilot-1",
        platform=platform,
        source_object_id=evidence_id,
        source_url=source_url or f"https://www.youtube.com/watch?v={evidence_id}",
        title=f"Evidence {evidence_id}",
        author="Reference source",
        published_at="2026-08-20T12:00:00+00:00",
        observed_at="2026-08-20T13:00:00+00:00",
        relevance=relevance,
        momentum=momentum,
        source_quality=source_quality,
        corroboration=corroboration,
        freshness=freshness,
        safety=safety,
    )


class EvidenceRankingTests(unittest.TestCase):
    def test_ranking_is_deterministic_explainable_and_non_mutating(self):
        candidates = [
            candidate("video-a"),
            candidate(
                "post-b",
                platform="x",
                source_url="https://x.com/i/web/status/post-b",
                relevance=88,
                momentum=90,
            ),
        ]
        first = rank_evidence(candidates)
        second = rank_evidence(reversed(candidates))
        self.assertEqual(first, second)
        self.assertEqual(first["items"][0]["evidence_id"], "post-b")
        self.assertTrue(first["items"][0]["why_ranked"])
        self.assertEqual(first["causality_claim"], "none")
        self.assertEqual(first["mutation"], "none")

    def test_duplicate_url_keeps_the_stronger_candidate(self):
        url = "https://www.youtube.com/watch?v=shared"
        result = rank_evidence([
            candidate("weak", source_url=url, relevance=20),
            candidate("strong", source_url=url, relevance=95),
        ])
        self.assertEqual(result["unique_source_count"], 1)
        self.assertEqual(result["items"][0]["evidence_id"], "strong")

    def test_platform_url_mismatch_and_cross_tenant_input_fail_closed(self):
        with self.assertRaises(ValueError):
            rank_evidence([
                candidate(
                    "bad",
                    platform="x",
                    source_url="https://www.youtube.com/watch?v=bad",
                )
            ])
        other = candidate("other")
        object.__setattr__(other, "tenant_id", "other")
        with self.assertRaises(ValueError):
            rank_evidence([candidate("one"), other])


if __name__ == "__main__":
    unittest.main()
