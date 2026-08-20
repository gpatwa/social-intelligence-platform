# Cross-platform scoring

The product separates **performance**, **trend momentum**, and **confidence**.
They answer different questions and must not be collapsed into a single raw
engagement ranking.

| Metric | Decision it supports | Guardrail |
| --- | --- | --- |
| `content_performance_score` | Which individual posts are efficient and worth studying? | Engagement rate is 50% of the score; reach and engagement volume are bounded. |
| `trend_score` | Which topics are accelerating unusually quickly? | Uses per-topic historical baselines, velocity, acceleration, novelty, breadth, and sentiment. |
| `cross_platform_confidence` | How much independent evidence supports the trend? | Rewards platform, creator, and post breadth; it is not a forecast. |

`gold_content_performance` exposes the post score and its inputs.
`gold_creator_performance` aggregates those scores per platform so a creator is
not ranked as if native audience and reach metrics were directly comparable
across networks. `gold_trend_snapshot` now includes
`cross_platform_confidence` alongside `trend_score`.

The canonical Python definitions are in
`src/social_intelligence/scoring.py`; Databricks SQL in
`notebooks/02_build_analytics.py` implements the same bounded expressions.
