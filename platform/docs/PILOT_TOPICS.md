# Pilot topics: design draft (revision 2)

**Status: design only, decisions accepted 2026-11-05.** Nothing here is implemented or deployed. Revision 2
folds in a Staff-engineer review of revision 1; the review's code claims were
checked against the repository where marked "verified", and the rest are
labelled "inferred".

## Problem

Silver `topic` is a hard-coded `CASE` from the original demo (`battery_issue`,
`glow_up_challenge`, `product_tips`, `lifestyle`; `02_build_analytics.py`). On
live pilot posts it says nothing about enterprise AI, so topic-level ranking,
trend detection and the evidence key `decision_id = 'topic:<topic>'` cannot
answer "which topic matters most" (frameworks, evals, reliability, governance).

Measured on 2026-11-05 in the dev workspace, live sources only (`source_id` in
`youtube-api-v3`, `x-api-v2`; the demo job's synthetic rows share
`platform = 'youtube'` and must be excluded), 306 posts:

| Platform | Posts | `lifestyle` | `product_tips` | `battery_issue` |
|---|---|---|---|---|
| YouTube | 221 | 193 | 24 | 4 |
| X | 85 | 80 | 1 | 4 |

So 273 of 306 (89%) fall to the `lifestyle` default and 8 (2.6%) land in
`battery_issue` because the legacy rule matches the substrings `problem` and
`issue` anywhere. `battery_issue` rows feed `gold_trending_topics`, and
`signal_key = topic` feeds the opportunity workflow, so the pilot can already
emit a "battery issue" opportunity from an enterprise-AI post. Small today, but
a defect. Also: every live YouTube row has `language = 'und'` (221 of 221, set by
PR 22 when no language is declared), so `language` cannot filter English.

`topic` cannot simply be replaced. It is used by `gold_topic_hourly`,
`gold_ranked_evidence` (decision key at `13_build_ranked_evidence.py:33` and the
momentum cohort), the human-label scorecard (`04_model_governance.py:88` compares
`reviewed_topic` to `topic`) and demo validation.

## Constraints that shape the design

- **No package in the analytics notebooks.** `02_build_analytics.py` and
  `13_build_ranked_evidence.py` run with no wheel attached and cannot import
  `social_intelligence`. Matching has to be Spark SQL, or the job must gain a
  library (a larger change). Python at notebook time is allowed.
- **Additive only.** Keep `topic` and every existing Gold table working.
- **Silver grain is one row per `tenant_id, platform, post_id`.** Content
  performance, creator counts and ranked evidence assume it (verified for the
  joins at `13:63-66`). Nothing here may change it.
- **Explainable.** A topic must be traceable to the rule that matched it.
- **Human-governed.** Rules are reviewed, versioned and measured against held-out
  human labels before anything ranks on them.
- **Tenant-scoped.** Rules and labels belong to a tenant; no cross-tenant sharing.
- **Text only.** Rules read text already collected. No new data, no identity
  resolution.

## Proposed design

### 1. Rules as data: `control_topic_rules`

A small Delta table seeded in `00_initialize_platform.py`, using the same MERGE
seed pattern as the existing control tables.

| Column | Meaning |
|---|---|
| `tenant_id` | owner |
| `taxonomy_version` | for example `pilot-topics-v1`; one active version per tenant |
| `topic_id` | stable snake_case id, for example `evals` |
| `rule_id` | `topic_id` plus a short suffix; unique per (`tenant_id`, `taxonomy_version`) and the MERGE key |
| `priority` | integer; lower wins when several topics match (see 3) |
| `pattern` | case-insensitive regex, restricted to a portable subset (below) |
| `exclude_pattern` | optional, same subset; the rule does not fire when it matches (for example beginner tutorials and courses on the broad framework rule); empty when unused |
| `enabled` | rules can be switched off without a deploy |
| `created_at`, `note` | audit and rationale |

Editing rules is a data change through a PR and review, not a notebook edit.

**Portable pattern subset.** Spark uses Java regex and the unit tests would use
Python `re`; they differ on inline flags and `\p{}` classes. Rules may use only
literals, alternation, groups, character classes and `\b`. A validator rejects
anything else, patterns over a length cap, and patterns that do not compile.

### 2. Matching: build the expression at notebook time, no cross join

The notebook reads the enabled rules for the tenant's active version (a few dozen
rows) with `spark.table(...).collect()`, validates each pattern, and builds one
`FILTER(ARRAY(...))` / `CASE` expression over the post text. This keeps matching
in Spark SQL, removes the posts x rules join and its fan-out risk, and avoids
per-row regex recompilation. One malformed rule row is skipped and counted, it
must not abort the whole Silver build (which would stop every downstream table).

**Matching text, defined.** Silver `content_text` is the title plus a newline plus
the description for YouTube (`youtube.py`), and the full post text for X, where
`source_title` is only its first 160 characters. Channel name is `source_author`,
a separate column and not matched. Match on `lower(<normalized title> || ' ' ||
<first N characters of normalized description>)` where N (proposed 500) keeps long
promotional descriptions, which restate a channel's whole topic list, from
inflating false positives. N and the title-only alternative are both scored on the
labelled set before one is chosen.

**Normalization, once, in a CTE.** Landed YouTube titles are HTML-escaped and
sometimes double-escaped (`&#39;`, `&amp;amp;`, `&quot;`). Unescape these, then
lowercase. Word-boundary `\b` patterns are required for short tokens (`mcp`,
`eval`) so they do not match inside other words. `\b` is ASCII-oriented in Java by
default, so non-ASCII text is matched on the lowered form only.

### 3. Where results live

Silver keeps one row per post. Two additive changes:

- **Columns on `silver_social_posts`, for display and explanation only:**
  `pilot_topic_primary STRING`, `pilot_topic_rule_ids ARRAY<STRING>`,
  `pilot_taxonomy_version STRING`. No existing column changes, including `topic`.
- **A long table `silver_post_topics(tenant_id, platform, post_id, topic_id,
  rule_id, taxonomy_version)`**, one row per matched topic. Multi-label counting,
  joins and audits use this table, not arrays, so a regrouping bug cannot corrupt
  Silver's grain.

**Primary topic.** The matched rule with the lowest `priority` wins; ties break on
`rule_id` (deterministic). Priority is by specificity, not by frequency: narrow
topics (`evals`, `governance_security`, `mcp`) outrank the broad `framework`, which
otherwise swallows most posts. `other` means on-topic evidence with no rule match.

**Counting rule.** Ranking and any per-topic total use the primary topic only.
Any multi-label view must say "posts mentioning the topic; totals exceed the post
count". The build asserts that `COUNT(*)` and `COUNT(DISTINCT post_id)` of Silver
are unchanged by this step.

**Legacy `topic`.** It stays computed. Decision for the owner: whether pilot-tenant
rows should stop using the legacy `problem|issue` rule (the 8 mislabelled posts
above). Recommended: yes, route them to the pilot taxonomy and leave the demo rules
for demo data.

### 4. Evidence and ranking

`gold_ranked_evidence` keeps `decision_id = 'topic:<topic>'` for legacy topics.
Pilot topics get `pilot_topic:<topic_id>` built from `pilot_topic_primary`. That
needs a UNION in the cohort CTE and the topic-platform corroboration step
(`13_build_ranked_evidence.py`), and a `taxonomy_version` column on the evidence
rows so a version change does not silently rewrite history.

`decision_id` is a caller-supplied contract (MCP service, review scorecard,
campaign intelligence), not an in-notebook join (verified: `12_build_decision_
workflow.py` derives opportunities from `signal_key`, not from ranked evidence).
Before slice 5, list every consumer that must accept `pilot_topic:*` ids. The same
post appears under a legacy and a pilot decision id by design; the Snowflake
publish (a replace) and any distinct-evidence counts must tolerate that.

With sparse pilot data most topics are single-platform, so the cross-platform
corroboration term will be flat. Expect that; do not read it as a defect.

The quality gate is a table, not a convention: `gold_topic_quality(tenant_id,
taxonomy_version, topic_id, labelled_n, precision_lower_bound, rankable)`, and
ranking joins `rankable`.

GitHub rows stay excluded as today; adoption is a separate view.

### 5. Quality gate

Do not rank on the taxonomy until it is measured on data no rule author has seen.

- **Labels get their own table.** `silver_human_labels.reviewed_topic` holds the
  legacy vocabulary and the scorecard compares it to `topic`; reusing it would
  silently report about zero accuracy for pilot labels. `reviewed_pilot_topic`
  (slice 1, built) is keyed by tenant, platform, post **and labeller**, not by post
  alone: the second labeller must label the same posts for the agreement check, and
  the earlier draft key would have forbidden that. Every row records `label_source`
  (`human` or `model`, always explicit, never defaulted) and the quality gate counts
  `human` rows only. The existing label CSVs are model-labelled and live untracked in
  the repo root; load them as `model`.
- **No circularity.** Write rules from a training set (the 50-post v2 sample and the
  27-post v3 sample). Score only on a fresh random held-out set, frozen before
  scoring, and record which post ids were used for authoring.
- **Precision gate.** Each ranked topic needs at least 40 held-out labelled
  examples and a Wilson lower bound on precision of at least 0.7. At 20 examples a
  0.7 point estimate cannot distinguish a true 0.6 from 0.7 (reviewer's estimate,
  not run), so 20 was too weak. These numbers are a proposal, not a tested standard.
- **Recall.** Label a random sample of all posts, including ones that matched
  nothing, and measure recall against that. Per-topic recall from about 25
  title-only labels is not meaningful; report only the `other` share until the
  sample is larger.
- **Agreement.** A second reviewer labels 20 posts so agreement can be estimated.

### 6. Observability and rollback

- `gold_topic_rule_yield(tenant_id, taxonomy_version, rule_id, matches, last_match)`
  plus the `other` share per run, parallel to the existing collection-rule yield
  query. A run whose `other` share crosses a threshold fails loudly.
- **Backfill and version changes are a rerun**, not a migration: Silver is rebuilt
  by `CREATE OR REPLACE` on every run (verified in the notebook and its tests).
- **Rollback:** set `enabled = false` on the rules (or the version) and rerun
  Silver. The additive columns can stay.

## Taxonomy v1 (draft)

Two model-labelled YouTube samples (titles only, not human-verified), both too
small to trust. The counts swing hard between them, which is itself the finding:
the mix is not yet stable.

| `topic_id` | Meaning | v2 sample (n=50) | v3 sample (n=27) |
|---|---|---|---|
| `framework` | agent frameworks and SDKs (LangGraph, CrewAI, Agents SDK, ADK, Pydantic AI) | 14 | 2 |
| `evals` | agent evaluation, benchmarks, grading | 2 | 3 |
| `reliability` | production agents, failure handling, observability, state | 6 | 4 |
| `mcp` | Model Context Protocol, tool integration | 2 | 1 |
| `governance_security` | guardrails, approvals, access control, compliance | 2 | 10 |
| `build_vs_buy` | choosing platforms, vendors, frameworks | 1 | 4 |
| `other` | on topic, no rule matched | 19 | 2 |

**Cut from v1:** `cost` (0 hits in the first sample, 1 in the second) and
`design_patterns` (no labelled support). Add either only when the held-out set
holds at least 20 labelled examples. Starter patterns must be written and tested
against the training set, not guessed.

**Language.** Live YouTube rows are all `und`, so `language` cannot gate matching.
Patterns are English. Posts that are not English are mapped to `other`, flagged
`language_unsupported` by a cheap script-detection heuristic, and counted. No
translated rules in v1.

## What counts as "most important topic"

Ranking by volume alone would crown `framework`, the noisiest topic. A summary view
should combine demand and evidence quality, but it is **out of scope for v1**; it
depends on a trustworthy taxonomy first.

## Proposed slices (each its own PR)

1. **Labels first (built).** `reviewed_pilot_topic` table
   (`00_initialize_platform.py`) and the idempotent loader
   (`social_intelligence/pilot_labels.py`, CLI `social-intelligence-pilot-labels`).
   Acceptance, tested: reloading the same CSV changes no rows (`received_at` is
   excluded from the comparison and the labelling day is an explicit argument); a
   changed label is refused before anything is written; a second labeller can label
   the same posts; titles, authors and URLs are never stored; a static test asserts
   the tenant column and the key. Both real sample files parse (50 and 27 rows).
   Not yet run against the workspace: the table is created on the next deploy.
2. **Rules table and validator (built).** `control_topic_rules` with `priority` and
   `exclude_pattern`, a MERGE seed that is the source of truth (changed rules are
   updated, removed rules are disabled, never deleted, only within the seeded
   tenant), and the reference implementation `social_intelligence/topic_rules.py`
   (portable-pattern validator, HTML normalization, matching, deterministic
   primary topic). The notebook cannot import the package, so a test parses the
   notebook's seed literal and requires it to equal the reference rules. Tested on
   hand-written fixtures, not on the sampled titles. Matching in Silver is slice 3.
3. **Normalization and matching in Silver (built).** `02_build_analytics.py` adds
   `pilot_topic_primary`, `pilot_topic_rule_ids`, `pilot_taxonomy_version` and
   `language_unsupported` to `silver_social_posts` and writes `silver_post_topics`
   (one row per post and matched rule). The match expression is built at notebook
   time from the enabled rules of the active taxonomy version (widget
   `taxonomy_version`); there is no posts x rules join. Demo sources
   (`source_id LIKE 'demo-%'`) and tenants without rules get NULL, not `other`.
   A pattern Spark rejects is skipped with a warning instead of aborting the build,
   and the notebook raises if Silver's grain changes. Acceptance, checked live on
   dev: Silver row count and distinct posts equal (1,583), legacy `topic`
   unchanged, and Spark's output equals the Python reference on all 640 live posts
   (primary topic, matched rule ids and the non-English flag) with 0 mismatches.
4. **Quality report and rule yield (built).** `16_build_topic_quality.py` (a job task
   after `refresh_analytics`; nothing depends on it) writes `gold_topic_quality`
   (per topic: labelled, predicted, true positives, precision, Wilson lower bound,
   recall, `meets_sample_size`, `meets_precision`, `rankable`),
   `gold_topic_quality_summary` and `gold_topic_rule_yield` (including rules that
   never fire). It is read-only reporting: it changes nothing ranking reads.
   Gold labels are human labels (always accepted) plus labellers listed in
   `control_gold_labellers`, which holds `agent_reviewer_01` by the owner's decision
   of 2026-11-06 (the seed is the source of truth; removing the row revokes it). Gate
   parameters are job widgets (`min_labelled` 40, `min_precision_lower_bound` 0.7).
   Reference implementation `social_intelligence/topic_quality.py`; on dev, Spark's
   output equals it on all 10 topic rows and the summary, and the job passes all 12
   tasks.
5. **Evidence key behind the gate.** `rankable`, `taxonomy_version`, consumer list.

## v1 rules and their first measurement

Six rules, by priority (lowest wins): `governance_security` 10, `evals` 20, `mcp` 30,
`reliability` 40, `build_vs_buy` 50, `framework` 60. They were written and tuned
only against the 77 model-labelled **training** posts (50 + 27, `label_source =
model`); the held-out sheets were drawn afterwards and no rule has seen them.

Measured on the 73 on-topic training posts, so these numbers are optimistic by
construction and are not a quality estimate:

| Topic | Labelled | Predicted | Precision | Recall |
|---|---|---|---|---|
| `governance_security` | 12 | 16 | 0.75 | 1.00 |
| `evals` | 5 | 3 | 1.00 | 0.60 |
| `mcp` | 3 | 5 | 0.60 | 1.00 |
| `reliability` | 10 | 5 | 0.80 | 0.40 |
| `framework` | 16 | 25 | 0.48 | 0.75 |
| `build_vs_buy` | 5 | 0 | n/a | 0.00 |
| `other` | 21 | 19 | 0.42 | 0.38 |

Primary accuracy 58% (n = 73); none of the 4 `off_topic` posts fired a rule. What
the errors taught:

- **`build_vs_buy` is a business-strategy topic, not a vocabulary one.** The labelled
  examples are "train your own models", an acquisition, a funding round. A bare `vs`
  rule fired on framework comparisons the labeller called `framework`, so the rule
  is narrow on purpose and currently matches nothing in the training set. It will
  almost certainly miss the quality gate; show it, do not rank it.
- **`framework` versus `other` is inconsistently labelled.** Some LangGraph
  tutorials are `framework`, others `other`. Rules cannot fix inconsistent labels;
  a written labelling rubric and the second labeller's agreement check can.
- Non-English titles (Spanish, Japanese) fall to `other` by design; some are
  `reliability` to a human reader.
- Titles that list many technologies ("... + langchain + langgraph + mcp") match
  `mcp` or `framework` although the label is `other`.

## Held-out labels and agreement (2026-11-06)

Two independent agents, with no shared context, labelled the held-out sheets from
titles only: `agent_labeller_01` (Opus-class model) labelled all 60 posts (40
YouTube, 20 X) and `agent_labeller_02` (a different model) labelled a hash-selected
20-post subset (12 YouTube, 8 X). Both are loaded into `reviewed_pilot_topic` with
`label_source = model`, tenant `demo`, labelled on 2026-11-06. The 77 earlier
training labels are `model_run_01`. No human labels exist yet.

Agreement on the 20 shared posts: topic 85% (Cohen's kappa 0.81), on-topic versus
off-topic 90%, audience fit exactly 90% and within one level 100%. Disagreements:
one `framework` versus `reliability`, two `other` versus `off_topic`.

**Read this number with care.** Both labellers followed the same written rubric and
are both models, so their errors are correlated; human-to-human agreement would be
lower. n = 20 is small. It shows the rubric is usable, not that the labels are
right. The primary labeller marked 15 of 60 rows "unsure".

### Senior reviewer labels (2026-11-06)

At the owner's request a third agent, `agent_reviewer_01` (Opus-class model),
labelled all 60 held-out posts as a senior reviewer. It was given the rubric
below **with the proposed tie-breaks applied**, so some of its differences from the
first two labellers come from the rubric change, not from judgement. It is loaded
with `label_source = model`: the owner asked for a stronger reviewer to stand in for
human labels, but a model's judgement is not a person's, so it is not recorded as
`human` and the human-only gate is still unmet. Treating this labeller as the gold
set is an explicit gate setting for slice 4 (a configurable set of accepted
labellers, default human only), to be chosen by the owner, not a relabelling of
provenance.

Agreement of the reviewer with `agent_labeller_01` on all 60 posts: topic 87%
(kappa 0.83), on-topic 92%, audience fit exactly 92%. With `agent_labeller_02` on
the 20 shared posts: topic 80% (kappa 0.75), on-topic 95%, fit exactly 95%. The
earlier pair scored 85% (kappa 0.81). The reviewer and `agent_labeller_01` are the
same model family, so their agreement is the least independent of the three
pairs. Where they differ the cases are `other` versus `off_topic` (4 posts) and
`other` versus `design_patterns` (2); remaining ambiguities the reviewer reported:
accuracy-improvement case studies between `evals` and `reliability`, talks on where
agents run between `other` and `build_vs_buy`, news of attacks carried out by
agents between `governance_security` and `off_topic`, and cheap-model releases
between `off_topic` and `cost`.

### Labelling rubric v1 (as given to the labellers)

One primary topic per post from the title text alone: `framework`, `evals`,
`reliability`, `mcp`, `governance_security`, `build_vs_buy`, `cost`,
`design_patterns`, `other` (about agents, no topic is the main subject), or
`off_topic`. Decide on the main subject, not every keyword; a list of many
technologies is usually `other`. `audience_fit` is how useful the post is to an
engineering or platform lead choosing an agent stack: high informs a decision with
substance, medium is relevant but shallow, promotional or news-like, low is
beginner, off-focus or noise.

### Rubric ambiguities both labellers hit (proposed tie-breaks, for the owner to confirm)

- `mcp` versus `governance_security`, for example MCP supply-chain checks: label by
  the concern. A security control wins, so `governance_security`.
- `framework` versus `reliability`, for example one framework's checkpointing or
  error handling: label by the main subject; a framework-specific how-to is
  `framework`, a general production practice is `reliability`.
- `framework` versus `build_vs_buy`, for example a build tutorial on a managed
  platform: a tutorial is `framework`; `build_vs_buy` is reserved for the decision
  itself or for vendor news.
- `cost` versus `build_vs_buy`, for example self-hosting a model versus paying for
  APIs: `cost` when money or latency is the argument, otherwise `build_vs_buy`.
- `other` versus `off_topic`, for example vague AI hype or AI-attack news shorts:
  `off_topic` unless agents are the subject.
- `audience_fit` has no rule for beginner tutorials on on-topic subjects; the
  labellers rated them `low`. Make that explicit.

## First held-out result (2026-11-06)

The rules scored against the 60 held-out posts, with `agent_reviewer_01` as gold
(51 on-topic, 9 `off_topic`):

| Topic | Gold | Predicted | Precision | Lower bound | Recall |
|---|---|---|---|---|---|
| `framework` | 23 | 22 | 0.64 | 0.46 | 0.61 |
| `evals` | 5 | 6 | 0.67 | 0.35 | 0.80 |
| `governance_security` | 4 | 5 | 0.20 | 0.05 | 0.25 |
| `mcp` | 3 | 3 | 0.33 | 0.08 | 0.33 |
| `reliability` | 2 | 3 | 0.33 | 0.08 | 0.50 |
| `build_vs_buy` | 1 | 1 | 1.00 | 0.27 | 1.00 |
| `other` | 8 | 20 | 0.25 | 0.13 | 0.62 |
| `cost`, `design_patterns` | 5 | 0 | n/a | n/a | 0.00 |

Primary accuracy on on-topic posts is **53%** (58% on the training set), and rules
fired on 4 of the 9 `off_topic` posts. **No topic is rankable:** the gate needs 40
gold examples per topic (`framework` has 23, the largest) and a precision lower
bound of 0.7 (the best is 0.46). With 60 gold posts the sample-size half of the gate
cannot be met for any topic, so a larger gold set is a precondition, not a detail.

How to read it, without over-reading n = 60:

- The gap between training and held-out is the overfitting the split was meant to
  expose: `governance_security` scored precision 0.75 and recall 1.00 on training
  and 0.20 and 0.25 here. The rules are weak, not just under-measured.
- The rules over-predict `other` (20 predicted against 8 gold): many posts the
  reviewer judged on-topic fall through, and `cost` and `design_patterns` are
  labelled but have no rule.
- **This held-out set is now spent.** Any rule change made after reading this table
  turns it into training data; the next round needs a fresh random sample.
- The gold labeller is a model by the owner's choice. These numbers say how well the
  rules agree with that labeller, not with a person.

## What the live parity check found (2026-11-06)

Comparing Spark's Silver output with the Python reference on every live post
caught one real difference that no unit test could have: **`\b` in Spark's regex
on the Databricks runtime is Unicode-aware**, so `langgraphに学ぶ` has no word
boundary after `langgraph` there. The first reference used ASCII-only boundaries
and disagreed on 3 of 640 posts. The reference now uses Python's default (Unicode)
`\b`, and rules avoid `\s` and `\w`, which differ between the engines. The
runtime's JDK version can change this, so the live check is worth rerunning after
any runtime upgrade.

First live distribution of the primary topic on 640 live posts: `other` 219 (34%),
`framework` 155 (24%), `governance_security` 116 (18%), `mcp` 59, `reliability` 44,
`evals` 44, `build_vs_buy` 3. The old rules put 576 of the same posts in
`lifestyle`. These are rule outputs, not a quality measurement: the quality report
(slice 4) scores them against the accepted gold labels.

## Second labelling round and rule revision (2026-11-10)

**Result: a larger gold set was built, but revising the keyword rules did not help on
sealed data. Nothing was adopted.** No topic can be ranked.

**Sample.** The Databricks SQL warehouse would not start (the platform answered
"Cannot create the resource"), so posts were drawn from the raw landed event files:
733 unique posts (384 X, 349 YouTube). After excluding the 137 already labelled, 596
were left (364 X, 232 YouTube). A seeded random sample of 240 (120 per platform, seed
20261111, SHA-256 prefix `210062da`) was frozen before any rule change.

**Labels.** Four Opus-class model agents labelled 60 posts each from the text alone,
with the rubric and the six tie-breaks below applied; a fifth labelled a hash-selected
40-post subset independently. Both are models following one rubric, so their errors
are correlated; no human labelled anything and the human-only gate is still unmet.
The tie-breaks were applied as a working rubric and are **not yet confirmed by the
owner**. Agreement on the 40 shared posts: topic 92% (kappa 0.91), on-topic versus
off-topic 98%, audience fit 92%. The labellers marked 98 of 240 posts (41%) unsure.
Gold counts: `framework` 51, `other` 40, `governance_security` 37, `off_topic` 28,
`evals` 22, `reliability` 18, `mcp` 18, `design_patterns` 14, `build_vs_buy` 8, `cost` 4.
Only `framework` reaches the 40-example size requirement. About 22% of X posts (26 of
120) were off-topic, against 2 of 120 YouTube posts; 38 of 240 (16%) were rated high
audience fit.

**Split.** Within each platform the 240 were ordered by SHA-256 of `split` plus the post
id: the first 60 per platform are `dev` (120, used to author rules) and the rest are
the sealed `test` (120, SHA-256 prefix `e5d7ad72`). Rules were authored from `dev` plus
the 77 earlier training labels. The 60 earlier held-out labels exist only in
Databricks, which could not be reached, so they were not used.

**Revision (v3).** Changes were derived from `dev` and the earlier training errors:
framework tutorials count as `framework` (the tie-break), distinctive framework names
match without a word boundary so they work next to CJK text, `evals` ahead of
`governance_security`, `build_vs_buy` ahead of `reliability`, and new narrow `cost` and
`design_patterns` rules. A first draft (v2) used broad terms such as bare "production",
"harness" and "planning" and fired on more off-topic posts, so v3 narrowed them.

| Set | v1 accuracy | v3 accuracy |
|---|---|---|
| Earlier training labels (77) | 59% | 60% |
| `dev` (120, used to author v3) | 64% | 76% |
| **Sealed `test` (120, 110 on-topic), scored once after v3 was locked** | **53%** | **55%** |

On the sealed test the only visible change was `framework` recall (0.67 to 0.81, 18 to
22 correct) at precision 0.63; `governance_security`, `mcp`, `evals` and `reliability`
did not move, `design_patterns` and `cost` stayed near zero, and rules fired on 4 of
10 off-topic posts, as before. A 2-point difference on 110 posts is noise. The 12-point
gain on `dev` did not generalise, which is the overfitting this split exists to expose.
No topic passes the gate: the largest sealed-test gold count is 27 (`framework`; the
gate needs 40) and the best precision lower bound is 0.49 (needs 0.70).

**Caveats.** The earlier training labels (`model_run_01`) predate the tie-breaks and
call beginner framework tutorials `other`, so they disagree with the current rubric on
exactly the case v3 changed. The `test` half is now spent: using its errors would turn
it into training data. These numbers measure agreement with a model labeller, not with
a person.

**What this says.** Keyword rules plateau near 55% primary accuracy on this data.
Raising the gold set will not change that by itself; it only tightens the estimate.
Options, for the owner to choose: (1) keep the rules as a weak first pass and add a
model classifier with a human audit sample; (2) keep ranking off and show only
volume-by-topic labelled as unvalidated, as the landing page already does; (3) collect
targeted examples for the rare topics so each can be measured. The six tie-breaks still
need confirmation before more labelling.

Gold labels (ids and labels only, no text) are kept untracked in `pilot_gold_round2.csv`
at the repository root; they have not been loaded into `reviewed_pilot_topic`.

## Decisions (accepted by the pilot owner, 2026-11-05)

1. **Multi-label plus primary:** yes. A long table with explicit `priority`; rank on
   the primary topic only in v1.
2. **`design_patterns` and `cost`:** cut from v1; add each only when the held-out
   set holds at least 20 labelled examples.
3. **Reviewer:** the pilot owner signs off the gate. Updated 2026-11-06: the owner
   chose to have AI agents label the held-out sheets instead of labelling by hand,
   and to use a second agent as the second labeller (see Held-out labels below).
   Those are **model** labels, so the human-only gate in the quality section is not
   met by them; the owner can review or correct any rows, which would then be loaded
   as human labels.
4. **Non-English:** mapped to `other`, flagged `language_unsupported` and counted;
   no translated rules in v1.
5. **Legacy rules for pilot-tenant rows:** stop applying the demo `problem|issue`
   rule to them; the demo rules stay for demo data.
6. **Matching text (settled 2026-11-06):** the first 300 characters of the normalized
   `content_text` (title plus the start of the description for YouTube, the start of
   the post for X). On the 73 on-topic training posts title-only and 100, 150, 300,
   600 and 1000 characters scored 56 to 62%, within three posts of each other, so 300
   is a robustness choice, not a tuned one. The held-out set was not used.

7. **Tenant (2026-11-06):** keep `demo` for collectors, labels and rules until the first
   real review record is stored; then revisit.
8. **Held-out sample (2026-11-06):** drawn with a fixed seed, never labelled and never
   used to write or tune a rule: `pilot_holdout_youtube.csv` (40 posts) and
   `pilot_holdout_x.csv` (20 posts), local untracked files in the repo root with id,
   title and link only. The pilot owner labels them; load with
   `social-intelligence-pilot-labels --label-source human`.

Still unresolved: which tenant owns the rules and how a second tenant gets a
taxonomy; who may edit rules and how a PR becomes an `enabled` data change; how X
posts, which have no real title, are matched; the retention treatment of labelled
posts; and the name of the second labeller.

## Not verified

No rule has been written or tested. Topic counts come from two model-labelled
samples. The distribution table in Problem is a read-only query on the dev
workspace on 2026-11-05. Code references were read from the repository, not from a
deployed run. The reviewer's regex and statistical points (Java versus Python
behavior, the n=20 power estimate, the cross-join cost) are inferred, not run.
