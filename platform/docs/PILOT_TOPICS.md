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
3. **Normalization and matching in Silver.** Added columns and the long table.
   Acceptance: Silver row count and `topic` unchanged, with a guard that
   `COUNT(*)` equals `COUNT(DISTINCT post_id)`.
4. **Quality report and rule yield.** Read-only, Wilson bounds, held-out split.
   Acceptance: runs cleanly when there are no labels.
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
6. **Matching text:** the description length N and title-only versus title plus
   description are settled by scoring both on the training set, not by argument.

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
