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

For every action taken from a signal, record the trend/challenge ID, hypothesis, action, owner, expected impact, and outcome. This converts the dashboard from passive reporting into a learning loop.

