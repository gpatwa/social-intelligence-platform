# Social Intelligence Operating Model

## Signal ownership

| Signal | Primary owner | Response target | Required action |
|---|---|---:|---|
| Trend score >= 45 | Marketing insights | 1 business day | Validate relevance; decide whether to create content, partner with creators, or monitor. |
| Challenge score >= 50 | Social/content team | 1 business day | Review participation quality, audience fit, and brand-safety risk. |
| Negative share >= 25% with high-risk mentions | Customer support + communications | 4 business hours | Identify the issue, draft response guidance, and open an incident if product safety is implicated. |
| Stale social feed | Data engineering | 30 minutes | Check source API status, rate limits, and pipeline run history. |
| Material model-quality decline | Data science | 2 business days | Review labeled examples, language coverage, prompt/model version, and rollback path. |

## Operating rhythm

- Daily: marketing reviews the Executive Pulse and Emerging Trends pages.
- Weekly: product, marketing, and support review persistent trends and challenge outcomes.
- Monthly: audit trend false positives, sentiment quality, data-source completeness, and alert thresholds.

## Decision record

For every action taken from a signal, the decision engine records the evidence,
product mapping, hypothesis, action, owner, expected metric, approval rationale,
experiment design, and measured outcome. `PROPOSED` recommendations require a
marketing owner; approved recommendations create a `PLANNED` experiment but do
not launch media or authorize spend.

Weekly pilot review should examine recommendation adoption, experiment velocity,
win rate, incremental revenue, and contribution margin from
`gold_pilot_scorecard`. See [the decision-engine contract](DECISION_ENGINE.md).
