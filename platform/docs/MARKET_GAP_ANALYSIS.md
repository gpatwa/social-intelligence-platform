# Market gap analysis and pilot positioning hypothesis

Status: first pass, 2026-10-16/17. Built from web searches and a few
official pages. Most competitor claims come from vendor-written articles, so
this is a set of hypotheses to test in the pilot, not a validated market study.
Items marked **verified** were read on the provider's own page; **reported**
means a secondary source only.

## Findings that change the plan

1. **Agent-callable social data is no longer white space.**
   - Sprinklr announced an MCP connector (beta) on 2026-07-15 and lists an
     "Insights MCP" in its 26.10 release (verified on sprinklr.com; the pages do
     not say which datasets are exposed, whether it is generally available, or
     what tenant controls exist).
   - Meltwater has an MCP server described as generally available (reported).
   - X documents an official hosted MCP server at `https://api.x.com/mcp`
     (verified on docs.x.com), covering post search, users, trends and news.
   - No official Brandwatch or Talkwalker MCP found (absence in search, not proof).
   - Consequence: "we expose MCP" cannot be the differentiator. Governance and
     the evidence-to-decision loop have to be.
2. **X access is metered and capped.** Pay-per-usage, no subscription, $0.005
   per post read, 3 million post reads per monthly cycle, higher volume needs
   Enterprise (verified). The page does not address commercial use or
   redistribution; confirm eligibility in the X developer terms before
   building a paid product on it.
3. **Reddit is gated for commercial use.** Reddit's own help page returned
   HTTP 403 to automated fetch. Secondary sources report that self-service
   access closed in November 2025, commercial use needs explicit written
   approval, and AI training on user content is not granted by default
   (reported). Keep Reddit out of the pilot and read Reddit's Data API Terms
   directly before applying.

## Where we should not compete

- Broad social listening and historical archives (Brandwatch, Sprinklr,
  Meltwater, Talkwalker, and cheaper tools).
- Incrementality and marketing-mix measurement (Haus, Measured, Recast and
  platform-native lift tools). Our aggregate-only, non-causal measurement is
  a pilot control, not a measurement product.
- Generic agent-framework comparisons. Many guides exist; the advisor only
  matters when tied to evidence and a buyer's constraints.

## Candidate differentiation (to test)

| Claim | Evidence in repo | Evidence needed |
|---|---|---|
| Every recommendation links to ranked, directly cited sources | Evidence ranking, recommendation context, citation checks | Reviewers confirm citations are what they would have checked themselves |
| Human approval is attributable and enforced at the write boundary | Append boundary binds reviewer to authenticated actor | A real reviewer completes a run |
| Evidence connects to a test and an aggregate result in one auditable chain | Review, experiment, measurement records with lineage checks | One real chain, not synthetic |
| Built for teams choosing and building AI-agent workflows | Agent Stack Advisor, pilot workspace | A named audience that says this saves them time |

## Positioning hypothesis

For teams building enterprise AI-agent workflows, a governed evidence layer
that turns YouTube and X signals into cited, human-approved, testable
recommendations, callable by agents, with a traceable path to a measured
result. The audience, brand and offer are not decided; this is a hypothesis,
not a choice.

## Open risks

- Incumbents are shipping MCP and AI layers quickly; the window may be short.
- X per-read cost and cap bound how much evidence a pilot can collect.
- Whether anyone will pay for this is untested. No buyer interviews yet.

## Still to verify

- X developer terms on commercial use and redistribution.
- Reddit Data API Terms and Responsible Builder Policy, read directly.
- Sprinklr and Meltwater MCP scope, pricing and data coverage.
- Bright Data and Apify social coverage and terms, if used as a fallback.
- Buyer-side demand: five to ten conversations with the chosen audience.

## Sources

- Sprinklr: [Summer '26 announcement](https://www.sprinklr.com/newsroom/sprinklr-introduces-new-ai-capabilities-to-help-brands-move-from-insights-to-real-time-customer-action/), [26.10 release](https://www.sprinklr.com/releases/26-10-release/)
- X: [pricing](https://docs.x.com/x-api/getting-started/pricing), [MCP](https://docs.x.com/tools/mcp)
- Meltwater: [MCP](https://www.meltwater.com/en/blog/meltwater-mcp) (vendor blog)
- Category overviews (vendor-authored): [Revuze](https://www.revuze.it/blog/16-best-social-listening-tools-2026/), [SegmentStream](https://segmentstream.com/blog/articles/top-10-incrementality-testing-tools), [N-iX](https://www.n-ix.com/langgraph-vs-crewai-vs-autogen/)
