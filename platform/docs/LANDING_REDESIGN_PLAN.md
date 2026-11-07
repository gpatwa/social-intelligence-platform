# Landing page redesign plan

**Status: plan only. Nothing here is built or published.** Written 2026-11-07 after
a designer review (a Principal Product Designer agent given screenshots of the live
page at 1440px and 390px, the page source, and the facts below) and a check of its
main claims against the code. The public site is redeployed only when the owner says so.

## Why

The page has real material (a computed status panel, evidence rows that link to real
sources, a readiness section that admits what is missing) but it argues against
itself. The first screen shows a decorative dashboard marked "Operational" and a line
saying "Discovery and serving are live"; the real status panel on the same screen can
read STALE. For an engineering lead, one caught contradiction makes the rest look
false. It also does not show the product's actual differentiator: cited evidence, a
named human approver, and measured results, including unflattering ones.

## Verified findings

Checked against the code, not only the screenshots:

- **Typed status contradicts computed status.** "Operational", "Discovery and serving
  are live" and per-source "Live" are fixed text in `app/page.tsx`; the worker marks
  a run STALE after 180 minutes (`worker/index.ts:114`). In the last two weeks X
  collection failed for lack of prepaid credits and the pipeline stalled for days
  while the typed copy still said live.
- **The hero is decoration.** The bars are a hard-coded array (`page.tsx:210`), the
  "4 decision stages" card counts slide boxes, and it says "Two sources" (`:238`)
  while the copy names three.
- **The proof strip is stale and unsourced:** 22 marts, "111 automated checks" (the
  real count is now over 230), "100% verified end-to-end run" with no date; the
  linked CI run is months old.
- **Layout breaks.** Grid minimums of 480px and 560px (`globals.css:134, 584, 1489`)
  are not overridden at 680px and below; the designer saw overflow at 390px and an
  input overlapping the evidence list on desktop (inferred from screenshots, to be
  reproduced in slice 1).
- **Legibility.** 29 declarations at 8 to 9px. The accent `#ff6b4a` is used as text
  on ivory at about 2.7:1, which fails WCAG AA even for large text (computed).
- **The primary call to action dead-ends** at a Databricks login wall and puts an
  internal workspace host and dashboard id on a public page (not a secret, but it
  should not be public).
- **Status scope is narrow and noisy for screen readers:** telemetry covers YouTube
  only, and the whole status section is `aria-live` and refreshes every 60 seconds.
- Missing: any real ranked-evidence row with its why-ranked reasons, the
  APPROVE/EDIT/REJECT step, and the measured-quality result.

## Direction

**Narrative:** every recommendation here is cited, reviewed by a named human, and
measured, including when the numbers are unflattering. **Audience:** engineering and
platform leads choosing an agent stack. Marketing and campaign language moves off the
main path.

### Storyboard

1. **Hero: a real decision record.** One recommendation card built from real data:
   title, three cited sources with links, topic, the review step, and a footer reading
   "Snapshot, date, source table". No chart.
2. **Live state strip.** Per-source collector state, run age and quota, all computed.
3. **Evidence.** The top five ranked rows from a dated snapshot: source link,
   platform, topic and why-ranked reasons.
4. **Decision lifecycle.** The human gate: Opportunity, Recommendation, Review
   (APPROVE, EDIT or REJECT), Experiment, then GO, ITERATE or STOP. Review is
   visually heaviest. Source: `platform/docs/diagrams/decision-lifecycle.html`.
5. **Measured quality.** The differentiator: held-out size, accuracy, the gate, how
   many topics passed, who made the labels.
6. **Architecture and access.** The data-flow diagram, Databricks as system of
   record, Snowflake read-only, MCP tenant-scoped read tools.
7. **Pilot workspace and stack advisor**, merged and collapsed by default.
8. **Readiness ledger**, current content plus dates.
9. **Call to action:** "Run a pilot on your workflow" and "Read the source". No
   Databricks link.

### Visual system

- **Type:** one family for text; a mono face only for data, timestamps and ids, never
  below 12px. Drop the serif italic in the hero.
- **Color roles:** ink on paper for text; one accent for actions only, darkened so it
  passes AA as text (about `#c2410c` on ivory, to be measured); status colors used
  only for status, always with an icon and a word (ok, stale, failed, unknown); no
  light-green text on light backgrounds.
- **Grid:** 12 columns at 1200px, 4 at 680px and below, no fixed minimum above 280px.
- **Data rule:** every figure carries its source and an "as of" time. Bars only where
  there is a real series. An empty value renders "-" and the reason.

### Components worth building

- **EvidenceRow:** rank, title linked to the source, platform, topic, two or three
  why-ranked chips, capture date. No author profile.
- **LifecycleStepper:** a keyboard-operable disclosure list of the five steps.
- **MeasuredResultCard:** metric, sample size, gate, pass or fail, caveat, date, link.

## Honest-claims rules (apply to every slice)

- No status word in markup. "Live", "operational" and "healthy" come from the worker,
  per source, with the run age beside them. Extend telemetry beyond YouTube before
  claiming X or GitHub status. If the endpoint fails, show "Status unavailable", not
  the last good value.
- Counts (tests, marts) are exported to a JSON file by CI; the page renders them "as
  of date" and shows the date prominently when it is old.
- Pattern for an unflattering metric: "[Metric]: [value] on [n held-out items], [date].
  Gate: [threshold]; [k of m] passed. Labels: [method and who chose it]. Next:
  [specific action]." For today's result: "Primary topic accuracy: 53% on 60 held-out
  posts. Gate: 40 gold examples per topic and a 0.7 precision lower bound; 0 topics
  passed. Gold labels come from a model labeller chosen by the pilot owner. Next:
  revise rules and re-measure on a fresh sample."
- No invented customers, logos, quotes or metrics. No individual-level content: posts
  appear by source link and derived fields, not by author.

## Mobile and accessibility

- At 680px and below the hero card stacks under the headline, the evidence row keeps
  rank, title and link with chips wrapping, the stepper becomes a vertical list, and
  the workspace form goes to one column. The status strip and results card stay.
- Focus order: skip link, nav, hero actions, status strip, evidence links, stepper.
- A status change is announced once through a small `role="status"` node holding only
  the summary sentence; remove `aria-live` from whole sections. Visible focus rings.
  External links say "(opens source)".
- Honor `prefers-reduced-motion` for every new component (no animated bars or
  pulsing dots).

## Phased plan (each slice its own PR; slice 1 is shippable alone and reversible)

1. **Truth patch.** Delete the typed status lines and the proof strip; replace the
   fake hero console with a static, dated evidence card; remove the dashboard and old
   run links; fix the overflow minimums and the input overlap; raise 8 to 9px labels
   to 12px; fix the accent contrast. Verify: no `Live`, `Operational`, `111` or `100%`
   in markup; no horizontal scroll at 390px; an accessibility audit pass; the rendered
   HTML test updated.
2. **Per-source status.** Worker reports state and age per source; status strip;
   stale thresholds per source (GitHub is collected daily). Verify: unit tests for
   stale, failed and unavailable responses.
3. **Evidence and results.** EvidenceRow from a CI-exported snapshot; MeasuredResultCard
   with the current held-out result and its caveats. Verify: the snapshot date renders
   and every link resolves.
4. **Lifecycle and architecture.** The stepper and the ported diagrams. Verify: a
   keyboard-only walk and a screen-reader pass.
5. **Restructure.** Reorder and merge sections, cut copy, update the nav. Verify:
   Lighthouse performance and accessibility at or above 95, and a 390px capture.

**Cut:** the fake console, proof strip, operational note, the capabilities grid (it
repeats the decision loop), the Databricks dashboard links and the old run link.
**Defer:** campaign and ad-spend language, the unexplained "92 fit score", and the
connector roadmap (it folds into the readiness ledger).

## Decisions and recommendations (for the owner; defaults used if no objection)

1. **Can the evidence snapshot be public?** Recommended: show the post link, platform,
   topic and why-ranked reasons, not the post text or author, since platforms
   restrict redistributing content. Check each platform's terms before slice 3.
2. **One audience?** Recommended yes: platform leads. Campaign content moves to a
   separate page later.
3. **Publish 53% and "0 topics passed"?** Recommended yes, in slice 3 below the hero,
   with the full caveat. It is the differentiator and the page's own principle. The
   owner confirms at publish time.
4. **Stale thresholds per source:** yes (slice 2).
5. **Remove the dashboard URL?** Remove from the page in slice 1; the repository
   history keeps it, which is acceptable because it is not a credential.

## What is not decided here

Final typography choices, exact copy, and whether the stack advisor and pilot
workspace stay on the home page or move. Contrast figures come from the designer's
screenshots and one computed ratio; measure with a tool in slice 1.
