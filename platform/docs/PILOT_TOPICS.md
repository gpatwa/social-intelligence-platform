# Pilot topics: design draft

**Status: design only.** Nothing here is implemented or deployed.

## Problem

Silver `topic` is a hard-coded `CASE` from the original demo (`battery_issue`,
`glow_up_challenge`, `product_tips`, `lifestyle`). Every pilot post lands in
`lifestyle` or `product_tips`, so topic-level ranking, trend detection and the
evidence key `decision_id = 'topic:<topic>'` say nothing about enterprise AI.
We cannot answer "which topic matters most" (frameworks, evals, reliability,
cost) until posts carry pilot topics.

`topic` cannot simply be replaced. It is used by `gold_topic_hourly`,
`gold_ranked_evidence` (decision key and momentum cohort), the human-label
scorecard (`04_model_governance.py`) and demo validation. Changing it in place
would break those.

## Constraints that shape the design

- **No package in the analytics notebooks.** `02_build_analytics.py` and
  `13_build_ranked_evidence.py` run in the external-ingestion job with no wheel
  attached, so they cannot import `social_intelligence`. Matching has to be
  Spark SQL, or the job must gain a library (a larger change).
- **Additive only.** Keep `topic` and every existing Gold table working.
- **Explainable.** A topic must be traceable to the rule that matched it.
- **Human-governed.** Rules are reviewed, versioned and measured against human
  labels before anything ranks on them.
- **Tenant-scoped.** Rules belong to a tenant; no cross-tenant sharing.
- **Text only.** Rules read title, description and channel text already
  collected. No new data and no identity resolution.

## Proposed design

### 1. Rules as data: `control_topic_rules`

A small Delta table seeded in `00_initialize_platform.py`, next to the existing
collection-rule seed.

| Column | Meaning |
|---|---|
| `tenant_id` | owner |
| `taxonomy_version` | for example `pilot-topics-v1` |
| `topic_id` | stable snake_case id, for example `evals` |
| `rule_id` | `topic_id` plus a short suffix, unique per tenant and version |
| `pattern` | case-insensitive regular expression over title and content text |
| `enabled` | rules can be switched off without a deploy |
| `created_at`, `note` | audit and rationale |

Editing rules is a data change with a PR and review, not a notebook edit.

### 2. Additive Silver columns

`silver_social_posts` gains, without touching `topic`:

- `pilot_topics ARRAY<STRING>`: every topic whose rules matched. A post can be
  both `evals` and `reliability`; forcing one label hides real overlap.
- `pilot_topic_primary STRING`: the first match in a fixed priority order, or
  `other` when nothing matched. One stable value for grouping and cohorts.
- `pilot_topic_rule_ids ARRAY<STRING>`: which rules fired, for explanation.
- `pilot_taxonomy_version STRING`: so a re-run under a new taxonomy is
  distinguishable.

Matching is a `LEFT JOIN` of posts to enabled rules on
`lower(title || ' ' || content_text) RLIKE pattern`, grouped back per post. It
works in plain SQL and needs no library.

### 3. Evidence and ranking

`gold_ranked_evidence` keeps `decision_id = 'topic:<topic>'` for the legacy
demo topics. Pilot topics get their own key, `pilot_topic:<topic_id>`, built
from `pilot_topic_primary`, so existing decisions, validation and the
recommendation workflow are unaffected. Moving the workflow to pilot topics is
a later step with its own review.

GitHub rows are excluded as today (`silver_repo_activity`); adoption is a
separate view.

### 4. Quality gate

Do not rank on the taxonomy until it is measured.

- Use the human-labelled sample (the 50-post YouTube sample, then more) as the
  gold set. `silver_human_labels` already has `reviewed_topic`.
- Report per-topic precision and recall for the rules, and the share of posts
  that fall to `other`.
- Proposed gate: each topic that is ranked needs at least 20 human-labelled
  examples and precision of at least 0.7. Topics below the gate are shown but
  not ranked. These numbers are a starting proposal, not a tested standard.

## Taxonomy v1 (draft)

Derived from one model-labelled sample of 50 YouTube posts (titles only, not
human-verified). Counts are rough.

| `topic_id` | Meaning | Seen in sample |
|---|---|---|
| `framework` | agent frameworks and SDKs (LangGraph, CrewAI, Agents SDK, ADK, Pydantic AI) | 14 |
| `evals` | agent evaluation, benchmarks, grading | 2 |
| `reliability` | production agents, failure handling, observability, state | 6 |
| `mcp` | Model Context Protocol, tool integration | 2 |
| `governance_security` | guardrails, approvals, access control, compliance | 2 |
| `build_vs_buy` | choosing platforms, vendors, frameworks | 1 |
| `cost` | token cost, latency, model choice for cost | 0 (hypothesis) |
| `design_patterns` | memory, context engineering, multi-agent patterns | candidate: appeared in titles, not yet labelled |
| `other` | on topic, no rule matched | 19 |

`cost` stays a hypothesis: it had zero hits. `design_patterns` is a candidate
added from reading titles; confirm it with the next labelled sample before
ranking it. Starter patterns come from the rule vocabulary already used in the
collection queries; they must be written and tested against the labelled set,
not guessed.

## What counts as "most important topic"

Ranking by volume alone would crown `framework`, the noisiest topic. The
summary view should show, per topic and week: post count, distinct authors and
platforms, the human-labelled high-fit share, and engagement normalised within
platform. A topic is "important" only when demand and evidence quality both
hold. This is a reporting view, not a recommendation, and is out of scope for
the first slice.

## Proposed slices (each its own PR)

1. **Rules table and seed.** `control_topic_rules`, v1 patterns, static tests.
2. **Silver columns.** The join and the four additive columns, lineage tests,
   a check that `topic` is unchanged.
3. **Quality report.** Precision, recall and `other` share against human
   labels, as a read-only query.
4. **Evidence key.** `pilot_topic:<id>` in `gold_ranked_evidence`, behind the
   quality gate.
5. **Summary view.** The weekly topic view above.

## Open decisions

- **Multi-label or single:** this draft keeps both (`pilot_topics` and a
  primary). Confirm that the primary priority order is acceptable.
- **Is `design_patterns` in v1?** Needs the next labelled sample.
- **Is `cost` in v1?** Keep as a hypothesis or drop it.
- **Reviewer:** who labels more posts and signs off the gate. Pilot reviewer is
  still unnamed.
- **Language:** patterns are English; many sampled posts are not. Decide
  whether non-English posts are `other` or get their own handling.
- **Regex limits:** rules over titles miss intent and match noise (for example
  "agent evaluation" in a beginner video). Rules improve recall cheaply but do
  not replace a model; revisit once the labelled set is large enough to
  evaluate one.

## Not verified

No rule has been written or tested. The topic counts come from a single
model-labelled sample of 50 titles. The job and notebook constraints were read
from the repository, not from a deployed run.
